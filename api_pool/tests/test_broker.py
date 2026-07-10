"""Comprehensive tests for API Pool Broker.

Uses mock/fake upstream providers to test all fallback scenarios
without real API keys.
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

# Ensure api_pool is importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))

from api_pool import app as broker_app
from api_pool import state
from api_pool import config
from api_pool.providers.base import ProviderResult


class BrokerTestBase(unittest.TestCase):
    """Base class for Broker tests with Flask test client."""

    @classmethod
    def setUpClass(cls):
        broker_app.app.testing = True
        cls.client = broker_app.app.test_client()
        # Use a temp file for SQLite (not :memory: - thread-local connections)
        cls._tmp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls._tmp_db.close()
        config.DB_PATH = cls._tmp_db.name

    @classmethod
    def tearDownClass(cls):
        state.close_all()
        if os.path.exists(cls._tmp_db.name):
            try:
                os.unlink(cls._tmp_db.name)
            except PermissionError:
                pass  # ignore if still locked

    def setUp(self):
        state.close_all()
        # Re-init with fresh temp file
        state.init_db()
        # Patch config to make all providers configured (tests mock the
        # provider search calls directly, but the endpoint checks config first)
        self._config_patcher = patch("api_pool.config.is_provider_configured", return_value=True)
        self._config_patcher.start()
        # Preserve the original three-provider order for legacy regression tests.
        # Firecrawl-specific ordering and fallback behavior lives in test_firecrawl.py.
        self._priority_patcher = patch.object(
            config, "DEFAULT_PRIORITY", ["brave", "tavily", "parallel"]
        )
        self._priority_patcher.start()
        # Also patch get_*_key to return dummy values so providers can "initialize"
        self._brave_key_patcher = patch("api_pool.config.get_brave_key", return_value="test-key")
        self._tavily_key_patcher = patch("api_pool.config.get_tavily_key", return_value="test-key")
        self._parallel_key_patcher = patch("api_pool.config.get_parallel_key", return_value="test-key")
        self._brave_key_patcher.start()
        self._tavily_key_patcher.start()
        self._parallel_key_patcher.start()
        # Set all providers to available
        for prov in ["brave", "tavily", "parallel"]:
            state.set_configured(prov, True)
            state.record_success(prov)

    def tearDown(self):
        self._config_patcher.stop()
        self._priority_patcher.stop()
        self._brave_key_patcher.stop()
        self._tavily_key_patcher.stop()
        self._parallel_key_patcher.stop()
        state.close_all()

    def _search(self, query="test query", **kwargs):
        """Helper to call /search endpoint."""
        payload = {"query": query, **kwargs}
        return self.client.post(
            "/search",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def _assert_attempts(self, data, expected_outcomes):
        """Assert that attempts match expected outcomes in order."""
        actual = [a["outcome"] for a in data.get("attempts", [])]
        self.assertEqual(actual, expected_outcomes, f"Expected {expected_outcomes}, got {actual}")


class TestHealth(BrokerTestBase):
    """Test /health endpoint."""

    def test_health_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")


class TestStatus(BrokerTestBase):
    """Test /status endpoint - no keys leaked."""

    def test_status_no_keys(self):
        resp = self.client.get("/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("priority_order", data)
        self.assertIn("providers", data)
        status_str = json.dumps(data)
        # Ensure no API keys in output
        for key_word in ["api_key", "BSAyiq", "sk-"]:
            self.assertNotIn(key_word, status_str)

    def test_status_providers_listed(self):
        resp = self.client.get("/status")
        data = resp.get_json()
        provider_names = [p["provider"] for p in data["providers"]]
        self.assertIn("brave", provider_names)
        self.assertIn("tavily", provider_names)
        self.assertIn("parallel", provider_names)


class TestBrokerErrors(BrokerTestBase):
    """Test error handling, edge cases, and input validation."""

    def test_empty_query(self):
        resp = self._search(query="")
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_missing_query(self):
        resp = self.client.post(
            "/search",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_json(self):
        resp = self.client.post(
            "/search",
            data="not json",
            content_type="application/json",
        )
        # Flask returns 400 for bad JSON with silent=True
        self.assertEqual(resp.status_code, 400)

    def test_non_string_query(self):
        """Non-string query (e.g. integer) should return 400."""
        resp = self._search(query=123)
        self.assertEqual(resp.status_code, 400)

    def test_zero_pageno(self):
        resp = self._search(pageno=0)
        self.assertEqual(resp.status_code, 400)

    def test_pageno_too_large(self):
        resp = self._search(pageno=101)
        self.assertEqual(resp.status_code, 400)

    def test_zero_max_results(self):
        resp = self._search(max_results=0)
        self.assertEqual(resp.status_code, 400)

    def test_max_results_too_large(self):
        resp = self._search(max_results=51)
        self.assertEqual(resp.status_code, 400)

    def test_invalid_safesearch(self):
        resp = self._search(safesearch=3)
        self.assertEqual(resp.status_code, 400)

    def test_invalid_time_range(self):
        resp = self._search(time_range="invalid")
        self.assertEqual(resp.status_code, 400)

    def test_all_providers_unconfigured(self):
        """Test all APIs unconfigured -> empty results."""
        for prov in ["brave", "tavily", "parallel"]:
            state.record_failure(prov, None, "misconfigured", is_misconfigured=True)

        with patch("api_pool.config.is_provider_configured", return_value=False):
            resp = self._search()
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertIsNone(data["provider"])
            self.assertEqual(data["results"], [])


class TestBraveSuccess(BrokerTestBase):
    """Test: Brave success, only Brave called."""

    @patch("api_pool.providers.brave.search")
    def test_brave_success_only(self, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=True,
            results=[
                {"url": "https://example.com", "title": "Example", "content": "Test content"}
            ],
            http_status=200,
        )

        resp = self._search()
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["provider"], "brave")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["url"], "https://example.com")

        # Verify only Brave was called
        mock_brave.assert_called_once()


class TestBraveQuotaThenFallback(BrokerTestBase):
    """Test: Brave quota -> Tavily fallback."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_brave_quota_then_tavily(self, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False,
            error_category="quota_exhausted",
            is_quota=True,
            http_status=402,
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "Tavily Result", "content": "Tavily"}],
            http_status=200,
        )

        resp = self._search()
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["provider"], "tavily")
        self.assertEqual(len(data["results"]), 1)
        self._assert_attempts(data, ["quota_exhausted", "success"])

        mock_brave.assert_called_once()
        mock_tavily.assert_called_once()


class TestAllProvidersExhausted(BrokerTestBase):
    """Test: Brave + Tavily exhausted -> Parallel."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    @patch("api_pool.providers.parallel.search")
    def test_all_exhausted_then_parallel(self, mock_parallel, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )
        mock_tavily.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=433
        )
        mock_parallel.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://parallel.example", "title": "Parallel", "content": "Parallel content"}],
            http_status=200,
        )

        resp = self._search()
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["provider"], "parallel")
        self._assert_attempts(data, ["quota_exhausted", "quota_exhausted", "success"])


class TestRateLimitCooldown(BrokerTestBase):
    """Test: 429 -> cooldown, does NOT mark quota exhausted."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_429_then_fallback(self, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="rate_limited", http_status=429, retry_after=60
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T", "content": "T"}],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "tavily")
        self._assert_attempts(data, ["rate_limited", "success"])

        # Brave should be in cooldown, NOT quota_exhausted
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "cooldown")
        self.assertIsNotNone(brave_state["cooldown_until"])


class TestTimeoutFallback(BrokerTestBase):
    """Test: timeout/5xx -> switch to next provider."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_timeout_then_fallback(self, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="timeout"
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T", "content": "T"}],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "tavily")
        self._assert_attempts(data, ["timeout", "success"])

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_5xx_then_fallback(self, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="http_error", http_status=503
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T", "content": "T"}],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "tavily")
        self._assert_attempts(data, ["http_error", "success"])


class Test401Misconfigured(BrokerTestBase):
    """Test: 401 -> misconfigured, skip permanently."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_401_skip(self, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="auth_failed", http_status=401, is_misconfigured=True
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T", "content": "T"}],
            http_status=200,
        )

        # First request: 401 on Brave, falls to Tavily
        resp1 = self._search()
        data1 = resp1.get_json()
        self.assertEqual(data1["provider"], "tavily")

        # Second request: Brave stays misconfigured, skip directly to Tavily
        resp2 = self._search()
        data2 = resp2.get_json()
        self.assertEqual(data2["provider"], "tavily")
        # Only 2 attempts: misconfigured (skipped), then success
        attempts = [a["outcome"] for a in data2.get("attempts", [])]
        self.assertEqual(attempts, ["misconfigured", "success"])


class TestEmptyResultsNoFallback(BrokerTestBase):
    """Test: HTTP 200 empty results -> no fallback by default."""

    @patch("api_pool.providers.brave.search")
    def test_empty_results_no_fallback(self, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=True, results=[], http_status=200
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "brave")
        self.assertEqual(data["results"], [])
        self._assert_attempts(data, ["success"])

        # Tavily should NOT have been called
        # (we didn't mock tavily, so if it was called it would fail)


class TestAllApisUnavailable(BrokerTestBase):
    """Test: all APIs unavailable -> returns 200 with empty results."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    @patch("api_pool.providers.parallel.search")
    def test_all_unavailable(self, mock_parallel, mock_tavily, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )
        mock_tavily.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=433
        )
        mock_parallel.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )

        resp = self._search()
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsNone(data["provider"])
        self.assertEqual(data["results"], [])
        self.assertEqual(len(data["attempts"]), 3)


class TestStatePersistence(BrokerTestBase):
    """Test: SQLite state persists across requests (emulated by checking state module)."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_state_persistence(self, mock_tavily, mock_brave):
        # Simulate Brave hitting quota
        mock_brave.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://t.example.com", "title": "T", "content": "T"}],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "tavily")

        # Verify Brave state in DB
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "quota_exhausted")
        self.assertIsNotNone(brave_state["probe_after"])
        self.assertGreater(brave_state["probe_after"], time.time())

        # Tavily should be available
        tavily_state = state.get_provider_state("tavily")
        self.assertEqual(tavily_state["status"], "available")


class TestProbeRecovery(BrokerTestBase):
    """Test: quota_exhausted probe recovery."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    def test_probe_recovery(self, mock_tavily, mock_brave):
        # First: Brave quota exhausted
        mock_brave.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://t.example.com", "title": "T", "content": "T"}],
            http_status=200,
        )

        self._search()

        # Verify Brave is marked exhausted
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "quota_exhausted")

        # Manually set probe time in the past to simulate recovery window
        state._get_connection().execute(
            "UPDATE providers SET probe_after = ? WHERE provider = 'brave'",
            (time.time() - 10,),
        )
        state._get_connection().commit()

        # Now Brave should be probed on next request
        mock_brave.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://brave.example.com", "title": "B", "content": "B"}],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        self.assertEqual(data["provider"], "brave")

        # After success, Brave should be available
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "available")


class TestStatusNoKeys(BrokerTestBase):
    """Test: /status never leaks keys."""

    def test_status_sanitized(self):
        resp = self.client.get("/status")
        content = resp.get_data(as_text=True)
        # Check for potential key patterns
        self.assertNotIn("api_key", content.lower())
        self.assertNotIn("subscription", content.lower())
        self.assertNotIn("x-api-key", content.lower())
        # Should not contain Bearer token patterns
        self.assertNotIn("Bearer ", content)


class TestResultMapping(BrokerTestBase):
    """Test: result mapping produces correct fields."""

    @patch("api_pool.providers.brave.search")
    def test_result_fields(self, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=True,
            results=[
                {
                    "url": "https://example.com/page",
                    "title": "Test Page",
                    "content": "Test content description",
                    "published_date": "2026-01-15",
                    "score": 0.95,
                }
            ],
            http_status=200,
        )

        resp = self._search()
        data = resp.get_json()
        result = data["results"][0]
        self.assertEqual(result["url"], "https://example.com/page")
        self.assertEqual(result["title"], "Test Page")
        self.assertEqual(result["content"], "Test content description")
        self.assertEqual(result["published_date"], "2026-01-15")
        self.assertEqual(result["score"], 0.95)


class TestSearchParamsPassthrough(BrokerTestBase):
    """Test: search parameters are correctly passed."""

    @patch("api_pool.providers.brave.search")
    def test_params_passthrough(self, mock_brave):
        mock_brave.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://example.com", "title": "Test", "content": "Test"}],
            http_status=200,
        )

        resp = self._search(query="hello world", pageno=2, time_range="week", safesearch=1, max_results=5)
        data = resp.get_json()
        self.assertEqual(data["provider"], "brave")

        # Verify Brave was called with correct params
        mock_brave.assert_called_once()
        call_kwargs = mock_brave.call_args[1]
        self.assertEqual(call_kwargs.get("pageno"), 2)
        self.assertEqual(call_kwargs.get("time_range"), "week")
        self.assertEqual(call_kwargs.get("safesearch"), 1)
        self.assertEqual(call_kwargs.get("max_results"), 5)


class TestTavilyAuth(BrokerTestBase):
    """Test: Tavily uses Authorization Bearer Header, no api_key in JSON body."""

    @patch("api_pool.providers.tavily.get_http_client")
    def test_tavily_bearer_header_and_no_api_key_in_body(self, mock_get_client):
        """Verify Tavily sends Bearer auth header and not api_key in request body."""
        import httpx

        captured_headers = {}
        captured_body = {}

        def handler(request):
            captured_headers.update(dict(request.headers))
            captured_body.update(json.loads(request.read()))
            return httpx.Response(
                200,
                json={"results": [{"url": "https://tavily.example", "title": "T", "content": "T"}]},
            )

        mock_transport_client = httpx.Client(transport=httpx.MockTransport(handler))
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_transport_client
        mock_get_client.return_value = mock_cm

        from api_pool.providers.tavily import search

        result = search(query="hello tavily", max_results=5)

        self.assertTrue(result.success)
        # Verify Bearer authorization header
        auth_header = captured_headers.get("authorization", "")
        self.assertIn("Bearer ", auth_header)
        self.assertIn("test-key", auth_header)
        # Verify no api_key in JSON body
        self.assertNotIn("api_key", captured_body)
        self.assertEqual(captured_body["query"], "hello tavily")
        self.assertEqual(captured_body["search_depth"], "basic")


class TestBraveDirectErrors(BrokerTestBase):
    """Test Brave-specific error categorization for timeout and connect errors."""

    @patch("api_pool.providers.brave.get_http_client")
    def test_brave_timeout_error(self, mock_get_client):
        """Brave timeout should be categorized as 'timeout'."""
        import httpx

        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_client.get.side_effect = httpx.TimeoutException(
            "Request timed out", request=httpx.Request("GET", "https://api.search.brave.com")
        )
        mock_cm.__enter__.return_value = mock_client
        mock_get_client.return_value = mock_cm

        from api_pool.providers.brave import search

        result = search(query="test")
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "timeout")
        self.assertIsNone(result.http_status)

    @patch("api_pool.providers.brave.get_http_client")
    def test_brave_connect_error(self, mock_get_client):
        """Brave connection error should be categorized as 'connection_error'."""
        import httpx

        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_cm.__enter__.return_value = mock_client
        mock_get_client.return_value = mock_cm

        from api_pool.providers.brave import search

        result = search(query="test")
        self.assertFalse(result.success)
        self.assertEqual(result.error_category, "connection_error")
        self.assertIsNone(result.http_status)


class TestParallelHeaders(BrokerTestBase):
    """Test: Parallel sends x-api-key header, valid default mode, and result mapping."""

    @patch("api_pool.providers.parallel.get_http_client")
    def test_parallel_x_api_key_header_and_mode(self, mock_get_client):
        """Verify Parallel sends x-api-key header and quality-first mode."""
        import httpx

        captured_headers = {}
        captured_body = {}

        def handler(request):
            captured_headers.update(dict(request.headers))
            captured_body.update(json.loads(request.read()))
            return httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://parallel.example", "title": "P", "content": "P", "score": 0.9}
                    ]
                },
            )

        mock_transport_client = httpx.Client(transport=httpx.MockTransport(handler))
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_transport_client
        mock_get_client.return_value = mock_cm

        from api_pool.providers.parallel import search

        result = search(query="hello parallel")

        self.assertTrue(result.success)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0]["title"], "P")
        # Verify x-api-key header
        self.assertIn("x-api-key", captured_headers)
        self.assertIn("test-key", captured_headers["x-api-key"])
        # Verify mode default
        self.assertEqual(captured_body.get("mode"), "advanced")
        self.assertEqual(captured_body.get("advanced_settings"), {"max_results": 10})
        self.assertNotIn("max_results", captured_body)


class TestProbeLeaseConcurrent(BrokerTestBase):
    """Test: only one concurrent request acquires the probe lease."""

    @patch("api_pool.providers.brave.search")
    @patch("api_pool.providers.tavily.search")
    @patch("api_pool.providers.parallel.search")
    def test_concurrent_probe_only_one_brave_call(self, mock_parallel, mock_tavily, mock_brave):
        """With 5 concurrent requests and Brave in probe window, only 1 gets the lease.

        Brave's probe returns failure (quota_exhausted) so the provider stays
        in quota_exhausted state. This prevents other threads from seeing Brave
        as "available" after the probe succeeds, making the test deterministic.
        """
        import threading

        # Mock: Brave always returns quota_exhausted (probe fails)
        mock_brave.return_value = ProviderResult(
            success=False, error_category="quota_exhausted", is_quota=True, http_status=402
        )
        # Fallback providers succeed
        mock_tavily.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://tavily.example", "title": "T", "content": "T"}],
            http_status=200,
        )
        mock_parallel.return_value = ProviderResult(
            success=True,
            results=[{"url": "https://parallel.example", "title": "P", "content": "P"}],
            http_status=200,
        )

        # Step 1: Exhaust Brave's quota via one search
        self._search()
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "quota_exhausted")

        # Step 2: Set probe_after to past so probe window is open
        state._get_connection().execute(
            "UPDATE providers SET probe_after = ? WHERE provider = 'brave'",
            (time.time() - 10,),
        )
        state._get_connection().commit()

        # Step 3: Reset all mock counts (Step 1 already consumed calls)
        mock_brave.reset_mock()
        mock_tavily.reset_mock()
        mock_parallel.reset_mock()

        # Step 4: Launch 5 concurrent search requests
        results_lock = threading.Lock()
        responses = []

        def do_search():
            try:
                resp = self._search()
                data = resp.get_json()
                with results_lock:
                    responses.append(data)
            except Exception as e:
                with results_lock:
                    responses.append({"error": str(e)})

        threads = [threading.Thread(target=do_search) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        # Step 5: Verify all 5 returned successfully
        self.assertEqual(len(responses), 5)
        for r in responses:
            self.assertIn("provider", r, f"Failed response: {r}")

        # Step 6: Exactly 1 Brave probe call (atomic lease ensures single winner).
        # The probing thread then falls to Tavily like the other 4.
        self.assertEqual(
            mock_brave.call_count,
            1,
            f"Expected exactly 1 Brave probe call, got {mock_brave.call_count}",
        )

        # All 5 threads should have succeeded via Tavily or Parallel
        tavily_count = mock_tavily.call_count
        parallel_count = mock_parallel.call_count
        self.assertGreaterEqual(
            tavily_count,
            1,
            f"Expected at least 1 Tavily call, got {tavily_count}",
        )
        self.assertEqual(
            parallel_count, 0, f"Expected no Parallel calls, got {parallel_count}"
        )

        # Step 7: Brave should still be quota_exhausted (probe returned failure)
        brave_state = state.get_provider_state("brave")
        self.assertEqual(
            brave_state["status"],
            "quota_exhausted",
            f"Expected Brave to stay quota_exhausted, got {brave_state['status']}",
        )


class TestStartupRecovery(BrokerTestBase):
    """Test: recover_configured_providers() recovers misconfigured/unavailable on startup."""

    def test_startup_recovery_misconfigured(self):
        """recover_configured_providers() should reset misconfigured to available."""
        state.record_failure("brave", 401, "auth_failed", is_misconfigured=True)
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "misconfigured")
        self.assertEqual(brave_state["configured"], 1)

        state.recover_configured_providers()
        brave_state = state.get_provider_state("brave")
        self.assertEqual(brave_state["status"], "available")

    def test_startup_recovery_unavailable(self):
        """recover_configured_providers() should reset unavailable to available."""
        # Manually set status to unavailable while keeping configured=1
        conn = state._get_connection()
        conn.execute(
            "UPDATE providers SET status = 'unavailable', configured = 1 WHERE provider = 'tavily'"
        )
        conn.commit()

        tavily_state = state.get_provider_state("tavily")
        self.assertEqual(tavily_state["status"], "unavailable")
        self.assertEqual(tavily_state["configured"], 1)

        state.recover_configured_providers()
        tavily_state = state.get_provider_state("tavily")
        self.assertEqual(tavily_state["status"], "available")

    def test_startup_recovery_skips_quota(self):
        """recover_configured_providers() should NOT reset quota_exhausted."""
        state.record_failure("parallel", 402, "quota_exhausted", is_quota=True)
        parallel_state = state.get_provider_state("parallel")
        self.assertEqual(parallel_state["status"], "quota_exhausted")

        state.recover_configured_providers()
        parallel_state = state.get_provider_state("parallel")
        # quota_exhausted should stay - must be recovered via probe lease
        self.assertEqual(parallel_state["status"], "quota_exhausted")


class TestSearXNGAdapter(unittest.TestCase):
    """Test: SearXNG api_pool engine uses JSON body (not data) for POST."""

    def setUp(self):
        self.engine_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "patches", "api_pool.py",
        )

    def test_engine_file_uses_json_body(self):
        """Verify engine source uses params['json'] not params['data']."""
        with open(self.engine_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn('params["json"]', content)
        self.assertNotIn('params["data"] = json', content)
        self.assertNotIn('json.dumps', content)

    @patch.dict("sys.modules", {"searx": MagicMock(), "searx.result_types": MagicMock()})
    def test_request_function_sets_json(self):
        """Verify the request() modifies params dict with json key."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "api_pool_engine_test", self.engine_path
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["api_pool_engine_test"] = mod
        spec.loader.exec_module(mod)

        params = {"pageno": 1, "time_range": None, "safesearch": 0, "headers": {}}
        mod.request("test query", params)

        self.assertIn("json", params)
        self.assertNotIn("data", params)
        self.assertEqual(params["json"]["query"], "test query")
        self.assertEqual(params["method"], "POST")
        self.assertEqual(params["headers"]["Content-Type"], "application/json")

        # Clean up
        del sys.modules["api_pool_engine_test"]


if __name__ == "__main__":
    unittest.main()
