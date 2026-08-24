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


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _load_json_payload(text: str):
    """从 LLM 回复中提取 JSON 对象。"""
    cleaned = _strip_code_fences(text)
    candidates = [cleaned]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start:end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def generate_report(
    dm_themes: list[dict],
    peaks: list[dict],
    cm_themes: list[dict],
    video_info: dict,
    on_progress=None,
) -> tuple[list[dict], list[dict]]:
    """
    生成复盘报告。

    返回 (slots, acts)
    """
    print("\n📊 正在生成复盘报告...")
    if on_progress:
        on_progress(4, "正在汇总复盘报告...", "", 0.1)

    # 构建分析上下文摘要
    context = _build_context(dm_themes, peaks, cm_themes, video_info)

    # 合并生成 5 个固定问题 + Top5 建议，原来这里是 6 次 LLM 调用。
    slots, acts = generate_report_bundle(context, dm_themes, cm_themes)
    if on_progress:
        on_progress(4, f"复盘报告完成：{len(slots)} 条结论 / {len(acts)} 条建议", "", 1.0)
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


def _slot_ref_count(answer: str, dm_themes: list[dict], cm_themes: list[dict]) -> int:
    ref_count = 0
    all_themes = (dm_themes or []) + (cm_themes or [])
    for t in all_themes:
        name = t.get("n", "")
        if name and name[:3] in answer:
            ref_count += 1
    return max(ref_count, 1)


def generate_report_bundle(
    context: str, dm_themes: list[dict], cm_themes: list[dict]
) -> tuple[list[dict], list[dict]]:
    """一次 LLM 调用同时生成复盘结论和可执行建议。解析失败时会自动退回原逻辑。"""
    print("  📝 合并生成复盘结论与 Top5 建议...")

    questions = "\n".join(f"- {q['h']}：{q['hint']}" for q in SLOT_QUESTIONS)
    prompt = (
        "根据以下B站视频的弹幕和评论分析结果，一次性生成复盘报告。\n\n"
        f"{context}\n\n"
        "请严格输出 JSON，不要输出额外解释。\n"
        "输出格式：\n"
        "{\n"
        "  \"slots\": [\n"
        "    {\"h\":\"观众最喜欢什么\",\"p\":\"一句话结论，引用具体数据\"}\n"
        "  ],\n"
        "  \"acts\": [\n"
        "    {\"t\":\"具体行动\",\"s\":\"对应的数据证据\"}\n"
        "  ]\n"
        "}\n\n"
        "固定问题必须且只包含以下 5 个：\n"
        f"{questions}\n\n"
        "要求：\n"
        "1. slots 每条 p 用一句话回答，并引用条数、时间点、争议度等具体数据。\n"
        "2. acts 必须给 5 条具体可执行建议，t 是行动，s 是依据。\n"
        "3. 不要使用 Markdown。\n"
    )
    raw = chat(prompt, max_new_tokens=700).strip()
    payload = _load_json_payload(raw)

    if isinstance(payload, dict):
        slots = _normalize_slots(payload.get("slots"), dm_themes, cm_themes)
        acts = _normalize_acts(payload.get("acts"))
        if len(slots) == len(SLOT_QUESTIONS) and len(acts) >= 3:
            for s in slots:
                print(f"    ✔ {s['h']}: {s['p'][:40]}...")
            for i, a in enumerate(acts[:5]):
                print(f"    {i+1}. {a['t'][:40]}...")
            return slots, acts[:5]

    # 解析失败时仍保持可用：用本地规则生成，不再额外请求模型。
    print("  ⚠ 合并报告解析失败，改用旧逻辑兜底")
    return _fallback_report_bundle(context, dm_themes, cm_themes)


def _normalize_slots(raw_slots, dm_themes: list[dict], cm_themes: list[dict]) -> list[dict]:
    if not isinstance(raw_slots, list):
        return []

    ordered_answers = []
    by_h = {}
    for item in raw_slots:
        if not isinstance(item, dict):
            continue
        h = str(item.get("h", "")).strip()
        p = _strip_markdown(str(item.get("p", "")).strip())
        if not p:
            continue
        ordered_answers.append(p)
        if h:
            by_h[h] = p

    slots = []
    used_answers = set()
    for i, sq in enumerate(SLOT_QUESTIONS):
        answer = by_h.get(sq["h"], "")
        if not answer:
            # 允许模型在标题上略有差异，按包含关系兜底匹配。
            for h, p in by_h.items():
                if p in used_answers:
                    continue
                if sq["h"] in h or h in sq["h"]:
                    answer = p
                    break
        if not answer and i < len(ordered_answers):
            # 标题不匹配时按输出顺序兜底，避免因为小标题变化触发 6 次回退调用。
            answer = ordered_answers[i]
        if not answer:
            continue
        used_answers.add(answer)
        slots.append({
            "h": sq["h"],
            "p": answer,
            "r": f"溯源 {_slot_ref_count(answer, dm_themes, cm_themes)} 个主题",
        })
    return slots


def _normalize_acts(raw_acts) -> list[dict]:
    if not isinstance(raw_acts, list):
        return []
    acts = []
    for item in raw_acts:
        if not isinstance(item, dict):
            continue
        t = _strip_markdown(str(item.get("t", "")).strip())
        s = _strip_markdown(str(item.get("s", "")).strip())
        if t:
            acts.append({"t": t, "s": s or "综合分析"})
    return acts[:5]


def _fallback_report_bundle(context: str, dm_themes: list[dict], cm_themes: list[dict]) -> tuple[list[dict], list[dict]]:
    """合并输出解析失败时的兜底，保持可用性。"""
    slots = generate_slots(context, dm_themes, cm_themes)
    acts = generate_acts(context)
    return slots, acts


# 下面两个函数保留作合并 JSON 解析失败时的兜底。

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

        slots.append({
            "h": sq["h"],
            "p": _strip_markdown(answer),
            "r": f"溯源 {_slot_ref_count(answer, dm_themes, cm_themes)} 个主题",
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
