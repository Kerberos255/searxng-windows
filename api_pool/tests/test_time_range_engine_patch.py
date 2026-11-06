"""Regression tests for searching with engines that lack date filters."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "patch_time_range_engines.py"
_SPEC = importlib.util.spec_from_file_location("patch_time_range_engines", _SCRIPT)
_PATCH = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader
_SPEC.loader.exec_module(_PATCH)

UPSTREAM = (
    "    def get_params(self, search_query, engine_category):\n"
    "        if search_query.pageno > 1 and not self.engine.paging:\n"
    "            return None\n"
    "        # if time_range is not supported, skip\n"
    "        if search_query.time_range and not self.engine.time_range_support:\n"
    "            return None\n"
    "        params: RequestParams = {\n"
    '            "time_range": search_query.time_range,\n'
    "        }\n"
    "        return params\n"
)


class TestDateFallbackPatch(unittest.TestCase):
    def test_supported_engine_gets_range_unsupported_gets_none(self):
        patched, changed = _PATCH.patch_source(UPSTREAM)
        self.assertTrue(changed)
        namespace = {"RequestParams": dict}
        exec("class Processor:\n    def __init__(self, engine): self.engine = engine\n" + patched, namespace)
        processor_cls = namespace["Processor"]
        query = type("Query", (), {"pageno": 1, "time_range": "week"})()
        engine = type("Engine", (), {"paging": True, "time_range_support": True})()
        self.assertEqual(processor_cls(engine).get_params(query, "general")["time_range"], "week")
        engine.time_range_support = False
        self.assertIsNone(processor_cls(engine).get_params(query, "general")["time_range"])

    def test_idempotent_and_rejects_unknown_upstream(self):
        first, changed = _PATCH.patch_source(UPSTREAM)
        self.assertTrue(changed)
        again, changed = _PATCH.patch_source(first)
        self.assertFalse(changed)
        self.assertEqual(first, again)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            _PATCH.patch_source("def unrelated(): pass")

    def test_patch_file_preserves_crlf_and_no_second_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / _PATCH._RELATIVE_TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(UPSTREAM.replace("\n", "\r\n").encode("utf-8"))
            self.assertTrue(_PATCH.patch_file(Path(tmp)))
            first = target.read_bytes()
            self.assertIn(b"effective_time_range", first)
            self.assertIn(b"\r\n", first)
            self.assertFalse(_PATCH.patch_file(Path(tmp)))
            self.assertEqual(target.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
