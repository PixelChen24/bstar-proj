"""LLM 后端封装：OpenAI 兼容接口 / Anthropic Messages API

两个后端共用 chat(prompt) -> str 接口。
"""

import re
import time

from .llm_config import load_config, validate

# 系统提示。末句用于抑制内部 XML 标签泄漏（部分模型关闭思考后会把
# <think>/<thinking> 写进正文），配合 _strip_think_tags 双重兜底。
SYSTEM_PROMPT = (
    "你是一个专业的B站视频数据分析助手，擅长归纳弹幕和评论的观点。回答简洁精准。"
    "不要在回答中包含任何内部或系统 XML 标签。"
)

_backend = None  # 已初始化的后端实例
_backend_cfg = None  # 初始化时使用的配置，用于检测配置变更


# ─── 初始化 ────────────────────────────────────────────────

def init_backend(cfg: dict | None = None, force: bool = False) -> str:
    """初始化 LLM 后端（单例）。配置变更时自动重建。返回后端描述字符串。"""
    global _backend, _backend_cfg

    cfg = cfg or load_config()

    # 配置没变就复用，避免每次分析都重新加载本地模型
    if _backend is not None and not force and cfg == _backend_cfg:
        return _backend.label

    errors = validate(cfg)
    if errors:
        raise RuntimeError(f"LLM 配置无效：{'；'.join(errors)}")

    provider = cfg["provider"]
    section = cfg[provider]

    print(f"🤖 正在初始化 LLM 后端: {provider}")
    if provider == "openai":
        _backend = _OpenAIBackend(section)
    elif provider == "anthropic":
        _backend = _AnthropicBackend(section)
    else:
        raise RuntimeError(f"未知的 provider: {provider}")

    _backend_cfg = cfg
    print(f"  ✔ {_backend.label}")
    return _backend.label


def current_backend_label() -> str:
    return _backend.label if _backend else "未初始化"


def chat(prompt: str, max_new_tokens: int = 300, temperature: float = 0.1) -> str:
    """单轮对话，返回模型回复文本。"""
    if _backend is None:
        raise RuntimeError("LLM 后端未初始化，请先调用 init_backend()")
    resp = _backend.chat(prompt, max_new_tokens, temperature)
    return _strip_think_tags(resp)


def batch_chat(prompts: list[str], max_new_tokens: int = 128) -> list[str]:
    """逐条处理多个 prompt。"""
    return [chat(p, max_new_tokens=max_new_tokens) for p in prompts]


def test_connection(cfg: dict) -> dict:
    """用给定配置发一次极短请求，验证连通性。不影响已初始化的后端。"""
    errors = validate(cfg)
    if errors:
        return {"ok": False, "error": "；".join(errors)}

    provider = cfg["provider"]
    section = cfg[provider]
    t0 = time.time()
    try:
        if provider == "openai":
            backend = _OpenAIBackend(section)
        else:
            backend = _AnthropicBackend(section)
        reply = backend.chat("回答一个字：好", max_new_tokens=16, temperature=0.1)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed": round(time.time() - t0, 1)}

    return {
        "ok": True,
        "label": backend.label,
        "reply": _strip_think_tags(reply)[:80],
        "elapsed": round(time.time() - t0, 1),
    }


def _strip_think_tags(text: str) -> str:
    """移除可能残留的 <think>/<thinking> 标签。"""
    text = re.sub(r"<(think|thinking)>.*?</\1>", "", text, flags=re.DOTALL)
    text = re.sub(r"<(think|thinking)>.*$", "", text, flags=re.DOTALL)
    return text.strip()


# ─── OpenAI 兼容接口 ────────────────────────────────────────

class _OpenAIBackend:
    """覆盖 OpenAI / DeepSeek / 通义 / Kimi / 智谱 / SiliconFlow / Ollama 等。"""

    def __init__(self, section: dict):
        import requests

        self._requests = requests
        self.model = section["model"]
        self.api_key = section.get("api_key") or ""
        self.base_url = section["base_url"].rstrip("/")
        self.url = f"{self.base_url}/chat/completions"
        # 部分服务（如新版 OpenAI 模型）不接受 temperature / max_tokens，
        # 首次遇到 400 后记住并降级重试
        self._drop_temperature = False
        self._use_max_completion_tokens = False

        host = self.base_url.split("//", 1)[-1].split("/", 1)[0]
        self.label = f"OpenAI 兼容接口 {self.model} @ {host}"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _payload(self, prompt: str, max_new_tokens: int, temperature: float) -> dict:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        key = "max_completion_tokens" if self._use_max_completion_tokens else "max_tokens"
        body[key] = max_new_tokens
        if not self._drop_temperature:
            body["temperature"] = temperature
        return body

    def chat(self, prompt: str, max_new_tokens: int, temperature: float, max_retries: int = 3) -> str:
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                resp = self._requests.post(
                    self.url,
                    json=self._payload(prompt, max_new_tokens, temperature),
                    headers=self._headers(),
                    timeout=60,
                )
            except self._requests.RequestException as e:
                last_error = e
                if attempt == max_retries:
                    break
                time.sleep(1 * attempt)
                continue

            if resp.status_code == 400 and self._downgrade(resp.text):
                continue  # 去掉不被接受的参数后立即重试，不计入退避
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                if attempt == max_retries:
                    break
                time.sleep(2 * attempt)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"接口返回 HTTP {resp.status_code}: {resp.text[:300]}")

            return self._extract(resp.json())

        raise RuntimeError(f"接口请求失败（重试 {max_retries} 次）: {last_error}")

    def _downgrade(self, body: str) -> bool:
        """按 400 报错内容剔除不被支持的参数。返回是否做了降级。"""
        lowered = body.lower()
        if "max_completion_tokens" in lowered and not self._use_max_completion_tokens:
            self._use_max_completion_tokens = True
            print("  ⚠ 该服务要求 max_completion_tokens，已切换")
            return True
        if "temperature" in lowered and not self._drop_temperature:
            self._drop_temperature = True
            print("  ⚠ 该服务不支持 temperature，已移除")
            return True
        return False

    @staticmethod
    def _extract(data: dict) -> str:
        if data.get("error"):
            raise RuntimeError(f"接口返回错误: {data['error']}")
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"接口返回内容为空: {str(data)[:200]}")
        return (choices[0].get("message", {}).get("content") or "").strip()


# ─── Anthropic Messages API ────────────────────────────────

class _AnthropicBackend:
    """官方 anthropic SDK。

    注意 Claude 5 系模型的两个约束：
    - temperature / top_p / top_k 已移除，发送会 400，所以这里不传采样参数；
    - 思考默认开启。本管线是几十次短小的归纳/分类调用，开思考成本和延迟都不划算，
      因此关闭思考并用 effort=low（关闭思考仅在 effort <= high 时允许）。
    """

    # 未配置 base_url 时显式传官方地址。SDK 对 None 参数会去读
    # ANTHROPIC_BASE_URL，留空等于把地址交给宿主机环境决定
    DEFAULT_API_BASE = "https://api.anthropic.com"

    def __init__(self, section: dict):
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError("未安装 anthropic SDK，请执行：pip install anthropic") from e

        self._anthropic = anthropic
        self.model = section["model"]

        # 三个凭证/地址参数全部显式传入：SDK 只在参数为 None 时才回退到
        # ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL，
        # 而开发机上这些变量常被别的工具占用。
        self.client = anthropic.Anthropic(
            api_key=section["api_key"],
            auth_token="",  # 空串（而非 None）用于屏蔽上面那次 env 回退
            base_url=section.get("base_url") or self.DEFAULT_API_BASE,
            max_retries=3,
            timeout=60.0,
        )
        # env 只在构造时读一次，构造完置回 None：留着空串会让 SDK 每次请求都带上
        # 一个空的 Authorization: Bearer 头，部分网关见到它会优先采用并直接 401
        self.client.auth_token = None

        # 首次请求探测是否支持服务端 refusal fallback（旧版 SDK 不认识该参数）
        self._server_fallback = True
        self.label = f"Anthropic {self.model}"

    def chat(self, prompt: str, max_new_tokens: int, temperature: float) -> str:
        params = {
            "model": self.model,
            "max_tokens": max(max_new_tokens, 16),
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "thinking": {"type": "disabled"},
            "output_config": {"effort": "low"},
        }

        if self._server_fallback:
            try:
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    **params,
                )
            except (TypeError, self._anthropic.BadRequestError) as e:
                # SDK 或账号不支持 fallback / effort / thinking 组合，退回普通调用
                self._server_fallback = False
                print(f"  ⚠ 服务端 fallback 不可用，改用标准调用（{type(e).__name__}）")
                resp = self._create_plain(params)
        else:
            resp = self._create_plain(params)

        return self._extract(resp)

    def _create_plain(self, params: dict):
        try:
            return self.client.messages.create(**params)
        except (TypeError, self._anthropic.BadRequestError):
            # 老模型不认识 output_config / thinking，逐个剥离后重试
            reduced = {k: v for k, v in params.items() if k not in ("output_config", "thinking")}
            return self.client.messages.create(**reduced)

    def _extract(self, resp) -> str:
        # refusal 是 HTTP 200，content 可能为空或只有部分内容，必须先判断
        if getattr(resp, "stop_reason", None) == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            raise RuntimeError(f"请求被安全策略拒绝（category={category}）")

        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(parts).strip()
