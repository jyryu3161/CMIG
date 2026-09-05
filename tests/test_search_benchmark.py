"""License-free algorithm-quality and budget regression gates."""

import math

import pytest

from cmig.core.search_benchmark import benchmark_search, synthetic_landscapes


@pytest.mark.parametrize(
    "landscape",
    ["additive", "hidden_synergy", "sparse_synergy", "competition", "infeasible_region"],
)
def test_benchmark_compares_unique_budgets_and_reports_truth(landscape):
    ids = [f"s{index:02}" for index in range(8)]
    report = benchmark_search(
        ids,
        synthetic_landscapes(ids)[landscape],
        min_size=3,
        max_size=3,
        budget=30,
        seeds=[0, 1],
        top_k=3,
    )
    assert len(report["trials"]) == 8
    for trial in report["trials"]:
        assert trial["evaluations"] == 30
        assert trial["budget_filled"]
        assert trial["regret"] >= 0
        assert 0 <= trial["feasible_fraction"] <= 1
        assert 0 <= trial["tie_inclusive_top_k_recall"] <= 1
    assert len(report["summary"]) == 4


def test_benchmark_full_budget_reaches_oracle_for_all_methods():
    ids = [str(index) for index in range(6)]
    report = benchmark_search(
        ids,
        lambda genome: float(sum(map(int, genome))),
        min_size=2,
        max_size=2,
        budget=15,
        seeds=[7],
    )
    assert all(trial["hit_optimum"] and trial["regret"] == 0 for trial in report["trials"])


def test_benchmark_rejects_unbounded_or_nonviable_oracles():
    with pytest.raises(ValueError, match="guard"):
        benchmark_search(
            list("abcdef"), lambda _: 1, min_size=3, max_size=3, budget=10, exhaustive_max=10
        )
    with pytest.raises(ValueError, match="no feasible"):
        benchmark_search(list("abc"), lambda _: -math.inf, min_size=2, max_size=2, budget=2)
