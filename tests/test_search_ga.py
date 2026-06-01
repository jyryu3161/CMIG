"""Phase 3.6 — search GA (>100 후보). Plan SC: SC-GA1~GA5. 순수(합성 fitness)·결정적."""

from __future__ import annotations

import pytest

from cmig.core.search_ga import GAConfig, genetic_search


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
    """SC-GA3: 동일 seed → 동일 결과(재현)."""
    f = lambda m: float(sum(int(x[1:]) for x in m))   # noqa: E731
    a = genetic_search(_ids(60), f, GAConfig(seed=7))
    b = genetic_search(_ids(60), f, GAConfig(seed=7))
    assert a.best_members == b.best_members and a.best_fitness == b.best_fitness


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
    ("config", "message"),
    [
        (GAConfig(pop_size=0), "pop_size"),
        (GAConfig(generations=-1), "generations"),
        (GAConfig(min_size=0), "min_size"),
        (GAConfig(min_size=3, max_size=2), "max_size"),
        (GAConfig(mutation_rate=1.5), "mutation_rate"),
        (GAConfig(tournament_k=0), "tournament_k"),
        (GAConfig(elitism=-1), "elitism"),
    ],
)
def test_ga_rejects_invalid_config(config, message):
    with pytest.raises(ValueError, match=message):
        genetic_search(_ids(10), lambda m: 1.0, config)
