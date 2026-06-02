"""User model-pool helpers.

The product workflow assumes users prepare GEM files locally. This module only
discovers supported files and builds a MICOM-compatible taxonomy table; it does
not download or curate external models.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_MODEL_SUFFIXES = (".xml", ".sbml", ".xml.gz", ".sbml.gz", ".json", ".mat")


def is_supported_model_file(path: Path) -> bool:
    """Return True for cobra-readable GEM file names CMIG accepts as pool members."""
    name = path.name.lower()
    return path.is_file() and any(name.endswith(suffix) for suffix in SUPPORTED_MODEL_SUFFIXES)


def _base_name(path: Path) -> str:
    name = path.name
    for suffix in sorted(SUPPORTED_MODEL_SUFFIXES, key=len, reverse=True):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def member_id_from_path(path: Path) -> str:
    """Derive a stable MICOM member id from a local file name."""
    member_id = re.sub(r"[^A-Za-z0-9_]+", "_", _base_name(path)).strip("_")
    if not member_id:
        member_id = "member"
    if not re.match(r"^[A-Za-z_]", member_id):
        member_id = f"m_{member_id}"
    return member_id


def discover_model_files(model_dir: str | Path, *, recursive: bool = False) -> list[Path]:
    """Discover supported GEM files in deterministic order."""
    root = Path(model_dir)
    if not root.exists():
        raise ValueError(f"model directory not found: {root}")
    if not root.is_dir():
        raise ValueError(f"model path is not a directory: {root}")
    candidates = root.rglob("*") if recursive else root.iterdir()
    files = sorted(p.resolve() for p in candidates if is_supported_model_file(p))
    if not files:
        raise ValueError(
            f"no supported model files found in {root} "
            f"(supported: {', '.join(SUPPORTED_MODEL_SUFFIXES)})"
        )
    return files


def taxonomy_from_model_dir(model_dir: str | Path, *, recursive: bool = False) -> Any:
    """Build a MICOM-compatible taxonomy DataFrame from a directory of GEM files."""
    import pandas as pd

    root = Path(model_dir).resolve()
    rows: list[dict[str, object]] = []
    bases: dict[str, list[Path]] = {}
    for model_path in discover_model_files(model_dir, recursive=recursive):
        bases.setdefault(member_id_from_path(model_path), []).append(model_path)
    for base in sorted(bases):
        paths = bases[base]
        for model_path in paths:
            member_id = base
            if len(paths) > 1:
                member_id = f"{base}_{_path_digest(model_path, root=root)}"
            rows.append({"id": member_id, "file": str(model_path), "abundance": 1.0})
    return pd.DataFrame.from_records(rows)


def _path_digest(path: Path, *, root: Path) -> str:
    """Short stable suffix for filenames that sanitize to the same member id."""
    try:
        key = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        key = path.resolve().as_posix()
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class PoolModelDiagnostic:
    """Per-model import and target-exchange diagnostic for search readiness."""

    member_id: str
    file: str
    readable: bool
    model_id: str | None
    n_reactions: int | None
    n_exchanges: int | None
    n_biomass: int | None
    has_target_exchange: bool
    matching_exchanges: tuple[str, ...]
    warnings: tuple[str, ...]
    error: str | None = None


def diagnose_model_pool(taxonomy: Any, target_metabolite: str) -> list[PoolModelDiagnostic]:
    """Load each pool model enough to report target-exchange and biomass readiness."""
    from cmig.io.model_import import exchange_metabolite_ids, import_model

    def exchange_metabolite(exchange_id: str) -> str:
        name = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
        for suffix in ("_e", "_m", "_lumen", "_blood"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    diagnostics: list[PoolModelDiagnostic] = []
    for record in taxonomy.to_dict("records"):
        member_id = str(record["id"])
        model_file = str(record["file"])
        try:
            summary = import_model(model_file)
            exchange_mets = set(exchange_metabolite_ids(summary))
            matching = tuple(
                sorted(
                    ex for ex in summary.exchanges
                    if exchange_metabolite(ex) == target_metabolite
                )
            )
            warnings: list[str] = []
            if not summary.biomass_reactions:
                warnings.append("biomass objective not detected")
            if target_metabolite not in exchange_mets:
                warnings.append(f"target exchange not detected for {target_metabolite}")
            diagnostics.append(
                PoolModelDiagnostic(
                    member_id=member_id,
                    file=model_file,
                    readable=True,
                    model_id=summary.model_id,
                    n_reactions=summary.n_reactions,
                    n_exchanges=len(summary.exchanges),
                    n_biomass=len(summary.biomass_reactions),
                    has_target_exchange=target_metabolite in exchange_mets,
                    matching_exchanges=matching,
                    warnings=tuple(warnings),
                )
            )
        except Exception as e:
            diagnostics.append(
                PoolModelDiagnostic(
                    member_id=member_id,
                    file=model_file,
                    readable=False,
                    model_id=None,
                    n_reactions=None,
                    n_exchanges=None,
                    n_biomass=None,
                    has_target_exchange=False,
                    matching_exchanges=(),
                    warnings=("model import failed",),
                    error=str(e),
                )
            )
    return diagnostics
