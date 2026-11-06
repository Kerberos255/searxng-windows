"""Keep engines without native time filters in SearXNG searches.

This is a narrow, idempotent source patch. Refuse unknown upstream layouts
instead of silently installing a broken or ineffective modification.
"""

from __future__ import annotations

import sys
from pathlib import Path

_RELATIVE_TARGET = Path("searxng/searx/search/processors/abstract.py")
_OLD_SKIP = (
    "        # if time_range is not supported, skip\n"
    "        if search_query.time_range and not self.engine.time_range_support:\n"
    "            return None\n"
)
_NEW_SKIP = (
    "        # Search without a date restriction on engines lacking this feature.\n"
    "        effective_time_range = (\n"
    "            search_query.time_range if self.engine.time_range_support else None\n"
    "        )\n"
)
_OLD_FIELD = '            "time_range": search_query.time_range,\n'
_NEW_FIELD = '            "time_range": effective_time_range,\n'


def patch_source(source: str) -> tuple[str, bool]:
    # Already patched? No rewrite or timestamp change needed.
    if (
        _NEW_SKIP in source
        and source.count(_NEW_FIELD) == 1
        and _OLD_SKIP not in source
        and _OLD_FIELD not in source
    ):
        return source, False
    if source.count(_OLD_SKIP) != 1 or source.count(_OLD_FIELD) != 1:
        raise ValueError("unexpected SearXNG engine processor layout")
    patched = source.replace(_OLD_SKIP, _NEW_SKIP, 1).replace(_OLD_FIELD, _NEW_FIELD, 1)
    if patched.count(_NEW_SKIP) != 1 or patched.count(_NEW_FIELD) != 1:
        raise ValueError("date fallback patch verification failed")
    return patched, True


def patch_file(root: Path) -> bool:
    target = root / _RELATIVE_TARGET
    if not target.is_file():
        raise FileNotFoundError(f"search processor not found: {target}")
    original = target.read_bytes()
    line_endings = b"\r\n" if b"\r\n" in original else b"\n"
    source = original.decode("utf-8").replace("\r\n", "\n")
    updated, changed = patch_source(source)
    if changed:
        encoded = updated.replace("\n", line_endings.decode("ascii")).encode("utf-8")
        target.write_bytes(encoded)
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: patch_time_range_engines.py INSTALL_ROOT", file=sys.stderr)
        raise SystemExit(2)
    try:
        changed = patch_file(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Could not apply date fallback patch: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Engine date fallback patch applied." if changed else "Engine date fallback patch already applied.")
