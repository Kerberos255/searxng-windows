"""Regression tests for Windows-safe SearXNG source archive extraction."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "extract-source.py"
SPEC = importlib.util.spec_from_file_location("searxng_source_extractor", EXTRACTOR_PATH)
assert SPEC is not None and SPEC.loader is not None
EXTRACTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXTRACTOR)


class TestSourceArchiveExtraction(unittest.TestCase):
    def _archive(self, path: Path, entries: dict[str, str]) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in entries.items():
                archive.writestr(name, content)

    def test_extracts_project_and_skips_colon_filenames(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "searxng.zip"
            destination = root / "source"
            self._archive(
                archive,
                {
                    "searxng-master/": "",
                    "searxng-master/setup.py": "from setuptools import setup\n",
                    "searxng-master/requirements.txt": "Flask\n",
                    "searxng-master/searx/__init__.py": "",
                    "searxng-master/searx/webapp.py": "app = None\n",
                    "searxng-master/utils/templates/nginx/site.conf:socket": "unix-only",
                },
            )

            extracted, skipped = EXTRACTOR.extract_source_archive(archive, destination)

            self.assertEqual(extracted, 4)
            self.assertEqual(skipped, 1)
            self.assertTrue((destination / "setup.py").is_file())
            self.assertTrue((destination / "requirements.txt").is_file())
            self.assertTrue((destination / "searx" / "__init__.py").is_file())
            self.assertTrue((destination / "searx" / "webapp.py").is_file())
            self.assertFalse((destination / "utils" / "templates" / "nginx" / "site.conf:socket").exists())

    def test_rejects_incomplete_source_and_cleans_staging_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "incomplete.zip"
            destination = root / "source"
            self._archive(archive, {"searxng-master/README.rst": "incomplete"})

            with self.assertRaisesRegex(ValueError, "missing required files"):
                EXTRACTOR.extract_source_archive(archive, destination)

            self.assertFalse(destination.exists())

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            destination = root / "source"
            self._archive(
                archive,
                {
                    "searxng-master/setup.py": "setup",
                    "searxng-master/requirements.txt": "requirements",
                    "searxng-master/../outside.txt": "outside",
                },
            )

            with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                EXTRACTOR.extract_source_archive(archive, destination)

            self.assertFalse((root / "outside.txt").exists())

    def test_rejects_archives_with_multiple_top_level_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "multi-root.zip"
            destination = root / "source"
            self._archive(
                archive,
                {
                    "searxng-master/setup.py": "setup",
                    "other/requirements.txt": "requirements",
                },
            )

            with self.assertRaisesRegex(ValueError, "one top-level directory"):
                EXTRACTOR.extract_source_archive(archive, destination)


if __name__ == "__main__":
    unittest.main()
