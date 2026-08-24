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

from fastapi import Body, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
import uvicorn

from bilibili.video import extract_bvid, fetch_video_info
from bilibili.danmaku import fetch_danmaku
from bilibili.comment import fetch_comments
from analyze_video import run_pipeline, save_json
from analysis import llm_config
from analysis.llm import init_backend, test_connection

app = FastAPI(title="弹幕评论区智能分析")

OUTPUT_DIR = "./output"
MAX_COMMENTS = 50  # demo 阶段限制评论数，加快速度


@app.get("/")
async def index():
    """Serve 前端页面"""
    return FileResponse("danmaku-comment-insight-demo.html")


# ─── LLM 配置 ──────────────────────────────────────────────
#
# 这些接口能读写 API Key，且本服务没有任何鉴权，所以默认只允许来自本机的
# 写操作/连通性测试。要在远端机器上用设置面板，需显式设置
# ALLOW_REMOTE_CONFIG=1，并自行套一层 HTTPS + 访问控制——否则 Key 会以明文
# 经 HTTP 传输。

ALLOW_REMOTE_CONFIG = os.environ.get("ALLOW_REMOTE_CONFIG", "0") != "0"


def _local_only(request) -> JSONResponse | None:
    """非本机来源且未显式放开时，拒绝请求。"""
    if ALLOW_REMOTE_CONFIG:
        return None
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return None
    return JSONResponse(
        {"error": "出于安全考虑，仅允许本机修改 LLM 配置。"
                  "如需远程配置，请设置环境变量 ALLOW_REMOTE_CONFIG=1 并启用 HTTPS。"},
        status_code=403,
    )


@app.get("/api/llm/config")
async def get_llm_config():
    """当前 LLM 配置（API Key 已脱敏）+ 可选项与配置来源"""
    cfg = llm_config.load_config()
    return JSONResponse({
        "config": llm_config.public_view(cfg),
        "errors": llm_config.validate(cfg),
        "presets": llm_config.OPENAI_PRESETS,
        "anthropic_models": llm_config.ANTHROPIC_MODELS,
        "sources": llm_config.describe_sources(),
        "allow_remote_config": ALLOW_REMOTE_CONFIG,
    })


@app.post("/api/llm/config")
async def set_llm_config(request: Request, patch: dict = Body(...)):
    """保存 LLM 配置到本地文件（权限 0600）。

    api_key 留空表示保留原值，方便前端提交脱敏后的表单。
    """
    denied = _local_only(request)
    if denied:
        return denied

    try:
        cfg = llm_config.save_config(patch)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except OSError as e:
        return JSONResponse({"error": f"配置写入失败: {e}"}, status_code=500)

    return JSONResponse({
        "config": llm_config.public_view(cfg),
        "sources": llm_config.describe_sources(),
        "saved_to": llm_config.describe_sources()["config_path"],
    })


@app.post("/api/llm/test")
async def test_llm(request: Request, patch: dict = Body(default={})):
    """测试 LLM 连通性。patch 为空时测试当前已保存的配置。"""
    denied = _local_only(request)
    if denied:
        return denied

    cfg = llm_config.load_config()
    if patch:
        # 复用 override 的合并逻辑：只覆盖传入的字段，api_key 留空则沿用已存的
        provider = patch.get("provider") or cfg["provider"]
        section = patch.get(provider) or {}
        cfg = llm_config.override(
            cfg,
            provider=provider,
            model=section.get("model"),
            api_key=section.get("api_key"),
            base_url=section.get("base_url"),
        )

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: test_connection(cfg))
    return JSONResponse(result, status_code=200 if result.get("ok") else 400)


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
                    data_dir, on_progress=on_progress
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
