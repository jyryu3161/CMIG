"""module-1c Validation — SC-7(튜토리얼 재현)·SC-5(version gate)·G-2(cross-feeding sanity).

G-2 는 micom 불요(합성 SolveResult). SC-7/SC-5 는 micom 필요 → importorskip.
"""

import json
from pathlib import Path

import pytest

from cmig.core.engine import SolveResult
from cmig.core.interactions import allocate_cross_feeding, build_tidy

# ── G-2 [Minor] cross-feeding sanity (extraction 계약, micom 불요) ──

def _synthetic_crossfeed() -> SolveResult:
    """멤버 A 가 ac 분비(+8), 멤버 B 가 ac 흡수(−5) → cross-feeding A→B."""
    return SolveResult(
        objective=0.9,
        member_growth={"A": 0.5, "B": 0.4},
        abundances={"A": 0.5, "B": 0.5},
        external_exchange={"ac": 3.0},          # net = +8 − 5 = +3 (분비)
        member_exchange={"A": {"ac": 8.0}, "B": {"ac": -5.0}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A", "B"],
    )


def test_cross_feeding_edge_weight_is_min():
    bundle = build_tidy(_synthetic_crossfeed())
    edges = bundle.edges.to_pylist()
    cf = [e for e in edges if e["edge_type"] == "cross_feeding"]
    assert len(cf) == 1
    e = cf[0]
    assert (e["source_id"], e["target_id"], e["metabolite"]) == ("A", "B", "ac")
    # tidy 1.3: community basis — min(분비 8×0.5, 흡수 5×0.5) = min(4, 2.5)
    assert e["weight"] == 2.5
    assert e["label"] == "secretion"


def test_member_pool_edges_present():
    bundle = build_tidy(_synthetic_crossfeed())
    edges = bundle.edges.to_pylist()
    sec = [e for e in edges if e["edge_type"] == "secretion"]
    upt = [e for e in edges if e["edge_type"] == "uptake"]
    # tidy 1.3: community basis — per-taxon flux × relative abundance (0.5 here)
    assert any(e["source_id"] == "A" and e["weight"] == 4.0 for e in sec)   # A→pool 8×0.5
    assert any(e["target_id"] == "B" and e["weight"] == 2.5 for e in upt)   # pool→B 5×0.5


def test_no_cross_feeding_when_no_consumer():
    r = _synthetic_crossfeed()
    r2 = SolveResult(**{**r.__dict__, "member_exchange": {"A": {"ac": 8.0}, "B": {"ac": 2.0}}})
    bundle = build_tidy(r2)  # 둘 다 분비 → consumer 없음
    assert not [e for e in bundle.edges.to_pylist() if e["edge_type"] == "cross_feeding"]


def test_cross_feeding_many_to_many_conserves_mass():
    """Two donors/two consumers must not emit four pairwise minima (20 from only 10 supply)."""
    result = SolveResult(
        objective=1.0,
        member_growth={m: 1.0 for m in ("S1", "S2", "C1", "C2")},
        abundances={m: 0.25 for m in ("S1", "S2", "C1", "C2")},
        external_exchange={},
        member_exchange={
            "S1": {"x": 5.0},
            "S2": {"x": 5.0},
            "C1": {"x": -5.0},
            "C2": {"x": -5.0},
        },
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["S1", "S2", "C1", "C2"],
    )
    edges = [
        row for row in build_tidy(result).edges.to_pylist()
        if row["edge_type"] == "cross_feeding"
    ]
    assert len(edges) == 4
    # tidy 1.3: community supply is 2 donors × 5.0 × 0.25 = 2.5; allocation conserves it.
    assert sum(row["weight"] for row in edges) == pytest.approx(2.5)
    for donor in ("S1", "S2"):
        assert sum(row["weight"] for row in edges if row["source_id"] == donor) <= 1.25
    for consumer in ("C1", "C2"):
        assert sum(row["weight"] for row in edges if row["target_id"] == consumer) <= 1.25


def test_cross_feeding_allocation_is_deterministic_and_handles_imbalance():
    a = allocate_cross_feeding({"B": 3.0, "A": 9.0}, {"D": -2.0, "C": -4.0})
    b = allocate_cross_feeding({"A": 9.0, "B": 3.0}, {"C": -4.0, "D": -2.0})
    assert a == b
    assert sum(weight for _source, _target, weight in a) == pytest.approx(6.0)


# ── SC-7 튜토리얼 재현 (micom 필요) ──

micom = pytest.importorskip("micom")  # noqa: F841


def test_engine_reproduces_direct_micom():
    """SC-7: 우리 wrapper 가 MICOM 직접 호출과 비트 동일(growth+profile) 재현 — 스크립트 0줄."""
    from cmig.core.engine import MicomEngine
    from cmig.golden_fixture import TRADEOFF_F, build_taxonomy

    eng = MicomEngine()
    tax = build_taxonomy()
    # 직접 MICOM
    com_direct = eng.build_community(tax, cmig_solver="gurobi")
    direct = com_direct.cooperative_tradeoff(fraction=TRADEOFF_F, fluxes=True, pfba=True)
    # 우리 wrapper (별도 community, 동일 입력)
    com_ours = eng.build_community(tax, cmig_solver="gurobi")
    ours = eng.cooperative_tradeoff(com_ours, TRADEOFF_F, cmig_solver="gurobi")

    assert abs(ours.objective - float(direct.growth_rate)) < 1e-9
    for col in direct.fluxes.columns:
        if col.startswith("EX_") and col.endswith("_m"):
            metab = col[3:-2]
            raw = float(direct.fluxes.loc["medium", col])
            if metab in ours.external_exchange:
                assert abs(ours.external_exchange[metab] - raw) < 1e-9


def test_tutorial_sanity_glucose_uptake_acetate_secretion():
    """SC-7 sanity: MICOM 튜토리얼 거동(글루코스 흡수·아세트산 분비) 재현."""
    from cmig.golden_fixture import solve

    result, _bundle = solve("gurobi")
    ext = result.external_exchange
    assert any(m.startswith("glc") and v < 0 for m, v in ext.items())  # 글루코스 흡수(−)
    assert ext.get("ac", 0.0) > 0                                       # 아세트산 분비(+)


# ── SC-5 MICOM-version golden regression gate (micom 필요) ──

def test_golden_versions_match_installed():
    """SC-5 positive: 커밋된 golden 의 micom_version == 설치 버전 → 승격 가능."""
    from cmig.golden_fixture import verify_golden_versions

    report = verify_golden_versions()
    assert all(r["ok"] for r in report.values()), report


def test_version_mismatch_blocks_promotion(tmp_path: Path):
    """SC-5 negative: 버전 불일치 golden → assert_golden_versions 가 차단."""
    from cmig.golden_fixture import (
        SOLVER_VARIANTS,
        GoldenVersionMismatch,
        assert_golden_versions,
    )

    for solver in SOLVER_VARIANTS:
        d = tmp_path / "expected" / solver
        d.mkdir(parents=True)
        (d / "config.json").write_text(json.dumps({"components": {"micom_version": "0.0.0-fake"}}))
    with pytest.raises(GoldenVersionMismatch):
        assert_golden_versions(tmp_path)
