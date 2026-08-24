"""每日请求限流：通过 ARP 将客户端 IP 反查为 MAC 地址作为设备标识。

环境变量：
  BSTAR_DAILY_LIMIT   每设备每日最多分析次数（0 或不设 = 不限制）
  BSTAR_RATE_STORE    计数文件路径（默认 ./config/rate_counts.json）

MAC 查询依赖 ARP 表（arp -n / ip neigh），仅对同一局域网段有效；
跨路由器访问时退回到客户端 IP 地址作为标识。
"""

import json
import os
import re
import subprocess
import threading
from datetime import date

DAILY_LIMIT = int(os.environ.get("BSTAR_DAILY_LIMIT", "0"))
_STORE_PATH = os.environ.get("BSTAR_RATE_STORE", "./config/rate_counts.json")

_lock = threading.Lock()
_mem: dict = {"date": "", "counts": {}}  # 内存镜像，启动时从磁盘加载


def _load_once():
    global _mem
    try:
        if os.path.exists(_STORE_PATH):
            with open(_STORE_PATH, "r", encoding="utf-8") as f:
                _mem = json.load(f)
    except Exception:
        _mem = {"date": "", "counts": {}}


def _save():
    try:
        parent = os.path.dirname(_STORE_PATH)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(_mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠ 限流计数写入失败: {e}")


def _get_mac(ip: str) -> str:
    """从 ARP 表获取 MAC 地址，失败则返回 IP。"""
    if ip in ("127.0.0.1", "::1"):
        return "localhost"
    try:
        r = subprocess.run(["arp", "-n", ip], capture_output=True, text=True, timeout=2)
        m = re.search(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", r.stdout, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    except FileNotFoundError:
        pass
    except Exception:
        pass
    try:
        r = subprocess.run(["ip", "neigh", "show", ip], capture_output=True, text=True, timeout=2)
        m = re.search(r"lladdr\s+([0-9a-f]{2}(?::[0-9a-f]{2}){5})", r.stdout, re.IGNORECASE)
        if m:
            return m.group(1).lower()
    except Exception:
        pass
    return ip


def check(ip: str) -> tuple[bool, str, int]:
    """检查限流。

    返回 (allowed, device_id, remaining)：
      allowed    — 是否允许本次请求
      device_id  — MAC 地址或 IP（用于日志）
      remaining  — 今日剩余次数（-1 表示无限制）
    """
    if DAILY_LIMIT <= 0:
        return True, ip, -1

    device = _get_mac(ip)
    today = date.today().isoformat()

    with _lock:
        if _mem.get("date") != today:
            _mem["date"] = today
            _mem["counts"] = {}

        used = _mem["counts"].get(device, 0)
        if used >= DAILY_LIMIT:
            return False, device, 0

        _mem["counts"][device] = used + 1
        _save()
        return True, device, DAILY_LIMIT - used - 1


# 启动时加载磁盘数据
_load_once()
