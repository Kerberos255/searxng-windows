"""Normalize SearXNG static registry keys on Windows for CSS, JS and images.

Upstream pathlib produces backslashes while templates use slash-style URLs.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TARGET = Path("searxng/searx/webapp.py")
_REQUIRED_CSS = Path("searxng/searx/static/themes/simple/sxng-ltr.min.css")
_OLD = "_STATIC_FILES = webutils.get_static_file_list()"
_NEW = '_STATIC_FILES = [name.replace(os.sep, "/") for name in webutils.get_static_file_list()]'


def patch_source(source: str) -> tuple[str, bool]:
    if source.count(_NEW) == 1 and _OLD not in source:
        return source, False
    if source.count(_OLD) != 1 or _NEW in source:
        raise ValueError("unexpected SearXNG static registry layout")
    return source.replace(_OLD, _NEW, 1), True


def patch_file(root: Path) -> bool:
    target = root / _TARGET
    if not (root / _REQUIRED_CSS).is_file():
        raise FileNotFoundError("SearXNG compiled CSS is missing")
    original = target.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    updated, changed = patch_source(original.decode("utf-8").replace("\r\n", "\n"))
    if changed:
        target.write_bytes(updated.replace("\n", newline).encode("utf-8"))
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_static_urls.py INSTALL_ROOT")
    try:
        changed = patch_file(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Windows static URL patch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Windows static URL patch applied." if changed else "Windows static URL patch already applied.")
