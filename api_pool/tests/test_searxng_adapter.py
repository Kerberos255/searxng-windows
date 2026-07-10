"""Tests for the SearXNG API Pool engine patch."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = REPO_ROOT / "patches" / "api_pool.py"


class _MainResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _EngineResults:
    class types:
        MainResult = _MainResult

    def __init__(self):
        self.results = []

    def add(self, result):
        self.results.append(result)


def _load_engine_module():
    fake_searx = types.ModuleType("searx")
    fake_result_types = types.ModuleType("searx.result_types")
    fake_result_types.EngineResults = _EngineResults
    old_searx = sys.modules.get("searx")
    old_result_types = sys.modules.get("searx.result_types")
    sys.modules["searx"] = fake_searx
    sys.modules["searx.result_types"] = fake_result_types
    try:
        spec = importlib.util.spec_from_file_location("test_api_pool_engine", ENGINE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if old_searx is None:
            sys.modules.pop("searx", None)
        else:
            sys.modules["searx"] = old_searx
        if old_result_types is None:
            sys.modules.pop("searx.result_types", None)
        else:
            sys.modules["searx.result_types"] = old_result_types


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestSearXNGAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = _load_engine_module()

    def test_parse_date_only_as_utc_datetime(self):
        parsed = self.engine._parse_published_date("2026-07-09")
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 7)
        self.assertEqual(parsed.day, 9)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_parse_zulu_timestamp(self):
        parsed = self.engine._parse_published_date("2026-07-09T12:34:56Z")
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        self.assertEqual(parsed.hour, 12)

    def test_invalid_date_is_omitted(self):
        self.assertIsNone(self.engine._parse_published_date("not-a-date"))
        self.assertIsNone(self.engine._parse_published_date(None))

    def test_response_maps_string_date_to_datetime(self):
        response = _Response(
            {
                "provider": "parallel",
                "attempts": [{"provider": "parallel", "outcome": "success"}],
                "results": [
                    {
                        "url": "https://example.com/result",
                        "title": "Example",
                        "content": "Useful excerpt",
                        "published_date": "2026-07-09",
                    }
                ],
            }
        )
        results = self.engine.response(response)
        self.assertEqual(len(results.results), 1)
        self.assertEqual(results.results[0].publishedDate.year, 2026)
        self.assertEqual(results.results[0].publishedDate.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
