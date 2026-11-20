"""Validate installed web search priority without calling real API providers."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
os.environ["SEARXNG_SETTINGS_PATH"] = str(root / "config" / "settings.yml")
sys.path.insert(0, str(root / "searxng"))

from searx import webapp  # noqa: E402
from searx.engines import api_pool  # noqa: E402
from searx.results import ResultContainer  # noqa: E402
from searx.search import SearchWithPlugins  # noqa: E402

seen = []


def fake_search(self):
    seen.append([ref.name for ref in self.search_query.engineref_list])
    return ResultContainer()


client = webapp.app.test_client()

with patch.object(SearchWithPlugins, "search", fake_search):
    for has_api in (True, False):
        with patch.object(api_pool, "_broker_has_configured_providers", return_value=has_api):
            response = client.get("/search?q=priority-smoke&format=json")
            if response.status_code != 200:
                raise SystemExit("Search request failed during route validation")
            expected = ["api pool"] if has_api else None
            if has_api and seen[-1] != expected:
                raise SystemExit("Configured API was not selected exclusively")
            if not has_api and ("api pool" in seen[-1] or not seen[-1]):
                raise SystemExit("No-key search did not directly select free engines")

    with patch.object(api_pool, "_broker_has_configured_providers", side_effect=AssertionError("Manual selection must not call broker status")):
        response = client.get("/search?q=priority-smoke&engines=bing&format=json")
        if response.status_code != 200 or seen[-1] != ["bing"]:
            raise SystemExit("Explicit Bing selection was overridden")

print("PASS configured API priority, no-key free search and manual Bing selection")
