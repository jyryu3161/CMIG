"""2b integration — SC-1 (solver별 golden) · SC-6 (OSQP→LP) · SC-5 · SC-9 (real data).

micom 미설치(2a) 환경에서는 전체 skip.
"""

from pathlib import Path

import pyarrow.parquet as pq
import pytest

pytest.importorskip("micom")

from cmig.core.golden import bundle_hashes, normalized_table_hash, tables_close  # noqa: E402
from cmig.golden_fixture import (  # noqa: E402
    FIXTURE_DIR,
    SOLVER_VARIANTS,
    VARIANT_DECIMALS,
    _run_hash_components,
    solve,
)

EXPECTED = FIXTURE_DIR / "expected"

# 행 키(안정적 문자열) / float 컬럼 — tolerance 비교용 (golden.tables_close).
KEYS = {
    "nodes": (["node_id"], ["growth", "abundance"]),
    "edges": (["source_id", "target_id", "metabolite", "edge_type"], ["weight"]),
    "profile": (["metabolite"], ["net_flux", "ui_flux", "fva_lo", "fva_hi"]),
}
# atol: OSQP cross-process jitter(측정 ~6.3e-6)를 안전 흡수. gurobi 는 exact 라 무관.
ATOL = 1e-4


def _expected(solver: str, table: str):
    return pq.read_table(EXPECTED / solver / f"{table}.parquet")


@pytest.mark.parametrize("solver", SOLVER_VARIANTS)
def test_golden_regression_per_solver(solver):
    """SC-1: 동일 solver 재solve → committed golden 과 일치.

    gurobi(결정적): hash-exact. OSQP 계열(iterative): tolerance 비교(OD-12·OD-47·OD-50).
    """
    _result, bundle = solve(solver)
    if solver == "gurobi":
        dec = VARIANT_DECIMALS[solver]
        fresh = bundle_hashes(bundle, dec)
        for table in ("nodes", "edges", "profile"):
            exp = normalized_table_hash(_expected(solver, table), dec)
            assert fresh[table] == exp, f"{solver}/{table} hash 불일치 (재현성, SC-1)"
    else:
        for table in ("nodes", "edges", "profile"):
            keys, floats = KEYS[table]
            actual = getattr(bundle, table)
            tables_close(actual, _expected(solver, table), keys, floats, atol=ATOL)


def test_osqp_profile_matches_gurobi_within_tolerance():
    """SC-6(F1 후): osqp external profile 이 gurobi 와 tolerance 내 일치(QP vs LP 근사)."""
    keys, floats = KEYS["profile"]
    tables_close(
        _expected("osqp", "profile"),
        _expected("gurobi", "profile"),
        keys, floats, atol=ATOL,
    )


def test_sign_labels_real_data():
    """SC-2(실데이터): profile label 이 sign 규약(+secretion/−uptake)과 일치."""
    _result, bundle = solve("gurobi")
    for r in bundle.profile.to_pylist():
        if r["net_flux"] > 0:
            assert r["label"] == "secretion"
        elif r["net_flux"] < 0:
            assert r["label"] == "uptake"
        assert r["ui_flux"] >= 0.0


def test_run_hash_includes_micom_version():
    """SC-5: run_hash 11구성요소에 micom_version 포함 (golden regression 게이트 기반)."""
    import dataclasses

    result, _bundle = solve("gurobi")
    comps = _run_hash_components(result)          # RunHashComponents (I-5: 단일 canonical)
    d = dataclasses.asdict(comps)
    assert "micom_version" in d
    assert comps.micom_version and comps.micom_version != "unknown"
    assert len(d) == 11                            # 정확히 11구성요소


def test_community_solves_nonempty():
    """SC-7(축약): 스크립트 0줄로 3-member community 가 산출을 낸다."""
    result, bundle = solve("gurobi")
    assert result.status == "optimal"
    assert result.objective > 0
    assert bundle.nodes.num_rows == 4   # 3 member + 1 environment_pool
    assert bundle.profile.num_rows > 0  # 환경 exchange 존재


def test_fixtures_committed():
    """golden 디렉토리가 실제로 존재(캡처됨)."""
    for solver in SOLVER_VARIANTS:
        for table in ("nodes", "edges", "profile"):
            assert (EXPECTED / solver / f"{table}.parquet").exists()
        assert (EXPECTED / solver / "growth_expected.tsv").exists()
        assert (EXPECTED / solver / "sign_expected.tsv").exists()


def test_expected_dir_is_under_fixtures():
    assert isinstance(EXPECTED, Path)
    assert EXPECTED.parts[-3:] == ("fixtures", "community_3_member", "expected")


@pytest.mark.parametrize("solver,exp_flux_solver,exp_report", [
    ("gurobi", "gurobi", "full"),                                # gurobi = canonical full-flux
    ("osqp", None, "qp_only_approximate"),                       # C-1/C-2: OSQP=QP only → LP 부재
])
def test_flux_report_metadata_per_solver(solver, exp_flux_solver, exp_report):
    """F1: gurobi=full, osqp=qp_only_approximate(flux_solver=None). hybrid 폐기."""
    result, _ = solve(solver)
    assert result.flux_solver == exp_flux_solver
    assert result.flux_report_status == exp_report


def test_hybrid_solver_removed():
    """F1 (SC-C3): osqp_growth_highs_flux 폐기 — SOLVER_VARIANTS·SOLVER_MAP 에서 제거."""
    from cmig.core.engine import SOLVER_MAP
    assert "osqp_growth_highs_flux" not in SOLVER_VARIANTS
    assert "osqp_growth_highs_flux" not in SOLVER_MAP
    assert set(SOLVER_VARIANTS) == {"gurobi", "osqp"}
