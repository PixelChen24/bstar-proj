"""B站弹幕采集（seg.so 分段 protobuf 方式）"""

from __future__ import annotations

import math
import struct
import time

import requests

from .video import HEADERS, VERIFY_SSL

API_DANMAKU_SEG = "https://api.bilibili.com/x/v2/dm/web/seg.so"
SEGMENT_SECONDS = 360


def fetch_danmaku(pages: list[dict], delay: float = 0.3, aid: int | None = None) -> dict:
    """
    获取视频全部分P的弹幕。

    新版接口按 6 分钟一段返回 protobuf 二进制弹幕，需要逐段拉取并解析。

    参数:
        pages: 视频分P信息列表，每个元素含 cid, page, part, duration
        delay: 每次请求间隔秒数
        aid: 可选稿件 avid，用于新版弹幕接口的 pid 参数

    返回:
        {
            "total_count": int,
            "segments": [
                {
                    "cid": int,
                    "page": int,
                    "part": str,
                    "duration": int,
                    "segment_count": int,
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
        duration = int(p.get("duration", 0) or 0)
        segment_count = max(1, math.ceil(duration / SEGMENT_SECONDS)) if duration > 0 else 1
        label = f"P{page_num}" + (f" {part}" if part else "")

        print(f"  ⏳ 拉取 {label} (cid={cid}, {segment_count} 段)...")

        danmakus = []
        for seg_idx in range(1, segment_count + 1):
            print(f"    ↳ 段 {seg_idx}/{segment_count}...", end="", flush=True)
            seg_danmakus = _fetch_danmaku_segment(cid, seg_idx, aid=aid)
            danmakus.extend(seg_danmakus)
            print(f" {len(seg_danmakus)} 条")
            if segment_count > 1:
                time.sleep(delay)

        count = len(danmakus)
        total_count += count

        segments.append({
            "cid": cid,
            "page": page_num,
            "part": part,
            "duration": duration,
            "segment_count": segment_count,
            "count": count,
            "danmakus": danmakus,
        })
        print(f"  ✔ {label} 共 {count} 条")

        if len(pages) > 1:
            time.sleep(delay)

    print(f"  ✔ 弹幕采集完成，共 {total_count} 条")
    return {
        "total_count": total_count,
        "segments": segments,
    }


def _fetch_danmaku_segment(cid: int, segment_index: int, max_retries: int = 3, aid: int | None = None) -> list[dict]:
    """拉取单个 cid 的单个分段弹幕（protobuf 方式）。"""
    params = {
        "type": 1,
        "oid": cid,
        "segment_index": segment_index,
    }
    if aid is not None:
        params["pid"] = aid

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                API_DANMAKU_SEG,
                params=params,
                headers=HEADERS,
                timeout=15,
                verify=VERIFY_SSL,
            )
            resp.raise_for_status()

            ctype = resp.headers.get("Content-Type", "").lower()
            if "application/json" in ctype or resp.content[:1] in (b"{", b"["):
                data = resp.json()
                if isinstance(data, dict) and data.get("code", 0) != 0:
                    raise RuntimeError(
                        f"API 返回错误 code={data.get('code')}: {data.get('message', '未知错误')}"
                    )
                raise RuntimeError("弹幕接口返回了 JSON 而不是 protobuf 数据")

            return _parse_danmaku_reply(resp.content)
        except Exception as e:
            if attempt == max_retries:
                print(f"\n  ⚠ cid={cid} segment={segment_index} 弹幕拉取失败: {e}")
                return []
            time.sleep(1 * attempt)
    return []


def _parse_danmaku_reply(content: bytes) -> list[dict]:
    """解析 DmSegMobileReply protobuf 内容，返回弹幕列表。"""
    elems: list[dict] = []
    pos = 0
    size = len(content)

    while pos < size:
        try:
            key, pos = _read_varint(content, pos)
        except ValueError:
            break

        field_num = key >> 3
        wire_type = key & 0x07

        if field_num == 1 and wire_type == 2:
            try:
                length, pos = _read_varint(content, pos)
            except ValueError:
                break
            end = pos + length
            if end > size:
                break
            elem = _parse_danmaku_elem(content[pos:end])
            pos = end
            if elem:
                elems.append(elem)
            continue

        pos = _skip_field(content, pos, wire_type)

    return elems


def _parse_danmaku_elem(content: bytes) -> dict:
    """解析 DanmakuElem protobuf 内容。"""
    record: dict = {}
    pos = 0
    size = len(content)

    while pos < size:
        try:
            key, pos = _read_varint(content, pos)
        except ValueError:
            break

        field_num = key >> 3
        wire_type = key & 0x07

        if wire_type == 0:
            try:
                value, pos = _read_varint(content, pos)
            except ValueError:
                break
        elif wire_type == 2:
            try:
                raw, pos = _read_length_delimited(content, pos)
            except ValueError:
                break
            value = raw.decode("utf-8", errors="replace")
        elif wire_type == 5:
            if pos + 4 > size:
                break
            value = struct.unpack_from("<I", content, pos)[0]
            pos += 4
        elif wire_type == 1:
            if pos + 8 > size:
                break
            value = struct.unpack_from("<Q", content, pos)[0]
            pos += 8
        else:
            pos = _skip_field(content, pos, wire_type)
            continue

        if field_num == 1:
            record["id"] = value
        elif field_num == 2:
            record["progress"] = round(int(value) / 1000.0, 2)
            record["progress_ms"] = int(value)
        elif field_num == 3:
            record["mode"] = int(value)
        elif field_num == 4:
            record["fontsize"] = int(value)
        elif field_num == 5:
            record["color"] = _dec_to_hex_color(int(value))
            record["color_dec"] = int(value)
        elif field_num == 6:
            record["mid_hash"] = value
        elif field_num == 7:
            record["content"] = value
        elif field_num == 8:
            record["send_time"] = int(value)
            record["ctime"] = int(value)
        elif field_num == 9:
            record["weight"] = int(value)
        elif field_num == 10:
            record["action"] = value
        elif field_num == 11:
            record["pool"] = int(value)
        elif field_num == 12:
            record["idStr"] = value
        elif field_num == 13:
            record["attr"] = int(value)
        elif field_num == 22:
            record["animation"] = value
        elif field_num == 24:
            record["colorful"] = int(value)

    if "content" not in record:
        return {}

    record.setdefault("id", 0)
    record.setdefault("progress", 0.0)
    record.setdefault("progress_ms", int(round(record["progress"] * 1000)))
    record.setdefault("mode", 0)
    record.setdefault("fontsize", 0)
    record.setdefault("color", "#000000")
    record.setdefault("mid_hash", "")
    record.setdefault("send_time", 0)
    record.setdefault("ctime", 0)
    record.setdefault("weight", 0)
    record.setdefault("action", "")
    record.setdefault("pool", 0)
    record.setdefault("idStr", str(record["id"]) if record.get("id") else "")
    record.setdefault("attr", 0)
    record.setdefault("animation", "")
    if "color_dec" not in record and record.get("color"):
        try:
            record["color_dec"] = int(str(record["color"]).lstrip("#"), 16)
        except ValueError:
            record["color_dec"] = 0

    # 保持与旧 XML 输出尽量一致，同时保留新接口的原始字段。
    return {
        "dmid": record.get("idStr") or str(record.get("id", "")),
        "progress": record.get("progress", 0.0),
        "progress_ms": record.get("progress_ms", 0),
        "mode": record.get("mode", 0),
        "fontsize": record.get("fontsize", 0),
        "color": record.get("color", "#000000"),
        "color_dec": record.get("color_dec", 0),
        "send_time": record.get("send_time", 0),
        "ctime": record.get("ctime", 0),
        "pool": record.get("pool", 0),
        "mid_hash": record.get("mid_hash", ""),
        "content": record.get("content", ""),
        "id": record.get("id", 0),
        "idStr": record.get("idStr", ""),
        "weight": record.get("weight", 0),
        "action": record.get("action", ""),
        "attr": record.get("attr", 0),
        "animation": record.get("animation", ""),
        "colorful": record.get("colorful", 0),
    }


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """读取 protobuf varint。"""
    result = 0
    shift = 0

    while True:
        if pos >= len(buf):
            raise ValueError("unexpected eof while reading varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift >= 64:
            raise ValueError("varint too long")


def _read_length_delimited(buf: bytes, pos: int) -> tuple[bytes, int]:
    """读取 protobuf length-delimited 字段。"""
    length, pos = _read_varint(buf, pos)
    end = pos + length
    if end > len(buf):
        raise ValueError("unexpected eof while reading length-delimited field")
    return buf[pos:end], end


def _skip_field(buf: bytes, pos: int, wire_type: int) -> int:
    """跳过 protobuf 中不关心的字段。"""
    if wire_type == 0:
        _, pos = _read_varint(buf, pos)
        return pos
    if wire_type == 1:
        return min(len(buf), pos + 8)
    if wire_type == 2:
        raw, pos = _read_length_delimited(buf, pos)
        return pos
    if wire_type == 5:
        return min(len(buf), pos + 4)
    raise ValueError(f"unsupported wire type: {wire_type}")


def _dec_to_hex_color(dec: int) -> str:
    """十进制 RGB888 转 #RRGGBB 格式。"""
    return f"#{dec:06X}"
