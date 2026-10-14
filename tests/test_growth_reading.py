from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmig.gui.growth import (
    latest_check_growth,
    medium_text,
    read_growth,
    run_clock,
    solver_text,
)
from cmig.io import project as proj


def _summary(tmp_path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "status": "ok", "solver": "gurobi", "growth_feasible": True, "growth_threshold": 1e-6,
        "warnings": [], "methods": {"FBA": {"status": "optimal", "objective": 0.8739}},
    }
    payload.update(overrides)
    run = tmp_path / "check-growth-20261014-103100"
    run.mkdir(exist_ok=True)
    (run / "single_summary.json").write_text(json.dumps(payload))
    return run


def _read(run: Path, warning: str | None = None):
    return read_growth(run, objective_warning=warning, medium="western_diet (exact)",
                       finished="10:31")


def test_growth_ok(tmp_path: Path) -> None:
    reading = _read(_summary(tmp_path))
    assert reading.symbol == "✓"
    assert reading.text == ("Growth 0.8739 h⁻¹ · Gurobi (full-flux) · western_diet (exact) · "
                            "10:31")


def test_osqp_is_labelled_approximate(tmp_path: Path) -> None:
    assert "OSQP (QP-only approximate)" in _read(_summary(tmp_path, solver="osqp")).text


def test_no_growth_is_a_failure_not_zero(tmp_path: Path) -> None:
    run = _summary(tmp_path, growth_feasible=False,
                   methods={"FBA": {"status": "optimal", "objective": 0.0}})
    reading = _read(run)
    assert reading.symbol == "✗"
    assert reading.text.startswith("No growth (below 1e-06)")


def test_infeasible(tmp_path: Path) -> None:
    run = _summary(tmp_path, methods={"FBA": {"status": "infeasible", "objective": None}})
    assert _read(run).text.startswith("✗ Infeasible") is False  # symbol is separate
    assert _read(run).symbol == "✗" and _read(run).text.startswith("Infeasible")


def test_objective_that_is_not_growth_is_never_called_growth(tmp_path: Path) -> None:
    reading = _read(_summary(tmp_path), warning="283 objective terms")
    assert reading.symbol == "⚠"
    assert reading.text.startswith("Objective value 0.8739 — 283 objective terms")
    assert "Growth" not in reading.text


def test_degraded_is_flagged_with_its_warnings(tmp_path: Path) -> None:
    run = _summary(tmp_path, status="degraded", warnings=["dropped EX_x_e"])
    reading = _read(run)
    assert reading.symbol == "⚠" and "dropped EX_x_e" in reading.text


def test_unreadable_summary(tmp_path: Path) -> None:
    run = tmp_path / "check-growth-1"
    run.mkdir()
    reading = _read(run)
    assert reading.symbol == "✗" and reading.text.startswith("Failed:")


@pytest.mark.parametrize(("ref", "text"), [("", "model default"),
                                           ("preset:western_diet", "western_diet (exact)"),
                                           ("medium:mine", "mine (exact)")])
def test_medium_text(ref: str, text: str) -> None:
    assert medium_text(ref) == text


def test_solver_and_clock() -> None:
    assert solver_text("gurobi") == "Gurobi (full-flux)"
    assert solver_text(None) == "solver not recorded"
    assert run_clock("check-growth-20261014-103100") == "10:31"
    assert run_clock("odd") == ""


def test_latest_check_growth_matches_model_and_file(tmp_path: Path) -> None:
    root = tmp_path
    runs = root / "runs"
    for name, model, sha in (("check-growth-20261014-090000", "a", "s1"),
                             ("check-growth-20261014-100000", "a", "s1"),
                             ("check-growth-20261014-110000", "a", "OLD"),
                             ("check-growth-20261014-120000", "b", "s2")):
        run = runs / name
        run.mkdir(parents=True)
        proj.write_run_request(run, "check_growth", {"model": model, "sha256": sha},
                               models=[model], media=[], cmig_version="0")
    found = latest_check_growth(root, "a", "s1")
    assert found is not None and found.name == "check-growth-20261014-100000"
    assert latest_check_growth(root, "c", "x") is None


def test_infeasible_run_as_the_cli_writes_it(tmp_path: Path) -> None:
    run = _summary(tmp_path, status="failed", growth_feasible=False,
                   methods={"FBA": {"status": "infeasible", "objective": None,
                                    "diagnostic": "FBA status=infeasible"}})
    reading = _read(run)
    assert reading.symbol == "✗"
    assert reading.text.startswith("Infeasible")
    assert "FBA status=infeasible" in reading.text
    assert reading.text.endswith("Gurobi (full-flux) · western_diet (exact) · 10:31")


def test_medium_text_names_skipped_metabolites() -> None:
    assert (medium_text("preset:western_diet", skip_unknown=True)
            == "western_diet (exact, model-lacking metabolites skipped)")
    assert medium_text("", skip_unknown=True) == "model default"
