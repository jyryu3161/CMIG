"""C8 — SCFA target readout. Plan SC: SC-F5. (순수 + 실 profile 검증)"""

from __future__ import annotations

import pytest

from cmig.core.targets import (
    SCFA,
    TARGET_PRESETS,
    TargetMetaboliteSet,
    target_delta_summary,
    target_summary,
)


def test_scfa_preset_contains_acetate_butyrate():
    assert SCFA.matches("ac") and SCFA.matches("but")
    assert not SCFA.matches("glc__D")
    assert TARGET_PRESETS["scfa"] is SCFA


def test_target_summary_filters_and_sorts():
    profile = [
        {"metabolite": "glc__D", "net_flux": -10.0, "ui_flux": 10.0, "label": "uptake"},
        {"metabolite": "but", "net_flux": 2.0, "ui_flux": 2.0, "label": "secretion"},
        {"metabolite": "ac", "net_flux": 5.0, "ui_flux": 5.0, "label": "secretion"},
    ]
    out = target_summary(profile, SCFA)
    assert [r["metabolite"] for r in out] == ["ac", "but"]       # 정렬·glc 제외
    assert out[0]["label"] == "secretion"                        # 재분류 없이 그대로
    assert out[0]["net_flux"] == 5.0


def test_target_summary_empty_when_no_match():
    profile = [{"metabolite": "glc__D", "net_flux": -1.0, "ui_flux": 1.0, "label": "uptake"}]
    assert target_summary(profile, SCFA) == []


def test_custom_target_set():
    ts = TargetMetaboliteSet("custom", frozenset({"co2"}))
    profile = [{"metabolite": "co2", "net_flux": 3.0, "ui_flux": 3.0, "label": "secretion"}]
    assert len(target_summary(profile, ts)) == 1


def test_target_delta_summary():
    from cmig.core.delta import DeltaResult, MetaboliteDelta

    delta = DeltaResult(profile=[
        MetaboliteDelta("ac", 5.0, 8.0, 3.0),
        MetaboliteDelta("glc__D", -10.0, -8.0, 2.0),
    ])
    out = target_delta_summary(delta, SCFA)
    assert len(out) == 1 and out[0]["metabolite"] == "ac"
    assert out[0]["delta"] == 3.0


def test_scfa_extracted_from_real_profile():
    """SC-F5: 실 3-member profile 에서 acetate(SCFA) 가 target summary 로 추출됨."""
    pytest.importorskip("micom")
    from cmig.golden_fixture import solve

    _, bundle = solve("gurobi")
    summary = target_summary(bundle.profile.to_pylist(), SCFA)
    mets = {r["metabolite"] for r in summary}
    assert "ac" in mets, "실 profile 의 acetate 가 SCFA summary 에 미포함"
    # summary 행은 profile 의 sign 정규화 값을 보존(재분류 없음)
    for r in summary:
        assert r["ui_flux"] is not None and r["ui_flux"] >= 0.0
