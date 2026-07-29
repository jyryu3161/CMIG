"""Phase 3.6 — search GA (>100 후보). Plan SC: SC-GA1~GA5. 순수(합성 fitness)·결정적."""

from __future__ import annotations

import math
import random

import pytest

from cmig.core.search_ga import GAConfig, _mutate, genetic_search


def _ids(n: int) -> list[str]:
    return [f"m{i:03d}" for i in range(n)]


def test_ga_finds_high_fitness_members():
    """SC-GA1: 특정 '좋은' 멤버 포함 시 fitness 높게 → GA가 그들을 수렴."""
    good = {"m005", "m010", "m015"}

    def fitness(members):                       # 좋은 멤버 포함 수 = 점수
        return float(len(set(members) & good))

    res = genetic_search(_ids(120), fitness, GAConfig(seed=0, generations=30, pop_size=40))
    assert res.best_fitness >= 2.0              # 최소 2개 good 멤버 수렴(근사)
    assert set(res.best_members) & good


def test_ga_respects_size_bounds():
    """SC-GA2: genome 크기가 [min_size, max_size] 준수."""
    res = genetic_search(_ids(50), lambda m: 1.0, GAConfig(min_size=2, max_size=3, seed=1))
    assert 2 <= len(res.best_members) <= 3
    for g, _ in res.top_k:
        assert 2 <= len(g) <= 3


def test_ga_deterministic():
    """SC-GA3: 동일 seed → history와 stop reason을 포함한 전체 결과가 동일."""
    f = lambda m: float(sum(int(x[1:]) for x in m))   # noqa: E731
    a = genetic_search(_ids(60), f, GAConfig(seed=7))
    b = genetic_search(_ids(60), f, GAConfig(seed=7))
    assert a == b


def test_ga_determinism_does_not_depend_on_candidate_input_order():
    fitness = lambda members: float(sum(int(member[1:]) for member in members))  # noqa: E731
    config = GAConfig(
        pop_size=18,
        generations=8,
        min_size=3,
        max_size=6,
        seed=29,
    )
    ids = _ids(60)

    assert genetic_search(ids, fitness, config) == genetic_search(
        list(reversed(ids)),
        fitness,
        config,
    )


def test_ga_fitness_cache_reduces_evals():
    """SC-GA4: fitness 캐시 → 평가 수 < pop_size×generations(solve 재호출 회피)."""
    calls = {"n": 0}

    def fitness(members):
        calls["n"] += 1
        return float(len(members))

    cfg = GAConfig(pop_size=20, generations=15, seed=2)
    res = genetic_search(_ids(40), fitness, cfg)
    assert res.evaluations == calls["n"]                       # 캐시 = 실 호출
    assert calls["n"] < cfg.pop_size * cfg.generations          # 재계산 회피


def test_ga_warning_present():
    """SC-GA5: 근사 경고 동반(honesty — 전역 최적 미보장)."""
    res = genetic_search(_ids(30), lambda m: 1.0)
    assert "근사" in res.warning and res.generations_run == GAConfig().generations


def test_ga_rejects_too_few_candidates():
    with pytest.raises(ValueError, match="min_size"):
        genetic_search(["a"], lambda m: 1.0, GAConfig(min_size=2))


@pytest.mark.parametrize(
    ("n_candidates", "cardinality"),
    [(20, 1), (20, 3), (8, 8)],
)
def test_ga_supports_exact_arbitrary_cardinality(n_candidates, cardinality):
    """고정 크기는 k=1, 일반 k, 전체 후보 k=N 모두 정확히 보존한다."""
    result = genetic_search(
        _ids(n_candidates),
        lambda members: float(sum(int(member[1:]) for member in members)),
        GAConfig(
            min_size=cardinality,
            max_size=cardinality,
            pop_size=12,
            generations=5,
            elitism=1,
            mutation_rate=1.0,
            seed=13,
        ),
        top_k=20,
    )

    assert len(result.best_members) == cardinality
    assert all(len(genome) == cardinality for genome, _score in result.top_k)
    assert all(tuple(sorted(genome)) == genome for genome, _score in result.top_k)
    if cardinality == n_candidates:
        assert result.stop_reason == "search_space_exhausted"
        assert result.evaluations == 1


def test_exact_k_mutation_swaps_against_global_candidate_pool():
    """exact-k mutation은 no-op add/remove가 아니라 전역 후보를 넣는 1-swap이다."""
    initial = ("m000", "m001", "m002")
    mutated = _mutate(initial, _ids(20), random.Random(4), 3, 3)

    assert len(mutated) == 3
    assert len(set(initial) - set(mutated)) == 1
    assert len(set(mutated) - set(initial)) == 1
    assert tuple(sorted(mutated)) == mutated


def test_variable_range_mutation_can_add_remove_and_swap():
    """가변 크기에서는 세 연산이 모두 reachable하고 항상 경계를 지킨다."""
    original = ("m005", "m006")
    outcomes = [
        _mutate(original, _ids(12), random.Random(seed), 1, 3)
        for seed in range(100)
    ]

    assert any(len(genome) == 1 for genome in outcomes)  # remove
    assert any(len(genome) == 3 for genome in outcomes)  # add
    assert any(
        len(genome) == 2 and len(set(genome) ^ set(original)) == 2
        for genome in outcomes
    )  # swap
    assert all(1 <= len(genome) <= 3 for genome in outcomes)


def test_exact_k_search_reaches_member_outside_initial_allele_pool():
    """부모 union 밖의 멤버도 전역 swap mutation으로 실제 평가된다."""
    evaluated: list[tuple[str, ...]] = []

    def fitness(members):
        evaluated.append(members)
        return float("m099" in members)

    config = GAConfig(
        pop_size=6,
        generations=5,
        min_size=3,
        max_size=3,
        mutation_rate=1.0,
        immigrant_fraction=0.0,
        elitism=1,
        seed=9,
    )
    genetic_search(_ids(100), fitness, config)

    initial_alleles = set().union(*map(set, evaluated[: config.pop_size]))
    later_alleles = set().union(*map(set, evaluated[config.pop_size :]))
    assert later_alleles - initial_alleles


def test_population_is_unique_when_search_space_is_large_enough():
    """초기 population을 채울 조합이 충분하면 중복 평가 없이 모두 고유하다."""
    calls: list[tuple[str, ...]] = []
    config = GAConfig(pop_size=20, generations=0, min_size=3, max_size=3, seed=5)
    result = genetic_search(
        _ids(30),
        lambda members: calls.append(members) or 0.0,
        config,
    )

    assert len(calls) == config.pop_size
    assert len(set(calls)) == config.pop_size
    assert result.history[0].unique_genomes == config.pop_size


def test_random_immigrants_add_global_diversity_without_mutation():
    """mutation을 꺼도 immigrant는 부모 allele pool 밖의 후보를 평가할 수 있다."""
    evaluated: list[tuple[str, ...]] = []

    def fitness(members):
        evaluated.append(members)
        return 0.0

    config = GAConfig(
        pop_size=8,
        generations=2,
        min_size=2,
        max_size=2,
        mutation_rate=0.0,
        immigrant_fraction=0.5,
        elitism=1,
        seed=3,
    )
    genetic_search(_ids(100), fitness, config)

    initial_alleles = set().union(*map(set, evaluated[: config.pop_size]))
    later_alleles = set().union(*map(set, evaluated[config.pop_size :]))
    assert later_alleles - initial_alleles


def test_max_evaluations_is_a_hard_cap_even_below_population_size():
    calls = {"count": 0}

    def fitness(members):
        calls["count"] += 1
        return float(len(members))

    result = genetic_search(
        _ids(50),
        fitness,
        GAConfig(pop_size=20, generations=100, max_evaluations=3, seed=2),
    )

    assert calls["count"] == result.evaluations == 3
    assert result.stop_reason == "max_evaluations"
    assert result.generations_run == 0
    assert [stats.generation for stats in result.history] == [0]


def test_mid_generation_budget_stop_is_reflected_in_history():
    result = genetic_search(
        _ids(80),
        lambda members: float(sum(int(member[1:]) for member in members)),
        GAConfig(
            pop_size=8,
            generations=20,
            max_evaluations=9,
            min_size=3,
            max_size=3,
            elitism=1,
            seed=17,
        ),
    )

    assert result.stop_reason == "max_evaluations"
    assert result.generations_run == 1
    assert result.evaluations == 9
    assert result.history[-1].generation == result.generations_run
    assert result.history[-1].evaluations == result.evaluations


@pytest.mark.parametrize("budget", [7, 8, 9])
def test_evaluation_budget_edges_around_population_size(budget):
    calls = {"count": 0}

    def fitness(members):
        calls["count"] += 1
        return float(sum(int(member[1:]) for member in members))

    result = genetic_search(
        _ids(80),
        fitness,
        GAConfig(
            pop_size=8,
            generations=20,
            max_evaluations=budget,
            min_size=3,
            max_size=3,
            elitism=1,
            seed=17,
        ),
    )

    assert calls["count"] == result.evaluations == budget
    assert result.stop_reason == "max_evaluations"
    assert result.history[-1].evaluations == budget


def test_patience_stops_after_requested_stagnant_generations():
    result = genetic_search(
        _ids(50),
        lambda members: 1.0,
        GAConfig(pop_size=12, generations=100, patience=2, seed=11),
    )

    assert result.stop_reason == "patience"
    assert result.generations_run == 2
    assert [stats.generation for stats in result.history] == [0, 1, 2]
    assert [stats.evaluations for stats in result.history] == sorted(
        stats.evaluations for stats in result.history
    )


def test_invalid_nonfinite_fitness_cannot_outrank_finite_and_minus_inf_is_preserved():
    scores = {
        "m000": math.nan,
        "m001": math.inf,
        "m002": -math.inf,
        "m003": 4.0,
    }
    result = genetic_search(
        list(scores),
        lambda members: scores[members[0]],
        GAConfig(
            pop_size=4,
            generations=0,
            min_size=1,
            max_size=1,
            elitism=1,
            seed=0,
        ),
        top_k=4,
    )
    ranked = dict(result.top_k)

    assert result.best_members == ("m003",)
    assert result.best_fitness == 4.0
    assert ranked[("m000",)] == -math.inf
    assert ranked[("m001",)] == -math.inf
    assert ranked[("m002",)] == -math.inf
    assert not math.isnan(result.history[0].mean_fitness)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (GAConfig(pop_size=0), "pop_size"),
        (GAConfig(generations=-1), "generations"),
        (GAConfig(min_size=0), "min_size"),
        (GAConfig(min_size=3, max_size=2), "max_size"),
        (GAConfig(mutation_rate=1.5), "mutation_rate"),
        (GAConfig(tournament_k=0), "tournament_k"),
        (GAConfig(elitism=-1), "elitism"),
        (GAConfig(pop_size=2, elitism=2), "elitism"),
        (GAConfig(immigrant_fraction=-0.1), "immigrant_fraction"),
        (GAConfig(immigrant_fraction=math.nan), "immigrant_fraction"),
        (GAConfig(max_evaluations=0), "max_evaluations"),
        (GAConfig(patience=0), "patience"),
        (GAConfig(seed=True), "seed"),
    ],
)
def test_ga_rejects_invalid_config(config, message):
    with pytest.raises(ValueError, match=message):
        genetic_search(_ids(10), lambda m: 1.0, config)


def test_ga_rejects_invalid_top_k():
    with pytest.raises(ValueError, match="top_k"):
        genetic_search(_ids(10), lambda members: 1.0, top_k=0)
