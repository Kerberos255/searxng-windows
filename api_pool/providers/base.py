"""Base provider interface and shared HTTP connection pools."""

import atexit
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import httpx

from .. import config


_CLIENT_LOCK = threading.Lock()
_CLIENTS: dict[bool, httpx.Client] = {}


def build_request_timeout(seconds: Optional[float]) -> Optional[httpx.Timeout]:
    """Build a per-request timeout with bounded connect and pool waits."""
    if seconds is None:
        return None
    bounded = max(0.05, float(seconds))
    return httpx.Timeout(
        bounded,
        connect=min(config.PROVIDER_CONNECT_TIMEOUT, bounded),
        pool=min(config.PROVIDER_POOL_TIMEOUT, bounded),
    )


def request_timeout_options(seconds: Optional[float]) -> dict:
    timeout = build_request_timeout(seconds)
    return {"timeout": timeout} if timeout is not None else {}


def _create_client(trust_env: bool) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(
            config.PROVIDER_REQUEST_TIMEOUT,
            connect=config.PROVIDER_CONNECT_TIMEOUT,
            pool=config.PROVIDER_POOL_TIMEOUT,
        ),
        follow_redirects=True,
        trust_env=trust_env,
        limits=httpx.Limits(
            max_connections=config.HTTP_MAX_CONNECTIONS,
            max_keepalive_connections=config.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            keepalive_expiry=config.HTTP_KEEPALIVE_EXPIRY,
        ),
    )


@contextmanager
def get_http_client(trust_env: bool = True) -> Iterator[httpx.Client]:
    """Borrow a shared client; httpx.Client is thread-safe and reuses keep-alive connections."""
    with _CLIENT_LOCK:
        client = _CLIENTS.get(trust_env)
        if client is None or client.is_closed:
            client = _create_client(trust_env)
            _CLIENTS[trust_env] = client
    yield client


def close_http_clients() -> None:
    """Close shared clients during process shutdown or test teardown."""
    with _CLIENT_LOCK:
        clients = list(_CLIENTS.values())
        _CLIENTS.clear()
    for client in clients:
        client.close()


atexit.register(close_http_clients)


class ProviderResult:
    """Result from a provider search call."""

    def __init__(
        self,
        success: bool,
        results: Optional[list[dict]] = None,
        error_category: Optional[str] = None,
        http_status: Optional[int] = None,
        is_quota: bool = False,
        is_misconfigured: bool = False,
        retry_after: Optional[int] = None,
    ):
        self.success = success
        self.results = results or []
        self.error_category = error_category
        self.http_status = http_status
        self.is_quota = is_quota
        self.is_misconfigured = is_misconfigured
        self.retry_after = retry_after


def make_result_item(
    url: str,
    title: str,
    content: str = "",
    published_date=None,
    score=None,
) -> dict:
    """Create a standardized result item dict."""
    return {
        "url": url,
        "title": title,
        "content": content,
        "published_date": published_date,
        "score": score,
    }
