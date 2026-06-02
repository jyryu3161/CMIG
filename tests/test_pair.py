"""Phase 1.2 — AN-PAIR (mono-vs-co) + matrix. Plan SC: SC-AP1~AP4.

synthetic acetate→butyrate cross-feeding fixture로 정성 검증:
mono(producer 10, consumer 5) → co(둘 다 12.5) = mutualism, mro=0, mip=1.
"""

from __future__ import annotations

import tempfile

import pytest

pytest.importorskip("micom")

from cmig.core.matrix import MATRIX_SCHEMA, build_matrix, read_matrix, write_matrix  # noqa: E402
from cmig.core.pair import analyze_pair, pair_matrix_rows  # noqa: E402
from cmig.synthetic_pair import build_pair_taxonomy  # noqa: E402


def _result():
    with tempfile.TemporaryDirectory() as td:
        tax = build_pair_taxonomy(td)
        return analyze_pair(tax, solver="gurobi", tradeoff_f=0.5)


def test_pair_mono_vs_co_growth():
    """SC-AP1: mono(producer 10, consumer 5) vs co(둘 다 12.5)."""
    r = _result()
    assert abs(r.mono_growth["producer"] - 10.0) < 1e-3
    assert abs(r.mono_growth["consumer"] - 5.0) < 1e-3
    assert abs(r.co_growth["producer"] - 12.5) < 1e-3
    assert abs(r.co_growth["consumer"] - 12.5) < 1e-3


def test_pair_interaction_mutualism():
    """SC-AP2: cross-feeding → 둘 다 co 에서 성장 증가 = mutualism (metrics.interaction_type)."""
    assert _result().interaction == "mutualism"


def test_pair_failed_co_culture_does_not_report_neutralism():
    """D-3: co-culture 실패는 interaction='failed' 로 전파되고 neutralism 으로 위장되지 않는다."""
    import pandas as pd

    from cmig.core.engine import SolveResult

    class _Engine:
        def build_community(self, taxonomy, cmig_solver):
            return object()

        def cooperative_tradeoff(self, community, tradeoff_f, cmig_solver):
            return SolveResult(
                objective=float("nan"),
                member_growth={"a": 0.0, "b": 0.0},
                abundances={"a": 0.5, "b": 0.5},
                external_exchange={},
                member_exchange={},
                status="infeasible",
                flux_report_status="full",
                growth_solver="gurobi",
                flux_solver="gurobi",
                diagnostic="forced infeasible",
                members=["a", "b"],
            )

    tax = pd.DataFrame({"id": ["a", "b"], "file": ["unused-a.xml", "unused-b.xml"]})
    r = analyze_pair(tax, engine=_Engine())
    assert r.status == "failed"
    assert r.interaction == "failed"
    assert r.diagnostic == "forced infeasible"


def test_pair_mro_mip():
    """SC-AP3: MRO=0(흡수 disjoint: glucose vs acetate), MIP=1(producer→consumer acetate)."""
    r = _result()
    assert r.mro_score == 0.0
    assert r.mip == 1


def test_pair_matrix_long_format():
    """SC-AP4: pair_matrix_rows → MATRIX_SCHEMA(9행). interaction 행=label only."""
    r = _result()
    rows = pair_matrix_rows(r)
    table = build_matrix(rows)
    assert table.schema.equals(MATRIX_SCHEMA)
    assert table.num_rows == 9
    pyrows = table.to_pylist()
    inter = next(x for x in pyrows if x["metric"] == "interaction")
    assert inter["value"] is None and inter["label"] == "mutualism"
    # growth_delta = co - mono (둘 다 양수 → mutualism 일관)
    deltas = {x["member_id"]: x["value"] for x in pyrows if x["metric"] == "growth_delta"}
    assert deltas["producer"] > 0 and deltas["consumer"] > 0


def test_matrix_parquet_roundtrip(tmp_path):
    """SC-AP4: matrix.parquet write/read 라운드트립(pickle 금지)."""
    r = _result()
    table = build_matrix(pair_matrix_rows(r))
    p = write_matrix(table, tmp_path / "matrix.parquet")
    back = read_matrix(p)
    assert back.num_rows == 9
    assert set(back.column("schema_version").to_pylist()) == {"1.0"}


def test_pair_rejects_non_two_members(tmp_path):
    """AN-PAIR 은 정확히 2 멤버."""
    import pandas as pd
    tax = pd.DataFrame({"id": ["a", "b", "c"], "file": ["x", "y", "z"]})
    with pytest.raises(ValueError, match="2 멤버"):
        analyze_pair(tax)
