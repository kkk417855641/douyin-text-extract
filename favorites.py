"""
douyin-text-extract: 抖音收藏夹批量提取工具

自动登录抖音，抓取收藏夹中的视频，下载并转录为文字，
生成汇总文档和知识卡片。

用法:
    python favorites.py                   交互式选择收藏夹视频
    python favorites.py --all             自动处理所有收藏
    python favorites.py --limit 10        只处理最近 10 个
    python favorites.py --select 1,3,5    指定处理第 1,3,5 个
    python favorites.py --login           仅登录并保存状态
"""

import sys
import re
import time
from datetime import datetime
from pathlib import Path

from common import (
    VALID_MODELS, OUTPUT_DIR, AUTH_DIR, USER_AGENT,
    check_dependencies, sanitize_filename, safe_print,
    create_browser_context, download_video, transcribe,
)


# ============================================================
# 登录
# ============================================================

def login_and_save():
    """打开浏览器让用户登录，自动检测登录成功后保存状态"""
    from playwright.sync_api import sync_playwright

    AUTH_DIR.mkdir(exist_ok=True)

    print("正在打开浏览器，请登录你的抖音账号...")
    print("登录成功后会自动保存状态，浏览器会自动关闭。\n")

    with sync_playwright() as p:
        browser, context = create_browser_context(p, headless=False)
        page = context.new_page()
        page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=30000)

        # 等待用户登录
        print("等待登录中...")
        logged_in = False
        for _ in range(120):  # 最多等 2 分钟
            time.sleep(2)
            try:
                avatar = page.query_selector(
                    '[class*="avatar"], [class*="Avatar"], [data-e2e="user-info"]'
                )
                if avatar:
                    logged_in = True
                    break
                if "login" not in page.url and page.query_selector(
                    '[class*="profile"], [class*="Profile"]'
                ):
                    logged_in = True
                    break
            except Exception:
                continue

        if logged_in:
            print("检测到登录成功！")
        else:
            print("等待超时，尝试保存当前状态...")

        context.storage_state(path=str(AUTH_DIR / "state.json"))
        print(f"登录状态已保存到: {AUTH_DIR / 'state.json'}")
        browser.close()

    return True


# ============================================================
# 收藏夹抓取
# ============================================================

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
        browser, context = create_browser_context(p)
        page = context.new_page()

        # 访问收藏页面
        page.goto(
            "https://www.douyin.com/user/self?showTab=favorite_collection",
            wait_until="domcontentloaded",
            timeout=30000,
        )
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

        for _ in range(100):  # 最多滚动 100 次
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            links = page.query_selector_all('a[href*="/video/"]')
            seen = set()
            for link in links:
                href = link.get_attribute("href") or ""
                match = re.search(r'/video/(\d+)', href)
                if match:
                    seen.add(match.group(1))

            current_count = len(seen)
            if current_count == prev_count:
                no_new_count += 1
                if no_new_count >= 5:
                    break
            else:
                no_new_count = 0
                if current_count % 10 == 0 or current_count > prev_count + 5:
                    print(f"  已加载 {current_count} 个视频...")
            prev_count = current_count

            if limit > 0 and current_count >= limit:
                break

        # 提取视频信息
        print("正在提取视频信息...")
        seen_ids = set()
        links = page.query_selector_all('a[href*="/video/"]')

        for link in links:
            try:
                href = link.get_attribute("href") or ""
                video_match = re.search(r'/video/(\d+)', href)
                if not video_match:
                    continue

                video_id = video_match.group(1)
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                # 从链接文本提取标题
                title = link.inner_text().strip()
                title = re.sub(r'\s+', ' ', title).strip()
                if not title or len(title) < 3:
                    title = f"视频_{video_id}"

                url = f"https://www.douyin.com/video/{video_id}"
                videos.append({
                    "id": video_id,
                    "title": title[:100],
                    "url": url,
                })

                if limit > 0 and len(videos) >= limit:
                    break

            except Exception:
                continue

        browser.close()

    print(f"共找到 {len(videos)} 个收藏视频")
    return videos


# ============================================================
# 汇总文档生成
# ============================================================

def generate_summary(results: list, output_dir: Path):
    """生成汇总 Markdown 文档和知识卡片"""
    output_dir.mkdir(exist_ok=True)

    # --- 汇总文档 ---
    summary_path = output_dir / "收藏夹汇总.md"
    lines = [
        "# 抖音收藏夹汇总\n",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"共 {len(results)} 个视频\n",
        "---\n",
    ]

    for i, r in enumerate(results, 1):
        lines.append(f"## {i}. {r['title']}\n")
        lines.append(f"**链接**: {r['url']}\n")
        lines.append(f"\n{r['transcript']}\n")
        lines.append("\n---\n")

    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"汇总文档已保存: {summary_path}")

    # --- 知识卡片 ---
    cards_path = output_dir / "知识卡片.md"
    cards = [
        "# 抖音知识卡片\n",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "---\n",
    ]

    for i, r in enumerate(results, 1):
        cards.append(f"## {i}. {r['title']}\n")
        cards.append(f"**来源**: [原视频]({r['url']})\n")

        # 提取要点：按句号/问号/感叹号分句，取关键句
        text = r["transcript"]
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

        cards.append("\n**核心要点**:\n")
        for s in sentences[:8]:
            cards.append(f"- {s}")
        cards.append("")
        cards.append("---\n")

    cards_path.write_text("\n".join(cards), encoding="utf-8")
    print(f"知识卡片已保存: {cards_path}")


# ============================================================
# 帮助
# ============================================================

def print_help():
    print(
        """抖音收藏夹批量提取工具

用法:
    python favorites.py                       交互式选择收藏夹视频
    python favorites.py --all                 自动处理所有收藏
    python favorites.py --limit 10            只处理最近 10 个
    python favorites.py --select 1,3,5        指定处理第 1,3,5 个
    python favorites.py --select 1-50         指定处理第 1-50 个
    python favorites.py --login               仅登录并保存状态

选项:
    --model <size>   语音模型大小 (默认 medium)
    --login          仅登录并保存状态，不提取
    --all            处理所有收藏视频
    --limit <n>      限制处理数量
    --select <ids>   指定要处理的视频编号 (如 1,3,5 或 1-10)
    --help           显示此帮助"""
    )


# ============================================================
# 主函数
# ============================================================

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
    select_str = None

    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_size = args[i + 1].lower()
            i += 2
        elif args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
            i += 2
        elif args[i] == "--select" and i + 1 < len(args):
            select_str = args[i + 1]
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
            safe_print(f"  {idx}. {v['title']}")

        if select_str:
            choice = select_str
            safe_print(f"\n使用 --select 参数: {choice}")
        else:
            print("\n输入要处理的视频编号（如 1,3,5 或 all）:")
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
        safe_print(f"[{idx}/{len(selected)}] {video['title']}")

        try:
            print("  下载中...")
            video_path = download_video(video["url"], use_auth=True)
            if not video_path:
                print("  下载失败，跳过")
                continue

            print("  转录中...")
            transcript = transcribe(video_path, model_size, verbose=False)

            if transcript.strip():
                txt_path = OUTPUT_DIR / f"{sanitize_filename(video['title'])}.txt"
                txt_path.write_text(transcript, encoding="utf-8")

                results.append({
                    "title": video["title"],
                    "url": video["url"],
                    "transcript": transcript,
                })
                print("  完成 ✓")
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
