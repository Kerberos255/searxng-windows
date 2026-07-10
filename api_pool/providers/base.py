"""Base provider interface and shared utilities."""

import httpx
from contextlib import contextmanager
from typing import Optional, Iterator

from .. import config


@contextmanager
def get_http_client() -> Iterator[httpx.Client]:
    """Context manager: create an httpx Client and ensure it is closed after use.

    Uses httpx's built-in environment proxy support (trust_env=True)
    so no explicit proxy URL is needed. The process env vars HTTP_PROXY,
    HTTPS_PROXY, NO_PROXY are read automatically.
    """
    client = httpx.Client(
        timeout=config.PROVIDER_REQUEST_TIMEOUT,
        follow_redirects=True,
        trust_env=True,
    )
    try:
        yield client
    finally:
        client.close()


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
