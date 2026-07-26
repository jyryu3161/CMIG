"""B3/B4/P1-4 regression — 다중 표적 랭킹의 과학적 해석 가능성.

고정하는 계약:
- B3: exchange 가 없는 target 은 flux 0 으로 기여하고 missing_targets 에 기록된다. 6종 중 1종이
  없다는 이유로 5종을 만드는 consortium 을 랭킹에서 탈락시키지 않는다. 진짜 non-optimal LP 만
  탈락 사유다. flux 열의 출처(joint 한 해 vs 표적별 독립 해)는 flux_basis 로 구별된다.
- B4: 전부-0 랭킹과 상위 동점은 warning 으로 노출된다(rank 1 = 알파벳 순 1등을 "최고"로
  보고하지 않기 위해).
- P1-4: carbon_equivalent 는 탄소 수로 가중해 실제 단위(mmol C)를 유지하므로 run 간 비교가
  가능하다 — mmol 단순합(C2 아세트산 = C4 부티르산)이 아니다.

solver 불요: 순수 랭킹 함수와 화학식 파서만 검증한다.
"""

from __future__ import annotations

import math

from cmig.core.search import Direction, TargetSpec
from cmig.core.search_product import (
    FLUX_BASIS_CAPABILITY,
    FLUX_BASIS_JOINT,
    MULTI_METRIC_UNITS,
    _ComboEval,
    _joint_lp_scales,
    _ranking_degeneracy_warnings,
    rank_multi_target,
)
from cmig.core.targets import SCFA, parse_carbon_number, preset_targets

SPECS = [
    TargetSpec("ac", Direction.MAX_SECRETION, 1.0),
    TargetSpec("but", Direction.MAX_SECRETION, 1.0),
]


def _eval(members, fluxes, *, status="optimal", missing=(), basis=FLUX_BASIS_JOINT):
    signed = {k: float(v) for k, v in fluxes.items()}
    return _ComboEval(
        members, status, 0.4, dict(fluxes), signed, None, tuple(missing), basis
    )


# ── B3: 부재 exchange 는 0 기여, 탈락 아님 ────────────────────────────────────────

def test_missing_exchange_contributes_zero_and_stays_ranked():
    evals = [
        # ac 만 만들 수 있고 but exchange 는 아예 없는 consortium.
        _eval(("A",), {"ac": 10.0, "but": 0.0}, missing=("but",)),
        _eval(("B",), {"ac": 1.0, "but": 1.0}),
    ]
    rows, _ = rank_multi_target(evals, SPECS, metric="raw_sum")
    by_members = {r.members: r for r in rows}
    partial = by_members[("A",)]
    assert partial.status == "optimal", "exchange 하나 부재로 랭킹에서 빠지면 안 된다"
    assert partial.missing_targets == ("but",)
    assert partial.weighted_score == 10.0          # 0 기여로 합산, -inf 아님
    # 실제로 랭킹 1위가 될 수 있다.
    assert rows[0].members == ("A",)


def test_genuinely_non_optimal_lp_is_still_disqualified():
    evals = [
        _eval(("A",), {"ac": 5.0, "but": 5.0}),
        _ComboEval(("B",), "infeasible", 0.0, {}, {}, "LP infeasible", (), FLUX_BASIS_CAPABILITY),
    ]
    rows, _ = rank_multi_target(evals, SPECS, metric="raw_sum")
    bad = next(r for r in rows if r.members == ("B",))
    assert bad.status == "infeasible"
    assert math.isinf(bad.weighted_score) and bad.weighted_score < 0
    assert bad.diagnostic == "LP infeasible"
    assert rows[0].members == ("A",)               # 평가 가능한 후보가 위로 온다


def test_flux_basis_distinguishes_joint_solution_from_capability_solves():
    evals = [
        _eval(("A",), {"ac": 5.0, "but": 5.0}, basis=FLUX_BASIS_JOINT),
        _eval(("B",), {"ac": 9.0, "but": 9.0}, status="infeasible", basis=FLUX_BASIS_CAPABILITY),
    ]
    rows, _ = rank_multi_target(evals, SPECS, metric="raw_sum")
    basis = {r.members: r.flux_basis for r in rows}
    # 동시 달성 불가한 표적별 최대치가 joint 해와 같은 칸에 무표시로 섞이지 않는다.
    assert basis[("A",)] == FLUX_BASIS_JOINT
    assert basis[("B",)] == FLUX_BASIS_CAPABILITY


# ── B4: 전부-0 / 동점 경고 ────────────────────────────────────────────────────────

def test_all_zero_ranking_is_warned():
    scored = [(("A", "B"), 0.0, "optimal"), (("A", "C"), 0.0, "optimal")]
    warnings = _ranking_degeneracy_warnings(scored)
    assert any("no candidate achieved a non-zero target flux" in w for w in warnings)


def test_tied_top_is_warned_with_count_and_score():
    scored = [
        (("A", "B"), 7.5, "optimal"),
        (("A", "C"), 7.5, "optimal"),
        (("B", "C"), 1.0, "optimal"),
    ]
    warnings = _ranking_degeneracy_warnings(scored)
    assert len(warnings) == 1
    assert "top-2 candidates tied at score 7.5" in warnings[0]
    assert "A+B" in warnings[0] and "A+C" in warnings[0]


def test_unique_winner_produces_no_degeneracy_warning():
    scored = [(("A", "B"), 7.5, "optimal"), (("A", "C"), 1.0, "optimal")]
    assert _ranking_degeneracy_warnings(scored) == []


def test_non_optimal_rows_are_ignored_by_degeneracy_check():
    scored = [(("A",), float("-inf"), "missing"), (("B",), 3.0, "optimal")]
    assert _ranking_degeneracy_warnings(scored) == []


# ── P1-4: carbon-equivalent 총량 ─────────────────────────────────────────────────

def test_carbon_equivalent_weights_by_carbon_number():
    """아세트산(C2) 6 mmol vs 부티르산(C4) 3 mmol → 탄소 기준으로는 동등(12 mmol C)."""
    acetate_specs = [
        TargetSpec("ac", Direction.MAX_SECRETION, 2.0),    # C2
        TargetSpec("but", Direction.MAX_SECRETION, 4.0),   # C4
    ]
    evals = [
        _eval(("acetate_maker",), {"ac": 6.0, "but": 0.0}),
        _eval(("butyrate_maker",), {"ac": 0.0, "but": 3.0}),
        _eval(("mixed",), {"ac": 2.0, "but": 2.0}),
    ]
    rows, normalizer = rank_multi_target(evals, acetate_specs, metric="carbon_equivalent")
    score = {r.members: r.weighted_score for r in rows}
    assert score[("acetate_maker",)] == 12.0       # 2*6
    assert score[("butyrate_maker",)] == 12.0      # 4*3
    assert score[("mixed",)] == 12.0               # 2*2 + 4*2
    assert "carbon_equivalent" in normalizer
    # mmol 단순합이라면 6 > 3 이 되어 부티르산 생산자를 과소평가한다.
    raw_rows, _ = rank_multi_target(evals, SPECS, metric="raw_sum")
    raw = {r.members: r.weighted_score for r in raw_rows}
    assert raw[("acetate_maker",)] == 6.0 and raw[("butyrate_maker",)] == 3.0


def test_absolute_metrics_do_not_rescale_by_candidate_set():
    """raw_sum/carbon_equivalent 점수는 후보 집합이 바뀌어도 그대로여야 한다(run 간 비교 가능)."""
    a = _eval(("A",), {"ac": 4.0, "but": 1.0})
    small, _ = rank_multi_target([a, _eval(("B",), {"ac": 1.0, "but": 1.0})], SPECS,
                                 metric="raw_sum")
    large, _ = rank_multi_target([a, _eval(("C",), {"ac": 99.0, "but": 99.0})], SPECS,
                                 metric="raw_sum")
    assert small[0].members == ("A",)
    assert next(r for r in small if r.members == ("A",)).weighted_score == 5.0
    assert next(r for r in large if r.members == ("A",)).weighted_score == 5.0


def test_normalized_weighted_is_candidate_set_relative():
    """대비 확인: 기본 metric 은 후보 집합에 따라 같은 후보의 점수가 달라진다."""
    a = _eval(("A",), {"ac": 4.0, "but": 1.0})
    ranges = {"ac": (0.0, 4.0), "but": (0.0, 1.0)}
    wide = {"ac": (0.0, 100.0), "but": (0.0, 100.0)}
    tight, _ = rank_multi_target([a], SPECS, normalization_ranges=ranges)
    loose, _ = rank_multi_target([a], SPECS, normalization_ranges=wide)
    assert tight[0].weighted_score != loose[0].weighted_score


def test_joint_lp_scales_keep_real_units_for_absolute_metrics():
    ranges = {"ac": (0.0, 50.0), "but": (0.0, 2.0)}
    assert _joint_lp_scales("carbon_equivalent", ranges) == {"ac": 1.0, "but": 1.0}
    assert _joint_lp_scales("raw_sum", ranges) == {"ac": 1.0, "but": 1.0}
    # 정규화 metric 은 capability 폭으로 나눈다(기존 동작 유지).
    assert _joint_lp_scales("normalized_weighted", ranges) == {"ac": 50.0, "but": 2.0}


def test_zero_width_capability_range_falls_back_to_one():
    assert _joint_lp_scales("normalized_weighted", {"ac": (3.0, 3.0)}) == {"ac": 1.0}


def test_metric_units_are_declared_for_every_metric():
    # `pareto` is not a scalarisation: it returns a non-dominated set rather than a single
    # ranked optimum, so it is listed here but carries a "not totally ordered" caveat.
    assert set(MULTI_METRIC_UNITS) == {
        "normalized_weighted", "carbon_equivalent", "raw_sum", "pareto",
    }
    assert "mmol C" in MULTI_METRIC_UNITS["carbon_equivalent"]
    assert "dimensionless" in MULTI_METRIC_UNITS["normalized_weighted"]
    assert "not totally ordered" in MULTI_METRIC_UNITS["pareto"]


# ── 화학식 파서 / preset ─────────────────────────────────────────────────────────

def test_parse_carbon_number_reads_scfa_formulas():
    assert parse_carbon_number("C2H3O2") == 2      # acetate
    assert parse_carbon_number("C3H5O2") == 3      # propionate
    assert parse_carbon_number("C4H7O2") == 4      # butyrate
    assert parse_carbon_number("C3H5O3") == 3      # lactate
    assert parse_carbon_number("C4H4O4") == 4      # succinate
    assert parse_carbon_number("CH4") == 1


def test_parse_carbon_number_returns_none_when_unknown():
    """모르는 것을 조용히 0/1 로 바꾸지 않는다 — 호출자가 멈출 수 있어야 한다."""
    assert parse_carbon_number(None) is None
    assert parse_carbon_number("") is None
    assert parse_carbon_number("   ") is None
    assert parse_carbon_number("H2O") is None      # 탄소 없음
    assert parse_carbon_number("R") is None        # generic placeholder
    assert parse_carbon_number("ac_e") is None     # 화학식이 아님


def test_scfa_preset_expands_to_the_documented_six():
    assert preset_targets("scfa") == ["ac", "but", "lac__D", "lac__L", "ppa", "succ"]
    assert set(preset_targets("scfa")) == set(SCFA.metabolites)


def test_unknown_preset_is_rejected():
    try:
        preset_targets("nope")
    except ValueError as error:
        assert "unknown target preset" in str(error)
    else:
        raise AssertionError("unknown preset must raise")
