"""Tavily Search API provider.

Endpoint: POST https://api.tavily.com/search
Documentation: https://docs.tavily.com/documentation/api-reference/endpoint/search
"""

from typing import Optional

import httpx

from .base import get_http_client, ProviderResult, make_result_item
from .. import config


BASE_URL = "https://api.tavily.com/search"


def search(
    query: str,
    pageno: int = 1,
    time_range: Optional[str] = None,
    date_after: Optional[str] = None,
    date_before: Optional[str] = None,
    safesearch: Optional[int] = None,
    max_results: int = 10,
) -> ProviderResult:
    """Call Tavily Search API and return results.

    Args:
        query: Search query string.
        pageno: Unused (Tavily does not support pagination in basic mode).
        time_range: Relative range (day/week/month/year).
        date_after: Exact inclusive start date in YYYY-MM-DD format.
        date_before: Exact inclusive end date in YYYY-MM-DD format.
        safesearch: Unused.
        max_results: Number of results (max_results parameter).

    Returns:
        ProviderResult with results or error information.
    """
    api_key = config.get_tavily_key()
    if not api_key:
        return ProviderResult(
            success=False,
            error_category="misconfigured",
            is_misconfigured=True,
        )

    if pageno > 1:
        return ProviderResult(success=True, results=[], http_status=200)

    payload = {
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": min(max_results, 20),
    }
    if date_after:
        payload["start_date"] = date_after
    if date_before:
        payload["end_date"] = date_before
    if time_range and not date_after and not date_before:
        payload["time_range"] = time_range
    if safesearch:
        payload["safe_search"] = True

    try:
        with get_http_client() as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            resp = client.post(BASE_URL, json=payload, headers=headers)
        status = resp.status_code

        if status == 200:
            data = resp.json()
            results = []
            for item in data.get("results", []):
                results.append(
                    make_result_item(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        content=item.get("content", ""),
                        published_date=item.get("published_date")
                        or item.get("publishedDate"),
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
        elif status in (432, 433):
            # Tavily specific: plan/usage limit
            return ProviderResult(
                success=False,
                error_category="quota_exhausted",
                http_status=status,
                is_quota=True,
                retry_after=_extract_retry(resp),
            )
        elif status == 429:
            return ProviderResult(
                success=False,
                error_category="rate_limited",
                http_status=429,
                retry_after=_extract_retry(resp),
            )
        elif status in (402, 403):
            return ProviderResult(
                success=False,
                error_category="quota_exhausted",
                http_status=status,
                is_quota=True,
                retry_after=_extract_retry(resp),
            )
        else:
            # Check response body for plan/usage limit hints
            try:
                body = resp.json()
                err = (body.get("error") or body.get("message") or "").lower()
                if any(kw in err for kw in ("plan", "limit", "usage", "quota")):
                    return ProviderResult(
                        success=False,
                        error_category="quota_exhausted",
                        http_status=status,
                        is_quota=True,
                    )
            except Exception:
                pass
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


def _extract_retry(resp) -> int | None:
    """Extract Retry-After header or reset time from body."""
    val = resp.headers.get("Retry-After")
    if val and val.isdigit():
        return int(val)
    # Tavily might return reset time in body
    try:
        body = resp.json()
        if "reset" in body:
            return body["reset"]
    except Exception:
        pass
    return None
