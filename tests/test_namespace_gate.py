"""SC-3 namespace hard gate — §4.8 차단/경고 동작. Plan SC: SC-3."""

import pytest

from cmig.core.namespace import (
    Confidence,
    DecisionStatus,
    GateBlockedError,
    NamespaceDecision,
    decisions_to_jsonable,
    evaluate_gate,
    suggest_namespace_decisions,
)


def _d(metab, conf, status, target="bigg:x"):
    return NamespaceDecision(
        metabolite=metab, source_id=f"src:{metab}",
        target_id=None if status is DecisionStatus.UNRESOLVED else target,
        confidence=conf, status=status,
    )


def test_unresolved_high_confidence_blocks():
    decisions = [
        _d("glc", Confidence.HIGH, DecisionStatus.RESOLVED),
        _d("ac", Confidence.HIGH, DecisionStatus.UNRESOLVED),  # → 차단
    ]
    result = evaluate_gate(decisions)
    assert result.blocked is True
    assert [d.metabolite for d in result.unresolved_high] == ["ac"]
    with pytest.raises(GateBlockedError):
        result.raise_if_blocked()


def test_low_confidence_warns_and_proceeds_no_automerge():
    decisions = [
        _d("glc", Confidence.HIGH, DecisionStatus.RESOLVED),
        _d("xyz", Confidence.LOW, DecisionStatus.WARNED),  # 경고 후 진행
    ]
    result = evaluate_gate(decisions)
    assert result.blocked is False           # 차단 아님
    assert len(result.warned_low) == 1
    # 자동병합 금지: WARNED 결정은 RESOLVED 로 승격되지 않는다.
    assert result.warned_low[0].status is DecisionStatus.WARNED
    result.raise_if_blocked()  # 예외 없음


def test_all_resolved_passes_with_full_coverage():
    decisions = [
        _d("glc", Confidence.HIGH, DecisionStatus.RESOLVED),
        _d("ac", Confidence.HIGH, DecisionStatus.RESOLVED),
    ]
    result = evaluate_gate(decisions)
    assert result.blocked is False
    assert result.coverage_pct == 100.0


def test_coverage_pct_partial():
    decisions = [
        _d("a", Confidence.HIGH, DecisionStatus.RESOLVED),
        _d("b", Confidence.LOW, DecisionStatus.WARNED),
        _d("c", Confidence.LOW, DecisionStatus.WARNED),
        _d("d", Confidence.HIGH, DecisionStatus.RESOLVED),
    ]
    result = evaluate_gate(decisions)
    assert result.coverage_pct == 50.0  # 2 resolved / 4 total


def test_empty_decisions_is_full_coverage_unblocked():
    result = evaluate_gate([])
    assert result.blocked is False
    assert result.coverage_pct == 100.0


def test_namespace_suggest_exact_matches_and_unresolved():
    decisions = suggest_namespace_decisions(["ac", "unknown"], known_targets={"ac"})
    by_met = {d.metabolite: d for d in decisions}
    assert by_met["ac"].status is DecisionStatus.RESOLVED
    assert by_met["ac"].target_id == "bigg:ac"
    assert by_met["unknown"].status is DecisionStatus.UNRESOLVED
    payload = decisions_to_jsonable(decisions)
    assert payload[0]["confidence"] == "high"
