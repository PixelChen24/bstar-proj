"""B站评论采集"""

import time

import requests

from .video import HEADERS, VERIFY_SSL

API_REPLY = "http://api.bilibili.com/x/v2/reply"
API_REPLY_REPLY = "http://api.bilibili.com/x/v2/reply/reply"


def fetch_comments(
    aid: int,
    max_comments: int = 500,
    delay: float = 0.3,
) -> dict:
    """
    获取视频评论（含子评论）。

    参数:
        aid: 视频 avid
        max_comments: 最多采集的根评论条数
        delay: 请求间隔秒数

    返回:
        {
            "aid": int,
            "total_count": int,       # 根评论总数（B站返回）
            "fetched_root": int,      # 实际采集的根评论数
            "fetched_replies": int,   # 实际采集的子评论数
            "comments": [...]
        }
    """
    print(f"\n📝 正在采集评论 (aid={aid}, 上限 {max_comments} 条根评论)...")

    all_comments = []
    total_count = 0
    fetched_replies = 0
    page_num = 1
    page_size = 20

    while len(all_comments) < max_comments:
        print(f"  ⏳ 第 {page_num} 页...", end="", flush=True)

        data = _fetch_reply_page(aid, sort=1, pn=page_num, ps=page_size)
        if data is None:
            print(" 请求失败，停止")
            break

        # 第一页获取总数
        if page_num == 1:
            page_info = data.get("page", {})
            total_count = page_info.get("count", 0)
            print(f" (评论区共 {total_count} 条根评论)", end="")

        replies = data.get("replies")
        if not replies:
            print(" 无更多评论")
            break

        page_comments = []
        for r in replies:
            comment = _extract_comment(r)
            page_comments.append(comment)

        all_comments.extend(page_comments)
        print(f" +{len(page_comments)} 条 (累计 {len(all_comments)})")

        page_num += 1
        time.sleep(delay)

    # 如果超出上限，截断
    if len(all_comments) > max_comments:
        all_comments = all_comments[:max_comments]

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
        "comments": all_comments,
    }
    print(f"  ✔ 评论采集完成: {result['fetched_root']} 条根评论, "
          f"{result['fetched_replies']} 条子评论")
    return result


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
