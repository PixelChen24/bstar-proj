#!/usr/bin/env python3
"""
弹幕评论区智能分析 · API 服务

启动:
    export HF_ENDPOINT=https://hf-mirror.com
    python server.py
    # 打开 http://localhost:8000
"""

import asyncio
import json
import os
import time
import traceback

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

from bilibili.video import extract_bvid, fetch_video_info
from bilibili.danmaku import fetch_danmaku
from bilibili.comment import fetch_comments
from analyze_video import run_pipeline, save_json

app = FastAPI(title="弹幕评论区智能分析")

OUTPUT_DIR = "./output"
MODEL_NAME = os.environ.get("LLM_MODEL", "Qwen/Qwen3-0.6B")
MAX_COMMENTS = 50  # demo 阶段限制评论数，加快速度


@app.get("/")
async def index():
    """Serve 前端页面"""
    return FileResponse("danmaku-comment-insight-demo.html")


@app.get("/api/report/{bvid}")
async def get_report(bvid: str):
    """读取已有的 report.json（缓存）"""
    report_path = os.path.join(OUTPUT_DIR, bvid, "report.json")
    if os.path.exists(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            return JSONResponse(json.load(f))
    return JSONResponse({"error": "报告不存在，请先分析"}, status_code=404)


@app.get("/api/analyze/stream")
async def analyze_stream(bvid: str = Query(..., description="BV号")):
    """SSE 流式分析：采集 + 分析 + 推送进度"""

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

            # ── 阶段 0: 数据采集 ──
            yield {"event": "progress", "data": json.dumps(
                {"stage": 0, "msg": "正在拉取视频信息...", "extra": ""}, ensure_ascii=False)}
            await asyncio.sleep(0.05)

            # 检查缓存
            has_cache = all(
                os.path.exists(os.path.join(data_dir, f))
                for f in ["video_info.json", "danmaku.json", "comments.json"]
            )

            if not has_cache:
                # 采集
                loop = asyncio.get_event_loop()

                video_info = await loop.run_in_executor(None, fetch_video_info, bvid)
                await loop.run_in_executor(None, save_json, video_info,
                                           os.path.join(data_dir, "video_info.json"))

                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "msg": f"拉取弹幕中...", "extra": ""}, ensure_ascii=False)}
                await asyncio.sleep(0.05)

                danmaku_data = await loop.run_in_executor(
                    None, lambda: fetch_danmaku(video_info["pages"]))
                await loop.run_in_executor(None, save_json, danmaku_data,
                                           os.path.join(data_dir, "danmaku.json"))

                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "msg": f"拉取评论中...", "extra": ""}, ensure_ascii=False)}
                await asyncio.sleep(0.05)

                comments_data = await loop.run_in_executor(
                    None, lambda: fetch_comments(video_info["aid"], max_comments=MAX_COMMENTS))
                await loop.run_in_executor(None, save_json, comments_data,
                                           os.path.join(data_dir, "comments.json"))

                dm_count = danmaku_data["total_count"]
                cm_count = comments_data["fetched_root"] + comments_data["fetched_replies"]
                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "msg": f"拉取弹幕 {dm_count} 条 / 评论 {cm_count} 条",
                     "extra": f"{time.time()-start_time:.1f}s"}, ensure_ascii=False)}
            else:
                yield {"event": "progress", "data": json.dumps(
                    {"stage": 0, "msg": "使用缓存数据", "extra": "0s"}, ensure_ascii=False)}

            await asyncio.sleep(0.05)

            # ── 阶段 1-4: 分析管线 ──
            progress_events = []

            def on_progress(stage, msg, extra=""):
                progress_events.append({"stage": stage, "msg": msg, "extra": extra})

            loop = asyncio.get_event_loop()
            report = await loop.run_in_executor(
                None, lambda: run_pipeline(
                    data_dir, model_name=MODEL_NAME, on_progress=on_progress
                )
            )

            # 推送所有进度事件
            for evt in progress_events:
                yield {"event": "progress", "data": json.dumps(evt, ensure_ascii=False)}
                await asyncio.sleep(0.05)

            # 记录耗时
            elapsed = round(time.time() - start_time, 1)
            report["meta"]["elapsed"] = elapsed

            # 保存
            report_path = os.path.join(data_dir, "report.json")
            await loop.run_in_executor(None, save_json, report, report_path)

            # ── 完成：发送完整报告 ──
            yield {"event": "done", "data": json.dumps(report, ensure_ascii=False)}

        except Exception as e:
            traceback.print_exc()
            yield {"event": "error", "data": json.dumps(
                {"msg": f"分析失败: {str(e)}"}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


if __name__ == "__main__":
    print("🚀 启动弹幕评论区智能分析服务...")
    print("   打开 http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
