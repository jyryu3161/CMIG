"""Publication-oriented GEM quality audit.

The audit separates reactions that are chemically balanced from reactions that cannot be
checked because formulas are missing. It does not claim to replace MEMOTE; it provides a
deterministic, dependency-light preflight that can be stored with CMIG benchmark outputs.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MODEL_QUALITY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ReactionImbalance:
    reaction_id: str
    imbalance: dict[str, float]


@dataclass(frozen=True)
class ModelQualityReport:
    schema_version: str
    model_id: str
    source_path: str | None
    source_checksum: str | None
    n_reactions: int
    n_metabolites: int
    n_genes: int
    n_exchanges: int
    objective_reactions: list[str]
    solve_status: str
    objective_value: float | None
    solve_seconds: float
    n_internal_reactions: int
    n_gene_associated_internal: int
    gene_association_coverage: float
    metabolite_formula_coverage: float
    metabolite_charge_coverage: float
    reaction_annotation_coverage: float
    metabolite_annotation_coverage: float
    gene_annotation_coverage: float
    n_mass_checkable: int
    n_mass_balanced: int
    n_mass_imbalanced: int
    n_mass_uncheckable: int
    mass_balance_pass_rate: float | None
    imbalanced_reactions: list[ReactionImbalance] = field(default_factory=list)
    n_dead_end_metabolites: int = 0
    dead_end_metabolites: list[str] = field(default_factory=list)
    blocked_reactions_checked: bool = False
    n_blocked_reactions: int | None = None
    blocked_reactions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _coverage(items: list[Any], predicate: Any) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if predicate(item)) / len(items)


def _source_checksum(path: str | Path | None) -> tuple[str | None, str | None]:
    if path is None:
        return None, None
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise ValueError(f"model quality source file not found: {source}")
    checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    return str(source), checksum


def _dead_end_metabolites(model: Any) -> list[str]:
    dead_ends: list[str] = []
    for metabolite in model.metabolites:
        can_produce = False
        can_consume = False
        for reaction in metabolite.reactions:
            coefficient = float(reaction.metabolites[metabolite])
            if reaction.upper_bound > 0.0:
                can_produce = can_produce or coefficient > 0.0
                can_consume = can_consume or coefficient < 0.0
            if reaction.lower_bound < 0.0:
                can_produce = can_produce or coefficient < 0.0
                can_consume = can_consume or coefficient > 0.0
        if not (can_produce and can_consume):
            dead_ends.append(str(metabolite.id))
    return sorted(dead_ends)


def audit_model_quality(
    model: Any,
    *,
    source_path: str | Path | None = None,
    solver: str = "gurobi",
    check_blocked_reactions: bool = False,
) -> ModelQualityReport:
    """Audit one Cobra-compatible model without mutating it."""
    from cobra.util.solver import linear_reaction_coefficients

    from cmig.core.single_model import _require_lp, set_model_solver

    _require_lp(solver)
    resolved_source, checksum = _source_checksum(source_path)
    reactions = list(model.reactions)
    metabolites = list(model.metabolites)
    genes = list(model.genes)
    exchanges = list(model.exchanges)
    internal = [reaction for reaction in reactions if not bool(reaction.boundary)]
    objective_reactions = sorted(str(r.id) for r in linear_reaction_coefficients(model))

    checkable = 0
    balanced = 0
    imbalanced: list[ReactionImbalance] = []
    uncheckable = 0
    for reaction in internal:
        if not reaction.metabolites or any(
            not str(getattr(metabolite, "formula", "") or "").strip()
            for metabolite in reaction.metabolites
        ):
            uncheckable += 1
            continue
        checkable += 1
        try:
            imbalance = {
                str(key): float(value)
                for key, value in reaction.check_mass_balance().items()
                if abs(float(value)) > 1e-9
            }
        except (TypeError, ValueError):
            uncheckable += 1
            checkable -= 1
            continue
        if imbalance:
            imbalanced.append(ReactionImbalance(str(reaction.id), imbalance))
        else:
            balanced += 1

    dead_ends = _dead_end_metabolites(model)
    blocked: list[str] = []
    started = time.perf_counter()
    with model:
        set_model_solver(model, solver)
        solution = model.optimize()
        solve_status = str(solution.status)
        objective_value = (
            float(solution.objective_value)
            if solve_status == "optimal" and solution.objective_value is not None
            else None
        )
        if objective_value is not None and not math.isfinite(objective_value):
            objective_value = None
        if check_blocked_reactions:
            from cobra.flux_analysis import find_blocked_reactions

            blocked = sorted(str(rid) for rid in find_blocked_reactions(model))
    elapsed = time.perf_counter() - started

    warnings: list[str] = []
    if not objective_reactions:
        warnings.append("objective reaction is not configured")
    if solve_status != "optimal":
        warnings.append(f"model objective solve is not optimal: {solve_status}")
    if uncheckable:
        warnings.append(
            f"{uncheckable} internal reactions lack complete metabolite formulas and were not "
            "classified as mass balanced"
        )
    if imbalanced:
        warnings.append(f"{len(imbalanced)} formula-complete internal reactions are imbalanced")
    if dead_ends:
        warnings.append(f"{len(dead_ends)} metabolites cannot both be produced and consumed")

    gene_associated = sum(1 for reaction in internal if str(reaction.gene_reaction_rule).strip())
    return ModelQualityReport(
        schema_version=MODEL_QUALITY_SCHEMA_VERSION,
        model_id=str(model.id),
        source_path=resolved_source,
        source_checksum=checksum,
        n_reactions=len(reactions),
        n_metabolites=len(metabolites),
        n_genes=len(genes),
        n_exchanges=len(exchanges),
        objective_reactions=objective_reactions,
        solve_status=solve_status,
        objective_value=objective_value,
        solve_seconds=elapsed,
        n_internal_reactions=len(internal),
        n_gene_associated_internal=gene_associated,
        gene_association_coverage=(gene_associated / len(internal) if internal else 0.0),
        metabolite_formula_coverage=_coverage(
            metabolites, lambda item: bool(str(getattr(item, "formula", "") or "").strip())
        ),
        metabolite_charge_coverage=_coverage(
            metabolites, lambda item: getattr(item, "charge", None) is not None
        ),
        reaction_annotation_coverage=_coverage(reactions, lambda item: bool(item.annotation)),
        metabolite_annotation_coverage=_coverage(metabolites, lambda item: bool(item.annotation)),
        gene_annotation_coverage=_coverage(genes, lambda item: bool(item.annotation)),
        n_mass_checkable=checkable,
        n_mass_balanced=balanced,
        n_mass_imbalanced=len(imbalanced),
        n_mass_uncheckable=uncheckable,
        mass_balance_pass_rate=(balanced / checkable if checkable else None),
        imbalanced_reactions=imbalanced,
        n_dead_end_metabolites=len(dead_ends),
        dead_end_metabolites=dead_ends,
        blocked_reactions_checked=check_blocked_reactions,
        n_blocked_reactions=len(blocked) if check_blocked_reactions else None,
        blocked_reactions=blocked,
        warnings=warnings,
    )
