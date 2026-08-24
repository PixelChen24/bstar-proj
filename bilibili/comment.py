"""B站评论采集"""

import time

import requests

from .video import HEADERS, VERIFY_SSL

API_REPLY = "http://api.bilibili.com/x/v2/reply"
API_REPLY_REPLY = "http://api.bilibili.com/x/v2/reply/reply"


SORT_TIME = 0  # 按时间倒序
SORT_HOT = 1   # 按热度


def fetch_comments(
    aid: int,
    max_comments: int = 500,
    delay: float = 0.3,
    sort: int = SORT_HOT,
) -> dict:
    """
    获取视频评论（含子评论）。

    参数:
        aid: 视频 avid
        max_comments: 最多采集的根评论条数
        delay: 请求间隔秒数
        sort: 排序方式，0=按时间 1=按热度

    未登录时按热度排序往往只返回少量根评论（几条），此时会自动改用按时间
    排序重采一次——分析层需要足够样本量，而排序方式本身不影响后续聚类。

    返回:
        {
            "aid": int,
            "total_count": int,       # 根评论总数（B站返回）
            "fetched_root": int,      # 实际采集的根评论数
            "fetched_replies": int,   # 实际采集的子评论数
            "sort": int,              # 实际生效的排序方式
            "comments": [...]
        }
    """
    all_comments, total_count = _fetch_root_comments(aid, max_comments, delay, sort)

    # 未登录时接口只回降级响应：实测三个视频（评论区 8.9w / 2.3w / 1.9w）
    # 按热度一律只返回 3 条根评论，按时间（sort=0）返回 0 条。换排序绕不过去，
    # 必须带登录态，所以这里只做提示，不再自动重试。
    if total_count > len(all_comments) * 3 and len(all_comments) < 50:
        print(f"  ⚠ 仅取到 {len(all_comments)} 条根评论，但评论区共 {total_count} 条。"
              f"这是未登录限制，设置环境变量 BILIBILI_SESSDATA 可拿到完整评论"
              f"（子评论不受影响，仍可正常拉取）")

    fetched_replies = 0

    # 拉取子评论
    print(f"  📎 正在拉取子评论...")
    for i, comment in enumerate(all_comments):
        rcount = comment.get("rcount", 0)
        preview_count = len(comment.get("replies", []))
        # 只有当子评论数大于预览数时才拉取完整子评论
        if rcount > preview_count and rcount > 0:
            print(f"    ⏳ [{i+1}/{len(all_comments)}] rpid={comment['rpid']} "
                  f"({rcount} 条回复)...", end="", flush=True)
            full_replies = _fetch_all_sub_replies(
                aid, comment["rpid"], rcount, delay
            )
            if full_replies is not None:
                comment["replies"] = full_replies
                fetched_replies += len(full_replies)
                print(f" ✔ {len(full_replies)} 条")
            else:
                fetched_replies += preview_count
                print(f" 使用预览 {preview_count} 条")
            time.sleep(delay)
        else:
            fetched_replies += preview_count

    result = {
        "aid": aid,
        "total_count": total_count,
        "fetched_root": len(all_comments),
        "fetched_replies": fetched_replies,
        "sort": sort,
        "comments": all_comments,
    }
    print(f"  ✔ 评论采集完成: {result['fetched_root']} 条根评论, "
          f"{result['fetched_replies']} 条子评论")
    return result


def _fetch_root_comments(
    aid: int, max_comments: int, delay: float, sort: int
) -> tuple[list[dict], int]:
    """按指定排序翻页拉取根评论。返回 (评论列表, 评论区根评论总数)。"""
    label = "热度" if sort == SORT_HOT else "时间"
    print(f"\n📝 正在采集评论 (aid={aid}, 按{label}排序, 上限 {max_comments} 条根评论)...")

    all_comments = []
    total_count = 0
    page_num = 1
    page_size = 20

    while len(all_comments) < max_comments:
        print(f"  ⏳ 第 {page_num} 页...", end="", flush=True)

        data = _fetch_reply_page(aid, sort=sort, pn=page_num, ps=page_size)
        if data is None:
            print(" 请求失败，停止")
            break

        # 第一页获取总数
        if page_num == 1:
            total_count = data.get("page", {}).get("count", 0)
            print(f" (评论区共 {total_count} 条根评论)", end="")

        replies = data.get("replies")
        if not replies:
            print(" 无更多评论")
            break

        all_comments.extend(_extract_comment(r) for r in replies)
        print(f" +{len(replies)} 条 (累计 {len(all_comments)})")

        page_num += 1
        time.sleep(delay)

    return all_comments[:max_comments], total_count


def _fetch_reply_page(
    aid: int, sort: int = 1, pn: int = 1, ps: int = 20, max_retries: int = 3
) -> dict | None:
    """拉取一页根评论。"""
    params = {
        "type": 1,
        "oid": aid,
        "sort": sort,
        "ps": ps,
        "pn": pn,
        "nohot": 1,
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                API_REPLY, params=params, headers=HEADERS, timeout=10,
                verify=VERIFY_SSL,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                msg = body.get("message", "")
                if body.get("code") == 12002:
                    # 评论区已关闭
                    print(f" ⚠ 评论区已关闭")
                    return None
                raise RuntimeError(f"API 错误 code={body['code']}: {msg}")
            return body.get("data", {})
        except Exception as e:
            if attempt == max_retries:
                print(f" ⚠ 请求失败: {e}")
                return None
            time.sleep(1 * attempt)
    return None


def _fetch_all_sub_replies(
    aid: int, root_rpid: int, total: int, delay: float = 0.3
) -> list[dict] | None:
    """拉取某条根评论的全部子评论。"""
    all_replies = []
    page_num = 1
    page_size = 20

    while len(all_replies) < total:
        data = _fetch_sub_reply_page(aid, root_rpid, pn=page_num, ps=page_size)
        if data is None:
            break

        replies = data.get("replies")
        if not replies:
            break

        for r in replies:
            all_replies.append(_extract_comment(r, is_reply=True))

        page_num += 1
        if len(replies) < page_size:
            break
        time.sleep(delay)

    return all_replies if all_replies else None


def _fetch_sub_reply_page(
    aid: int, root_rpid: int, pn: int = 1, ps: int = 20, max_retries: int = 3
) -> dict | None:
    """拉取一页子评论。"""
    params = {
        "type": 1,
        "oid": aid,
        "root": root_rpid,
        "ps": ps,
        "pn": pn,
    }
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                API_REPLY_REPLY, params=params, headers=HEADERS, timeout=10,
                verify=VERIFY_SSL,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 0:
                raise RuntimeError(f"API 错误 code={body['code']}")
            return body.get("data", {})
        except Exception as e:
            if attempt == max_retries:
                return None
            time.sleep(1 * attempt)
    return None


def _extract_comment(raw: dict, is_reply: bool = False) -> dict:
    """从 API 返回的评论条目中提取关键字段。"""
    member = raw.get("member", {})
    content = raw.get("content", {})

    comment = {
        "rpid": raw.get("rpid"),
        "mid": raw.get("mid"),
        "uname": member.get("uname", ""),
        "level": member.get("level_info", {}).get("current_level", 0),
        "content": content.get("message", ""),
        "like": raw.get("like", 0),
        "ctime": raw.get("ctime", 0),
    }

    if not is_reply:
        # 根评论额外信息
        comment["rcount"] = raw.get("rcount", 0)
        comment["up_like"] = raw.get("up_action", {}).get("like", False)
        comment["up_reply"] = raw.get("up_action", {}).get("reply", False)

        # 子评论预览（API 内嵌的前 3 条）
        preview_replies = raw.get("replies") or []
        comment["replies"] = [
            _extract_comment(r, is_reply=True) for r in preview_replies
        ]
    else:
        comment["parent"] = raw.get("parent", 0)

    return comment
