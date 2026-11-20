"""Check all installed SearXNG result templates resolve through Jinja."""
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
source = root / "searxng"
os.environ["SEARXNG_SETTINGS_PATH"] = str(root / "config" / "settings.yml")
sys.path.insert(0, str(source))

from searx import webapp  # noqa: E402

directory = source / "searx" / "templates" / "simple" / "result_templates"
templates = sorted(directory.glob("*.html"))
if not templates or not (directory / "default.html").is_file():
    raise SystemExit("SearXNG result templates missing")

for template in templates:
    expected = "simple/result_templates/" + template.name
    resolved = webapp.get_result_template("simple", template.name)
    if resolved != expected:
        raise SystemExit(f"Wrong result-template route: {template.name!r} => {resolved!r}")
    webapp.app.jinja_env.get_template(resolved)

print(f"PASS all {len(templates)} installed result templates resolve through Jinja")
