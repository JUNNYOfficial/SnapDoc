"""
PDF转Markdown工具 - Gradio Web界面
基于MinerU API实现PDF批量转换
"""

import gradio as gr
import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime

from mineru_api import MinerUAPI


CONFIG_FILE = "pdf2md_config.json"
MAX_TOKEN_HISTORY = 10
LOG_DIR = "logs"


def setup_logging():
    """设置日志记录"""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"{timestamp}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    return log_file


LOG_FILE = setup_logging()
logging.info(f"应用启动，日志文件: {LOG_FILE}")


def load_config() -> dict:
    """加载配置文件"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {
        "token_history": [],
        "model_version": "vlm",
        "enable_formula": True,
        "enable_table": True,
        "language": "ch",
        "rate_limit": 2
    }


def save_config(config: dict):
    """保存配置文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except:
        pass


def add_token_to_history(token: str, config: dict):
    """添加token到历史记录"""
    if not token or len(token) < 10:
        return
    
    history = config.get("token_history", [])
    
    if token in history:
        history.remove(token)
    
    history.insert(0, token)
    
    if len(history) > MAX_TOKEN_HISTORY:
        history = history[:MAX_TOKEN_HISTORY]
    
    config["token_history"] = history
    save_config(config)


def format_size(size: int) -> str:
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_output_dir(user_output_dir: str = None) -> str:
    """获取输出目录

    Args:
        user_output_dir: 用户指定的输出目录

    Returns:
        输出目录路径
    """
    # 优先使用用户指定的目录
    if user_output_dir and user_output_dir.strip():
        output_dir = user_output_dir.strip()
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    # 默认使用用户下载目录下的PDF2MD_Output文件夹
    default_dir = str(Path.home() / "Downloads" / "PDF2MD_Output")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def parse_pdf_files(file_obj):
    """处理上传的PDF文件"""
    if file_obj is None:
        return [], "请上传PDF文件"
    
    file_paths = []
    if isinstance(file_obj, list):
        for f in file_obj:
            if hasattr(f, 'name'):
                file_paths.append(f.name)
    else:
        if hasattr(file_obj, 'name'):
            file_paths = [file_obj.name]
    
    if not file_paths:
        return [], "未找到有效的PDF文件"
    
    files_info = []
    for fp in file_paths:
        if os.path.exists(fp):
            size = os.path.getsize(fp)
            files_info.append(f"{os.path.basename(fp)} ({format_size(size)})")
    
    return file_paths, "\n".join(files_info) if files_info else "未找到有效的PDF文件"


def convert_process(
    token: str,
    files,
    output_dir_input: str,
    model_version: str,
    enable_formula: bool,
    enable_table: bool,
    language: str,
    rate_limit: float,
    progress=gr.Progress()
):
    """转换处理函数"""
    logging.info("开始转换任务")

    if not token or len(token) < 10:
        logging.error("无效的API Token")
        yield "错误: 请输入有效的API Token", ""
        return

    config = load_config()
    add_token_to_history(token, config)

    file_paths, file_info = parse_pdf_files(files)
    if not file_paths:
        logging.error("未找到有效的PDF文件")
        yield "错误: 请上传PDF文件", ""
        return

    if len(file_paths) > 200:
        logging.error("文件数量超过限制: 200")
        yield "错误: 单次最多支持200个文件", ""
        return
    
    output_dir = get_output_dir(output_dir_input)
    logging.info(f"输出目录: {output_dir}")
    
    try:
        requests_per_second = 1.0 / max(rate_limit, 1.0)
    except:
        requests_per_second = 0.5
    
    api = MinerUAPI(token, requests_per_second=requests_per_second)
    
    total = len(file_paths)
    progress(0, desc="正在上传文件...")
    logging.info(f"开始上传 {total} 个文件")
    
    batch_result = api.batch_upload_files(
        file_paths=file_paths,
        model_version=model_version,
        enable_formula=enable_formula,
        enable_table=enable_table,
        language=language
    )
    
    tasks = batch_result.tasks
    logging.info(f"文件上传完成，批次ID: {batch_result.batch_id}")
    yield f"已上传 {len(tasks)} 个文件，等待解析中...", ""
    
    progress(0.1, desc="等待解析完成...")
    logging.info("等待解析完成...")
    
    check_interval = 3
    while True:
        result = api.get_batch_results(batch_result.batch_id)
        extract_results = result.get("extract_result", [])
        
        all_done = True
        done_count = 0
        
        for extract_result in extract_results:
            file_name = extract_result.get("file_name", "")
            state = extract_result.get("state", "")
            
            for task in tasks:
                if task.file_name == file_name:
                    task.state = state
                    task.error_msg = extract_result.get("err_msg", "")
                    task.zip_url = extract_result.get("full_zip_url", "")
                    
                    progress_data = extract_result.get("extract_progress", {})
                    task.extracted_pages = progress_data.get("extracted_pages", 0)
                    task.total_pages = progress_data.get("total_pages", 0)
                    
                    if state not in ["done", "failed"]:
                        all_done = False
                    else:
                        done_count += 1
                    break
        
        if all_done:
            break
        
        progress(0.1 + 0.7 * (done_count / total), desc=f"解析中 {done_count}/{total}")
        logging.info(f"解析进度: {done_count}/{total}")
        time.sleep(check_interval)
    
    progress(0.8, desc="下载结果...")
    logging.info("解析完成，开始下载结果...")
    
    results = api.download_all_results(
        tasks=tasks,
        output_dir=output_dir
    )
    
    success_count = sum(1 for t in tasks if t.state == "done")
    fail_count = sum(1 for t in tasks if t.state == "failed")
    logging.info(f"转换完成，成功: {success_count}, 失败: {fail_count}")
    
    result_msg = f"转换完成！\n成功: {success_count}, 失败: {fail_count}\n输出目录: {output_dir}"
    
    if fail_count > 0:
        result_msg += "\n失败文件:\n"
        for task in tasks:
            if task.state == "failed":
                result_msg += f"- {task.file_name}: {task.error_msg}\n"
                logging.error(f"文件转换失败: {task.file_name} - {task.error_msg}")
    
    progress(1.0, desc="完成")
    logging.info("转换任务完成")

    yield result_msg, output_dir


def mask_token(token: str) -> str:
    """对token进行脱敏处理，只显示前4位和后4位"""
    if not token or len(token) < 10:
        return token
    return f"{token[:4]}...{token[-4:]}"


def get_token_choices():
    """获取token历史下拉选项（脱敏显示）"""
    config = load_config()
    history = config.get("token_history", [])
    if history:
        # 返回 (显示标签, 实际值) 的元组列表
        choices = [("", "")]
        for token in history:
            choices.append((mask_token(token), token))
        return choices
    return [("", "")]


def create_app():
    """创建Gradio应用"""
    config = load_config()
    
    with gr.Blocks(title="PDF转Markdown工具") as demo:
        gr.Markdown("# PDF转Markdown工具\n基于MinerU API实现PDF批量转换\n\n**输出目录默认为 ~/Downloads/PDF2MD_Output**")
        
        with gr.Row():
            with gr.Column(scale=2):
                with gr.Row():
                    token_input = gr.Textbox(
                        label="MinerU API Token",
                        placeholder="请输入API Token",
                        type="password"
                    )
                with gr.Row():
                    token_history = gr.Dropdown(
                        label="历史记录",
                        choices=get_token_choices(),
                        value=""
                    )
                    def on_token_select(selected):
                        return selected
                    token_history.change(
                        fn=on_token_select,
                        inputs=[token_history],
                        outputs=[token_input]
                    )
            
            with gr.Column(scale=1):
                gr.Markdown("* Token可在 [MinerU官网](https://mineru.net) 获取<br>* 历史记录会自动保存")
        
        with gr.Row():
            file_input = gr.File(
                label="上传PDF文件",
                file_count="multiple",
                file_types=[".pdf"]
            )

        with gr.Row():
            output_dir_input = gr.Textbox(
                label="输出目录（可选，留空则使用默认目录）",
                placeholder="留空则使用 ~/Downloads/PDF2MD_Output"
            )
        
        with gr.Row():
            with gr.Column():
                model_version_input = gr.Dropdown(
                    label="模型版本",
                    choices=["vlm", "pipeline"],
                    value=config.get("model_version", "vlm")
                )
                gr.Markdown("""
**模型说明：**
- **vlm**: 视觉语言模型，适合复杂文档（含公式、表格、多栏排版），解析质量更高
- **pipeline**: 传统流水线方式，速度快，适合简单文档（纯文字、标准排版）
                """)
            
            with gr.Column():
                language_input = gr.Dropdown(
                    label="语言",
                    choices=["ch", "en", "japan", "korean", "french", "german"],
                    value=config.get("language", "ch")
                )
            
            with gr.Column():
                rate_limit_input = gr.Slider(
                    label="请求间隔(秒)",
                    minimum=1,
                    maximum=10,
                    value=config.get("rate_limit", 2),
                    step=1
                )
        
        with gr.Row():
            with gr.Column():
                enable_formula_input = gr.Checkbox(
                    label="启用公式识别",
                    value=config.get("enable_formula", True)
                )
            
            with gr.Column():
                enable_table_input = gr.Checkbox(
                    label="启用表格识别",
                    value=config.get("enable_table", True)
                )
        
        convert_btn = gr.Button("开始转换", variant="primary")
        
        with gr.Row():
            output_text = gr.Textbox(
                label="转换结果",
                lines=5
            )
        
        with gr.Row():
            output_dir_display = gr.Textbox(
                label="输出目录",
                interactive=False
            )
        
        convert_btn.click(
            fn=convert_process,
            inputs=[
                token_input,
                file_input,
                output_dir_input,
                model_version_input,
                enable_formula_input,
                enable_table_input,
                language_input,
                rate_limit_input
            ],
            outputs=[output_text, output_dir_display]
        )
    
    return demo


if __name__ == "__main__":
    demo = create_app()
    demo.launch(server_name="0.0.0.0", server_port=7860)