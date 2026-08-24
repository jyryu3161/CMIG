"""Pure-Python regression coverage for model-pool product search accounting."""

from __future__ import annotations

import itertools
import math
from collections import Counter

import pytest

from cmig.core.search_product import (
    PoolRank,
    PoolSearchResult,
    _unrank_combination,
    choose_strategy,
    count_candidate_combinations,
    sample_candidate_combinations,
)


@pytest.mark.parametrize(
    ("n_ids", "min_size", "max_size", "expected"),
    [
        (0, 1, 3, 0),
        (4, 2, 2, 6),
        (5, 2, 4, 25),
        (4, 4, 9, 1),
        (4, 5, 9, 0),
    ],
)
def test_count_candidate_combinations_matches_exact_combinatorics(
    n_ids, min_size, max_size, expected
) -> None:
    ids = [f"m{index}" for index in range(n_ids)]

    assert count_candidate_combinations(ids, min_size, max_size) == expected


def test_sample_candidate_combinations_is_seeded_sorted_and_unique() -> None:
    ids = ["d", "b", "a", "c", "e"]

    first = sample_candidate_combinations(ids, 2, 3, n_samples=7, seed=91)
    second = sample_candidate_combinations(ids, 2, 3, n_samples=7, seed=91)

    assert first == second
    assert len(first) == len(set(first)) == 7
    assert all(tuple(sorted(members)) == members for members in first)
    assert sample_candidate_combinations(ids, 2, 3, n_samples=7, seed=92) != first


def test_small_uniform_sampler_reaches_every_combination_without_skew() -> None:
    ids = ["d", "b", "a", "c"]
    expected = set(itertools.combinations(sorted(ids), 2))
    counts = Counter(
        sample_candidate_combinations(ids, 2, 2, n_samples=1, seed=seed)[0]
        for seed in range(6000)
    )

    assert set(counts) == expected
    assert all(900 <= count <= 1100 for count in counts.values())
    assert set(sample_candidate_combinations(ids, 2, 2, n_samples=99, seed=7)) == expected


def test_sample_candidate_combinations_rejects_nonpositive_sample_size() -> None:
    with pytest.raises(ValueError, match="--n-samples must be > 0"):
        sample_candidate_combinations(["a", "b"], 1, 2, n_samples=0, seed=0)


def test_unrank_combination_matches_lexicographic_order_and_edges() -> None:
    ids = ["a", "b", "c", "d"]
    expected = list(itertools.combinations(ids, 2))

    assert [_unrank_combination(ids, 2, rank) for rank in range(6)] == expected
    assert _unrank_combination(ids, 0, 0) == ()
    assert _unrank_combination(ids, len(ids), 0) == tuple(ids)
    with pytest.raises(ValueError, match="combination rank out of range"):
        _unrank_combination(ids, 2, -1)
    with pytest.raises(ValueError, match="combination rank out of range"):
        _unrank_combination(ids, 2, math.comb(len(ids), 2))
    with pytest.raises(ValueError, match="combination rank out of range"):
        _unrank_combination(ids, len(ids) + 1, 0)


def test_choose_strategy_pins_auto_threshold_and_explicit_requests() -> None:
    assert choose_strategy(99, "auto", exhaustive_max=100) == "exhaustive"
    assert choose_strategy(100, "auto", exhaustive_max=100) == "exhaustive"
    assert choose_strategy(101, "auto", exhaustive_max=100) == "ga"
    assert choose_strategy(10_000, "random", exhaustive_max=1) == "random"
    assert choose_strategy(0, "exhaustive", exhaustive_max=0) == "exhaustive"


def test_pool_search_result_accounting_and_robustness_failures() -> None:
    ranks = [
        PoolRank(1, ("a", "b"), 3.0, 3.0, 0.5, "optimal", robustness_status=None),
        PoolRank(2, ("a", "c"), 2.0, 2.0, 0.4, "optimal", robustness_status="ok"),
        PoolRank(
            3,
            ("b", "c"),
            1.0,
            1.0,
            0.3,
            "optimal",
            robustness_status="solver_failed",
        ),
    ]
    unevaluated = [
        PoolRank(0, ("a", "d"), float("-inf"), 0.0, 0.0, "failed")
    ]
    result = PoolSearchResult(
        target="but",
        target_exchange="EX_but_m",
        direction="max_secretion",
        strategy="exhaustive",
        n_pool_members=4,
        n_candidates_total=6,
        n_candidates_evaluated=4,
        ranks=ranks,
        warnings=[],
        unevaluated=unevaluated,
    )

    assert result.n_candidates_ranked + result.n_candidates_failed == (
        result.n_candidates_evaluated
    )
    assert result.n_candidates_ranked == 3
    assert result.n_candidates_failed == 1
    assert result.n_robustness_failed == 1
