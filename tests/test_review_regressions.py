"""Track-C 적대적 리뷰 발굴분 회귀 고정 (Important 9건). Plan SC: SC-H3.

Design Ref(hardening): §4 — per-slice Check 가 'complete' 로 표기한 6모듈에서 적대 리뷰가
발굴한 확정 결함(TC-1~9)을 회귀로 고정한다. 각 테스트는 결함 id 를 명시한다.
"""

from __future__ import annotations

import math

import pyarrow.parquet as pq

from cmig.core.delta import DeltaResult, MetaboliteDelta, compute_delta
from cmig.core.engine import SolveResult
from cmig.core.sandbox import SandboxState, evaluate_sandbox
from cmig.core.sweep import (
    SWEEP_SCHEMA,
    SweepRow,
    write_sweep_parquet,
)


def _sr(objective, status="optimal", members=("A", "B"), ext=None):
    return SolveResult(
        objective=objective,
        member_growth={m: 0.1 for m in members},
        abundances={m: 0.5 for m in members},
        external_exchange=ext if ext is not None else {"ac": 1.0},
        member_exchange={m: {} for m in members},
        status=status, flux_report_status="full",
        growth_solver="gurobi", flux_solver="gurobi", members=list(members),
    )


# ── delta.py ────────────────────────────────────────────────────────────────

def test_tc4_delta_propagates_failed_status():
    """TC-4: 입력 infeasible → DeltaResult.status='failed' + diagnostic(≠null)."""
    base = _sr(0.5)
    bad = _sr(0.5, status="infeasible")
    d = compute_delta(base, bad)
    assert d.status == "failed"
    assert d.diagnostic and "infeasible" in d.diagnostic


def test_tc5_delta_nan_growth_flagged_not_silent():
    """TC-5: objective NaN → growth_delta NaN 이지만 status='failed' 로 노출(silent 금지)."""
    base = _sr(0.5)
    nan = _sr(math.nan, status="infeasible")
    d = compute_delta(base, nan)
    assert math.isnan(d.growth_delta)
    assert d.status == "failed"                 # NaN 이 진단 없이 묻히지 않음


def test_tc6_significant_does_not_drop_nan_delta():
    """TC-6: NaN delta 는 significant 에서 조용히 누락되지 않는다(변화없음 위장 방지)."""
    prof = [MetaboliteDelta("x", 1.0, math.nan, math.nan)]
    d = DeltaResult(profile=prof)
    sig = d.significant(threshold=1e-6)
    assert len(sig) == 1                        # NaN delta 가 significant 로 잡힘
    assert sig[0].metabolite == "x"


# ── sandbox.py ────────────────────────────────────────────────────────────────

def test_tc1_infeasible_not_masked_as_no_change():
    """TC-1: constrained infeasible → no_significant_change=False + status='failed'."""
    base = _sr(0.5, ext={"ac": 1.0})
    # constrained 가 infeasible 이고 profile 도 동일 → 과거엔 no_change=True 로 위장.
    constrained = _sr(math.nan, status="infeasible", ext={"ac": 1.0})
    r = evaluate_sandbox(base, constrained, state=SandboxState.PREVIEW)
    assert r.status == "failed"
    assert r.no_significant_change is False, "infeasible 가 '변화 없음'으로 위장됨(TC-1 회귀)"
    assert r.diagnostic


def test_tc1_optimal_unchanged_still_reports_no_change():
    """TC-1 보강: 정상 solve 가 실제 변화 없으면 여전히 no_significant_change=True."""
    base = _sr(0.5, ext={"ac": 1.0})
    same = _sr(0.5, ext={"ac": 1.0})
    r = evaluate_sandbox(base, same, state=SandboxState.PREVIEW)
    assert r.status == "ok"
    assert r.no_significant_change is True


# ── sweep.py ────────────────────────────────────────────────────────────────

def _row(axis_values, **kw):
    base = dict(condition_id="cond-0000", axis_values=axis_values, metric="growth",
                value=0.5, run_hash="h", status="ok", diagnostic=None, cache_hit=False)
    base.update(kw)
    return SweepRow(**base)


def test_tc2_sweep_has_six_axis_columns(tmp_path):
    """TC-2: sweep.parquet 가 schema §6.1 의 6개 per-axis 컬럼을 가진다(단일 axes JSON 아님)."""
    names = set(SWEEP_SCHEMA.names)
    for col in ("axis_medium_variant", "axis_abundance", "axis_member_set",
                "axis_bounds", "axis_tradeoff_f", "axis_solver"):
        assert col in names, f"{col} 누락 (schema §6.1)"
    assert "axes" not in names, "단일 axes JSON 컬럼이 남아있음(TC-2 회귀)"
    # axis_tradeoff_f 는 float64
    assert str(SWEEP_SCHEMA.field("axis_tradeoff_f").type) == "double"

    out = tmp_path / "sweep.parquet"
    write_sweep_parquet([_row({"tradeoff_f": 0.5, "solver": "gurobi"})], out)
    t = pq.read_table(out)
    assert t.column("axis_tradeoff_f").to_pylist() == [0.5]
    assert t.column("axis_solver").to_pylist() == ["gurobi"]
    assert t.column("axis_abundance").to_pylist() == [None]   # 미지정 축=null


def test_tc3_sweep_tradeoff_f_canonical_rounding(tmp_path):
    """TC-3: axis_tradeoff_f 가 A17 rounding + 비유한은 null(비결정 직렬화 제거)."""
    out = tmp_path / "sweep.parquet"
    write_sweep_parquet([
        _row({"tradeoff_f": 0.5 + 1e-9}, condition_id="cond-0000"),  # 잡음 → 반올림
        _row({"tradeoff_f": math.nan}, condition_id="cond-0001"),    # 비유한 → null
    ], out)
    vals = pq.read_table(out).column("axis_tradeoff_f").to_pylist()
    assert vals[0] == 0.5                       # 6 decimal 반올림으로 잡음 흡수
    assert vals[1] is None                      # NaN → null (NaN 토큰 방출 안 함)


# ── render/client.py ──────────────────────────────────────────────────────────

def test_tc7_csv_nonfinite_becomes_na(tmp_path):
    """TC-7: _write_csv 가 NaN/inf/None → '' (R NA), float 고정 자릿수(결정성)."""
    from cmig.render.client import _write_csv

    out = tmp_path / "d.csv"
    _write_csv([
        {"metabolite": "ac", "net_flux": math.nan, "ui_flux": 1.0, "label": "secretion"},
        {"metabolite": "glc", "net_flux": float("inf"), "ui_flux": None, "label": "uptake"},
        {"metabolite": "o2", "net_flux": -2.0 + 1e-12, "ui_flux": 2.0, "label": "uptake"},
    ], out)
    text = out.read_text()
    assert "nan" not in text.lower() and "inf" not in text.lower(), "NaN/inf 토큰 방출(TC-7 회귀)"
    lines = text.strip().splitlines()
    # o2 net_flux 가 고정 자릿수 -2.000000 (결정적)
    assert any("-2.000000" in ln for ln in lines)


# ── medium.py ────────────────────────────────────────────────────────────────

def test_tc8_tc9_capability_absent_is_unavailable_not_infeasible():
    """TC-8/TC-9: MILP 미지원 solver 요청 → MILPUnavailableError(capability seam 경유)."""
    import pytest

    from cmig.core.medium import (
        MILPInfeasibleError,
        MILPUnavailableError,
        minimal_medium_cardinality,
    )

    pytest.importorskip("cobra")
    # osqp 는 MILP 미지원(capability.milp=False) → infeasible 아니라 Unavailable 로 fail-fast.
    with pytest.raises(MILPUnavailableError):
        minimal_medium_cardinality(object(), 0.1, solver="osqp")
    # 두 에러는 별개 계층(TC-8)
    assert not issubclass(MILPInfeasibleError, MILPUnavailableError)
