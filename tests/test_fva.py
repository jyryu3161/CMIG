"""AN-SINGLE FVA (실제 cobra) — G-3 해소. Plan SC: SC-H4.

Design Ref(hardening): §5.2 — cobra flux_variability_analysis 위임, fva_lo≤net≤fva_hi 불변,
infeasible 명시 에러, profile fva_lo/hi 실채움.
"""

import math

import pytest

pytest.importorskip("cobra")

from cmig.core.fva import (  # noqa: E402
    FVAInfeasibleError,
    FVARange,
    attach_fva_to_profile,
    flux_variability,
)


@pytest.fixture(scope="module")
def textbook():
    import cobra

    return cobra.io.load_model("textbook")          # e_coli_core


def test_fva_ranges_lo_le_hi(textbook):
    """모든 reaction 의 FVA 범위가 lo ≤ hi (불변식)."""
    fva = flux_variability(textbook, fraction_of_optimum=1.0)
    assert len(fva) == len(textbook.reactions)
    for rng in fva.values():
        assert isinstance(rng, FVARange)
        assert rng.lo <= rng.hi
        assert math.isfinite(rng.lo) and math.isfinite(rng.hi)


def test_fva_brackets_optimal_flux(textbook):
    """fraction_of_optimum=1 → 최적 flux 가 [lo, hi] 안에 포함."""
    sol = textbook.optimize()
    fva = flux_variability(textbook, fraction_of_optimum=1.0)
    rid = textbook.reactions[0].id
    v = sol.fluxes[rid]
    assert fva[rid].lo - 1e-6 <= v <= fva[rid].hi + 1e-6


def test_fraction_widens_ranges(textbook):
    """fraction_of_optimum 완화(0.5) → 범위가 좁아지지 않는다(≥ 1.0 폭)."""
    tight = flux_variability(textbook, fraction_of_optimum=1.0)
    loose = flux_variability(textbook, fraction_of_optimum=0.5)
    rid = next(r.id for r in textbook.reactions if "EX_glc" in r.id)
    assert (loose[rid].hi - loose[rid].lo) >= (tight[rid].hi - tight[rid].lo) - 1e-6


def test_fraction_out_of_range_raises(textbook):
    with pytest.raises(ValueError):
        flux_variability(textbook, fraction_of_optimum=0.0)
    with pytest.raises(ValueError):
        flux_variability(textbook, fraction_of_optimum=1.5)


def test_attach_fva_populates_profile():
    """profile rows 에 fva_lo/hi 실채움 + 매칭 없으면 None(강제 0 금지)."""
    fva = {"EX_ac_e": FVARange("EX_ac_e", -2.0, 5.0)}
    rows = [
        {"metabolite": "EX_ac_e", "net_flux": 3.0, "label": "secretion"},
        {"metabolite": "EX_unknown_e", "net_flux": 0.0, "label": None},
    ]
    out = attach_fva_to_profile(rows, fva)
    assert out[0]["fva_lo"] == -2.0 and out[0]["fva_hi"] == 5.0
    assert out[0]["fva_lo"] <= out[0]["net_flux"] <= out[0]["fva_hi"]   # 불변식
    assert out[1]["fva_lo"] is None and out[1]["fva_hi"] is None        # 결측=None


def test_fva_infeasible_raises(textbook):
    """달성 불가 제약 강제 → FVAInfeasibleError (silent NaN 금지)."""
    m = textbook.copy()
    bio_id = next(r.id for r in m.reactions if "BIOMASS" in r.id.upper())
    m.reactions.get_by_id(bio_id).lower_bound = 1000.0   # 달성 불가 성장 하한 → infeasible
    with pytest.raises(FVAInfeasibleError):
        flux_variability(m, fraction_of_optimum=1.0)
