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


#: The `--allow-unknown-medium` option, in GUI words (medium_policy v3). Medium ids the model has
#: no exchange for are always skipped and listed; the option only lets a REFUSED medium run.
MISMATCHED_MEDIUM_OPTION = "Run a mismatched medium anyway (drops its unmatched rows; degraded)"
MISMATCHED_MEDIUM_TOOLTIP = (
    "Medium ids the models have no exchange for are always skipped and listed — that needs no "
    "option. This option only matters when the medium is refused: when none of its ids matches "
    "the models (another namespace), or when ids are written in another notation of an exchange "
    "the models have (e.g. EX_glc_D_m for EX_glc__D_m). It then drops those rows and the run is "
    "marked degraded. Renaming the rows in the medium file is the fix."
)

_NEAR_MISS_PAIR = re.compile(r"(EX_\S+?) -> (EX_[^\s,.;]+)")


def medium_text(ref: str, *, skip_unknown: bool = False) -> str:
    """How a run's medium is named; a run that allowed a mismatched medium says so."""
    if not ref:
        return "model default"
    mode = "exact, mismatched medium allowed" if skip_unknown else "exact"
    return f"{ref.partition(':')[2] or ref} ({mode})"


def medium_refusal_hint(reason: str) -> str:
    """What to do about a refused medium, from the CLI's refusal text ("" if not a medium one).

    A near miss is the same nutrient misspelled: rename it (dropping it would run without it).
    """
    pairs = _NEAR_MISS_PAIR.findall(reason) if "another notation" in reason else []
    option = f"ticking “{MISMATCHED_MEDIUM_OPTION}” would drop them instead"
    if pairs:
        renames = ", ".join(f"{old} to {new}" for old, new in pairs)
        return f" — rename {renames} in the medium file ({option})"
    if "none of the medium's" in reason or "no counterpart" in reason:
        return (" — the medium matches none of this model's exchanges: write the medium in this "
                f"model's namespace ({option})")
    return ""


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
    note += _not_applicable_note(summary)
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


def _not_applicable_note(summary: dict[str, object]) -> str:
    """Medium ids this model has no exchange for: dropped, LP unchanged, not a degradation."""
    ids = summary.get("medium_not_applicable_to_pool")
    if not isinstance(ids, list) or not ids:
        return ""
    matched = summary.get("medium_matched")
    fraction = (
        f"; {matched.get('matched')}/{matched.get('requested')} matched"
        if isinstance(matched, dict) and matched.get("requested") else ""
    )
    return (f" · {len(ids)} medium ids not applicable to this model "
            f"({', '.join(str(x) for x in ids)}){fraction}")


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
