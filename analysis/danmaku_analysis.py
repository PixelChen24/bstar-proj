"""弹幕分析：峰值检测 + 主题聚类"""

import json
import re
from collections import Counter, defaultdict

import jieba
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from .llm import chat


# ─── LLM 解析 ───────────────────────────────────────────────


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_payload(text: str):
    """从 LLM 回复中提取 JSON 对象或数组。"""
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


def _clean_name(name: str, fallback: str, limit: int = 20) -> str:
    name = str(name or "").strip().strip('"').strip("'").strip("「」").strip("《》")
    if not name or len(name) > limit:
        return fallback[:10] if fallback else "弹幕主题"
    return name


# ─── 主入口 ─────────────────────────────────────────────────


def analyze_danmaku(
    danmakus: list[dict], video_duration: int, on_progress=None
) -> tuple[list[dict], list[dict]]:
    """
    分析弹幕数据。

    返回 (dmThemes, peaks)
    """
    print(f"\n🔍 正在分析弹幕 ({len(danmakus)} 条)...")

    if on_progress:
        on_progress(2, "检测弹幕峰值...", "", 0.12)
    peaks = detect_peaks(danmakus, video_duration)
    if on_progress:
        on_progress(2, f"弹幕聚类中（{len(danmakus)} 条）...", "", 0.42)
    dm_themes = cluster_danmaku_themes(danmakus)
    if on_progress:
        on_progress(2, f"批量生成 {len(dm_themes)} 个弹幕主题和 {len(peaks)} 个高能时刻摘要...", "", 0.75)
    dm_themes, peaks = annotate_danmaku_findings(dm_themes, peaks, danmakus)
    if on_progress:
        on_progress(2, f"弹幕分析完成：{len(dm_themes)} 个主题 / {len(peaks)} 个峰值", "", 1.0)

    return dm_themes, peaks


# ─── 峰值检测 ───────────────────────────────────────────────


def detect_peaks(
    danmakus: list[dict], video_duration: int, bucket_sec: int = 10, threshold: float = 3.0
) -> list[dict]:
    """检测弹幕密度峰值。"""
    print("  📈 检测弹幕密度峰值...")

    if not danmakus or video_duration <= 0:
        return []

    num_buckets = max(1, video_duration // bucket_sec + 1)
    buckets = [0] * num_buckets
    for dm in danmakus:
        idx = min(int(dm["progress"] / bucket_sec), num_buckets - 1)
        buckets[idx] += 1

    avg = sum(buckets) / num_buckets if num_buckets > 0 else 0
    if avg == 0:
        return []

    hot_indices = [i for i, c in enumerate(buckets) if c > avg * threshold]
    if not hot_indices:
        hot_indices = [i for i, c in enumerate(buckets) if c > avg * 2]
    if not hot_indices:
        return []

    regions = []
    start = hot_indices[0]
    end = hot_indices[0]
    for idx in hot_indices[1:]:
        if idx <= end + 1:
            end = idx
        else:
            regions.append((start, end))
            start = idx
            end = idx
    regions.append((start, end))

    peaks = []
    for start, end in regions:
        t_start = start * bucket_sec
        t_end = (end + 1) * bucket_sec
        count = sum(buckets[start:end + 1])
        density = count / ((end - start + 1) * bucket_sec) if end >= start else 0
        avg_density = avg / bucket_sec
        multiplier = density / avg_density if avg_density > 0 else 0

        t_mid = (t_start + t_end) // 2
        tm = f"{t_mid // 60:02d}:{t_mid % 60:02d}"

        peaks.append({
            "tm": tm,
            "x": f"{multiplier:.1f}x",
            "n": count,
            "t_start": t_start,
            "t_end": t_end,
            "s": "",
        })

    peaks.sort(key=lambda p: float(p["x"].rstrip("x")), reverse=True)
    peaks = peaks[:3]

    for p in peaks:
        print(f"    ⚡ {p['tm']} 密度 {p['x']}，{p['n']} 条弹幕")

    return peaks


# ─── 主题聚类 ───────────────────────────────────────────────


def _tokenize(text: str) -> str:
    """jieba 分词，返回空格分隔的字符串。"""
    words = jieba.lcut(text)
    stop = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
        "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
        "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
        "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "啦", "呀", "嘛",
        "哈哈", "哈哈哈", "哈哈哈哈", "233", "2333", "23333",
    }
    words = [w for w in words if len(w) > 1 and w not in stop]
    return " ".join(words)


def cluster_danmaku_themes(danmakus: list[dict]) -> list[dict]:
    """使用 TF-IDF + KMeans 对弹幕进行主题聚类。"""
    print("  🏷️ 弹幕主题聚类中...")

    if len(danmakus) < 10:
        return []

    texts = [_tokenize(dm["content"]) for dm in danmakus]
    valid = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if len(valid) < 10:
        return []

    indices, tokenized = zip(*valid)
    vectorizer = TfidfVectorizer(max_features=500, min_df=2, max_df=0.8)
    try:
        tfidf_matrix = vectorizer.fit_transform(tokenized)
    except ValueError:
        return []

    k = min(8, max(3, len(valid) // 80))
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=100)
    labels = kmeans.fit_predict(tfidf_matrix)

    clusters = defaultdict(list)
    for idx, label in zip(indices, labels):
        clusters[label].append(danmakus[idx])

    themes = []
    for label in sorted(clusters.keys()):
        members = clusters[label]
        if len(members) < 3:
            continue

        content_counter = Counter(m["content"] for m in members)
        top_contents = [c for c, _ in content_counter.most_common(5)]
        time_range = _describe_time_range(members)

        themes.append({
            "n": "",
            "c": len(members),
            "t": time_range,
            "_samples": top_contents,
        })

    themes.sort(key=lambda t: t["c"], reverse=True)
    themes = themes[:6]

    for t in themes:
        print(f"    📌 {t['c']} 条 ({t['t']})")

    return themes


def _describe_time_range(danmakus: list[dict]) -> str:
    """生成弹幕时间段描述。"""
    if not danmakus:
        return "零散"

    progresses = [dm["progress"] for dm in danmakus]
    p_min = min(progresses)
    p_max = max(progresses)
    span = p_max - p_min

    total_range = p_max
    if total_range > 0 and span / total_range > 0.7:
        return "全片"

    progresses.sort()
    q1 = progresses[len(progresses) // 4]
    q3 = progresses[3 * len(progresses) // 4]

    if q3 - q1 < 30:
        mid = (q1 + q3) / 2
        return f"{int(mid)//60:02d}:{int(mid)%60:02d} 附近"

    return (
        f"{int(q1)//60:02d}:{int(q1)%60:02d}-"
        f"{int(q3)//60:02d}:{int(q3)%60:02d}"
    )


# ─── 批量补全 ───────────────────────────────────────────────


def annotate_danmaku_findings(
    themes: list[dict], peaks: list[dict], danmakus: list[dict]
) -> tuple[list[dict], list[dict]]:
    """一次 LLM 调用同时补全弹幕主题名和高能时刻叙事。"""
    if not themes and not peaks:
        return themes, peaks

    theme_lines = []
    for i, theme in enumerate(themes, start=1):
        samples = theme.get("_samples", [])
        sample_text = "\n".join(f"{j + 1}. {s}" for j, s in enumerate(samples[:4]))
        theme_lines.append(
            f"[主题{i}] 数量={theme['c']}，时段={theme['t']}\n{sample_text}"
        )

    peak_lines = []
    for i, peak in enumerate(peaks, start=1):
        t_start = peak.get("t_start", 0)
        t_end = peak.get("t_end", 0)
        region_dms = [
            dm["content"] for dm in danmakus
            if t_start <= dm["progress"] < t_end
        ]
        seen = set()
        unique_dms = []
        for text in region_dms:
            if text not in seen:
                seen.add(text)
                unique_dms.append(text)
            if len(unique_dms) >= 12:
                break
        sample_text = "\n".join(f"{j + 1}. {s}" for j, s in enumerate(unique_dms))
        peak_lines.append(f"[峰值{i}] 时间={peak['tm']}，弹幕数={peak['n']}\n{sample_text}")

    prompt = (
        "以下是B站视频的弹幕主题和高能时刻。\n"
        "请一次性完成全部分析，并严格输出 JSON，不要输出额外解释。\n\n"
        "输出格式：\n"
        "{\n"
        "  \"theme_names\": [\"主题名1\", \"主题名2\"],\n"
        "  \"peak_narratives\": [\"峰值总结1\", \"峰值总结2\"]\n"
        "}\n\n"
        "规则：\n"
        "1. theme_names 的顺序必须与输入主题顺序一致。\n"
        "2. peak_narratives 的顺序必须与输入峰值顺序一致。\n"
        "3. 主题名要求简短准确，峰值总结要求一句话概括观众情绪或反应。\n\n"
        f"弹幕主题：\n{chr(10).join(theme_lines)}\n\n"
        f"高能时刻：\n{chr(10).join(peak_lines)}\n"
    )
    raw = chat(prompt, max_new_tokens=500).strip()
    payload = _load_json_payload(raw)
    if not isinstance(payload, dict):
        payload = {}

    raw_theme_names = payload.get("theme_names") if isinstance(payload.get("theme_names"), list) else []
    raw_peak_narratives = payload.get("peak_narratives") if isinstance(payload.get("peak_narratives"), list) else []

    for i, theme in enumerate(themes):
        samples = theme.get("_samples", [])
        fallback = samples[0] if samples else "弹幕主题"
        name = _clean_name(raw_theme_names[i] if i < len(raw_theme_names) else "", fallback)
        theme["n"] = name
        theme.pop("_samples", None)

    for i, peak in enumerate(peaks):
        narrative = str(raw_peak_narratives[i]).strip() if i < len(raw_peak_narratives) else ""
        if not narrative:
            narrative = "弹幕密度较高，观众反应集中。"
        peak["s"] = narrative
        peak.pop("t_start", None)
        peak.pop("t_end", None)

    return themes, peaks


# ─── 兼容旧接口 ─────────────────────────────────────────────


def generate_peak_narratives(peaks: list[dict], danmakus: list[dict]) -> list[dict]:
    """兼容旧接口：单独补全峰值叙事。"""
    _, peaks = annotate_danmaku_findings([], peaks, danmakus)
    return peaks
