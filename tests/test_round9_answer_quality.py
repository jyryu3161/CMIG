"""Round-9 answer-quality regressions for abundance weighting and Pareto disclosure."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from cmig.core.metrics import community_contributions
from cmig.core.search import Direction, TargetSpec
from cmig.core.search_product import (
    MultiTargetConfig,
    _ComboEval,
    _multi_target_warnings,
    rank_multi_target,
)
from cmig.core.tidy import MissingAbundanceError


@pytest.mark.parametrize("invalid", [None, math.nan, math.inf, -0.1])
def test_missing_or_invalid_abundance_cannot_become_a_target_contribution(invalid):
    with pytest.raises(MissingAbundanceError, match="abundance missing|finite and non-negative"):
        community_contributions({"A": {"ac": 2.0}}, {"A": invalid}, "ac")


def test_absent_abundance_key_is_missing_and_zero_abundance_is_valid():
    with pytest.raises(MissingAbundanceError, match="abundance missing"):
        community_contributions({"A": {"ac": 2.0}}, {}, "ac")

    assert community_contributions({"A": {"ac": 2.0}}, {"A": 0.0}, "ac") == {"A": 0.0}


def test_three_target_pareto_column_handles_ties_and_dominance():
    specs = [
        TargetSpec("ac", Direction.MAX_SECRETION, 1.0),
        TargetSpec("but", Direction.MAX_SECRETION, 1.0),
        TargetSpec("succ", Direction.MAX_SECRETION, 1.0),
    ]
    evals = [
        _ComboEval(
            ("ac_specialist",),
            "optimal",
            0.4,
            {"ac": 5.0, "but": 1.0, "succ": 1.0},
            {"ac": 5.0, "but": 1.0, "succ": 1.0},
        ),
        _ComboEval(
            ("but_specialist",),
            "optimal",
            0.4,
            {"ac": 1.0, "but": 5.0, "succ": 1.0},
            {"ac": 1.0, "but": 5.0, "succ": 1.0},
        ),
        _ComboEval(
            ("balanced",),
            "optimal",
            0.4,
            {"ac": 3.0, "but": 3.0, "succ": 3.0},
            {"ac": 3.0, "but": 3.0, "succ": 3.0},
        ),
        _ComboEval(
            ("balanced_tie",),
            "optimal",
            0.4,
            {"ac": 3.0, "but": 3.0, "succ": 3.0},
            {"ac": 3.0, "but": 3.0, "succ": 3.0},
        ),
        _ComboEval(
            ("dominated",),
            "optimal",
            0.4,
            {"ac": 2.0, "but": 2.0, "succ": 2.0},
            {"ac": 2.0, "but": 2.0, "succ": 2.0},
        ),
        _ComboEval(("failed",), "failed", 0.0, {}, {}, "synthetic failure"),
    ]

    rows, _ = rank_multi_target(evals, specs, metric="raw_sum")
    pareto_by_members = {row.members: row.pareto for row in rows}

    assert pareto_by_members == {
        ("ac_specialist",): True,
        ("but_specialist",): True,
        ("balanced",): True,
        ("balanced_tie",): True,
        ("dominated",): False,
        ("failed",): False,
    }
    config = MultiTargetConfig(
        targets=[spec.metabolite for spec in specs],
        directions={spec.metabolite: spec.direction for spec in specs},
        weights={spec.metabolite: spec.weight for spec in specs},
        metric="raw_sum",
    )
    warnings = _multi_target_warnings(
        [row for row in rows if row.rank > 0],
        [row for row in rows if row.rank == 0],
        config,
    )
    assert not any("pareto was NOT computed" in warning for warning in warnings)


def test_real_gurobi_missing_abundance_becomes_a_failed_null_sweep_point(monkeypatch, tmp_path):
    """The library hard error reaches abundance-impact's diagnostic failure boundary."""
    from cmig.cli.main import main
    from cmig.core.engine import MicomEngine
    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = tmp_path / "taxonomy.csv"
    build_pair_taxonomy(tmp_path / "microbes").to_csv(taxonomy, index=False)
    real_tradeoff = MicomEngine.cooperative_tradeoff

    def solve_with_missing_abundance(self, community, tradeoff_f, *, cmig_solver="gurobi"):
        result = real_tradeoff(self, community, tradeoff_f, cmig_solver=cmig_solver)
        abundances = dict(result.abundances)
        abundances["producer"] = None
        return replace(result, abundances=abundances)

    monkeypatch.setattr(MicomEngine, "cooperative_tradeoff", solve_with_missing_abundance)
    out = tmp_path / "abundance_impact"
    rc = main(
        [
            "abundance-impact",
            "--taxonomy",
            str(taxonomy),
            "--member",
            "producer",
            "--fractions",
            "0.5",
            "--target",
            "ac",
            "--solver",
            "gurobi",
            "--out",
            str(out),
        ]
    )

    # main.py is owned by V1. V2 pins the scientific output contract while allowing the
    # coordinator to make the command's all-failed exit code non-zero during integration.
    assert rc in (0, 3)
    row = json.loads((out / "abundance_impact_summary.json").read_text())["rows"][0]
    assert row["status"] == "failed"
    assert "member abundance missing" in row["diagnostic"]
    for field in (
        "target_influence_share",
        "target_secretion_share",
        "target_member_contribution",
    ):
        assert row[field] is None
