"""Shared constraints and measured membership for every consortium search solve."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

SEARCH_POLICY_VERSION = "consortium_search_v2"


@dataclass(frozen=True)
class GrowthPolicy:
    min_member_growth: float = 0.0
    min_community_growth: float = 0.0

    def validate(self) -> None:
        for name in ("min_member_growth", "min_community_growth"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")


def validate_taxonomy(taxonomy: Any) -> None:
    """Reject ambiguous IDs and invalid abundances before spending a solve budget."""
    ids = [str(value) for value in taxonomy["id"]]
    if not ids or any(not value.strip() or value.lower() == "nan" for value in ids):
        raise ValueError("taxonomy requires non-empty member IDs")
    if len(set(ids)) != len(ids):
        raise ValueError("taxonomy id values must be unique")
    if "abundance" in getattr(taxonomy, "columns", ()):
        for member, value in zip(ids, taxonomy["abundance"], strict=True):
            try:
                valid = math.isfinite(float(value)) and float(value) > 0
            except (ValueError, TypeError):
                valid = False
            if not valid:
                raise ValueError(f"abundance for {member!r} must be finite and > 0")


def actual_members(community: Any, requested: tuple[str, ...]) -> tuple[str, ...]:
    """Check MICOM's effective membership, including relative-abundance filtering."""
    taxa = getattr(community, "taxa", None)
    # Plain COBRA models used by target-LP clients do not have a taxonomy.
    effective = tuple(sorted(str(value) for value in taxa)) if taxa is not None else requested
    if effective != tuple(sorted(requested)):
        raise ValueError(
            f"membership mismatch: requested={list(requested)}, effective={list(effective)}; "
            "MICOM may have filtered small relative abundances; revise the taxonomy"
        )
    return effective


def apply_member_growth(model: Any, policy: GrowthPolicy) -> None:
    policy.validate()
    if policy.min_member_growth == 0:
        return
    taxa = getattr(model, "taxa", None)
    if taxa is None:
        raise ValueError("min_member_growth requires a MICOM community with member objectives")
    for member in taxa:
        constraint = model.constraints.get(f"objective_{member}")
        if constraint is None:
            raise ValueError(f"member growth constraint is missing for {member}")
        from functools import partial

        from cobra.util.context import get_context

        context = get_context(model)
        if context is not None:
            context(partial(setattr, constraint, "lb", constraint.lb))
        constraint.lb = max(float(constraint.lb or 0.0), policy.min_member_growth)


def member_measurements(model: Any) -> tuple[dict[str, float], dict[str, float]]:
    """Read the same optimum as the target flux; never re-solve for member growth."""
    growth: dict[str, float] = {}
    abundance: dict[str, float] = {}
    for member in getattr(model, "taxa", ()):
        constraint = model.constraints.get(f"objective_{member}")
        if constraint is not None and constraint.primal is not None:
            value = float(constraint.primal)
            if not math.isfinite(value):
                raise ValueError(f"non-finite growth for member {member}")
            growth[str(member)] = value
    for member, value in getattr(model, "abundances", {}).items():
        abundance[str(member)] = float(value)
    return growth, abundance
