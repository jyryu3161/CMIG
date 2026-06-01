"""G4 Sweep — run_hash 캐시·실패 diagnostic·AggregationStore. Plan SC: SC-4."""

import pyarrow.parquet as pq
import pytest

from cmig.core.manifest import RunHashComponents, compute_run_hash
from cmig.core.sweep import (
    RunHashCache,
    SweepAxis,
    SweepCondition,
    enumerate_conditions,
    run_sweep,
    write_sweep_parquet,
)


def test_axis_kind_validated():
    SweepAxis("tradeoff_f", [0.3, 0.5])      # ok
    with pytest.raises(ValueError):
        SweepAxis("not_an_axis", [1])


def test_enumerate_cartesian():
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5]), SweepAxis("solver", ["gurobi", "osqp"])]
    conds = enumerate_conditions(axes)
    assert len(conds) == 4
    assert conds[0].axis_values == {"tradeoff_f": 0.3, "solver": "gurobi"}
    assert all(c.condition_id.startswith("cond-") for c in conds)


def _rh(cond: SweepCondition) -> str:
    return f"hash::{cond.axis_values}"


def test_cache_hit_avoids_recompute():
    """SC-4: 동일 조건 재sweep → 캐시 hit, solve 미호출."""
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5])]
    calls = {"n": 0}

    def solve_fn(cond):
        calls["n"] += 1
        return cond.axis_values["tradeoff_f"] * 10

    cache = RunHashCache()
    run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="growth", cache=cache)
    assert calls["n"] == 2 and cache.misses == 2
    # 두 번째 sweep — 동일 cache → 전부 hit, solve 추가 호출 없음
    rows2 = run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="growth", cache=cache)
    assert calls["n"] == 2                    # 재계산 회피
    assert all(r.cache_hit for r in rows2)
    assert cache.hits == 2


def test_changed_component_misses():
    axes = [SweepAxis("tradeoff_f", [0.3])]
    cache = RunHashCache()
    run_sweep(axes, run_hash_fn=_rh, solve_fn=lambda c: 1.0, metric="g", cache=cache)
    # 다른 tradeoff_f → 다른 run_hash → miss
    axes2 = [SweepAxis("tradeoff_f", [0.7])]
    rows = run_sweep(axes2, run_hash_fn=_rh, solve_fn=lambda c: 2.0, metric="g", cache=cache)
    assert rows[0].cache_hit is False


def test_failed_run_records_diagnostic():
    """SC-4: 실패 run 도 condition_id별 diagnostic 저장(누락 금지)."""
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5])]

    def solve_fn(cond):
        if cond.axis_values["tradeoff_f"] == 0.5:
            raise RuntimeError("infeasible")
        return 1.0

    rows = run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="g")
    failed = [r for r in rows if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].value is None
    assert failed[0].diagnostic and "infeasible" in failed[0].diagnostic   # 누락 0


def test_run_hash_determinism_real_manifest():
    """sweep 축이 run_hash 11구성요소를 바꾸면 hash 가 달라진다 (SC-4 연동)."""
    def comps(f):
        return RunHashComponents(
            model_checksum="m", medium_checksum="md", member_set=["A"], abundance={"A": 1.0},
            bounds={}, tradeoff_f=f, solver_setting={"growth_solver": "gurobi"},
            micom_version="0.39.0", cmig_core_version="0.1.0",
            namespace_mapping_decisions=[], flux_normalization_method="pfba",
        )
    assert compute_run_hash(comps(0.3)) != compute_run_hash(comps(0.5))
    assert compute_run_hash(comps(0.5)) == compute_run_hash(comps(0.5))


def test_write_sweep_parquet_roundtrip(tmp_path):
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5])]

    def solve_fn(cond):
        if cond.axis_values["tradeoff_f"] == 0.5:
            raise ValueError("bad")
        return 4.2

    rows = run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="growth")
    out = tmp_path / "sweep.parquet"
    write_sweep_parquet(rows, out)
    t = pq.read_table(out)
    assert t.num_rows == 2
    assert set(t.column("status").to_pylist()) == {"ok", "failed"}
    # failed 행의 diagnostic 은 비어있지 않음
    recs = t.to_pylist()
    failed = [r for r in recs if r["status"] == "failed"][0]
    assert failed["value"] is None and failed["diagnostic"]


def test_schema_version_first_column():
    """C-3: SWEEP_SCHEMA 첫 컬럼 = schema_version (schema §6.1)."""
    from cmig.core.sweep import SWEEP_SCHEMA_VERSION, write_sweep_parquet
    axes = [SweepAxis("tradeoff_f", [0.3])]
    rows = run_sweep(axes, run_hash_fn=_rh, solve_fn=lambda c: 1.0, metric="g")
    import pathlib
    import tempfile
    out = pathlib.Path(tempfile.mkdtemp()) / "s.parquet"
    write_sweep_parquet(rows, out)
    t = pq.read_table(out)
    assert t.schema.names[0] == "schema_version"
    assert set(t.column("schema_version").to_pylist()) == {SWEEP_SCHEMA_VERSION}


def test_failed_run_is_cached():
    """I-2: 실패 run 도 캐시 → 동일 조건 재sweep 시 재계산 안 함."""
    axes = [SweepAxis("tradeoff_f", [0.5])]
    calls = {"n": 0}
    def solve_fn(cond):
        calls["n"] += 1
        raise RuntimeError("infeasible")
    cache = RunHashCache()
    r1 = run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="g", cache=cache)
    r2 = run_sweep(axes, run_hash_fn=_rh, solve_fn=solve_fn, metric="g", cache=cache)
    assert calls["n"] == 1                         # 두 번째는 캐시 hit (재계산 없음)
    assert r1[0].status == "failed" and r2[0].status == "failed"
    assert r2[0].cache_hit is True and r2[0].diagnostic
