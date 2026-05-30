"""
douyin-text-extract: 抖音视频文案提取工具（单视频模式）

从抖音视频链接自动下载视频并转录为文字。

用法:
    python extract.py <抖音视频URL>
    python extract.py --file <本地视频文件>
    python extract.py --help
"""

import sys
from pathlib import Path

from common import (
    VALID_MODELS, OUTPUT_DIR,
    check_dependencies, download_video, transcribe, save_transcript,
)


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
        print("正在下载视频...")
        video_path = download_video(url, use_auth=False)
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
