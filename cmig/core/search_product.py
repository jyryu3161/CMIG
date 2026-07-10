"""Product-facing model-pool search.

This layer connects the target-max search core to user-provided model pools.
It supports exhaustive small-pool ranking, deterministic random sampling, and
GA approximation for larger candidate spaces.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, replace
from typing import Any, Literal

from cmig.core.search import Direction, TargetSpec, score_target_result, target_max_solve

SearchStrategy = Literal["auto", "exhaustive", "random", "ga"]


@dataclass(frozen=True)
class SearchConfig:
    target: str
    direction: Direction = Direction.MAX_SECRETION
    min_size: int = 2
    max_size: int = 2
    strategy: SearchStrategy = "auto"
    n_samples: int = 100
    seed: int = 0
    top_k: int = 10
    growth_fraction: float = 0.5
    solver: str = "gurobi"
    robustness_fva: bool = False


@dataclass(frozen=True)
class PoolRank:
    rank: int
    members: tuple[str, ...]
    score: float
    target_flux: float
    community_growth: float
    status: str
    diagnostic: str | None = None
    robustness_fva_lo: float | None = None
    robustness_fva_hi: float | None = None
    robustness_status: str | None = None

    @property
    def robustness_width(self) -> float | None:
        if self.robustness_fva_lo is None or self.robustness_fva_hi is None:
            return None
        return self.robustness_fva_hi - self.robustness_fva_lo


@dataclass(frozen=True)
class PoolSearchResult:
    target: str
    target_exchange: str
    direction: str
    strategy: str
    n_pool_members: int
    n_candidates_total: int
    n_candidates_evaluated: int
    ranks: list[PoolRank]
    warnings: list[str]


def _validate_config(config: SearchConfig) -> None:
    if config.min_size <= 0:
        raise ValueError("--min-size must be > 0")
    if config.max_size < config.min_size:
        raise ValueError("--max-size must be >= --min-size")
    if config.n_samples <= 0:
        raise ValueError("--n-samples must be > 0")
    if config.top_k <= 0:
        raise ValueError("--top-k must be > 0")
    if not (0.0 < config.growth_fraction <= 1.0):
        raise ValueError("--growth-fraction must satisfy 0<f<=1")


def candidate_combinations(ids: list[str], min_size: int, max_size: int) -> list[tuple[str, ...]]:
    """Enumerate sorted member combinations deterministically."""
    if max_size > len(ids):
        max_size = len(ids)
    return [
        tuple(combo)
        for size in range(min_size, max_size + 1)
        for combo in itertools.combinations(sorted(ids), size)
    ]


def choose_strategy(
    n_candidates: int, requested: SearchStrategy, *, exhaustive_max: int = 100
) -> str:
    """Resolve auto/random/GA strategy for product search."""
    if requested != "auto":
        return requested
    return "exhaustive" if n_candidates <= exhaustive_max else "random"


def _sample_candidates(
    candidates: list[tuple[str, ...]], *, n_samples: int, seed: int
) -> list[tuple[str, ...]]:
    if len(candidates) <= n_samples:
        return candidates
    rng = random.Random(seed)
    return sorted(rng.sample(candidates, n_samples))


def _evaluate_members(
    engine: Any,
    taxonomy: Any,
    members: tuple[str, ...],
    spec: TargetSpec,
    *,
    growth_fraction: float,
    solver: str,
    medium_spec: Any | None = None,
    strict_medium: bool = True,
    robustness_fva: bool = False,
) -> PoolRank:
    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        if medium_spec is not None:
            from cmig.core.medium_spec import apply_medium_checked

            apply_medium_checked(community, medium_spec, strict=strict_medium)
        result = target_max_solve(
            community,
            spec,
            growth_fraction=growth_fraction,
            solver=solver,
        )
        fva_lo = fva_hi = None
        fva_status = None
        if robustness_fva:
            from cmig.core.search_advanced import robustness_fva as run_robustness_fva

            fva = run_robustness_fva(
                community,
                spec,
                growth_fraction=growth_fraction,
                solver=solver,
            )
            fva_status = fva.status
            if fva.status == "ok":
                fva_lo = fva.fva_lo
                fva_hi = fva.fva_hi
        return PoolRank(
            rank=0,
            members=members,
            score=score_target_result(result, spec),
            target_flux=result.target_flux,
            community_growth=result.community_growth,
            status=result.status,
            diagnostic=result.diagnostic,
            robustness_fva_lo=fva_lo,
            robustness_fva_hi=fva_hi,
            robustness_status=fva_status,
        )
    except Exception as error:  # noqa: BLE001 - isolate one failed consortium
        return PoolRank(
            rank=0,
            members=members,
            score=float("-inf"),
            target_flux=0.0,
            community_growth=0.0,
            status="failed",
            diagnostic=str(error),
        )


def search_model_pool(
    engine: Any,
    taxonomy: Any,
    config: SearchConfig,
    *,
    medium_spec: Any | None = None,
    strict_medium: bool = True,
) -> PoolSearchResult:
    """Rank model-pool combinations for a target metabolite."""
    _validate_config(config)
    ids = [str(x) for x in taxonomy["id"]]
    if len(set(ids)) != len(ids):
        raise ValueError("taxonomy id values must be unique")
    candidates = candidate_combinations(ids, config.min_size, config.max_size)
    if not candidates:
        raise ValueError("no candidate combinations generated")
    strategy = choose_strategy(len(candidates), config.strategy)
    spec = TargetSpec(config.target, config.direction)
    warnings: list[str] = []
    cache: dict[tuple[str, ...], PoolRank] = {}

    def evaluate(members: tuple[str, ...]) -> PoolRank:
        if members not in cache:
            cache[members] = _evaluate_members(
                engine,
                taxonomy,
                members,
                spec,
                growth_fraction=config.growth_fraction,
                solver=config.solver,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
                robustness_fva=config.robustness_fva,
            )
        return cache[members]

    if strategy == "exhaustive":
        selected = candidates
    elif strategy == "random":
        selected = _sample_candidates(candidates, n_samples=config.n_samples, seed=config.seed)
        if len(selected) < len(candidates):
            warnings.append("random sampling evaluated a subset; global optimum is not guaranteed")
    elif strategy == "ga":
        from cmig.core.search_ga import GAConfig, genetic_search

        warnings.append("GA approximate search; global optimum is not guaranteed")
        ga = genetic_search(
            ids,
            lambda genome: evaluate(tuple(genome)).score,
            GAConfig(
                min_size=config.min_size,
                max_size=config.max_size,
                seed=config.seed,
            ),
            top_k=max(config.top_k, config.n_samples),
        )
        selected = [tuple(members) for members, _score in ga.top_k]
        warnings.append(ga.warning)
    else:
        raise ValueError(f"unsupported search strategy: {strategy}")

    ranks = [evaluate(members) for members in selected]
    ranks.sort(key=lambda row: (-row.score, row.members))
    ranked = [
        PoolRank(
            rank=i + 1,
            members=row.members,
            score=row.score,
            target_flux=row.target_flux,
            community_growth=row.community_growth,
            status=row.status,
            diagnostic=row.diagnostic,
            robustness_fva_lo=row.robustness_fva_lo,
            robustness_fva_hi=row.robustness_fva_hi,
            robustness_status=row.robustness_status,
        )
        for i, row in enumerate(ranks[: config.top_k])
    ]
    return PoolSearchResult(
        target=config.target,
        target_exchange=spec.exchange_id(),
        direction=config.direction.value,
        strategy=strategy,
        n_pool_members=len(ids),
        n_candidates_total=len(candidates),
        n_candidates_evaluated=len(cache),
        ranks=ranked,
        warnings=warnings,
    )


# ── Multi-target search (§14 다중 타깃) ─────────────────────────────────────────
# Users can rank model-pool combinations against several targets at once, combined
# by a weighted sum of per-target scores normalized into [0,1] over the observed
# range, plus (for exactly two targets) a Pareto non-dominated flag.


@dataclass(frozen=True)
class MultiTargetConfig:
    targets: list[str]
    directions: dict[str, Direction]
    weights: dict[str, float]
    min_size: int = 2
    max_size: int = 2
    growth_fraction: float = 0.5
    solver: str = "gurobi"
    top_k: int = 10
    exhaustive_max: int = 100


@dataclass(frozen=True)
class MultiTargetRank:
    rank: int
    members: tuple[str, ...]
    weighted_score: float               # Σ weight·normalized ([0,1]); -inf if not evaluable
    target_fluxes: dict[str, float]     # metabolite → raw exchange flux
    target_scores: dict[str, float]     # metabolite → normalized [0,1]
    community_growth: float
    status: str
    pareto: bool = False
    diagnostic: str | None = None


@dataclass(frozen=True)
class MultiTargetSearchResult:
    targets: list[str]
    target_exchanges: dict[str, str]
    directions: dict[str, str]
    weights: dict[str, float]
    strategy: str
    normalizer: str
    solution_semantics: str
    n_pool_members: int
    n_candidates_total: int
    n_candidates_evaluated: int
    ranks: list[MultiTargetRank]
    warnings: list[str]


@dataclass(frozen=True)
class _ComboEval:
    members: tuple[str, ...]
    status: str
    community_growth: float
    fluxes: dict[str, float]
    signed: dict[str, float]            # direction-adjusted raw (larger = better), no weight
    diagnostic: str | None = None


def _signed_raw(result: Any, spec: TargetSpec) -> float:
    """Direction-adjusted raw target value (larger = better), without the weight."""
    if result.status != "optimal":
        return float("-inf")
    match spec.direction:
        case Direction.MAX_SECRETION | Direction.MIN_UPTAKE:
            return float(result.target_flux)
        case _:  # MIN_SECRETION, MAX_UPTAKE
            return -float(result.target_flux)


def rank_multi_target(
    evals: list[_ComboEval], specs: list[TargetSpec], *,
    normalization_ranges: dict[str, tuple[float, float]] | None = None,
) -> tuple[list[MultiTargetRank], str]:
    """Pure ranking: normalize per-target over observed range, weight, Pareto-flag (2 targets).

    Returns (ranked_rows, normalizer_name). Testable without a solver.
    """
    from cmig.core.search_advanced import (
        normalize_score,
        pareto_frontier,
        weighted_multi_target,
    )

    mets = [s.metabolite for s in specs]
    ok = [e for e in evals if e.status == "optimal"]
    ranges: dict[str, tuple[float, float]] = {}
    for m in mets:
        if normalization_ranges is not None and m in normalization_ranges:
            ranges[m] = normalization_ranges[m]
        else:
            vals = [e.signed[m] for e in ok if m in e.signed]
            ranges[m] = (min(vals), max(vals)) if vals else (0.0, 1.0)

    rows: list[MultiTargetRank] = []
    normalizer = (
        "capability_range_joint_lp" if normalization_ranges is not None else "observed_range"
    )
    for e in evals:
        if e.status != "optimal":
            rows.append(MultiTargetRank(
                0, e.members, float("-inf"), e.fluxes, {}, e.community_growth,
                e.status, False, e.diagnostic))
            continue
        normalized: dict[str, float] = {}
        for m in mets:
            lo, hi = ranges[m]
            normalized[m] = normalize_score(
                e.signed[m], observed_min=lo, observed_max=hi).value
        ws = weighted_multi_target(normalized, specs)
        rows.append(MultiTargetRank(
            0, e.members, ws, e.fluxes, normalized, e.community_growth, "optimal", False, None))

    if len(mets) == 2:
        ok_idx = [i for i, r in enumerate(rows) if r.status == "optimal"]
        pts = [(evals[i].signed[mets[0]], evals[i].signed[mets[1]]) for i in ok_idx]
        keep = {ok_idx[k] for k in pareto_frontier(pts)}
        rows = [replace(r, pareto=(i in keep)) for i, r in enumerate(rows)]

    rows.sort(key=lambda r: (-r.weighted_score, r.members))
    return [replace(r, rank=i + 1) for i, r in enumerate(rows)], normalizer


def _evaluate_members_multi(
    engine: Any, taxonomy: Any, members: tuple[str, ...], specs: list[TargetSpec], *,
    growth_fraction: float, solver: str, medium_spec: Any | None, strict_medium: bool,
) -> _ComboEval:
    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        if medium_spec is not None:
            from cmig.core.medium_spec import apply_medium_checked

            apply_medium_checked(community, medium_spec, strict=strict_medium)
        fluxes: dict[str, float] = {}
        signed: dict[str, float] = {}
        status = "optimal"
        growth = 0.0
        diag: str | None = None
        for spec in specs:
            res = target_max_solve(
                community, spec, growth_fraction=growth_fraction, solver=solver)
            fluxes[spec.metabolite] = float(res.target_flux)
            signed[spec.metabolite] = _signed_raw(res, spec)
            growth = float(res.community_growth)
            if res.status != "optimal":       # any target unevaluable → combo not rankable
                status = res.status
                diag = res.diagnostic
        return _ComboEval(members, status, growth, fluxes, signed, diag)
    except Exception as e:  # noqa: BLE001 - per-combo isolation
        return _ComboEval(members, "failed", 0.0, {}, {}, str(e))


def _capability_ranges(
    evals: list[_ComboEval], specs: list[TargetSpec]
) -> dict[str, tuple[float, float]]:
    """Observed per-target capability ranges used only to scale the joint LP objective."""
    ok = [row for row in evals if row.status == "optimal"]
    ranges: dict[str, tuple[float, float]] = {}
    for spec in specs:
        values = [row.signed[spec.metabolite] for row in ok if spec.metabolite in row.signed]
        ranges[spec.metabolite] = (min(values), max(values)) if values else (0.0, 1.0)
    return ranges


def _evaluate_members_multi_joint(
    engine: Any, taxonomy: Any, members: tuple[str, ...], specs: list[TargetSpec], *,
    normalization_ranges: dict[str, tuple[float, float]], growth_fraction: float,
    solver: str, medium_spec: Any | None, strict_medium: bool,
) -> _ComboEval:
    """Evaluate one consortium with a single jointly feasible weighted LP solution."""
    from cmig.core.search import joint_target_solve

    sub = taxonomy[taxonomy["id"].astype(str).isin(members)].copy()
    try:
        community = engine.build_community(sub, cmig_solver=solver)
        if medium_spec is not None:
            from cmig.core.medium_spec import apply_medium_checked

            apply_medium_checked(community, medium_spec, strict=strict_medium)
        scales = {
            metabolite: (high - low if high - low > 1e-12 else 1.0)
            for metabolite, (low, high) in normalization_ranges.items()
        }
        result = joint_target_solve(
            community,
            specs,
            normalization_scales=scales,
            growth_fraction=growth_fraction,
            solver=solver,
        )
        return _ComboEval(
            members,
            result.status,
            result.community_growth,
            result.target_fluxes,
            result.signed_values,
            result.diagnostic,
        )
    except Exception as e:  # noqa: BLE001 - per-combo isolation
        return _ComboEval(members, "failed", 0.0, {}, {}, str(e))


def search_model_pool_multi(
    engine: Any, taxonomy: Any, config: MultiTargetConfig, *,
    medium_spec: Any | None = None, strict_medium: bool = True,
) -> MultiTargetSearchResult:
    """Rank model-pool combinations against multiple targets (weighted-normalized + Pareto)."""
    if len(config.targets) < 2:
        raise ValueError("multi-target search needs >= 2 targets; use single --target otherwise")
    if config.min_size <= 0 or config.max_size < config.min_size:
        raise ValueError("require 0 < --min-size <= --max-size")
    if config.top_k <= 0:
        raise ValueError("--top-k must be > 0")
    if not (0.0 < config.growth_fraction <= 1.0):
        raise ValueError("--growth-fraction must satisfy 0<f<=1")
    if set(config.directions) != set(config.targets):
        raise ValueError("directions keys must match targets exactly")
    if set(config.weights) != set(config.targets):
        raise ValueError("weights keys must match targets exactly")
    if any(not math.isfinite(config.weights[t]) or config.weights[t] < 0.0 for t in config.targets):
        raise ValueError("target weights must be finite and non-negative")
    if not any(config.weights[t] > 0.0 for t in config.targets):
        raise ValueError("at least one target weight must be positive")

    ids = [str(x) for x in taxonomy["id"]]
    if len(set(ids)) != len(ids):
        raise ValueError("taxonomy id values must be unique")
    specs = [
        TargetSpec(t, config.directions[t], config.weights[t]) for t in config.targets
    ]
    candidates = candidate_combinations(ids, config.min_size, config.max_size)
    if not candidates:
        raise ValueError("no candidate combinations generated")
    if len(candidates) > config.exhaustive_max:
        raise ValueError(
            f"{len(candidates)} candidates > exhaustive_max={config.exhaustive_max}; "
            "narrow --min-size/--max-size (multi-target search is exhaustive-only, no silent "
            "truncation)")

    capability_evals = [
        _evaluate_members_multi(
            engine, taxonomy, members, specs,
            growth_fraction=config.growth_fraction, solver=config.solver,
            medium_spec=medium_spec, strict_medium=strict_medium)
        for members in candidates
    ]
    ranges = _capability_ranges(capability_evals, specs)
    evals: list[_ComboEval] = []
    for members, capability in zip(candidates, capability_evals, strict=True):
        if capability.status != "optimal":
            evals.append(capability)
            continue
        evals.append(
            _evaluate_members_multi_joint(
                engine,
                taxonomy,
                members,
                specs,
                normalization_ranges=ranges,
                growth_fraction=config.growth_fraction,
                solver=config.solver,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
            )
        )
    ranked, normalizer = rank_multi_target(
        evals, specs, normalization_ranges=ranges
    )
    warnings: list[str] = []
    if any(r.status != "optimal" for r in ranked):
        warnings.append(
            "some combinations were not evaluable on every target (missing exchange or "
            "non-optimal solve); those are excluded from ranking with a diagnostic")
    return MultiTargetSearchResult(
        targets=list(config.targets),
        target_exchanges={s.metabolite: s.exchange_id() for s in specs},
        directions={t: config.directions[t].value for t in config.targets},
        weights=dict(config.weights),
        strategy="exhaustive",
        normalizer=normalizer,
        solution_semantics="joint_weighted_lp_single_flux_vector",
        n_pool_members=len(ids),
        n_candidates_total=len(candidates),
        n_candidates_evaluated=len(evals),
        ranks=ranked[: config.top_k],
        warnings=warnings,
    )
