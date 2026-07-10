"""Writers for dFBA sensitivity and numerical-audit outputs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cmig.core.dfba import DfbaSensitivityResult

DFBA_SENSITIVITY_COLUMNS = (
    "dt",
    "km",
    "status",
    "n_steps",
    "final_t",
    "final_biomass",
    "final_concentrations",
    "depletion_times",
    "max_concentration_residual",
    "max_biomass_residual",
    "relative_biomass_error_to_finest_dt",
)


def write_dfba_sensitivity(
    result: DfbaSensitivityResult,
    out_dir: str | Path,
    *,
    provenance: dict[str, Any] | None = None,
) -> list[str]:
    """Write lossless JSON plus analysis-ready CSV."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = [asdict(row) for row in result.rows]
    max_concentration_residual = max(
        (row.max_concentration_residual for row in result.rows), default=0.0
    )
    max_biomass_residual = max(
        (row.max_biomass_residual for row in result.rows), default=0.0
    )
    payload = {
        "dfba_sensitivity_schema_version": "1.0",
        "source_config": asdict(result.source_config),
        "provenance": provenance or {},
        "n_runs": len(result.rows),
        "acceptance": {
            "all_statuses_completed": all(row.status == "completed" for row in result.rows),
            "concentration_balance_tolerance": 1e-9,
            "biomass_balance_tolerance": 1e-9,
            "max_concentration_residual": max_concentration_residual,
            "max_biomass_residual": max_biomass_residual,
            "balance_passed": (
                max_concentration_residual <= 1e-9 and max_biomass_residual <= 1e-9
            ),
        },
        "rows": rows,
    }
    (out / "dfba_sensitivity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"
    )
    with open(out / "dfba_sensitivity.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DFBA_SENSITIVITY_COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["final_concentrations"] = json.dumps(
                record["final_concentrations"], sort_keys=True, separators=(",", ":")
            )
            record["depletion_times"] = json.dumps(
                record["depletion_times"], sort_keys=True, separators=(",", ":")
            )
            writer.writerow(record)
    return ["dfba_sensitivity.json", "dfba_sensitivity.csv"]
