"""报告生成：复盘结论（slots）+ 可执行建议（acts）"""

import json
import re

from .llm import chat


def _strip_markdown(text: str) -> str:
    """去除 markdown 格式标记（**bold** → bold 等）。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    return text.strip()


def generate_report(
    dm_themes: list[dict],
    peaks: list[dict],
    cm_themes: list[dict],
    video_info: dict,
) -> tuple[list[dict], list[dict]]:
    """
    生成复盘报告。

    返回 (slots, acts)
    """
    print("\n📊 正在生成复盘报告...")

    # 构建分析上下文摘要
    context = _build_context(dm_themes, peaks, cm_themes, video_info)

    # 1. 生成 5 个固定问题的结论
    slots = generate_slots(context, dm_themes, cm_themes)

    # 2. 生成 Top5 可执行建议
    acts = generate_acts(context)

    return slots, acts


def _build_context(
    dm_themes: list[dict],
    peaks: list[dict],
    cm_themes: list[dict],
    video_info: dict,
) -> str:
    """构建供 LLM 使用的分析上下文摘要。"""
    lines = []
    lines.append(f"视频: {video_info.get('title', '未知')}")
    stat = video_info.get("stat", {})
    lines.append(f"播放: {stat.get('view', 0)} | 弹幕: {stat.get('danmaku', 0)} | 评论: {stat.get('reply', 0)}")

    if dm_themes:
        lines.append("\n弹幕主题:")
        for t in dm_themes:
            lines.append(f"  - {t['n']}: {t['c']}条 ({t['t']})")

    if peaks:
        lines.append("\n高能时刻:")
        for p in peaks:
            lines.append(f"  - {p['tm']} 密度{p['x']}，{p['n']}条弹幕: {p.get('s', '')}")

    if cm_themes:
        lines.append("\n评论主题:")
        for t in cm_themes:
            dis = f"，争议度{t['dis']}" if t.get("dis") else ""
            lines.append(f"  - {t['n']}: {t['c']}条{dis}")
            for q in t.get("q", []):
                stance = "支持" if q["k"] == "pro" else "反对"
                lines.append(f"    [{stance}] {q['t'][:50]} ({q['l']}赞)")

    return "\n".join(lines)


# ─── 复盘结论 ───────────────────────────────────────────────

SLOT_QUESTIONS = [
    {"h": "观众最喜欢什么", "hint": "找到最受欢迎的内容和时刻"},
    {"h": "最不满意什么", "hint": "找到负面反馈最多的主题"},
    {"h": "最常问什么", "hint": "找到观众提问或求资源的主题"},
    {"h": "有哪些争议", "hint": "找到支持和反对分歧大的主题"},
    {"h": "下期值得关注", "hint": "从评论中提取选题线索和催更方向"},
]


def generate_slots(
    context: str, dm_themes: list[dict], cm_themes: list[dict]
) -> list[dict]:
    """生成 5 个固定问题的回答。"""
    print("  📝 生成复盘结论...")
    slots = []

    for sq in SLOT_QUESTIONS:
        prompt = (
            f"根据以下B站视频的弹幕和评论分析结果：\n\n"
            f"{context}\n\n"
            f"问题: {sq['h']}？（{sq['hint']}）\n"
            f"请用一句话简洁回答，引用具体数据（如条数、时间点等）："
        )
        answer = chat(prompt, max_new_tokens=100)
        answer = answer.strip()

        # 计算溯源主题数
        ref_count = 0
        all_themes = (dm_themes or []) + (cm_themes or [])
        for t in all_themes:
            name = t.get("n", "")
            if name and name[:3] in answer:
                ref_count += 1
        ref_count = max(ref_count, 1)

        slots.append({
            "h": sq["h"],
            "p": _strip_markdown(answer),
            "r": f"溯源 {ref_count} 个主题",
        })
        print(f"    ✔ {sq['h']}: {answer[:40]}...")

    return slots


# ─── 可执行建议 ───────────────────────────────────────────────

def generate_acts(context: str) -> list[dict]:
    """生成 Top5 可执行改进建议。"""
    print("  📝 生成 Top5 建议...")

    prompt = (
        f"根据以下B站视频的弹幕和评论分析结果：\n\n"
        f"{context}\n\n"
        f"请给UP主提出5条具体可执行的改进建议。\n"
        f"每条建议格式：\n"
        f"建议: <具体行动>\n"
        f"依据: <对应的数据证据>\n\n"
        f"请输出5条："
    )
    resp = chat(prompt, max_new_tokens=500)

    acts = _parse_acts(resp)

    # 如果解析不出 5 条，补充默认建议
    if len(acts) < 3:
        acts = _fallback_acts(context)

    # strip markdown
    for a in acts:
        a["t"] = _strip_markdown(a["t"])
        a["s"] = _strip_markdown(a["s"])

    for i, a in enumerate(acts[:5]):
        print(f"    {i+1}. {a['t'][:40]}...")

    return acts[:5]


def _parse_acts(text: str) -> list[dict]:
    """从 LLM 输出中解析建议列表。"""
    acts = []
    lines = text.strip().split("\n")

    current_t = ""
    current_s = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 尝试匹配 "建议:" 或 "N." 或 "N、" 格式
        if line.startswith("建议") and ":" in line:
            if current_t:
                acts.append({"t": current_t, "s": current_s or "综合分析"})
            current_t = line.split(":", 1)[1].strip() if ":" in line else line.split("：", 1)[1].strip()
            current_s = ""
        elif line.startswith("依据") and (":" in line or "：" in line):
            sep = "：" if "：" in line else ":"
            current_s = line.split(sep, 1)[1].strip()
        elif len(line) > 2 and line[0].isdigit() and line[1] in ".、.）)":
            if current_t:
                acts.append({"t": current_t, "s": current_s or "综合分析"})
            current_t = line[2:].strip().lstrip(".、）) ")
            current_s = ""
        elif current_t and not current_s:
            # 可能是建议的续行或依据
            if "依据" in line or "证据" in line or "数据" in line:
                current_s = line
            else:
                current_t += line

    if current_t:
        acts.append({"t": current_t, "s": current_s or "综合分析"})

    return acts


def _fallback_acts(context: str) -> list[dict]:
    """当解析失败时，逐条生成建议。"""
    acts = []
    for i in range(1, 6):
        prompt = (
            f"根据以下分析结果，给UP主第{i}条改进建议（一句话，15字以内）：\n"
            f"{context[:500]}\n建议："
        )
        t = chat(prompt, max_new_tokens=40).strip()
        acts.append({"t": t, "s": "综合分析"})
    return acts
