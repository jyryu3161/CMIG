"""SC-3 namespace hard gate — §4.8 차단/경고 동작. Plan SC: SC-3."""

import pytest

from cmig.core.namespace import (
    Confidence,
    DecisionStatus,
    GateBlockedError,
    NamespaceDecision,
    apply_namespace_decisions_to_model,
    decisions_to_jsonable,
    evaluate_gate,
    mapped_taxonomy,
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


def test_low_confidence_resolved_is_not_warned():
    result = evaluate_gate([_d("x", Confidence.LOW, DecisionStatus.RESOLVED)])
    assert result.coverage_pct == 100.0
    assert result.warned_low == []


def test_coverage_pct_partial():
    decisions = [
        _d("a", Confidence.HIGH, DecisionStatus.RESOLVED),
        _d("b", Confidence.LOW, DecisionStatus.WARNED),
        _d("c", Confidence.LOW, DecisionStatus.WARNED),
        _d("d", Confidence.HIGH, DecisionStatus.RESOLVED),
    ]
    result = evaluate_gate(decisions)
    assert result.coverage_pct == 50.0  # 2 resolved / 4 total


def test_empty_decisions_is_zero_coverage_and_blocked():
    result = evaluate_gate([])
    assert result.blocked is True
    assert result.missing_decisions is True
    assert result.coverage_pct == 0.0
    with pytest.raises(GateBlockedError, match="검토된 namespace decision"):
        result.raise_if_blocked()


def test_resolved_decision_requires_target():
    decision = NamespaceDecision(
        metabolite="ac", source_id="src:ac", target_id=None,
        confidence=Confidence.HIGH, status=DecisionStatus.RESOLVED,
    )
    with pytest.raises(ValueError, match="target_id"):
        evaluate_gate([decision])


def test_namespace_suggest_exact_matches_and_unresolved():
    decisions = suggest_namespace_decisions(
        ["ac", "EX_GLC_e", "unknown"],
        known_targets={"ac", "glc"},
    )
    by_met = {d.metabolite: d for d in decisions}
    assert by_met["ac"].status is DecisionStatus.RESOLVED
    assert by_met["ac"].target_id == "bigg:ac"
    assert by_met["EX_GLC_e"].status is DecisionStatus.WARNED
    assert by_met["EX_GLC_e"].confidence is Confidence.LOW
    assert by_met["EX_GLC_e"].target_id == "bigg:glc"
    assert by_met["unknown"].status is DecisionStatus.UNRESOLVED
    payload = decisions_to_jsonable(decisions)
    by_payload = {d["metabolite"]: d for d in payload}
    assert by_payload["ac"]["confidence"] == "high"
    assert by_payload["EX_GLC_e"]["confidence"] == "low"


def test_resolved_mapping_is_applied_to_model_copy_ids():
    cobra = pytest.importorskip("cobra")
    model = cobra.Model("mapped")
    acetate = cobra.Metabolite("acetate_e", compartment="e")
    exchange = cobra.Reaction("EX_acetate_e")
    exchange.add_metabolites({acetate: -1.0})
    model.add_reactions([exchange])
    decision = NamespaceDecision(
        metabolite="acetate", source_id="source:acetate", target_id="bigg:ac",
        confidence=Confidence.HIGH, status=DecisionStatus.RESOLVED,
    )

    applied = apply_namespace_decisions_to_model(model, [decision])

    assert model.metabolites.has_id("ac_e")
    assert model.reactions.has_id("EX_ac_e")
    assert len(applied) == 1
    assert applied[0].source_metabolite_id == "acetate_e"
    assert applied[0].target_metabolite_id == "ac_e"


def test_warned_mapping_is_never_applied():
    cobra = pytest.importorskip("cobra")
    model = cobra.Model("warned")
    acetate = cobra.Metabolite("acetate_e", compartment="e")
    exchange = cobra.Reaction("EX_acetate_e")
    exchange.add_metabolites({acetate: -1.0})
    model.add_reactions([exchange])
    decision = NamespaceDecision(
        metabolite="acetate", source_id="source:acetate", target_id="bigg:ac",
        confidence=Confidence.LOW, status=DecisionStatus.WARNED,
    )

    assert apply_namespace_decisions_to_model(model, [decision]) == []
    assert model.metabolites.has_id("acetate_e")


def test_mapped_taxonomy_serializes_temporary_model_and_preserves_source(tmp_path):
    cobra = pytest.importorskip("cobra")
    pd = pytest.importorskip("pandas")
    model = cobra.Model("mapped")
    acetate = cobra.Metabolite("acetate_e", compartment="e")
    exchange = cobra.Reaction("EX_acetate_e")
    exchange.add_metabolites({acetate: -1.0})
    model.add_reactions([exchange])
    source = tmp_path / "source.xml"
    cobra.io.write_sbml_model(model, str(source))
    taxonomy = pd.DataFrame({"id": ["A"], "file": [str(source)], "abundance": [1.0]})
    decision = NamespaceDecision(
        metabolite="acetate", source_id="source:acetate", target_id="bigg:ac",
        confidence=Confidence.HIGH, status=DecisionStatus.RESOLVED,
    )

    with mapped_taxonomy(taxonomy, [decision]) as (mapped, applied):
        mapped_path = mapped.loc[0, "file"]
        mapped_model = cobra.io.read_sbml_model(mapped_path)
        assert mapped_model.reactions.has_id("EX_ac_e")
        assert len(applied) == 1

    source_model = cobra.io.read_sbml_model(str(source))
    assert source_model.reactions.has_id("EX_acetate_e")
