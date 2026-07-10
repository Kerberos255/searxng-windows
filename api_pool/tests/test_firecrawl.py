"""Firecrawl provider and four-provider API Pool tests."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))

from api_pool import app as broker_app
from api_pool import config, state
from api_pool.providers.base import ProviderResult


class FirecrawlBrokerBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        broker_app.app.testing = True
        cls.client = broker_app.app.test_client()
        cls._tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls._tmp_db.close()
        cls._old_db_path = config.DB_PATH
        config.DB_PATH = cls._tmp_db.name

    @classmethod
    def tearDownClass(cls):
        state.close_all()
        config.DB_PATH = cls._old_db_path
        try:
            os.unlink(cls._tmp_db.name)
        except (FileNotFoundError, PermissionError):
            pass

    def setUp(self):
        state.close_all()
        state.init_db()
        self.patchers = [
            patch.object(config, "DEFAULT_PRIORITY", ["brave", "firecrawl", "tavily", "parallel"]),
            patch("api_pool.config.is_provider_configured", return_value=True),
            patch("api_pool.config.get_brave_key", return_value="test-key"),
            patch("api_pool.config.get_firecrawl_key", return_value="test-key"),
            patch("api_pool.config.get_tavily_key", return_value="test-key"),
            patch("api_pool.config.get_parallel_key", return_value="test-key"),
        ]
        for patcher in self.patchers:
            patcher.start()
        for provider in ["brave", "firecrawl", "tavily", "parallel"]:
            state.set_configured(provider, True)
            state.record_success(provider)

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        state.close_all()

    def search(self, **kwargs):
        payload = {"query": "test query", **kwargs}
        return self.client.post(
            "/search",
            data=json.dumps(payload),
            content_type="application/json",
        )


class TestFourProviderOrder(FirecrawlBrokerBase):
    def test_status_order(self):
        response = self.client.get("/status")
        data = response.get_json()
        self.assertEqual(
            data["priority_order"],
            ["brave", "firecrawl", "tavily", "parallel"],
        )
        self.assertNotIn("test-key", response.get_data(as_text=True))

    @patch("api_pool.providers.parallel.search")
    @patch("api_pool.providers.tavily.search")
    @patch("api_pool.providers.firecrawl.search")
    @patch("api_pool.providers.brave.search")
    def test_brave_success_does_not_call_firecrawl(
        self, mock_brave, mock_firecrawl, mock_tavily, mock_parallel
    ):
        mock_brave.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://brave.example", "title": "B"}],
            http_status=200,
        )
        data = self.search().get_json()
        self.assertEqual(data["provider"], "brave")
        mock_firecrawl.assert_not_called()
        mock_tavily.assert_not_called()
        mock_parallel.assert_not_called()

    @patch("api_pool.providers.firecrawl.search")
    @patch("api_pool.providers.brave.search")
    def test_brave_quota_falls_to_firecrawl(self, mock_brave, mock_firecrawl):
        mock_brave.return_value = ProviderResult(
            success=False,
            error_category="quota_exhausted",
            http_status=402,
            is_quota=True,
        )
        mock_firecrawl.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://firecrawl.example", "title": "F"}],
            http_status=200,
        )
        data = self.search().get_json()
        self.assertEqual(data["provider"], "firecrawl")
        self.assertEqual(
            [item["outcome"] for item in data["attempts"]],
            ["quota_exhausted", "success"],
        )

    @patch("api_pool.providers.tavily.search")
    @patch("api_pool.providers.firecrawl.search")
    @patch("api_pool.providers.brave.search")
    def test_brave_and_firecrawl_quota_fall_to_tavily(
        self, mock_brave, mock_firecrawl, mock_tavily
    ):
        quota = ProviderResult(
            success=False,
            error_category="quota_exhausted",
            http_status=402,
            is_quota=True,
        )
        mock_brave.return_value = quota
        mock_firecrawl.return_value = quota
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T"}],
            http_status=200,
        )
        data = self.search().get_json()
        self.assertEqual(data["provider"], "tavily")
        self.assertEqual(
            [item["outcome"] for item in data["attempts"]],
            ["quota_exhausted", "quota_exhausted", "success"],
        )


class TestFirecrawlProvider(FirecrawlBrokerBase):
    @patch("api_pool.providers.firecrawl.get_http_client")
    def test_bearer_body_and_result_mapping(self, mock_get_client):
        captured = {}

        def handler(request):
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.read())
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "web": [
                            {
                                "title": "Firecrawl Result",
                                "description": "Useful description",
                                "url": "https://example.com/page",
                                "metadata": {"publishedTime": "2026-07-10"},
                            },
                            {"title": "Missing URL"},
                        ]
                    },
                    "creditsUsed": 2,
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        cm = MagicMock()
        cm.__enter__.return_value = client
        mock_get_client.return_value = cm

        from api_pool.providers.firecrawl import search

        result = search(query="hello", time_range="week", max_results=5)
        self.assertTrue(result.success)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["title"], "Firecrawl Result")
        self.assertEqual(result.results[0]["published_date"], "2026-07-10")
        self.assertEqual(captured["headers"]["authorization"], "Bearer test-key")
        self.assertEqual(captured["body"]["sources"], ["web"])
        self.assertEqual(captured["body"]["limit"], 5)
        self.assertEqual(captured["body"]["tbs"], "qdr:w")
        self.assertNotIn("api_key", captured["body"])
        self.assertNotIn("scrapeOptions", captured["body"])

    @patch("api_pool.providers.firecrawl.get_http_client")
    def test_error_classification(self, mock_get_client):
        from api_pool.providers.firecrawl import search

        cases = [
            (401, {"error": "Unauthorized"}, "auth_failed", False, True),
            (402, {"error": "Insufficient credits"}, "quota_exhausted", True, False),
            (429, {"error": "Too many requests"}, "rate_limited", False, False),
            (408, {"error": "Request timed out"}, "timeout", False, False),
            (503, {"error": "Unavailable"}, "http_error", False, False),
        ]
        for status, body, category, is_quota, is_misconfigured in cases:
            with self.subTest(status=status):
                client = MagicMock()
                response = httpx.Response(
                    status,
                    json=body,
                    headers={"Retry-After": "60"},
                    request=httpx.Request("POST", "https://api.firecrawl.dev/v2/search"),
                )
                client.post.return_value = response
                cm = MagicMock()
                cm.__enter__.return_value = client
                mock_get_client.return_value = cm
                result = search(query="test")
                self.assertFalse(result.success)
                self.assertEqual(result.error_category, category)
                self.assertEqual(result.is_quota, is_quota)
                self.assertEqual(result.is_misconfigured, is_misconfigured)

    @patch("api_pool.providers.firecrawl.get_http_client")
    def test_timeout_and_connect_errors(self, mock_get_client):
        from api_pool.providers.firecrawl import search

        for exception, category in [
            (httpx.TimeoutException("timeout"), "timeout"),
            (httpx.ConnectError("connect"), "connection_error"),
        ]:
            with self.subTest(category=category):
                client = MagicMock()
                client.post.side_effect = exception
                cm = MagicMock()
                cm.__enter__.return_value = client
                mock_get_client.return_value = cm
                result = search(query="test")
                self.assertFalse(result.success)
                self.assertEqual(result.error_category, category)

    def test_later_page_returns_empty_without_request(self):
        from api_pool.providers.firecrawl import search

        with patch("api_pool.providers.firecrawl.get_http_client") as mock_client:
            result = search(query="test", pageno=2)
        self.assertTrue(result.success)
        self.assertEqual(result.results, [])
        mock_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
