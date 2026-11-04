"""Regression tests for Windows-invalid SearXNG upstream filenames (issues #6, #7)."""

from __future__ import annotations

import importlib.util
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "extract-source.py"
_SPEC = importlib.util.spec_from_file_location("searxng_source_extractor", _SCRIPT)
_EXTRACTOR = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_EXTRACTOR)

_REQUIRED = {
    "searxng-master/setup.py": b"from setuptools import setup\n",
    "searxng-master/requirements.txt": b"flask\n",
    "searxng-master/searx/webapp.py": b"app = None\n",
}


def _write_fixture_zip(path: Path, overrides: dict[str, bytes] | None = None) -> None:
    files = dict(_REQUIRED) if overrides is None else dict(overrides)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class TestWindowsSourceExtractor(unittest.TestCase):
    def test_skips_colon_templates_but_keeps_complete_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.zip"
            dest = Path(tmp) / "stage"
            files = {
                **_REQUIRED,
                "searxng-master/utils/templates/etc/httpd/sites-available/searxng.conf:socket": b"invalid on Windows",
                "searxng-master/utils/templates/etc/nginx/default.apps-available/searxng.conf:socket": b"invalid on Windows",
                "searxng-master/utils/templates/etc/uwsgi/apps-available/searxng.ini:socket": b"invalid on Windows",
                "searxng-master/utils/templates/etc/uwsgi/apps-archlinux/searxng.ini:socket": b"invalid on Windows",
                "searxng-master/searx/settings.yml": b"general: {}\n",
            }
            _write_fixture_zip(archive, files)
            extracted, skipped = _EXTRACTOR.extract_source_archive(archive, dest)
            self.assertEqual(extracted, 4)
            self.assertEqual(skipped, 4)
            self.assertTrue((dest / "searx" / "webapp.py").is_file())
            self.assertTrue((dest / "searx" / "settings.yml").is_file())
            self.assertFalse((dest / "utils" / "templates" / "etc" / "httpd" /
                              "sites-available" / "searxng.conf:socket").exists())

    def test_rejects_path_traversal_and_removes_partial_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.zip"
            dest = Path(tmp) / "stage"
            files = {**_REQUIRED, "searxng-master/../../escape.txt": b"escape"}
            _write_fixture_zip(archive, files)
            with self.assertRaises(ValueError):
                _EXTRACTOR.extract_source_archive(archive, dest)
            self.assertFalse(dest.exists())
            self.assertFalse((Path(tmp) / "escape.txt").exists())

    def test_rejects_archive_missing_required_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.zip"
            dest = Path(tmp) / "stage"
            files = {"searxng-master/requirements.txt": b"flask\n"}
            _write_fixture_zip(archive, files)
            with self.assertRaisesRegex(ValueError, "missing required files"):
                _EXTRACTOR.extract_source_archive(archive, dest)
            self.assertFalse(dest.exists())

    def test_rejects_nonempty_stage_without_touching_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.zip"
            dest = Path(tmp) / "stage"
            dest.mkdir()
            sentinel = dest / "do-not-delete.txt"
            sentinel.write_text("preserve", encoding="utf-8")
            _write_fixture_zip(archive)
            with self.assertRaisesRegex(ValueError, "Destination must be empty"):
                _EXTRACTOR.extract_source_archive(archive, dest)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve")

    def test_skips_symlink_and_reserved_windows_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.zip"
            dest = Path(tmp) / "stage"
            with zipfile.ZipFile(archive, "w") as z:
                for path, content in _REQUIRED.items():
                    z.writestr(path, content)
                link = zipfile.ZipInfo("searxng-master/searx/link")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(link, b"/somewhere")
                z.writestr("searxng-master/searx/CON", b"reserved")
            extracted, skipped = _EXTRACTOR.extract_source_archive(archive, dest)
            self.assertEqual((extracted, skipped), (3, 2))
            self.assertFalse((dest / "searx" / "link").exists())


if __name__ == "__main__":
    unittest.main()
