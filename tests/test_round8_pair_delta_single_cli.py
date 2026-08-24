"""Round 8 U1 — reachable pair/delta/single/minimal-medium workflows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("cobra")
pytest.importorskip("micom")

from cmig.cli.main import _inspect_run_dir, main  # noqa: E402
from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.core.medium_spec import MediumSpec  # noqa: E402
from cmig.core.pair import analyze_pair  # noqa: E402
from cmig.core.single_model import growth_feasible, solve_single_model  # noqa: E402
from cmig.synthetic_pair import build_pair_models, build_pair_taxonomy  # noqa: E402


def _medium(path: Path, glucose: float, acetate: float) -> Path:
    path.write_text(
        "exchange_id,uptake_limit\n"
        f"EX_glc__D_e,{glucose}\n"
        f"EX_ac_e,{acetate}\n"
    )
    return path


def _solve_result(
    members: list[str], external: dict[str, float], growth: float
) -> SolveResult:
    abundance = 1.0 / len(members)
    return SolveResult(
        objective=growth,
        member_growth={member: growth for member in members},
        abundances={member: abundance for member in members},
        external_exchange=external,
        member_exchange={member: {} for member in members},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=members,
    )


def test_growth_feasible_medium_is_translated_exactly_and_restores_model():
    producer, _consumer = build_pair_models()
    native = solve_single_model(producer).objective
    acetate_only = MediumSpec(
        uptake={"EX_glc__D_m": 0.0, "EX_ac_m": 10.0}
    )

    assert native == pytest.approx(10.0)
    assert growth_feasible(producer, medium=acetate_only, exact_medium=True) is False
    assert solve_single_model(producer).objective == pytest.approx(native)


def test_pair_projects_the_effective_community_medium_onto_both_mono_legs(tmp_path):
    taxonomy = build_pair_taxonomy(tmp_path / "models")
    acetate_only = MediumSpec(
        uptake={"EX_glc__D_e": 0.0, "EX_ac_e": 10.0}
    )

    result = analyze_pair(taxonomy, medium=acetate_only, exact_medium=True)

    # The old mismatch kept the producer's native glucose uptake and reported mono=10 here.
    assert result.mono_growth["producer"] == pytest.approx(0.0)
    assert result.mono_growth["consumer"] == pytest.approx(5.0)
    assert result.co_growth["producer"] == pytest.approx(0.0)
    assert result.co_growth["consumer"] == pytest.approx(5.0)
    assert result.interaction == "neutralism"


def test_all_four_cli_workflows_write_inspectable_integrity_checked_runs(tmp_path):
    taxonomy = build_pair_taxonomy(tmp_path / "models")
    taxonomy_path = tmp_path / "pair.csv"
    taxonomy.to_csv(taxonomy_path, index=False)
    glucose = _medium(tmp_path / "glucose.csv", 10.0, 0.0)

    pair_out = tmp_path / "pair_run"
    assert main([
        "pair", "--taxonomy", str(taxonomy_path), "--medium", str(glucose),
        "--exact-medium", "--assume-bigg-namespace", "--out", str(pair_out),
    ]) == 0
    assert (pair_out / "matrix.parquet").exists()

    producer_path = Path(str(taxonomy.loc[taxonomy["id"] == "producer", "file"].iloc[0]))
    single_out = tmp_path / "single_run"
    assert main([
        "single", "--model", str(producer_path), "--method", "both", "--fva",
        "--reaction-ko", "GLC2AC", "--medium", str(glucose), "--exact-medium",
        "--assume-bigg-namespace", "--out", str(single_out),
    ]) == 0
    single_summary = json.loads((single_out / "single_summary.json").read_text())
    assert single_summary["methods"]["FBA"]["objective"] == pytest.approx(10.0)
    assert single_summary["methods"]["pFBA"]["objective"] == pytest.approx(10.0)
    assert (single_out / "fva.csv").exists()
    assert (single_out / "reaction_knockouts.csv").exists()

    minimal_out = tmp_path / "minimal_run"
    assert main([
        "minimal-medium", "--model", str(producer_path), "--min-growth", "1",
        "--medium", str(glucose), "--exact-medium", "--assume-bigg-namespace",
        "--out", str(minimal_out),
    ]) == 0
    minimal = json.loads((minimal_out / "minimal_medium_summary.json").read_text())
    assert minimal["components"] == ["EX_glc__D_e"]
    assert minimal["limiting_nutrients"] == ["EX_glc__D_e"]

    baseline_dir, variant_dir = tmp_path / "baseline", tmp_path / "variant"
    build_tidy(_solve_result(["A"], {"ac": 2.0}, 0.4)).write(baseline_dir)
    build_tidy(_solve_result(["A", "B"], {"ac": 5.0, "but": 1.0}, 0.6)).write(
        variant_dir
    )
    delta_out = tmp_path / "delta_run"
    assert main([
        "delta", "--baseline", str(baseline_dir), "--variant", str(variant_dir),
        "--out", str(delta_out),
    ]) == 0
    delta = json.loads((delta_out / "delta_summary.json").read_text())
    assert delta["growth_delta"] == pytest.approx(0.2)
    assert delta["added_members"] == ["B"]

    for run_dir, kind in (
        (pair_out, "pair"),
        (single_out, "single"),
        (minimal_out, "minimal_medium"),
        (delta_out, "delta"),
    ):
        inspection = _inspect_run_dir(run_dir)
        assert inspection["kind"] == kind
        assert inspection["run_hash"]
        assert inspection["artifact_integrity"] == "verified"
        assert inspection["result_digest"]["match"] is True
