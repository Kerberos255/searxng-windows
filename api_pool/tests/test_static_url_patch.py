"""Windows static asset URL resolution regression tests."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "patch_static_urls.py"
spec = importlib.util.spec_from_file_location("patch_static_urls", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


class TestStaticUrlPatch(unittest.TestCase):
    def test_registry_paths_match_jinja_static_urls_on_windows(self):
        patched, changed = mod.patch_source("import os\n_STATIC_FILES = webutils.get_static_file_list()\n")
        self.assertTrue(changed)
        self.assertIn('name.replace(os.sep, "/")', patched)
        self.assertNotIn("_STATIC_FILES = webutils.get_static_file_list()", patched)

    def test_idempotence_and_unknown_layout(self):
        patched, changed = mod.patch_source(mod._OLD)
        self.assertTrue(changed)
        again, changed = mod.patch_source(patched)
        self.assertFalse(changed)
        self.assertEqual(patched, again)
        with self.assertRaises(ValueError):
            mod.patch_source("_STATIC_FILES = get_static_files_from_upstream()")

    def test_crlf_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / mod._TARGET
            target.parent.mkdir(parents=True)
            target.write_bytes((mod._OLD + "\r\n").encode())
            css = root / mod._REQUIRED_CSS
            css.parent.mkdir(parents=True)
            css.write_text("fixture", encoding="utf-8")
            self.assertTrue(mod.patch_file(root))
            self.assertIn(b"\r\n", target.read_bytes())
            self.assertFalse(mod.patch_file(root))

    def test_missing_css_does_not_mutate_webapp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / mod._TARGET
            target.parent.mkdir(parents=True)
            target.write_text(mod._OLD, encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                mod.patch_file(root)
            self.assertEqual(target.read_text(encoding="utf-8"), mod._OLD)


if __name__ == "__main__":
    unittest.main()
