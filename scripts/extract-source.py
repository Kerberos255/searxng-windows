"""Safely extract upstream SearXNG ZIP archives on Windows."""
from __future__ import annotations

import argparse
import shutil
import stat
import sys
import zipfile
from pathlib import Path

_WINDOWS_INVALID = frozenset('<>:"\\|?*')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _safe_parts(member_name: str) -> tuple[str, ...]:
    normalized = member_name.replace("\\", "/").rstrip("/")
    if not normalized or normalized.startswith("/"):
        raise ValueError(f"Unsafe archive path: {member_name!r}")

    parts = tuple(normalized.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Unsafe archive path: {member_name!r}")
    if len(parts) < 2:
        raise ValueError(f"Archive entry is missing its top-level folder: {member_name!r}")
    return parts


def _windows_compatible(parts: tuple[str, ...]) -> bool:
    for part in parts:
        if any(character in _WINDOWS_INVALID or ord(character) < 32 for character in part):
            return False
        if part.endswith((" ", ".")):
            return False
        if part.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
            return False
    return True


def extract_source_archive(archive_path: Path, destination: Path) -> tuple[int, int]:
    archive_path = Path(archive_path)
    destination = Path(destination)

    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Destination must be empty: {destination}")

    destination.mkdir(parents=True, exist_ok=True)
    extracted_files = 0
    skipped_entries = 0

    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = []
            for info in archive.infolist():
                if not info.filename.rstrip("/"):
                    continue
                if info.is_dir() and info.filename.rstrip("/").count("/") == 0:
                    continue
                entries.append((info, _safe_parts(info.filename)))
            roots = {parts[0] for _, parts in entries}
            if len(roots) != 1:
                raise ValueError("Expected a GitHub source archive with one top-level directory.")
            root = next(iter(roots))

            for info, parts in entries:
                if parts[0] != root:
                    raise ValueError(f"Unexpected archive root in {info.filename!r}")
                relative_parts = parts[1:]
                if not relative_parts:
                    continue
                if not _windows_compatible(relative_parts):
                    skipped_entries += 1
                    continue

                if stat.S_ISLNK(info.external_attr >> 16):
                    skipped_entries += 1
                    continue

                target = destination.joinpath(*relative_parts)
                try:
                    target.resolve().relative_to(destination.resolve())
                except ValueError as error:
                    raise ValueError(f"Archive entry escapes the destination: {info.filename!r}") from error

                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                extracted_files += 1

        required_files = ("setup.py", "requirements.txt", "searx/webapp.py")
        missing = [name for name in required_files if not (destination / name).is_file()]
        if missing:
            raise ValueError(
                "Extracted archive is incomplete; missing required files: "
                + ", ".join(missing)
            )

        return extracted_files, skipped_entries
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Upstream SearXNG ZIP archive")
    parser.add_argument("destination", type=Path, help="Empty destination directory")
    args = parser.parse_args()

    try:
        extracted, skipped = extract_source_archive(args.archive, args.destination)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"SearXNG source extraction failed: {error}", file=sys.stderr)
        return 1

    print(
        f"SearXNG source extracted: {extracted} files; "
        f"skipped {skipped} Windows-incompatible or unsupported entries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
