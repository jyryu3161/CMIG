"""Shared host result types and evidence-backed two-interface classification.

This is deliberately a leaf of the host stack.  Both :mod:`cmig.core.host` and
:mod:`cmig.core.host_coupling` import these definitions, which lets ``host``
statically re-export the coupling entry points without the old ``__getattr__``
cycle workaround.

Interface classification is conservative.  A generic ``e``/``s`` extracellular
compartment is not, by itself, evidence that the exchange is apical rather than
basolateral.  It becomes lumen evidence only when the same model exposes a
distinct, explicitly blood-side compartment.  Side-specific reaction or
metabolite metadata, explicit compartment names, the historical id suffixes,
and reviewed-map overrides are retained as inspectable evidence.  Conflicting
signals remain unclassified unless a reviewed override resolves them.
"""

from __future__ import annotations

import enum
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, TypeAlias

from cmig.core.sign import Scope, convert

DEFAULT_BIGG_COUPLING_EXCLUDE = frozenset({"h", "h2o", "co2"})
BIOMASS_BASIS_KINDS = frozenset({"measured", "literature", "validation"})


class HostInterface(enum.Enum):
    LUMEN = "lumen"
    BLOOD = "blood"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class InterfaceEvidence:
    """One reviewable reason an exchange was assigned to one host side."""

    rule: str
    source: str
    value: str
    interface: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "source": self.source,
            "value": self.value,
            "interface": self.interface,
        }


@dataclass(frozen=True)
class HostInterfaceAssignment:
    """Evidence-backed side assignment for one host exchange."""

    exchange_id: str
    interface: str
    evidence: tuple[InterfaceEvidence, ...]
    reviewed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "exchange_id": self.exchange_id,
            "interface": self.interface,
            "reviewed": self.reviewed,
            "evidence": [item.as_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class HostInterfaceClassification:
    """Complete classification audit for a host model's exchange boundary."""

    assignments: tuple[HostInterfaceAssignment, ...]
    unclassified_exchange_ids: tuple[str, ...]
    conflicted_exchange_ids: tuple[str, ...]
    n_exchanges: int

    @property
    def n_lumen(self) -> int:
        return sum(item.interface == HostInterface.LUMEN.value for item in self.assignments)

    @property
    def n_blood(self) -> int:
        return sum(item.interface == HostInterface.BLOOD.value for item in self.assignments)

    @property
    def has_lumen_blood_interfaces(self) -> bool:
        return self.n_lumen > 0 and self.n_blood > 0

    @property
    def complete(self) -> bool:
        return (
            self.has_lumen_blood_interfaces
            and len(self.assignments) == self.n_exchanges
            and not self.conflicted_exchange_ids
        )

    def by_exchange(self) -> dict[str, HostInterfaceAssignment]:
        return {item.exchange_id: item for item in self.assignments}

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_exchanges": self.n_exchanges,
            "n_lumen": self.n_lumen,
            "n_blood": self.n_blood,
            "n_unclassified": len(self.unclassified_exchange_ids),
            "n_conflicted": len(self.conflicted_exchange_ids),
            "has_lumen_blood_interfaces": self.has_lumen_blood_interfaces,
            "complete": self.complete,
            "assignments": [item.as_dict() for item in self.assignments],
            "unclassified_exchange_ids": list(self.unclassified_exchange_ids),
            "conflicted_exchange_ids": list(self.conflicted_exchange_ids),
        }


@dataclass(frozen=True)
class ReviewedInterfaceEntry:
    """One old-style or side-aware reviewed interface-map value."""

    exchange_id: str
    interface: str | None = None
    map_key: str = ""


InterfaceMapValue: TypeAlias = str | Mapping[str, Any]
HostInterfaceMap: TypeAlias = Mapping[str, InterfaceMapValue]


def reviewed_interface_entry(map_key: str, raw_value: InterfaceMapValue) -> ReviewedInterfaceEntry:
    """Parse one reviewed-map value without changing the legacy string meaning.

    Old files store ``metabolite: "EX_met_e"``.  The optional side-aware form is
    ``metabolite: {"host_exchange": "EX_met_e", "interface": "lumen"}``.
    A plain string deliberately has ``interface=None`` so old maps continue to
    route exactly as before.
    """
    key = str(map_key)
    if isinstance(raw_value, str):
        exchange_id = raw_value.strip()
        if not exchange_id:
            raise ValueError(f"invalid host exchange mapping: {key} -> {raw_value!r}")
        return ReviewedInterfaceEntry(exchange_id=exchange_id, map_key=key)
    if not isinstance(raw_value, Mapping):
        raise ValueError(f"invalid host exchange mapping: {key} -> {raw_value!r}")
    raw_exchange = raw_value.get("host_exchange")
    if not isinstance(raw_exchange, str) or not raw_exchange.strip():
        raise ValueError(
            f"structured host interface mapping requires non-empty host_exchange: {key}"
        )
    raw_interface = raw_value.get("interface")
    interface: str | None = None
    if raw_interface is not None:
        interface = str(raw_interface).strip().lower()
        allowed = {HostInterface.LUMEN.value, HostInterface.BLOOD.value}
        if interface not in allowed:
            raise ValueError(
                f"host interface must be lumen or blood: {key} -> {raw_interface!r}"
            )
    return ReviewedInterfaceEntry(
        exchange_id=raw_exchange.strip(), interface=interface, map_key=key
    )


def reviewed_interface_entries(
    interface_map: HostInterfaceMap | None,
) -> dict[str, ReviewedInterfaceEntry]:
    return {
        str(key): reviewed_interface_entry(str(key), value)
        for key, value in (interface_map or {}).items()
    }


_LUMEN_TEXT = re.compile(
    r"\b(?:lumen|luminal|apical)\b|\b(?:intestinal|colonic|gut)\s+lumen\b",
    re.IGNORECASE,
)
_BLOOD_TEXT = re.compile(
    r"\b(?:blood|basolateral|plasma|serum)\b|\bportal\s+(?:blood|vein|circulation)\b",
    re.IGNORECASE,
)
_GENERIC_EXTERNAL_IDS = frozenset({"e", "s"})


def _interface_of_suffix(exchange_id: str) -> HostInterface:
    lowered = exchange_id.lower()
    if lowered.endswith("_lumen"):
        return HostInterface.LUMEN
    if lowered.endswith("_blood"):
        return HostInterface.BLOOD
    return HostInterface.UNKNOWN


def _text_interfaces(value: Any) -> set[HostInterface]:
    text = str(value)
    out: set[HostInterface] = set()
    if _LUMEN_TEXT.search(text):
        out.add(HostInterface.LUMEN)
    if _BLOOD_TEXT.search(text):
        out.add(HostInterface.BLOOD)
    return out


def _annotation_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [
            f"{key}={item}"
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        ]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item) for item in value]
    return [str(value)]


def _sole_metabolite(reaction: Any) -> Any | None:
    metabolites = list(getattr(reaction, "metabolites", ()) or ())
    return metabolites[0] if len(metabolites) == 1 else None


def _host_exchanges(host: Any) -> list[Any]:
    """Exchange reactions confirmed against the complete boundary view when available."""
    try:
        exchanges = list(host.exchanges)
    except Exception:  # noqa: BLE001 - compatibility with lightweight review/test models
        exchanges = [
            reaction for reaction in host.reactions
            if str(reaction.id).startswith("EX_")
        ]
    try:
        from cmig.core.boundary import boundary_reactions

        boundary = boundary_reactions(host)
    except Exception:  # noqa: BLE001 - classification can still expose suffix evidence on stubs
        boundary = list(exchanges)
    boundary_ids = {str(reaction.id) for reaction in boundary}
    by_id = {str(reaction.id): reaction for reaction in exchanges}
    compartments = {
        str(key): str(value)
        for key, value in dict(getattr(host, "compartments", {}) or {}).items()
    }
    # cobra's ``model.exchanges`` chooses one external compartment. A genuine two-interface model
    # can therefore omit every blood boundary from that accessor. Recover boundary reactions that
    # explicitly identify a side; do not sweep in anonymous intracellular sinks/demands.
    for reaction in boundary:
        reaction_id = str(reaction.id)
        metabolite = _sole_metabolite(reaction)
        compartment_id = str(getattr(metabolite, "compartment", "") or "")
        explicit_side = (
            _interface_of_suffix(reaction_id) is not HostInterface.UNKNOWN
            or bool(_text_interfaces(getattr(reaction, "name", "") or ""))
            or bool(_text_interfaces(getattr(reaction, "subsystem", "") or ""))
            or bool(_text_interfaces(compartment_id))
            or bool(_text_interfaces(compartments.get(compartment_id, "")))
        )
        if reaction_id.startswith("EX_") or explicit_side:
            by_id.setdefault(reaction_id, reaction)
    return sorted(
        (reaction for reaction in by_id.values() if str(reaction.id) in boundary_ids),
        key=lambda reaction: str(reaction.id),
    )


def classify_host_interfaces(
    host: Any,
    *,
    interface_map: HostInterfaceMap | None = None,
) -> HostInterfaceClassification:
    """Classify host exchanges as lumen/blood and retain every rule that fired.

    Reviewed entries with an explicit ``interface`` override model-derived
    signals.  Without an override, contradictory signals are reported as a
    conflict and no side is guessed.
    """
    reviewed = reviewed_interface_entries(interface_map)
    exchanges = _host_exchanges(host)
    exchange_ids = {str(reaction.id) for reaction in exchanges}
    if reviewed:
        try:
            from cmig.core.boundary import boundary_reactions

            boundary_by_id = {
                str(reaction.id): reaction for reaction in boundary_reactions(host)
            }
        except Exception:  # noqa: BLE001 - lightweight models may expose only reactions
            boundary_by_id = {
                str(reaction.id): reaction
                for reaction in getattr(host, "reactions", ()) or ()
            }
        for entry in reviewed.values():
            reaction = boundary_by_id.get(entry.exchange_id)
            if reaction is not None and entry.exchange_id not in exchange_ids:
                exchanges.append(reaction)
                exchange_ids.add(entry.exchange_id)
        exchanges.sort(key=lambda reaction: str(reaction.id))
    overrides: dict[str, list[ReviewedInterfaceEntry]] = {}
    for entry in reviewed.values():
        if entry.exchange_id in exchange_ids and entry.interface is not None:
            overrides.setdefault(entry.exchange_id, []).append(entry)

    raw_compartments = dict(getattr(host, "compartments", {}) or {})
    compartment_labels = {str(key): str(value) for key, value in raw_compartments.items()}
    explicit_blood_compartments = {
        key
        for key, name in compartment_labels.items()
        if HostInterface.BLOOD in _text_interfaces(key)
        or HostInterface.BLOOD in _text_interfaces(name)
    }

    assignments: list[HostInterfaceAssignment] = []
    unclassified: list[str] = []
    conflicted: list[str] = []
    for reaction in exchanges:
        reaction_id = str(reaction.id)
        reviewed_for_reaction = overrides.get(reaction_id, [])
        reviewed_sides = {entry.interface for entry in reviewed_for_reaction}
        if reviewed_for_reaction and len(reviewed_sides) == 1:
            reviewed_side = next(iter(reviewed_sides))
            assert reviewed_side is not None
            evidence = tuple(
                InterfaceEvidence(
                    rule="reviewed_interface_map",
                    source=f"interface_map[{entry.map_key!r}]",
                    value=entry.exchange_id,
                    interface=reviewed_side,
                )
                for entry in sorted(reviewed_for_reaction, key=lambda item: item.map_key)
            )
            assignments.append(HostInterfaceAssignment(
                exchange_id=reaction_id,
                interface=reviewed_side,
                evidence=evidence,
                reviewed=True,
            ))
            continue
        if len(reviewed_sides) > 1:
            conflicted.append(reaction_id)
            continue

        signals: list[InterfaceEvidence] = []

        suffix_side = _interface_of_suffix(reaction_id)
        if suffix_side is not HostInterface.UNKNOWN:
            signals.append(InterfaceEvidence(
                rule="exchange_id_suffix",
                source="reaction.id",
                value=reaction_id,
                interface=suffix_side.value,
            ))

        for source, value in (
            ("reaction.name", getattr(reaction, "name", "") or ""),
            ("reaction.subsystem", getattr(reaction, "subsystem", "") or ""),
        ):
            for detected_side in sorted(_text_interfaces(value), key=lambda item: item.value):
                signals.append(InterfaceEvidence(
                    rule="side_specific_metadata",
                    source=source,
                    value=str(value),
                    interface=detected_side.value,
                ))
        for annotation_key, raw_value in sorted(
            dict(getattr(reaction, "annotation", {}) or {}).items()
        ):
            for value in _annotation_values(raw_value):
                for detected_side in sorted(
                    _text_interfaces(value), key=lambda item: item.value
                ):
                    signals.append(InterfaceEvidence(
                        rule="reaction_annotation",
                        source=f"reaction.annotation[{annotation_key!r}]",
                        value=value,
                        interface=detected_side.value,
                    ))

        metabolite = _sole_metabolite(reaction)
        if metabolite is not None:
            metabolite_name = getattr(metabolite, "name", "") or ""
            for detected_side in sorted(
                _text_interfaces(metabolite_name), key=lambda item: item.value
            ):
                signals.append(InterfaceEvidence(
                    rule="side_specific_metadata",
                    source="metabolite.name",
                    value=str(metabolite_name),
                    interface=detected_side.value,
                ))
            for annotation_key, raw_value in sorted(
                dict(getattr(metabolite, "annotation", {}) or {}).items()
            ):
                for value in _annotation_values(raw_value):
                    for detected_side in sorted(
                        _text_interfaces(value), key=lambda item: item.value
                    ):
                        signals.append(InterfaceEvidence(
                            rule="metabolite_annotation",
                            source=f"metabolite.annotation[{annotation_key!r}]",
                            value=value,
                            interface=detected_side.value,
                        ))
            compartment_id = str(getattr(metabolite, "compartment", "") or "")
            compartment_name = compartment_labels.get(compartment_id, "")
            compartment_sides = (
                _text_interfaces(compartment_id) | _text_interfaces(compartment_name)
            )
            for detected_side in sorted(compartment_sides, key=lambda item: item.value):
                signals.append(InterfaceEvidence(
                    rule="explicit_compartment",
                    source=f"compartment[{compartment_id!r}]",
                    value=compartment_name or compartment_id,
                    interface=detected_side.value,
                ))
            if (
                not compartment_sides
                and compartment_id.lower() in _GENERIC_EXTERNAL_IDS
                and explicit_blood_compartments
            ):
                signals.append(InterfaceEvidence(
                    rule="paired_external_compartment",
                    source=f"compartment[{compartment_id!r}]",
                    value=(
                        f"{compartment_name or compartment_id}; distinct blood-side compartments="
                        f"{sorted(explicit_blood_compartments)}"
                    ),
                    interface=HostInterface.LUMEN.value,
                ))

        sides = {item.interface for item in signals}
        if len(sides) == 1:
            assignments.append(HostInterfaceAssignment(
                exchange_id=reaction_id,
                interface=next(iter(sides)),
                evidence=tuple(signals),
            ))
        elif len(sides) > 1:
            conflicted.append(reaction_id)
        else:
            unclassified.append(reaction_id)

    return HostInterfaceClassification(
        assignments=tuple(assignments),
        unclassified_exchange_ids=tuple(unclassified),
        conflicted_exchange_ids=tuple(conflicted),
        n_exchanges=len(exchanges),
    )


@dataclass(frozen=True)
class InterfaceFlux:
    """One host exchange flux with its interface, sign, and classification evidence."""

    exchange_id: str
    interface: str
    metabolite: str
    flux: float
    label: str | None
    evidence: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class HostSolveResult:
    viable: bool
    status: str
    biomass: float
    interface_fluxes: list[InterfaceFlux] = field(default_factory=list)
    lumen_uptake: dict[str, float] = field(default_factory=dict)
    diagnostic: str | None = None
    lumen_uptake_ranges: dict[str, tuple[float, float]] = field(default_factory=dict)
    attribution_method: str = "objective_fixed_fva"
    flux_unit: str = "mmol gDW_host^-1 h^-1"
    boundary_isolation: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CouplingScale:
    microbial_biomass_gdw: float
    host_biomass_gdw: float
    microbe_to_host_ratio: float
    basis_kind: str
    basis_source: str
    source_flux_unit: str = "mmol gDW_microbiome^-1 h^-1"
    target_flux_unit: str = "mmol gDW_host^-1 h^-1"


@dataclass(frozen=True)
class HostModelSummary:
    model_id: str
    n_reactions: int
    n_metabolites: int
    n_genes: int
    n_exchanges: int
    compartments: dict[str, str]
    objective_reactions: list[str]
    exchange_examples: list[str]
    has_lumen_blood_interfaces: bool
    objective_warning: str | None = None
    n_boundary_reactions: int = 0
    n_nonexchange_boundary_uptake: int = 0
    interface_classification: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HostBenchmarkResult:
    summary: HostModelSummary
    solve: HostSolveResult
    solve_seconds: float
    peak_memory_mb: float
    quantitative_coupling_ready: bool
    warnings: list[str]


@dataclass(frozen=True)
class BiggHostMicrobeResult:
    community_status: str
    community_growth: float
    microbial_secretion: dict[str, float]
    member_secretion: dict[str, dict[str, float]]
    matched_exchanges: dict[str, str]
    unmatched_metabolites: list[str]
    host_result: HostSolveResult
    impact: Any
    warnings: list[str]
    community_secretion: dict[str, float] = field(default_factory=dict)
    coupling_scale: CouplingScale | None = None
    objective_warning: str | None = None
    objective_reactions: list[str] = field(default_factory=list)
    unapplied_medium_exchanges: tuple[str, ...] = ()


def _met_from_host_exchange(exchange_id: str) -> str:
    value = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
    for suffix in ("_lumen", "_blood"):
        if value.endswith(suffix):
            return value[: -len(suffix)]
    return value


def _bigg_exchange_id(metabolite: str, *, suffix: str = "_e") -> str:
    return f"EX_{metabolite}{suffix}"


def _met_from_bigg_exchange(exchange_id: str, *, suffix: str = "_e") -> str:
    value = exchange_id[3:] if exchange_id.startswith("EX_") else exchange_id
    return value[: -len(suffix)] if value.endswith(suffix) else value


def _availability_flux(value: float, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} availability must be numeric, not bool")
    flux = float(value)
    if not math.isfinite(flux) or flux < 0.0:
        raise ValueError(f"{label} availability must be finite and non-negative")
    return flux


def _coupling_scale(
    microbial_biomass_gdw: float,
    host_biomass_gdw: float,
    *,
    basis_kind: str,
    basis_source: str,
) -> CouplingScale:
    microbial = _availability_flux(
        microbial_biomass_gdw, label="microbial_biomass_gdw"
    )
    host = _availability_flux(host_biomass_gdw, label="host_biomass_gdw")
    if microbial <= 0.0 or host <= 0.0:
        raise ValueError("microbial_biomass_gdw and host_biomass_gdw must be > 0")
    kind = str(basis_kind).strip().lower()
    if kind not in BIOMASS_BASIS_KINDS:
        raise ValueError(
            "biomass_basis_kind must be one of: " + ", ".join(sorted(BIOMASS_BASIS_KINDS))
        )
    source = str(basis_source).strip()
    if not source:
        raise ValueError(
            "biomass_basis_source is required (measurement method or literature citation)"
        )
    return CouplingScale(microbial, host, microbial / host, kind, source)


def _uptake_fva_ranges(
    model: Any, exchange_ids: list[str]
) -> dict[str, tuple[float, float]]:
    if not exchange_ids:
        return {}
    from cobra.flux_analysis import flux_variability_analysis

    table = flux_variability_analysis(
        model,
        reaction_list=sorted(exchange_ids),
        fraction_of_optimum=1.0,
    )
    ranges: dict[str, tuple[float, float]] = {}
    for reaction_id in sorted(exchange_ids):
        minimum = float(table.loc[reaction_id, "minimum"])
        maximum = float(table.loc[reaction_id, "maximum"])
        ranges[reaction_id] = (max(0.0, -maximum), max(0.0, -minimum))
    return ranges


def _identified_points(
    ranges: dict[str, tuple[float, float]], *, tolerance: float = 1e-6
) -> dict[str, float]:
    return {
        metabolite: (lower + upper) / 2.0
        for metabolite, (lower, upper) in ranges.items()
        if upper > tolerance and upper - lower <= tolerance
    }


def _reaction_metabolite_id(host: Any, exchange_id: str) -> str:
    try:
        reaction = host.reactions.get_by_id(exchange_id)
    except (AttributeError, KeyError):
        return _met_from_host_exchange(exchange_id)
    metabolite = _sole_metabolite(reaction)
    if metabolite is None:
        return _met_from_host_exchange(exchange_id)
    value = str(metabolite.id)
    compartment = str(getattr(metabolite, "compartment", "") or "")
    suffix = f"_{compartment}" if compartment else ""
    return value[: -len(suffix)] if suffix and value.endswith(suffix) else value


def classify_host_exchanges(
    fluxes: dict[str, float],
    *,
    host: Any | None = None,
    interface_map: HostInterfaceMap | None = None,
) -> list[InterfaceFlux]:
    """Classify host exchange fluxes with one sign-conversion entry point.

    The no-model form retains the historical suffix-only behavior.  Supplying a
    host enables the evidence-backed classifier.
    """
    if host is None:
        assignments = {
            exchange_id: HostInterfaceAssignment(
                exchange_id=exchange_id,
                interface=side.value,
                evidence=(InterfaceEvidence(
                    rule="exchange_id_suffix",
                    source="reaction.id",
                    value=exchange_id,
                    interface=side.value,
                ),),
            )
            for exchange_id in fluxes
            if (side := _interface_of_suffix(exchange_id)) is not HostInterface.UNKNOWN
        }
    else:
        assignments = classify_host_interfaces(
            host, interface_map=interface_map
        ).by_exchange()
    out: list[InterfaceFlux] = []
    for exchange_id, flux in sorted(fluxes.items()):
        assignment = assignments.get(exchange_id)
        if assignment is None:
            continue
        signed = convert(flux, Scope.ENVIRONMENT)
        out.append(InterfaceFlux(
            exchange_id=exchange_id,
            interface=assignment.interface,
            metabolite=(
                _reaction_metabolite_id(host, exchange_id)
                if host is not None else _met_from_host_exchange(exchange_id)
            ),
            flux=flux,
            label=signed.label.value if signed.label is not None else None,
            evidence=tuple(item.as_dict() for item in assignment.evidence),
        ))
    return out
