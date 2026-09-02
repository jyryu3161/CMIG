"""BiGG/explicit-map host coupling implementation.

The generic host inspection and lumen/blood host contract stay in :mod:`cmig.core.host`; this
module isolates the larger microbial-availability mapping and end-to-end MICOM orchestration.
"""

from __future__ import annotations

from typing import Any

from cmig.core.boundary import (
    BOUNDARY_ISOLATION_POLICY,
    boundary_reactions,
    close_boundary_supply,
    mass_supplying_boundary,
    set_supply_limit,
)
from cmig.core.host_types import (
    DEFAULT_BIGG_COUPLING_EXCLUDE,
    BiggHostMicrobeResult,
    HostInterface,
    HostInterfaceMap,
    HostSolveResult,
    InterfaceFlux,
    _availability_flux,
    _bigg_exchange_id,
    _coupling_scale,
    _identified_points,
    _met_from_bigg_exchange,
    _uptake_fva_ranges,
    classify_host_interfaces,
    reviewed_interface_entries,
)
from cmig.core.sign import Scope, convert

#: Which boundary reactions ``close_unlisted_uptake`` closes to isolate the host. Round 6 (track H)
#: changed this from `model.exchanges` to every boundary reaction, which **moved published host
#: objectives without moving any `run_hash`** — measured on Recon3D: `host-microbe-bigg`
#: `host_objective` 368.010247546 -> 0.0 under the identical `run_hash 60b4409749abdb98…`, with only
#: `result_digest` recording the change (5e0878dd… -> 9e22bffa…). This is exactly the situation
#: round 5 introduced `medium_policy` for: the discontinuity cannot live in a hash component
#: because `cmig_core_version` is frozen, so it is stamped as a non-hashed provenance marker
#: instead.
#:
#: Relationship to :data:`cmig.core.boundary.BOUNDARY_ISOLATION_POLICY`, since round 6 produced
#: both and they are **not** duplicates: this one dates *the host-coupling answer* (did
#: `close_unlisted_uptake` close only exchanges, or the whole boundary?), while
#: `boundary_isolation_policy` dates *the primitive* every isolation site now shares (medium
#: application, dFBA, minimal medium, the 2-interface host contract). A reader of a
#: `host_microbe_bigg` manifest needs the first to interpret `host_objective`; a reader of a
#: `solve` manifest needs the second to interpret a medium. Both are in
#: :data:`cmig.core.workflow_manifest.NON_HASHED_PROVENANCE_MARKERS`, so both reach `inspect-run`.
HOST_ISOLATION_POLICY = "all_boundary_uptake_v2"   # was: model_exchanges_only_v1

# ── Round 7: medium applicability on the host path ─────────────────────────────────────────────
# `run_bigg_host_microbe` hard-coded `apply_medium_checked(..., strict=True)` and no host command
# exposed `--allow-unknown-medium`, so a medium that `solve`/`search`/`strain-growth`/
# `abundance-impact`/`sweep` all run with a documented degradation was **fatal** on
# `host-microbe-bigg`, `host-search-bigg` and `host-ko-impact`. Measured on the shipped
# `medium_presets/gut_overlay_vmh_high_fiber_x100.csv` against `iML1515+iYO844+iHN637`: exactly
# one row of eighty (`EX_n2_m`, requested limit 0.0) has no counterpart in that pool.
#
# The messages below are constants because their *content* is the fix. The round-6 scenario
# surfaced `microbial community solve was not optimal (status=solver_failed)` for a medium
# problem, which sends a reader to debug the solver. A message that names the ids and the flag
# that unblocks them is the difference between a five-minute fix and a wrong conclusion.
MEDIUM_NOT_APPLICABLE = (
    "microbial medium exchange has no counterpart in the microbial community "
    "(matched on metabolite)"
)
HOST_MEDIUM_NOT_APPLICABLE = "host medium entry has no exchange in the host model"
MEDIUM_RELAXATION_HINT = (
    "pass --allow-unknown-medium to drop them and continue; the run is then reported as "
    "degraded and the dropped ids are named in warnings"
)
MEDIUM_DROPPED_PREFIX = (
    "requested microbial medium exchanges were NOT applied — no counterpart in the community "
    "(--allow-unknown-medium)"
)
HOST_MEDIUM_DROPPED_PREFIX = (
    "requested host medium entries were NOT applied — no exchange in the host model "
    "(--allow-unknown-medium)"
)


def host_exchange_resolver(
    exchange_ids: set[str],
    normalized_interface: dict[str, str],
    *,
    exchange_suffix: str = "_e",
) -> Any:
    """One id-resolution rule for host coupling, used by both the mapper and the solver.

    Round 6 [P0, pre-existing]: there were two. ``run_bigg_host_microbe`` built the fallback
    exchange id from the **raw** metabolite id and ``solve_bigg_host`` from the **lowercased**
    one, so a D/L metabolite resolved differently on the two sides of the same run. Measured:
    ``matched_exchanges {'lac__D': 'EX_lac__D_e'}`` was reported while the LP opened
    ``EX_lac__d_e``, which does not exist — the host was fed nothing, biomass came back ``0.0``,
    and ``warnings`` was ``[]``. A silent wrong answer.

    The resolution order, in one place:

    1. the key is already a reaction id in this model — use it;
    2. the reviewed interface map has an entry for its normalized form — use that;
    3. otherwise build ``EX_<raw metabolite><suffix>``.

    Step 3 uses the **raw** id because BiGG metabolite ids are case-sensitive (``glc__D`` is
    glucose; ``glc__d`` is nothing). Normalization exists to make *map lookup* and *exclusion*
    tolerant, and lowercasing an id before constructing a reaction name was never part of that.
    """
    from cmig.core.namespace import _normalize_metabolite_id

    def resolve(key: str) -> str:
        raw = str(key)
        if raw in exchange_ids:
            return raw
        mapped = normalized_interface.get(_normalize_metabolite_id(raw))
        if mapped is not None:
            return mapped
        return _bigg_exchange_id(raw, suffix=exchange_suffix)

    return resolve


def solve_bigg_host(
    host: Any,
    microbial_availability: dict[str, float],
    *,
    host_medium: dict[str, float] | None = None,
    interface_map: HostInterfaceMap | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_uptake: bool = True,
    strict_medium: bool = True,
    solver: str = "gurobi",
) -> HostSolveResult:
    """Solve a host GEM using microbial availability and an optional reviewed interface map.

    ``strict_medium=True`` (the default) refuses a ``host_medium`` entry the host has no exchange
    for. Round 7: those entries used to be dropped in silence — ``add_availability`` returned
    ``(None, flux)`` and nothing recorded it — so a half-applied host background was published
    with every artifact reporting a complete run. Unmatched *microbial* availability was already
    disclosed (``unmatched_metabolites``); the host's own medium was the one that was not.
    """
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.namespace import _normalize_metabolite_id
    from cmig.core.single_model import _require_lp, set_model_solver

    _require_lp(solver)
    host_medium = host_medium or {}
    with host:
        set_model_solver(host, solver)
        reviewed_entries = reviewed_interface_entries(interface_map)
        interface_classification = classify_host_interfaces(host, interface_map=interface_map)
        exchange_ids = {
            assignment.exchange_id for assignment in interface_classification.assignments
        } | set(interface_classification.unclassified_exchange_ids) | set(
            interface_classification.conflicted_exchange_ids
        )
        normalized_reviewed: dict[str, Any] = {}
        normalized_interface: dict[str, str] = {}
        for raw_metabolite, reviewed_entry in reviewed_entries.items():
            key = _normalize_metabolite_id(str(raw_metabolite))
            exchange_id = reviewed_entry.exchange_id
            if exchange_id not in exchange_ids:
                raise ValueError(
                    f"interface map host exchange not found: {raw_metabolite} -> {exchange_id}"
                )
            prior = normalized_interface.setdefault(key, exchange_id)
            if prior != exchange_id:
                raise ValueError(
                    f"conflicting interface map for {raw_metabolite}: {prior}, {exchange_id}"
                )
            prior_entry = normalized_reviewed.setdefault(key, reviewed_entry)
            if (
                prior_entry.exchange_id != reviewed_entry.exchange_id
                or prior_entry.interface != reviewed_entry.interface
            ):
                raise ValueError(
                    f"conflicting interface map for {raw_metabolite}: "
                    f"{prior_entry}, {reviewed_entry}"
                )

        exchange_for = host_exchange_resolver(
            exchange_ids, normalized_interface, exchange_suffix=exchange_suffix
        )

        inferred_by_exchange = interface_classification.by_exchange()
        reviewed_by_exchange: dict[str, Any] = {}
        for entry in reviewed_entries.values():
            prior = reviewed_by_exchange.setdefault(entry.exchange_id, entry)
            if prior.interface != entry.interface:
                raise ValueError(
                    "conflicting reviewed interface sides for host exchange "
                    f"{entry.exchange_id}: {prior.interface!r}, {entry.interface!r}"
                )

        def interface_for(
            key: str, reaction_id: str
        ) -> tuple[str | None, tuple[dict[str, str], ...]]:
            reviewed = normalized_reviewed.get(_normalize_metabolite_id(str(key)))
            if reviewed is not None:
                # A plain string is the legacy map form.  It deliberately suppresses inference
                # for this route so old files keep their pre-round-7 meaning.
                if reviewed.interface is None:
                    return None, ()
                return reviewed.interface, ({
                    "rule": "reviewed_interface_map",
                    "source": f"interface_map[{reviewed.map_key!r}]",
                    "value": reviewed.exchange_id,
                    "interface": reviewed.interface,
                },)
            assignment = inferred_by_exchange.get(reaction_id)
            if assignment is None:
                return None, ()
            return (
                assignment.interface,
                tuple(item.as_dict() for item in assignment.evidence),
            )

        host_exchange_to_metabolite = {
            exchange_id: metabolite
            for metabolite, exchange_id in normalized_interface.items()
        }
        # Round 6 (track B, instance 2 / R6-CC-9): this used to iterate `host.exchanges`, which
        # excludes sinks and demands. On Recon3D that left 95 boundary reactions at
        # `lower_bound = -1000` — unbounded intracellular mass sources — and the published host
        # objective (368.01) was measured to be the same with microbial availability ZEROED, with
        # 36 `SK_*` reactions supplying mass at the optimum and 0 `EX_`. Isolation is now written
        # against `model.boundary`, which is the complete set.
        #
        # The concurrent human-GEM track fixed the same defect with a local loop over
        # `host.reactions`. This keeps the shared primitive (one place, direction-aware, and
        # byte-identical arithmetic to cobra's `set_active_bound`) and keeps that track's *output*:
        # `isolation_warnings` below names the sinks/demands that were closed, which is what makes
        # the isolation visible to a caller holding only a `HostSolveResult`.
        isolation_record: dict[str, Any] | None = None
        isolation_warnings: list[str] = []
        if close_unlisted_uptake:
            closure = close_boundary_supply(host)
            isolation_record = {
                "isolated": True,
                **closure.as_dict(),
                "n_open_suppliers": len(closure.opened),
                "n_open_non_exchange_suppliers": 0,
            }
            if closure.non_exchange_closed:
                isolation_warnings.append(
                    f"{len(closure.non_exchange_closed)} non-exchange boundary reactions "
                    "(cobra sinks/demands) also had uptake closed so the host is isolated; "
                    f"first: {list(closure.non_exchange_closed[:5])}"
                )
            if closure.forced_supply:
                isolation_warnings.append(
                    "host background could not be fully closed — these boundary reactions' bounds "
                    f"FORCE mass supply: {sorted(closure.forced_supply)}"
                )
        else:
            # `--keep-host-uptake` deliberately does NOT isolate: leaving the background open is a
            # legitimate diagnostic mode. Doing it *silently* is not, so the count travels with
            # the result and `run_bigg_host_microbe` turns it into a warning.
            open_suppliers = mass_supplying_boundary(host)
            isolation_record = {
                "isolated": False,
                "policy": BOUNDARY_ISOLATION_POLICY,
                "n_boundary": len(boundary_reactions(host)),
                "n_closed": 0,
                "n_closed_non_exchange": 0,
                "n_opened": len(open_suppliers),
                "forced_supply": {},
                "complete": False,
                "n_open_suppliers": len(open_suppliers),
                "n_open_non_exchange_suppliers": sum(
                    1 for supply in open_suppliers.values() if not supply.is_exchange
                ),
            }
            if open_suppliers:
                # R6-H's phrasing, kept verbatim: `--keep-host-uptake` is legal, and the objective
                # it produces must say on its own face that it is unattributed.
                isolation_warnings.append(
                    f"host uptake was NOT closed (--keep-host-uptake): {len(open_suppliers)} "
                    "boundary reactions can still supply mass, so this host objective is not "
                    "attributable to the microbial availability"
                )

        exchange_availability: dict[str, float] = {}
        microbial_caps: dict[str, float] = {}
        background_caps: dict[str, float] = {}
        applied_interface: dict[str, tuple[str, tuple[dict[str, str], ...]]] = {}

        def add_availability(
            key: str,
            value: float,
            *,
            label: str,
            required_interface: HostInterface | None = None,
        ) -> tuple[str | None, float, str | None]:
            reaction_id = exchange_for(key)
            flux = _availability_flux(value, label=label)
            if reaction_id in exchange_ids:
                interface, evidence = interface_for(key, reaction_id)
                if required_interface is not None and interface not in {
                    None, required_interface.value,
                }:
                    return None, flux, interface
                exchange_availability[reaction_id] = (
                    exchange_availability.get(reaction_id, 0.0) + flux
                )
                if interface is not None:
                    applied_interface[reaction_id] = (interface, evidence)
                return reaction_id, flux, None
            return None, flux, None

        unapplied_host_medium: list[str] = []
        wrong_side_host_medium: dict[str, str] = {}
        for key, value in host_medium.items():
            reaction_id, flux, wrong_side = add_availability(
                str(key), value, label=f"host_medium[{key!r}]",
                required_interface=HostInterface.BLOOD,
            )
            if reaction_id is not None:
                metabolite = _normalize_metabolite_id(str(key))
                background_caps[metabolite] = background_caps.get(metabolite, 0.0) + flux
            elif wrong_side is not None:
                wrong_side_host_medium[str(key)] = wrong_side
            else:
                unapplied_host_medium.append(str(key))
        if wrong_side_host_medium:
            raise ValueError(
                "host medium entries resolve to the lumen interface, but host_medium is the "
                f"blood/basolateral supply: {sorted(wrong_side_host_medium)}"
            )
        if unapplied_host_medium:
            if strict_medium:
                raise ValueError(
                    f"{HOST_MEDIUM_NOT_APPLICABLE}: {sorted(unapplied_host_medium)}. "
                    f"{MEDIUM_RELAXATION_HINT}"
                )
            isolation_warnings.append(
                f"{HOST_MEDIUM_DROPPED_PREFIX}: {sorted(unapplied_host_medium)}"
            )
        excluded = set(exclude_metabolites or set())
        # metabolite -> the host reaction id its availability was actually applied to. Round 6
        # [P0]: this used to be a *set* of normalized metabolites, and the FVA block below then
        # re-derived the reaction id from the normalized name — a second resolution, on a
        # different input, of a question already answered. With the raw-id fix in
        # `host_exchange_resolver` the two answers diverge (`arab__L` -> `EX_arab__L_e` on the way
        # in, `arab__l` -> `EX_arab__l_e` on the way out), so the resolved id is remembered
        # instead of being computed twice.
        matched: dict[str, str] = {}
        # normalized id -> the caller's raw id. The caps/ranges below are accumulated under the
        # normalized (lower-cased, suffix-stripped) id, but `lumen_uptake` and
        # `lumen_uptake_ranges` are joined downstream (`host_impact`, member contribution,
        # `host-ko-impact --target`) against the *raw* MICOM metabolite ids of the secretion
        # dict. Publishing them under the normalized spelling silently dropped every stereo
        # descriptor metabolite (`lac__D` -> `lac__d`, `glc__D`, every `__L` amino acid) from
        # microbe_to_host while `host_uptake.csv` listed it under the other spelling.
        raw_by_normalized: dict[str, str] = {}
        wrong_side_microbial: dict[str, str] = {}
        for raw_metabolite, value in microbial_availability.items():
            metabolite = _normalize_metabolite_id(str(raw_metabolite))
            if metabolite in excluded:
                continue
            reaction_id, flux, wrong_side = add_availability(
                raw_metabolite,
                value,
                label=f"microbial_availability[{raw_metabolite!r}]",
                required_interface=HostInterface.LUMEN,
            )
            if reaction_id is not None:
                microbial_caps[metabolite] = microbial_caps.get(metabolite, 0.0) + flux
                matched[metabolite] = reaction_id
                raw_by_normalized.setdefault(metabolite, str(raw_metabolite))
            elif wrong_side is not None:
                wrong_side_microbial[str(raw_metabolite)] = wrong_side
        if wrong_side_microbial:
            isolation_warnings.append(
                "microbial secretions resolved to blood/basolateral host exchanges and were NOT "
                f"coupled to the lumen: {sorted(wrong_side_microbial)}"
            )
        for reaction_id, availability in exchange_availability.items():
            # Same arithmetic as before for a `met -->` exchange; correct (upper_bound) for a
            # boundary reaction written the other way round, which the old line inverted.
            set_supply_limit(host.reactions.get_by_id(reaction_id), availability)
        if close_unlisted_uptake and isolation_record is not None:
            isolation_record["n_open_suppliers"] = len(exchange_availability)

        solution = host.optimize()
        status = "no_solution" if solution is None else str(solution.status)
        if status != "optimal":
            from cmig.core.diagnostics import DiagnosticCode, diagnostic_from_parts

            diagnostic = diagnostic_from_parts([(
                DiagnosticCode.INFEASIBLE,
                f"host LP non-optimal under microbial coupling (status={status})",
            )])
            return HostSolveResult(
                False, status, 0.0, [], {}, diagnostic,
                boundary_isolation=isolation_record,
                # A failed host LP still has to disclose what its background was, otherwise the
                # only run that can never be re-inspected is the one that went wrong.
                warnings=list(isolation_warnings),
            )

        fluxes = {str(reaction_id): float(value) for reaction_id, value in solution.fluxes.items()}
        coefficients = linear_reaction_coefficients(host)
        objective_value = sum(
            float(coefficient) * fluxes.get(reaction.id, 0.0)
            for reaction, coefficient in coefficients.items()
        )
        total_ranges = _uptake_fva_ranges(host, sorted(set(matched.values())))
        microbial_ranges: dict[str, tuple[float, float]] = {}
        for metabolite, reaction_id in sorted(matched.items()):
            total_lower, total_upper = total_ranges.get(reaction_id, (0.0, 0.0))
            microbial_cap = microbial_caps.get(metabolite, 0.0)
            lower = min(
                microbial_cap,
                max(0.0, total_lower - background_caps.get(metabolite, 0.0)),
            )
            upper = min(microbial_cap, total_upper)
            microbial_ranges[raw_by_normalized.get(metabolite, metabolite)] = (
                lower, max(lower, upper)
            )
        lumen_uptake = _identified_points(microbial_ranges)
        interface_fluxes: list[InterfaceFlux] = []
        for reaction_id in sorted(exchange_ids):
            flux = fluxes.get(reaction_id, 0.0)
            signed = convert(flux, Scope.ENVIRONMENT)
            if signed.label is None:
                continue
            metabolite = host_exchange_to_metabolite.get(
                reaction_id,
                _met_from_bigg_exchange(reaction_id, suffix=exchange_suffix),
            )
            reviewed_for_exchange = reviewed_by_exchange.get(reaction_id)
            assignment = inferred_by_exchange.get(reaction_id)
            if reviewed_for_exchange is not None and reviewed_for_exchange.interface is None:
                interface = "bigg_external"
                evidence: tuple[dict[str, str], ...] = ()
            elif reaction_id in applied_interface:
                interface, evidence = applied_interface[reaction_id]
            elif assignment is not None:
                interface = assignment.interface
                evidence = tuple(item.as_dict() for item in assignment.evidence)
            else:
                interface = "bigg_external"
                evidence = ()
            interface_fluxes.append(
                InterfaceFlux(
                    exchange_id=reaction_id,
                    interface=interface,
                    metabolite=metabolite,
                    flux=flux,
                    label=signed.label.value,
                    evidence=evidence,
                )
            )
        return HostSolveResult(
            viable=objective_value > 1e-9,
            status=status,
            biomass=objective_value,
            interface_fluxes=interface_fluxes,
            lumen_uptake=lumen_uptake,
            lumen_uptake_ranges=microbial_ranges,
            boundary_isolation=isolation_record,
            warnings=list(isolation_warnings),
        )


def _host_objective_reactions(host: Any) -> list[str]:
    """Reaction ids carrying a non-zero objective coefficient on the host, id-sorted."""
    from cobra.util.solver import linear_reaction_coefficients

    return sorted(str(reaction.id) for reaction in linear_reaction_coefficients(host))


def run_bigg_host_microbe(
    taxonomy: Any,
    host: Any,
    *,
    microbial_biomass_gdw: float,
    host_biomass_gdw: float,
    biomass_basis_kind: str,
    biomass_basis_source: str,
    solver: str = "gurobi",
    tradeoff_f: float = 0.5,
    microbe_medium: Any | None = None,
    host_medium: dict[str, float] | None = None,
    interface_map: HostInterfaceMap | None = None,
    exchange_suffix: str = "_e",
    exclude_metabolites: set[str] | frozenset[str] | None = DEFAULT_BIGG_COUPLING_EXCLUDE,
    close_unlisted_host_uptake: bool = True,
    strict_medium: bool = True,
    engine: Any = None,
) -> BiggHostMicrobeResult:
    """MICOM community secretion to reviewed-map/BiGG host coupling.

    ``strict_medium`` governs **both** media a host run carries (``microbe_medium`` and
    ``host_medium``) and is the single thing every host command's ``--allow-unknown-medium``
    sets. Default ``True`` — a medium the model cannot honour is refused, exactly as it was
    before round 7; what changed is that the refusal is now overridable, says which of the two
    media failed, and names the ids and the flag.
    """
    from cmig.core.engine import MicomEngine
    from cmig.core.host_impact import host_impact
    from cmig.core.namespace import _normalize_metabolite_id
    from cmig.io.model_import import objective_structure_warning

    # Round 6 [P1]: the guard runs BEFORE any solve, so an unusable objective is reported even when
    # the community or the host LP later fails. Every host-coupling command (`host-microbe-bigg`,
    # `host-search-bigg`, `host-ko-impact`) reaches it because every one of them calls this
    # function — that is the point of putting it here rather than in three CLI handlers.
    host_objective_reactions = _host_objective_reactions(host)
    objective_warning = objective_structure_warning(
        len(host_objective_reactions),
        [host.reactions.get_by_id(rid) for rid in host_objective_reactions],
    )

    community_engine = engine if engine is not None else MicomEngine()
    scale = _coupling_scale(
        microbial_biomass_gdw,
        host_biomass_gdw,
        basis_kind=biomass_basis_kind,
        basis_source=biomass_basis_source,
    )
    community = community_engine.build_community(taxonomy, cmig_solver=solver)
    unapplied_medium: tuple[str, ...] = ()
    if microbe_medium is not None:
        from cmig.core.medium_spec import medium_application_report, translate_medium_for_model

        # The strictness decision is made here, on the same translation the application uses, so
        # the refusal can name the ids *and* the remedy. Delegating it to
        # `apply_medium_translated(strict=True)` produced "medium exchange has no counterpart in
        # the target model" — true, but a host run has two media and the message named neither
        # the medium nor the way forward.
        preview = translate_medium_for_model(community, microbe_medium)
        if strict_medium and preview.unmatched:
            raise ValueError(
                f"{MEDIUM_NOT_APPLICABLE}: {list(preview.unmatched)}. {MEDIUM_RELAXATION_HINT}"
            )
        translation = medium_application_report(community, microbe_medium, strict=False)
        unapplied_medium = tuple(translation.unmatched)
    medium_warnings = (
        [f"{MEDIUM_DROPPED_PREFIX}: {list(unapplied_medium)}"] if unapplied_medium else []
    )
    community_result = community_engine.cooperative_tradeoff(
        community, tradeoff_f, cmig_solver=solver
    )
    if community_result.status != "optimal":
        host_result = HostSolveResult(
            False, community_result.status, 0.0, [], {}, community_result.diagnostic
        )
        return BiggHostMicrobeResult(
            community_status=community_result.status,
            community_growth=community_result.objective,
            microbial_secretion={},
            member_secretion={},
            matched_exchanges={},
            unmatched_metabolites=[],
            host_result=host_result,
            impact=host_impact({}, host_result),
            warnings=(
                ["biomass basis is validation-only; result is not publication-ready"]
                if scale.basis_kind == "validation" else []
            ) + [
                f"microbial community solve was not optimal (status={community_result.status})"
            ]
            # Round 7: the cause was reachable nowhere. The round-6 scenario published
            # `status=solver_failed` with two generic warnings, and the engine's own diagnostic
            # ("pFBA flux stage failed: OptimizationError: could not get community growth rate.")
            # went only onto the inner `HostSolveResult`, which no host command writes out. A
            # reader could not tell an infeasible community from a rejected medium, and the
            # message they did get pointed at the solver.
            + ([
                f"microbial community solve diagnostic: {community_result.diagnostic}"
            ] if getattr(community_result, "diagnostic", None) else [])
            + medium_warnings
            + list(getattr(community_result, "warnings", []) or [])
            + ([f"host objective: {objective_warning}"] if objective_warning else []),
            coupling_scale=scale,
            objective_warning=objective_warning,
            objective_reactions=host_objective_reactions,
            unapplied_medium_exchanges=unapplied_medium,
        )
    community_secretion = {
        metabolite: flux
        for metabolite, flux in community_result.external_exchange.items()
        if flux > 1e-6
    }
    secretion = {
        metabolite: flux * scale.microbe_to_host_ratio
        for metabolite, flux in community_secretion.items()
    }
    missing_abundances = [
        member
        for member in community_result.member_exchange
        if community_result.abundances.get(member) is None
    ]
    if missing_abundances:
        raise ValueError(
            f"member abundance missing; cannot scale host attribution: {missing_abundances}"
        )
    abundances = {
        member: float(abundance)
        for member, abundance in community_result.abundances.items()
        if abundance is not None
    }
    member_secretion = {
        member: {
            metabolite: flux * abundances[member] * scale.microbe_to_host_ratio
            for metabolite, flux in exchange.items()
            if flux > 1e-6
        }
        for member, exchange in community_result.member_exchange.items()
    }
    excluded = set(exclude_metabolites or set())
    reviewed_entries = reviewed_interface_entries(interface_map)
    interface_classification = classify_host_interfaces(host, interface_map=interface_map)
    exchange_ids = {
        assignment.exchange_id for assignment in interface_classification.assignments
    } | set(interface_classification.unclassified_exchange_ids) | set(
        interface_classification.conflicted_exchange_ids
    )
    normalized_interface = {
        _normalize_metabolite_id(metabolite): entry.exchange_id
        for metabolite, entry in reviewed_entries.items()
    }
    normalized_reviewed = {
        _normalize_metabolite_id(metabolite): entry
        for metabolite, entry in reviewed_entries.items()
    }
    # Round 6 [P0, pre-existing]: this block had its OWN id resolver, built from the raw
    # metabolite id, while `solve_bigg_host` built one from the lowercased id. The two disagreed
    # for any stereo metabolite: `matched_exchanges {'lac__D': 'EX_lac__D_e'}` was published while
    # the LP tried to open `EX_lac__d_e`, which does not exist — host biomass 0.0, `warnings: []`,
    # a silent wrong answer. There is now one resolver and both sides call it, so the reported map
    # and the applied bounds agree by construction rather than by coincidence.
    host_exchange_for = host_exchange_resolver(
        exchange_ids, normalized_interface, exchange_suffix=exchange_suffix
    )
    classified_by_exchange = interface_classification.by_exchange()

    def resolved_side(metabolite: str, exchange_id: str) -> str | None:
        reviewed = normalized_reviewed.get(_normalize_metabolite_id(metabolite))
        if reviewed is not None:
            return reviewed.interface
        assignment = classified_by_exchange.get(exchange_id)
        return assignment.interface if assignment is not None else None

    matched = {
        metabolite: host_exchange_for(metabolite)
        for metabolite in secretion
        if _normalize_metabolite_id(metabolite) not in excluded
        and host_exchange_for(metabolite) in exchange_ids
        and resolved_side(metabolite, host_exchange_for(metabolite))
        != HostInterface.BLOOD.value
    }
    blood_side_unmatched = sorted(
        metabolite for metabolite in secretion
        if _normalize_metabolite_id(metabolite) not in excluded
        and host_exchange_for(metabolite) in exchange_ids
        and resolved_side(metabolite, host_exchange_for(metabolite))
        == HostInterface.BLOOD.value
    )
    unmatched = sorted(
        metabolite for metabolite in secretion
        if metabolite not in matched and _normalize_metabolite_id(metabolite) not in excluded
    )
    host_result = solve_bigg_host(
        host,
        secretion,
        host_medium=host_medium,
        interface_map=interface_map,
        exchange_suffix=exchange_suffix,
        exclude_metabolites=exclude_metabolites,
        close_unlisted_uptake=close_unlisted_host_uptake,
        strict_medium=strict_medium,
        solver=solver,
    )
    warnings: list[str] = list(medium_warnings)
    if scale.basis_kind == "validation":
        warnings.append(
            "biomass basis is validation-only; result is not publication-ready"
        )
    if objective_warning:
        warnings.append(f"host objective: {objective_warning}")
    # Round 6 (track B): whether the host's background was actually closed decides whether the
    # host objective is attributable to the microbes at all. R6-CC-9 measured the failure: with
    # 95 sinks open the objective was 368.01 both with microbial availability and with it ZEROED.
    # `--keep-host-uptake` is a legitimate mode, so this is a warning and not a refusal — but it
    # is never silent, and the count is stated.
    isolation = host_result.boundary_isolation or {}
    if isolation.get("isolated") is False:
        warnings.append(
            "host background was NOT isolated (--keep-host-uptake): "
            f"{isolation.get('n_open_suppliers', '?')} boundary reactions can supply the host "
            f"mass, {isolation.get('n_open_non_exchange_suppliers', '?')} of them sinks/demands "
            "that no exchange enumeration can see; the host objective is therefore NOT "
            "attributable to the microbial community"
        )
    elif isolation.get("forced_supply"):
        warnings.append(
            "host background could not be fully closed — these boundary reactions' bounds FORCE "
            f"mass supply: {sorted(isolation['forced_supply'])}; the host objective is only "
            "partly attributable to the microbial community"
        )
    # R6-H: host-LP facts must reach the top-level summary too, not only the host block. The two
    # prefixes below are the ones the run-level block above already states, in a richer form (it
    # adds how many of the open suppliers are sinks/demands), so re-emitting them here would put
    # two paraphrases of one fact in the same list. Everything else the host LP recorded — notably
    # *which* sinks/demands were closed — is stated nowhere else and travels up.
    _RESTATED_AT_RUN_LEVEL = (
        "host uptake was NOT closed",
        "host background could not be fully closed",
    )
    warnings.extend(
        warning for warning in host_result.warnings
        if not warning.startswith(_RESTATED_AT_RUN_LEVEL)
    )
    # B6: host LP 실패는 최상위 요약에서 조용히 사라져서는 안 된다(status 파생 + warning 양쪽).
    if host_result.status != "optimal":
        warnings.append(
            f"host solve was not optimal (status={host_result.status}); "
            "the reported host objective is not a result"
        )
    # engine seam 은 duck-typed (engine: Any) — warnings 를 갖지 않는 double 도 허용한다.
    warnings.extend(getattr(community_result, "warnings", []) or [])
    excluded_present = sorted(set(secretion) & excluded)
    if excluded_present:
        warnings.append(f"excluded currency microbial secretions: {excluded_present}")
    if unmatched:
        warnings.append(f"unmatched microbial secretions: {unmatched}")
    if blood_side_unmatched:
        warnings.append(
            "microbial secretions mapped to blood/basolateral exchanges and were not coupled to "
            f"the lumen: {blood_side_unmatched}"
        )
    if not matched:
        warnings.append("no microbial secretions matched host exchange ids")
    impact = host_impact(secretion, host_result)
    if impact.ambiguous_metabolites:
        warnings.append(
            "host transfer is not point-identifiable at the optimal objective for: "
            f"{impact.ambiguous_metabolites}; report FVA intervals"
        )
    if any(member_secretion.values()):
        warnings.append(
            "member contribution uses an abundance-weighted proportional allocation; "
            "it is not causal or uniquely identifiable"
        )
    return BiggHostMicrobeResult(
        community_status=community_result.status,
        community_growth=community_result.objective,
        microbial_secretion=secretion,
        member_secretion=member_secretion,
        matched_exchanges=matched,
        unmatched_metabolites=unmatched,
        host_result=host_result,
        impact=impact,
        warnings=warnings,
        community_secretion=community_secretion,
        coupling_scale=scale,
        objective_warning=objective_warning,
        objective_reactions=host_objective_reactions,
        unapplied_medium_exchanges=unapplied_medium,
    )
