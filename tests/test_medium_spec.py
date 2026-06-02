"""C6 — Medium 입력/preset. Plan SC: SC-F3·F4.

Design Ref(foundations): §4. MediumSpec(uptake_limit≥0)·load·apply(community.medium)·checksum.
순수 검증(spec/checksum)은 micom 비의존; apply/CLI 통합은 micom 필요(importorskip).
"""

from __future__ import annotations

import json

import pytest

from cmig.core.medium_spec import MediumSpec, load_medium, medium_checksum

PRESETS = "medium_presets"


# ── 순수 (micom 비의존) ──────────────────────────────────────────────────────

def test_medium_spec_validates_nonnegative():
    MediumSpec({"EX_glc__D_m": 10.0}).validate()
    with pytest.raises(ValueError):
        MediumSpec({"EX_glc__D_m": -1.0}).validate()       # 음수 uptake_limit 금지
    with pytest.raises(ValueError):
        MediumSpec({"EX_x_m": float("nan")}).validate()    # 비유한 금지


def test_load_csv_and_json(tmp_path):
    csv_p = tmp_path / "m.csv"
    csv_p.write_text("exchange_id,uptake_limit\nEX_glc__D_m,5.0\nEX_o2_m,1000\n")
    spec = load_medium(csv_p)
    assert spec.uptake == {"EX_glc__D_m": 5.0, "EX_o2_m": 1000.0}

    json_p = tmp_path / "m.json"
    json_p.write_text(json.dumps({"EX_glc__D_m": 5.0}))
    assert load_medium(json_p).uptake == {"EX_glc__D_m": 5.0}


def test_load_csv_bad_header_fails(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("ex,val\nEX_glc__D_m,5\n")
    with pytest.raises(ValueError):
        load_medium(p)


def test_presets_load():
    for name in ("western_diet", "high_fiber"):
        spec = load_medium(f"{PRESETS}/{name}.csv")
        spec.validate()
        assert spec.uptake                                  # 비어있지 않음


def test_medium_checksum_deterministic_and_distinct():
    a = MediumSpec({"EX_glc__D_m": 20.0})
    b = MediumSpec({"EX_glc__D_m": 3.0})
    assert medium_checksum(a) == medium_checksum(a)          # 결정적
    assert medium_checksum(a) != medium_checksum(b)          # 다른 medium → 다른 checksum
    assert medium_checksum(None) == "micom_default_medium"   # default sentinel
    assert len(medium_checksum(a).removeprefix("medium:")) == 64


# ── micom 통합 ───────────────────────────────────────────────────────────────

def test_apply_medium_changes_external_profile():
    """SC-F3: medium A(고당) vs B(저당) → external_profile·growth 상이."""
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.core.medium_spec import apply_medium
    from cmig.golden_fixture import TRADEOFF_F, build_taxonomy

    eng = MicomEngine()
    tax = build_taxonomy()

    def solve_with(preset):
        c = eng.build_community(tax, cmig_solver="gurobi")
        apply_medium(c, load_medium(f"{PRESETS}/{preset}.csv"))
        return eng.cooperative_tradeoff(c, TRADEOFF_F, cmig_solver="gurobi")

    western = solve_with("western_diet")
    fiber = solve_with("high_fiber")
    assert abs(western.objective - fiber.objective) > 1e-4, "diet 차이가 growth 에 미반영"


def test_apply_medium_returns_original_for_undo():
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.core.medium_spec import apply_medium
    from cmig.golden_fixture import build_taxonomy

    c = MicomEngine().build_community(build_taxonomy(), cmig_solver="gurobi")
    before = dict(c.medium)
    original = apply_medium(c, MediumSpec({"EX_glc__D_m": 1.0}))
    assert original == before                               # undo 자산
    assert c.medium["EX_glc__D_m"] == 1.0                   # 실제 적용됨
