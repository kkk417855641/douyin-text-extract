"""
抖音收藏夹自动提取工具

自动登录抖音，抓取收藏夹中的视频，下载并转录为文字，
生成汇总文档和知识卡片。

用法:
    python favorites.py                   交互式选择收藏夹视频
    python favorites.py --all             自动处理所有收藏
    python favorites.py --limit 10        只处理最近 10 个
    python favorites.py --login           仅登录并保存状态
"""

import sys
import re
import time
import json
from datetime import datetime
from pathlib import Path

VALID_MODELS = ("tiny", "base", "small", "medium", "large")
OUTPUT_DIR = Path(__file__).parent / "output"
AUTH_DIR = Path(__file__).parent / ".auth"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def check_dependencies():
    """检查依赖"""
    missing = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        missing.append("playwright")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        missing.append("faster-whisper")
    try:
        import httpx
    except ImportError:
        missing.append("httpx")

    if missing:
        print("缺少以下依赖，请先安装:")
        for dep in missing:
            print(f"  pip install {dep}")
        if "playwright" in missing:
            print("  python -m playwright install chromium")
        sys.exit(1)


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')
    return name[:max_len] if name else "untitled"


def login_and_save():
    """打开浏览器让用户登录，保存登录状态"""
    from playwright.sync_api import sync_playwright

    AUTH_DIR.mkdir(exist_ok=True)

    print("正在打开浏览器，请登录你的抖音账号...")
    print("登录完成后，按回车键继续...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="zh-CN",
            storage_state=str(AUTH_DIR / "state.json") if (AUTH_DIR / "state.json").exists() else None,
        )
        page = context.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)

        input(">> 登录完成后按回车...")

        # 保存登录状态
        context.storage_state(path=str(AUTH_DIR / "state.json"))
        print(f"登录状态已保存到: {AUTH_DIR / 'state.json'}")
        browser.close()

    return True


def get_browser_context(playwright):
    """获取带有登录状态的浏览器上下文"""
    from playwright.sync_api import sync_playwright

    AUTH_DIR.mkdir(exist_ok=True)
    state_file = AUTH_DIR / "state.json"

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=USER_AGENT,
        locale="zh-CN",
        storage_state=str(state_file) if state_file.exists() else None,
    )
    return browser, context


def scrape_favorites(limit: int = 0) -> list:
    """抓取收藏夹视频列表

    Args:
        limit: 限制数量，0 表示全部

    Returns:
        视频信息列表 [{"title": ..., "url": ..., "author": ...}, ...]
    """
    from playwright.sync_api import sync_playwright

    state_file = AUTH_DIR / "state.json"
    if not state_file.exists():
        print("未找到登录状态，请先运行: python favorites.py --login")
        return []

    print("正在打开抖音收藏夹...")
    videos = []

    with sync_playwright() as p:
        browser, context = get_browser_context(p)
        page = context.new_page()

        # 访问收藏夹页面
        page.goto("https://www.douyin.com/user/self?showTab=favorite",
                   wait_until="domcontentloaded", timeout=30000)
        time.sleep(5)

        # 检查是否登录成功
        if "login" in page.url:
            print("登录已过期，请重新登录: python favorites.py --login")
            browser.close()
            return []

        # 滚动加载更多视频
        print("正在加载收藏列表...")
        prev_count = 0
        no_new_count = 0
        max_scrolls = 50  # 最多滚动50次

        for i in range(max_scrolls):
            # 滚动到底部
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # 提取视频卡片
            cards = page.query_selector_all('div[class*="DyOneListItem"], a[href*="/video/"]')

            current_count = len(cards)
            if current_count == prev_count:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0
            prev_count = current_count

            if limit > 0 and current_count >= limit:
                break

            print(f"  已加载 {current_count} 个视频...")

        # 提取视频信息
        cards = page.query_selector_all('a[href*="/video/"]')
        seen_urls = set()

        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                video_match = re.search(r'/video/(\d+)', href)
                if not video_match:
                    continue

                video_id = video_match.group(1)
                if video_id in seen_urls:
                    continue
                seen_urls.add(video_id)

                # 提取标题
                title_el = card.query_selector('[class*="title"], [class*="desc"], p, span')
                title = title_el.inner_text().strip() if title_el else f"视频_{video_id}"

                # 提取作者
                author_el = card.query_selector('[class*="author"], [class*="nickname"]')
                author = author_el.inner_text().strip() if author_el else ""

                url = f"https://www.douyin.com/video/{video_id}"
                videos.append({
                    "id": video_id,
                    "title": title,
                    "author": author,
                    "url": url,
                })

                if limit > 0 and len(videos) >= limit:
                    break

            except Exception:
                continue

        browser.close()

    print(f"共找到 {len(videos)} 个收藏视频")
    return videos


def download_video(url: str) -> str:
    """用 Playwright 下载单个视频"""
    import httpx
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    video_url = None
    video_title = "douyin_video"

    with sync_playwright() as p:
        browser, context = get_browser_context(p)
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
            video_title = sanitize_filename(page.title())
        except Exception:
            pass

        browser.close()

    if not video_url:
        print("  无法提取视频URL")
        return None

    output_path = OUTPUT_DIR / f"{video_title}.mp4"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.douyin.com/",
    }

    with httpx.Client(follow_redirects=True, timeout=60) as client:
        with client.stream("GET", video_url, headers=headers) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_bytes(8192):
                    f.write(chunk)

    return str(output_path)


def transcribe(video_path: str, model_size: str = "medium") -> str:
    """用 faster-whisper 转录视频"""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, language="zh", beam_size=5, vad_filter=True)

    full_text = []
    for segment in segments:
        full_text.append(segment.text)

    return "\n".join(full_text)


def generate_summary(results: list, output_dir: Path):
    """生成汇总 Markdown 文档"""
    output_dir.mkdir(exist_ok=True)

    # 汇总文档
    summary_path = output_dir / "收藏夹汇总.md"
    lines = [
        f"# 抖音收藏夹汇总\n",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"共 {len(results)} 个视频\n",
        "---\n",
    ]

    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r['title']}\n")
        if r.get("author"):
            lines.append(f"**作者**: {r['author']}\n")
        lines.append(f"**链接**: {r['url']}\n")
        lines.append(f"\n{r['transcript']}\n")
        lines.append("\n---\n")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"汇总文档已保存: {summary_path}")

    # 知识卡片
    cards_path = output_dir / "知识卡片.md"
    cards = [
        f"# 抖音知识卡片\n",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "---\n",
    ]

    for i, r in enumerate(results, 1):
        cards.append(f"## 📌 {r['title']}\n")
        if r.get("author"):
            cards.append(f"**来源**: {r['author']} | [原视频]({r['url']})\n")
        else:
            cards.append(f"**来源**: [原视频]({r['url']})\n")

        # 提取要点（简单方式：按句号/逗号分句，取关键句）
        text = r["transcript"]
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        cards.append("\n**核心要点**:\n")
        for s in sentences[:8]:  # 最多取8句
            cards.append(f"- {s}")
        cards.append("")
        cards.append("---\n")

    cards_path.write_text("\n".join(cards), encoding="utf-8")
    print(f"知识卡片已保存: {cards_path}")


def print_help():
    print(
        """抖音收藏夹自动提取工具

用法:
    python favorites.py                   交互式选择收藏夹视频
    python favorites.py --all             自动处理所有收藏
    python favorites.py --limit 10        只处理最近 10 个
    python favorites.py --login           仅登录并保存状态

选项:
    --model <size>   语音模型大小 (默认 medium)
    --login          仅登录并保存状态，不提取
    --all            处理所有收藏视频
    --limit <n>      限制处理数量
    --help           显示此帮助"""
    )


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print_help()
        sys.exit(0)

    check_dependencies()

    # 解析参数
    model_size = "medium"
    limit = 0
    login_only = False
    auto_all = False

    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_size = args[i + 1].lower()
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--login":
            login_only = True
            i += 1
        elif args[i] == "--all":
            auto_all = True
            i += 1
        else:
            print(f"未知参数: {args[i]}")
            sys.exit(1)

    if model_size not in VALID_MODELS:
        print(f"无效的模型: {model_size}，可选: {', '.join(VALID_MODELS)}")
        sys.exit(1)

    # 仅登录模式
    if login_only:
        login_and_save()
        return

    # 检查登录状态
    if not (AUTH_DIR / "state.json").exists():
        print("首次使用需要登录抖音账号")
        login_and_save()

    # 抓取收藏列表
    videos = scrape_favorites(limit=limit if not auto_all else 0)

    if not videos:
        print("未找到收藏视频")
        return

    # 非自动模式，让用户选择
    if not auto_all and limit == 0:
        print("\n收藏视频列表:")
        for idx, v in enumerate(videos, 1):
            author_str = f" - {v['author']}" if v['author'] else ""
            print(f"  {idx}. {v['title']}{author_str}")

        print(f"\n输入要处理的视频编号（如 1,3,5 或 all）:")
        choice = input(">> ").strip()

        if choice.lower() == "all":
            selected = videos
        else:
            indices = []
            for part in choice.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-")
                    indices.extend(range(int(start), int(end) + 1))
                elif part.isdigit():
                    indices.append(int(part))
            selected = [videos[i - 1] for i in indices if 0 < i <= len(videos)]
    else:
        selected = videos

    print(f"\n将处理 {len(selected)} 个视频\n")

    # 处理每个视频
    results = []
    for idx, video in enumerate(selected, 1):
        print(f"[{idx}/{len(selected)}] {video['title']}")

        try:
            # 下载
            print("  下载中...")
            video_path = download_video(video["url"])
            if not video_path:
                print("  下载失败，跳过")
                continue

            # 转录
            print("  转录中...")
            transcript = transcribe(video_path, model_size)

            if transcript.strip():
                # 保存单个文案
                txt_path = OUTPUT_DIR / f"{sanitize_filename(video['title'])}.txt"
                txt_path.write_text(transcript, encoding="utf-8")

                results.append({
                    "title": video["title"],
                    "author": video.get("author", ""),
                    "url": video["url"],
                    "transcript": transcript,
                })
                print(f"  完成 ✓")
            else:
                print("  未识别到文字内容")

        except Exception as e:
            print(f"  处理失败: {e}")
            continue

    # 生成汇总
    if results:
        print(f"\n正在生成汇总文档...")
        generate_summary(results, OUTPUT_DIR)
        print(f"\n全部完成！共处理 {len(results)} 个视频")
    else:
        print("\n没有成功处理的视频")


if __name__ == "__main__":
    main()
