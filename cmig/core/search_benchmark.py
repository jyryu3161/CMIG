"""Small, exact-oracle multi-seed benchmarks for set search (no solver dependency)."""

from __future__ import annotations

import math
import time
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from itertools import combinations
from statistics import mean
from typing import Any

from cmig.core.search_ga import GAConfig, Genome, genetic_search
from cmig.core.search_product import count_candidate_combinations, sample_candidate_combinations


def benchmark_search(
    ids: list[str],
    fitness: Callable[[Genome], float],
    *,
    min_size: int,
    max_size: int,
    budget: int,
    seeds: Sequence[int] = tuple(range(10)),
    top_k: int = 10,
    exhaustive_max: int = 10_000,
) -> dict[str, Any]:
    """Build an exact oracle once, then compare algorithms at equal unique-query budgets.

    The recorded search time/memory exclude oracle construction and native solver
    allocations. For GEMs the expensive evaluations are timed separately. This
    measures search quality, not a claimed end-to-end parallel speedup.
    """
    ids = sorted(ids)
    total = count_candidate_combinations(ids, min_size, max_size)
    if not seeds or len(set(seeds)) != len(seeds) or not 0 < budget <= total:
        raise ValueError("use unique nonempty seeds and 0 < budget <= candidate count")
    if total > exhaustive_max or top_k < 1:
        raise ValueError("benchmark exceeds exhaustive guard or invalid top_k")
    start = time.perf_counter()
    oracle = {
        genome: float(fitness(genome))
        for size in range(min_size, max_size + 1)
        for genome in combinations(ids, size)
    }
    oracle = {
        genome: value if math.isfinite(value) else -math.inf for genome, value in oracle.items()
    }
    oracle_seconds = time.perf_counter() - start
    ranked = sorted(oracle, key=lambda genome: (-oracle[genome], genome))
    viable = [genome for genome in ranked if math.isfinite(oracle[genome])]
    if not viable:
        raise ValueError("benchmark oracle contains no feasible solution")
    optimum = oracle[viable[0]]
    threshold = oracle[viable[min(top_k, len(viable)) - 1]]
    reference = {genome for genome in viable if oracle[genome] >= threshold}
    population = min(30, max(3, budget // 4), total)
    config = GAConfig(
        min_size=min_size,
        max_size=max_size,
        pop_size=population,
        elitism=min(2, population - 1),
        generations=max(1000, budget * 10),
        max_evaluations=budget,
    )
    variants = {
        "ga": config,
        "restart": replace(config, restart_after=3),
        "local_swap": replace(config, local_search_fraction=0.3, preserve_common=True),
    }
    trials: list[dict[str, Any]] = []
    best_sets: dict[str, list[set[Genome]]] = {}
    for seed in seeds:
        for method in ("random", *variants):
            seen: dict[Genome, float] = {}

            def fit(genome: Genome, ledger: dict[Genome, float] = seen) -> float:
                ledger[genome] = oracle[genome]
                return oracle[genome]

            tracemalloc.start()
            start = time.perf_counter()
            history = []
            if method == "random":
                for genome in sample_candidate_combinations(
                    ids,
                    min_size,
                    max_size,
                    n_samples=budget,
                    seed=seed,
                ):
                    fit(genome)
                stop = "max_evaluations"
            else:
                result = genetic_search(ids, fit, replace(variants[method], seed=seed), top_k=top_k)
                history = [asdict(row) for row in result.history]
                stop = result.stop_reason
            elapsed = time.perf_counter() - start
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            best = max(seen.values(), default=-math.inf)
            top = set(sorted(seen, key=lambda genome: (-seen[genome], genome))[:top_k])
            best_sets.setdefault(method, []).append(top)
            trials.append(
                {
                    "method": method,
                    "seed": seed,
                    "evaluations": len(seen),
                    "budget_filled": len(seen) == budget,
                    "best": best,
                    "regret": optimum - best,
                    "hit_optimum": math.isclose(best, optimum, abs_tol=1e-8),
                    "tie_inclusive_top_k_recall": len(set(seen) & reference) / len(reference),
                    "feasible_fraction": mean(math.isfinite(value) for value in seen.values()),
                    "top_members": sorted(top),
                    "search_seconds": elapsed,
                    "peak_python_bytes": peak,
                    "stop_reason": stop,
                    "history": history,
                }
            )
    summaries = []
    for method, sets in best_sets.items():
        rows = [row for row in trials if row["method"] == method]
        overlap = [len(a & b) / len(a | b) for a, b in combinations(sets, 2)]
        summaries.append(
            {
                "method": method,
                "optimum_hit_rate": mean(row["hit_optimum"] for row in rows),
                "mean_regret": mean(row["regret"] for row in rows),
                "mean_top_k_recall": mean(row["tie_inclusive_top_k_recall"] for row in rows),
                "mean_top_k_jaccard_across_seeds": mean(overlap) if overlap else None,
                "all_budgets_filled": all(row["budget_filled"] for row in rows),
            }
        )
    return {
        "policy": "set_search_benchmark_v1",
        "oracle_candidates": total,
        "oracle_seconds": oracle_seconds,
        "oracle": [{"members": list(genome), "fitness": value} for genome, value in oracle.items()],
        "ga_configs": {name: asdict(value) for name, value in variants.items()},
        "optimum": optimum,
        "budget": budget,
        "seeds": list(seeds),
        "timing_scope": "oracle replay; Python-only search peak memory",
        "top_k_policy": "recall of all oracle solutions tied at the top-k threshold",
        "summary": summaries,
        "trials": trials,
    }


def synthetic_landscapes(ids: list[str]) -> dict[str, Callable[[Genome], float]]:
    strength = {member: float(index + 1) for index, member in enumerate(ids)}
    key = set(ids[:3])

    def additive(genome: Genome) -> float:
        return sum(strength[member] for member in genome)

    return {
        "additive": additive,
        "hidden_synergy": lambda genome: additive(genome) + (200 if key <= set(genome) else 0),
        "sparse_synergy": lambda genome: float(key <= set(genome)),
        "competition": lambda genome: (
            additive(genome) - (100 if set(ids[-2:]) <= set(genome) else 0)
        ),
        "infeasible_region": lambda genome: additive(genome) if ids[0] in genome else -math.inf,
    }
