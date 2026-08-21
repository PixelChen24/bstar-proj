"""LLM 加载与调用封装"""

import re
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_model = None
_tokenizer = None
_device = None

DEFAULT_MODEL = "Qwen/Qwen3-0.6B"


def load_model(model_name: str = DEFAULT_MODEL) -> None:
    """加载模型和 tokenizer 到 GPU（单例）。"""
    global _model, _tokenizer, _device

    if _model is not None:
        return

    print(f"🤖 正在加载模型: {model_name}")
    _device = "cuda" if torch.cuda.is_available() else "cpu"

    _tokenizer = AutoTokenizer.from_pretrained(
        model_name, trust_remote_code=True
    )
    _model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if _device == "cuda" else torch.float32,
        device_map="auto" if _device == "cuda" else None,
        trust_remote_code=True,
    )
    _model.eval()

    mem = torch.cuda.memory_allocated() / 1024**2 if _device == "cuda" else 0
    print(f"  ✔ 模型已加载到 {_device} (显存占用: {mem:.0f} MB)")


def chat(prompt: str, max_new_tokens: int = 300, temperature: float = 0.1) -> str:
    """单轮对话，返回模型回复文本。"""
    if _model is None:
        raise RuntimeError("模型未加载，请先调用 load_model()")

    messages = [
        {"role": "system", "content": "你是一个专业的B站视频数据分析助手，擅长归纳弹幕和评论的观点。回答简洁精准。"},
        {"role": "user", "content": prompt},
    ]

    # Qwen3 支持 enable_thinking=False 跳过思考过程，直接输出回答
    text = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = _tokenizer(text, return_tensors="pt").to(_model.device)

    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=max(temperature, 0.01),
            top_p=0.9,
            do_sample=temperature > 0,
            pad_token_id=_tokenizer.pad_token_id or _tokenizer.eos_token_id,
        )

    # 只取新生成的部分
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    response = _tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    # 保险：仍然清理可能残留的 think 标签
    response = _strip_think_tags(response)
    return response


def _strip_think_tags(text: str) -> str:
    """移除可能残留的 <think>...</think> 标签。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


def batch_chat(prompts: list[str], max_new_tokens: int = 128) -> list[str]:
    """逐条处理多个 prompt。"""
    results = []
    for p in prompts:
        results.append(chat(p, max_new_tokens=max_new_tokens))
    return results
