"""B站视频元信息采集"""

import os
import re
import time
import requests
import urllib3

# 部分环境缺少根证书，允许通过环境变量关闭 SSL 验证
VERIFY_SSL = os.environ.get("BILIBILI_VERIFY_SSL", "0") != "0"
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 公共 Headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
}

# 登录态（可选）。未登录时评论接口只回降级响应——实测评论区上万条的视频
# 也只返回 3 条根评论，且换排序无效——所以要拿到完整评论必须带 Cookie。
# 取值方式：浏览器登录 B站 → 开发者工具 → Application → Cookies → 复制 SESSDATA。
# 这是账号凭据，请用环境变量传入，不要写进代码或提交到仓库。
SESSDATA = os.environ.get("BILIBILI_SESSDATA", "").strip()
if SESSDATA:
    HEADERS["Cookie"] = f"SESSDATA={SESSDATA}"
    print("🔑 已启用 B站登录态（BILIBILI_SESSDATA）")

# BV 号正则
BV_PATTERN = re.compile(r"BV[a-zA-Z0-9]{10}")

API_VIDEO_VIEW = "http://api.bilibili.com/x/web-interface/view"


def extract_bvid(input_str: str) -> str:
    """从用户输入中提取 BV 号，支持纯 BV 号或完整链接。"""
    input_str = input_str.strip()
    match = BV_PATTERN.search(input_str)
    if match:
        return match.group(0)
    raise ValueError(f"无法识别 BV 号: {input_str}")


def _request_with_retry(url: str, params: dict, max_retries: int = 3) -> dict:
    """带重试的 GET 请求，返回 JSON。"""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10, verify=VERIFY_SSL)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(
                    f"API 返回错误 code={data.get('code')}: {data.get('message', '未知错误')}"
                )
            return data["data"]
        except (requests.RequestException, RuntimeError) as e:
            if attempt == max_retries:
                raise
            print(f"  ⚠ 请求失败 ({attempt}/{max_retries}): {e}，重试中...")
            time.sleep(1 * attempt)
    # 不应到达这里
    raise RuntimeError("请求失败")


def fetch_video_info(bvid: str) -> dict:
    """
    获取视频详细信息。

    返回精简后的字典：
    {
        "bvid", "aid", "title", "up", "cover", "duration",
        "stat", "pages", "desc", "pubdate", "tname"
    }
    """
    print(f"📺 正在获取视频信息: {bvid}")
    raw = _request_with_retry(API_VIDEO_VIEW, {"bvid": bvid})

    owner = raw.get("owner", {})
    stat = raw.get("stat", {})
    pages = raw.get("pages", [])

    info = {
        "bvid": raw.get("bvid", bvid),
        "aid": raw.get("aid"),
        "title": raw.get("title", ""),
        "desc": raw.get("desc", ""),
        "tname": raw.get("tname", ""),
        "pubdate": raw.get("pubdate"),
        "up": {
            "mid": owner.get("mid"),
            "name": owner.get("name", ""),
            "face": owner.get("face", ""),
        },
        "cover": raw.get("pic", ""),
        "duration": raw.get("duration", 0),
        "stat": {
            "view": stat.get("view", 0),
            "danmaku": stat.get("danmaku", 0),
            "reply": stat.get("reply", 0),
            "favorite": stat.get("favorite", 0),
            "coin": stat.get("coin", 0),
            "share": stat.get("share", 0),
            "like": stat.get("like", 0),
        },
        "pages": [
            {
                "cid": p.get("cid"),
                "page": p.get("page"),
                "part": p.get("part", ""),
                "duration": p.get("duration", 0),
            }
            for p in pages
        ],
    }

    view_str = _format_count(info["stat"]["view"])
    print(f"  ✔ {info['title']}")
    print(f"    UP主: {info['up']['name']} | 播放: {view_str} | "
          f"弹幕: {info['stat']['danmaku']} | 评论: {info['stat']['reply']}")
    print(f"    分P数: {len(info['pages'])} | 时长: {info['duration']}s")

    return info


def _format_count(n: int) -> str:
    """将数字格式化为易读形式，如 12300 -> '1.2w'。"""
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}w"
    return str(n)
