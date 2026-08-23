"""LLM 后端配置：本地配置文件（密钥）+ 环境变量（非敏感项）

优先级：配置文件 > 环境变量 > 内置默认值。

API Key 与接口地址只从本地配置文件读取（./config/llm.json，权限 0600，
由 Web 设置面板或手动写入）。故意不从环境变量继承这两项：宿主机上常有
同名变量（如其他工具设置的 ANTHROPIC_BASE_URL / OPENAI_API_KEY），
继承会让本服务在用户不知情的情况下把请求和密钥发往意料之外的地址。

环境变量只用于非敏感项（LLM_PROVIDER / LLM_MODEL），方便 Docker / CI 选后端。
"""

import json
import os

PROVIDERS = ("local", "openai", "anthropic")

DEFAULT_LOCAL_MODEL = "Qwen/Qwen3-0.6B"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"

# 供前端下拉展示的 OpenAI 兼容服务预设
OPENAI_PRESETS = [
    {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    {"label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    {"label": "阿里云百炼（通义）", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    {"label": "月之暗面 Kimi", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-8k"},
    {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    {"label": "硅基流动 SiliconFlow", "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen3-8B"},
    {"label": "本地 Ollama", "base_url": "http://localhost:11434/v1", "model": "qwen3:0.6b"},
]

# 供前端下拉展示的 Anthropic 模型
ANTHROPIC_MODELS = [
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
    "claude-fable-5",
]

SECRET_FIELDS = ("api_key",)


def config_path() -> str:
    return os.environ.get("LLM_CONFIG_PATH", "./config/llm.json")


# ─── 默认值与环境变量 ────────────────────────────────────────

def _defaults() -> dict:
    """内置默认值。base_url 一律留空，由用户显式填写——预置一个默认地址会让
    误配的请求静默发往某个真实服务端，而不是当场报错。"""
    return {
        "provider": "local",
        "local": {"model": DEFAULT_LOCAL_MODEL},
        "openai": {"model": "", "api_key": "", "base_url": ""},
        "anthropic": {"model": DEFAULT_ANTHROPIC_MODEL, "api_key": "", "base_url": ""},
    }


def from_env() -> dict:
    """从环境变量构建配置。只读取非敏感项。

    刻意不读 OPENAI_API_KEY / ANTHROPIC_API_KEY / *_BASE_URL：这些名字在开发机上
    经常已被别的工具占用，继承会导致密钥和请求被发往用户没有指定的地址。
    密钥与接口地址统一走 config_path() 指向的本地文件。
    """
    cfg = _defaults()

    provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if provider in PROVIDERS:
        cfg["provider"] = provider

    # LLM_MODEL 作用于当前 provider（兼容旧版行为：provider=local 时即本地模型名）
    if os.environ.get("LLM_MODEL"):
        cfg[cfg["provider"]]["model"] = os.environ["LLM_MODEL"]

    return cfg


# ─── 读写 ──────────────────────────────────────────────────

def _is_placeholder_secret(value: str) -> bool:
    """判断是否为脱敏回显值。前端把 mask_secret() 的结果原样提交回来时，
    不能当成真实密钥写入，否则会把已保存的 key 覆盖成一串星号。"""
    return "*" in value


def _merge(base: dict, patch: dict) -> dict:
    """两层深合并，只接受已知的 provider 字段。

    密钥字段留空或为脱敏回显值时保留原值——前端表单默认展示脱敏串，
    用户不改动就应该沿用已存的密钥。
    """
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    if not isinstance(patch, dict):
        return out

    provider = str(patch.get("provider", "")).strip().lower()
    if provider in PROVIDERS:
        out["provider"] = provider

    for name in PROVIDERS:
        section = patch.get(name)
        if not isinstance(section, dict):
            continue
        for key in out[name]:
            if key not in section or section[key] is None:
                continue
            value = str(section[key]).strip()
            if key in SECRET_FIELDS and (not value or _is_placeholder_secret(value)):
                continue
            out[name][key] = value

    return out


def override(
    cfg: dict,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """把命令行参数覆盖到配置上（不落盘）。空值表示不覆盖。"""
    patch = {}
    if provider:
        patch["provider"] = provider

    target = (provider or cfg.get("provider") or "local").strip().lower()
    section = {k: v for k, v in
               (("model", model), ("api_key", api_key), ("base_url", base_url)) if v}
    if section and target in PROVIDERS:
        patch[target] = section

    return _merge(cfg, patch)


def load_config() -> dict:
    """读取生效配置（配置文件覆盖环境变量）。"""
    cfg = from_env()

    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = _merge(cfg, json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠ 配置文件读取失败，回退到环境变量: {path} ({e})")

    return cfg


def save_config(patch: dict) -> dict:
    """把 patch 合并进现有配置并落盘。返回落盘后的完整配置。"""
    cfg = _merge(load_config(), patch)

    errors = validate(cfg)
    if errors:
        raise ValueError("；".join(errors))

    path = config_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 先以 0600 创建再写入，避免 API key 短暂处于默认权限下
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    return cfg


# ─── 校验与脱敏 ─────────────────────────────────────────────

def validate(cfg: dict) -> list[str]:
    """校验配置，返回错误信息列表（空列表表示通过）。"""
    errors = []
    provider = cfg.get("provider")
    if provider not in PROVIDERS:
        return [f"未知的 provider: {provider}"]

    section = cfg.get(provider) or {}
    if not section.get("model"):
        errors.append("模型名不能为空")

    if provider == "openai":
        base_url = section.get("base_url") or ""
        if not base_url:
            errors.append("接口地址（base_url）不能为空")
        elif not base_url.startswith(("http://", "https://")):
            errors.append("接口地址需以 http:// 或 https:// 开头")
    elif provider == "anthropic":
        if not section.get("api_key"):
            errors.append("Anthropic API Key 不能为空")

    return errors


def mask_secret(value: str) -> str:
    """脱敏展示：保留前 6 后 4 位。"""
    if not value:
        return ""
    if len(value) <= 12:
        return "*" * len(value)
    return f"{value[:6]}{'*' * 6}{value[-4:]}"


def public_view(cfg: dict) -> dict:
    """给前端的配置视图：密钥字段脱敏，附带 *_set 标记。"""
    out = {"provider": cfg["provider"]}
    for name in PROVIDERS:
        section = dict(cfg.get(name) or {})
        for field in SECRET_FIELDS:
            if field in section:
                raw = section[field]
                section[field] = mask_secret(raw)
                section[f"{field}_set"] = bool(raw)
        out[name] = section
    return out


def describe_sources() -> dict:
    """当前配置的来源，供前端提示。"""
    path = config_path()
    env_keys = [k for k in ("LLM_PROVIDER", "LLM_MODEL") if os.environ.get(k)]

    # 环境里存在但被本服务忽略的同名变量。提示出来避免用户以为它们生效了
    ignored = [
        k for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL",
                    "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL")
        if os.environ.get(k)
    ]
    return {
        "config_path": os.path.abspath(path),
        "config_file_exists": os.path.exists(path),
        "env_vars": env_keys,
        "ignored_env_vars": ignored,
    }
