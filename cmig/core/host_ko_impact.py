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

# A knockout that removes the host's only carbon source makes the host infeasible. That is a
# result, not a failure of the comparison — but it is not a number either.
NON_COMPARABLE = "host solve was not optimal in this arm; no delta is defined"


@dataclass(frozen=True)
class HostArm:
    """One host-coupling arm (baseline or a single knockout)."""

    label: str                                   # "baseline" or "<member>:<ko_id>"
    member: str | None                           # perturbed member (None for baseline)
    ko_id: str | None                            # gene/reaction id (None for baseline)
    ko_level: str | None                         # "gene" | "reaction" | None
    run_status: str                              # ok | degraded | failed
    community_status: str
    community_growth: float
    host_status: str
    host_viable: bool
    host_objective: float
    target_transfer: float
    microbe_to_host: dict[str, float] = field(default_factory=dict)
    matched_exchanges: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    diagnostic: str | None = None

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
    relative_host_objective: float | None        # Δ / baseline, when the baseline is non-zero
    host_status: str
    community_status: str
    diagnostic: str | None = None


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


def _delta_or_none(baseline: float, perturbed: float, comparable: bool) -> float | None:
    """A delta only exists when both arms are real numbers from optimal solves."""
    if not comparable or not (math.isfinite(baseline) and math.isfinite(perturbed)):
        return None
    return perturbed - baseline


def compute_host_ko_delta(baseline: HostArm, arm: HostArm) -> HostKoDelta:
    """Pure delta arithmetic for one knockout arm. Testable without a solver.

    An arm that did not solve gets ``comparable=False`` and null deltas — encoding an infeasible
    host objective as 0 would report a killed host as "no change" or as a clean negative effect.
    """
    comparable = baseline.is_comparable and arm.is_comparable
    delta_objective = _delta_or_none(
        baseline.host_objective, arm.host_objective, comparable
    )
    delta_transfer = _delta_or_none(
        baseline.target_transfer, arm.target_transfer, comparable
    )
    metabolite_delta: dict[str, float] = {}
    if comparable:
        for metabolite in sorted(set(baseline.microbe_to_host) | set(arm.microbe_to_host)):
            before = float(baseline.microbe_to_host.get(metabolite, 0.0))
            after = float(arm.microbe_to_host.get(metabolite, 0.0))
            if abs(after - before) > 1e-9:
                metabolite_delta[metabolite] = after - before
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
    transfer = float(result.impact.microbe_to_host.get(target, 0.0))
    host_status = str(host.status)
    community_status = str(result.community_status)
    if host_status == "optimal" and community_status == "optimal":
        run_status = "ok" if result.matched_exchanges else "degraded"
    else:
        run_status = "failed"
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
        target_transfer=transfer,
        microbe_to_host=dict(result.impact.microbe_to_host),
        matched_exchanges=dict(result.matched_exchanges),
        warnings=list(result.warnings),
        diagnostic=host.diagnostic,
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
    null_effect = [
        d.label for d in deltas
        if d.comparable and d.delta_host_objective is not None
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
    elif non_comparable or not baseline.matched_exchanges or degraded_reasons:
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
