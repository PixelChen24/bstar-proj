#!/usr/bin/env python3
"""
弹幕评论区智能分析 · API 服务

启动:
    python server.py
    # 打开 http://localhost:8000
"""

import asyncio
import json
import os
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
import uvicorn

from bilibili.video import extract_bvid, fetch_video_info
from bilibili.danmaku import fetch_danmaku
from bilibili.comment import fetch_comments
from analyze_video import run_pipeline, save_json
from analysis.llm import init_backend, test_connection
from analysis import rate_limit
from analysis.danmaku_analysis import build_peak_danmaku_showcase
from analysis.wordcloud import generate_word_clouds_from_records

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="弹幕评论区智能分析")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "frontend")), name="static")

OUTPUT_DIR = str(BASE_DIR / "output")
MAX_COMMENTS = 50  # demo 阶段限制评论数，加快速度


def _flatten_comment_records(comments_data: dict) -> list[dict]:
    records = []
    for c in comments_data.get("comments", []):
        records.append(c)
        for r in c.get("replies", []):
            records.append(r)
    return records


def _ensure_word_clouds(data_dir: str, report: dict) -> dict:
    """补齐并刷新词云字段，兼容旧缓存报告。

    词云统计逻辑会定期迭代，因此只要原始弹幕/评论文件存在，就
    直接从源数据重算一份，避免旧缓存里残留已修正的表情词条。
    同时保留 wordClouds 字段，避免旧前端/旧缓存直接报错。
    """
    try:
        with open(os.path.join(data_dir, "danmaku.json"), "r", encoding="utf-8") as f:
            danmaku_data = json.load(f)
        with open(os.path.join(data_dir, "comments.json"), "r", encoding="utf-8") as f:
            comments_data = json.load(f)
    except OSError:
        if report.get("wordcloud"):
            report.setdefault("wordClouds", report["wordcloud"])
        return report

    danmakus = []
    for seg in danmaku_data.get("segments", []):
        danmakus.extend(seg.get("danmakus", []))
    comments = _flatten_comment_records(comments_data)

    try:
        wc = generate_word_clouds_from_records(danmakus, comments)
        changed = report.get("wordcloud") != wc or report.get("wordClouds") != wc
        report["wordcloud"] = wc
        report["wordClouds"] = wc

        if changed:
            report_path = os.path.join(data_dir, "report.json")
            try:
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
            except OSError as e:
                print(f"⚠ 词云缓存刷新失败: {e}")
    except Exception as e:
        print(f"⚠ 词云生成失败: {e}")
    return report


def _ensure_hot_danmaku(data_dir: str, report: dict) -> dict:
    """补齐高能弹幕飞屏字段，兼容旧缓存报告。"""
    if report.get("hotDanmaku"):
        return report
    peaks = report.get("peaks") or []
    if not peaks:
        return report

    try:
        with open(os.path.join(data_dir, "danmaku.json"), "r", encoding="utf-8") as f:
            danmaku_data = json.load(f)
    except OSError:
        return report

    danmakus = []
    for seg in danmaku_data.get("segments", []):
        danmakus.extend(seg.get("danmakus", []))

    try:
        duration = (report.get("video") or {}).get("duration", 0)
        report["hotDanmaku"] = build_peak_danmaku_showcase(danmakus, peaks, duration)
    except Exception as e:
        print(f"⚠ 高能弹幕飞屏数据生成失败: {e}")
    return report


@app.get("/")
async def index():
    """Serve 前端页面"""
    return FileResponse(str(BASE_DIR / "frontend" / "index.html"))


@app.get("/api/report/{bvid}")
async def get_report(bvid: str):
    """读取已有的 report.json（缓存）"""
    report_path = os.path.join(OUTPUT_DIR, bvid, "report.json")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        report = _ensure_word_clouds(os.path.join(OUTPUT_DIR, bvid), report)
        report = _ensure_hot_danmaku(os.path.join(OUTPUT_DIR, bvid), report)
        return JSONResponse(report)
    return JSONResponse({"error": "报告不存在，请先分析"}, status_code=404)


@app.get("/api/analyze/stream")
async def analyze_stream(
    bvid: str = Query(..., description="BV号"),
    force: bool = Query(False, description="是否强制重新分析，忽略已有报告缓存"),
    request: Request = None,
):
    """SSE 流式分析：采集 + 分析 + 推送进度"""

    # 限流检查
    client_ip = request.client.host if request.client else "unknown"
    allowed, device_id, remaining = rate_limit.check(client_ip)
    if not allowed:
        async def rate_limit_gen():
            yield {"event": "error", "data": json.dumps(
                {"msg": f"今日请求次数已达上限（{rate_limit.DAILY_LIMIT} 次/天），请明天再试。"},
                ensure_ascii=False)}
        return EventSourceResponse(rate_limit_gen())

    if remaining >= 0:
        print(f"[限流] {device_id} 今日已通过，剩余 {remaining} 次")

    try:
        bvid = extract_bvid(bvid)
    except ValueError as e:
        async def error_gen():
            yield {"event": "error", "data": json.dumps({"msg": str(e)}, ensure_ascii=False)}
        return EventSourceResponse(error_gen())

    async def event_generator():
        try:
            data_dir = os.path.join(OUTPUT_DIR, bvid)
            start_time = time.time()

            loop = asyncio.get_running_loop()
            report_path = os.path.join(data_dir, "report.json")

            # ── 阶段 -1: 完整报告缓存 ──
            # 非强制模式下，已有 report.json 直接返回，避免同一个 BV 重复消耗 LLM。
            if not force and os.path.exists(report_path):
                yield {"event": "progress", "data": json.dumps(
                    {"stage": 4, "pct": 1.0, "msg": "使用已生成的报告缓存", "extra": "0s"}, ensure_ascii=False)}
                with open(report_path, "r", encoding="utf-8") as f:
                    report = json.load(f)
                report = _ensure_word_clouds(data_dir, report)
                report = _ensure_hot_danmaku(data_dir, report)
                yield {"event": "done", "data": json.dumps(report, ensure_ascii=False)}
                return

            # ── 阶段 0: 数据采集 ──
            yield {"event": "progress", "data": json.dumps(
                {"stage": 0, "pct": 0.05, "msg": "正在拉取视频信息...", "extra": ""}, ensure_ascii=False)}
            await asyncio.sleep(0.05)

            has_cache = all(
                os.path.exists(os.path.join(data_dir, f))
                for f in ["video_info.json", "danmaku.json", "comments.json"]
            )

            if not has_cache:
                video_info = await loop.run_in_executor(None, fetch_video_info, bvid)
                await loop.run_in_executor(None, save_json, video_info,
                                           os.path.join(data_dir, "video_info.json"))

                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "pct": 0.28, "msg": "拉取弹幕中...", "extra": ""}, ensure_ascii=False)}
                await asyncio.sleep(0.05)

                danmaku_data = await loop.run_in_executor(
                    None, lambda: fetch_danmaku(video_info["pages"], aid=video_info.get("aid")))
                await loop.run_in_executor(None, save_json, danmaku_data,
                                           os.path.join(data_dir, "danmaku.json"))

                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "pct": 0.62, "msg": "拉取评论中...", "extra": ""}, ensure_ascii=False)}
                await asyncio.sleep(0.05)

                comments_data = await loop.run_in_executor(
                    None, lambda: fetch_comments(video_info["aid"], max_comments=MAX_COMMENTS))
                await loop.run_in_executor(None, save_json, comments_data,
                                           os.path.join(data_dir, "comments.json"))

                dm_count = danmaku_data["total_count"]
                cm_count = comments_data["fetched_root"] + comments_data["fetched_replies"]
                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "pct": 1.0, "msg": f"拉取弹幕 {dm_count} 条 / 评论 {cm_count} 条",
                     "extra": f"{time.time()-start_time:.1f}s"}, ensure_ascii=False)}
            else:
                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "pct": 1.0, "msg": "使用缓存数据", "extra": "0s"}, ensure_ascii=False)}

            await asyncio.sleep(0.05)

            # ── 阶段 1-4: 分析管线 ──
            # run_pipeline 是同步函数，放线程池执行；on_progress 通过 asyncio.Queue
            # 立即回传给 SSE，避免等整条管线结束后才一次性显示进度。
            progress_queue: asyncio.Queue[dict] = asyncio.Queue()

            def on_progress(stage, msg, extra="", pct=None):
                evt = {"stage": stage, "msg": msg, "extra": extra}
                if pct is not None:
                    evt["pct"] = pct
                loop.call_soon_threadsafe(progress_queue.put_nowait, evt)

            future = loop.run_in_executor(
                None, lambda: run_pipeline(data_dir, on_progress=on_progress)
            )

            while True:
                if future.done() and progress_queue.empty():
                    break
                try:
                    evt = await asyncio.wait_for(progress_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    if request is not None and await request.is_disconnected():
                        future.cancel()
                        return
                    continue
                yield {"event": "progress", "data": json.dumps(evt, ensure_ascii=False)}

            report = await future

            elapsed = round(time.time() - start_time, 1)
            report["meta"]["elapsed"] = elapsed

            await loop.run_in_executor(None, save_json, report, report_path)

            yield {"event": "done", "data": json.dumps(report, ensure_ascii=False)}

        except Exception as e:
            traceback.print_exc()
            yield {"event": "error", "data": json.dumps(
                {"msg": f"分析失败: 视频不存在"}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    print("🚀 启动弹幕评论区智能分析服务...")
    print("   打开 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
