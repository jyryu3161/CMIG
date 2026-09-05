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
from dataclasses import asdict, dataclass, field
from itertools import combinations
from numbers import Real
from typing import Any

GA_POLICY_VERSION = "set_ga_v2"

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
    tie_tolerance: float = 1e-9
    restart_after: int | None = None
    local_search_fraction: float = 0.0
    preserve_common: bool = False


@dataclass(frozen=True)
class GAGenerationStats:
    """한 세대가 끝났을 때의 결정적 수렴 진단."""

    generation: int
    best_fitness: float
    mean_fitness: float
    unique_genomes: int
    evaluations: int
    member_coverage: float = 0.0
    member_entropy: float = 0.0
    mean_jaccard_distance: float = 0.0
    jaccard_pairs: int = 0
    feasible_fraction: float = 0.0
    new_evaluation_fraction: float = 0.0
    size_counts: dict[int, int] = field(default_factory=dict)
    restarted: bool = False


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
    *, tolerance: float = 1e-9,
) -> Genome:
    contenders = rng.sample(pop, min(k, len(pop)))
    best = max(fit(genome) for genome in contenders)
    tied = [genome for genome in contenders if fit(genome) == best or math.isclose(
        fit(genome), best, rel_tol=tolerance, abs_tol=tolerance,
    )]
    return rng.choice(tied)


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
        ("local_search_fraction", config.local_search_fraction),
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
        ("restart_after", config.restart_after),
    ):
        if optional_integer is not None and (
            isinstance(optional_integer, bool)
            or not isinstance(optional_integer, int)
            or optional_integer <= 0
        ):
            raise ValueError(f"{name} 는 None 또는 > 0 인 정수여야 함")
    if not math.isfinite(config.tie_tolerance) or config.tie_tolerance < 0:
        raise ValueError("tie_tolerance must be finite and non-negative")
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
    checkpoint_state: dict[str, Any] | None = None,
    on_checkpoint: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    batch_fitness_fn: Callable[[list[Genome]], list[float]] | None = None,
    batch_size: int = 1,
    rank_population: Callable[[list[Genome]], list[Genome]] | None = None,
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
    boundary: dict[str, Any] = {}

    def check() -> None:
        if cancel_check is not None:
            cancel_check()

    def persist() -> None:
        if on_checkpoint is not None:
            state = {
                **boundary, "policy": GA_POLICY_VERSION, "ids": ids,
                "config": asdict(config),
                "cache": [[list(genome), value if math.isfinite(value) else None]
                          for genome, value in cache.items()],
            }
            on_checkpoint(state)

    def evaluate_population(genomes: Sequence[Genome]) -> bool:
        unseen = list(dict.fromkeys(genome for genome in genomes if genome not in cache))
        remaining = (config.max_evaluations - len(cache)
                     if config.max_evaluations is not None else len(unseen))
        selected = unseen[:remaining]
        for start in range(0, len(selected), max(1, batch_size)):
            check()
            batch = selected[start:start + max(1, batch_size)]
            if batch_fitness_fn is None:
                for genome in batch:
                    fit(genome)
            else:
                values = batch_fitness_fn(batch)
                if len(values) != len(batch):
                    raise ValueError("batch fitness returned the wrong number of scores")
                for genome, value in zip(batch, values, strict=True):
                    cache[genome] = _normalise_fitness(value)
                    persist()
                    if on_progress is not None:
                        on_progress(len(cache), config.max_evaluations or search_space_size)
        return len(selected) < len(unseen)

    def fit(genome: Genome) -> float:
        if genome not in cache:
            check()
            # All call sites check the budget first. Keeping the guard here makes
            # the hard cap robust if the implementation is changed later.
            if (
                config.max_evaluations is not None
                and len(cache) >= config.max_evaluations
            ):
                raise RuntimeError("GA evaluation budget exhausted")
            cache[genome] = _normalise_fitness(fitness_fn(genome))
            persist()
            if on_progress is not None:
                on_progress(len(cache), config.max_evaluations or search_space_size)
        return cache[genome]

    def ranked(genomes: Sequence[Genome]) -> list[Genome]:
        # Seeded ties for survival too; names remain only a final reporting order.
        shuffled = sorted(set(genomes))
        rng.shuffle(shuffled)
        if rank_population is not None:
            return rank_population(shuffled)
        return sorted(shuffled, key=lambda genome: -cache[genome])

    def generation_stats(
        generation: int, population: Sequence[Genome], *, restarted: bool = False,
    ) -> GAGenerationStats:
        from collections import Counter

        genomes = sorted(set(population))
        values = [cache[genome] for genome in genomes]
        finite_values = [value for value in values if math.isfinite(value)]
        mean_fitness = (
            math.fsum(value / len(finite_values) for value in finite_values)
            if finite_values else -math.inf
        )
        counts = Counter(member for genome in genomes for member in genome)
        total_members = sum(counts.values())
        # Bound diagnostic cost independently of the requested population size.
        # Use a separate RNG so telemetry cannot alter genetic operators.
        if math.comb(len(genomes), 2) <= 2048:
            pairs = list(combinations(genomes, 2))
        else:
            probe_rng = random.Random(0)
            sampled: set[tuple[int, ...]] = set()
            while len(sampled) < 2048:
                sampled.add(tuple(sorted(probe_rng.sample(range(len(genomes)), 2))))
            pairs = [(genomes[a], genomes[b]) for a, b in sorted(sampled)]
        distance = math.fsum(
            1 - len(set(a) & set(b)) / len(set(a) | set(b)) for a, b in pairs
        ) / len(pairs) if pairs else 0.0
        previous_evaluations = history[-1].evaluations if history else 0
        return GAGenerationStats(
            generation=generation,
            best_fitness=max(cache.values()),
            mean_fitness=mean_fitness,
            unique_genomes=len(set(population)),
            evaluations=len(cache),
            member_coverage=len(counts) / len(ids),
            member_entropy=-math.fsum(
                (count / total_members) * math.log(count / total_members)
                for count in counts.values()
            ) / math.log(len(ids)) if len(ids) > 1 else 0.0,
            mean_jaccard_distance=distance,
            jaccard_pairs=len(pairs),
            feasible_fraction=len(finite_values) / len(genomes),
            new_evaluation_fraction=(len(cache) - previous_evaluations) / len(genomes),
            size_counts=dict(sorted(Counter(map(len, genomes)).items())),
            restarted=restarted,
        )

    history: list[GAGenerationStats] = []
    generations_run = 0
    best_fitness = -math.inf
    stagnant_generations = 0
    stop_reason = "generations_complete"
    start_generation = 0

    def tuple_tree(value: Any) -> Any:
        return tuple(tuple_tree(item) for item in value) if isinstance(value, list) else value

    if checkpoint_state is not None:
        import json

        if (checkpoint_state.get("policy") != GA_POLICY_VERSION
                or checkpoint_state.get("ids") != ids
                or json.dumps(checkpoint_state.get("config"), sort_keys=True)
                != json.dumps(asdict(config), sort_keys=True)):
            raise ValueError("GA checkpoint configuration/policy mismatch")
        cache = {tuple(genome): (-math.inf if value is None else float(value))
                 for genome, value in checkpoint_state["cache"]}
        population = [tuple(genome) for genome in checkpoint_state["population"]]
        rng.setstate(tuple_tree(checkpoint_state["rng_state"]))
        start_generation = int(checkpoint_state["next_generation"])
        stagnant_generations = int(checkpoint_state["stagnant_generations"])
        value = checkpoint_state["best_fitness"]
        best_fitness = -math.inf if value is None else float(value)
        for raw in checkpoint_state["history"]:
            item = dict(raw)
            for name in ("best_fitness", "mean_fitness"):
                if item[name] is None:
                    item[name] = -math.inf
            item["size_counts"] = {int(k): v for k, v in item.get("size_counts", {}).items()}
            history.append(GAGenerationStats(**item))
        generations_run = max(0, start_generation - 1)
    else:
        population = _draw_unique_random_genomes(ids, rng, lo, hi, initial_target)

    def set_boundary(next_generation: int) -> None:
        nonlocal boundary
        stats = [asdict(item) for item in history]
        for item in stats:
            for name in ("best_fitness", "mean_fitness"):
                if not math.isfinite(item[name]):
                    item[name] = None
        boundary = {
            "population": [list(genome) for genome in population],
            "rng_state": rng.getstate(), "next_generation": next_generation,
            "stagnant_generations": stagnant_generations,
            "best_fitness": best_fitness if math.isfinite(best_fitness) else None,
            "history": stats,
        }

    set_boundary(start_generation)
    if start_generation == 0:
        evaluate_population(population)
        history = [generation_stats(0, population)]
        best_fitness = max(cache.values())
        start_generation = 1
        set_boundary(1)
        persist()

    replay_partial = checkpoint_state is not None and len(cache) > history[-1].evaluations
    if len(cache) >= search_space_size and not replay_partial:
        stop_reason = "search_space_exhausted"
    elif (
        config.max_evaluations is not None
        and len(cache) >= config.max_evaluations
        and not replay_partial
    ):
        stop_reason = "max_evaluations"
    else:
        for generation in range(start_generation, config.generations + 1):
            check()
            set_boundary(generation)
            persist()
            current_ranked = ranked(population)
            ordering = {genome: index for index, genome in enumerate(current_ranked)}
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
            restarted = (config.restart_after is not None and stagnant_generations > 0
                         and stagnant_generations % config.restart_after == 0)
            if restarted:
                offspring_target = len(next_population)

            attempts = 0
            max_attempts = max(100, population_target * 50)
            while (
                len(next_population) < offspring_target
                and attempts < max_attempts
            ):
                attempts += 1
                def parent(ranked_genomes: list[Genome], order: dict[Genome, int]) -> Genome:
                    if rank_population is not None:
                        return min(rng.sample(ranked_genomes, min(config.tournament_k,
                                   len(ranked_genomes))), key=order.__getitem__)
                    return _tournament(ranked_genomes, fit, rng, config.tournament_k,
                                       tolerance=config.tie_tolerance)
                parent_a = parent(current_ranked, ordering)
                parent_b = parent(current_ranked, ordering)
                child = _crossover(parent_a, parent_b, rng, lo, hi)
                if config.preserve_common:
                    common = set(parent_a) & set(parent_b)
                    size = min(hi, max(lo, len(common), len(child)))
                    pool = sorted((set(parent_a) | set(parent_b)) - common)
                    child = tuple(sorted(common | set(rng.sample(pool, size - len(common)))))
                if rng.random() < config.local_search_fraction:
                    child = _mutate(current_ranked[0], ids, rng, lo, hi)
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

            budget_exhausted = evaluate_population(next_population)
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

            population = (ranked(population + next_population)[:population_target]
                          if rank_population is not None else next_population)
            generations_run = generation
            history.append(generation_stats(generation, population, restarted=restarted))

            current_best = max(cache.values())
            if current_best > best_fitness and not math.isclose(
                current_best, best_fitness, rel_tol=config.tie_tolerance,
                abs_tol=config.tie_tolerance,
            ):
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
