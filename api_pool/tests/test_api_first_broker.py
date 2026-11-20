"""Broker routing contracts for default API-first web search.

All API calls are mocked; these tests never spend third-party API credits.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from api_pool import app as broker
from api_pool import config


class TestApiFirstBroker(unittest.TestCase):
    def setUp(self):
        self.client = broker.app.test_client()

    def test_post_empty_api_reserves_short_free_fallback(self):
        api_result = {"provider": None, "results": [], "attempts": []}
        free_result = {
            "provider": "searxng_free",
            "fallback_used": True,
            "results": [{"url": "https://example.test", "title": "Free"}],
        }
        with (
            patch.object(config, "API_POOL_ENGINE_TIMEOUT", 17),
            patch.object(config, "API_POOL_ENGINE_FALLBACK_RESERVE", 5),
            patch.object(config, "SEARXNG_FREE_FALLBACK", True),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.app._run_api_search", return_value=api_result) as api,
            patch("api_pool.app._run_free_search", return_value=free_result) as free,
        ):
            r = self.client.post("/search", json={"query": "demo", "fallback_on_empty": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(api.call_args.kwargs["deadline"], 112)
        self.assertEqual(free.call_args.kwargs["deadline"], 117)
        self.assertEqual(r.json["provider"], "searxng_free")

    def test_post_explicit_no_fallback_preserves_old_contract(self):
        api_result = {"provider": "brave", "results": [], "attempts": []}
        with (
            patch.object(config, "API_POOL_ENGINE_TIMEOUT", 17),
            patch("api_pool.app.time.monotonic", return_value=100),
            patch("api_pool.app._run_api_search", return_value=api_result) as api,
            patch("api_pool.app._run_free_search") as free,
        ):
            r = self.client.post("/search", json={"query": "demo", "fallback_on_empty": False})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(api.call_args.kwargs["deadline"], 117)
        self.assertEqual(r.json["provider"], "brave")
        free.assert_not_called()

    def test_post_api_success_does_not_use_free(self):
        api_result = {"provider": "tavily", "results": [{"url": "https://example.test"}], "attempts": []}
        with (
            patch("api_pool.app._run_api_search", return_value=api_result),
            patch("api_pool.app._run_free_search") as free,
        ):
            r = self.client.post("/search", json={"query": "demo", "fallback_on_empty": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["provider"], "tavily")
        self.assertFalse(r.json["fallback_used"])
        free.assert_not_called()

    def test_fallback_flag_disables_free_search(self):
        api_result = {"provider": None, "results": [], "attempts": []}
        with (
            patch.object(config, "SEARXNG_FREE_FALLBACK", False),
            patch("api_pool.app._run_api_search", return_value=api_result),
            patch("api_pool.app._run_free_search") as free,
        ):
            r = self.client.post("/search", json={"query": "demo", "fallback_on_empty": True})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json["results"], [])
        free.assert_not_called()

    def test_no_keys_skip_upstream_api_provider(self):
        free_result = {"provider": "searxng_free", "fallback_used": True, "results": []}
        with (
            patch("api_pool.app._get_priority", return_value=["brave"]),
            patch("api_pool.config.is_provider_configured", return_value=False),
            patch("api_pool.state.set_configured"),
            patch("api_pool.providers.brave.search") as brave,
            patch("api_pool.app._run_free_search", return_value=free_result) as free,
        ):
            r = self.client.get("/search?q=demo")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json["fallback_used"])
        brave.assert_not_called()
        free.assert_called_once()


if __name__ == "__main__":
    unittest.main()
