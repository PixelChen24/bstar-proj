"""B站弹幕采集（XML 方式）"""

import time
import xml.etree.ElementTree as ET

import requests

from .video import HEADERS, VERIFY_SSL

API_DANMAKU_XML = "http://api.bilibili.com/x/v1/dm/list.so"


def fetch_danmaku(pages: list[dict], delay: float = 0.3) -> dict:
    """
    获取视频全部分P的弹幕。

    参数:
        pages: 视频分P信息列表，每个元素含 cid, page, part, duration
        delay: 每次请求间隔秒数

    返回:
        {
            "total_count": int,
            "segments": [
                {
                    "cid": int,
                    "page": int,
                    "part": str,
                    "count": int,
                    "danmakus": [...]
                }
            ]
        }
    """
    print(f"\n💬 正在采集弹幕 (共 {len(pages)} 个分P)...")
    segments = []
    total_count = 0

    for p in pages:
        cid = p["cid"]
        page_num = p["page"]
        part = p.get("part", "")
        label = f"P{page_num}" + (f" {part}" if part else "")

        print(f"  ⏳ 拉取 {label} (cid={cid})...", end="", flush=True)

        danmakus = _fetch_danmaku_for_cid(cid)
        count = len(danmakus)
        total_count += count

        segments.append({
            "cid": cid,
            "page": page_num,
            "part": part,
            "count": count,
            "danmakus": danmakus,
        })
        print(f" {count} 条")

        if len(pages) > 1:
            time.sleep(delay)

    print(f"  ✔ 弹幕采集完成，共 {total_count} 条")
    return {
        "total_count": total_count,
        "segments": segments,
    }


def _fetch_danmaku_for_cid(cid: int, max_retries: int = 3) -> list[dict]:
    """拉取单个 cid 的全部弹幕（XML 方式）。"""
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                API_DANMAKU_XML,
                params={"oid": cid},
                headers=HEADERS,
                timeout=15,
                verify=VERIFY_SSL,
            )
            resp.raise_for_status()
            # 接口返回 deflate 压缩的 XML，requests 自动解压
            # 但 Content-Type 可能是 application/octet-stream，需手动解码
            content = resp.content
            return _parse_danmaku_xml(content)
        except Exception as e:
            if attempt == max_retries:
                print(f"\n  ⚠ cid={cid} 弹幕拉取失败: {e}")
                return []
            time.sleep(1 * attempt)
    return []


def _parse_danmaku_xml(content: bytes) -> list[dict]:
    """解析弹幕 XML 内容，返回弹幕列表。"""
    try:
        # 尝试直接解析（requests 可能已自动解压）
        root = ET.fromstring(content)
    except ET.ParseError:
        # 如果解析失败，尝试用 deflate 解压
        import zlib
        try:
            decompressed = zlib.decompress(content, -zlib.MAX_WBITS)
            root = ET.fromstring(decompressed)
        except Exception:
            # 再尝试标准 deflate
            decompressed = zlib.decompress(content)
            root = ET.fromstring(decompressed)

    danmakus = []
    for d in root.iter("d"):
        p_attr = d.get("p", "")
        text = d.text or ""
        if not p_attr:
            continue

        parts = p_attr.split(",")
        if len(parts) < 8:
            continue

        try:
            progress = float(parts[0])       # 视频内出现时间（秒）
            mode = int(parts[1])             # 弹幕类型
            fontsize = int(parts[2])         # 字号
            color_dec = int(parts[3])        # 十进制 RGB888 颜色
            send_time = int(parts[4])        # 发送时间戳
            pool = int(parts[5])             # 弹幕池
            mid_hash = parts[6]              # 发送者 mid hash
            dmid = parts[7]                  # 弹幕 ID
        except (ValueError, IndexError):
            continue

        danmakus.append({
            "dmid": dmid,
            "progress": round(progress, 2),
            "mode": mode,
            "fontsize": fontsize,
            "color": _dec_to_hex_color(color_dec),
            "send_time": send_time,
            "pool": pool,
            "mid_hash": mid_hash,
            "content": text,
        })

    return danmakus


def _dec_to_hex_color(dec: int) -> str:
    """十进制 RGB888 转 #RRGGBB 格式。"""
    return f"#{dec:06X}"
