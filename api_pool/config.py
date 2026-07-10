"""Public API Pool configuration.

Loads optional API keys from process environment first, then from an env file.
The default env file is ``<install-root>/config/api-pool.env`` and can be
overridden with ``API_POOL_ENV_FILE``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = ROOT_DIR / "config" / "api-pool.env"
ENV_FILE = Path(os.environ.get("API_POOL_ENV_FILE", str(DEFAULT_ENV_FILE))).expanduser()

_PROVIDER_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "brave": ("BRAVE_API_KEY", "OPENCLAW_BRAVE_API_KEY"),
    "firecrawl": ("FIRECRAWL_API_KEY",),
    "tavily": ("TAVILY_API_KEY",),
    "parallel": ("PARALLEL_API_KEY",),
}
SUPPORTED_PROVIDERS = tuple(_PROVIDER_KEY_ALIASES)
DEFAULT_PRIORITY = ["parallel", "tavily", "brave", "firecrawl"]


def _load_env_file() -> dict[str, str]:
    result: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return result
    for raw_line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            continue
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[match.group(1)] = value
    return result


def _get_api_key(provider: str) -> str | None:
    file_values = _load_env_file()
    for variable in _PROVIDER_KEY_ALIASES.get(provider, ()):
        value = os.environ.get(variable)
        if value is None:
            value = file_values.get(variable, "")
        value = value.strip()
        if value and value != "***":
            return value
    return None


def get_brave_key() -> str | None:
    return _get_api_key("brave")


def get_firecrawl_key() -> str | None:
    return _get_api_key("firecrawl")


def get_tavily_key() -> str | None:
    return _get_api_key("tavily")


def get_parallel_key() -> str | None:
    return _get_api_key("parallel")


def is_provider_configured(provider: str) -> bool:
    return _get_api_key(provider) is not None


def get_configured_providers() -> dict[str, bool]:
    return {provider: is_provider_configured(provider) for provider in SUPPORTED_PROVIDERS}


def get_priority() -> list[str]:
    raw = os.environ.get("API_POOL_PRIORITY") or _load_env_file().get("API_POOL_PRIORITY", "")
    if not raw.strip():
        return list(DEFAULT_PRIORITY)
    requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
    result: list[str] = []
    for provider in requested:
        if provider in SUPPORTED_PROVIDERS and provider not in result:
            result.append(provider)
    for provider in DEFAULT_PRIORITY:
        if provider not in result:
            result.append(provider)
    return result


DB_DIR = ROOT_DIR / "api_pool" / "data"
DB_PATH = DB_DIR / "api_pool.sqlite"
BROKER_HOST = os.environ.get("API_POOL_HOST", "127.0.0.1")
BROKER_PORT = int(os.environ.get("API_POOL_PORT", "8890"))
COOLDOWN_BASE_SECONDS = int(os.environ.get("API_POOL_COOLDOWN_SECONDS", "120"))
QUOTA_PROBE_INTERVAL_SECONDS = int(os.environ.get("API_POOL_QUOTA_PROBE_SECONDS", "86400"))
MAX_CONSECUTIVE_FAILURES = 5
PROVIDER_REQUEST_TIMEOUT = float(os.environ.get("API_POOL_PROVIDER_TIMEOUT", "15"))

SEARXNG_BACKEND_URL = os.environ.get(
    "SEARXNG_BACKEND_URL", "http://127.0.0.1:8888"
).rstrip("/")
_configured_free_engines = tuple(
    engine.strip()
    for engine in os.environ.get(
        "SEARXNG_FREE_ENGINES", "bing,sogou,qwant,mojeek"
    ).split(",")
    if engine.strip() and engine.strip().lower() not in ("api pool", "api_pool")
)
SEARXNG_FREE_ENGINES = _configured_free_engines or (
    "bing",
    "sogou",
    "qwant",
    "mojeek",
)
SEARXNG_FREE_FALLBACK = os.environ.get(
    "SEARXNG_FREE_FALLBACK", "true"
).strip().lower() in ("1", "true", "yes", "on")
SEARXNG_FALLBACK_TIMEOUT = float(
    os.environ.get("SEARXNG_FALLBACK_TIMEOUT", "20")
)
