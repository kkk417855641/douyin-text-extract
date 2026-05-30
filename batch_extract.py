"""
抖音收藏夹批量提取工具（并行版本）

使用多线程并行下载和转录，大幅提升处理速度。

用法:
    python batch_extract.py --select 1-10        处理第 1-10 个视频
    python batch_extract.py --all                处理所有收藏
    python batch_extract.py --select 1,5,10      处理指定视频
"""

import sys
import re
import time
import concurrent.futures
from pathlib import Path
from datetime import datetime

from common import (
    VALID_MODELS, OUTPUT_DIR, AUTH_DIR, USER_AGENT,
    check_dependencies, sanitize_filename, safe_print,
    create_browser_context, transcribe,
)
from favorites import scrape_favorites, generate_summary


def download_single_video(url: str, title: str, index: int, total: int) -> dict:
    """下载单个视频（用于并行执行）"""
    import httpx
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    video_url = None
    video_title = title

    try:
        with sync_playwright() as p:
            browser, context = create_browser_context(p)
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
                for suffix in (" - 抖音", " | 抖音", "- 抖音"):
                    if raw_title.endswith(suffix):
                        raw_title = raw_title[:-len(suffix)]
                video_title = sanitize_filename(raw_title.strip())
            except Exception:
                pass

            browser.close()

        if not video_url:
            safe_print(f"  [{index}/{total}] ✗ 无法提取视频URL: {title[:30]}")
            return None

        # 下载视频
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

        safe_print(f"  [{index}/{total}] ✓ 下载完成: {title[:30]}")
        return {
            "title": title,
            "video_title": video_title,
            "video_path": str(output_path),
            "url": url,
        }

    except Exception as e:
        safe_print(f"  [{index}/{total}] ✗ 下载失败: {title[:30]} - {e}")
        return None


def transcribe_single_video(video_info: dict, model_size: str, index: int, total: int) -> dict:
    """转录单个视频（用于并行执行）"""
    try:
        safe_print(f"  [{index}/{total}] 转录中: {video_info['title'][:30]}")
        transcript = transcribe(video_info["video_path"], model_size, verbose=False)

        if transcript.strip():
            # 保存单个文案
            txt_path = OUTPUT_DIR / f"{sanitize_filename(video_info['title'])}.txt"
            txt_path.write_text(transcript, encoding="utf-8")

            safe_print(f"  [{index}/{total}] ✓ 转录完成: {video_info['title'][:30]}")
            return {
                "title": video_info["title"],
                "url": video_info["url"],
                "transcript": transcript,
            }
        else:
            safe_print(f"  [{index}/{total}] ✗ 未识别到文字: {video_info['title'][:30]}")
            return None

    except Exception as e:
        safe_print(f"  [{index}/{total}] ✗ 转录失败: {video_info['title'][:30]} - {e}")
        return None


def process_videos_parallel(videos: list, model_size: str = "medium", max_workers: int = 3):
    """并行处理多个视频

    Args:
        videos: 视频列表
        model_size: Whisper 模型大小
        max_workers: 最大并行数（默认 3，避免占用太多资源）
    """
    total = len(videos)
    print(f"\n开始并行处理 {total} 个视频（并行数: {max_workers}）\n")

    # 第一阶段：并行下载
    print("=" * 50)
    print("阶段 1: 并行下载视频")
    print("=" * 50)

    downloaded = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for idx, video in enumerate(videos, 1):
            future = executor.submit(
                download_single_video,
                video["url"],
                video["title"],
                idx,
                total,
            )
            futures.append(future)

        # 等待所有下载完成
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                downloaded.append(result)

    print(f"\n下载完成: {len(downloaded)}/{total}\n")

    if not downloaded:
        print("没有成功下载的视频")
        return []

    # 第二阶段：并行转录
    print("=" * 50)
    print("阶段 2: 并行转录音频")
    print("=" * 50)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for idx, video_info in enumerate(downloaded, 1):
            future = executor.submit(
                transcribe_single_video,
                video_info,
                model_size,
                idx,
                len(downloaded),
            )
            futures.append(future)

        # 等待所有转录完成
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    print(f"\n转录完成: {len(results)}/{len(downloaded)}")
    return results


def print_help():
    print(
        """抖音收藏夹批量提取工具（并行版本）

用法:
    python batch_extract.py --select 1-10        处理第 1-10 个视频
    python batch_extract.py --all                处理所有收藏
    python batch_extract.py --select 1,5,10      处理指定视频

选项:
    --model <size>     语音模型大小 (默认 medium)
    --workers <n>      并行数 (默认 3)
    --all              处理所有收藏视频
    --select <ids>     指定要处理的视频编号
    --help             显示此帮助"""
    )


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print_help()
        sys.exit(0)

    check_dependencies()

    # 解析参数
    model_size = "medium"
    max_workers = 3
    auto_all = False
    select_str = None

    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_size = args[i + 1].lower()
            i += 2
        elif args[i] == "--workers" and i + 1 < len(args):
            max_workers = int(args[i + 1])
            i += 2
        elif args[i] == "--select" and i + 1 < len(args):
            select_str = args[i + 1]
            i += 2
        elif args[i] == "--all":
            auto_all = True
            i += 1
        else:
            print(f"未知参数: {args[i]}")
            sys.exit(1)

    if model_size not in VALID_MODELS:
        print(f"无效的模型: {model_size}，可选: {', '.join(VALID_MODELS)}")
        sys.exit(1)

    # 检查登录状态
    if not (AUTH_DIR / "state.json").exists():
        print("未找到登录状态，请先运行: python favorites.py --login")
        sys.exit(1)

    # 抓取收藏列表
    videos = scrape_favorites()

    if not videos:
        print("未找到收藏视频")
        return

    # 显示列表
    print("\n收藏视频列表:")
    for idx, v in enumerate(videos, 1):
        safe_print(f"  {idx}. {v['title']}")

    # 选择视频
    if auto_all:
        selected = videos
    elif select_str:
        if select_str.lower() == "all":
            selected = videos
        else:
            indices = []
            for part in select_str.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-")
                    indices.extend(range(int(start), int(end) + 1))
                elif part.isdigit():
                    indices.append(int(part))
            selected = [videos[i - 1] for i in indices if 0 < i <= len(videos)]
    else:
        print("\n请使用 --select 指定视频编号，或 --all 处理全部")
        return

    print(f"\n将处理 {len(selected)} 个视频")

    # 并行处理
    results = process_videos_parallel(selected, model_size, max_workers)

    # 生成汇总
    if results:
        print(f"\n正在生成汇总文档...")
        generate_summary(results, OUTPUT_DIR)
        print(f"\n全部完成！共处理 {len(results)} 个视频")
    else:
        print("\n没有成功处理的视频")


if __name__ == "__main__":
    main()
