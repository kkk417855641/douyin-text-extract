"""
内容收集到 Obsidian 工作流

支持多种输入方式：
1. 抖音链接 → 下载视频 → 转录 → 整理到 Obsidian
2. 本地视频文件 → 转录 → 整理到 Obsidian
3. 文本内容 → 直接整理到 Obsidian

用法:
    python to_obsidian.py <抖音URL>
    python to_obsidian.py --file <本地视频>
    python to_obsidian.py --text "你的笔记内容" --title "笔记标题"
"""

import sys
import os
import re
import hashlib
from pathlib import Path
from datetime import datetime

# Windows 终端编码修复
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        os.system('chcp 65001 > nul 2>&1')
    except Exception:
        pass
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Obsidian vault 路径
OBSIDIAN_VAULT = Path(r"C:\Users\sunyan\Documents\Obsidian Vault")
KNOWLEDGE_DIR = OBSIDIAN_VAULT / "2-Knowledge"
INBOX_DIR = OBSIDIAN_VAULT / "0-Inbox"

# 当前脚本目录
SCRIPT_DIR = Path(__file__).parent


def check_dependencies():
    """检查依赖"""
    missing = []
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        missing.append("faster-whisper")
    try:
        import httpx
    except ImportError:
        missing.append("httpx")

    if missing:
        print(f"缺少依赖: {', '.join(missing)}")
        print("运行: pip install " + " ".join(missing))
        sys.exit(1)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "untitled"


def download_video(url: str) -> str:
    """下载抖音视频"""
    import httpx
    from playwright.sync_api import sync_playwright

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    output_dir = SCRIPT_DIR / "output"
    output_dir.mkdir(exist_ok=True)

    video_url = None
    video_title = "douyin_video"

    print("正在启动浏览器...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN")
        page = context.new_page()

        def handle_response(response):
            nonlocal video_url
            resp_url = response.url
            content_type = response.headers.get("content-type", "")
            if ("video" in content_type or ".mp4" in resp_url) and any(
                kw in resp_url for kw in ("douyinvod", "v26", "v3-web")
            ):
                video_url = resp_url

        page.on("response", handle_response)

        print(f"正在访问: {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass

        import time
        time.sleep(3)

        try:
            raw_title = page.title()
            for suffix in (" - 抖音", " | 抖音", "- 抖音"):
                if raw_title.endswith(suffix):
                    raw_title = raw_title[:-len(suffix)]
            video_title = sanitize_filename(raw_title.strip())
        except Exception:
            pass

        browser.close()

    if not video_url:
        print("无法提取视频URL")
        return None, None

    print("正在下载视频...")
    output_path = output_dir / f"{video_title}.mp4"
    headers = {"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        with client.stream("GET", video_url, headers=headers) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_bytes(8192):
                    f.write(chunk)

    print(f"下载完成: {output_path}")
    return str(output_path), video_title


def transcribe_video(video_path: str, model_size: str = "medium") -> str:
    """转录视频为文字"""
    from faster_whisper import WhisperModel

    print(f"正在加载语音识别模型 ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("正在转录...")
    segments, _ = model.transcribe(video_path, language="zh", beam_size=5, vad_filter=True)

    text = []
    for segment in segments:
        text.append(segment.text)

    return "\n".join(text)


def extract_key_insights(text: str, max_insights: int = 5) -> list[str]:
    """从文本中提取核心观点"""
    # 按句号、问号、感叹号分句
    sentences = re.split(r'[。！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]

    # 简单的关键词匹配，优先选择包含重要词汇的句子
    important_keywords = ['核心', '关键', '重要', '本质', '总结', '结论', '发现', '应该', '需要', '可以']

    scored = []
    for s in sentences:
        score = 0
        for kw in important_keywords:
            if kw in s:
                score += 1
        # 较长的句子通常更有信息量
        if len(s) > 20:
            score += 1
        scored.append((score, s))

    # 按分数排序，取前N个
    scored.sort(key=lambda x: x[0], reverse=True)
    insights = [s for _, s in scored[:max_insights]]

    return insights


def find_related_notes(title: str, content: str) -> list[str]:
    """在 Obsidian vault 中查找相关笔记"""
    related = []
    keywords = set()

    # 从标题和内容中提取关键词
    words = re.findall(r'[一-鿿]+', title + content[:500])
    for w in words:
        if len(w) >= 2:
            keywords.add(w)

    # 搜索 vault 中的笔记
    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        if md_file.name.startswith('.'):
            continue
        try:
            file_content = md_file.read_text(encoding="utf-8")[:2000]
            for kw in keywords:
                if kw in file_content:
                    note_name = md_file.stem
                    if note_name not in related:
                        related.append(note_name)
                    break
        except Exception:
            continue

    return related[:5]  # 最多返回5个相关笔记


def create_obsidian_note(
    title: str,
    content: str,
    source_url: str = "",
    category: str = "抖音收藏",
    tags: list[str] = None,
) -> str:
    """创建 Obsidian 笔记

    Args:
        title: 笔记标题
        content: 笔记内容（转录文本或用户输入）
        source_url: 来源链接
        category: 分类目录
        tags: 标签列表

    Returns:
        创建的笔记路径
    """
    # 创建分类目录
    category_dir = KNOWLEDGE_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    # 提取核心洞察
    insights = extract_key_insights(content)

    # 查找相关笔记
    related = find_related_notes(title, content)

    # 构建笔记内容
    note_lines = [
        f"# {title}",
        "",
        "> " + (insights[0] if insights else "待补充核心观点"),
        "",
        "## 核心洞察",
        "",
    ]

    if insights:
        for insight in insights:
            note_lines.append(f"- {insight}")
    else:
        note_lines.append("- 待补充")

    note_lines.extend([
        "",
        "## 详细内容",
        "",
        content,
        "",
    ])

    # 添加相关笔记链接
    if related:
        note_lines.extend([
            "## 相关笔记",
            "",
        ])
        for note in related:
            note_lines.append(f"- [[{note}]]")
        note_lines.append("")

    # 添加元数据
    note_lines.extend([
        "---",
        "",
        "## 元数据",
        "",
    ])

    if tags:
        tag_str = " ".join(f"#{t}" for t in tags)
        note_lines.append(f"- **关键词**: {tag_str}")

    if source_url:
        note_lines.append(f"- **来源**: [{source_url}]({source_url})")

    note_lines.append(f"- **创建时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 保存笔记
    safe_title = sanitize_filename(title)
    note_path = category_dir / f"{safe_title}.md"
    note_path.write_text("\n".join(note_lines), encoding="utf-8")

    print(f"笔记已保存: {note_path}")
    return str(note_path)


def process_url(url: str, model_size: str = "medium"):
    """处理抖音URL：下载 → 转录 → 整理到 Obsidian"""
    print("=" * 50)
    print("步骤 1: 下载视频")
    print("=" * 50)

    video_path, title = download_video(url)
    if not video_path:
        print("下载失败")
        return

    print("\n" + "=" * 50)
    print("步骤 2: 转录音频")
    print("=" * 50)

    transcript = transcribe_video(video_path, model_size)
    if not transcript.strip():
        print("转录失败或无语音内容")
        return

    print("\n" + "=" * 50)
    print("步骤 3: 整理到 Obsidian")
    print("=" * 50)

    note_path = create_obsidian_note(
        title=title,
        content=transcript,
        source_url=url,
        category="抖音收藏",
        tags=["抖音", "视频转录"],
    )

    print("\n" + "=" * 50)
    print("完成！")
    print("=" * 50)
    print(f"笔记已保存到: {note_path}")
    print("你可以在 Obsidian 中打开查看")


def process_file(file_path: str, model_size: str = "medium"):
    """处理本地视频文件"""
    path = Path(file_path)
    if not path.exists():
        print(f"文件不存在: {file_path}")
        return

    print("=" * 50)
    print("步骤 1: 转录音频")
    print("=" * 50)

    transcript = transcribe_video(file_path, model_size)
    if not transcript.strip():
        print("转录失败或无语音内容")
        return

    print("\n" + "=" * 50)
    print("步骤 2: 整理到 Obsidian")
    print("=" * 50)

    title = path.stem
    note_path = create_obsidian_note(
        title=title,
        content=transcript,
        category="抖音收藏",
        tags=["视频转录"],
    )

    print("\n完成！")
    print(f"笔记已保存到: {note_path}")


def process_text(title: str, text: str, source_url: str = "", tags: list[str] = None):
    """处理文本内容，直接整理到 Obsidian"""
    print("正在整理到 Obsidian...")

    note_path = create_obsidian_note(
        title=title,
        content=text,
        source_url=source_url,
        category="抖音收藏",
        tags=tags or ["笔记"],
    )

    print(f"笔记已保存到: {note_path}")


def print_help():
    print(
        """内容收集到 Obsidian 工作流

用法:
    python to_obsidian.py <抖音URL>                    从抖音链接提取并整理
    python to_obsidian.py --file <本地视频>             从本地视频整理
    python to_obsidian.py --text "内容" --title "标题"   直接整理文本

选项:
    --model <size>     语音模型大小 (默认 medium)
    --title <title>    笔记标题 (用于 --text 模式)
    --tags <tag1,tag2> 标签 (逗号分隔)
    --category <dir>   分类目录 (默认 抖音收藏)
    --help             显示此帮助

示例:
    python to_obsidian.py https://v.douyin.com/xxxxx/
    python to_obsidian.py --file video.mp4
    python to_obsidian.py --text "今天学到了..." --title "学习笔记" --tags "学习,笔记"
"""
    )


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_help()
        sys.exit(0)

    # 解析参数
    model_size = "medium"
    title = ""
    tags = None
    category = "抖音收藏"
    url = None
    local_file = None
    text = None

    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_size = args[i + 1]
            i += 2
        elif args[i] == "--title" and i + 1 < len(args):
            title = args[i + 1]
            i += 2
        elif args[i] == "--tags" and i + 1 < len(args):
            tags = [t.strip() for t in args[i + 1].split(",")]
            i += 2
        elif args[i] == "--category" and i + 1 < len(args):
            category = args[i + 1]
            i += 2
        elif args[i] == "--file" and i + 1 < len(args):
            local_file = args[i + 1]
            i += 2
        elif args[i] == "--text" and i + 1 < len(args):
            text = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            url = args[i]
            i += 1
        else:
            print(f"未知参数: {args[i]}")
            sys.exit(1)

    # 检查依赖
    if url or local_file:
        check_dependencies()

    # 执行
    if text:
        if not title:
            title = "未命名笔记"
        process_text(title, text, tags=tags)
    elif local_file:
        process_file(local_file, model_size)
    elif url:
        process_url(url, model_size)
    else:
        print("请提供抖音URL、本地文件或文本内容")
        print("使用 --help 查看帮助")


if __name__ == "__main__":
    main()
