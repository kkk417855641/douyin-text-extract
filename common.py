"""
douyin-text-extract: 公共模块

提供共享的工具函数和常量，供 extract.py 和 favorites.py 使用。
"""

import sys
import os
import re
import time
from pathlib import Path

# ============================================================
# Windows 终端编码修复
# ============================================================

def setup_encoding():
    """设置 Windows 终端为 UTF-8 编码，解决中文乱码问题"""
    if sys.platform == 'win32':
        # 设置环境变量
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        # 尝试设置控制台代码页
        try:
            os.system('chcp 65001 > nul 2>&1')
        except Exception:
            pass
        # 重新配置 stdout/stderr
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# 启动时自动修复编码
setup_encoding()

# ============================================================
# 常量
# ============================================================

VALID_MODELS = ("tiny", "base", "small", "medium", "large")
OUTPUT_DIR = Path("F:/douyin-extract-output")
AUTH_DIR = Path(__file__).parent / ".auth"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ============================================================
# 依赖检查
# ============================================================

def check_dependencies():
    """检查关键依赖是否安装，缺少则提示并退出"""
    missing = []
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        missing.append("playwright")
    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except ImportError:
        missing.append("faster-whisper")
    try:
        import httpx  # noqa: F401
    except ImportError:
        missing.append("httpx")

    if missing:
        print("缺少以下依赖，请先安装:")
        for dep in missing:
            print(f"  pip install {dep}")
        if "playwright" in missing:
            print("  python -m playwright install chromium")
        sys.exit(1)


# ============================================================
# 文件名处理
# ============================================================

def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名，移除 Windows 非法字符"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "untitled"


# ============================================================
# 安全打印（处理 Windows 终端编码问题）
# ============================================================

def safe_print(text: str):
    """安全打印，处理 Windows 终端 GBK 编码无法显示 emoji 等字符的问题"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        # 移除 emoji 和其他 Unicode 扩展字符
        clean = re.sub(r'[\U0001F000-\U0001FFFF☀-➿⭐⭕✨🔥💯✅❌⚡🎯📌💡🔧🎨🎬📚💰🤖]', '', text)
        try:
            print(clean, flush=True)
        except UnicodeEncodeError:
            # 最后手段：用 UTF-8 编码写入
            try:
                sys.stdout.buffer.write((clean + '\n').encode('utf-8', errors='replace'))
                sys.stdout.buffer.flush()
            except Exception:
                print(clean.encode('ascii', errors='replace').decode('ascii'))


# ============================================================
# 浏览器工具
# ============================================================

def create_browser_context(playwright, headless=True):
    """创建带有登录状态的浏览器上下文

    Args:
        playwright: Playwright 实例
        headless: 是否无头模式

    Returns:
        (browser, context) 元组
    """
    from playwright.sync_api import sync_playwright  # noqa: F401

    AUTH_DIR.mkdir(exist_ok=True)
    state_file = AUTH_DIR / "state.json"

    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="zh-CN",
        storage_state=str(state_file) if state_file.exists() else None,
    )
    return browser, context


# ============================================================
# 视频下载
# ============================================================

def download_video(url: str, use_auth: bool = False) -> str:
    """用 Playwright 下载抖音视频

    Args:
        url: 抖音视频 URL
        use_auth: 是否使用登录状态（收藏夹视频需要）

    Returns:
        下载后的本地文件路径，失败返回 None
    """
    import httpx
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    video_url = None
    video_title = "douyin_video"

    with sync_playwright() as p:
        if use_auth:
            browser, context = create_browser_context(p)
        else:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="zh-CN",
            )

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

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            pass

        time.sleep(3)

        try:
            raw_title = page.title()
            # 去掉 " - 抖音" 后缀
            for suffix in (" - 抖音", " | 抖音", "- 抖音"):
                if raw_title.endswith(suffix):
                    raw_title = raw_title[:-len(suffix)]
            video_title = sanitize_filename(raw_title.strip())
        except Exception:
            pass

        browser.close()

    if not video_url:
        return None

    output_path = OUTPUT_DIR / f"{video_title}.mp4"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.douyin.com/",
    }

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        with client.stream("GET", video_url, headers=headers) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in resp.iter_bytes(8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded / total * 100
                        print(f"\r下载进度: {pct:.1f}%", end="", flush=True)

    print(f"\n下载完成: {output_path}")
    return str(output_path)


# ============================================================
# 语音转录
# ============================================================

def transcribe(video_path: str, model_size: str = "medium", verbose: bool = True) -> str:
    """用 faster-whisper 将视频音频转录为文字

    Args:
        video_path: 视频文件路径
        model_size: Whisper 模型大小 (tiny/base/small/medium/large)
        verbose: 是否打印转录过程

    Returns:
        转录后的完整文本
    """
    from faster_whisper import WhisperModel

    if verbose:
        print(f"正在加载语音识别模型 ({model_size})...")

    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    if verbose:
        print("正在转录...")

    segments, _info = model.transcribe(
        video_path,
        language="zh",
        beam_size=5,
        vad_filter=True,
    )

    full_text = []
    for segment in segments:
        if verbose:
            line = f"[{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}"
            safe_print(line)
        full_text.append(segment.text)

    return "\n".join(full_text)


# ============================================================
# 文案保存
# ============================================================

def save_transcript(text: str, video_path: str) -> str:
    """保存转录文本到文件

    Args:
        text: 转录文本
        video_path: 视频文件路径（用于生成 txt 文件名）

    Returns:
        保存的文件路径
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    video_name = Path(video_path).stem
    output_file = OUTPUT_DIR / f"{video_name}.txt"
    output_file.write_text(text, encoding="utf-8")
    print(f"\n文案已保存到: {output_file}")
    return str(output_file)
