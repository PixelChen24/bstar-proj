"""弹幕分析：峰值检测 + 主题聚类"""

from collections import Counter, defaultdict
import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from .llm import chat


def analyze_danmaku(
    danmakus: list[dict], video_duration: int
) -> tuple[list[dict], list[dict]]:
    """
    分析弹幕数据。

    返回 (dmThemes, peaks)
    """
    print(f"\n🔍 正在分析弹幕 ({len(danmakus)} 条)...")

    # 1. 峰值检测
    peaks = detect_peaks(danmakus, video_duration)

    # 2. 主题聚类
    dm_themes = cluster_danmaku_themes(danmakus)

    # 3. LLM 生成峰值叙事
    peaks = generate_peak_narratives(peaks, danmakus)

    return dm_themes, peaks


# ─── 峰值检测 ───────────────────────────────────────────────

def detect_peaks(
    danmakus: list[dict], video_duration: int, bucket_sec: int = 10, threshold: float = 3.0
) -> list[dict]:
    """
    检测弹幕密度峰值。

    按 bucket_sec 秒分桶，找出密度 > 全局平均 × threshold 的区间。
    """
    print("  📈 检测弹幕密度峰值...")

    if not danmakus or video_duration <= 0:
        return []

    # 分桶统计
    num_buckets = max(1, video_duration // bucket_sec + 1)
    buckets = [0] * num_buckets
    for dm in danmakus:
        idx = min(int(dm["progress"] / bucket_sec), num_buckets - 1)
        buckets[idx] += 1

    # 全局平均
    avg = sum(buckets) / num_buckets if num_buckets > 0 else 0
    if avg == 0:
        return []

    # 找高密度桶
    hot_indices = [i for i, c in enumerate(buckets) if c > avg * threshold]
    if not hot_indices:
        # 降低阈值再试
        hot_indices = [i for i, c in enumerate(buckets) if c > avg * 2]
    if not hot_indices:
        return []

    # 合并相邻桶为区间
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

    # 构建峰值结果
    peaks = []
    for start, end in regions:
        t_start = start * bucket_sec
        t_end = (end + 1) * bucket_sec
        count = sum(buckets[start:end + 1])
        density = count / ((end - start + 1) * bucket_sec) if end >= start else 0
        avg_density = avg / bucket_sec
        multiplier = density / avg_density if avg_density > 0 else 0

        # 取中点作为标记时间
        t_mid = (t_start + t_end) // 2
        tm = f"{t_mid // 60:02d}:{t_mid % 60:02d}"

        peaks.append({
            "tm": tm,
            "x": f"{multiplier:.1f}x",
            "n": count,
            "t_start": t_start,
            "t_end": t_end,
            "s": "",  # 后续 LLM 填充
        })

    # 按密度倍数排序，取 TOP 3
    peaks.sort(key=lambda p: float(p["x"].rstrip("x")), reverse=True)
    peaks = peaks[:3]

    for p in peaks:
        print(f"    ⚡ {p['tm']} 密度 {p['x']}，{p['n']} 条弹幕")

    return peaks


# ─── 主题聚类 ───────────────────────────────────────────────

def _tokenize(text: str) -> str:
    """jieba 分词，返回空格分隔的字符串。"""
    words = jieba.lcut(text)
    # 过滤单字和停用词
    stop = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
            "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "啦", "呀", "嘛",
            "哈哈", "哈哈哈", "哈哈哈哈", "233", "2333", "23333"}
    words = [w for w in words if len(w) > 1 and w not in stop]
    return " ".join(words)


def cluster_danmaku_themes(danmakus: list[dict]) -> list[dict]:
    """
    使用 TF-IDF + KMeans 对弹幕进行主题聚类。
    """
    print("  🏷️ 弹幕主题聚类中...")

    if len(danmakus) < 10:
        return []

    # 分词
    texts = [_tokenize(dm["content"]) for dm in danmakus]
    # 过滤空文本
    valid = [(i, t) for i, t in enumerate(texts) if t.strip()]
    if len(valid) < 10:
        return []

    indices, tokenized = zip(*valid)

    # TF-IDF
    vectorizer = TfidfVectorizer(max_features=500, min_df=2, max_df=0.8)
    try:
        tfidf_matrix = vectorizer.fit_transform(tokenized)
    except ValueError:
        return []

    # 选择 k
    k = min(8, max(3, len(valid) // 80))

    # KMeans 聚类
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=100)
    labels = kmeans.fit_predict(tfidf_matrix)

    # 按簇分组
    clusters = defaultdict(list)
    for idx, label in zip(indices, labels):
        clusters[label].append(danmakus[idx])

    # 为每个簇生成主题
    themes = []
    for label in sorted(clusters.keys()):
        members = clusters[label]
        if len(members) < 3:
            continue

        # 选代表弹幕（按出现频率选最典型的 5 条）
        content_counter = Counter(m["content"] for m in members)
        top_contents = [c for c, _ in content_counter.most_common(5)]

        # 时间分布
        time_range = _describe_time_range(members)

        # LLM 生成主题名
        sample_text = "\n".join(f"- {c}" for c in top_contents)
        prompt = (
            f"以下是B站视频中同一类弹幕的代表内容，请用一个简短的主题名概括（8字以内）：\n"
            f"{sample_text}\n"
            f"主题名："
        )
        theme_name = chat(prompt, max_new_tokens=30)
        # 清理引号等
        theme_name = theme_name.strip().strip('"').strip("'").strip("「」").strip("《》")
        if not theme_name or len(theme_name) > 20:
            theme_name = top_contents[0][:10]

        themes.append({
            "n": theme_name,
            "c": len(members),
            "t": time_range,
        })

    # 按数量排序
    themes.sort(key=lambda t: t["c"], reverse=True)
    themes = themes[:6]  # 最多 6 个主题

    for t in themes:
        print(f"    📌 {t['n']}: {t['c']} 条 ({t['t']})")

    return themes


def _describe_time_range(danmakus: list[dict]) -> str:
    """生成弹幕时间段描述。"""
    if not danmakus:
        return "零散"

    progresses = [dm["progress"] for dm in danmakus]
    p_min = min(progresses)
    p_max = max(progresses)
    span = p_max - p_min

    # 如果跨度很大（覆盖 > 70% 视频），标为全片
    total_range = p_max  # 近似
    if total_range > 0 and span / total_range > 0.7:
        return "全片"

    # 找密度集中区间（Q1-Q3）
    progresses.sort()
    q1 = progresses[len(progresses) // 4]
    q3 = progresses[3 * len(progresses) // 4]

    if q3 - q1 < 30:
        # 很集中
        mid = (q1 + q3) / 2
        return f"{int(mid)//60:02d}:{int(mid)%60:02d} 附近"

    return (
        f"{int(q1)//60:02d}:{int(q1)%60:02d}-"
        f"{int(q3)//60:02d}:{int(q3)%60:02d}"
    )


# ─── 峰值叙事 ───────────────────────────────────────────────

def generate_peak_narratives(peaks: list[dict], danmakus: list[dict]) -> list[dict]:
    """用 LLM 为每个峰值区间生成叙事总结。"""
    if not peaks:
        return peaks

    print("  📝 生成峰值叙事...")

    for peak in peaks:
        t_start = peak.get("t_start", 0)
        t_end = peak.get("t_end", 0)

        # 收集该区间内的弹幕
        region_dms = [
            dm["content"] for dm in danmakus
            if t_start <= dm["progress"] < t_end
        ]

        if not region_dms:
            peak["s"] = "弹幕密度较高的区间"
            continue

        # 取代表弹幕（去重后取前 15 条）
        seen = set()
        unique_dms = []
        for text in region_dms:
            if text not in seen:
                seen.add(text)
                unique_dms.append(text)
            if len(unique_dms) >= 15:
                break

        sample_text = "\n".join(f"- {d}" for d in unique_dms)
        prompt = (
            f"视频在 {peak['tm']} 附近弹幕密度暴增（{peak['n']}条），"
            f"以下是这段时间的弹幕内容：\n{sample_text}\n\n"
            f"请用一句话总结观众在这个时间点的反应和情绪（30字以内）："
        )
        narrative = chat(prompt, max_new_tokens=60)
        peak["s"] = narrative.strip()

    # 清理内部字段
    for peak in peaks:
        peak.pop("t_start", None)
        peak.pop("t_end", None)

    return peaks
