"""Regression tests for the API-first default web-search routing."""
from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from test_searxng_adapter import _load_engine_module


class FakeQuery:
    def __init__(self, *engines, category="general"):
        self.engineref_list = [
            types.SimpleNamespace(name=engine, category=category)
            for engine in engines
        ]

    @property
    def categories(self):
        return [ref.category for ref in self.engineref_list]

    @property
    def names(self):
        return [ref.name for ref in self.engineref_list]


class TestDefaultSearchRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = _load_engine_module()

    def apply(self, query, *, has_api, specific=False, form=None):
        with patch.object(self.engine, "_broker_has_configured_providers", return_value=has_api) as status:
            self.engine.apply_default_search_priority(
                query, types.SimpleNamespace(specific=specific), form or {}
            )
        return status

    def test_configured_api_is_only_default_general_engine(self):
        query = FakeQuery("bing", "sogou", "api pool")
        status = self.apply(query, has_api=True)
        self.assertEqual(query.names, ["api pool"])
        status.assert_called_once()

    def test_no_configured_api_directly_uses_free_engines(self):
        query = FakeQuery("bing", "sogou", "api pool")
        self.apply(query, has_api=False)
        self.assertEqual(query.names, ["bing", "sogou"])

    def test_explicit_engines_are_respected_and_do_not_probe_broker(self):
        query = FakeQuery("bing", "api pool")
        status = self.apply(query, has_api=True, form={"engines": "bing"})
        self.assertEqual(query.names, ["bing", "api pool"])
        status.assert_not_called()

    def test_bangs_are_respected(self):
        query = FakeQuery("bing", "api pool")
        status = self.apply(query, has_api=True, specific=True)
        self.assertEqual(query.names, ["bing", "api pool"])
        status.assert_not_called()

    def test_non_web_category_is_untouched(self):
        query = FakeQuery("bing images", "api pool", category="images")
        status = self.apply(query, has_api=True)
        self.assertEqual(query.names, ["bing images", "api pool"])
        status.assert_not_called()

    def test_no_api_pool_engine_is_not_injected(self):
        query = FakeQuery("bing", "sogou")
        status = self.apply(query, has_api=True)
        self.assertEqual(query.names, ["bing", "sogou"])
        status.assert_not_called()

    def test_nonlocal_broker_is_never_contacted(self):
        with patch.object(self.engine, "broker_url", "https://example.org/search"):
            self.assertFalse(self.engine._broker_has_configured_providers())


class TestPriorityPatch(unittest.TestCase):
    def test_patch_is_idempotent_and_rejects_unknown_layout(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "patch_default_search_priority.py"
        spec = importlib.util.spec_from_file_location("priority_patch", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        old = "        search_obj = searx.search.SearchWithPlugins(search_query, sxng_request, sxng_request.user_plugins)"
        updated, changed = module.patch_source(old)
        self.assertTrue(changed)
        self.assertIn("apply_default_search_priority(search_query, raw_text_query, sxng_request.form)", updated)
        repeated, changed = module.patch_source(updated)
        self.assertFalse(changed)
        self.assertEqual(updated, repeated)
        with self.assertRaises(ValueError):
            module.patch_source("search_obj = new_upstream_route()")

    def test_crlf_preserved(self):
        script = Path(__file__).resolve().parents[2] / "scripts" / "patch_default_search_priority.py"
        spec = importlib.util.spec_from_file_location("priority_patch_crlf", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "searxng" / "searx" / "webapp.py"
            target.parent.mkdir(parents=True)
            old = "        search_obj = searx.search.SearchWithPlugins(search_query, sxng_request, sxng_request.user_plugins)"
            target.write_bytes(("before\r\n" + old + "\r\nafter\r\n").encode())
            self.assertTrue(module.patch_file(Path(tmp)))
            self.assertIn(b"\r\n", target.read_bytes())
            self.assertFalse(module.patch_file(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
