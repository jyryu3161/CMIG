"""Per-model browse/search index under ``models/.index/<sha256>.json`` (Qt-free).

A cache for the model browser and project search only — never an analysis input, a taxonomy
row or a CLI argument. A file that cannot be read, has another schema, or belongs to another
model file reads as missing and is rebuilt.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from cmig.io.atomic import atomic_write_text

INDEX_SCHEMA_VERSION = 1
_KEYS = ("reactions", "metabolites", "genes", "exchanges", "objective")


def index_path(root: Path, sha256: str) -> Path:
    return Path(root) / "models" / ".index" / f"{sha256}.json"


def _bound(value: object) -> float | None:
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) else None


def _charge(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number == int(number) else None


def index_from_model(model: Any) -> dict[str, Any]:
    from cobra.util.solver import linear_reaction_coefficients

    reactions = [
        {
            "id": str(r.id),
            "name": str(r.name or ""),
            "metabolites": {str(m.id): float(c) for m, c in r.metabolites.items()},
            "lower": _bound(r.lower_bound),
            "upper": _bound(r.upper_bound),
            "gpr": str(r.gene_reaction_rule or ""),
            "subsystem": str(r.subsystem or ""),
        }
        for r in model.reactions
    ]
    metabolites = [
        {
            "id": str(m.id),
            "name": str(m.name or ""),
            "formula": str(m.formula or ""),
            "charge": _charge(m.charge),
            "compartment": str(m.compartment or ""),
        }
        for m in model.metabolites
    ]
    genes = [
        {"id": str(g.id), "name": str(g.name or ""),
         "reactions": sorted(str(r.id) for r in g.reactions)}
        for g in model.genes
    ]
    objective = [
        {"id": str(r.id), "coef": float(c)}
        for r, c in linear_reaction_coefficients(model).items()
    ]
    return {
        "reactions": reactions,
        "metabolites": metabolites,
        "genes": genes,
        "exchanges": sorted(str(r.id) for r in model.exchanges),
        "objective": sorted(objective, key=lambda item: str(item["id"])),
    }


def write_index(root: Path, sha256: str, model_id: str, body: dict[str, Any]) -> Path:
    payload = {"schema_version": INDEX_SCHEMA_VERSION, "sha256": sha256,
               "model_id": model_id, **body}
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return atomic_write_text(index_path(root, sha256), text)


def load_index(root: Path, sha256: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(index_path(root, sha256).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != INDEX_SCHEMA_VERSION
        or payload.get("sha256") != sha256
        or not all(isinstance(payload.get(key), list) for key in _KEYS)
    ):
        return None
    return payload


def build_index_file(root: Path, model_file: Path, sha256: str, model_id: str) -> Path:
    """Read one model copy and write its index. Raises on an unreadable model or disk error."""
    from cmig.io.model_import import load_cobra_model

    return write_index(root, sha256, model_id, index_from_model(load_cobra_model(model_file)))


def search_rows(index: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(kind, id, name) for every reaction, metabolite and gene; exchanges are reactions."""
    rows: list[tuple[str, str, str]] = []
    for kind, key in (("reaction", "reactions"), ("metabolite", "metabolites"),
                      ("gene", "genes")):
        for item in index.get(key) or []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                rows.append((kind, item["id"], str(item.get("name") or "")))
    return rows
