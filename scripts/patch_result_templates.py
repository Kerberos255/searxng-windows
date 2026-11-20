"""Normalize SearXNG HTML result-template keys on Windows (issue #6).

Upstream uses os.path.join to collect registry keys but forward slashes when
resolving them. Refuse unknown upstream layouts rather than patch blindly.
"""
from __future__ import annotations

import sys
from pathlib import Path

_TARGET = Path("searxng/searx/webapp.py")
_REQUIRED_TEMPLATE = Path("searxng/searx/templates/simple/result_templates/default.html")
_OLD = "result_templates = get_result_templates(templates_path)"
_NEW = 'result_templates = {name.replace(os.sep, "/") for name in get_result_templates(templates_path)}'


def patch_source(source: str) -> tuple[str, bool]:
    if source.count(_NEW) == 1 and _OLD not in source:
        return source, False
    if source.count(_OLD) != 1 or _NEW in source:
        raise ValueError("unexpected SearXNG result-template registry layout")
    updated = source.replace(_OLD, _NEW, 1)
    if updated.count(_NEW) != 1:
        raise ValueError("result-template patch verification failed")
    return updated, True


def patch_file(root: Path) -> bool:
    target = root / _TARGET
    if not target.is_file():
        raise FileNotFoundError(f"SearXNG webapp missing: {target}")
    if not (root / _REQUIRED_TEMPLATE).is_file():
        raise FileNotFoundError(f"HTML result template is missing: {root / _REQUIRED_TEMPLATE}")
    original = target.read_bytes()
    newline = "\r\n" if b"\r\n" in original else "\n"
    source = original.decode("utf-8").replace("\r\n", "\n")
    updated, changed = patch_source(source)
    if changed:
        target.write_bytes(updated.replace("\n", newline).encode("utf-8"))
    return changed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: patch_result_templates.py INSTALL_ROOT", file=sys.stderr)
        raise SystemExit(2)
    try:
        changed = patch_file(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Windows result-template patch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print("Windows result-template patch applied." if changed else "Windows result-template patch already applied.")
