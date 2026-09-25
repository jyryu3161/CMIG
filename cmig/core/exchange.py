"""Physical amount coordinates for verified model exchange reactions.

COBRA medium bounds remain reaction-flux magnitudes. Concentrations and host availability
are metabolite amounts: for the sole boundary metabolite coefficient c, q = -c * v.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExchangeIdentity:
    reaction_id: str
    metabolite: str
    compartment: str
    coefficient: float

    def signed_environment(self, raw_flux: float) -> float:
        return -self.coefficient * float(raw_flux)

    def uptake(self, raw_flux: float) -> float:
        return max(0.0, self.coefficient * float(raw_flux))

    def uptake_range(self, low: float, high: float) -> tuple[float, float]:
        return tuple(sorted((self.uptake(low), self.uptake(high))))  # type: ignore[return-value]

    def set_physical_uptake_limit(self, reaction: Any, amount: float) -> None:
        from cmig.core.boundary import set_supply_limit

        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f"invalid physical uptake limit for {self.reaction_id}: {amount}")
        set_supply_limit(reaction, amount / abs(self.coefficient))


def exchange_identity(reaction: Any) -> ExchangeIdentity:
    """Validate one-metabolite external boundary topology without reaction-name inference."""
    rid = str(reaction.id)
    metabolites = getattr(reaction, "metabolites", None)
    if metabolites is None or len(metabolites) != 1:
        raise ValueError(f"unsupported multi-metabolite or empty exchange: {rid}")
    metabolite, raw = next(iter(metabolites.items()))
    coefficient = float(raw)
    if not math.isfinite(coefficient) or coefficient == 0:
        raise ValueError(f"invalid exchange coefficient: {rid}={raw}")
    met_id = str(getattr(metabolite, "id", "") or "")
    compartment = str(getattr(metabolite, "compartment", "") or "")
    suffix = f"_{compartment}"
    if not compartment or not met_id.endswith(suffix) or len(met_id) <= len(suffix):
        raise ValueError(f"unresolved exchange metabolite identity: {rid} -> {met_id}")
    return ExchangeIdentity(rid, met_id[: -len(suffix)], compartment, coefficient)
