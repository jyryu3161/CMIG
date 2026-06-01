"""Consortium Search — 유전 알고리즘 (>100 후보) (Roadmap Phase 3.6, §14).

Design Ref: §14 (GA strategy) / cmig-search-ga.design. Plan SC: SC-GA1~GA5.

대규모 후보(>100)에서 exhaustive 불가 → GA로 근사 탐색. genome=멤버셋(size bounds), fitness=
주입(target-max score), tournament 선택·union crossover·add/remove mutation·elitism. **결정적**
(seed) + fitness 캐시(solve 재호출 회피). [honesty] 근사(전역 최적 미보장) — 결과에 경고 동반.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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


@dataclass(frozen=True)
class GAResult:
    best_members: Genome
    best_fitness: float
    top_k: list[tuple[Genome, float]]
    generations_run: int
    evaluations: int                    # 실제 fitness 호출 수(캐시 효과 가시화)
    warning: str = "GA 근사 — 전역 최적 미보장(non-exhaustive)"


def _tournament(
    pop: list[Genome], fit: Callable[[Genome], float], rng: random.Random, k: int,
) -> Genome:
    contenders = rng.sample(pop, min(k, len(pop)))
    return max(contenders, key=fit)


def _crossover(a: Genome, b: Genome, rng: random.Random, lo: int, hi: int) -> Genome:
    pool = sorted(set(a) | set(b))
    size = rng.randint(lo, min(hi, len(pool)))
    return tuple(sorted(rng.sample(pool, size)))


def _mutate(g: Genome, ids: list[str], rng: random.Random, lo: int, hi: int) -> Genome:
    members = set(g)
    if rng.random() < 0.5 and len(members) > lo:        # remove
        members.discard(rng.choice(sorted(members)))
    else:                                               # add
        avail = [x for x in ids if x not in members]
        if avail and len(members) < hi:
            members.add(rng.choice(avail))
    return tuple(sorted(members))


def genetic_search(
    candidate_ids: Sequence[str],
    fitness_fn: Callable[[Genome], float],
    config: GAConfig | None = None,
    *,
    top_k: int = 10,
) -> GAResult:
    """GA 멤버셋 탐색. fitness_fn(members)→점수(클수록 우수). 결정적(seed)·fitness 캐시."""
    config = config if config is not None else GAConfig()
    if config.pop_size <= 0:
        raise ValueError("pop_size 는 > 0 이어야 함")
    if config.generations < 0:
        raise ValueError("generations 는 >= 0 이어야 함")
    if config.min_size <= 0:
        raise ValueError("min_size 는 > 0 이어야 함")
    if config.max_size < config.min_size:
        raise ValueError("max_size 는 min_size 이상이어야 함")
    if not (0.0 <= config.mutation_rate <= 1.0):
        raise ValueError("mutation_rate 는 [0,1] 범위여야 함")
    if config.tournament_k <= 0:
        raise ValueError("tournament_k 는 > 0 이어야 함")
    if config.elitism < 0:
        raise ValueError("elitism 은 >= 0 이어야 함")
    rng = random.Random(config.seed)
    ids = sorted(set(candidate_ids))
    lo, hi = config.min_size, min(config.max_size, len(ids))
    if len(ids) < lo:
        raise ValueError(f"후보 {len(ids)} < min_size={lo}")

    cache: dict[Genome, float] = {}

    def fit(g: Genome) -> float:
        if g not in cache:
            cache[g] = fitness_fn(g)
        return cache[g]

    def random_genome() -> Genome:
        size = rng.randint(lo, hi)
        return tuple(sorted(rng.sample(ids, size)))

    pop = [random_genome() for _ in range(config.pop_size)]
    for _ in range(config.generations):
        ranked = sorted(pop, key=fit, reverse=True)
        nxt: list[Genome] = ranked[: config.elitism]    # elitism
        while len(nxt) < config.pop_size:
            p1 = _tournament(ranked, fit, rng, config.tournament_k)
            p2 = _tournament(ranked, fit, rng, config.tournament_k)
            child = _crossover(p1, p2, rng, lo, hi)
            if rng.random() < config.mutation_rate:
                child = _mutate(child, ids, rng, lo, hi)
            nxt.append(child)
        pop = nxt

    final = sorted(set(pop) | set(cache), key=fit, reverse=True)
    best = final[0]
    return GAResult(
        best_members=best, best_fitness=fit(best),
        top_k=[(g, fit(g)) for g in final[:top_k]],
        generations_run=config.generations, evaluations=len(cache),
    )
