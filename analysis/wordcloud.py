"""词云数据生成：从弹幕/评论文本中提取高频关键词。"""

from __future__ import annotations

import re
from collections import Counter

import jieba


_STOP_WORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这",
    "他", "她", "它", "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "啦", "呀", "嘛",
    "一个", "这个", "那个", "什么", "怎么", "可以", "还是", "但是", "因为", "所以",
    "如果", "已经", "这样", "那样", "就是", "不是", "真的", "感觉", "视频", "弹幕",
    "评论", "回复", "大家", "现在", "时候", "一下", "这么", "那么", "这里", "那里",
    "哈哈", "哈哈哈", "哈哈哈哈", "233", "2333", "23333", "www", "wwww", "wwwww",
    "up", "UP", "up主", "UP主", "b站", "B站", "bilibili", "BV",
}

_RE_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_RE_TAG = re.compile(r"\[[^\]]+\]")
_RE_NOISE = re.compile(r"^[\W_\d]+$", re.U)
_RE_BVID = re.compile(r"^BV[a-zA-Z0-9]+$")


def _normalize_text(text: str) -> str:
    text = _RE_URL.sub(" ", text or "")
    text = _RE_TAG.sub(" ", text)
    text = text.replace("【", " ").replace("】", " ")
    return text


def _valid_token(token: str) -> bool:
    token = token.strip()
    if len(token) < 2 or len(token) > 12:
        return False
    if token in _STOP_WORDS:
        return False
    if token.lower() in {w.lower() for w in _STOP_WORDS}:
        return False
    if _RE_NOISE.match(token):
        return False
    if _RE_BVID.match(token):
        return False
    # 过滤纯数字、纯拉丁短词、长串重复字符
    if token.isdigit():
        return False
    if re.fullmatch(r"[a-zA-Z]{1,2}", token):
        return False
    if re.fullmatch(r"(.)\1{2,}", token):
        return False
    return True


def _iter_tokens(texts: list[str]):
    for text in texts:
        for token in jieba.lcut(_normalize_text(text)):
            token = token.strip()
            if _valid_token(token):
                yield token


def generate_word_cloud(texts: list[str], limit: int = 56) -> list[dict]:
    """返回词云数据：[{t: 词, c: 次数, w: 0~1权重}]。"""
    counter = Counter(_iter_tokens(texts))
    if not counter:
        return []

    items = counter.most_common(limit)
    max_count = max(c for _, c in items) or 1
    min_count = min(c for _, c in items) or 0
    span = max(max_count - min_count, 1)

    words = []
    for token, count in items:
        # sqrt 压缩长尾，让小词也可见。
        raw = (count - min_count) / span
        weight = 0.24 + 0.76 * (raw ** 0.5)
        words.append({"t": token, "c": count, "w": round(weight, 3)})
    return words


def generate_word_clouds_from_records(
    danmakus: list[dict], comments: list[dict], limit: int = 56
) -> dict:
    """从弹幕/评论记录生成前端使用的词云数据。"""
    dm_texts = [str(d.get("content", "")) for d in danmakus]
    cm_texts = [str(c.get("content", "")) for c in comments]
    return {
        "danmaku": generate_word_cloud(dm_texts, limit=limit),
        "comment": generate_word_cloud(cm_texts, limit=limit),
    }
