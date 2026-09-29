"""Multi-target search Pareto trade-off figure (search_pareto.svg/.tiff).

Points come from every recorded evaluation row, only joint-optimal finite vectors are drawn,
the recorded ``pareto`` flag is the highlight and a figure failure never costs the run.
"""

from __future__ import annotations

import json
import re
from unittest.mock import patch

import pandas as pd

import cmig.cli.main as cli
from cmig.core.search_product import (
    FLUX_BASIS_CAPABILITY,
    FLUX_BASIS_JOINT,
    FLUX_BASIS_NONE,
    MultiTargetRank,
    MultiTargetSearchResult,
)

PARETO_FILES = ("search_pareto.svg", "search_pareto.tiff")


def _row(members, fluxes, *, rank=1, status="optimal", pareto=False,
         basis=FLUX_BASIS_JOINT, missing=()):
    score = sum(fluxes.values()) if status == "optimal" else float("-inf")
    return MultiTargetRank(
        rank if status == "optimal" else 0,
        tuple(members),
        score,
        dict(fluxes),
        dict(fluxes) if status == "optimal" else {},
        0.5,
        status,
        pareto,
        None,
        tuple(missing),
        basis,
    )


def _result(evaluations, *, targets=("a", "b"), metric="raw_sum", strategy="exhaustive",
            ranks=None):
    targets = list(targets)
    ranked = [r for r in evaluations if r.rank > 0] if ranks is None else ranks
    return MultiTargetSearchResult(
        targets=targets,
        target_exchanges={t: f"EX_{t}_m" for t in targets},
        directions=dict.fromkeys(targets, "max_secretion"),
        weights=dict.fromkeys(targets, 1.0),
        strategy=strategy,
        normalizer="none_raw_sum_absolute_units",
        solution_semantics="joint_feasible_lp_vectors",
        n_pool_members=3,
        n_candidates_total=len(evaluations),
        n_candidates_evaluated=len(evaluations),
        ranks=ranked,
        warnings=[],
        metric=metric,
        score_unit="mmol/gDW/h",
        unevaluated=[r for r in evaluations if r.rank == 0],
        evaluations=list(evaluations),
    )


def _write(result, out):
    return cli._write_multi_target_outputs(result, pd.DataFrame({"id": ["A"]}), out)


def _points(panel):
    return {(p["members"], p["x"], p["y"]): p for p in panel["points"]}


def test_only_joint_optimal_finite_rows_are_plotted_from_all_evaluations():
    rows = [
        _row(["A"], {"a": 2.0, "b": 1.0}, rank=1, pareto=True),
        _row(["B"], {"a": 1.0, "b": 0.5}, rank=2),
        _row(["C"], {"a": 5.0, "b": 5.0}, rank=3, basis=FLUX_BASIS_CAPABILITY),
        _row(["D"], {"a": float("nan"), "b": 1.0}, rank=4),
        _row(["E"], {"a": 0.0, "b": 0.0}, status="failed", basis=FLUX_BASIS_NONE),
        _row(["F"], {"a": 0.0, "b": 0.0}, status="non_viable", basis=FLUX_BASIS_NONE),
        _row(["G"], {"a": 0.0, "b": 0.0}, status="missing", basis=FLUX_BASIS_NONE),
        _row(["H"], {"a": 0.0, "b": 0.0}, status="timeout", basis=FLUX_BASIS_NONE),
    ]
    # top-k is 1 but the figure must still see every evaluated row.
    panels = cli._search_pareto_panels(_result(rows, ranks=rows[:1]))
    assert len(panels) == 1
    assert (panels[0]["x"], panels[0]["y"]) == ("a", "b")
    assert set(_points(panels[0])) == {("A", 2.0, 1.0), ("B", 1.0, 0.5)}


def test_highlight_uses_recorded_pareto_flag_without_recomputing_dominance():
    # B dominates A numerically, but only A carries the recorded flag.
    rows = [
        _row(["A"], {"a": 1.0, "b": 1.0}, rank=1, pareto=True),
        _row(["B"], {"a": 3.0, "b": 3.0}, rank=2, pareto=False),
    ]
    points = _points(cli._search_pareto_panels(_result(rows))[0])
    assert points[("A", 1.0, 1.0)]["pareto"] is True
    assert points[("B", 3.0, 3.0)]["pareto"] is False


def test_three_targets_give_three_panels_and_missing_axis_is_marked():
    rows = [
        _row(["A"], {"a": 1.0, "b": 2.0, "c": 0.0}, rank=1, pareto=True, missing=("c",)),
        _row(["B"], {"a": 2.0, "b": 1.0, "c": 3.0}, rank=2, pareto=True),
    ]
    panels = cli._search_pareto_panels(_result(rows, targets=("a", "b", "c")))
    assert [(p["x"], p["y"]) for p in panels] == [("a", "b"), ("a", "c"), ("b", "c")]
    by_pair = {(p["x"], p["y"]): _points(p) for p in panels}
    assert by_pair[("a", "b")][("A", 1.0, 2.0)]["absent"] is False
    assert by_pair[("a", "c")][("A", 1.0, 0.0)]["absent"] is True
    assert by_pair[("b", "c")][("A", 2.0, 0.0)]["absent"] is True
    assert by_pair[("a", "c")][("B", 2.0, 3.0)]["absent"] is False


def test_axis_label_keeps_sign_and_names_direction_and_better_side():
    rows = [_row(["A"], {"a": -2.0, "b": 1.0}, rank=1, pareto=True)]
    result = _result(rows)
    result = MultiTargetSearchResult(**{
        **result.__dict__, "directions": {"a": "max_uptake", "b": "max_secretion"},
    })
    panel = cli._search_pareto_panels(result)[0]
    assert panel["points"][0]["x"] == -2.0  # raw signed flux, not flipped
    x_label = cli._search_pareto_axis_label(result, "a", axis="x")
    y_label = cli._search_pareto_axis_label(result, "b", axis="y")
    assert "max uptake" in x_label and "better ←" in x_label
    assert "max secretion" in y_label and "better ↑" in y_label
    assert "mmol gDW" in x_label


def test_two_target_run_writes_pareto_figure_and_registers_it(tmp_path):
    rows = [
        _row(["A"], {"a": 2.0, "b": 1.0}, rank=1, pareto=True),
        _row(["B"], {"a": 1.0, "b": 2.0}, rank=2, pareto=True),
        _row(["C"], {"a": 0.5, "b": 0.5}, rank=3, missing=("b",)),
    ]
    out = tmp_path / "run"
    artifacts = _write(_result(rows, metric="pareto", strategy="ga_epsilon_archive"), out)
    for name in PARETO_FILES:
        assert (out / name).is_file()
        assert name in artifacts
    summary = json.loads((out / "search_summary.json").read_text())
    assert set(PARETO_FILES) <= set(summary["artifacts"])
    assert not any("Pareto figure" in w for w in summary["warnings"])
    assert PARETO_FILES[0] in cli.KNOWN_SEARCH_ARTIFACTS
    assert PARETO_FILES[1] in cli.KNOWN_SEARCH_ARTIFACTS
    # SVG keeps text (svg.fonttype none); wrapped lines are separate elements.
    svg = " ".join(re.sub(r"<[^>]+>", " ", (out / "search_pareto.svg").read_text()).split())
    assert "not a complete continuous front" in svg
    assert "approximate search" in svg
    assert "target exchange absent" in svg


def test_no_plottable_point_writes_no_pareto_file(tmp_path):
    rows = [
        _row(["C"], {"a": 5.0, "b": 5.0}, rank=1, basis=FLUX_BASIS_CAPABILITY),
        _row(["E"], {"a": 0.0, "b": 0.0}, status="failed", basis=FLUX_BASIS_NONE),
    ]
    out = tmp_path / "run"
    artifacts = _write(_result(rows), out)
    for name in PARETO_FILES:
        assert not (out / name).exists()
        assert name not in artifacts
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["status"] == "degraded"  # the failed row, not the missing figure
    assert not any("Pareto figure" in w for w in summary["warnings"])


def test_single_target_result_has_no_pareto_panels():
    rows = [_row(["A"], {"a": 1.0}, rank=1, pareto=True)]
    assert cli._search_pareto_panels(_result(rows, targets=("a",))) == []


def test_figure_failure_removes_partial_files_and_only_warns(tmp_path):
    rows = [
        _row(["A"], {"a": 2.0, "b": 1.0}, rank=1, pareto=True),
        _row(["B"], {"a": 1.0, "b": 2.0}, rank=2, pareto=True),
    ]
    original = cli.save_publication_tiff

    def failing(fig, path, *args, **kwargs):
        if path.name == "search_pareto.tiff":
            raise OSError("disk full")
        return original(fig, path, *args, **kwargs)

    out = tmp_path / "run"
    with patch.object(cli, "save_publication_tiff", side_effect=failing):
        artifacts = _write(_result(rows), out)
    for name in PARETO_FILES:
        assert not (out / name).exists()  # the SVG written first is removed too
        assert name not in artifacts
    assert (out / "search_plot.svg").is_file()
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["status"] == "ok"
    assert any(w.startswith("Pareto figure not written: ") and "disk full" in w
               for w in summary["warnings"])


def test_search_workflow_advertises_pareto_figure():
    search = next(w for w in cli.GUI_CLI_WORKFLOWS if w["cli_command"] == "cmig search")
    assert "search_pareto.svg" in search["key_outputs"]


def test_real_multi_target_cli_search_writes_pareto_figure(tmp_path):
    from tests.test_remediation_pareto import two_product_taxonomy

    taxonomy_file = tmp_path / "taxonomy.csv"
    two_product_taxonomy(tmp_path).to_csv(taxonomy_file, index=False)
    out = tmp_path / "run"
    rc = cli.main([
        "search", "--taxonomy", str(taxonomy_file), "--targets", "a,b",
        "--multi-metric", "pareto", "--min-size", "1", "--max-size", "1",
        "--top-k", "1", "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    for name in PARETO_FILES:
        assert (out / name).is_file()
        assert name in manifest["artifacts"]
    inspection = cli._inspect_run_dir(out)
    assert inspection["artifact_integrity"] == "verified"


def test_real_cli_pareto_figure_failure_keeps_run_and_exit_code(tmp_path):
    from tests.test_remediation_pareto import two_product_taxonomy

    taxonomy_file = tmp_path / "taxonomy.csv"
    two_product_taxonomy(tmp_path).to_csv(taxonomy_file, index=False)
    out = tmp_path / "run"
    with patch.object(cli, "_draw_search_pareto_figure", side_effect=RuntimeError("boom")):
        rc = cli.main([
            "search", "--taxonomy", str(taxonomy_file), "--targets", "a,b",
            "--multi-metric", "pareto", "--min-size", "1", "--max-size", "1",
            "--top-k", "1", "--out", str(out),
        ])
    assert rc == 0
    summary = json.loads((out / "search_summary.json").read_text())
    assert "Pareto figure not written: boom" in summary["warnings"]
    assert not any((out / name).exists() for name in PARETO_FILES)
    assert (out / "search_rankings.csv").is_file()
    assert cli._inspect_run_dir(out)["artifact_integrity"] == "verified"
