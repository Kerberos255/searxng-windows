"""Enable API-first default search routing in the installed SearXNG webapp.

Only patch the known upstream hook, preserving CRLF and refusing layout drift.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TARGET = Path("searxng/searx/webapp.py")
_OLD = "        search_obj = searx.search.SearchWithPlugins(search_query, sxng_request, sxng_request.user_plugins)"
_NEW = (
    "        from searx.engines.api_pool import apply_default_search_priority\n"
    "        apply_default_search_priority(search_query, raw_text_query, sxng_request.form)\n"
    + _OLD
)


def patch_source(source: str) -> tuple[str, bool]:
    if source.count(_NEW) == 1:
        return source, False
    if source.count(_OLD) != 1 or "apply_default_search_priority(" in source:
        raise ValueError("unexpected SearXNG default search layout")
    return source.replace(_OLD, _NEW, 1), True


def patch_file(root: Path) -> bool:
    path = root / _TARGET
    data = path.read_bytes()
    newline = "\r\n" if b"\r\n" in data else "\n"
    updated, changed = patch_source(data.decode("utf-8").replace("\r\n", "\n"))
    if changed:
        path.write_bytes(updated.replace("\n", newline).encode("utf-8"))
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_default_search_priority.py INSTALL_ROOT")
    try:
        changed = patch_file(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Default API-first search patch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Default API-first search patch applied." if changed else "Default API-first search patch already applied.")
