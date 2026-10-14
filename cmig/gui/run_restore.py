"""Which page a run belongs to, and the banner shown when it is reopened (Qt-free)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cmig.io import project as proj

#: manifest `workflow_kind` -> page key
_WORKFLOW_PAGES = {
    "model_pool_search": "search",
    "multi_target_model_pool_search": "search",
    "gene_ko_search": "gene_ko",
    "strain_growth": "strain_growth",
    "abundance_impact": "ratio_impact",
    "host_microbe_bigg": "host",
    "host_search_bigg": "host_search",
    "dfba": "dfba",
    "spatial_preview": "spatial",
    "sweep": "sweep",
    "minimal_medium": "medium",
    "single": "check_growth",
}
#: summary file -> page key, for runs whose manifest names no workflow kind
_SUMMARY_PAGES = {
    "search_summary.json": "search",
    "spatial_summary.json": "spatial",
    "dfba_summary.json": "dfba",
}
#: run folder kind (the GUI names folders `<kind>-YYYYMMDD-HHMMSS[-N]`) -> page key
_FOLDER_PAGES = {
    "search": "search", "gene-ko": "gene_ko", "strain-growth": "strain_growth",
    "abundance-impact": "ratio_impact", "community": "community", "host-microbe": "host",
    "host-search": "host_search", "dfba": "dfba", "spatial": "spatial",
    "medium-growth": "medium", "minimal-medium": "medium", "sweep": "sweep",
    "check-growth": "check_growth",
}
_STAMP = re.compile(r"-\d{8}-\d{6}(?:-\d+)?$")


def _manifest_kind(run_dir: Path) -> str | None:
    try:
        manifest = json.loads((run_dir / "manifest.json").read_text())
    except (OSError, ValueError, RecursionError):
        return None
    kind = manifest.get("workflow_kind") if isinstance(manifest, dict) else None
    return kind if isinstance(kind, str) else None


def analysis_for_run(run_dir: Path) -> tuple[str | None, dict[str, Any] | None, str]:
    run_dir = Path(run_dir)
    record, problem = proj.read_run_request(run_dir)
    if record is not None:
        return str(record["analysis"]), record, ""
    kind = _manifest_kind(run_dir)
    if kind in _WORKFLOW_PAGES:
        return _WORKFLOW_PAGES[kind], None, problem
    for name, key in _SUMMARY_PAGES.items():
        if (run_dir / name).exists():
            return key, None, problem
    if (run_dir / "nodes.parquet").exists():
        return "community", None, problem
    match = _STAMP.search(run_dir.name)
    prefix = run_dir.name[: match.start()] if match else ""
    return _FOLDER_PAGES.get(prefix), None, problem


def banner_text(run_name: str, record: dict[str, Any] | None, problem: str,
                notes: list[str]) -> str:
    if record is None:
        return (f"Inputs for {run_name} cannot be restored"
                + (f": {problem}." if problem else "; the inputs on screen are unchanged."))
    text = f"Inputs restored from {run_name}."
    if notes:
        text += " Not restored: " + "; ".join(notes) + "."
    return text


def request_models_and_media(values: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Model ids (picker lists) and medium refs (`preset:`/`medium:`) named in a snapshot."""
    models: list[str] = []
    media: list[str] = []
    for value in values.values():
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            models.extend(v for v in value if v not in models)
        elif isinstance(value, str) and value.startswith(("preset:", "medium:")):
            media.append(value)
    return models, media
