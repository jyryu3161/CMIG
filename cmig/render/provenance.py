"""Deterministic provenance sidecars for publication figure rendering."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
from typing import Any

from cmig.io.atomic import atomic_write_text

RENV_LOCK = Path(__file__).resolve().parent.parent / "render_r" / "renv.lock"


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_rows_sha256(rows: list[dict[str, Any]]) -> str:
    """Hash rows using a stable JSON representation for non-R renderers."""
    payload = json.dumps(
        rows,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def parse_r_provenance(stdout: str) -> tuple[str | None, dict[str, str]]:
    """Parse machine-readable runtime lines emitted by the bundled R scripts."""
    version: str | None = None
    packages: dict[str, str] = {}
    for line in stdout.splitlines():
        fields = line.split("\t")
        if len(fields) == 2 and fields[0] == "CMIG_R_VERSION":
            version = fields[1]
        elif len(fields) == 3 and fields[0] == "CMIG_R_PACKAGE":
            packages[fields[1]] = fields[2]
    return version, dict(sorted(packages.items()))


def write_render_provenance(
    out: Path,
    *,
    renderer: str,
    spec_path: Path,
    input_sha256: str,
    input_serialization: str,
    script: Path | None = None,
    rscript: str | None = None,
    r_stdout: str = "",
) -> Path:
    """Write a provenance record only after a figure was rendered successfully."""
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "renderer": renderer,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "input": {
            "serialization": input_serialization,
            "sha256": input_sha256,
        },
        "figure": {
            "file": out.name,
            "sha256": sha256_file(out),
        },
        "figure_spec": {
            "file": spec_path.name,
            "sha256": sha256_file(spec_path),
        },
    }
    if RENV_LOCK.exists():
        payload["renv_lock"] = {
            "file": "cmig/render_r/renv.lock",
            "sha256": sha256_file(RENV_LOCK),
        }
    if renderer == "r":
        r_version, packages = parse_r_provenance(r_stdout)
        payload["runtime"].update(
            {
                "rscript": rscript,
                "r_version": r_version,
                "r_packages": packages,
            }
        )
        if script is not None:
            payload["script"] = {
                "file": f"cmig/render_r/{script.name}",
                "sha256": sha256_file(script),
            }
    elif renderer == "matplotlib":
        try:
            matplotlib_version = importlib.metadata.version("matplotlib")
        except importlib.metadata.PackageNotFoundError:  # pragma: no cover - guarded by caller
            matplotlib_version = None
        payload["runtime"]["matplotlib"] = matplotlib_version

    sidecar = out.with_name(out.name + ".render_provenance.json")
    # R5-P3 V3: a failed rewrite must not replace a good provenance record with a partial one.
    atomic_write_text(
        sidecar, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    )
    return sidecar
