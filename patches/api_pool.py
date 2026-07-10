# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine to search using the local API Pool Broker.

The Broker (api_pool/app.py) manages Brave / Firecrawl / Tavily / Parallel API calls
with automatic failover and quota tracking.
"""

from datetime import datetime, timezone
from typing import Optional

from searx.result_types import EngineResults

about = {
    "website": "https://github.com/Kerberos255/searxng-windows",
    "wikidata_id": None,
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": "JSON",
}

categories = ["general", "web"]
paging = True
time_range_support = True
safesearch = True

# Local Broker URL
broker_url = "http://127.0.0.1:8890/search"

# Max results per page
max_results: int = 10

# Broker timeout
timeout: int = 20


def request(query: str, params) -> None:
    """Create a POST request to the local Broker."""
    payload = {
        "query": query,
        "pageno": params.get("pageno", 1),
        "max_results": max_results,
        "fallback_on_empty": False,
    }

    if params.get("time_range"):
        payload["time_range"] = params["time_range"]

    if params.get("safesearch", 0) > 0:
        payload["safesearch"] = params["safesearch"]

    params["url"] = broker_url
    params["method"] = "POST"
    params["headers"]["Content-Type"] = "application/json"
    params["json"] = payload
    params["timeout"] = timeout


def _parse_published_date(value):
    """Convert Broker ISO date strings to the datetime SearXNG expects."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def response(resp) -> EngineResults:
    """Process Broker JSON response and return results."""
    res = EngineResults()
    data = resp.json()

    results = data.get("results", [])

    for item in results:
        res.add(
            res.types.MainResult(
                url=item.get("url", ""),
                title=item.get("title", ""),
                content=item.get("content", ""),
                publishedDate=_parse_published_date(item.get("published_date")),
                score=item.get("score"),
            ),
        )

    return res
