# douyin-text-extract 🎬➡️📝

抖音视频文案提取工具 — 输入抖音链接，自动下载视频并转录为文字。

## 工作原理

1. **Playwright** 自动化浏览器访问抖音页面，拦截视频流请求
2. **httpx** 下载视频到本地
3. **faster-whisper** (OpenAI Whisper 加速版) 识别语音，转录为中文文字

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> ffmpeg 也需要安装。Windows 用户可使用 `winget install Gyan.FFmpeg`

### 2. 使用

```bash
# 从抖音链接提取文案
python extract.py https://v.douyin.com/xxxxx/

# 从本地视频文件提取
python extract.py --file video.mp4

# 使用更快的模型
python extract.py https://v.douyin.com/xxxxx/ --model small
```

### 3. 输出

转录结果保存在 `output/` 目录下，以视频标题命名的 `.txt` 文件。

## 语音模型选择

| 模型 | 速度 | 准确度 | 适用场景 |
|------|------|--------|----------|
| `tiny` | ⚡⚡⚡ | ⭐ | 快速预览 |
| `base` | ⚡⚡ | ⭐⭐ | 简单内容 |
| `small` | ⚡ | ⭐⭐⭐ | 日常使用 |
| `medium` | 🐢 | ⭐⭐⭐⭐ | **推荐**，中文效果好 |
| `large` | 🐌 | ⭐⭐⭐⭐⭐ | 最高准确度 |

首次使用会自动下载模型文件（medium 约 1.5GB）。

## 项目结构

```
douyin-extract/
├── extract.py          # 主程序
├── requirements.txt    # Python 依赖
├── README.md           # 项目说明
├── LICENSE             # MIT 开源协议
└── output/             # 输出目录 (自动创建)
```

## 注意事项

- 首次运行需要下载 Whisper 模型，请耐心等待
- 中文视频建议使用 `medium` 或 `large` 模型
- 背景音乐可能影响识别准确度
- 仅限个人学习研究使用，请遵守抖音用户协议

## License

[MIT](LICENSE)
