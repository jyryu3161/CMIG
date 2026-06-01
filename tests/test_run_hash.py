"""SC-4 run_hash 결정성·캐시 키 — schema §4.2. Plan SC: SC-4."""

import dataclasses
from types import SimpleNamespace

from cmig.core.manifest import (
    RUN_HASH_COMPONENTS,
    RunHashComponents,
    canonical_payload,
    compute_run_hash,
)
from cmig.io.solve_output import build_run_components


def _components(**over):
    base = dict(
        model_checksum="m-abc",
        medium_checksum="med-123",
        member_set=["B", "A", "C"],
        abundance={"A": 0.5, "B": 0.3, "C": 0.2},
        bounds={"EX_glc": [-10.0, 1000.0]},
        tradeoff_f=0.5,
        solver_setting={"growth_solver": "osqp", "flux_solver": "gurobi", "tolerance": 1e-6},
        micom_version="0.33.0",
        cmig_core_version="0.1.0",
        namespace_mapping_decisions=["glc->bigg:glc", "ac->bigg:ac"],
        flux_normalization_method="pfba",
    )
    base.update(over)
    return RunHashComponents(**base)


def test_exactly_eleven_components():
    assert len(RUN_HASH_COMPONENTS) == 11
    assert set(RUN_HASH_COMPONENTS) == {f.name for f in dataclasses.fields(RunHashComponents)}


def test_same_components_same_hash():
    assert compute_run_hash(_components()) == compute_run_hash(_components())


def test_member_set_order_invariant():
    # member_set 정렬 → 순서만 다르면 동일 hash
    h1 = compute_run_hash(_components(member_set=["A", "B", "C"]))
    h2 = compute_run_hash(_components(member_set=["C", "B", "A"]))
    assert h1 == h2


def test_any_component_change_changes_hash():
    base = compute_run_hash(_components())
    assert compute_run_hash(_components(tradeoff_f=0.6)) != base
    assert compute_run_hash(_components(micom_version="0.34.0")) != base
    assert compute_run_hash(_components(bounds={"EX_glc": [-9.0, 1000.0]})) != base
    assert compute_run_hash(_components(flux_normalization_method="fba")) != base


def test_build_run_components_threads_bounds_into_hash():
    result = SimpleNamespace(
        abundances={"A": 1.0},
        members=["A"],
        growth_solver="gurobi",
        flux_solver="gurobi",
    )
    a = build_run_components(
        result,
        model_checksum="m",
        medium_checksum="med",
        tradeoff_f=0.5,
        micom_version="0.39.0",
        bounds={"EX_x": [-1.0, 1000.0]},
    )
    b = build_run_components(
        result,
        model_checksum="m",
        medium_checksum="med",
        tradeoff_f=0.5,
        micom_version="0.39.0",
        bounds={"EX_x": [-2.0, 1000.0]},
    )
    assert compute_run_hash(a) != compute_run_hash(b)


def test_float_rounding_absorbs_noise():
    # 6 decimal 이하 잡음은 동일 hash (alternate-optima 흡수)
    h1 = compute_run_hash(_components(tradeoff_f=0.5))
    h2 = compute_run_hash(_components(tradeoff_f=0.5 + 1e-9))
    assert h1 == h2


def test_env_lock_not_in_payload():
    payload = canonical_payload(_components())
    assert "env_lock" not in payload
    assert set(payload.keys()) == set(RUN_HASH_COMPONENTS)


def test_non_finite_floats_deterministic():
    """I-6: bounds 의 ±inf/NaN 가 결정적 sentinel 로 직렬화(NaN≠NaN·Infinity 비결정성 제거)."""
    import math

    def inf_b():
        return _components(bounds={"EX_x": [-math.inf, math.inf]})

    def nan_b():
        return _components(bounds={"EX_x": [math.nan, 1.0]})

    # 예외 없이 결정적 hash 산출 + 동일 입력 동일 hash
    assert compute_run_hash(inf_b()) == compute_run_hash(inf_b())
    assert compute_run_hash(nan_b()) == compute_run_hash(nan_b())
    # inf != finite
    assert compute_run_hash(inf_b()) != compute_run_hash(_components(bounds={"EX_x": [-1.0, 1.0]}))
