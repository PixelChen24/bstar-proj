"""LLM 后端配置：本地配置文件 + 环境变量

优先级：配置文件 > 环境变量 > 内置默认值。

支持的环境变量：
  LLM_PROVIDER     — 后端选择（openai / anthropic）
  LLM_MODEL        — 模型名（作用于当前 provider）
  BSTAR_KEY        — API Key（作用于当前 provider）
  BSTAR_MODEL      — 模型名，优先级高于 LLM_MODEL
  BSTAR_BASE_URL   — 接口地址（作用于当前 provider）

配置文件（./config/llm.json，权限 0600）可手动写入，优先级最高。
"""

import json
import os

PROVIDERS = ("openai", "anthropic")

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"


def config_path() -> str:
    return os.environ.get("LLM_CONFIG_PATH", "./config/llm.json")


def _defaults() -> dict:
    return {
        "provider": "anthropic",
        "openai": {"model": "", "api_key": "", "base_url": ""},
        "anthropic": {"model": DEFAULT_ANTHROPIC_MODEL, "api_key": "", "base_url": ""},
    }


def from_env() -> dict:
    """从环境变量构建配置。"""
    cfg = _defaults()

    provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if provider in PROVIDERS:
        cfg["provider"] = provider

    if os.environ.get("LLM_MODEL"):
        cfg[cfg["provider"]]["model"] = os.environ["LLM_MODEL"]

    target = cfg["provider"]
    if os.environ.get("BSTAR_KEY"):
        cfg[target]["api_key"] = os.environ["BSTAR_KEY"]
    if os.environ.get("BSTAR_MODEL"):
        cfg[target]["model"] = os.environ["BSTAR_MODEL"]
    if os.environ.get("BSTAR_BASE_URL"):
        cfg[target]["base_url"] = os.environ["BSTAR_BASE_URL"]

    return cfg


def _merge(base: dict, patch: dict) -> dict:
    """两层深合并，空值不覆盖已有值。"""
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
            if not value:
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

    target = (provider or cfg.get("provider") or "anthropic").strip().lower()
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
