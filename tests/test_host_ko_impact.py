"""P1-E — microbial knockout → host objective delta, and the comparability rules around it.

Every independent evaluation asked for this capability and every one found it absent: the only way
to get it was to hand-edit an SBML and re-run host coupling, with nothing enforcing that the two
runs shared a medium, interface map, biomass basis or host objective. These tests pin the delta
semantics that make such a comparison defensible:

- a delta exists only when BOTH arms solved optimally;
- an infeasible perturbed host yields a null delta, never ``-baseline`` (a killed host and a host
  objective that fell to zero are different findings);
- run status is derived from the worst arm;
- the validation biomass basis still marks the whole comparison non-publication.

Pure arithmetic — no solver.
"""

from __future__ import annotations

import math

import pytest

from cmig.core.host_ko_impact import (
    NON_COMPARABLE,
    HostArm,
    assemble_result,
    compute_host_ko_delta,
)


def _arm(
    label: str,
    *,
    host_objective: float,
    transfer: float = 0.0,
    host_status: str = "optimal",
    community_status: str = "optimal",
    microbe_to_host: dict[str, float] | None = None,
    matched: dict[str, str] | None = None,
    ko_id: str | None = None,
) -> HostArm:
    return HostArm(
        label=label,
        member="iHN637" if ko_id else None,
        ko_id=ko_id,
        ko_level="reaction" if ko_id else None,
        run_status="ok" if host_status == "optimal" else "failed",
        community_status=community_status,
        community_growth=0.11,
        host_status=host_status,
        host_viable=host_objective > 0,
        host_objective=host_objective,
        target_transfer=transfer,
        microbe_to_host=dict(microbe_to_host or {}),
        matched_exchanges=dict(matched if matched is not None else {"etoh": "EX_etoh_lumen"}),
    )


# ── delta arithmetic ─────────────────────────────────────────────────────────────

def test_delta_is_perturbed_minus_baseline():
    baseline = _arm("baseline", host_objective=30.25, transfer=5.0)
    arm = _arm("iHN637:ETOHt", host_objective=19.0, transfer=1.0, ko_id="ETOHt")
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.comparable is True
    # Evaluator B's manual bridge: 30.25 -> 19.0 is a -11.25 host effect.
    assert delta.delta_host_objective == -11.25
    assert delta.delta_target_transfer == -4.0
    assert delta.relative_host_objective == pytest.approx(-11.25 / 30.25)


def test_infeasible_perturbed_host_gives_a_null_delta_not_minus_baseline():
    """The whole point: a killed host must not be reported as a clean negative effect."""
    baseline = _arm("baseline", host_objective=9.21, transfer=3.40)
    arm = _arm(
        "iHN637:ETOHt", host_objective=0.0, host_status="infeasible", ko_id="ETOHt"
    )
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.comparable is False
    assert delta.delta_host_objective is None       # NOT -9.21
    assert delta.delta_target_transfer is None
    assert delta.delta_microbe_to_host == {}
    assert delta.diagnostic == NON_COMPARABLE


def test_infeasible_baseline_blocks_every_delta():
    baseline = _arm("baseline", host_objective=0.0, host_status="infeasible", matched={})
    arm = _arm("iHN637:ETOHt", host_objective=5.0, ko_id="ETOHt")
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.comparable is False
    assert delta.delta_host_objective is None


def test_non_optimal_community_also_blocks_the_delta():
    baseline = _arm("baseline", host_objective=9.0)
    arm = _arm(
        "iHN637:X", host_objective=8.0, community_status="solver_failed", ko_id="X"
    )
    assert compute_host_ko_delta(baseline, arm).delta_host_objective is None


def test_non_finite_objective_is_never_turned_into_a_number():
    baseline = _arm("baseline", host_objective=9.0)
    arm = _arm("iHN637:X", host_objective=float("nan"), ko_id="X")
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.delta_host_objective is None


def test_metabolite_level_rerouting_is_reported():
    """A knockout that reroutes carbon shows up per metabolite, not only in the objective."""
    baseline = _arm(
        "baseline", host_objective=9.21, transfer=3.40,
        microbe_to_host={"etoh": 3.40},
    )
    arm = _arm(
        "iHN637:ETOHt", host_objective=8.61, transfer=0.0,
        microbe_to_host={"ac": 4.81}, ko_id="ETOHt",
    )
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.delta_microbe_to_host["etoh"] == pytest.approx(-3.40)
    assert delta.delta_microbe_to_host["ac"] == pytest.approx(4.81)


def test_unchanged_metabolites_are_not_listed():
    baseline = _arm("baseline", host_objective=9.0, microbe_to_host={"etoh": 3.0})
    arm = _arm("iHN637:X", host_objective=9.0, microbe_to_host={"etoh": 3.0}, ko_id="X")
    assert compute_host_ko_delta(baseline, arm).delta_microbe_to_host == {}


def test_zero_baseline_objective_yields_no_relative_change():
    baseline = _arm("baseline", host_objective=0.0)
    arm = _arm("iHN637:X", host_objective=1.0, ko_id="X")
    delta = compute_host_ko_delta(baseline, arm)
    assert delta.delta_host_objective == 1.0
    assert delta.relative_host_objective is None      # division by zero is not reported as inf


# ── assembled run status and warnings ────────────────────────────────────────────

def _assemble(baseline: HostArm, arms: list[HostArm], kind: str = "measured"):
    return assemble_result(
        target="etoh",
        baseline=baseline,
        arms=arms,
        biomass_basis={"kind": kind, "source": "s"},
        comparability={"only_perturbed_member_model_differs": True},
    )


def test_all_arms_optimal_is_ok():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [_arm("iHN637:A", host_objective=8.0, ko_id="A")],
    )
    assert result.status == "ok"
    assert len(result.deltas) == 1


def test_one_failed_arm_degrades_the_run():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [
            _arm("iHN637:A", host_objective=8.0, ko_id="A"),
            _arm("iHN637:B", host_objective=0.0, host_status="infeasible", ko_id="B"),
        ],
    )
    assert result.status == "degraded"
    assert any("did not yield a comparable host solve" in w for w in result.warnings)


def test_infeasible_baseline_fails_the_run():
    result = _assemble(
        _arm("baseline", host_objective=0.0, host_status="infeasible", matched={}),
        [_arm("iHN637:A", host_objective=8.0, ko_id="A")],
    )
    assert result.status == "failed"
    assert any("baseline host solve was not optimal" in w for w in result.warnings)


def test_empty_coupling_is_flagged_and_degrades():
    """A host fed only by its own medium cannot respond to a microbial knockout at all."""
    result = _assemble(
        _arm("baseline", host_objective=0.877, matched={}),
        [_arm("iHN637:A", host_objective=0.877, ko_id="A", matched={})],
    )
    assert result.status == "degraded"
    assert any("no microbial metabolite reached the host" in w for w in result.warnings)


def test_all_null_effect_knockouts_are_called_out():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [
            _arm("iHN637:A", host_objective=9.0, ko_id="A"),
            _arm("iHN637:B", host_objective=9.0, ko_id="B"),
        ],
    )
    assert any("left the host objective unchanged" in w for w in result.warnings)
    assert any("must not be reported as an effect" in w for w in result.warnings)


def test_a_real_effect_does_not_trigger_the_null_warning():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [
            _arm("iHN637:A", host_objective=9.0, ko_id="A"),
            _arm("iHN637:B", host_objective=3.0, ko_id="B"),
        ],
    )
    assert not any("left the host objective unchanged" in w for w in result.warnings)


def test_validation_basis_marks_the_comparison_non_publication():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [_arm("iHN637:A", host_objective=8.0, ko_id="A")],
        kind="validation",
    )
    assert any("not publication-ready" in w for w in result.warnings)


def test_measured_basis_carries_no_publication_warning():
    result = _assemble(
        _arm("baseline", host_objective=9.0),
        [_arm("iHN637:A", host_objective=8.0, ko_id="A")],
        kind="measured",
    )
    assert not any("not publication-ready" in w for w in result.warnings)


def test_arm_is_comparable_requires_both_solves_and_a_finite_objective():
    assert _arm("x", host_objective=1.0).is_comparable is True
    assert _arm("x", host_objective=1.0, host_status="infeasible").is_comparable is False
    assert _arm("x", host_objective=1.0, community_status="failed").is_comparable is False
    assert _arm("x", host_objective=math.nan).is_comparable is False
