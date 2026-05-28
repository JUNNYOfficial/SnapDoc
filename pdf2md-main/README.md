# PDF 转 Markdown 工具

基于 MinerU API 实现的 PDF 批量转换工具，提供 Gradio Web 界面，支持将 PDF 文件转换为 Markdown 格式。

## 功能特性

- 📄 **批量转换**：支持一次上传最多 200 个 PDF 文件
- 🔄 **多种模型**：支持 VLM（视觉语言模型）和 Pipeline 两种解析模式
- 🌍 **多语言支持**：支持中文、英文、日语、韩语、法语、德语
- 📊 **智能识别**：可选启用公式识别和表格识别
- 💾 **历史记录**：自动保存 API Token 历史记录
- 📝 **日志记录**：完整的操作日志记录

## 依赖安装

```bash
pip install -r requirements.txt
```

依赖：
- `requests>=2.28.0`
- `gradio>=4.0.0`

## 使用方法

### 1. 获取 API Token

访问 [MinerU 官网](https://mineru.net) 注册并获取 API Token。

### 2. 启动应用

```bash
conda activate dl && python app.py
```

启动后访问 `http://localhost:7860` 即可使用。

### 3. 配置参数

| 参数 | 说明 |
|------|------|
| **API Token** | MinerU 平台的认证令牌 |
| **模型版本** | `vlm`：视觉语言模型，适合复杂文档；`pipeline`：传统流水线，速度更快 |
| **语言** | 选择文档主要语言，提高识别准确率 |
| **请求间隔** | API 请求间隔时间（秒），默认 2 秒 |
| **公式识别** | 启用后可识别并转换数学公式 |
| **表格识别** | 启用后可识别并转换表格 |

### 4. 输出

转换后的 Markdown 文件默认保存在 `~/Downloads/PDF2MD_Output/` 目录，也可在界面上指定自定义输出路径。

## 项目结构

```
pdf2md/
├── app.py              # Gradio Web 界面主程序
├── mineru_api.py       # MinerU API 封装
├── requirements.txt    # 依赖列表
├── pdf2md_config.json  # 配置文件（自动生成）
└── logs/               # 日志目录（自动生成）
```

## 注意事项

1. 需要有效的 MinerU API Token 才能使用
2. 大文件或多文件转换可能需要较长时间，请耐心等待
3. 日志文件按时间戳命名，保存在 `logs/` 目录下

## License

MIT
