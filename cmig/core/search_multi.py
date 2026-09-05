"""Budgeted multi-target discovery with fixed fitness scales and a feasible Pareto archive."""

from __future__ import annotations

import math
from dataclasses import asdict, replace
from itertools import islice
from typing import Any, cast

from cmig.core.search import TargetSpec
from cmig.core.search_advanced import pareto_frontier_nd
from cmig.core.search_execution import SearchControl
from cmig.core.search_ga import Genome, genetic_search
from cmig.core.search_product import (
    MULTI_METRIC_UNITS,
    MultiTargetConfig,
    MultiTargetRank,
    MultiTargetSearchResult,
    _capability_ranges,
    _ComboEval,
    _evaluate_members_multi,
    _evaluate_members_multi_joint,
    _ga_metadata,
    _iter_candidate_combinations,
    _json_safe,
    _multi_target_warnings,
    _pareto_points_for_members,
    choose_strategy,
    count_candidate_combinations,
    rank_multi_target,
    sample_candidate_combinations,
)


def archive_order(
    genomes: list[Genome], points: dict[Genome, list[_ComboEval]], targets: list[str]
) -> list[Genome]:
    """Rank feasible *solutions*, then use their best rank/crowding for each consortium.

    No componentwise capability vector is invented: every vector is an achieved
    LP solution with its own epsilon policy. Stable ties preserve the GA's seeded shuffle.
    """
    remaining = [
        (genome, tuple(point.signed[target] for target in targets))
        for genome in genomes
        for point in points[genome]
        if point.status == "optimal"
    ]
    priority = dict.fromkeys(genomes, (math.inf, math.inf))
    front_index = 0
    while remaining:
        front = pareto_frontier_nd([vector for _, vector in remaining])
        crowding = dict.fromkeys(front, 0.0)
        for dimension in range(len(targets)):
            ordered = sorted(front, key=lambda i: remaining[i][1][dimension])
            low, high = remaining[ordered[0]][1][dimension], remaining[ordered[-1]][1][dimension]
            if high <= low:
                continue
            crowding[ordered[0]] = crowding[ordered[-1]] = math.inf
            for pos in range(1, len(ordered) - 1):
                crowding[ordered[pos]] += (
                    remaining[ordered[pos + 1]][1][dimension]
                    - remaining[ordered[pos - 1]][1][dimension]
                ) / (high - low)
        for index in front:
            genome = remaining[index][0]
            priority[genome] = min(priority[genome], (front_index, -crowding[index]))
        keep = set(front)
        remaining = [point for index, point in enumerate(remaining) if index not in keep]
        front_index += 1
    return sorted(genomes, key=priority.__getitem__)


def _decode(raw: dict[str, Any]) -> _ComboEval:
    return _ComboEval(
        **{
            **raw,
            "members": tuple(raw["members"]),
            "missing_targets": tuple(raw.get("missing_targets", ())),
            "effective_members": tuple(raw.get("effective_members", ())),
        }
    )


def run_multi_search(
    engine: Any,
    taxonomy: Any,
    config: MultiTargetConfig,
    *,
    medium_spec: Any,
    strict_medium: bool,
    control: SearchControl | None,
    _batch_evaluate: Any = None,
) -> MultiTargetSearchResult:
    from cmig.core.search_ga import GAConfig
    from cmig.service.search_service import ConfiguredEngine, SearchRequest, search_workers

    if control is not None and control.workers > 1 and _batch_evaluate is None:
        request = SearchRequest(taxonomy, config, medium_spec, strict_medium)
        with search_workers(request, control) as batch:
            return run_multi_search(
                engine,
                taxonomy,
                config,
                medium_spec=medium_spec,
                strict_medium=strict_medium,
                control=control,
                _batch_evaluate=batch,
            )

    if (
        len(config.targets) < 2
        or len(set(config.targets)) != len(config.targets)
        or set(config.directions) != set(config.targets)
        or set(config.weights) != set(config.targets)
    ):
        raise ValueError("unique targets, directions and weights must agree (at least two targets)")
    if any(
        not math.isfinite(weight) or weight < 0 for weight in config.weights.values()
    ) or not any(config.weights.values()):
        raise ValueError("target weights must be finite, non-negative and not all zero")
    if (
        config.min_size < 1
        or config.max_size < config.min_size
        or config.top_k < 1
        or not 0 < config.growth_fraction <= 1
        or config.pareto_resolution < 2
    ):
        raise ValueError("invalid size, top-k, growth fraction or Pareto resolution")
    if config.metric not in MULTI_METRIC_UNITS:
        raise ValueError(f"unsupported multi-target metric: {config.metric}")
    ids = [str(member) for member in taxonomy["id"]]
    total = count_candidate_combinations(ids, config.min_size, config.max_size)
    if not total:
        raise ValueError("no candidate combinations generated")
    strategy = choose_strategy(total, config.strategy, exhaustive_max=config.exhaustive_max)
    if strategy == "exhaustive" and total > config.exhaustive_max:
        raise ValueError(f"{total} candidates > exhaustive_max={config.exhaustive_max}")
    if config.reference_scales and (
        set(config.reference_scales) != set(config.targets)
        or any(not math.isfinite(value) or value <= 0 for value in config.reference_scales.values())
    ):
        raise ValueError("reference scales must be finite and positive for every target")
    if (
        strategy in {"ga", "random"}
        and config.metric == "normalized_weighted"
        and not config.reference_scales
    ):
        raise ValueError(
            "approximate normalized search requires fixed --target-scales; "
            "or use --multi-metric raw_sum/carbon_equivalent/pareto"
        )
    if strategy not in {"ga", "random", "exhaustive"}:
        raise ValueError(f"unsupported search strategy: {strategy}")
    if control is not None:
        engine = ConfiguredEngine(engine, control.solver_threads, control.solve_timeout)
    specs = [
        TargetSpec(target, config.directions[target], config.weights[target])
        for target in config.targets
    ]
    notes: set[str] = set()
    common = dict(
        growth_fraction=config.growth_fraction,
        solver=config.solver,
        medium_spec=medium_spec,
        strict_medium=strict_medium,
        medium_notes=notes,
        growth_policy=config.growth_policy,
    )
    cache: dict[Genome, list[_ComboEval]] = {}
    capabilities: dict[Genome, _ComboEval] = {}
    if control is not None:
        for genome, record in control.records.items():
            if record.get("capability") is not None:
                capabilities[genome] = _decode(record["capability"])
            if record.get("points") is not None:
                cache[genome] = [_decode(point) for point in record["points"]]
        notes.update(
            point.medium_note
            for point in [
                *capabilities.values(),
                *(point for group in cache.values() for point in group),
            ]
            if point.medium_note
        )

    def check() -> None:
        if control is not None:
            control.check()

    def save(genome: Genome) -> None:
        if control is not None:
            control.records[genome] = _json_safe(
                {
                    "members": list(genome),
                    "capability": asdict(capabilities[genome]) if genome in capabilities else None,
                    "points": [asdict(point) for point in cache[genome]]
                    if genome in cache
                    else None,
                }
            )
            control.save()
            control.report(len(cache), total)

    def capability(genome: Genome) -> _ComboEval:
        if genome not in capabilities:
            check()
            capabilities[genome] = _evaluate_members_multi(
                engine, taxonomy, genome, specs, **common
            )
            save(genome)
        return capabilities[genome]

    ranges = {target: (0.0, config.reference_scales.get(target, 1.0)) for target in config.targets}

    def batch_evaluate(genomes: list[Genome], *, phase: str = "evaluate") -> list[float]:
        known = capabilities if phase == "capability" else cache
        pending = [genome for genome in genomes if genome not in known]
        if _batch_evaluate is not None and pending:
            check()
            for genome, cap, group, messages in _batch_evaluate(
                pending,
                phase=phase,
                ranges=ranges,
                capabilities=capabilities,
            ):
                if cap is not None:
                    capabilities[genome] = cap
                if group is not None:
                    cache[genome] = group
                notes.update(messages)
                save(genome)
        if phase == "capability":
            for genome in pending:
                capability(genome)
            return []
        return [evaluate(genome) for genome in genomes]

    def evaluate_candidates(candidates: Any, *, phase: str = "evaluate") -> None:
        iterator = iter(candidates)
        while batch := list(islice(iterator, control.workers if control else 1)):
            check()
            batch_evaluate(batch, phase=phase)

    if config.metric == "normalized_weighted" and not config.reference_scales:
        evaluate_candidates(
            _iter_candidate_combinations(ids, config.min_size, config.max_size),
            phase="capability",
        )
        ranges = _capability_ranges(list(capabilities.values()), specs)

    def evaluate(genome: Genome) -> float:
        if genome not in cache:
            check()
            if config.metric == "pareto":
                cap = capability(genome)
                cache[genome] = (
                    _pareto_points_for_members(
                        engine,
                        taxonomy,
                        genome,
                        specs,
                        capability=cap.signed,
                        resolution=config.pareto_resolution,
                        **common,
                    )
                    if cap.status == "optimal"
                    else [cap]
                )
            else:
                cache[genome] = [
                    _evaluate_members_multi_joint(
                        engine,
                        taxonomy,
                        genome,
                        specs,
                        normalization_ranges=ranges,
                        metric=config.metric,
                        **common,
                    )
                ]
            save(genome)
        ranked, _ = rank_multi_target(
            cache[genome], specs, normalization_ranges=ranges, metric=config.metric
        )
        return max((row.weighted_score for row in ranked), default=-math.inf)

    metadata = None
    if strategy == "ga":
        ga_config = replace(
            config.ga_config or GAConfig(),
            min_size=config.min_size,
            max_size=config.max_size,
            seed=config.seed,
        )
        if config.metric == "pareto" and ga_config.patience is not None:
            # A scalar-best plateau is not a Pareto plateau. Use the hard budget
            # and generation cap; expose this effective setting in provenance.
            ga_config = replace(ga_config, patience=None)
            notes.add("Pareto search disables scalar patience; evaluation/generation limits apply")
        result = genetic_search(
            ids,
            evaluate,
            ga_config,
            top_k=config.top_k,
            rank_population=(lambda genomes: archive_order(genomes, cache, config.targets))
            if config.metric == "pareto"
            else None,
            batch_fitness_fn=batch_evaluate if _batch_evaluate is not None else None,
            batch_size=control.workers if control else 1,
            **cast(
                dict[str, Any],
                {
                    "checkpoint_state": control.algorithm_state,
                    "on_checkpoint": control.save_algorithm,
                    "cancel_check": control.check,
                    "on_progress": control.report,
                }
                if control is not None
                else {},
            ),
        )
        metadata = _ga_metadata(ga_config, result)
        metadata["selection"] = (
            "feasible_front_rank_and_crowding" if config.metric == "pareto" else "scalar"
        )
    else:
        candidates = (
            _iter_candidate_combinations(ids, config.min_size, config.max_size)
            if strategy == "exhaustive"
            else iter(
                sample_candidate_combinations(
                    ids,
                    config.min_size,
                    config.max_size,
                    n_samples=config.n_samples,
                    seed=config.seed,
                )
            )
        )
        evaluate_candidates(candidates)

    points = [point for group in cache.values() for point in group]
    all_rows, normalizer = rank_multi_target(
        points, specs, normalization_ranges=ranges, metric=config.metric
    )
    if config.metric == "normalized_weighted":
        normalizer = (
            "fixed_reference_affine_unclipped"
            if config.reference_scales
            else "capability_range_affine_unclipped"
        )
    solved = [row for row in all_rows if row.rank > 0]
    failed = [row for row in all_rows if row.rank == 0]
    archive: list[MultiTargetRank] = []
    seen = set()
    for row in solved:
        if row.pareto:
            key = (
                row.members,
                tuple(round(row.target_fluxes[target], 8) for target in config.targets),
            )
            if key not in seen:
                seen.add(key)
                archive.append(replace(row, rank=len(archive) + 1))
    ranked = archive if config.metric == "pareto" else solved
    warnings = list(_multi_target_warnings(solved, failed, config)) + sorted(notes)
    if strategy != "exhaustive":
        warnings.append("approximate multi-target search; global optimum is not guaranteed")
    if config.metric == "pareto":
        warnings.append(
            "sampled Pareto approximation with objective extremes; not a complete "
            "continuous front. rank is reporting order, not a best-producer claim"
        )
    return MultiTargetSearchResult(
        targets=config.targets,
        target_exchanges={spec.metabolite: spec.exchange_id() for spec in specs},
        directions={target: direction.value for target, direction in config.directions.items()},
        weights=config.weights,
        strategy=strategy + ("_epsilon_archive" if config.metric == "pareto" else ""),
        normalizer=normalizer,
        solution_semantics="joint_feasible_lp_vectors",
        n_pool_members=len(ids),
        n_candidates_total=total,
        n_candidates_evaluated=len(cache),
        ranks=ranked[: config.top_k],
        warnings=warnings,
        metric=config.metric,
        score_unit=MULTI_METRIC_UNITS[config.metric],
        unevaluated=failed,
        pareto_archive=archive,
        evaluations=all_rows,
        ga_metadata=metadata,
        normalization_ranges=ranges,
    )
