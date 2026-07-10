"""Parallel Search API request schema and priority tests."""

import json
import unittest
from unittest.mock import MagicMock, patch

import httpx

from api_pool import config
from api_pool.providers.parallel import search


class TestParallelProvider(unittest.TestCase):
    @patch("api_pool.providers.parallel.config.get_parallel_key", return_value="test-key")
    @patch("api_pool.providers.parallel.get_http_client")
    def test_advanced_request_schema_and_result_mapping(self, mock_get_client, _mock_key):
        captured = {}

        def handler(request):
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.read())
            return httpx.Response(
                200,
                json={
                    "search_id": "search-test",
                    "session_id": "session-test",
                    "results": [
                        {
                            "url": "https://example.com/result",
                            "title": "Parallel Result",
                            "publish_date": "2026-07-10",
                            "excerpts": ["First excerpt.", "Second excerpt."],
                        }
                    ],
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cm = MagicMock()
        cm.__enter__.return_value = client
        mock_get_client.return_value = cm

        result = search(
            query="latest vector database benchmarks",
            time_range="month",
            max_results=7,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.results[0]["title"], "Parallel Result")
        self.assertEqual(result.results[0]["published_date"], "2026-07-10")
        self.assertEqual(result.results[0]["content"], "First excerpt.\nSecond excerpt.")
        self.assertEqual(captured["headers"]["x-api-key"], "test-key")
        self.assertEqual(captured["body"]["mode"], "advanced")
        self.assertEqual(
            captured["body"]["search_queries"],
            ["latest vector database benchmarks"],
        )
        self.assertIn("past month", captured["body"]["objective"])
        self.assertEqual(
            captured["body"]["advanced_settings"],
            {"max_results": 7},
        )
        self.assertNotIn("max_results", captured["body"])

    @patch("api_pool.providers.parallel.config.get_parallel_key", return_value="test-key")
    @patch("api_pool.providers.parallel.get_http_client")
    def test_later_page_returns_empty_without_request(self, mock_get_client, _mock_key):
        result = search(query="test", pageno=2)
        self.assertTrue(result.success)
        self.assertEqual(result.results, [])
        mock_get_client.assert_not_called()

    def test_quality_first_default_priority(self):
        self.assertEqual(
            config.DEFAULT_PRIORITY,
            ["parallel", "tavily", "brave", "firecrawl"],
        )


if __name__ == "__main__":
    unittest.main()
