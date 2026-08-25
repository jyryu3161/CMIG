#!/usr/bin/env python3
"""Release-version alignment guard (docs/release-drafts/0.2.0-version-alignment.md).

Standard library only. Reads every public version surface, prints each
source/value pair, and fails when they disagree. On a ``vX.Y.Z`` tag (pass the
tag as argv[1] or set GITHUB_REF_NAME) it additionally requires the tag, every
metadata value, and the finalized changelog heading to equal ``X.Y.Z`` and a
real CITATION release date.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent


def _pyproject_version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return str(data["project"]["version"])


def _package_version() -> str:
    # cmig/__init__.py must stay importable without solver/GUI extras; read the
    # literal instead of importing to keep this guard dependency-free.
    text = (ROOT / "cmig" / "__init__.py").read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("cmig/__init__.py: __version__ literal not found")
    return match.group(1)


def _citation() -> tuple[str, str | None]:
    version = None
    released = None
    for line in (ROOT / "CITATION.cff").read_text().splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("date-released:"):
            released = line.split(":", 1)[1].strip().strip('"')
    if version is None:
        raise SystemExit("CITATION.cff: top-level version not found")
    return version, released


def _zenodo_version() -> str:
    data = json.loads((ROOT / ".zenodo.json").read_text())
    version = data.get("version")
    if not version:
        raise SystemExit(".zenodo.json: top-level version missing")
    return str(version)


def _marketplace_version() -> str:
    data = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    return str(data["metadata"]["version"])


def _lock_version() -> str:
    data = tomllib.loads((ROOT / "uv.lock").read_text())
    for package in data.get("package", []):
        if package.get("name") == "cmig":
            return str(package["version"])
    raise SystemExit("uv.lock: cmig package entry not found")


def _changelog_heading_version() -> str | None:
    """First finalized release heading. An empty `[Unreleased]` section above it is
    standard Keep-a-Changelog structure and is skipped, not treated as unfinalized."""
    for line in (ROOT / "CHANGELOG.md").read_text().splitlines():
        match = re.match(r"## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}", line)
        if match:
            return match.group(1)
    return None


def main() -> int:
    tag = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_REF_NAME", "")).strip()
    values = {
        "pyproject.toml project.version": _pyproject_version(),
        "cmig/__init__.py __version__": _package_version(),
        "CITATION.cff version": _citation()[0],
        ".zenodo.json version": _zenodo_version(),
        ".claude-plugin/marketplace.json metadata.version": _marketplace_version(),
        "uv.lock cmig": _lock_version(),
    }
    for source, value in values.items():
        print(f"  {source:48s} {value}")
    distinct = sorted(set(values.values()))
    ok = len(distinct) == 1
    if not ok:
        print(f"VERSION MISMATCH: {distinct}", file=sys.stderr)

    if re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        release = tag[1:]
        print(f"  tag {tag} → release build checks for {release}")
        if distinct != [release]:
            print(f"tag {tag} does not match metadata {distinct}", file=sys.stderr)
            ok = False
        heading = _changelog_heading_version()
        print(f"  CHANGELOG finalized heading                      {heading}")
        if heading != release:
            print(
                f"CHANGELOG top release heading must be [{release}] - YYYY-MM-DD "
                f"(found: {heading})", file=sys.stderr,
            )
            ok = False
        released = _citation()[1]
        print(f"  CITATION.cff date-released                       {released}")
        if not released or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", released):
            print("CITATION.cff date-released must be a real date on a tag", file=sys.stderr)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
