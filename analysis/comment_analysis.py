"""评论分析：主题聚类 + 情感/立场分析"""

from collections import defaultdict
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from .llm import chat


def analyze_comments(comments: list[dict], total_comments: int) -> list[dict]:
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

    # 1. 主题聚类
    clusters = cluster_comments(comments)

    # 2. 为每个簇构建主题
    cm_themes = []
    for label, members in clusters.items():
        if len(members) < 2:
            continue

        theme = build_comment_theme(members, total_comments)
        if theme:
            cm_themes.append(theme)

    # 按数量排序
    cm_themes.sort(key=lambda t: t["c"], reverse=True)
    cm_themes = cm_themes[:5]  # 最多 5 个主题

    # 重新计算 pct：相对最大簇的百分比，最大簇=100
    if cm_themes:
        max_count = cm_themes[0]["c"]
        for t in cm_themes:
            t["pct"] = round(t["c"] / max(max_count, 1) * 100)

    for t in cm_themes:
        dis_str = f" [争议度:{t['dis']}]" if t.get("dis") else ""
        print(f"    📌 {t['n']}: {t['c']} 条{dis_str}")

    return cm_themes


# ─── 聚类 ───────────────────────────────────────────────────

# 停用词
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


# ─── 构建主题 ───────────────────────────────────────────────

def build_comment_theme(members: list[dict], total_comments: int) -> dict | None:
    """为一个评论簇构建完整的主题对象。"""

    # 按点赞排序，选代表性评论
    sorted_members = sorted(members, key=lambda c: c.get("like", 0), reverse=True)
    top_quotes = sorted_members[:5]  # 取前 5 条高赞

    # LLM 生成主题名
    quote_texts = [q["content"][:80] for q in top_quotes[:3]]
    sample_text = "\n".join(f"- {t}" for t in quote_texts)
    prompt = (
        f"以下是B站视频评论区中同一类评论的代表内容，请用一个简短的主题名概括（10字以内）：\n"
        f"{sample_text}\n"
        f"主题名："
    )
    theme_name = chat(prompt, max_new_tokens=30)
    theme_name = theme_name.strip().strip('"').strip("'").strip("「」")
    if not theme_name or len(theme_name) > 25:
        theme_name = quote_texts[0][:12] + "..."

    # LLM 情感/立场分析（对 top 引用逐条判断）
    quotes_with_stance = []
    for q in top_quotes[:4]:
        stance = classify_stance(q["content"], theme_name)
        quotes_with_stance.append({
            "t": q["content"][:100],
            "l": q.get("like", 0),
            "r": q.get("rcount", len(q.get("replies", []))),
            "k": stance,
        })

    # 计算争议度
    pro_count = sum(1 for q in quotes_with_stance if q["k"] == "pro")
    con_count = sum(1 for q in quotes_with_stance if q["k"] == "con")
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

    # 占比
    pct = round(len(members) / max(total_comments, 1) * 100) if total_comments > 0 else 0

    # 编辑注释（争议度中/高时生成）
    note = ""
    if dis and dis in ("中", "高"):
        note = generate_editorial_note(theme_name, pro_count, con_count, len(members))
    elif len(members) >= 5:
        # 普通注释
        note_prompt = (
            f"评论主题「{theme_name}」共 {len(members)} 条评论，"
            f"给UP主一句简短的分析提示（15字以内）："
        )
        note = chat(note_prompt, max_new_tokens=40).strip()

    theme = {
        "n": theme_name,
        "c": len(members),
        "pct": pct,
        "q": quotes_with_stance[:3],  # 最多展示 3 条引用
    }
    if dis:
        theme["dis"] = dis
    if note:
        theme["note"] = note

    return theme


# ─── 情感分析 ───────────────────────────────────────────────

def classify_stance(text: str, theme_name: str) -> str:
    """用 LLM 判断评论对某主题的立场。"""
    prompt = (
        f"判断以下B站评论对主题[{theme_name}]的态度。\n"
        f"评论：{text[:100]}\n"
        "如果是支持、赞同、提建议，回答'支持'。如果是反对、质疑、不认同，回答'反对'。\n"
        "回答（支持/反对）："
    )
    resp = chat(prompt, max_new_tokens=10)
    if "反对" in resp or "反" in resp:
        return "con"
    return "pro"


def generate_editorial_note(theme_name: str, pro: int, con: int, total: int) -> str:
    """生成编辑注释。"""
    prompt = (
        f"评论主题「{theme_name}」共 {total} 条评论，"
        f"其中 {pro} 条支持、{con} 条反对。"
        f"给UP主一句简短的行动建议（20字以内）："
    )
    note = chat(prompt, max_new_tokens=50)
    return note.strip()
