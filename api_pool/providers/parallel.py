"""Parallel Search API provider.

Endpoint: POST https://api.parallel.ai/v1/search
Documentation: https://docs.parallel.ai/api-reference/search/search
"""

from typing import Optional

import httpx

from .base import get_http_client, ProviderResult, make_result_item
from .. import config


BASE_URL = "https://api.parallel.ai/v1/search"


def search(
    query: str,
    pageno: int = 1,
    time_range: Optional[str] = None,
    safesearch: Optional[int] = None,
    max_results: int = 10,
) -> ProviderResult:
    """Call Parallel Search API and return results.

    Args:
        query: Search query string.
        pageno: Unused (Parallel handles pagination differently).
        time_range: Unused.
        safesearch: Unused.
        max_results: Number of results requested.

    Returns:
        ProviderResult with results or error information.
    """
    api_key = config.get_parallel_key()
    if not api_key:
        return ProviderResult(
            success=False,
            error_category="misconfigured",
            is_misconfigured=True,
        )

    if pageno > 1:
        return ProviderResult(success=True, results=[], http_status=200)

    normalized_query = " ".join(query.split())
    search_query = normalized_query[:200]
    objective = normalized_query[:5000]
    freshness = {
        "day": " Prefer sources published within the past day.",
        "week": " Prefer sources published within the past week.",
        "month": " Prefer sources published within the past month.",
        "year": " Prefer sources published within the past year.",
    }.get(time_range, "")
    if freshness:
        objective = (objective[: 5000 - len(freshness)] + freshness).strip()

    payload = {
        "search_queries": [search_query],
        "objective": objective,
        "mode": "advanced",
        "advanced_settings": {
            "max_results": min(max(max_results, 1), 20),
        },
    }

    try:
        with get_http_client() as client:
            headers = {"x-api-key": api_key, "Content-Type": "application/json"}
            resp = client.post(BASE_URL, json=payload, headers=headers)
        status = resp.status_code

        if status == 200:
            data = resp.json()
            results_data = data.get("results", data.get("sources", data.get("data", [])))
            if isinstance(results_data, dict):
                # Some APIs nest results
                results_data = results_data.get("results", results_data.get("items", []))

            results = []
            for item in (results_data or []):
                if not isinstance(item, dict):
                    continue
                # Extract excerpts into content
                excerpts = item.get("excerpts", [])
                if isinstance(excerpts, list):
                    content = "\n".join(e for e in excerpts if isinstance(e, str))
                else:
                    content = str(excerpts) if excerpts else ""

                results.append(
                    make_result_item(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        content=content or item.get("snippet", ""),
                        published_date=item.get("publish_date") or item.get("published_date"),
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
        elif status == 429:
            return ProviderResult(
                success=False,
                error_category="rate_limited",
                http_status=429,
                retry_after=_get_retry_after(resp),
            )
        elif status in (402, 403):
            # Plan/usage limits
            return ProviderResult(
                success=False,
                error_category="quota_exhausted",
                http_status=status,
                is_quota=True,
            )
        else:
            # Check body for error context
            try:
                body = resp.json()
                err = (body.get("error") or body.get("message") or "").lower()
                if any(kw in err for kw in ("quota", "limit", "plan", "usage", "credit")):
                    return ProviderResult(
                        success=False,
                        error_category="quota_exhausted",
                        http_status=status,
                        is_quota=True,
                    )
                if any(kw in err for kw in ("auth", "key", "token")):
                    return ProviderResult(
                        success=False,
                        error_category="auth_failed",
                        http_status=status,
                        is_misconfigured=True,
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


def _get_retry_after(resp) -> int | None:
    val = resp.headers.get("Retry-After")
    if val and val.isdigit():
        return int(val)
    return None
