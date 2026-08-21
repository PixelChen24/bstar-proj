"""清洗去重模块：规则预过滤 + LLM 辅助判断"""

import re
from collections import Counter

from .llm import chat

# 纯标点/表情/特殊字符正则
RE_JUNK = re.compile(
    r"^[\s\W　-〿＀-￯]*$"  # 纯标点/全角符号
)
RE_EMOJI_ONLY = re.compile(
    r"^\[[\w一-鿿]+\]$"  # 纯表情标签 如 [doge]
)
RE_REPEAT_CHAR = re.compile(r"(.)\1{9,}")  # 同一字符连续 10+ 次


def clean_danmakus(danmakus: list[dict], use_llm: bool = True) -> tuple[list[dict], dict]:
    """
    清洗弹幕数据。

    返回 (清洗后列表, 统计信息)
    """
    print("🧹 正在清洗弹幕...")
    stats = {"total": len(danmakus), "rule_filtered": 0, "llm_filtered": 0, "dedup": 0}

    # 1. 完全去重
    seen_contents = {}
    deduped = []
    for dm in danmakus:
        content = dm["content"].strip()
        if content in seen_contents:
            stats["dedup"] += 1
            continue
        seen_contents[content] = True
        deduped.append(dm)

    # 2. 规则过滤
    rule_passed = []
    for dm in deduped:
        content = dm["content"].strip()
        if len(content) < 2:
            stats["rule_filtered"] += 1
            continue
        if RE_JUNK.match(content):
            stats["rule_filtered"] += 1
            continue
        if RE_EMOJI_ONLY.match(content):
            stats["rule_filtered"] += 1
            continue
        if RE_REPEAT_CHAR.search(content):
            stats["rule_filtered"] += 1
            continue
        rule_passed.append(dm)

    # 3. LLM 辅助：对高频弹幕（出现 ≥ 3 次的相似内容）批量判断
    result = rule_passed
    if use_llm:
        # 统计近似重复（按前6字分组）
        prefix_groups = Counter()
        for dm in rule_passed:
            prefix = dm["content"].strip()[:6]
            prefix_groups[prefix] += 1

        # 找出高频前缀对应的弹幕样本
        frequent_prefixes = {p for p, c in prefix_groups.items() if c >= 5}
        if frequent_prefixes:
            samples = []
            for p in list(frequent_prefixes)[:15]:  # 最多检查 15 组
                # 找一个该前缀的样例
                for dm in rule_passed:
                    if dm["content"].strip().startswith(p):
                        samples.append(dm["content"].strip()[:30])
                        break

            if samples:
                sample_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(samples))
                prompt = (
                    "以下是B站视频中出现多次的弹幕，判断每条是否为刷屏或无意义内容。\n"
                    "对每条回答'保留'或'过滤'，用序号对应。\n\n"
                    f"{sample_text}"
                )
                resp = chat(prompt, max_new_tokens=200)

                # 解析 LLM 回复，找出要过滤的前缀
                filter_prefixes = set()
                for i, prefix in enumerate(list(frequent_prefixes)[:15]):
                    if f"{i+1}" in resp and "过滤" in resp.split(f"{i+1}")[1][:20] if f"{i+1}" in resp else False:
                        filter_prefixes.add(prefix)

                if filter_prefixes:
                    before = len(result)
                    result = [
                        dm for dm in rule_passed
                        if dm["content"].strip()[:6] not in filter_prefixes
                    ]
                    stats["llm_filtered"] = before - len(result)

    stats["kept"] = len(result)
    print(f"  ✔ 弹幕清洗完成: {stats['total']} → {stats['kept']} 条")
    print(f"    去重: {stats['dedup']} | 规则过滤: {stats['rule_filtered']} | "
          f"LLM过滤: {stats['llm_filtered']}")
    return result, stats


def clean_comments(comments: list[dict], use_llm: bool = True) -> tuple[list[dict], dict]:
    """
    清洗评论数据。

    返回 (清洗后列表, 统计信息)
    """
    print("🧹 正在清洗评论...")
    stats = {"total": len(comments), "rule_filtered": 0, "llm_filtered": 0}

    # 规则过滤
    result = []
    for c in comments:
        content = c["content"].strip()
        if len(content) < 2:
            stats["rule_filtered"] += 1
            continue
        if RE_JUNK.match(content):
            stats["rule_filtered"] += 1
            continue
        if RE_EMOJI_ONLY.match(content):
            stats["rule_filtered"] += 1
            continue
        result.append(c)

    stats["kept"] = len(result)
    print(f"  ✔ 评论清洗完成: {stats['total']} → {stats['kept']} 条")
    print(f"    规则过滤: {stats['rule_filtered']}")
    return result, stats
