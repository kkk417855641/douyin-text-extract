"""
douyin-text-extract: 抖音视频文案提取工具

从抖音视频链接自动下载视频并转录为文字。
使用 Playwright 自动化浏览器绕过反爬，faster-whisper 进行语音识别。

用法:
    python extract.py <抖音视频URL>
    python extract.py --file <本地视频文件>
    python extract.py --help
"""

import sys
import re
import time
from pathlib import Path

# 检查关键依赖
_MISSING_DEPS = []
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    _MISSING_DEPS.append("playwright")

try:
    from faster_whisper import WhisperModel
except ImportError:
    _MISSING_DEPS.append("faster-whisper")

try:
    import httpx
except ImportError:
    _MISSING_DEPS.append("httpx")

VALID_MODELS = ("tiny", "base", "small", "medium", "large")
OUTPUT_DIR = Path(__file__).parent / "output"

# Playwright 浏览器 User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def check_dependencies():
    """检查依赖是否安装"""
    if _MISSING_DEPS:
        print("缺少以下依赖，请先安装:")
        for dep in _MISSING_DEPS:
            print(f"  pip install {dep}")
        if "playwright" in _MISSING_DEPS:
            print("  python -m playwright install chromium")
        sys.exit(1)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名，移除 Windows 非法字符"""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "douyin_video"


def download_with_playwright(url: str) -> str:
    """用 Playwright 自动化浏览器下载抖音视频。

    通过拦截网络请求捕获视频流 URL，然后用 httpx 下载到本地。
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    video_url = None
    video_title = "douyin_video"

    print("正在启动浏览器...")
    with sync_playwright() as p:
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
                keyword in resp_url
                for keyword in ("douyinvod", "v26", "v3-web")
            ):
                video_url = resp_url

        page.on("response", handle_response)

        print(f"正在访问: {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            print("页面加载超时，继续尝试...")

        time.sleep(3)

        # 获取视频标题
        try:
            video_title = sanitize_filename(page.title())
        except Exception:
            pass

        browser.close()

    if not video_url:
        print("无法提取视频URL")
        return None

    # 下载视频
    print("正在下载视频...")
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


def transcribe(video_path: str, model_size: str = "medium") -> str:
    """用 faster-whisper 将视频音频转录为文字。

    Args:
        video_path: 视频文件路径
        model_size: Whisper 模型大小 (tiny/base/small/medium/large)

    Returns:
        转录后的完整文本
    """
    print(f"正在加载语音识别模型 ({model_size})...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("正在转录...")
    segments, _info = model.transcribe(
        video_path,
        language="zh",
        beam_size=5,
        vad_filter=True,
    )

    full_text = []
    for segment in segments:
        line = f"[{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}"
        print(line)
        full_text.append(segment.text)

    return "\n".join(full_text)


def save_transcript(text: str, video_path: str) -> str:
    """保存转录文本到文件"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    video_name = Path(video_path).stem
    output_file = OUTPUT_DIR / f"{video_name}.txt"
    output_file.write_text(text, encoding="utf-8")
    print(f"\n文案已保存到: {output_file}")
    return str(output_file)


def print_help():
    """打印帮助信息"""
    print(
        """抖音视频文案提取工具

用法:
    python extract.py <抖音视频URL>           下载并转录抖音视频
    python extract.py --file <本地视频>        直接转录本地视频文件
    python extract.py --help                   显示此帮助

选项:
    --model <size>   语音模型大小 (默认 medium)
                     tiny   - 最快，准确度低
                     base   - 较快，适合简单内容
                     small  - 平衡速度和质量
                     medium - 中文效果好 (推荐)
                     large  - 最准但最慢

示例:
    python extract.py https://v.douyin.com/xxxxx/
    python extract.py https://www.douyin.com/video/123456789
    python extract.py --file video.mp4 --model small"""
    )


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_help()
        sys.exit(0)

    check_dependencies()

    # 解析参数
    model_size = "medium"
    url = None
    local_file = None

    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_size = args[i + 1].lower()
            i += 2
        elif args[i] == "--file" and i + 1 < len(args):
            local_file = args[i + 1]
            i += 2
        elif not args[i].startswith("--"):
            url = args[i]
            i += 1
        else:
            print(f"未知参数: {args[i]}")
            print("使用 --help 查看帮助")
            sys.exit(1)

    # 校验模型大小
    if model_size not in VALID_MODELS:
        print(f"无效的模型: {model_size}")
        print(f"可选: {', '.join(VALID_MODELS)}")
        sys.exit(1)

    # 获取视频文件
    if local_file:
        if not Path(local_file).exists():
            print(f"文件不存在: {local_file}")
            sys.exit(1)
        video_path = local_file
        print(f"使用本地文件: {video_path}")
    elif url:
        video_path = download_with_playwright(url)
        if not video_path:
            print("\n下载失败，请尝试:")
            print("  手动下载视频后使用: python extract.py --file 视频.mp4")
            sys.exit(1)
    else:
        print("请提供抖音视频URL或本地文件路径")
        print("使用 --help 查看帮助")
        sys.exit(1)

    # 转录
    text = transcribe(video_path, model_size)

    # 保存
    if text.strip():
        save_transcript(text, video_path)
    else:
        print("未识别到任何文字内容")


if __name__ == "__main__":
    main()
