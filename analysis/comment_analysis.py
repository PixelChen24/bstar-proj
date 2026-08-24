"""评论分析：主题聚类 + 高价值反馈筛选 + 情感/立场分析"""

import json
import math
import re
from collections import defaultdict

import jieba
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from .llm import chat


# ─── 基础分析 ───────────────────────────────────────────────


def analyze_comments(comments: list[dict], total_comments: int, on_progress=None) -> list[dict]:
    """
    分析评论数据，返回 cmThemes 列表。

    参数:
        comments: 清洗后的评论列表
        total_comments: 评论区总评论数（用于计算占比）
    """
    print(f"\n🔍 正在分析评论 ({len(comments)} 条)...")

    if len(comments) < 5:
        print("  ⚠ 评论数量不足，跳过分析")
        return []

    if on_progress:
        on_progress(3, "评论聚类中...", "", 0.18)
    clusters = cluster_comments(comments)
    theme_specs = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        sorted_members = sorted(members, key=value_score, reverse=True)
        top_quotes = sorted_members[:5]
        theme_specs.append({
            "members": members,
            "quotes": top_quotes,
            "samples": [q["content"][:80] for q in top_quotes[:4]],
        })

    if not theme_specs:
        return []

    theme_specs.sort(key=lambda item: len(item["members"]), reverse=True)
    if on_progress:
        on_progress(3, f"批量分析 {len(theme_specs)} 个评论主题...", "", 0.68)
    analyses = _batch_analyze_comment_themes(theme_specs)

    cm_themes = []
    for spec, analysis in zip(theme_specs, analyses):
        theme = _build_theme_from_analysis(spec, analysis, total_comments)
        if theme:
            cm_themes.append(theme)

    cm_themes.sort(key=lambda t: t["c"], reverse=True)
    cm_themes = cm_themes[:5]

    if cm_themes:
        max_count = cm_themes[0]["c"]
        for t in cm_themes:
            t["pct"] = round(t["c"] / max(max_count, 1) * 100)

    for t in cm_themes:
        dis_str = f" [争议度:{t['dis']}]" if t.get("dis") else ""
        print(f"    📌 {t['n']}: {t['c']} 条{dis_str}")

    if on_progress:
        on_progress(3, f"评论分析完成：{len(cm_themes)} 个主题", "", 1.0)

    return cm_themes


# ─── 聚类 ───────────────────────────────────────────────────

_STOP_WORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "啦", "呀", "嘛",
    "什么", "怎么", "可以", "还是", "这个", "那个", "但是", "因为",
    "所以", "如果", "已经", "这样", "那样", "回复",
}


def _tokenize_comment(text: str) -> str:
    """jieba 分词。"""
    words = jieba.lcut(text)
    words = [w for w in words if len(w) > 1 and w not in _STOP_WORDS]
    return " ".join(words)


def cluster_comments(comments: list[dict]) -> dict[int, list[dict]]:
    """TF-IDF + KMeans 聚类评论。"""
    texts = [_tokenize_comment(c["content"]) for c in comments]
    valid = [(i, t) for i, t in enumerate(texts) if t.strip()]

    if len(valid) < 5:
        return {0: comments}

    indices, tokenized = zip(*valid)

    vectorizer = TfidfVectorizer(max_features=500, min_df=2, max_df=0.8)
    try:
        tfidf_matrix = vectorizer.fit_transform(tokenized)
    except ValueError:
        return {0: comments}

    k = min(6, max(2, len(valid) // 15))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=100)
    labels = kmeans.fit_predict(tfidf_matrix)

    clusters = defaultdict(list)
    for idx, label in zip(indices, labels):
        clusters[label].append(comments[idx])

    return dict(clusters)


# ─── 高价值反馈筛选 ─────────────────────────────────────────

W_LIKE = 2.0
W_RCOUNT = 1.5
W_LEVEL = 0.5
W_UP_LIKE = 2.0
W_UP_REPLY = 3.0


def _reply_count(c: dict) -> int:
    """回复数。子评论没有 rcount 字段，退回已抓到的 replies 长度。"""
    return c.get("rcount", len(c.get("replies", [])))


def value_score(c: dict) -> float:
    """评论的高价值得分。"""
    return (
        W_LIKE * math.log1p(max(c.get("like", 0), 0))
        + W_RCOUNT * math.log1p(max(_reply_count(c), 0))
        + W_LEVEL * min(max(c.get("level", 0), 0), 6)
        + (W_UP_LIKE if c.get("up_like") else 0)
        + (W_UP_REPLY if c.get("up_reply") else 0)
    )


def value_reasons(c: dict) -> list[str]:
    """入选理由标签，供前端展示。"""
    reasons = []
    if c.get("up_reply"):
        reasons.append("UP主回复")
    if c.get("up_like"):
        reasons.append("UP主点赞")

    like = c.get("like", 0)
    if like >= 10000:
        reasons.append(f"{like / 10000:.1f}w赞")
    elif like >= 1000:
        reasons.append(f"{like / 1000:.1f}k赞")
    elif like > 0:
        reasons.append(f"{like}赞")

    rcount = _reply_count(c)
    if rcount >= 5:
        reasons.append(f"{rcount}条回复")

    level = c.get("level", 0)
    if level >= 5:
        reasons.append(f"L{level}")

    return reasons


# ─── LLM 解析与兜底 ─────────────────────────────────────────


def _strip_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text.strip()


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_payload(text: str):
    cleaned = _strip_code_fences(text)
    candidates = [cleaned]
    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")
    if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
        candidates.append(cleaned[obj_start:obj_end + 1])
    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")
    if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
        candidates.append(cleaned[arr_start:arr_end + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _normalize_stance(value) -> str:
    s = str(value).strip().lower()
    if not s:
        return "pro"
    if s in {"con", "反对", "反", "negative", "oppose", "no", "disagree"}:
        return "con"
    return "pro"


def _heuristic_stance(text: str, theme_name: str = "") -> str:
    t = f"{theme_name} {text}"
    negative_tokens = ("不", "别", "差", "烂", "失望", "无聊", "太慢", "看不懂", "反对", "质疑", "离谱")
    positive_tokens = ("喜欢", "支持", "好", "精彩", "感谢", "期待", "推荐", "有用", "学到了", "不错", "舒服")
    neg_score = sum(1 for kw in negative_tokens if kw in t)
    pos_score = sum(1 for kw in positive_tokens if kw in t)
    return "con" if neg_score > pos_score else "pro"


def _fallback_theme_name(samples: list[str]) -> str:
    if not samples:
        return "评论主题"
    base = samples[0].strip()
    if not base:
        return "评论主题"
    return base[:12] + ("..." if len(base) > 12 else "")


def _fallback_note(theme_name: str, pro_count: int, con_count: int, total: int) -> str:
    if con_count > pro_count:
        return f"建议补充回应「{theme_name}」的质疑点。"
    if total >= 8:
        return f"「{theme_name}」讨论热度高，可继续延展。"
    return f"「{theme_name}」值得继续观察。"


# ─── 一次性批量分析 ─────────────────────────────────────────


def _batch_analyze_comment_themes(theme_specs: list[dict]) -> list[dict]:
    """一次 LLM 调用完成所有评论簇的主题名、立场和注释。"""
    if not theme_specs:
        return []

    items = []
    for i, spec in enumerate(theme_specs, start=1):
        sample_text = "\n".join(f"{j + 1}. {s}" for j, s in enumerate(spec["samples"]))
        items.append(
            f"[{i}] 评论数={len(spec['members'])}\n{sample_text}"
        )

    prompt = (
        "下面是多个B站评论簇的代表评论。\n"
        "请一次性完成全部分析，并严格输出 JSON，不要输出额外解释。\n\n"
        "输出格式：\n"
        "{\n"
        "  \"themes\": [\n"
        "    {\"theme_name\":\"10字以内主题名\",\"stances\":[\"pro\",\"con\"],\"note\":\"20字以内分析提示\"}\n"
        "  ]\n"
        "}\n\n"
        "规则：\n"
        "1. themes 的顺序必须与输入顺序一致。\n"
        "2. stances 的长度必须等于该评论簇展示的评论条数。\n"
        "3. 立场只允许使用 pro 或 con；支持/赞同/提建议用 pro，反对/质疑/不认同用 con。\n"
        "4. note 给 UP 主一句简短分析提示。\n\n"
        f"输入：\n{chr(10).join(items)}\n"
    )
    raw = chat(prompt, max_new_tokens=700).strip()
    payload = _load_json_payload(raw)
    if not isinstance(payload, dict):
        payload = {}

    raw_themes = payload.get("themes") if isinstance(payload.get("themes"), list) else []
    analyses = []
    for idx, spec in enumerate(theme_specs):
        item = raw_themes[idx] if idx < len(raw_themes) and isinstance(raw_themes[idx], dict) else {}
        analyses.append(_normalize_theme_analysis(spec, item))
    return analyses


def _normalize_theme_analysis(spec: dict, item: dict) -> dict:
    samples = spec["samples"]
    quotes = spec["quotes"]

    theme_name = _strip_markdown(str(item.get("theme_name", "")).strip())
    if not theme_name or len(theme_name) > 25:
        theme_name = _fallback_theme_name(samples)

    raw_stances = item.get("stances") if isinstance(item.get("stances"), list) else []
    stances = []
    for i, q in enumerate(quotes[:4]):
        if i < len(raw_stances):
            stances.append(_normalize_stance(raw_stances[i]))
        else:
            stances.append(_heuristic_stance(q["content"], theme_name))

    pro_count = sum(1 for s in stances if s == "pro")
    con_count = sum(1 for s in stances if s == "con")
    total_judged = pro_count + con_count
    dis = None
    if total_judged > 0:
        con_ratio = con_count / total_judged
        if con_ratio < 0.15:
            dis = "低"
        elif con_ratio < 0.35:
            dis = "中"
        else:
            dis = "高"

    note = _strip_markdown(str(item.get("note", "")).strip())
    if not note:
        note = _fallback_note(theme_name, pro_count, con_count, len(spec["members"]))

    quotes_with_stance = []
    for q, stance in zip(quotes[:4], stances):
        quotes_with_stance.append({
            "t": q["content"][:100],
            "l": q.get("like", 0),
            "r": _reply_count(q),
            "k": stance,
            "why": value_reasons(q),
        })

    return {
        "n": theme_name,
        "c": len(spec["members"]),
        "q": quotes_with_stance[:3],
        "dis": dis,
        "note": note,
    }


def _build_theme_from_analysis(spec: dict, analysis: dict, total_comments: int) -> dict:
    pct = round(len(spec["members"]) / max(total_comments, 1) * 100) if total_comments > 0 else 0
    theme = {
        "n": analysis["n"],
        "c": analysis["c"],
        "pct": pct,
        "q": analysis["q"],
    }
    if analysis.get("dis"):
        theme["dis"] = analysis["dis"]
    if analysis.get("note"):
        theme["note"] = analysis["note"]
    return theme


# ─── 兼容旧调用：不再在主流程使用 ───────────────────────────


def build_comment_theme(members: list[dict], total_comments: int) -> dict | None:
    """兼容旧接口：单簇分析。主流程现在用 _batch_analyze_comment_themes。"""
    sorted_members = sorted(members, key=value_score, reverse=True)
    top_quotes = sorted_members[:5]
    spec = {
        "members": members,
        "quotes": top_quotes,
        "samples": [q["content"][:80] for q in top_quotes[:4]],
    }
    analysis = _batch_analyze_comment_themes([spec])[0]
    return _build_theme_from_analysis(spec, analysis, total_comments)


def classify_stance(text: str, theme_name: str) -> str:
    """兼容旧接口：优先使用轻量启发式，避免额外 LLM 请求。"""
    return _heuristic_stance(text, theme_name)


def generate_editorial_note(theme_name: str, pro: int, con: int, total: int) -> str:
    """兼容旧接口：用本地兜底生成，避免额外 LLM 请求。"""
    return _fallback_note(theme_name, pro, con, total)
