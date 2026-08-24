#!/usr/bin/env python3
"""
弹幕评论区智能分析 · 分析管线

用法:
    python analyze_video.py BV1xx411c7mD
    python analyze_video.py ./output/BV117411r7R1/
"""

import argparse
import json
import os
import sys
import time
from typing import Callable

from bilibili.video import extract_bvid, fetch_video_info
from bilibili.danmaku import fetch_danmaku
from bilibili.comment import fetch_comments
from analysis.llm import init_backend
from analysis.llm_config import load_config, override
from analysis.clean import clean_danmakus, clean_comments
from analysis.danmaku_analysis import analyze_danmaku
from analysis.comment_analysis import analyze_comments
from analysis.report import generate_report
from analysis.wordcloud import generate_word_clouds_from_records


def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: dict, filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"  💾 已保存: {filepath} ({size_kb:.1f} KB)")


def _format_count(n: int) -> str:
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}w"
    return str(n)


# ─── 核心管线函数（供 CLI 和 server.py 共用）──────────────────

def run_fetch(bvid: str, output_dir: str = "./output",
              max_comments: int = 500, delay: float = 0.3,
              on_progress: Callable | None = None) -> str:
    """
    采集数据并保存。返回数据目录路径。
    on_progress(stage, msg, extra) 用于推送进度。
    """
    data_dir = os.path.join(output_dir, bvid)

    def _progress(stage, msg, extra=""):
        if on_progress:
            on_progress(stage, msg, extra)

    # 视频信息
    t0 = time.time()
    video_info = fetch_video_info(bvid)
    save_json(video_info, os.path.join(data_dir, "video_info.json"))
    dm_count = video_info["stat"]["danmaku"]
    cm_count = video_info["stat"]["reply"]
    _progress(0, f"拉取视频信息完成 / 弹幕 {dm_count} / 评论 {cm_count}", f"{time.time()-t0:.1f}s")

    # 弹幕
    t0 = time.time()
    danmaku_data = fetch_danmaku(video_info["pages"], delay=delay, aid=video_info.get("aid"))
    save_json(danmaku_data, os.path.join(data_dir, "danmaku.json"))
    _progress(0, f"拉取弹幕 {danmaku_data['total_count']} 条", f"{time.time()-t0:.1f}s")

    # 评论
    t0 = time.time()
    comments_data = fetch_comments(video_info["aid"], max_comments=max_comments, delay=delay)
    save_json(comments_data, os.path.join(data_dir, "comments.json"))
    total_cm = comments_data["fetched_root"] + comments_data["fetched_replies"]
    _progress(0, f"拉取评论 {total_cm} 条", f"{time.time()-t0:.1f}s")

    return data_dir


def run_pipeline(data_dir: str, cfg: dict | None = None,
                 skip_clean: bool = False,
                 on_progress: Callable | None = None) -> dict:
    """
    运行完整分析管线。

    参数:
        data_dir: 数据目录路径（含 video_info.json, danmaku.json, comments.json）
        cfg: LLM 配置（None 时从环境变量+配置文件读取）
        skip_clean: 是否跳过清洗
        on_progress: 进度回调 on_progress(stage, msg, extra)

    返回: report dict
    """
    logs = []
    cfg = cfg or load_config()

    def _progress(stage, msg, extra="", pct=None):
        logs.append([msg, extra])
        if on_progress:
            on_progress(stage, msg, extra, pct)

    # 1. 加载数据
    video_info = load_json(os.path.join(data_dir, "video_info.json"))
    danmaku_data = load_json(os.path.join(data_dir, "danmaku.json"))
    comments_data = load_json(os.path.join(data_dir, "comments.json"))

    all_danmakus = []
    for seg in danmaku_data.get("segments", []):
        all_danmakus.extend(seg.get("danmakus", []))

    all_comments = []
    for c in comments_data.get("comments", []):
        all_comments.append(c)
        for r in c.get("replies", []):
            r.setdefault("rcount", 0)
            all_comments.append(r)

    # 2. 初始化 LLM 后端
    backend_label = init_backend(cfg)
    _progress(1, f"LLM 后端就绪：{backend_label}", "", 0.08)

    # 3. 清洗
    t0 = time.time()
    clean_stats = {}
    if not skip_clean:
        all_danmakus, dm_cs = clean_danmakus(all_danmakus)
        all_comments, cm_cs = clean_comments(all_comments)
        clean_stats = {"danmaku": dm_cs, "comment": cm_cs}
        dm_kept = dm_cs["kept"]
        cm_kept = cm_cs["kept"]
        dm_removed = dm_cs["total"] - dm_kept
        cm_removed = cm_cs["total"] - cm_kept
        _progress(1, f"清洗去重：过滤弹幕 {dm_removed} 条、评论 {cm_removed} 条",
                  f"剩余 {dm_kept + cm_kept} 条", 1.0)
    else:
        _progress(1, "跳过清洗", "", 1.0)

    # 4. 词云数据
    word_clouds = generate_word_clouds_from_records(all_danmakus, all_comments)

    # 5. 弹幕分析
    t0 = time.time()
    dm_themes, peaks = analyze_danmaku(all_danmakus, video_info.get("duration", 0), on_progress=on_progress)
    _progress(2, f"聚类得 {len(dm_themes)} 个弹幕主题 + {len(peaks)} 个峰值",
              f"{time.time()-t0:.1f}s", 1.0)

    # 6. 评论分析
    t0 = time.time()
    cm_themes = analyze_comments(all_comments, comments_data.get("total_count", len(all_comments)), on_progress=on_progress)
    _progress(3, f"归纳为 {len(dm_themes)} 个弹幕主题 / {len(cm_themes)} 个评论主题",
              f"{time.time()-t0:.1f}s", 1.0)

    # 7. 报告生成
    t0 = time.time()
    slots, acts = generate_report(dm_themes, peaks, cm_themes, video_info, on_progress=on_progress)
    _progress(4, f"生成复盘报告与 Top{len(acts)} 建议", f"{time.time()-t0:.1f}s", 1.0)

    # 8. 组装
    stat = video_info.get("stat", {})
    report = {
        "video": {
            "title": video_info.get("title", ""),
            "up": f"@{video_info.get('up', {}).get('name', '')}",
            "play": _format_count(stat.get("view", 0)),
            "dm": stat.get("danmaku", 0),
            "cm": stat.get("reply", 0),
            "bvid": video_info.get("bvid", ""),
            "cover": video_info.get("cover", ""),
            "duration": video_info.get("duration", 0),  # 秒，前端画时间轴用
        },
        "dmThemes": dm_themes,
        "peaks": peaks,
        "cmThemes": cm_themes,
        "slots": slots,
        "acts": acts,
        "wordClouds": word_clouds,
        "logs": logs,
        "meta": {
            "provider": cfg["provider"],
            "model": cfg[cfg["provider"]].get("model", ""),
            "backend": backend_label,
            "clean_stats": clean_stats,
        },
    }

    return report


# ─── CLI 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="B站视频弹幕+评论智能分析管线")
    parser.add_argument("input", help="BV 号或已采集数据的目录路径")
    parser.add_argument("--provider", choices=["openai", "anthropic"],
                        help="LLM 后端 (默认: 读取配置文件/环境变量，缺省 anthropic)")
    parser.add_argument("--model", type=str, help="模型名称，覆盖配置")
    parser.add_argument("--api-key", type=str,
                        help="API Key，覆盖配置（更推荐用环境变量，避免出现在 shell 历史里）")
    parser.add_argument("--base-url", type=str, help="接口地址，覆盖配置")
    parser.add_argument("--output-dir", type=str, default="./output",
                        help="输出根目录 (默认: ./output)")
    parser.add_argument("--skip-clean", action="store_true", help="跳过清洗步骤")
    args = parser.parse_args()

    cfg = override(load_config(), provider=args.provider, model=args.model,
                   api_key=args.api_key, base_url=args.base_url)

    start_time = time.time()

    # 定位数据目录
    input_dir = _resolve_input_dir(args.input, args.output_dir)
    if not input_dir:
        sys.exit(1)

    print("=" * 60)
    print("  弹幕评论区智能分析 · 分析管线")
    print("=" * 60)

    # 运行管线
    report = run_pipeline(input_dir, cfg=cfg, skip_clean=args.skip_clean)

    elapsed = round(time.time() - start_time, 1)
    report["meta"]["elapsed"] = elapsed

    # 保存
    report_path = os.path.join(input_dir, "report.json")
    save_json(report, report_path)

    # 摘要
    print("\n" + "=" * 60)
    print("  📊 分析完成")
    print("=" * 60)
    print(f"  视频: {report['video']['title']}")
    print(f"  弹幕主题: {len(report['dmThemes'])} 个")
    print(f"  高能时刻: {len(report['peaks'])} 个")
    print(f"  评论主题: {len(report['cmThemes'])} 个")
    print(f"  复盘结论: {len(report['slots'])} 条")
    print(f"  改进建议: {len(report['acts'])} 条")
    print(f"  总耗时: {elapsed}s")
    print(f"  报告: {os.path.abspath(report_path)}")
    print("=" * 60)


def _resolve_input_dir(input_str: str, output_root: str) -> str | None:
    if os.path.isdir(input_str):
        return input_str
    try:
        bvid = extract_bvid(input_str)
        dir_path = os.path.join(output_root, bvid)
        if os.path.isdir(dir_path):
            return dir_path
        else:
            print(f"❌ 数据目录不存在: {dir_path}")
            print(f"   请先运行: python fetch_video.py {bvid}")
            return None
    except ValueError:
        print(f"❌ 无法识别输入: {input_str}")
        return None


if __name__ == "__main__":
    main()
