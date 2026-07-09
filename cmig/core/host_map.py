"""Host-microbe exchange mapping wizard (§12 mapping wizard).

Pre-flight for host-microbe coupling: given a host GEM and a microbial model pool,
report which microbial secretions the host can directly consume (exact BiGG id),
which match only after id normalization (manual review), and which are unmatched
(no host counterpart) — so a user prepares an interface map instead of discovering
silent mismatches at solve time. Pure over cobra models; engine-independent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cmig.core.namespace import _normalize_metabolite_id


@dataclass(frozen=True)
class ExchangeMapEntry:
    metabolite: str                     # microbial secretion metabolite id (e.g. ac_e)
    microbial_exchange: str             # e.g. EX_ac_e
    secreting_members: list[str]
    host_exchange: str | None           # matched/suggested host exchange id (None = unmatched)
    match_type: str                     # exact | normalized | unmatched
    host_can_uptake: bool               # host exchange currently allows uptake (lower_bound < 0)
    suggestion: str


@dataclass(frozen=True)
class HostMapResult:
    n_microbial_secretions: int
    n_exact: int
    n_normalized: int
    n_unmatched: int
    n_host_uptake_capable: int
    entries: list[ExchangeMapEntry]
    warnings: list[str] = field(default_factory=list)


def _sole_metabolite_id(rxn: Any) -> str | None:
    """An exchange reaction touches exactly one metabolite; return its id (else None)."""
    mets = list(rxn.metabolites)
    return str(mets[0].id) if len(mets) == 1 else None


def _iter_exchanges(model: Any) -> list[Any]:
    try:
        return list(model.exchanges)
    except Exception:  # noqa: BLE001 - models without a cobra exchanges accessor
        return [r for r in model.reactions if str(r.id).startswith("EX_")]


# metabolite/normalized id → (host exchange id, host currently allows uptake)
_HostIdx = dict[str, tuple[str, bool]]


def _host_exchange_index(host: Any) -> tuple[_HostIdx, _HostIdx]:
    """Return (exact-id index, normalized-id index); each value is (exchange_id, can_uptake)."""
    exact: _HostIdx = {}
    normalized: _HostIdx = {}
    for rxn in _iter_exchanges(host):
        met = _sole_metabolite_id(rxn)
        if met is None:
            continue
        can_uptake = float(rxn.lower_bound) < 0.0
        exact.setdefault(met, (str(rxn.id), can_uptake))
        normalized.setdefault(_normalize_metabolite_id(met), (str(rxn.id), can_uptake))
    return exact, normalized


def build_host_map(host: Any, member_models: dict[str, Any]) -> HostMapResult:
    """Match each secretable microbial metabolite to a host exchange (exact/normalized/none)."""
    exact_idx, norm_idx = _host_exchange_index(host)

    # microbial secretable metabolites: metabolite → (exchange_id, [members])
    secretions: dict[str, tuple[str, list[str]]] = {}
    for member_id, model in member_models.items():
        for rxn in _iter_exchanges(model):
            if float(rxn.upper_bound) <= 0.0:      # can this exchange secrete at all?
                continue
            met = _sole_metabolite_id(rxn)
            if met is None:
                continue
            ex_id, members = secretions.get(met, (str(rxn.id), []))
            if str(member_id) not in members:
                members.append(str(member_id))
            secretions[met] = (ex_id, members)

    entries: list[ExchangeMapEntry] = []
    n_exact = n_norm = n_unmatched = n_uptake = 0
    for met in sorted(secretions):
        ex_id, members = secretions[met]
        if met in exact_idx:
            host_ex, can_uptake = exact_idx[met]
            match_type = "exact"
            suggestion = (
                "direct BiGG match; host consumes it" if can_uptake
                else "host exchange present but uptake closed (open lower_bound to consume)"
            )
            n_exact += 1
        elif _normalize_metabolite_id(met) in norm_idx:
            host_ex, can_uptake = norm_idx[_normalize_metabolite_id(met)]
            match_type = "normalized"
            suggestion = (
                f"normalized match to {host_ex}; verify identity before coupling "
                "(compartment/suffix differs)"
            )
            n_norm += 1
        else:
            host_ex, can_uptake = None, False
            match_type = "unmatched"
            suggestion = "no host exchange; add EX_<met> to the host or provide an interface map"
            n_unmatched += 1
        if can_uptake:
            n_uptake += 1
        entries.append(ExchangeMapEntry(
            metabolite=met,
            microbial_exchange=ex_id,
            secreting_members=sorted(members),
            host_exchange=host_ex,
            match_type=match_type,
            host_can_uptake=can_uptake,
            suggestion=suggestion,
        ))

    warnings: list[str] = []
    if n_unmatched:
        warnings.append(f"{n_unmatched} microbial secretions have no host exchange")
    if n_norm:
        warnings.append(
            f"{n_norm} matches rely on id normalization; manual review recommended")
    return HostMapResult(
        n_microbial_secretions=len(secretions),
        n_exact=n_exact,
        n_normalized=n_norm,
        n_unmatched=n_unmatched,
        n_host_uptake_capable=n_uptake,
        entries=entries,
        warnings=warnings,
    )
