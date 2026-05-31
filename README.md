# douyin-text-extract 🎬➡️📝

抖音视频文案提取工具 — 输入抖音链接，自动下载视频并转录为文字。

支持两种模式：
- **单视频模式** — 输入链接，提取单个视频文案
- **收藏夹模式** — 自动抓取抖音收藏夹，批量提取并生成汇总

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

### 2. 单视频提取

```bash
# 从抖音链接提取文案
python extract.py https://v.douyin.com/xxxxx/

# 从本地视频文件提取
python extract.py --file video.mp4

# 使用更快的模型
python extract.py https://v.douyin.com/xxxxx/ --model small
```

转录结果保存在 `output/` 目录下，以视频标题命名的 `.txt` 文件。

### 3. 收藏夹批量提取

```bash
# 首次使用：登录并保存状态
python favorites.py --login

# 交互式选择视频
python favorites.py

# 自动处理所有收藏
python favorites.py --all

# 只处理最近 10 个
python favorites.py --limit 10
```

### 4. 并行批量提取（更快）

```bash
# 并行处理，3倍速度
python batch_extract.py --select 1-10 --workers 3

# 处理所有收藏
python batch_extract.py --all --workers 5

# 指定视频编号
python batch_extract.py --select 1,5,10-20
```

### 5. 内容收集到 Obsidian（一键整理）

```bash
# 从抖音链接提取并整理到 Obsidian
python to_obsidian.py https://v.douyin.com/xxxxx/

# 从本地视频整理
python to_obsidian.py --file video.mp4

# 直接整理文本内容
python to_obsidian.py --text "你的笔记内容" --title "笔记标题" --tags "标签1,标签2"
```

功能特点：
- 自动提取核心观点
- 自动查找相关笔记并添加双向链接
- 自动生成元数据（标签、来源、时间）
- 直接保存到 Obsidian 知识库

#### 输出文件

| 文件 | 说明 |
|------|------|
| `output/视频标题.txt` | 每个视频的单独文案 |
| `output/收藏夹汇总.md` | 所有视频文案汇总（含标题、作者、链接） |
| `output/知识卡片.md` | 每个视频的核心要点提取 |

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
├── common.py           # 公共模块（下载、转录、工具函数）
├── extract.py          # 单视频提取
├── favorites.py        # 收藏夹批量提取（交互式）
├── batch_extract.py    # 收藏夹批量提取（并行版，更快）
├── requirements.txt    # Python 依赖
├── README.md           # 项目说明
├── LICENSE             # MIT 开源协议
├── .auth/              # 登录状态 (自动创建，不会上传)
└── output/             # 输出目录 (自动创建)
```

## 注意事项

- 首次运行收藏夹功能需要登录抖音账号
- 登录状态保存在 `.auth/` 目录，不会上传到 GitHub
- 首次运行需要下载 Whisper 模型，请耐心等待
- 中文视频建议使用 `medium` 或 `large` 模型
- 背景音乐可能影响识别准确度
- 仅限个人学习研究使用，请遵守抖音用户协议

## License

[MIT](LICENSE)
