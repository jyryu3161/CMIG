#!/usr/bin/env python3
"""Audit CMIG wheel/sdist members against an explicit publication allowlist."""

from __future__ import annotations

import argparse
import re
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
FORBIDDEN_PARTS = frozenset(
    {
        ".git",
        ".run",
        ".omc",
        ".bkit",
        ".Rlib",
        "models",
        "fixtures",
        "REVIEW",
        "__pycache__",
    }
)
FORBIDDEN_NAMES = frozenset({".env", "gurobi.lic", "credentials.json"})
SDIST_ALLOWED_ROOTS = frozenset(
    {
        "cmig",
        "tests",
        "scripts",
        "docs",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "CITATION.cff",
        "CHANGELOG.md",
        "RELEASE_CHECKLIST.md",
        ".gitignore",
        "PKG-INFO",
    }
)
SDIST_ALLOWED_DOCS = frozenset({"PUBLICATION_VALIDATION.md"})
DIST_INFO_RE = re.compile(r"^cmig-[^/]+\.dist-info$")


@dataclass(frozen=True)
class ArchiveMember:
    name: str
    size: int
    is_link: bool = False


def _members(archive: Path) -> tuple[str, list[ArchiveMember]]:
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as handle:
            return "wheel", [
                ArchiveMember(item.filename, item.file_size)
                for item in handle.infolist()
                if not item.is_dir()
            ]
    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, mode="r:gz") as handle:
            return "sdist", [
                ArchiveMember(item.name, item.size, item.issym() or item.islnk())
                for item in handle.getmembers()
                if item.isfile() or item.issym() or item.islnk()
            ]
    raise ValueError(f"unsupported distribution format: {archive}")


def _safe_parts(name: str) -> tuple[str, ...]:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"unsafe archive path: {name}")
    return tuple(part for part in path.parts if part not in {"", "."})


def _strip_sdist_root(parts: tuple[str, ...]) -> tuple[str, ...]:
    if parts and re.fullmatch(r"cmig-[^/]+", parts[0]):
        return parts[1:]
    return parts


def audit_archive(archive: Path) -> None:
    """Raise ValueError when an archive violates the release allowlist."""
    kind, members = _members(archive)
    if not members:
        raise ValueError(f"empty distribution: {archive}")
    total_size = sum(member.size for member in members)
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise ValueError(
            f"distribution expands to {total_size} bytes "
            f"(limit {MAX_UNCOMPRESSED_BYTES}): {archive}"
        )

    violations: list[str] = []
    for member in members:
        try:
            parts = _safe_parts(member.name)
        except ValueError as error:
            violations.append(str(error))
            continue
        if member.is_link:
            violations.append(f"archive links are forbidden: {member.name}")
        if FORBIDDEN_PARTS.intersection(parts) or (parts and parts[-1] in FORBIDDEN_NAMES):
            violations.append(f"forbidden member: {member.name}")
            continue
        if kind == "wheel":
            root = parts[0] if parts else ""
            if root != "cmig" and not DIST_INFO_RE.fullmatch(root):
                violations.append(f"wheel member outside allowlist: {member.name}")
        else:
            relative = _strip_sdist_root(parts)
            root = relative[0] if relative else ""
            if root not in SDIST_ALLOWED_ROOTS:
                violations.append(f"sdist member outside allowlist: {member.name}")
            elif root == "docs" and (
                len(relative) != 2 or relative[1] not in SDIST_ALLOWED_DOCS
            ):
                violations.append(f"sdist documentation outside allowlist: {member.name}")
    if violations:
        sample = "\n  - ".join(violations[:20])
        raise ValueError(f"{archive} failed distribution audit:\n  - {sample}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    args = parser.parse_args(argv)
    for archive in args.archives:
        audit_archive(archive)
        print(f"distribution audit passed: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
