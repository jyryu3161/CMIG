"""Reading a Check Growth run (`cmig single --fba`) for the model browser header (Qt-free).

Never reports a failed, infeasible or zero-growth run as growth, and never calls the value of
an objective that is not a growth rate "Growth".
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from cmig.io import project as proj

_CLOCK = re.compile(r"-(\d{8})-(\d{2})(\d{2})(\d{2})(?:-\d+)?$")


@dataclass(frozen=True)
class GrowthReading:
    symbol: str
    text: str


def solver_text(name: object) -> str:
    return {"gurobi": "Gurobi (full-flux)", "osqp": "OSQP (QP-only approximate)"}.get(
        str(name) if isinstance(name, str) else "", "solver not recorded"
    )


def medium_text(ref: str, *, skip_unknown: bool = False) -> str:
    """How a run's medium is named; a run that skipped model-lacking metabolites says so."""
    if not ref:
        return "model default"
    mode = "exact, model-lacking metabolites skipped" if skip_unknown else "exact"
    return f"{ref.partition(':')[2] or ref} ({mode})"


def failed_summary(run_dir: Path) -> bool:
    """True when the run's `single_summary.json` reads and records a failed solve."""
    try:
        summary = json.loads((Path(run_dir) / "single_summary.json").read_text())
    except (OSError, ValueError, RecursionError):
        return False
    return isinstance(summary, dict) and summary.get("status") == "failed"


def run_clock(run_name: str) -> str:
    match = _CLOCK.search(run_name)
    return "" if match is None else f"{match.group(2)}:{match.group(3)}"


def read_growth(run_dir: Path, *, objective_warning: str | None, medium: str,
                finished: str) -> GrowthReading:
    try:
        summary = json.loads((Path(run_dir) / "single_summary.json").read_text())
        fba = summary["methods"]["FBA"]
        if not isinstance(summary, dict) or not isinstance(fba, dict):
            raise ValueError("unexpected summary shape")
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        return GrowthReading("✗", f"Failed: the result could not be read ({exc})")
    tail = " · ".join(part for part in (solver_text(summary.get("solver")), medium, finished)
                      if part)
    run_status = str(summary.get("status", "unknown"))
    status = str(fba.get("status", "unknown"))
    if run_status == "failed":
        # e.g. an infeasible FBA: `cmig single` records it and exits 3. Name the solve status.
        label = ("Failed" if status in ("optimal", "unknown")
                 else status.replace("_", " ").capitalize())
        diagnostic = fba.get("diagnostic")
        detail = f" — {diagnostic}" if isinstance(diagnostic, str) and diagnostic else ""
        return GrowthReading("✗", f"{label}{detail} · {tail}")
    if status != "optimal":
        return GrowthReading("✗", f"{status.replace('_', ' ').capitalize()} · {tail}")
    value = fba.get("objective")
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return GrowthReading("✗", f"No objective value recorded · {tail}")
    warnings = [str(w) for w in summary.get("warnings") or []]
    note = f" · {'; '.join(warnings)}" if run_status == "degraded" and warnings else ""
    if objective_warning is not None:
        return GrowthReading(
            "⚠", f"Objective value {float(value):.4g} — {objective_warning} · {tail}{note}"
        )
    if not summary.get("growth_feasible"):
        threshold = summary.get("growth_threshold")
        below = f" (below {float(threshold):g})" if isinstance(threshold, (int, float)) else ""
        return GrowthReading("✗", f"No growth{below} · {tail}")
    symbol = "⚠" if run_status == "degraded" else "✓"
    return GrowthReading(symbol, f"Growth {float(value):.4g} h⁻¹ · {tail}{note}")


def latest_check_growth(root: Path, model_id: str, sha256: str) -> Path | None:
    """The newest Check Growth run recorded for exactly this model file, or None."""
    inputs = Path(root) / "runs" / "_inputs"
    found: list[Path] = []
    for path in inputs.glob("check-growth-*-request.json"):
        run_dir = Path(root) / "runs" / path.name.removesuffix("-request.json")
        record, _problem = proj.read_run_request(run_dir)
        if (record is not None and record.get("analysis") == "check_growth"
                and record["values"].get("model") == model_id
                and record["values"].get("sha256") == sha256 and run_dir.is_dir()):
            found.append(run_dir)
    return max(found, key=lambda p: p.name, default=None)
