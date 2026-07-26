"""Writers for publication-oriented model quality audits."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from cmig.core.model_quality import ModelQualityReport

MODEL_QUALITY_SUMMARY_COLUMNS = (
    "model_id",
    "source_path",
    "source_checksum",
    "n_reactions",
    "n_metabolites",
    "n_genes",
    "n_exchanges",
    "solve_status",
    "objective_value",
    # A-B9: >1 means the "objective value" above is not a growth rate.
    "n_objective_terms",
    "solve_seconds",
    "gene_association_coverage",
    "metabolite_formula_coverage",
    "metabolite_charge_coverage",
    "reaction_annotation_coverage",
    "metabolite_annotation_coverage",
    "gene_annotation_coverage",
    "n_mass_checkable",
    "n_mass_balanced",
    "n_mass_imbalanced",
    "n_mass_uncheckable",
    "mass_balance_pass_rate",
    "n_dead_end_metabolites",
    "blocked_reactions_checked",
    "n_blocked_reactions",
)


def _summary_row(report: ModelQualityReport) -> dict[str, Any]:
    payload = report.as_dict()
    return {column: payload[column] for column in MODEL_QUALITY_SUMMARY_COLUMNS}


def write_model_quality_reports(
    reports: list[ModelQualityReport], out_dir: str | Path
) -> list[str]:
    """Write a lossless JSON report and a flat CSV summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_quality_schema_version": "1.0",
        "n_models": len(reports),
        "reports": [report.as_dict() for report in reports],
    }
    (out / "model_quality.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    with open(out / "model_quality.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MODEL_QUALITY_SUMMARY_COLUMNS)
        writer.writeheader()
        for report in reports:
            writer.writerow(_summary_row(report))
    return ["model_quality.json", "model_quality.csv"]
