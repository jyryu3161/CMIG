"""Consortium Search — 유전 알고리즘 (>100 후보) (Roadmap Phase 3.6, §14).

Design Ref: §14 (GA strategy) / cmig-search-ga.design. Plan SC: SC-GA1~GA5.

대규모 후보(>100)에서 exhaustive 불가 → GA로 근사 탐색. genome=멤버셋(size bounds), fitness=
주입(target-max score), tournament 선택·union crossover·add/remove/swap mutation·elitism.
**결정적**(seed) + fitness 캐시(solve 재호출 회피). [honesty] 근사(전역 최적 미보장) —
결과에 경고 동반.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import combinations
from numbers import Real

Genome = tuple[str, ...]


@dataclass(frozen=True)
class GAConfig:
    pop_size: int = 30
    generations: int = 20
    min_size: int = 2
    max_size: int = 4
    mutation_rate: float = 0.2
    tournament_k: int = 3
    elitism: int = 2
    seed: int = 0
    immigrant_fraction: float = 0.1
    max_evaluations: int | None = None
    patience: int | None = None


@dataclass(frozen=True)
class GAGenerationStats:
    """한 세대가 끝났을 때의 결정적 수렴 진단."""

    generation: int
    best_fitness: float
    mean_fitness: float
    unique_genomes: int
    evaluations: int


@dataclass(frozen=True)
class GAResult:
    best_members: Genome
    best_fitness: float
    top_k: list[tuple[Genome, float]]
    generations_run: int
    evaluations: int                    # 실제 fitness 호출 수(캐시 효과 가시화)
    warning: str = "GA 근사 — 전역 최적 미보장(non-exhaustive)"
    stop_reason: str = "generations_complete"
    history: list[GAGenerationStats] = field(default_factory=list)


def _tournament(
    pop: list[Genome], fit: Callable[[Genome], float], rng: random.Random, k: int,
) -> Genome:
    contenders = rng.sample(pop, min(k, len(pop)))
    return min(contenders, key=lambda genome: (-fit(genome), genome))


def _crossover(a: Genome, b: Genome, rng: random.Random, lo: int, hi: int) -> Genome:
    pool = sorted(set(a) | set(b))
    size = rng.randint(lo, min(hi, len(pool)))
    return tuple(sorted(rng.sample(pool, size)))


def _mutate(g: Genome, ids: list[str], rng: random.Random, lo: int, hi: int) -> Genome:
    """Apply one valid set mutation.

    At an exact cardinality (``lo == hi``), add and remove are not valid independent
    operations, so mutation is a true one-for-one swap against the *global* candidate
    pool. This is what lets an exact-k search reach alleles absent from both parents.
    For a variable range, add, remove, and swap are all eligible whenever their size
    constraints permit them.
    """
    members = set(g)
    available = [member for member in ids if member not in members]
    operations: list[str] = []
    if len(members) > lo:
        operations.append("remove")
    if available and len(members) < hi:
        operations.append("add")
    if members and available:
        operations.append("swap")
    if not operations:
        return tuple(sorted(members))

    operation = rng.choice(operations)
    if operation == "remove":
        members.remove(rng.choice(sorted(members)))
    elif operation == "add":
        members.add(rng.choice(available))
    else:
        members.remove(rng.choice(sorted(members)))
        members.add(rng.choice(available))
    return tuple(sorted(members))


def _validate_config(config: GAConfig, top_k: int) -> None:
    integer_fields = (
        ("pop_size", config.pop_size, 1),
        ("generations", config.generations, 0),
        ("min_size", config.min_size, 1),
        ("max_size", config.max_size, 1),
        ("tournament_k", config.tournament_k, 1),
        ("elitism", config.elitism, 0),
    )
    for name, integer_value, minimum in integer_fields:
        if (
            isinstance(integer_value, bool)
            or not isinstance(integer_value, int)
            or integer_value < minimum
        ):
            comparator = ">=" if minimum == 0 else ">"
            bound = 0
            raise ValueError(f"{name} 는 {comparator} {bound} 인 정수여야 함")
    if config.max_size < config.min_size:
        raise ValueError("max_size 는 min_size 이상이어야 함")
    if config.elitism >= config.pop_size:
        raise ValueError("elitism 은 pop_size 보다 작아야 함")
    if isinstance(config.seed, bool) or not isinstance(config.seed, int):
        raise ValueError("seed 는 정수여야 함")

    for name, probability in (
        ("mutation_rate", config.mutation_rate),
        ("immigrant_fraction", config.immigrant_fraction),
    ):
        if (
            isinstance(probability, bool)
            or not isinstance(probability, Real)
            or not math.isfinite(float(probability))
            or not 0.0 <= float(probability) <= 1.0
        ):
            raise ValueError(f"{name} 는 유한한 [0,1] 범위여야 함")

    for name, optional_integer in (
        ("max_evaluations", config.max_evaluations),
        ("patience", config.patience),
    ):
        if optional_integer is not None and (
            isinstance(optional_integer, bool)
            or not isinstance(optional_integer, int)
            or optional_integer <= 0
        ):
            raise ValueError(f"{name} 는 None 또는 > 0 인 정수여야 함")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k 는 > 0 인 정수여야 함")


def _search_space_size(n_ids: int, lo: int, hi: int) -> int:
    return sum(math.comb(n_ids, size) for size in range(lo, hi + 1))


def _random_genome(
    ids: list[str], rng: random.Random, lo: int, hi: int,
) -> Genome:
    size = rng.randint(lo, hi)
    return tuple(sorted(rng.sample(ids, size)))


def _draw_unique_random_genomes(
    ids: list[str],
    rng: random.Random,
    lo: int,
    hi: int,
    count: int,
    *,
    exclude: set[Genome] | None = None,
) -> list[Genome]:
    """Draw distinct genomes without materialising a large combination space."""
    seen = set() if exclude is None else set(exclude)
    total_available = _search_space_size(len(ids), lo, hi) - len(seen)
    target = min(count, max(0, total_available))
    drawn: list[Genome] = []

    # Rejection sampling is fast for the normal GA regime (population << search
    # space). A deterministic combinations fallback guarantees completion in tiny
    # or nearly saturated spaces.
    attempts = 0
    max_attempts = max(100, target * 50)
    while len(drawn) < target and attempts < max_attempts:
        attempts += 1
        genome = _random_genome(ids, rng, lo, hi)
        if genome in seen:
            continue
        seen.add(genome)
        drawn.append(genome)

    if len(drawn) < target:
        for size in range(lo, hi + 1):
            for combo in combinations(ids, size):
                genome = tuple(combo)
                if genome in seen:
                    continue
                seen.add(genome)
                drawn.append(genome)
                if len(drawn) == target:
                    return drawn
    return drawn


def _normalise_fitness(value: float) -> float:
    """Map invalid optimistic scores to the existing failed-score sentinel."""
    score = float(value)
    if math.isnan(score) or score == math.inf:
        return -math.inf
    return score  # Includes -inf, the established "failed evaluation" sentinel.


def genetic_search(
    candidate_ids: Sequence[str],
    fitness_fn: Callable[[Genome], float],
    config: GAConfig | None = None,
    *,
    top_k: int = 10,
) -> GAResult:
    """GA 멤버셋 탐색. fitness_fn(members)→점수(클수록 우수). 결정적(seed)·fitness 캐시."""
    config = config if config is not None else GAConfig()
    _validate_config(config, top_k)

    rng = random.Random(config.seed)
    ids = sorted(set(candidate_ids))
    lo, hi = config.min_size, min(config.max_size, len(ids))
    if len(ids) < lo:
        raise ValueError(f"후보 {len(ids)} < min_size={lo}")

    search_space_size = _search_space_size(len(ids), lo, hi)
    population_target = min(config.pop_size, search_space_size)
    initial_target = population_target
    if config.max_evaluations is not None:
        initial_target = min(initial_target, config.max_evaluations)

    cache: dict[Genome, float] = {}

    def fit(genome: Genome) -> float:
        if genome not in cache:
            # All call sites check the budget first. Keeping the guard here makes
            # the hard cap robust if the implementation is changed later.
            if (
                config.max_evaluations is not None
                and len(cache) >= config.max_evaluations
            ):
                raise RuntimeError("GA evaluation budget exhausted")
            cache[genome] = _normalise_fitness(fitness_fn(genome))
        return cache[genome]

    def ranked(genomes: Sequence[Genome]) -> list[Genome]:
        return sorted(set(genomes), key=lambda genome: (-cache[genome], genome))

    def generation_stats(generation: int, population: Sequence[Genome]) -> GAGenerationStats:
        values = [cache[genome] for genome in set(population)]
        finite_values = [value for value in values if math.isfinite(value)]
        mean_fitness = (
            sum(finite_values) / len(finite_values) if finite_values else -math.inf
        )
        return GAGenerationStats(
            generation=generation,
            best_fitness=max(cache.values()),
            mean_fitness=mean_fitness,
            unique_genomes=len(set(population)),
            evaluations=len(cache),
        )

    population = _draw_unique_random_genomes(
        ids, rng, lo, hi, initial_target,
    )
    for genome in population:
        fit(genome)

    history = [generation_stats(0, population)]
    generations_run = 0
    best_fitness = max(cache.values())
    stagnant_generations = 0
    stop_reason = "generations_complete"

    if len(cache) >= search_space_size:
        stop_reason = "search_space_exhausted"
    elif (
        config.max_evaluations is not None
        and len(cache) >= config.max_evaluations
    ):
        stop_reason = "max_evaluations"
    else:
        for generation in range(1, config.generations + 1):
            current_ranked = ranked(population)
            elite_count = min(config.elitism, population_target)
            next_population = current_ranked[:elite_count]
            next_seen = set(next_population)

            immigrant_count = (
                math.ceil(population_target * float(config.immigrant_fraction))
                if config.immigrant_fraction > 0.0
                else 0
            )
            immigrant_count = min(
                immigrant_count, population_target - len(next_population),
            )
            offspring_target = population_target - immigrant_count

            attempts = 0
            max_attempts = max(100, population_target * 50)
            while (
                len(next_population) < offspring_target
                and attempts < max_attempts
            ):
                attempts += 1
                parent_a = _tournament(
                    current_ranked, fit, rng, config.tournament_k,
                )
                parent_b = _tournament(
                    current_ranked, fit, rng, config.tournament_k,
                )
                child = _crossover(parent_a, parent_b, rng, lo, hi)
                if rng.random() < config.mutation_rate:
                    child = _mutate(child, ids, rng, lo, hi)
                if child in next_seen:
                    continue
                next_seen.add(child)
                next_population.append(child)

            # If crossover cannot supply enough distinct children (for example,
            # parents share a tiny allele pool), fill those slots globally.
            if len(next_population) < offspring_target:
                fillers = _draw_unique_random_genomes(
                    ids,
                    rng,
                    lo,
                    hi,
                    offspring_target - len(next_population),
                    exclude=next_seen,
                )
                next_population.extend(fillers)
                next_seen.update(fillers)

            immigrants = _draw_unique_random_genomes(
                ids,
                rng,
                lo,
                hi,
                population_target - len(next_population),
                exclude=next_seen,
            )
            next_population.extend(immigrants)

            budget_exhausted = False
            for genome in next_population:
                if genome in cache:
                    continue
                if (
                    config.max_evaluations is not None
                    and len(cache) >= config.max_evaluations
                ):
                    budget_exhausted = True
                    break
                fit(genome)
            if budget_exhausted:
                # A hard budget may land in the middle of a generation. Record
                # that partial population so the final history entry still
                # accounts for every expensive fitness call.
                evaluated_population = [
                    genome for genome in next_population if genome in cache
                ]
                population = evaluated_population
                generations_run = generation
                history.append(generation_stats(generation, population))
                stop_reason = "max_evaluations"
                break

            population = next_population
            generations_run = generation
            history.append(generation_stats(generation, population))

            current_best = max(cache.values())
            if current_best > best_fitness:
                best_fitness = current_best
                stagnant_generations = 0
            else:
                stagnant_generations += 1

            if len(cache) >= search_space_size:
                stop_reason = "search_space_exhausted"
                break
            if (
                config.max_evaluations is not None
                and len(cache) >= config.max_evaluations
            ):
                stop_reason = "max_evaluations"
                break
            if (
                config.patience is not None
                and stagnant_generations >= config.patience
            ):
                stop_reason = "patience"
                break

    final = sorted(cache, key=lambda genome: (-cache[genome], genome))
    best = final[0]
    return GAResult(
        best_members=best,
        best_fitness=cache[best],
        top_k=[(genome, cache[genome]) for genome in final[:top_k]],
        generations_run=generations_run,
        evaluations=len(cache),
        stop_reason=stop_reason,
        history=history,
    )
