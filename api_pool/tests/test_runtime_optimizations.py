import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from api_pool import app as broker_app
from api_pool import config, state
from api_pool.providers.base import (
    build_request_timeout,
    close_http_clients,
    get_http_client,
)
from api_pool.providers.base import ProviderResult


class TestSharedHttpClients(unittest.TestCase):
    def tearDown(self):
        close_http_clients()

    def test_clients_are_reused_and_proxy_modes_are_isolated(self):
        with get_http_client() as provider_client:
            with get_http_client() as reused_client:
                self.assertIs(provider_client, reused_client)

        with get_http_client(trust_env=False) as local_client:
            self.assertIsNot(provider_client, local_client)

    def test_request_timeout_bounds_connect_and_pool_waits(self):
        timeout = build_request_timeout(2.5)
        self.assertIsInstance(timeout, httpx.Timeout)
        self.assertEqual(timeout.connect, 2.5)
        self.assertEqual(timeout.pool, 2.0)
        self.assertEqual(timeout.read, 2.5)


class TestQueryRedaction(unittest.TestCase):
    def test_query_values_are_removed_from_diagnostic_messages(self):
        record = logging.makeLogRecord(
            {
                "msg": 'GET /search?q=private-search-term&count=5 HTTP/1.1',
                "args": (),
            }
        )

        self.assertTrue(broker_app.QueryRedactionFilter().filter(record))
        message = record.getMessage()
        self.assertNotIn("private-search-term", message)
        self.assertIn("/search?[REDACTED]", message)


class TestRequestBudgets(unittest.TestCase):
    def setUp(self):
        self.client = broker_app.app.test_client()

    def test_gateway_reserves_time_for_free_fallback(self):
        api_result = {"provider": None, "results": [], "attempts": []}
        fallback_result = {
            "provider": "searxng_free",
            "results": [{"url": "https://example.test", "title": "Example"}],
            "fallback_used": True,
        }

        with (
            patch.object(config, "API_POOL_GATEWAY_TIMEOUT", 27),
            patch.object(config, "SEARXNG_FALLBACK_RESERVE", 10),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.app._run_api_search", return_value=api_result) as api_search,
            patch("api_pool.app._run_free_search", return_value=fallback_result) as free_search,
        ):
            response = self.client.get("/search?q=budget-test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_search.call_args.kwargs["deadline"], 117)
        self.assertEqual(free_search.call_args.kwargs["deadline"], 127)

    def test_engine_post_uses_shorter_budget_and_does_not_run_gateway_fallback(self):
        api_result = {"provider": None, "results": [], "attempts": []}

        with (
            patch.object(config, "API_POOL_ENGINE_TIMEOUT", 17),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.app._run_api_search", return_value=api_result) as api_search,
            patch("api_pool.app._run_free_search") as free_search,
        ):
            response = self.client.post(
                "/search",
                json={"query": "budget-test", "fallback_on_empty": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_search.call_args.kwargs["deadline"], 117)
        free_search.assert_not_called()

    def test_expired_provider_budget_skips_upstream_call(self):
        search_input = {
            "query": "budget-test",
            "pageno": 1,
            "time_range": None,
            "date_after": None,
            "date_before": None,
            "safesearch": 0,
            "max_results": 10,
            "fallback_on_empty": True,
        }
        with (
            patch("api_pool.app._get_priority", return_value=["brave"]),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.providers.brave.search") as brave_search,
        ):
            result = broker_app._run_api_search(search_input, deadline=99)

        self.assertEqual(result["attempts"][0]["outcome"], "request_budget_exhausted")
        brave_search.assert_not_called()

    def test_provider_receives_only_remaining_request_time(self):
        search_input = {
            "query": "budget-test",
            "pageno": 1,
            "time_range": None,
            "date_after": None,
            "date_before": None,
            "safesearch": 0,
            "max_results": 10,
            "fallback_on_empty": True,
        }
        with (
            patch("api_pool.app._get_priority", return_value=["brave"]),
            patch.object(config, "is_provider_configured", return_value=True),
            patch.object(state, "set_configured"),
            patch.object(state, "get_provider_state", return_value={"status": state.STATUS_AVAILABLE}),
            patch.object(state, "record_success"),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.providers.brave.search", return_value=ProviderResult(
                success=True, results=[{"url": "https://example.test", "title": "Example"}]
            )) as brave_search,
        ):
            broker_app._run_api_search(search_input, deadline=104.25)

        self.assertEqual(brave_search.call_args.kwargs["timeout"], 4.25)


class TestEnvFileCache(unittest.TestCase):
    def test_env_file_cache_refreshes_after_file_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / "api-pool.env"
            env_file.write_text("CACHE_TEST=first\n", encoding="utf-8")

            with patch.object(config, "ENV_FILE", env_file):
                self.assertEqual(config._load_env_file()["CACHE_TEST"], "first")
                env_file.write_text("CACHE_TEST=second-value\n", encoding="utf-8")
                self.assertEqual(config._load_env_file()["CACHE_TEST"], "second-value")


if __name__ == "__main__":
    unittest.main()
