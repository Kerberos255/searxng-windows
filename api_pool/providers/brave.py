"""Brave Search API provider.

Uses the existing Brave Web Search API at:
https://api.search.brave.com/res/v1/web/search
"""

from typing import Optional
from urllib.parse import urlencode

import httpx

from .base import get_http_client, ProviderResult, make_result_item
from .. import config


BASE_URL = "https://api.search.brave.com/res/v1/web/search"


def search(
    query: str,
    pageno: int = 1,
    time_range: Optional[str] = None,
    safesearch: Optional[int] = None,
    max_results: int = 10,
) -> ProviderResult:
    """Call Brave Search API and return results.

    Args:
        query: Search query string.
        pageno: Page number (1-based).
        time_range: SearXNG time range string ("day", "week", "month", "year").
        safesearch: SearXNG safesearch level (0=off, 1=moderate, 2=strict).
        max_results: Results per page.

    Returns:
        ProviderResult with results or error information.
    """
    api_key = config.get_brave_key()
    if not api_key:
        return ProviderResult(
            success=False,
            error_category="misconfigured",
            is_misconfigured=True,
        )

    time_range_map = {
        "day": "past_day",
        "week": "past_week",
        "month": "past_month",
        "year": "past_year",
    }

    params = {
        "q": query,
        "count": max_results,
        "offset": (pageno - 1) * max_results,
    }
    if time_range and time_range in time_range_map:
        params["time_range"] = time_range_map[time_range]
    if safesearch:
        # 1=moderate, 2=strict; Brave only supports strict
        params["safesearch"] = "strict" if safesearch >= 2 else "moderate"

    try:
        with get_http_client() as client:
            url = f"{BASE_URL}?{urlencode(params)}"
            headers = {"X-Subscription-Token": api_key}
            resp = client.get(url, headers=headers)
        status = resp.status_code

        if status == 200:
            data = resp.json()
            results = []
            for item in data.get("web", {}).get("results", []):
                results.append(
                    make_result_item(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        content=item.get("description", ""),
                        published_date=item.get("age"),
                        score=item.get("score"),
                    )
                )
            return ProviderResult(success=True, results=results, http_status=200)

        elif status == 401:
            return ProviderResult(
                success=False,
                error_category="auth_failed",
                http_status=401,
                is_misconfigured=True,
            )
        elif status in (429,):
            return ProviderResult(
                success=False,
                error_category="rate_limited",
                http_status=429,
                retry_after=_get_retry_after(resp),
            )
        elif status in (402, 403):
            # Plan/usage limit
            return ProviderResult(
                success=False,
                error_category="quota_exhausted",
                http_status=status,
                is_quota=True,
                retry_after=_get_retry_after(resp),
            )
        else:
            return ProviderResult(
                success=False,
                error_category="http_error",
                http_status=status,
            )

    except httpx.TimeoutException:
        return ProviderResult(
            success=False,
            error_category="timeout",
        )
    except httpx.ConnectError:
        return ProviderResult(
            success=False,
            error_category="connection_error",
        )
    except Exception:
        return ProviderResult(
            success=False,
            error_category="unexpected_error",
        )


def _get_retry_after(resp) -> int | None:
    """Extract Retry-After header if present."""
    val = resp.headers.get("Retry-After")
    if val and val.isdigit():
        return int(val)
    return None
