"""
MinerU API 封装模块
用于批量上传PDF文件并转换为Markdown
"""

import requests
import time
import os
import zipfile
import io
import threading
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class RateLimiter:
    """请求限速器，防止API被限速"""
    
    def __init__(self, requests_per_second: float = 1.0, min_interval: float = 1.0):
        """
        Args:
            requests_per_second: 每秒最大请求数
            min_interval: 最小请求间隔(秒)
        """
        self.min_interval = max(1.0 / requests_per_second, min_interval)
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait(self):
        """等待直到可以发送下一个请求"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_request_time = time.time()


class TaskState(Enum):
    WAITING_FILE = "waiting-file"
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CONVERTING = "converting"


@dataclass
class FileTask:
    """单个文件任务信息"""
    file_path: str
    file_name: str
    data_id: str
    state: str = "pending"
    progress: int = 0
    total_pages: int = 0
    extracted_pages: int = 0
    zip_url: str = ""
    error_msg: str = ""


@dataclass
class BatchResult:
    """批量任务结果"""
    batch_id: str
    file_urls: List[str]
    tasks: List[FileTask]


class MinerUAPI:
    """MinerU API 客户端"""
    
    BASE_URL = "https://mineru.net/api/v4"
    
    def __init__(self, token: str, requests_per_second: float = 0.5):
        """
        Args:
            token: MinerU API Token
            requests_per_second: 每秒最大请求数，默认0.5（即每2秒1个请求）
        """
        self.token = token
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        self.rate_limiter = RateLimiter(requests_per_second=requests_per_second, min_interval=2.0)
        self.max_retries = 3
        self.retry_delay = 5  # 重试延迟(秒)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """发送API请求，带限速和重试"""
        url = f"{self.BASE_URL}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                # 限速等待
                self.rate_limiter.wait()
                
                response = requests.request(method, url, headers=self.headers, timeout=60, **kwargs)
                
                # 处理限速响应
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay * (attempt + 1)))
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                result = response.json()
                
                if result.get("code") != 0:
                    error_code = result.get('code')
                    # 如果是限速相关错误，重试
                    if error_code in [-60009]:  # 任务提交队列已满
                        time.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise Exception(f"API错误: {result.get('msg', '未知错误')} (code: {error_code})")
                
                return result
                
            except requests.exceptions.Timeout:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise
            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise
        
        raise Exception("请求失败，已达最大重试次数")
    
    def batch_upload_files(
        self, 
        file_paths: List[str],
        model_version: str = "vlm",
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        progress_callback: Optional[Callable[[str, int], None]] = None
    ) -> BatchResult:
        """
        批量上传本地文件进行解析
        
        Args:
            file_paths: 本地文件路径列表
            model_version: 模型版本 (pipeline/vlm)
            enable_formula: 是否开启公式识别
            enable_table: 是否开启表格识别
            language: 文档语言
            progress_callback: 进度回调函数 (file_name, progress)
        
        Returns:
            BatchResult: 批量任务结果
        """
        # 准备文件信息
        files_data = []
        tasks = []
        for i, file_path in enumerate(file_paths):
            file_name = os.path.basename(file_path)
            data_id = f"paper_{i}_{int(time.time())}"
            files_data.append({
                "name": file_name,
                "data_id": data_id
            })
            tasks.append(FileTask(
                file_path=file_path,
                file_name=file_name,
                data_id=data_id
            ))
        
        # 申请上传链接
        request_data = {
            "files": files_data,
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language
        }
        
        result = self._request("POST", "file-urls/batch", json=request_data)
        batch_id = result["data"]["batch_id"]
        file_urls = result["data"]["file_urls"]
        
        # 上传文件（带限速）
        for i, (file_path, upload_url) in enumerate(zip(file_paths, file_urls)):
            if progress_callback:
                progress_callback(tasks[i].file_name, 0)
            
            # 限速等待
            self.rate_limiter.wait()
            
            # 重试上传
            for attempt in range(self.max_retries):
                try:
                    with open(file_path, 'rb') as f:
                        upload_response = requests.put(upload_url, data=f, timeout=300)
                        if upload_response.status_code == 200:
                            tasks[i].state = "pending"
                            if progress_callback:
                                progress_callback(tasks[i].file_name, 10)
                            break
                        elif upload_response.status_code == 429:
                            # 被限速，等待后重试
                            time.sleep(self.retry_delay * (attempt + 1))
                            continue
                        else:
                            if attempt == self.max_retries - 1:
                                tasks[i].state = "failed"
                                tasks[i].error_msg = f"上传失败: HTTP {upload_response.status_code}"
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        tasks[i].state = "failed"
                        tasks[i].error_msg = f"上传异常: {str(e)}"
                    else:
                        time.sleep(self.retry_delay)
        
        return BatchResult(
            batch_id=batch_id,
            file_urls=file_urls,
            tasks=tasks
        )
    
    def get_batch_results(self, batch_id: str) -> Dict:
        """
        获取批量任务结果
        
        Args:
            batch_id: 批量任务ID
        
        Returns:
            任务结果字典
        """
        result = self._request("GET", f"extract-results/batch/{batch_id}")
        return result["data"]
    
    def wait_for_completion(
        self,
        batch_id: str,
        tasks: List[FileTask],
        progress_callback: Optional[Callable[[str, str, int, int], None]] = None,
        check_interval: int = 5,
        timeout: int = 3600
    ) -> List[FileTask]:
        """
        等待批量任务完成
        
        Args:
            batch_id: 批量任务ID
            tasks: 任务列表
            progress_callback: 进度回调 (file_name, state, extracted_pages, total_pages)
            check_interval: 检查间隔(秒)
            timeout: 超时时间(秒)
        
        Returns:
            更新后的任务列表
        """
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                raise TimeoutError("任务超时")
            
            result = self.get_batch_results(batch_id)
            extract_results = result.get("extract_result", [])
            
            all_done = True
            for extract_result in extract_results:
                file_name = extract_result.get("file_name", "")
                state = extract_result.get("state", "")
                
                # 查找对应的任务
                for task in tasks:
                    if task.file_name == file_name:
                        task.state = state
                        task.error_msg = extract_result.get("err_msg", "")
                        task.zip_url = extract_result.get("full_zip_url", "")
                        
                        progress = extract_result.get("extract_progress", {})
                        task.extracted_pages = progress.get("extracted_pages", 0)
                        task.total_pages = progress.get("total_pages", 0)
                        
                        if progress_callback:
                            progress_callback(
                                file_name, 
                                state, 
                                task.extracted_pages, 
                                task.total_pages
                            )
                        
                        if state not in ["done", "failed"]:
                            all_done = False
                        break
            
            if all_done:
                break
            
            time.sleep(check_interval)
        
        return tasks
    
    def download_result(
        self, 
        zip_url: str, 
        output_dir: str,
        output_filename: str = None,
        extract_markdown: bool = True
    ) -> str:
        """
        下载并解压结果
        
        Args:
            zip_url: 结果压缩包URL
            output_dir: 输出目录
            output_filename: 输出文件名（不含扩展名），如果指定则直接命名为 {output_filename}_markdown.md
            extract_markdown: 是否只提取markdown文件
        
        Returns:
            输出文件路径
        """
        response = requests.get(zip_url)
        response.raise_for_status()
        
        os.makedirs(output_dir, exist_ok=True)
        
        output_path = None
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            if extract_markdown:
                # 提取markdown文件和images文件夹
                md_content = None
                images_prefix = None
                
                # 先找到md文件和images目录前缀
                for name in zf.namelist():
                    if name.endswith('.md') and md_content is None:
                        md_content = zf.read(name)
                        # 获取md文件所在目录作为images的相对路径基准
                        md_dir = os.path.dirname(name)
                        if md_dir:
                            images_prefix = f"{md_dir}/images/"
                        else:
                            images_prefix = "images/"
                
                if md_content:
                    # 保存md文件
                    if output_filename:
                        final_name = f"{output_filename}_markdown.md"
                    else:
                        final_name = "output.md"
                    output_path = os.path.join(output_dir, final_name)
                    
                    # 创建该文件专属的images目录
                    if output_filename:
                        images_dir = os.path.join(output_dir, f"{output_filename}_images")
                    else:
                        images_dir = os.path.join(output_dir, "images")
                    
                    # 提取所有图片到images目录
                    for name in zf.namelist():
                        if '/images/' in name or name.startswith('images/'):
                            # 获取图片文件名
                            img_filename = os.path.basename(name)
                            if img_filename:  # 排除目录本身
                                os.makedirs(images_dir, exist_ok=True)
                                img_content = zf.read(name)
                                img_path = os.path.join(images_dir, img_filename)
                                with open(img_path, 'wb') as f:
                                    f.write(img_content)
                    
                    # 修改md内容中的图片路径
                    md_text = md_content.decode('utf-8')
                    if output_filename:
                        # 替换 images/ 为 {output_filename}_images/
                        md_text = md_text.replace('](images/', f']({output_filename}_images/')
                        md_text = md_text.replace('](./images/', f']({output_filename}_images/')
                    
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(md_text)
            else:
                # 解压所有文件
                zf.extractall(output_dir)
                output_path = output_dir
        
        return output_path
    
    def download_all_results(
        self,
        tasks: List[FileTask],
        output_dir: str,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, str]:
        """
        下载所有成功任务的结果
        
        Args:
            tasks: 任务列表
            output_dir: 输出目录
            progress_callback: 进度回调 (file_name, current, total)
        
        Returns:
            文件名到输出路径的映射
        """
        results = {}
        successful_tasks = [t for t in tasks if t.state == "done" and t.zip_url]
        total = len(successful_tasks)
        
        for i, task in enumerate(successful_tasks):
            if progress_callback:
                progress_callback(task.file_name, i + 1, total)
            
            try:
                # 直接输出到指定目录，命名为 PDF名字_markdown.md
                pdf_name = os.path.splitext(task.file_name)[0]  # 去掉.pdf扩展名
                output_path = self.download_result(
                    task.zip_url, 
                    output_dir, 
                    output_filename=pdf_name
                )
                results[task.file_name] = output_path
            except Exception as e:
                results[task.file_name] = f"下载失败: {str(e)}"
        
        return results


def test_token(token: str) -> bool:
    """测试Token是否有效"""
    try:
        api = MinerUAPI(token)
        # 尝试一个简单的请求来验证token
        # 由于没有专门的验证接口，我们通过格式检查
        if not token or len(token) < 10:
            return False
        return True
    except:
        return False
