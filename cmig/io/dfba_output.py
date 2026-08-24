"""Writers for dFBA sensitivity and numerical-audit outputs."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pyarrow as pa

from cmig.core.dfba import DfbaSensitivityResult
from cmig.core.dfba_community import CommunityDfbaResult
from cmig.io.atomic import atomic_write_parquet

COMMUNITY_DFBA_TIMECOURSE_KIND = "community_dfba_timecourse"
COMMUNITY_DFBA_TIMECOURSE_SCHEMA_VERSION = "1.0"

COMMUNITY_DFBA_TIMECOURSE_SCHEMA = pa.schema([
    ("schema_version", pa.string()),
    ("kind", pa.string()),
    ("t", pa.float64()),
    ("entity_type", pa.string()),
    ("member", pa.string()),
    ("series", pa.string()),
    ("value", pa.float64()),
])

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
    "untracked_uptake",
    "warnings",
)


def community_timecourse_rows(result: CommunityDfbaResult) -> list[dict[str, Any]]:
    """Return a long-format timecourse with explicit member and shared-pool entities."""
    rows: list[dict[str, Any]] = []
    for point in result.timecourse:
        for member in result.members:
            rows.append({
                "t": point.t,
                "entity_type": "member",
                "member": member,
                "series": "biomass",
                "value": point.member_biomasses[member],
            })
            rows.append({
                "t": point.t,
                "entity_type": "member",
                "member": member,
                "series": "growth_rate",
                "value": point.member_growth_rates[member],
            })
        for exchange_id in result.managed_exchanges:
            rows.append({
                "t": point.t,
                "entity_type": "shared_pool",
                "member": None,
                "series": exchange_id,
                "value": point.concentrations[exchange_id],
            })
    return rows


def build_community_timecourse(result: CommunityDfbaResult) -> pa.Table:
    """Build the distinct, self-identifying community dFBA timecourse table."""
    return pa.Table.from_pylist(
        [
            {
                "schema_version": COMMUNITY_DFBA_TIMECOURSE_SCHEMA_VERSION,
                "kind": COMMUNITY_DFBA_TIMECOURSE_KIND,
                **row,
            }
            for row in community_timecourse_rows(result)
        ],
        schema=COMMUNITY_DFBA_TIMECOURSE_SCHEMA,
    )


def write_community_timecourse(result: CommunityDfbaResult, path: str | Path) -> Path:
    """Atomically publish a community dFBA timecourse as Parquet."""
    return atomic_write_parquet(path, build_community_timecourse(result))


def sensitivity_acceptance(result: DfbaSensitivityResult) -> dict[str, Any]:
    """The audit verdict for one dt x Km grid. Single source of truth for writer AND CLI.

    Round 5 (blocker 2): the first cut derived `interpretable` from the integration residuals and
    the untracked-uptake check only. A grid whose four runs were **all infeasible** therefore came
    back `interpretable: true` with exit 0 — the residuals really were 0.0, because nothing was
    integrated and `final_biomass` was just the initial condition (0.01 for every row). Certifying
    that as interpretable is worse than the original defect, because it carries an explicit stamp
    of validity. A grid can only answer "does the endpoint depend on dt/Km" if every run actually
    produced a trajectory, so the run statuses are now part of the verdict.
    """
    max_concentration_residual = max(
        (row.max_concentration_residual for row in result.rows), default=0.0
    )
    max_biomass_residual = max(
        (row.max_biomass_residual for row in result.rows), default=0.0
    )
    all_completed = all(row.status == "completed" for row in result.rows)
    no_untracked = not any(row.untracked_uptake for row in result.rows)
    balance_passed = (
        max_concentration_residual <= 1e-9 and max_biomass_residual <= 1e-9
    )
    n_infeasible = sum(1 for row in result.rows if row.status == "infeasible")
    n_stalled = sum(1 for row in result.rows if row.status == "stalled")
    # `infeasible` and `stalled` are NOT the same failure. An infeasible run produced no
    # trajectory at all (its "endpoint" is the initial condition). A stalled run integrated and
    # then stopped growing, which is often the real finding — so a grid that mixes stalled and
    # completed runs still has dynamics to compare and stays interpretable. Only when EVERY run
    # stalled is there nothing to be sensitive to.
    reasons: list[str] = []
    if not result.rows:
        reasons.append("the grid contains no runs")
    if n_infeasible:
        reasons.append(
            f"{n_infeasible} of {len(result.rows)} runs were infeasible and produced no "
            "trajectory; their endpoint is the initial condition, so the dt/Km comparison is "
            "meaningless"
        )
    elif result.rows and n_stalled == len(result.rows):
        reasons.append(
            "every run stalled before producing dynamics, so the endpoint is the initial "
            "condition for the whole grid; check that the tracked substrates actually support "
            "growth (a --close-untracked-uptake run needs every required nutrient in --initial)"
        )
    if not no_untracked:
        reasons.append(
            "growth was fed by untracked, never-depleting default-medium substrates; re-run "
            "with --close-untracked-uptake"
        )
    if not balance_passed:
        reasons.append("mass-balance residuals exceed tolerance")
    return {
        "all_statuses_completed": all_completed,
        "n_infeasible": n_infeasible,
        "n_stalled": n_stalled,
        "concentration_balance_tolerance": 1e-9,
        "biomass_balance_tolerance": 1e-9,
        "max_concentration_residual": max_concentration_residual,
        "max_biomass_residual": max_biomass_residual,
        "balance_passed": balance_passed,
        "no_untracked_uptake": no_untracked,
        "interpretable": bool(result.rows) and not reasons,
        "not_interpretable_because": reasons,
    }


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
    payload = {
        "dfba_sensitivity_schema_version": "1.0",
        "source_config": asdict(result.source_config),
        "provenance": provenance or {},
        "n_runs": len(result.rows),
        # Integration residuals alone cannot say the *experiment* is meaningful.
        "acceptance": sensitivity_acceptance(result),
        "warnings": sorted({w for row in result.rows for w in row.warnings}),
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
            record["untracked_uptake"] = json.dumps(
                record.get("untracked_uptake", {}), sort_keys=True, separators=(",", ":")
            )
            record["warnings"] = json.dumps(
                record.get("warnings", []), sort_keys=True, separators=(",", ":")
            )
            writer.writerow(record)
    return ["dfba_sensitivity.json", "dfba_sensitivity.csv"]
