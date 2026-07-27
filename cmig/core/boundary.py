"""Boundary isolation — the one place CMIG decides what may supply mass to a model.

Round 6, track B. This module exists because the same defect was found independently in three
review rounds and had reached five call sites: **CMIG closed what it enumerated, and every
enumeration it used is a strict subset of what can supply mass.**

``cobra`` offers three views of a model's edge and only one of them is complete:

===================  ==============================================================
``model.medium``     the boundary reactions that are *currently open*, exchanges only
``model.exchanges``  ``find_boundary_types(model, "exchange")`` — excludes sinks/demands
``model.boundary``   every reaction with a single side — ``exchanges ∪ sinks ∪ demands``
===================  ==============================================================

Measured on Recon3D (`data/gems/Recon3D.xml`, cobra 0.31.1)::

    boundary 1806 = exchanges 1560 + sinks 101 + demands 145
    boundary able to supply mass: 1655, of which 95 are NOT in model.exchanges
    those 95 sit at lower_bound = -1000

So a loop over ``model.exchanges`` leaves 95 unbounded intracellular mass sources open, and
``model.medium = {...}`` cannot close them either: cobra's own setter does
``exchange_rxns = frozenset(self.exchanges)`` and only turns those off. That is why wrapping the
setter is not optional — ``model.medium = …`` can never produce a closed background.

The invariant this module makes checkable, in one sentence:

    **After isolation, no boundary reaction may supply mass except the explicitly declared
    ones, at their declared bounds.**

:func:`boundary_isolation_violations` is that sentence as code, and it is what the generic
invariant test asserts across Recon3D, RECON1 and the bundled microbial models.

Why a module of its own rather than a helper inside ``medium_spec`` or ``host_coupling``: the five
call sites live in five different concerns (medium application, host coupling, dFBA, minimal
medium, and the CLI). Putting the primitive in any one of them would make the other four import an
unrelated module — which is how the previous partial fixes drifted apart in the first place. A
leaf module with no CMIG imports can be used by all of them and by the tests without a cycle.

Sign convention (identical to cobra's ``Model.medium``, deliberately, so that routing a medium
through this module cannot change a number on a model with no sinks or demands):

* a boundary reaction written ``met -->`` (the metabolite is a *reactant*) supplies mass at
  **negative** flux, so its supply capacity is ``max(0, -lower_bound)``;
* a boundary reaction written ``--> met`` (the metabolite is a *product*) supplies mass at
  **positive** flux, so its supply capacity is ``max(0, upper_bound)``.

Forced supply is a real case and is never papered over. ``iAF987`` ships
``EX_ac_e [-8.88, -6.84]`` and ``EX_fe3_e [-67.37, -49.21]``: the bounds *require* uptake, so
closure is arithmetically impossible without changing the model's feasible set. Those reactions
are reported in :attr:`BoundaryIsolation.forced_supply` and, with ``strict=True``, refused —
never silently mangled and never silently left open.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

#: Non-hashed provenance marker. Bump when the isolation *semantics* change, so a consumer can
#: tell pre-fix numbers from post-fix ones mechanically. Follows round 5's `medium_policy`
#: precedent: the discontinuity cannot be recorded in a hash component (`cmig_core_version` is
#: frozen), and the fix moves published answers, so the marker is the only mechanical signal.
#: `exchange_view_v0` is the era in which closure enumerated `model.exchanges` / `model.medium`.
BOUNDARY_ISOLATION_POLICY = "boundary_reactions_v1"   # was: exchange_view_v0

#: Flux magnitudes below this are treated as no supply. Matches the 1e-9 used by the dFBA and
#: host uptake readers, so "can supply" and "did supply" use one threshold.
SUPPLY_TOLERANCE = 1e-9


class BoundaryIsolationError(ValueError):
    """Isolation was requested but cannot be delivered as described.

    Raised rather than returning a partially isolated model, because a run whose background is
    only *mostly* closed publishes a number that looks controlled and is not — the failure mode
    this whole module exists to remove.
    """


@dataclass(frozen=True)
class BoundarySupply:
    """One boundary reaction's ability to add its metabolite to the model."""

    reaction_id: str
    capacity: float          # max supply rate permitted by the bounds (>= 0)
    forced: float            # min supply rate REQUIRED by the bounds (>= 0); >0 ⇒ cannot close
    # False ⇒ a sink or a demand, i.e. invisible to every pre-round-6 closure loop.
    is_exchange: bool


@dataclass(frozen=True)
class BoundaryIsolation:
    """What an isolation actually did. Every field is a measurement, not an intention."""

    policy: str
    n_boundary: int
    closed: tuple[str, ...] = ()             # reactions whose supply was turned off
    opened: dict[str, float] = field(default_factory=dict)   # reaction id -> declared supply limit
    forced_supply: dict[str, float] = field(default_factory=dict)  # id -> irreducible supply rate
    non_exchange_closed: tuple[str, ...] = ()   # the subset invisible to model.exchanges
    unmatched: tuple[str, ...] = ()          # declared ids the model does not have

    @property
    def n_closed(self) -> int:
        return len(self.closed)

    @property
    def complete(self) -> bool:
        """True iff nothing outside ``opened`` can still supply mass."""
        return not self.forced_supply

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready record for a manifest provenance block."""
        return {
            "policy": self.policy,
            "n_boundary": self.n_boundary,
            "n_closed": self.n_closed,
            "n_closed_non_exchange": len(self.non_exchange_closed),
            "n_opened": len(self.opened),
            "forced_supply": {k: float(v) for k, v in sorted(self.forced_supply.items())},
            "complete": self.complete,
        }


# ── enumeration ───────────────────────────────────────────────────────────────────────────────


def boundary_reactions(model: Any) -> list[Any]:
    """Every boundary reaction, id-sorted. ``exchanges ∪ sinks ∪ demands``.

    ``model.boundary`` is the complete view. Anything narrower is a convenience view and using one
    to decide "what can feed this model" is the defect this module replaces.
    """
    try:
        reactions = list(model.boundary)
    except (AttributeError, TypeError) as error:
        raise BoundaryIsolationError(
            "model does not expose .boundary, so the set of reactions that can supply mass "
            "cannot be enumerated; isolation would be a claim rather than a fact"
        ) from error
    return sorted(reactions, key=lambda reaction: str(reaction.id))


def exposes_boundary(model: Any) -> bool:
    """True iff ``model.boundary`` can be enumerated (cobra models can)."""
    try:
        iter(model.boundary)
    except (AttributeError, TypeError):
        return False
    return True


def _supplies_at_negative_flux(reaction: Any) -> bool:
    """``met -->`` (metabolite consumed at positive flux) ⇒ supply happens at negative flux.

    Mirrors cobra's ``Model.medium``, which branches on ``reaction.reactants`` first.
    """
    return bool(getattr(reaction, "reactants", None))


def supply_capacity(reaction: Any) -> float:
    """Maximum rate at which this boundary reaction may ADD its metabolite to the model."""
    if _supplies_at_negative_flux(reaction):
        return max(0.0, -float(reaction.lower_bound))
    if getattr(reaction, "products", None):
        return max(0.0, float(reaction.upper_bound))
    return 0.0


def forced_supply(reaction: Any) -> float:
    """Minimum supply rate the bounds REQUIRE. ``> 0`` means the reaction cannot be closed.

    ``iAF987``'s ``EX_ac_e [-8.88, -6.84]`` forces 6.84 mmol gDW⁻¹ h⁻¹ of acetate uptake — i.e.
    acetate supply into the model — because every feasible flux is negative.
    """
    if _supplies_at_negative_flux(reaction):
        return max(0.0, -float(reaction.upper_bound))
    if getattr(reaction, "products", None):
        return max(0.0, float(reaction.lower_bound))
    return 0.0


def supply_rate(reaction: Any, flux: float) -> float:
    """How much mass a *realised* flux added to the model (0.0 when it removed mass).

    Needed because "uptake" is not simply ``flux < 0``: for a demand written ``--> met`` the
    supplying direction is positive. The dFBA untracked-uptake recorder tested ``flux < -1e-9``
    and therefore could not see a supplying demand at all.
    """
    value = float(flux)
    if _supplies_at_negative_flux(reaction):
        return max(0.0, -value)
    if getattr(reaction, "products", None):
        return max(0.0, value)
    return 0.0


def mass_supplying_boundary(
    model: Any, *, tolerance: float = SUPPLY_TOLERANCE
) -> dict[str, BoundarySupply]:
    """Every boundary reaction that can currently supply mass, id-keyed.

    This is the honest answer to "what can feed this model", and it is a strict superset of
    ``model.medium`` on any model with an open sink.
    """
    exchange_ids = {str(reaction.id) for reaction in getattr(model, "exchanges", []) or []}
    supplies: dict[str, BoundarySupply] = {}
    for reaction in boundary_reactions(model):
        capacity = supply_capacity(reaction)
        if capacity <= tolerance:
            continue
        rid = str(reaction.id)
        supplies[rid] = BoundarySupply(
            reaction_id=rid,
            capacity=capacity,
            forced=forced_supply(reaction),
            is_exchange=rid in exchange_ids,
        )
    return supplies


# ── mutation ──────────────────────────────────────────────────────────────────────────────────


def _close_supply(reaction: Any) -> bool:
    """Turn off this reaction's ability to supply mass. False iff the bounds forbid it."""
    if _supplies_at_negative_flux(reaction):
        if float(reaction.upper_bound) < 0.0:
            return False                     # forced uptake — closing would invert the bounds
        reaction.lower_bound = 0.0
        return True
    if getattr(reaction, "products", None):
        if float(reaction.lower_bound) > 0.0:
            return False                     # forced production
        reaction.upper_bound = 0.0
        return True
    return True


def set_supply_limit(reaction: Any, limit: float) -> None:
    """Allow this boundary reaction to supply at most ``limit`` (>= 0).

    Byte-for-byte the same arithmetic as cobra's ``set_active_bound``, so routing an
    exchange-only model through this module cannot move a number.
    """
    value = float(limit)
    if value < 0.0:
        raise BoundaryIsolationError(
            f"supply limit must be >= 0 (magnitude, mmol gDW^-1 h^-1); got {reaction.id}={value}"
        )
    if _supplies_at_negative_flux(reaction):
        reaction.lower_bound = -value
    elif getattr(reaction, "products", None):
        reaction.upper_bound = value
    else:
        # A reaction with no metabolites has no supplying direction, so "give it a supply limit"
        # is not a request that can be honoured. Doing nothing would leave a caller believing a
        # medium had been applied when no bound moved — the silent-no-op form of this round's
        # defect. It fails loudly instead.
        raise BoundaryIsolationError(
            f"{getattr(reaction, 'id', '?')} has no metabolites, so it has no supplying "
            "direction and cannot carry a medium uptake limit"
        )


def close_boundary_supply(
    model: Any,
    *,
    keep: Iterable[str] = (),
    only: Iterable[str] | None = None,
    tolerance: float = SUPPLY_TOLERANCE,
) -> BoundaryIsolation:
    """Close every boundary reaction that can supply mass, except the ids in ``keep``.

    Sinks and demands keep their ability to *remove* mass — only the supplying direction is
    closed — so a model does not become infeasible merely because its demands were shut.

    ``only`` restricts the operation to a named subset of the boundary. It exists for CMIG's
    2-interface host contract, where the lumen is closed by default and the blood interface is
    legitimately left open — the subset is still taken from ``model.boundary``, so a sink or demand
    on the restricted interface is included where a loop over ``model.exchanges`` would miss it.
    """
    kept = {str(item) for item in keep}
    reactions = boundary_reactions(model)
    n_boundary = len(reactions)          # the whole boundary, even when `only` narrows the action
    if only is not None:
        selected = {str(item) for item in only}
        reactions = [
            reaction for reaction in reactions if str(reaction.id) in selected
        ]
    exchange_ids = {str(reaction.id) for reaction in getattr(model, "exchanges", []) or []}
    closed: list[str] = []
    non_exchange_closed: list[str] = []
    forced: dict[str, float] = {}
    for reaction in reactions:
        rid = str(reaction.id)
        if rid in kept:
            continue
        if supply_capacity(reaction) <= tolerance:
            continue
        if _close_supply(reaction):
            closed.append(rid)
            if rid not in exchange_ids:
                non_exchange_closed.append(rid)
        else:
            forced[rid] = forced_supply(reaction)
    return BoundaryIsolation(
        policy=BOUNDARY_ISOLATION_POLICY,
        n_boundary=n_boundary,
        closed=tuple(closed),
        forced_supply=forced,
        non_exchange_closed=tuple(non_exchange_closed),
    )


def open_boundary_supply(
    model: Any, availability: Mapping[str, float], *, strict: bool = True
) -> tuple[dict[str, float], tuple[str, ...]]:
    """Open the declared boundary reactions at the declared limits. Closes nothing.

    Returns ``(opened, unmatched)``. ``strict=True`` refuses ids the model does not have, because
    silently dropping one produces a medium that is not the medium the manifest fingerprinted.
    """
    opened: dict[str, float] = {}
    unmatched: list[str] = []
    for raw_id, limit in sorted(availability.items()):
        rid = str(raw_id)
        try:
            reaction = model.reactions.get_by_id(rid)
        except KeyError:
            unmatched.append(rid)
            continue
        set_supply_limit(reaction, float(limit))
        opened[rid] = float(limit)
    if strict and unmatched:
        raise BoundaryIsolationError(
            f"declared boundary reaction not present in the model: {sorted(unmatched)}"
        )
    return opened, tuple(sorted(unmatched))


def isolate_boundary(
    model: Any,
    availability: Mapping[str, float],
    *,
    strict: bool = False,
    strict_unmatched: bool = True,
    tolerance: float = SUPPLY_TOLERANCE,
) -> BoundaryIsolation:
    """Make ``availability`` the **whole** set of mass sources this model has.

    Close every boundary reaction that can supply mass, then open exactly the declared ones at
    their declared limits. This is the operation ``model.medium = {...}`` claims to perform and
    does not: cobra's setter closes ``frozenset(self.exchanges)`` and leaves sinks and demands
    untouched.

    ``strict=True`` raises when the model's own bounds force a supply that cannot be closed, so a
    caller that needs a provably closed background gets an error instead of a plausible number.
    """
    closure = close_boundary_supply(model, keep=[str(k) for k in availability], tolerance=tolerance)
    if strict and closure.forced_supply:
        raise BoundaryIsolationError(
            "cannot isolate the boundary: these reactions' bounds FORCE mass supply, so the "
            "background cannot be closed without changing the model — "
            f"{ {k: round(v, 6) for k, v in sorted(closure.forced_supply.items())} }. "
            "Relax the bounds in the SBML, declare them as availability, or accept a background "
            "that is not closed (and say so in the result)."
        )
    opened, unmatched = open_boundary_supply(model, availability, strict=strict_unmatched)
    return BoundaryIsolation(
        policy=closure.policy,
        n_boundary=closure.n_boundary,
        closed=closure.closed,
        opened=opened,
        forced_supply=closure.forced_supply,
        non_exchange_closed=closure.non_exchange_closed,
        unmatched=unmatched,
    )


# ── the invariant, as code ────────────────────────────────────────────────────────────────────


def boundary_isolation_violations(
    model: Any,
    declared: Mapping[str, float],
    *,
    tolerance: float = SUPPLY_TOLERANCE,
) -> dict[str, float]:
    """Boundary reactions that can supply mass illegally. Empty dict ⇒ the invariant holds.

    A reaction is illegal when it can supply mass and either
    (a) it is not declared, or
    (b) it is declared but can supply MORE than its declared limit.

    The returned value is the excess supply capacity, so the caller can report a magnitude and
    not merely a name. This is the single assertion the generic invariant test makes; every
    per-site test is a way of *reaching* it, not a re-statement of it.
    """
    limits = {str(key): float(value) for key, value in declared.items()}
    violations: dict[str, float] = {}
    for reaction in boundary_reactions(model):
        rid = str(reaction.id)
        capacity = supply_capacity(reaction)
        allowed = limits.get(rid, 0.0)
        excess = capacity - allowed
        if excess > tolerance:
            violations[rid] = excess
    return violations


def realised_boundary_suppliers(
    model: Any,
    fluxes: Mapping[str, float],
    *,
    tolerance: float = SUPPLY_TOLERANCE,
) -> dict[str, float]:
    """Which boundary reactions actually supplied mass in a solution, and at what rate.

    Reads ``model.boundary``, so a supplying sink or demand is visible. The round-6 verification
    that found instances 3–5 built exactly this probe by hand around ``model.optimize``; having
    it in production means a test can assert on the real solve instead of re-implementing it.
    """
    supplied: dict[str, float] = {}
    for reaction in boundary_reactions(model):
        rid = str(reaction.id)
        if rid not in fluxes:
            continue
        rate = supply_rate(reaction, float(fluxes[rid]))
        if rate > tolerance:
            supplied[rid] = rate
    return supplied
