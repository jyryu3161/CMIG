"""SC-07/08: undefined inference and native solver integration checks."""

from __future__ import annotations

import json
import math
from unittest.mock import patch

import cobra
import pytest

from cmig.cli.main import main
from cmig.core.single_model import SingleModelUnavailableError, _require_lp
from cmig.core.solver import HighsBackend, capability_matrix
from cmig.core.stats import cohens_d, prepare_volcano_data, two_group_test


@pytest.mark.parametrize("a,b,reason", [
    ([1, 1, 1], [10, 10, 10], "zero pooled variance"),
    ([1, 1, 1], [1, 1, 1], "zero pooled variance"),
    ([1], [2, 3], "insufficient sample"),
    ([], [2, 3], "empty group"),
    ([1, float("nan")], [2, 3], "nonfinite input"),
])
def test_degenerate_cohen_d_is_null_with_reason(a, b, reason):
    result = two_group_test(a, b, parametric=True)
    assert result.effect_size is None
    assert result.status in {"degenerate", "unavailable"}
    assert reason in (result.reason or "")
    assert cohens_d(a, b) is None
    with pytest.raises(ValueError, match="requires numeric effect_size"):
        prepare_volcano_data({"feature": result})


def test_one_constant_group_with_positive_pooled_variance_is_defined():
    result = two_group_test([1, 1, 1], [2, 3, 4], parametric=True)
    assert result.status == "completed"
    assert result.effect_size is not None and math.isfinite(result.effect_size)


def test_highs_package_without_cobra_adapter_is_unavailable():
    with patch("cmig.core.solver._importable", return_value=True), patch(
        "cmig.core.solver._cobra_interface_available", return_value=False
    ):
        capability = HighsBackend().capability()
        assert capability.package_installed and not capability.interface_available
        assert not capability.available
        assert "interface missing" in (capability.unavailable_reason or "")
        with pytest.raises(SingleModelUnavailableError, match="LP capability"):
            _require_lp("highs")


def test_advertised_gurobi_adapter_solves_tiny_lp():
    assert capability_matrix()["gurobi"].supports("LP")
    model = cobra.Model("tiny")
    reaction = cobra.Reaction("source")
    reaction.bounds = (0, 2)
    model.add_reactions([reaction])
    model.objective = reaction
    model.solver = "gurobi"
    assert model.slim_optimize() == pytest.approx(2)


def test_parametric_stats_sweep_serializes_degenerate_effect_as_null(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        {"status": "ok", "metric": "growth", "axis_solver": group,
         "replicate_id": f"r{index}", "value": value}
        for group, value in (("one", 1.0), ("ten", 10.0))
        for index in range(3)
    ]
    sweep = tmp_path / "replicates.parquet"
    pq.write_table(pa.Table.from_pylist(rows), sweep)
    out = tmp_path / "stats"
    assert main([
        "stats-sweep", "--sweep", str(sweep), "--parametric",
        "--replicate-column", "replicate_id", "--confirm-independent-replicates",
        "--out", str(out),
    ]) == 0
    payload = json.loads((out / "stats_sweep_summary.json").read_text())
    assert payload["inference"]["status"] == "degenerate"
    assert payload["test"]["effect_size"] is None
    assert payload["test"]["reason"] == "zero pooled variance"
    assert payload["test"]["statistic"] is None
