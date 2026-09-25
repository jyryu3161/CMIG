"""P1-E — microbial perturbation → host effect, as one composed workflow.

This is the capability every independent evaluation asked for: "inhibit / knock out microbe or
gene X" → "the host objective changes by Y". Round-2 evaluators could only get it by hand-editing
an SBML, writing it to scratch, and re-running `host-microbe-bigg` against it — an unsupported
bridge with nothing enforcing that the two runs shared a medium, an interface map, a biomass basis
or a host objective. Any of those drifting silently turns the delta into an artifact.

The contract here is therefore *comparability first*:

- baseline and every perturbed run go through the same :func:`run_bigg_host_microbe` call with the
  identical medium, interface map, biomass basis, host objective, solver and tradeoff;
- only the named member's model is replaced, and only by a knockout of the named gene/reaction;
- abundances are carried over from the baseline taxonomy unchanged;
- a delta is emitted **only when both host solves are optimal**. An infeasible perturbed host is
  reported as `host_status="infeasible"` with a null delta, never as `delta = -baseline`, because
  "the host died" and "the host objective fell to zero" are different findings;
- the biomass-basis guardrails ride along, so a `validation` basis still marks the whole comparison
  non-publication.

Pure orchestration + pure delta arithmetic; the solver work is delegated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cmig.core.host_impact import _lookup_by_metabolite, identified_transfer_point

# A knockout that removes the host's only carbon source makes the host infeasible. That is a
# result, not a failure of the comparison — but it is not a number either.
NON_COMPARABLE = "host solve was not optimal in this arm; no delta is defined"


@dataclass(frozen=True)
class HostArm:
    """One host-coupling arm (baseline or a single knockout)."""

    label: str  # "baseline" or "<member>:<ko_id>"
    member: str | None  # perturbed member (None for baseline)
    ko_id: str | None  # gene/reaction id (None for baseline)
    ko_level: str | None  # "gene" | "reaction" | None
    run_status: str  # ok | degraded | failed
    community_status: str
    community_growth: float
    host_status: str
    host_viable: bool
    host_objective: float
    target_transfer: float | None
    microbe_to_host: dict[str, float] = field(default_factory=dict)
    matched_exchanges: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostic: str | None = None
    target_transfer_range: tuple[float, float] | None = None
    target_identifiability: str = "unavailable"
    target_reason: str | None = None
    microbe_to_host_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    metabolite_identifiability: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A legacy direct caller that supplies a finite point makes an explicit
        # assertion. The coupling adapter supplies None whenever FVA cannot
        # identify a point, so this compatibility path cannot invent one there.
        if (
            self.target_transfer is not None
            and math.isfinite(self.target_transfer)
            and self.target_transfer_range is None
            and self.target_identifiability == "unavailable"
            and self.target_reason is None
        ):
            object.__setattr__(
                self, "target_transfer_range", (self.target_transfer, self.target_transfer)
            )
            object.__setattr__(self, "target_identifiability", "identified")

    @property
    def is_comparable(self) -> bool:
        """Can this arm take part in a delta at all?"""
        return (
            self.host_status == "optimal"
            and self.community_status == "optimal"
            and math.isfinite(self.host_objective)
        )


@dataclass(frozen=True)
class HostKoDelta:
    """baseline → knockout change in the host readouts."""

    label: str
    member: str | None
    ko_id: str | None
    comparable: bool
    delta_host_objective: float | None
    delta_target_transfer: float | None
    delta_microbe_to_host: dict[str, float]
    relative_host_objective: float | None  # Δ / baseline, when the baseline is non-zero
    host_status: str
    community_status: str
    diagnostic: str | None = None
    target_comparable: bool = False
    delta_target_transfer_range: tuple[float, float] | None = None
    delta_microbe_to_host_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    metabolite_identifiability: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HostKoImpactResult:
    """Full baseline + knockout comparison set."""

    target: str
    baseline: HostArm
    arms: list[HostArm]
    deltas: list[HostKoDelta]
    warnings: list[str]
    status: str
    biomass_basis: dict[str, Any] = field(default_factory=dict)
    comparability: dict[str, Any] = field(default_factory=dict)


def _delta_or_none(
    baseline: float | None, perturbed: float | None, comparable: bool
) -> float | None:
    """A delta only exists when both arms are real numbers from optimal solves."""
    if baseline is None or perturbed is None or not comparable:
        return None
    if not (math.isfinite(baseline) and math.isfinite(perturbed)):
        return None
    return perturbed - baseline


def _identified_metabolite_point_from_readout(
    points: dict[str, float], ranges: dict[str, tuple[float, float]], metabolite: str
) -> float | None:
    """Read a point from a measured collapsed range or an explicit finite point.

    The coupling point map is sparse (positive transfers only), so absence from it
    cannot mean zero. A finite collapsed FVA range can establish zero directly.
    """
    return identified_transfer_point(points, ranges, metabolite)


def _identified_metabolite_point(arm: HostArm, metabolite: str) -> float | None:
    return _identified_metabolite_point_from_readout(
        arm.microbe_to_host, arm.microbe_to_host_ranges, metabolite
    )


def compute_host_ko_delta(baseline: HostArm, arm: HostArm) -> HostKoDelta:
    """Pure delta arithmetic for one knockout arm. Testable without a solver.

    An arm that did not solve gets ``comparable=False`` and null deltas — encoding an infeasible
    host objective as 0 would report a killed host as "no change" or as a clean negative effect.
    """
    comparable = baseline.is_comparable and arm.is_comparable
    delta_objective = _delta_or_none(baseline.host_objective, arm.host_objective, comparable)
    delta_transfer = _delta_or_none(baseline.target_transfer, arm.target_transfer, comparable)
    metabolite_delta: dict[str, float] = {}
    metabolite_ranges: dict[str, tuple[float, float]] = {}
    identifiability: dict[str, str] = {}
    if comparable:
        metabolites = (
            set(baseline.microbe_to_host)
            | set(arm.microbe_to_host)
            | set(baseline.microbe_to_host_ranges)
            | set(arm.microbe_to_host_ranges)
        )
        for metabolite in sorted(metabolites):
            before = _identified_metabolite_point(baseline, metabolite)
            after = _identified_metabolite_point(arm, metabolite)
            low = _lookup_by_metabolite(baseline.microbe_to_host_ranges, metabolite)
            high = _lookup_by_metabolite(arm.microbe_to_host_ranges, metabolite)
            if low is not None and high is not None:
                metabolite_ranges[metabolite] = (high[0] - low[1], high[1] - low[0])
            state = (
                "identified"
                if before is not None and after is not None
                else ("ambiguous" if low is not None or high is not None else "unavailable")
            )
            identifiability[metabolite] = state
            if state == "identified" and before is not None and after is not None:
                if abs(after - before) > 1e-9:
                    metabolite_delta[metabolite] = after - before
    target_comparable = comparable and delta_transfer is not None
    target_range = None
    if comparable and baseline.target_transfer_range and arm.target_transfer_range:
        target_range = (
            arm.target_transfer_range[0] - baseline.target_transfer_range[1],
            arm.target_transfer_range[1] - baseline.target_transfer_range[0],
        )
    relative = None
    if delta_objective is not None and abs(baseline.host_objective) > 1e-12:
        relative = delta_objective / baseline.host_objective
    diagnostic = arm.diagnostic
    if not comparable and diagnostic is None:
        diagnostic = NON_COMPARABLE
    return HostKoDelta(
        label=arm.label,
        member=arm.member,
        ko_id=arm.ko_id,
        comparable=comparable,
        delta_host_objective=delta_objective,
        delta_target_transfer=delta_transfer,
        delta_microbe_to_host=metabolite_delta,
        relative_host_objective=relative,
        host_status=arm.host_status,
        community_status=arm.community_status,
        diagnostic=diagnostic,
        target_comparable=target_comparable,
        delta_target_transfer_range=target_range,
        delta_microbe_to_host_ranges=metabolite_ranges,
        metabolite_identifiability=identifiability,
    )


def arm_from_coupling(
    result: Any,
    *,
    label: str,
    target: str,
    member: str | None = None,
    ko_id: str | None = None,
    ko_level: str | None = None,
) -> HostArm:
    """BiggHostMicrobeResult → HostArm (readout extraction only, no solving)."""
    host = result.host_result
    impact = result.impact
    transfer_range = _lookup_by_metabolite(impact.microbe_to_host_ranges, target)
    point = _lookup_by_metabolite(impact.microbe_to_host, target)
    # A sparse positive-only point map does not establish a zero. A solved absence of microbial
    # secretion is structural evidence; an unmatched secreted target is not.
    secreted = _lookup_by_metabolite(getattr(result, "microbial_secretion", {}), target)
    unmatched = any(
        _lookup_by_metabolite({name: True}, target) is not None
        for name in getattr(result, "unmatched_metabolites", [])
    )
    host_status = str(host.status)
    community_status = str(result.community_status)
    solved = (host_status == "optimal" and community_status == "optimal"
              and math.isfinite(float(host.biomass)))
    if solved and transfer_range is not None:
        identified = identified_transfer_point(
            impact.microbe_to_host, impact.microbe_to_host_ranges, target
        )
        if identified is not None:
            point = identified
            target_state, reason = "identified", None
        elif (
            len(transfer_range) == 2
            and all(math.isfinite(x) for x in transfer_range)
            and transfer_range[0] <= transfer_range[1]
        ):
            point = None
            target_state, reason = (
                "ambiguous",
                "optimal host transfer has alternate feasible values",
            )
        else:
            point, transfer_range = None, None
            target_state, reason = "unavailable", "invalid transfer range"
    elif solved and point is not None and math.isfinite(point):
        transfer_range = (point, point)
        target_state, reason = "identified", None
    elif solved and not unmatched and (secreted is None or secreted <= 1e-6):
        point, transfer_range = 0.0, (0.0, 0.0)
        target_state, reason = "identified", "no microbial availability for requested target"
    else:
        point, transfer_range = None, None
        target_state = "unavailable"
        reason = "unmatched target" if unmatched else "transfer readout unavailable"
    if solved:
        run_status = (
            "ok" if result.matched_exchanges and target_state == "identified" else "degraded"
        )
    else:
        run_status = "failed"
    metabolite_ranges = dict(impact.microbe_to_host_ranges)
    if solved and target_state == "identified" and transfer_range is not None:
        # Keep a proven structural zero in the per-metabolite readout as well.
        if _lookup_by_metabolite(metabolite_ranges, target) is None:
            metabolite_ranges[target] = transfer_range
    return HostArm(
        label=label,
        member=member,
        ko_id=ko_id,
        ko_level=ko_level,
        run_status=run_status,
        community_status=community_status,
        community_growth=float(result.community_growth),
        host_status=host_status,
        host_viable=bool(host.viable),
        host_objective=float(host.biomass),
        target_transfer=point,
        microbe_to_host=dict(impact.microbe_to_host),
        matched_exchanges=dict(result.matched_exchanges),
        warnings=list(result.warnings),
        diagnostic=host.diagnostic,
        target_transfer_range=transfer_range,
        target_identifiability=target_state,
        target_reason=reason,
        microbe_to_host_ranges=metabolite_ranges,
        metabolite_identifiability={
            met: (
                "identified" if solved and _identified_metabolite_point_from_readout(
                    impact.microbe_to_host, metabolite_ranges, met
                ) is not None else "ambiguous" if solved else "unavailable"
            )
            for met in metabolite_ranges
        },
    )


def assemble_result(
    *,
    target: str,
    baseline: HostArm,
    arms: list[HostArm],
    biomass_basis: dict[str, Any],
    comparability: dict[str, Any],
    extra_warnings: list[str] | None = None,
    degraded_reasons: list[str] | None = None,
) -> HostKoImpactResult:
    """Combine arms into a result with derived status and honesty warnings.

    ``degraded_reasons`` are setup facts that make the comparison less than what was asked for
    without invalidating it — round 7's case is a medium applied minus the rows the community
    could not honour. They are both warnings *and* status: a caller that could add the warning
    but not the tier would leave `inspect-run` reporting `ok` for a run standing on a different
    medium from the one its manifest names.
    """
    deltas = [compute_host_ko_delta(baseline, arm) for arm in arms]
    warnings: list[str] = list(extra_warnings or []) + list(degraded_reasons or [])

    if not baseline.is_comparable:
        warnings.append(
            "the baseline host solve was not optimal "
            f"(community={baseline.community_status}, host={baseline.host_status}); no knockout "
            "delta is defined against it"
        )
    if not baseline.matched_exchanges:
        warnings.append(
            "no microbial metabolite reached the host in the baseline arm "
            "(matched_exchanges is empty), so the host objective reflects only its own medium and "
            "a knockout cannot change it through coupling"
        )
    non_comparable = [d.label for d in deltas if not d.comparable]
    if non_comparable:
        warnings.append(
            f"{len(non_comparable)} of {len(deltas)} knockout arms did not yield a comparable "
            f"host solve and carry a null delta rather than a numeric one: {non_comparable}"
        )
    unidentifiable = [
        arm.label
        for arm in [baseline, *arms]
        if arm.is_comparable and arm.target_identifiability != "identified"
    ]
    if unidentifiable:
        warnings.append(
            "target transfer is not point identifiable in these optimal arms; objective deltas "
            f"remain comparable and target point deltas are null: {unidentifiable}"
        )
    null_effect = [
        d.label
        for d in deltas
        if d.comparable
        and d.delta_host_objective is not None
        and abs(d.delta_host_objective) <= 1e-9
    ]
    if null_effect and len(null_effect) == len([d for d in deltas if d.comparable]):
        warnings.append(
            "every comparable knockout left the host objective unchanged; there is no ranked hit "
            "and rank 1 must not be reported as an effect"
        )
    if str(biomass_basis.get("kind")) == "validation":
        warnings.append(
            "biomass basis is validation-only; this comparison is not publication-ready"
        )

    if not baseline.is_comparable:
        status = "failed"
    elif (
        non_comparable
        or not baseline.matched_exchanges
        or degraded_reasons
        or baseline.target_identifiability != "identified"
        or any(arm.target_identifiability != "identified" for arm in arms)
    ):
        status = "degraded"
    else:
        status = "ok"
    return HostKoImpactResult(
        target=target,
        baseline=baseline,
        arms=arms,
        deltas=deltas,
        warnings=warnings,
        status=status,
        biomass_basis=biomass_basis,
        comparability=comparability,
    )
