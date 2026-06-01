"""G1 Constraint Sandbox — preview/commit 분리. Plan SC: SC-8 (preview 비오염)."""

import pytest

from cmig.core.engine import SolveResult
from cmig.core.sandbox import (
    InMemoryRunStore,
    SandboxState,
    evaluate_sandbox,
)


def _result(external, growth=0.5):
    return SolveResult(
        objective=growth, member_growth={"A": growth}, abundances={"A": 1.0},
        external_exchange=external, member_exchange={"A": {}}, status="optimal",
        flux_report_status="full", growth_solver="gurobi", flux_solver="gurobi", members=["A"],
    )


def test_preview_does_not_write_store():
    """SC-8 핵심: preview solve 는 store 에 기록하지 않는다."""
    store = InMemoryRunStore()
    base = _result({"ac": 5.0})
    constrained = _result({"ac": 8.0})
    res = evaluate_sandbox(base, constrained, state=SandboxState.PREVIEW, store=store)
    assert store.count == 0                 # 비오염
    assert res.committed is False
    assert res.run_hash is None             # ephemeral
    assert res.state is SandboxState.PREVIEW


def test_commit_promotes_to_artifact():
    """Apply/Save: commit 시에만 store.record_run + run_hash 승격."""
    store = InMemoryRunStore()
    base = _result({"ac": 5.0})
    constrained = _result({"ac": 8.0})
    res = evaluate_sandbox(
        base, constrained, state=SandboxState.COMMITTED, store=store, run_hash="rh-123",
    )
    assert store.count == 1                  # 1 artifact 승격
    assert res.committed is True
    assert res.run_hash == "rh-123"


def test_commit_requires_run_hash():
    with pytest.raises(ValueError):
        evaluate_sandbox(_result({"ac": 5.0}), _result({"ac": 8.0}),
                         state=SandboxState.COMMITTED, store=InMemoryRunStore())


def test_no_significant_change_diagnostic():
    """보상 우회로 변화 미미 → no_significant_change=True."""
    base = _result({"ac": 5.0, "co2": 1.0})
    constrained = _result({"ac": 5.0, "co2": 1.0})  # 동일 = 변화 없음
    res = evaluate_sandbox(base, constrained, state=SandboxState.PREVIEW)
    assert res.no_significant_change is True


def test_significant_change_detected():
    base = _result({"ac": 5.0})
    constrained = _result({"ac": 9.0})       # 변화 큼
    res = evaluate_sandbox(base, constrained, state=SandboxState.PREVIEW)
    assert res.no_significant_change is False
    assert res.delta.significant()[0].metabolite == "ac"


def test_multiple_previews_never_contaminate():
    """preview N회 반복 → store 레코드 0 (sweep/cache/store 비오염, A11)."""
    store = InMemoryRunStore()
    base = _result({"ac": 5.0})
    for i in range(5):
        evaluate_sandbox(base, _result({"ac": 5.0 + i}), state=SandboxState.PREVIEW, store=store)
    assert store.count == 0
