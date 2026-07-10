"""Public package safety and configuration tests."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api_pool import config


REPO_ROOT = Path(__file__).resolve().parents[2]
KEY_NAMES = (
    "BRAVE_API_KEY",
    "FIRECRAWL_API_KEY",
    "TAVILY_API_KEY",
    "PARALLEL_API_KEY",
)


class TestPublicConfiguration(unittest.TestCase):
    def test_default_env_path_is_install_local(self):
        self.assertEqual(config.DEFAULT_ENV_FILE, REPO_ROOT / "config" / "api-pool.env")

    def test_example_keys_are_empty(self):
        text = (REPO_ROOT / "config" / "api-pool.env.example").read_text(encoding="utf-8")
        values = {}
        for line in text.splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
        for name in KEY_NAMES:
            self.assertIn(name, values)
            self.assertEqual(values[name], "")

    def test_env_file_and_priority_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "api-pool.env"
            env_path.write_text(
                "FIRECRAWL_API_KEY=test-firecrawl\n"
                "API_POOL_PRIORITY=firecrawl,brave\n",
                encoding="utf-8",
            )
            with patch.object(config, "ENV_FILE", env_path), patch.dict(os.environ, {}, clear=True):
                self.assertTrue(config.is_provider_configured("firecrawl"))
                self.assertFalse(config.is_provider_configured("brave"))
                self.assertEqual(
                    config.get_priority(),
                    ["firecrawl", "brave", "tavily", "parallel"],
                )

    def test_process_environment_precedes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "api-pool.env"
            env_path.write_text("BRAVE_API_KEY=file-value\n", encoding="utf-8")
            with patch.object(config, "ENV_FILE", env_path), patch.dict(
                os.environ, {"BRAVE_API_KEY": "process-value"}, clear=True
            ):
                self.assertEqual(config.get_brave_key(), "process-value")


class TestPublicPackageSafety(unittest.TestCase):
    def test_no_private_local_paths_in_package(self):
        forbidden = ("E:" + "\\openclaw").lower()
        private_env = (".config" + "\\openclaw.env").lower()
        findings = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() in {".pyc", ".sqlite", ".zip"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            lowered = text.lower()
            if forbidden in lowered or private_env in lowered:
                findings.append(str(path.relative_to(REPO_ROOT)))
        self.assertEqual(findings, [])

    def test_engine_patch_license_and_template_entry(self):
        engine = (REPO_ROOT / "patches" / "api_pool.py").read_text(encoding="utf-8")
        settings = (REPO_ROOT / "config" / "settings.example.yml").read_text(encoding="utf-8")
        self.assertIn("SPDX-License-Identifier: AGPL-3.0-or-later", engine)
        self.assertIn("engine: api_pool", settings)
        self.assertIn("disabled: true", settings)
        self.assertIn("enable_http: true", settings)


    def test_lifecycle_scripts_treat_api_pool_as_opt_in(self):
        start = (REPO_ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
        check = (REPO_ROOT / "scripts" / "check.ps1").read_text(encoding="utf-8")
        helper = (REPO_ROOT / "scripts" / "api-pool.ps1").read_text(encoding="utf-8")
        self.assertIn("Test-ApiPoolEnabled", helper)
        self.assertIn("if ($ApiPoolEnabled)", start)
        self.assertIn("Broker startup skipped", start)
        self.assertIn("if ($ApiPoolEnabled)", check)
        self.assertIn("Broker checks skipped", check)


    def test_release_workflow_is_gated_by_validation(self):
        workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn('tags:', workflow)
        self.assertIn('"v*.*.*"', workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("needs: validate", workflow)
        self.assertIn("merge-base --is-ancestor", workflow)
        self.assertIn("build-release.ps1", workflow)

        builder = (REPO_ROOT / "scripts" / "build-release.ps1").read_text(encoding="utf-8")
        self.assertIn("git archive", builder)
        self.assertIn("Get-FileHash", builder)
        self.assertIn("SHA256SUMS.txt", builder)

        installer = (REPO_ROOT / "install-searxng-windows.ps1").read_text(encoding="utf-8")
        self.assertIn("releases/latest", installer)
        self.assertNotIn('[string]$Ref = "v0.1.0"', installer)


if __name__ == "__main__":
    unittest.main()
