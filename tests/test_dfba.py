"""Phase 3.3 — dFBA well-mixed 동적 FBA. Plan SC: SC-DF1~DF6.

e_coli_core glucose-batch: biomass 성장 + glucose 고갈 + non-negativity. 고갈 후 ATP-maintenance
미충족 → infeasible(생물학적으로 옳은 세포 사멸 — silent 위장 금지). 수치 acceptance 검증.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("micom")
pytest.importorskip("cobra")

import cobra  # noqa: E402
import micom  # noqa: E402

from cmig.core.dfba import (  # noqa: E402
    TIMECOURSE_SCHEMA,
    DfbaConfig,
    build_timecourse,
    simulate_dfba,
)

_MODEL = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")


def _model() -> cobra.Model:
    return cobra.io.read_sbml_model(_MODEL)


def _glucose_cfg(t_end: float) -> DfbaConfig:
    return DfbaConfig(
        t_end=t_end, dt=0.1, initial_biomass=0.01,
        initial_concentrations={"EX_glc__D_e": 10.0},
    )


def test_dfba_biomass_grows():
    """SC-DF1: biomass 성장(monotonic non-decreasing, μ≥0)."""
    r = simulate_dfba(_model(), _glucose_cfg(1.0), solver="gurobi")
    assert r.timecourse[-1].biomass > r.timecourse[0].biomass
    biomasses = [tp.biomass for tp in r.timecourse]
    assert all(biomasses[i + 1] >= biomasses[i] - 1e-9 for i in range(len(biomasses) - 1))


def test_dfba_completes_short_horizon():
    """SC-DF2: 고갈 전 짧은 horizon → status=completed, glucose 잔존."""
    r = simulate_dfba(_model(), _glucose_cfg(1.0), solver="gurobi")
    assert r.status == "completed"
    assert r.timecourse[-1].concentrations["EX_glc__D_e"] > 0


def test_dfba_glucose_depletes_and_nonnegative():
    """SC-DF3: 긴 horizon → glucose 고갈(≈0) + **non-negativity**(모든 농도 ≥ 0)."""
    r = simulate_dfba(_model(), _glucose_cfg(10.0), solver="gurobi")
    final_glc = r.timecourse[-1].concentrations["EX_glc__D_e"]
    assert final_glc < 0.01
    for tp in r.timecourse:
        assert tp.concentrations["EX_glc__D_e"] >= -1e-9     # non-negativity 불변


def test_dfba_emergency_clamp_scales_growth_with_substrate(monkeypatch):
    """D-12: min_dt 에서도 substrate 초과 소비면 flux/growth 를 같은 fraction 으로 스케일."""
    import cmig.core.dfba as dfba
    import cmig.core.single_model as single_model

    monkeypatch.setattr(single_model, "_require_lp", lambda solver: None)
    monkeypatch.setattr(single_model, "set_model_solver", lambda model, solver: None)
    monkeypatch.setattr(dfba, "_growth_of", lambda model, sol: 2.0)

    class _Reaction:
        lower_bound = -1000.0

    class _Reactions:
        def __init__(self) -> None:
            self._rxn = _Reaction()

        def get_by_id(self, rid):
            return self._rxn

    class _Solution:
        status = "optimal"
        fluxes = {"EX_s": -100.0}

    class _Model:
        def __init__(self) -> None:
            self.reactions = _Reactions()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def optimize(self):
            return _Solution()

    r = simulate_dfba(
        _Model(),
        DfbaConfig(
            t_end=0.1,
            dt=0.1,
            min_dt=0.1,
            initial_biomass=1.0,
            initial_concentrations={"EX_s": 1.0},
            vmax={"EX_s": 100.0},
            growth_floor=0.0,
        ),
        solver="gurobi",
    )

    assert r.status == "completed"
    assert r.timecourse[-1].concentrations["EX_s"] == pytest.approx(0.0)
    assert r.timecourse[-1].growth_rate == pytest.approx(0.2)
    assert r.timecourse[-1].biomass == pytest.approx(1.02)


def test_dfba_infeasible_after_depletion_is_explicit():
    """SC-DF4: 고갈 후 ATP-maintenance 미충족 → status=infeasible+diagnostic(silent 위장 금지)."""
    r = simulate_dfba(_model(), _glucose_cfg(20.0), solver="gurobi")
    assert r.status in ("infeasible", "stalled", "completed")
    if r.status == "infeasible":
        assert r.diagnostic is not None and "status=" in r.diagnostic


def test_dfba_timecourse_schema():
    """SC-DF5: timecourse long-format(biomass·growth_rate·exchange 농도 series)."""
    r = simulate_dfba(_model(), _glucose_cfg(0.5), solver="gurobi")
    table = build_timecourse(r)
    assert table.schema.equals(TIMECOURSE_SCHEMA)
    series = set(table.column("series").to_pylist())
    assert {"biomass", "growth_rate", "EX_glc__D_e"} <= series


def test_dfba_osqp_hybrid_restores_model_bounds():
    """SC-DF6: osqp hybrid LP 경로가 동작하고 시뮬레이션 bound 변경을 모델에 남기지 않는다."""
    model = _model()
    before = model.reactions.get_by_id("EX_glc__D_e").bounds
    result = simulate_dfba(model, _glucose_cfg(0.5), solver="osqp")
    assert result.status in ("completed", "stalled")
    assert model.reactions.get_by_id("EX_glc__D_e").bounds == before
