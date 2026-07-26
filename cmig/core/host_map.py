"""Host-microbe exchange mapping wizard (§12 mapping wizard).

Pre-flight for host-microbe coupling: given a host GEM and a microbial model pool,
report which microbial secretions the host can directly consume (exact BiGG id),
which match only after id normalization (manual review), and which are unmatched
(no host counterpart) — so a user prepares an interface map instead of discovering
silent mismatches at solve time. Pure over cobra models; engine-independent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cmig.core.namespace import (
    NORMALIZE_COMPARTMENT_SUFFIXES,
    NORMALIZE_EXCHANGE_PREFIX,
    _normalize_metabolite_id,
)

# ── the matching policy, as data ───────────────────────────────────────────────
# `build_host_map` has no user-facing knobs: what it produces is determined by the host model, the
# microbial pool, and *these rules*. Each constant below is read by the matcher itself — the
# ordering drives the strategy loop, the criterion names the predicate that runs, the annotation
# sources drive the index build — so editing one changes the answer rather than only the
# description of it. HOST_MAP_MATCH_POLICY_VERSION announces such a change to a human reader; it is
# no longer what *guards* the fingerprint (see `host_map_policy`).
HOST_MAP_MATCH_POLICY_VERSION = "1.0"

#: Match strategies attempted, in order; first hit wins. Consumed by :func:`build_host_map`.
HOST_MAP_MATCH_ORDER: tuple[str, ...] = ("exact", "annotation", "normalized")
#: Match types auto-admitted into `interface_map` (safe to pass through unedited).
HOST_MAP_INTERFACE_MAP_ADMITS: tuple[str, ...] = ("exact",)
#: Match types parked in `needs_review` — computational guesses, incl. D/L stereoisomer swaps.
HOST_MAP_NEEDS_REVIEW_TYPES: tuple[str, ...] = ("annotation", "normalized")
#: Annotation fields consulted for the annotation strategy, as (level, annotation key) in priority
#: order; the first level that yields any id wins. Consumed by :func:`_host_exchange_index`.
HOST_MAP_ANNOTATION_SOURCES: tuple[tuple[str, str], ...] = (
    ("metabolite", "bigg.metabolite"),
    ("reaction", "bigg.reaction"),
)
#: An annotation candidate is used only when every host exchange carrying that BiGG id is the same
#: exchange — two exchanges claiming one id identify nothing. Consumed by `_host_exchange_index`.
HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET = True
#: Names the predicate in `_SECRETION_CRITERIA` that decides whether a microbial exchange counts as
#: a secretion. Consumed by :func:`build_host_map`.
HOST_MAP_SECRETION_CRITERION = "exchange_upper_bound_gt_0"


def _secretes_when_upper_bound_gt_0(rxn: Any) -> bool:
    """Can this exchange carry positive (outward) flux at all?"""
    return float(rxn.upper_bound) > 0.0


#: criterion name → the predicate that implements it.
_SECRETION_CRITERIA: dict[str, Callable[[Any], bool]] = {
    "exchange_upper_bound_gt_0": _secretes_when_upper_bound_gt_0,
}


def _annotation_source_labels() -> list[str]:
    """The annotation sources as the human-readable expressions recorded in `map_spec`."""
    return [f"{level}.annotation[{key!r}]" for level, key in HOST_MAP_ANNOTATION_SOURCES]


def host_map_policy() -> dict[str, Any]:
    """The answer-determining matching policy of :func:`build_host_map`, as a hashable dict.

    Two kinds of field live here and the difference matters:

    * **Determining inputs.** ``match_behavior`` is a digest of what the matcher and the id
      normalizer actually *did* to a frozen probe fixture (see :mod:`cmig.core.host_map_probe`),
      and the remaining fields are read straight out of the constants the matcher consumes.
    * **Descriptions.** ``match_policy_version`` and the two normalizer notes
      (``uppercase_stereoisomer_suffix_folded``, ``case_folded``) are for a human reading the
      manifest. They are *not* what makes the fingerprint sound — ``match_behavior`` is.

    That distinction is the round-5 fix. Previously the control-flow facts were restated here as
    inert literals, so the matcher could be edited freely and the fingerprint would not notice: one
    changed comparison took the auto-admitted interface map from 67 entries to 11 under a
    bit-identical ``run_hash``. A described policy cannot certify an artifact; a measured one can.

    **What this does and does not guarantee.** Any change to a matching rule the probe fixture
    exercises moves this dict, and with it the host-map ``run_hash``. It is *not* true that every
    behaviour change does: the probe measures one small synthetic instance, so a change keyed on
    scale (a cap on how many entries are reported) or on real BiGG vocabulary (a currency-metabolite
    filter) can leave it unmoved — verification demonstrated exactly that, three times. Those are
    caught on the answer side instead, by ``result_digest`` in the manifest
    (:func:`cmig.core.workflow_manifest.artifact_result_digest`), which fingerprints the artifact
    bytes rather than the inputs. Certifying an implementation from the input side cannot be
    completed; the two fingerprints together are the guarantee, not this one alone.
    """
    from cmig.core.host_map_probe import match_behavior_component

    return {
        "match_policy_version": HOST_MAP_MATCH_POLICY_VERSION,
        "match_behavior": match_behavior_component(),
        "match_order": list(HOST_MAP_MATCH_ORDER),
        "interface_map_admits": list(HOST_MAP_INTERFACE_MAP_ADMITS),
        "needs_review_match_types": list(HOST_MAP_NEEDS_REVIEW_TYPES),
        "annotation_sources": _annotation_source_labels(),
        "annotation_requires_unique_target": HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET,
        "secretion_criterion": HOST_MAP_SECRETION_CRITERION,
        "id_normalization": {
            "exchange_prefix_stripped": NORMALIZE_EXCHANGE_PREFIX,
            "compartment_suffixes_stripped": list(NORMALIZE_COMPARTMENT_SUFFIXES),
            "uppercase_stereoisomer_suffix_folded": True,
            "case_folded": True,
        },
    }


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
    n_annotation: int
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


def _annotation_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _metabolite_annotation_ids(rxn: Any, key: str) -> list[str]:
    return [
        value
        for metabolite in rxn.metabolites
        for value in _annotation_values(metabolite.annotation.get(key))
    ]


def _reaction_annotation_ids(rxn: Any, key: str) -> list[str]:
    return _annotation_values(rxn.annotation.get(key))


#: annotation level → how ids are read at that level, for `HOST_MAP_ANNOTATION_SOURCES`.
_ANNOTATION_READERS: dict[str, Callable[[Any, str], list[str]]] = {
    "metabolite": _metabolite_annotation_ids,
    "reaction": _reaction_annotation_ids,
}


def _host_exchange_index(host: Any) -> tuple[_HostIdx, _HostIdx, _HostIdx]:
    """Return exact, normalized, and authoritative BiGG-annotation indices."""
    exact: _HostIdx = {}
    normalized: _HostIdx = {}
    annotation_candidates: dict[str, list[tuple[str, bool]]] = {}
    for rxn in _iter_exchanges(host):
        met = _sole_metabolite_id(rxn)
        if met is None:
            continue
        can_uptake = float(rxn.lower_bound) < 0.0
        exact.setdefault(met, (str(rxn.id), can_uptake))
        normalized.setdefault(_normalize_metabolite_id(met), (str(rxn.id), can_uptake))
        # Sources in declared priority order: metabolite cross-references identify the exchanged
        # chemical directly, and some curated models retain stale reaction-level BiGG annotations,
        # so the reaction level is consulted only when the metabolite level yielded nothing.
        annotation_ids: list[str] = []
        for level, annotation_key in HOST_MAP_ANNOTATION_SOURCES:
            annotation_ids.extend(_ANNOTATION_READERS[level](rxn, annotation_key))
            if annotation_ids:
                break
        for annotation_id in annotation_ids:
            key = _normalize_metabolite_id(annotation_id)
            annotation_candidates.setdefault(key, []).append((str(rxn.id), can_uptake))
    annotation = {
        key: values[0]
        for key, values in annotation_candidates.items()
        if not HOST_MAP_ANNOTATION_REQUIRES_UNIQUE_TARGET
        or len({exchange_id for exchange_id, _can_uptake in values}) == 1
    }
    return exact, normalized, annotation


def _exact_suggestion(_host_ex: str, can_uptake: bool) -> str:
    return (
        "direct BiGG match; host consumes it" if can_uptake
        else "host exchange present but uptake closed (open lower_bound to consume)"
    )


def _annotation_suggestion(host_ex: str, _can_uptake: bool) -> str:
    return (
        f"host BiGG annotation match to {host_ex}; confirm in interface map before "
        "quantitative coupling"
    )


def _normalized_suggestion(host_ex: str, _can_uptake: bool) -> str:
    return (
        f"normalized match to {host_ex}; verify identity before coupling "
        "(compartment/suffix differs)"
    )


#: strategy name → the reviewer-facing note recorded for a hit from that strategy.
_MATCH_SUGGESTIONS: dict[str, Callable[[str, bool], str]] = {
    "exact": _exact_suggestion,
    "annotation": _annotation_suggestion,
    "normalized": _normalized_suggestion,
}


def build_host_map(host: Any, member_models: dict[str, Any]) -> HostMapResult:
    """Match each secretable microbial metabolite to a host exchange (exact/normalized/none)."""
    exact_idx, norm_idx, annotation_idx = _host_exchange_index(host)
    secretes = _SECRETION_CRITERIA[HOST_MAP_SECRETION_CRITERION]

    # microbial secretable metabolites: metabolite → (exchange_id, [members])
    secretions: dict[str, tuple[str, list[str]]] = {}
    for member_id, model in member_models.items():
        for rxn in _iter_exchanges(model):
            if not secretes(rxn):                  # can this exchange secrete at all?
                continue
            met = _sole_metabolite_id(rxn)
            if met is None:
                continue
            ex_id, members = secretions.get(met, (str(rxn.id), []))
            if str(member_id) not in members:
                members.append(str(member_id))
            secretions[met] = (ex_id, members)

    entries: list[ExchangeMapEntry] = []
    counts: dict[str, int] = {"exact": 0, "annotation": 0, "normalized": 0, "unmatched": 0}
    n_uptake = 0
    for met in sorted(secretions):
        ex_id, members = secretions[met]
        # One lookup per declared strategy, consulted in HOST_MAP_MATCH_ORDER: the recorded
        # priority is the priority that runs, so reordering the constant reorders the answer
        # instead of only relabelling the manifest.
        normalized_met = _normalize_metabolite_id(met)
        candidates: dict[str, tuple[str, bool] | None] = {
            "exact": exact_idx.get(met),
            "annotation": annotation_idx.get(normalized_met),
            "normalized": norm_idx.get(normalized_met),
        }
        host_ex: str | None = None
        can_uptake = False
        match_type = "unmatched"
        suggestion = "no host exchange; add EX_<met> to the host or provide an interface map"
        for strategy in HOST_MAP_MATCH_ORDER:
            hit = candidates.get(strategy)
            if hit is None:
                continue
            host_ex, can_uptake = hit
            match_type = strategy
            suggestion = _MATCH_SUGGESTIONS[strategy](host_ex, can_uptake)
            break
        counts[match_type] = counts.get(match_type, 0) + 1
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

    n_exact, n_annotation = counts["exact"], counts["annotation"]
    n_norm, n_unmatched = counts["normalized"], counts["unmatched"]
    warnings: list[str] = []
    if n_unmatched:
        warnings.append(f"{n_unmatched} microbial secretions have no host exchange")
    if n_annotation:
        warnings.append(
            f"{n_annotation} matches use host BiGG annotations; save and review the interface map"
        )
    if n_norm:
        warnings.append(
            f"{n_norm} matches rely on id normalization; manual review recommended")
    return HostMapResult(
        n_microbial_secretions=len(secretions),
        n_exact=n_exact,
        n_annotation=n_annotation,
        n_normalized=n_norm,
        n_unmatched=n_unmatched,
        n_host_uptake_capable=n_uptake,
        entries=entries,
        warnings=warnings,
    )
