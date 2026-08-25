"""词云数据：弹幕/评论词频统计

只做分词与计数，不生成图片。前端按词频映射字号渲染。
两种模式（有/无 LLM）都会生成。
"""

from collections import Counter, defaultdict
import jieba

# 与聚类模块共用的停用词，额外补充弹幕高频语气词
_STOP_WORDS = {
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "吗", "吧", "啊", "呢", "哈", "嗯", "哦", "啦", "呀", "嘛",
    "什么", "怎么", "可以", "还是", "这个", "那个", "但是", "因为",
    "所以", "如果", "已经", "这样", "那样", "回复",
    "哈哈", "哈哈哈", "哈哈哈哈", "233", "2333", "23333",
    "我们", "你们", "他们", "而且", "然后", "不是", "就是",
    "真的", "感觉", "觉得", "现在", "一下", "一样", "还有",
}

TOP_N = 80
MAX_SAMPLES = 3


def build_wordcloud(danmakus: list[dict], comments: list[dict]) -> dict:
    """
    构建词云数据。

    返回 {"dm": [{"w","c","s"}], "cm": [{"w","c","s"}]}
    w=词, c=出现次数, s=最多 3 条包含该词的原文样例
    """
    print("\n☁️ 正在统计热词...")

    dm_texts = [d.get("content", "") for d in danmakus]
    cm_texts = [c.get("content", "") for c in comments]

    dm_words = _top_words(dm_texts)
    cm_words = _top_words(cm_texts)

    print(f"  ✔ 弹幕热词 {len(dm_words)} 个 / 评论热词 {len(cm_words)} 个")
    if dm_words:
        preview = "、".join(f"{w['w']}({w['c']})" for w in dm_words[:5])
        print(f"    弹幕 TOP5: {preview}")
    if cm_words:
        preview = "、".join(f"{w['w']}({w['c']})" for w in cm_words[:5])
        print(f"    评论 TOP5: {preview}")

    return {"dm": dm_words, "cm": cm_words}


def _top_words(texts: list[str]) -> list[dict]:
    """统计词频，返回 TOP_N 个词及原文样例。"""
    counter = Counter()
    samples = defaultdict(list)

    for text in texts:
        text = (text or "").strip()
        if not text:
            continue
        # 同一条内的重复词只计一次，避免单条刷屏抬高权重
        for word in set(_segment(text)):
            counter[word] += 1
            if len(samples[word]) < MAX_SAMPLES:
                samples[word].append(text[:60])

    return [
        {"w": word, "c": count, "s": samples[word]}
        for word, count in counter.most_common(TOP_N)
    ]


def _segment(text: str) -> list[str]:
    """jieba 分词并过滤停用词、单字、纯数字。"""
    return [
        w for w in jieba.lcut(text)
        if len(w) > 1 and w not in _STOP_WORDS and not w.isdigit()
    ]


def generate_word_clouds_from_records(danmakus: list[dict], comments: list[dict]) -> dict:
    """兼容 bstar 2 旧调用名，返回当前仓库更清晰的词云数据结构。"""
    return build_wordcloud(danmakus, comments)
