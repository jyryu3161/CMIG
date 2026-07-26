"""Round 6 track B — instances 4 and 5 of the incomplete-enumeration defect.

Both sites claim to control an experiment by closing what can feed the model, and both enumerated
``model.exchanges``. The models here are deliberately minimal and carry a **sink** whose metabolite
is cytosolic, so it is a boundary reaction and not an exchange — the shape that made both claims
false on any GEM that ships one (Recon3D ships 101 sinks and 145 demands).

The invariant asserted is the same one as everywhere else in this round:
:func:`cmig.core.boundary.boundary_isolation_violations` must be empty after isolation.
"""

from __future__ import annotations

import pytest

from cmig.core.boundary import boundary_isolation_violations, mass_supplying_boundary

cobra = pytest.importorskip("cobra")
pytest.importorskip("gurobipy")


def _sink_fed_model() -> object:
    """Biomass is fed ONLY by a cytosolic sink; the exchange is a decoy the run will track.

    ``SK_atp_c`` is a boundary reaction (single metabolite) but not an exchange (``atp_c`` is not
    in the external compartment), so every loop over ``model.exchanges`` in this codebase was
    blind to it.
    """
    from cobra import Metabolite, Model, Reaction

    model = Model("sink_fed")
    glc_e = Metabolite("glc__D_e", compartment="e")
    atp_c = Metabolite("atp_c", compartment="c")
    model.add_metabolites([glc_e, atp_c])

    ex = Reaction("EX_glc__D_e", lower_bound=-10.0, upper_bound=1000.0)
    ex.add_metabolites({glc_e: -1.0})
    sink = Reaction("SK_atp_c", lower_bound=-1000.0, upper_bound=1000.0)
    sink.add_metabolites({atp_c: -1.0})
    biomass = Reaction("BIOMASS_test", lower_bound=0.0, upper_bound=1000.0)
    biomass.add_metabolites({atp_c: -1.0})
    model.add_reactions([ex, sink, biomass])
    model.objective = "BIOMASS_test"
    model.solver = "gurobi"
    return model


# ── instance 4: dFBA --close-untracked-uptake ──────────────────────────────────────────────────


def _dfba_config(**overrides: object) -> object:
    from cmig.core.dfba import DfbaConfig

    base = {
        "t_end": 0.3,
        "dt": 0.1,
        "initial_concentrations": {"EX_glc__D_e": 0.0},   # the tracked substrate starts EMPTY
        "initial_biomass": 0.01,
        "km": 0.01,
    }
    base.update(overrides)
    return DfbaConfig(**base)          # type: ignore[arg-type]


def test_dfba_close_untracked_uptake_closes_a_supplying_sink():
    """The measured symptom: biomass 0.01 -> 5.01 -> 2510.01 with the tracked substrate at 0.0.

    Growth came entirely off a sink the closure loop could not see, so the run reported a
    controlled substrate/Km experiment that never was.
    """
    from cmig.core.dfba import simulate_dfba

    model = _sink_fed_model()
    result = simulate_dfba(model, _dfba_config(close_untracked_uptake=True), solver="gurobi")

    # Nothing can feed the model except the tracked exchange, which is empty, so there is no growth.
    assert result.status == "stalled"
    assert result.timecourse[-1].biomass == pytest.approx(0.01)
    assert result.untracked_uptake == {}


def test_dfba_reports_a_supplying_sink_when_it_does_not_close_it():
    """Round-2's D5 guarantee: a run fed by a sink must not come back with ``warnings: []``."""
    from cmig.core.dfba import simulate_dfba

    model = _sink_fed_model()
    result = simulate_dfba(model, _dfba_config(close_untracked_uptake=False), solver="gurobi")

    assert result.timecourse[-1].biomass > 1.0        # it grew, on nothing it tracks
    assert "SK_atp_c" in result.untracked_uptake
    assert result.untracked_uptake["SK_atp_c"] == pytest.approx(1000.0)
    assert result.warnings, "a run fed by an untracked sink reported no warnings"
    assert any("UNCONSTRAINED" in warning for warning in result.warnings)


def test_dfba_closure_satisfies_the_boundary_invariant():
    """Same assertion as every other isolation site, reached through ``simulate_dfba``."""
    from cmig.core.dfba import simulate_dfba

    model = _sink_fed_model()
    observed: dict[str, dict[str, float]] = {}
    real_optimize = model.optimize

    def spy(*args: object, **kwargs: object) -> object:
        observed.setdefault(
            "violations", boundary_isolation_violations(model, {"EX_glc__D_e": 10.0})
        )
        return real_optimize(*args, **kwargs)

    model.optimize = spy                                     # type: ignore[method-assign]
    try:
        simulate_dfba(model, _dfba_config(close_untracked_uptake=True), solver="gurobi")
    finally:
        del model.optimize                                   # type: ignore[attr-defined]

    assert observed["violations"] == {}


def test_dfba_close_untracked_uptake_refuses_a_model_exposing_only_exchanges(monkeypatch):
    """A model that can list exchanges but not ``boundary`` must be refused, not half-closed.

    The pre-fix guard probed ``.exchanges``, so this stub would have passed it and produced a run
    labelled "controlled" whose background was never enumerated at all.
    """
    from cmig.core import single_model
    from cmig.core.dfba import simulate_dfba

    monkeypatch.setattr(single_model, "_require_lp", lambda solver: None)
    monkeypatch.setattr(single_model, "set_model_solver", lambda model, solver: None)

    class _ExchangesOnlyModel:
        exchanges = ()          # enumerable, and a strict subset of what can supply mass

        class _Reactions:
            @staticmethod
            def get_by_id(rid: str) -> object:
                class _R:
                    lower_bound = -10.0
                return _R()

        reactions = _Reactions()

        def __enter__(self) -> object:
            return self

        def __exit__(self, *exc: object) -> bool:
            return False

    with pytest.raises(ValueError, match="untracked uptake cannot be closed"):
        simulate_dfba(
            _ExchangesOnlyModel(), _dfba_config(close_untracked_uptake=True), solver="gurobi"
        )


# ── instance 5: minimal medium ─────────────────────────────────────────────────────────────────


def test_minimal_medium_does_not_return_a_zero_component_medium():
    """It returned a **zero-component** minimal medium that passed its own re-solve validation.

    Because the re-solve went through ``model.medium``, which cannot close the sink, an empty
    medium "achieved" growth 1000 and was published as a cardinality-minimal nutrient set.
    """
    from cmig.core.medium import MILPInfeasibleError, minimal_medium_cardinality

    model = _sink_fed_model()
    with pytest.raises(MILPInfeasibleError):
        minimal_medium_cardinality(model, 1.0, solver="gurobi")


def test_minimal_medium_isolates_the_boundary_before_the_milp():
    """Positive control: with a real route from an exchange, the medium is found AND isolated."""
    from cobra import Metabolite, Reaction

    from cmig.core.medium import minimal_medium_cardinality

    model = _sink_fed_model()
    glc_c = Metabolite("glc__D_c", compartment="c")
    model.add_metabolites([glc_c])
    transport = Reaction("GLCt", lower_bound=0.0, upper_bound=1000.0)
    transport.add_metabolites({model.metabolites.get_by_id("glc__D_e"): -1.0, glc_c: 1.0})
    generate = Reaction("ATPS_test", lower_bound=0.0, upper_bound=1000.0)
    generate.add_metabolites({glc_c: -1.0, model.metabolites.get_by_id("atp_c"): 1.0})
    model.add_reactions([transport, generate])

    result = minimal_medium_cardinality(model, 1.0, solver="gurobi")

    assert result.components == ["EX_glc__D_e"]
    assert result.n_components == 1
    assert result.achieved_growth >= 1.0
    # The model is left as the context found it; the isolation was internal to the computation.
    assert "SK_atp_c" in mass_supplying_boundary(model)
