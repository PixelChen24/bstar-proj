#!/usr/bin/env python3
"""
弹幕评论区智能分析 · 数据采集脚本

用法:
    python fetch_video.py BV1xx411c7mD
    python fetch_video.py https://www.bilibili.com/video/BV1xx411c7mD
    python fetch_video.py BV1xx411c7mD --max-comments 200 --output-dir ./data
"""

import argparse
import json
import os
import sys
import time

from bilibili.video import extract_bvid, fetch_video_info
from bilibili.danmaku import fetch_danmaku
from bilibili.comment import fetch_comments


def save_json(data: dict, filepath: str) -> None:
    """保存字典为 JSON 文件。"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"  💾 已保存: {filepath} ({size_kb:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(
        description="B站视频弹幕+评论数据采集工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  python fetch_video.py BV117411r7R1\n"
               "  python fetch_video.py https://www.bilibili.com/video/BV117411r7R1\n",
    )
    parser.add_argument(
        "input",
        help="BV 号或包含 BV 号的链接",
    )
    parser.add_argument(
        "--max-comments", type=int, default=500,
        help="最多采集的根评论条数 (默认: 500)",
    )
    parser.add_argument(
        "--output-dir", type=str, default="./output",
        help="输出目录 (默认: ./output)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.3,
        help="请求间隔秒数 (默认: 0.3)",
    )
    parser.add_argument(
        "--skip-danmaku", action="store_true",
        help="跳过弹幕采集",
    )
    parser.add_argument(
        "--skip-comments", action="store_true",
        help="跳过评论采集",
    )

    args = parser.parse_args()

    # 1. 解析 BV 号
    try:
        bvid = extract_bvid(args.input)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    output_dir = os.path.join(args.output_dir, bvid)
    start_time = time.time()

    print("=" * 60)
    print("  弹幕评论区智能分析 · 数据采集")
    print("=" * 60)

    # 2. 获取视频信息
    try:
        video_info = fetch_video_info(bvid)
    except Exception as e:
        print(f"❌ 获取视频信息失败: {e}")
        sys.exit(1)

    save_json(video_info, os.path.join(output_dir, "video_info.json"))

    # 3. 采集弹幕
    danmaku_data = None
    if not args.skip_danmaku:
        try:
            danmaku_data = fetch_danmaku(
                video_info["pages"], delay=args.delay
            )
            save_json(danmaku_data, os.path.join(output_dir, "danmaku.json"))
        except Exception as e:
            print(f"⚠ 弹幕采集出错: {e}")

    # 4. 采集评论
    comments_data = None
    if not args.skip_comments:
        try:
            comments_data = fetch_comments(
                video_info["aid"],
                max_comments=args.max_comments,
                delay=args.delay,
            )
            save_json(comments_data, os.path.join(output_dir, "comments.json"))
        except Exception as e:
            print(f"⚠ 评论采集出错: {e}")

    # 5. 打印摘要
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print("  📊 采集摘要")
    print("=" * 60)
    print(f"  视频: {video_info['title']}")
    print(f"  UP主: {video_info['up']['name']}")
    print(f"  BV号: {bvid}")
    if danmaku_data:
        print(f"  弹幕: {danmaku_data['total_count']} 条")
    if comments_data:
        print(f"  评论: {comments_data['fetched_root']} 条根评论 + "
              f"{comments_data['fetched_replies']} 条子评论")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  输出: {os.path.abspath(output_dir)}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
