# SPDX-License-Identifier: AGPL-3.0-or-later
"""Engine to search using the local API Pool Broker.

The Broker (api_pool/app.py) manages Brave / Firecrawl / Tavily / Parallel API calls
with automatic failover and quota tracking.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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
        "fallback_on_empty": True,
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
    """Convert ISO or RFC 2822 dates to SearXNG-compatible datetimes."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(normalized)
        except (TypeError, ValueError, IndexError):
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


# Default web searches use the API Pool only if at least one API is configured.
# Explicit engine/bang choices, as well as non-web categories, are unchanged.
def _broker_has_configured_providers() -> bool:
    import json
    from urllib.parse import urlsplit, urlunsplit
    from urllib.request import ProxyHandler, build_opener

    endpoint = urlsplit(broker_url)
    if endpoint.scheme != "http" or endpoint.hostname not in ("localhost", "127.0.0.1", "::1"):
        return False
    status_url = urlunsplit((endpoint.scheme, endpoint.netloc, "/status", "", ""))
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(status_url, timeout=0.35) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(65536))
        return isinstance(payload, dict) and any(
            provider.get("configured") is True
            for provider in payload.get("providers", ())
            if isinstance(provider, dict)
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def apply_default_search_priority(search_query, raw_text_query, form) -> None:
    """Prefer API Pool in default general/web searches; otherwise use free engines.

    Manual !bang and engines= selection must continue to behave as requested.
    """
    if form.get("engines") or raw_text_query.specific:
        return
    selected_categories = set(search_query.categories)
    if not selected_categories or not selected_categories <= {"general", "web"}:
        return

    pool = [ref for ref in search_query.engineref_list if ref.name == "api pool"]
    if not pool:
        return  # API Pool disabled by settings or the user's preferences.

    if _broker_has_configured_providers():
        search_query.engineref_list = pool
    else:
        # Don't make an API request when no API credentials are configured.
        search_query.engineref_list = [
            ref for ref in search_query.engineref_list if ref.name != "api pool"
        ]
