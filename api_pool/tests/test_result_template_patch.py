"""Regression coverage for Windows result-template routing."""
from __future__ import annotations

import importlib.util
import tempfile
import types
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "patch_result_templates.py"
_SPEC = importlib.util.spec_from_file_location("patch_result_templates", _SCRIPT)
_PATCH = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_PATCH)

UPSTREAM = 'import os\ntemplates_path = "unused"\nresult_templates = get_result_templates(templates_path)\n'


class TestResultTemplatePatch(unittest.TestCase):
    def test_windows_paths_resolve_as_jinja_keys(self):
        patched, changed = _PATCH.patch_source(UPSTREAM)
        self.assertTrue(changed)
        namespace = {
            "os": types.SimpleNamespace(sep="\\"),
            "get_result_templates": lambda _: [
                "simple\\result_templates\\default.html",
                "simple\\result_templates\\images.html",
            ],
        }
        exec(patched, namespace)
        self.assertEqual(
            namespace["result_templates"],
            {"simple/result_templates/default.html", "simple/result_templates/images.html"},
        )

    def test_idempotence_and_unknown_layout(self):
        patched, changed = _PATCH.patch_source(UPSTREAM)
        self.assertTrue(changed)
        again, changed = _PATCH.patch_source(patched)
        self.assertFalse(changed)
        self.assertEqual(patched, again)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            _PATCH.patch_source("result_templates = some_new_api(templates_path)")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            _PATCH.patch_source(UPSTREAM + UPSTREAM)

    def test_crlf_preserved_and_no_second_rewrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / _PATCH._TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes(UPSTREAM.replace("\n", "\r\n").encode())
            template = root / _PATCH._REQUIRED_TEMPLATE
            template.parent.mkdir(parents=True)
            template.write_text("fixture", encoding="utf-8")
            self.assertTrue(_PATCH.patch_file(root))
            first = target.read_bytes()
            self.assertIn(b"\r\n", first)
            self.assertFalse(_PATCH.patch_file(root))
            self.assertEqual(first, target.read_bytes())

    def test_missing_template_rejects_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / _PATCH._TARGET
            target.parent.mkdir(parents=True)
            target.write_text(UPSTREAM)
            with self.assertRaisesRegex(FileNotFoundError, "template is missing"):
                _PATCH.patch_file(root)
            self.assertEqual(UPSTREAM, target.read_text())


if __name__ == "__main__":
    unittest.main()
