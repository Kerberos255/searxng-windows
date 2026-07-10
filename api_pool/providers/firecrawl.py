"""Firecrawl v2 Search API provider."""

from typing import Optional

import httpx

from .base import ProviderResult, get_http_client, make_result_item
from .. import config


BASE_URL = "https://api.firecrawl.dev/v2/search"


def search(
    query: str,
    pageno: int = 1,
    time_range: Optional[str] = None,
    safesearch: Optional[int] = None,
    max_results: int = 10,
) -> ProviderResult:
    """Search Firecrawl without enabling page scraping.

    Firecrawl Search does not expose a stable page/offset parameter. Requests for
    pages after the first therefore return a successful empty result rather than
    repeating page one and wasting credits.
    """
    del safesearch  # Firecrawl Search currently has no equivalent parameter.

    api_key = config.get_firecrawl_key()
    if not api_key:
        return ProviderResult(
            success=False,
            error_category="misconfigured",
            is_misconfigured=True,
        )

    if pageno > 1:
        return ProviderResult(success=True, results=[], http_status=200)

    payload: dict = {
        "query": query,
        "limit": max_results,
        "sources": ["web"],
    }
    time_range_map = {
        "day": "qdr:d",
        "week": "qdr:w",
        "month": "qdr:m",
        "year": "qdr:y",
    }
    if time_range in time_range_map:
        payload["tbs"] = time_range_map[time_range]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        with get_http_client() as client:
            response = client.post(BASE_URL, headers=headers, json=payload)
        status = response.status_code

        if status == 200:
            data = _safe_json(response)
            if data.get("success") is False:
                return _classify_api_error(status, data, response)

            results = []
            web_results = data.get("data", {}).get("web", [])
            if not isinstance(web_results, list):
                web_results = []

            for item in web_results:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url:
                    continue
                metadata = item.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                title = str(item.get("title") or metadata.get("title") or url).strip()
                content = str(
                    item.get("description")
                    or metadata.get("description")
                    or ""
                ).strip()
                published_date = (
                    item.get("date")
                    or metadata.get("publishedTime")
                    or metadata.get("publishedDate")
                    or metadata.get("date")
                )
                results.append(
                    make_result_item(
                        url=url,
                        title=title,
                        content=content,
                        published_date=published_date,
                        score=item.get("score"),
                    )
                )
            return ProviderResult(success=True, results=results, http_status=200)

        return _classify_api_error(status, _safe_json(response), response)

    except httpx.TimeoutException:
        return ProviderResult(success=False, error_category="timeout")
    except httpx.ConnectError:
        return ProviderResult(success=False, error_category="connection_error")
    except Exception:
        return ProviderResult(success=False, error_category="unexpected_error")


def _safe_json(response) -> dict:
    try:
        value = response.json()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _classify_api_error(status: int, data: dict, response) -> ProviderResult:
    retry_after = _get_retry_after(response)
    error_text = _safe_error_text(data)

    if status == 401:
        return ProviderResult(
            success=False,
            error_category="auth_failed",
            http_status=status,
            is_misconfigured=True,
        )
    if status == 429:
        return ProviderResult(
            success=False,
            error_category="rate_limited",
            http_status=status,
            retry_after=retry_after,
        )
    if status == 408:
        return ProviderResult(
            success=False,
            error_category="timeout",
            http_status=status,
            retry_after=retry_after,
        )

    quota_markers = (
        "insufficient credit",
        "insufficient credits",
        "credit limit",
        "credits exhausted",
        "payment required",
        "plan limit",
        "usage limit",
        "quota",
    )
    auth_markers = ("invalid api key", "unauthorized", "authentication")

    if status == 402 or any(marker in error_text for marker in quota_markers):
        return ProviderResult(
            success=False,
            error_category="quota_exhausted",
            http_status=status,
            is_quota=True,
            retry_after=retry_after,
        )
    if status == 403 and any(marker in error_text for marker in auth_markers):
        return ProviderResult(
            success=False,
            error_category="auth_failed",
            http_status=status,
            is_misconfigured=True,
        )
    if status >= 500:
        return ProviderResult(
            success=False,
            error_category="http_error",
            http_status=status,
            retry_after=retry_after,
        )
    return ProviderResult(
        success=False,
        error_category="http_error",
        http_status=status,
        retry_after=retry_after,
    )


def _safe_error_text(data: dict) -> str:
    values = [data.get("code"), data.get("error"), data.get("message")]
    detail = data.get("detail")
    if isinstance(detail, dict):
        values.extend([detail.get("code"), detail.get("error"), detail.get("message")])
    elif isinstance(detail, str):
        values.append(detail)
    return " ".join(str(value) for value in values if value).lower()[:500]


def _get_retry_after(response) -> int | None:
    value = response.headers.get("Retry-After")
    if value and value.isdigit():
        return int(value)
    return None
