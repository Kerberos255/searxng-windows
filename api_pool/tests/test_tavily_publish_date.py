"""Date-limited Tavily requests ask for publication metadata without strict exclusion."""
import json
from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import patch
import httpx

from api_pool.providers import tavily


class TestTavilyPublishedDate(TestCase):
    def _request(self, **kwargs):
        captured = []
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={"results": [
                {"url": "https://example.org/a", "title": "A", "content": "hello",
                 "published_date": "2026-11-05T00:00:00Z"}
            ]})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.object(tavily.config, "get_tavily_key", return_value="test-only"), \
             patch.object(tavily, "get_http_client", return_value=nullcontext(client)):
            result = tavily.search(query="test", **kwargs)
        client.close()
        self.assertTrue(result.success)
        self.assertEqual(result.results[0]["published_date"], "2026-11-05T00:00:00Z")
        return captured[0]

    def test_relative_date_requests_metadata_without_strict_filter(self):
        payload = self._request(time_range="week")
        self.assertEqual(payload["time_range"], "week")
        self.assertIs(payload["include_published_date"], True)
        self.assertNotIn("filter_by_published_date", payload)

    def test_exact_date_requests_metadata_without_strict_filter(self):
        payload = self._request(date_after="2026-11-01", date_before="2026-11-06")
        self.assertIs(payload["include_published_date"], True)
        self.assertNotIn("time_range", payload)
        self.assertNotIn("filter_by_published_date", payload)

    def test_normal_request_remains_unchanged(self):
        payload = self._request()
        self.assertNotIn("include_published_date", payload)
        self.assertNotIn("filter_by_published_date", payload)
