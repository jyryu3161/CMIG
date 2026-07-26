"""Phase 0.1 — FileSystemStore (Store seam #3). Plan SC: SC-S2·SC-S4.

run_hash별 artifact + sqlite meta + cache_lookup. core RunStore Protocol 충족(sandbox commit
경유 영속). run_hash 는 인자(재계산 0). micom 불필요(순수 store 단위 — SolveResult 직접 구성).
"""

from __future__ import annotations

import math

from cmig.core.engine import SolveResult
from cmig.core.run_store import RunStore
from cmig.core.sandbox import RunStore as SandboxRunStore  # back-compat re-export
from cmig.service import FileSystemStore


def _result(objective: float = 0.42, status: str = "optimal") -> SolveResult:
    return SolveResult(
        objective=objective,
        member_growth={"A": 0.4},
        abundances={"A": 1.0},
        external_exchange={},
        member_exchange={},
        status=status,  # type: ignore[arg-type]
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        diagnostic=None,
        members=["A"],
    )


# R5-P3 (codex F13): ``record_run`` now enforces the contract it always documented — a run_hash
# is a canonical SHA-256 hex digest — because treating an arbitrary string as a path component let
# ``../escaped`` create a directory outside the store root. These fixtures used short placeholders
# purely for readability; production callers have always passed ``compute_run_hash`` output
# (cmig/service/engine_service.py builds it, cmig/core/sandbox.py forwards it). Rejection of a
# non-digest is covered by tests/test_round5_p3_io_exception.py.
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_NAN = "c" * 64
HASH_COMMIT = "d" * 64


def test_filesystem_store_satisfies_runstore_protocol(tmp_path):
    """SC-S4: FileSystemStore 가 core RunStore Protocol 충족 + sandbox re-export 동일 객체."""
    store = FileSystemStore(tmp_path)
    assert isinstance(store, RunStore)            # runtime_checkable
    assert SandboxRunStore is RunStore            # sandbox 가 core/run_store 를 re-export


def test_record_run_then_cache_lookup_hit(tmp_path):
    """SC-S2: record_run 후 cache_lookup hit(meta dict) + run_dir 생성."""
    store = FileSystemStore(tmp_path)
    store.record_run(HASH_A, _result(objective=0.42), micom_version="0.39.0")
    row = store.cache_lookup_by_run_hash(HASH_A)
    assert row is not None
    assert row["run_hash"] == HASH_A and row["status"] == "optimal"
    assert abs(float(row["objective"]) - 0.42) < 1e-9
    assert row["flux_solver"] == "gurobi"
    assert row["micom_version"] == "0.39.0"
    assert (tmp_path / HASH_A).is_dir()
    assert row["run_dir"] == str(tmp_path / HASH_A)


def test_cache_lookup_miss_returns_none(tmp_path):
    """SC-S2: 미기록 run_hash → None (재solve·재계산 없음)."""
    assert FileSystemStore(tmp_path).cache_lookup_by_run_hash("nope") is None


def test_record_run_idempotent(tmp_path):
    """동일 run_hash 2회 → 1 row 유지(INSERT OR IGNORE, 첫 기록 보존)."""
    store = FileSystemStore(tmp_path)
    store.record_run(HASH_B, _result(objective=1.0))
    store.record_run(HASH_B, _result(objective=2.0))   # ignored
    assert abs(float(store.cache_lookup_by_run_hash(HASH_B)["objective"]) - 1.0) < 1e-9


def test_record_run_nan_objective_stored_null(tmp_path):
    """NaN objective → NULL(직렬화 안전)."""
    store = FileSystemStore(tmp_path)
    store.record_run(HASH_NAN, _result(objective=math.nan))
    assert store.cache_lookup_by_run_hash(HASH_NAN)["objective"] is None


def test_sandbox_commit_via_filesystem_store(tmp_path):
    """SC-S4: evaluate_sandbox(store=FileSystemStore) COMMIT → record_run 영속."""
    from cmig.core.sandbox import SandboxState, evaluate_sandbox

    store = FileSystemStore(tmp_path)
    res = evaluate_sandbox(
        _result(objective=0.4), _result(objective=0.3),
        state=SandboxState.COMMITTED, store=store, run_hash=HASH_COMMIT, micom_version="0.39.0",
    )
    assert res.committed and res.run_hash == HASH_COMMIT
    row = store.cache_lookup_by_run_hash(HASH_COMMIT)
    assert row is not None
    assert row["micom_version"] == "0.39.0"


def test_sandbox_preview_does_not_persist(tmp_path):
    """SC-8 불변: preview 는 store 비기록(FileSystemStore 도 동일)."""
    from cmig.core.sandbox import SandboxState, evaluate_sandbox

    store = FileSystemStore(tmp_path)
    evaluate_sandbox(
        _result(objective=0.4), _result(objective=0.4),
        state=SandboxState.PREVIEW, store=store,
    )
    assert store.cache_lookup_by_run_hash("any") is None
