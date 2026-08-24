from __future__ import annotations

import itertools
import json
import math
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from cmig.core.search import Direction
from cmig.core.search_ga import GAConfig
from cmig.core.search_product import (
    MultiTargetConfig,
    PoolRank,
    SearchConfig,
    choose_strategy,
    count_candidate_combinations,
    sample_candidate_combinations,
    search_model_pool,
    search_model_pool_multi,
)


class _Taxonomy:
    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    def __getitem__(self, key: str) -> list[str]:
        assert key == "id"
        return self.ids


class _Column(list[str]):
    def astype(self, _kind: type[str]) -> _Column:
        return self

    def isin(self, members: tuple[str, ...]) -> list[bool]:
        return [value in members for value in self]


class _FilterableTaxonomy(_Taxonomy):
    def __getitem__(self, key: Any) -> Any:
        if key == "id":
            return _Column(self.ids)
        assert isinstance(key, list) and all(isinstance(value, bool) for value in key)
        return self

    def copy(self) -> _FilterableTaxonomy:
        return self


def _install_fake_evaluator(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failed: set[tuple[str, ...]] | None = None,
) -> list[tuple[tuple[str, ...], bool]]:
    from cmig.core import search_product

    failed = failed or set()
    calls: list[tuple[tuple[str, ...], bool]] = []

    def fake_evaluate(
        _engine: Any,
        _taxonomy: Any,
        members: tuple[str, ...],
        _spec: Any,
        **kwargs: Any,
    ) -> PoolRank:
        calls.append((members, kwargs["robustness_fva"]))
        if members in failed:
            return PoolRank(
                rank=0,
                members=members,
                score=float("-inf"),
                target_flux=0.0,
                community_growth=0.0,
                status="failed",
                diagnostic="synthetic failure",
            )
        score = float(sum(int(member[1:]) for member in members) + 1)
        return PoolRank(
            rank=0,
            members=members,
            score=score,
            target_flux=score,
            community_growth=0.5,
            status="optimal",
        )

    monkeypatch.setattr(search_product, "_evaluate_members", fake_evaluate)
    return calls


def _forbid_materialized_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    from cmig.core import search_product

    def fail(*_args: Any, **_kwargs: Any) -> list[tuple[str, ...]]:
        raise AssertionError("single-target scalable search materialized every combination")

    monkeypatch.setattr(search_product, "candidate_combinations", fail)


def test_combination_count_uses_arbitrary_exact_and_variable_k() -> None:
    ids = [f"m{i:03d}" for i in range(200)]

    assert count_candidate_combinations(ids, 3, 3) == math.comb(200, 3)
    assert count_candidate_combinations(ids, 7, 7) == math.comb(200, 7)
    assert count_candidate_combinations(ids, 2, 5) == sum(
        math.comb(200, size) for size in range(2, 6)
    )
    assert count_candidate_combinations(ids[:4], 5, 8) == 0


def test_auto_strategy_boundary_is_explicit() -> None:
    assert choose_strategy(100, "auto", exhaustive_max=100) == "exhaustive"
    assert choose_strategy(101, "auto", exhaustive_max=100) == "ga"


def test_large_multi_target_guard_runs_before_candidate_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [f"m{i:03d}" for i in range(200)]
    _forbid_materialized_candidates(monkeypatch)
    config = MultiTargetConfig(
        targets=["ac", "but"],
        directions={
            "ac": Direction.MAX_SECRETION,
            "but": Direction.MAX_SECRETION,
        },
        weights={"ac": 1.0, "but": 1.0},
        min_size=3,
        max_size=3,
        exhaustive_max=100,
    )

    with pytest.raises(ValueError, match=r"1313400 candidates > exhaustive_max=100"):
        search_model_pool_multi(object(), _Taxonomy(ids), config)


def test_random_sampler_covers_the_mixed_size_universe_without_duplicates() -> None:
    ids = [f"m{i}" for i in range(6)]
    expected = {
        combo
        for size in range(2, 5)
        for combo in itertools.combinations(sorted(ids), size)
    }

    sampled = sample_candidate_combinations(
        ids,
        2,
        4,
        n_samples=len(expected),
        seed=19,
    )

    assert set(sampled) == expected
    assert len(sampled) == len(set(sampled))
    assert {len(members) for members in sampled} == {2, 3, 4}


def test_large_random_search_is_deterministic_without_candidate_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [f"m{i:03d}" for i in range(200)]
    taxonomy = _Taxonomy(ids)
    _forbid_materialized_candidates(monkeypatch)
    _install_fake_evaluator(monkeypatch)
    config = SearchConfig(
        target="but",
        min_size=6,
        max_size=6,
        strategy="random",
        n_samples=25,
        seed=314,
        top_k=25,
    )

    first = search_model_pool(object(), taxonomy, config)
    second = search_model_pool(object(), taxonomy, config)

    first_members = [row.members for row in first.ranks]
    assert first_members == [row.members for row in second.ranks]
    assert len(first_members) == len(set(first_members)) == 25
    assert all(len(members) == 6 for members in first_members)
    assert first.n_candidates_total == math.comb(200, 6)
    assert first.n_candidates_evaluated == 25
    assert first.strategy == "random"


def test_single_target_exhaustive_path_iterates_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = [f"m{i}" for i in range(6)]
    _forbid_materialized_candidates(monkeypatch)
    _install_fake_evaluator(monkeypatch)

    result = search_model_pool(
        object(),
        _Taxonomy(ids),
        SearchConfig(
            target="but",
            min_size=2,
            max_size=3,
            strategy="exhaustive",
            top_k=2,
        ),
    )

    assert result.n_candidates_total == math.comb(6, 2) + math.comb(6, 3)
    assert result.n_candidates_evaluated == result.n_candidates_total


def test_large_auto_search_routes_to_ga_and_reports_every_fitness_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cmig.core import search_ga

    ids = [f"m{i:03d}" for i in range(200)]
    taxonomy = _Taxonomy(ids)
    genomes = [
        tuple(ids[0:7]),
        tuple(ids[1:8]),
        tuple(ids[2:9]),
        tuple(ids[3:10]),
    ]
    failed = {genomes[1], genomes[3]}
    calls = _install_fake_evaluator(monkeypatch, failed=failed)
    _forbid_materialized_candidates(monkeypatch)
    captured: dict[str, Any] = {}

    def fake_genetic_search(
        candidate_ids: list[str],
        fitness_fn: Any,
        config: GAConfig,
        *,
        top_k: int,
    ) -> SimpleNamespace:
        captured.update(ids=candidate_ids, config=config, top_k=top_k)
        scores = [fitness_fn(genome) for genome in genomes]
        return SimpleNamespace(
            best_members=genomes[0],
            best_fitness=scores[0],
            top_k=[(genomes[0], scores[0])],
            generations_run=3,
            evaluations=len(genomes),
            stop_reason="patience",
            history=[
                {
                    "generation": 0,
                    "evaluations": len(genomes),
                    "best_fitness": float("-inf"),
                    "mean_fitness": float("nan"),
                    "upper_bound": float("inf"),
                }
            ],
            warning="synthetic GA warning",
        )

    monkeypatch.setattr(search_ga, "genetic_search", fake_genetic_search)
    result = search_model_pool(
        object(),
        taxonomy,
        SearchConfig(
            target="but",
            min_size=7,
            max_size=7,
            strategy="auto",
            n_samples=0,
            seed=71,
            top_k=2,
            exhaustive_max=10,
            ga_config=GAConfig(
                pop_size=8,
                generations=9,
                min_size=1,
                max_size=2,
                seed=999,
            ),
        ),
    )

    assert result.strategy == "ga"
    assert result.n_candidates_total == math.comb(200, 7)
    assert result.n_candidates_evaluated == len(genomes)
    assert {row.members for row in result.unevaluated} == failed
    assert len(result.ranks) == 2
    assert all(not robustness for _members, robustness in calls)
    assert captured["top_k"] == 2
    normalized = captured["config"]
    assert (normalized.min_size, normalized.max_size, normalized.seed) == (7, 7, 71)
    assert normalized.pop_size == 8 and normalized.generations == 9
    assert result.ga_metadata is not None
    assert result.ga_metadata["evaluations"] == len(genomes)
    assert result.ga_metadata["stop_reason"] == "patience"
    assert result.ga_metadata["config"]["min_size"] == 7
    assert result.ga_metadata["history"] == [
        {
            "generation": 0,
            "evaluations": len(genomes),
            "best_fitness": None,
            "mean_fitness": None,
            "upper_bound": None,
        }
    ]
    json.dumps(result.ga_metadata, allow_nan=False)
    assert any("2 of 4 candidates" in warning for warning in result.warnings)


@pytest.mark.parametrize("cardinality", [3, 11])
def test_real_ga_core_integrates_with_200_member_exact_n_search(
    monkeypatch: pytest.MonkeyPatch,
    cardinality: int,
) -> None:
    """The product callback and real GA agree on exact-n, budgets, and provenance."""
    ids = [f"m{i:03d}" for i in range(200)]
    calls = _install_fake_evaluator(monkeypatch)
    _forbid_materialized_candidates(monkeypatch)

    result = search_model_pool(
        object(),
        _Taxonomy(ids),
        SearchConfig(
            target="but",
            min_size=cardinality,
            max_size=cardinality,
            strategy="auto",
            seed=23,
            top_k=5,
            exhaustive_max=100,
            ga_config=GAConfig(
                pop_size=16,
                generations=20,
                mutation_rate=0.5,
                immigrant_fraction=0.25,
                max_evaluations=60,
                patience=5,
            ),
        ),
    )

    assert result.strategy == "ga"
    assert result.n_candidates_total == math.comb(200, cardinality)
    assert result.n_candidates_evaluated == len(calls) <= 60
    assert all(len(row.members) == cardinality for row in result.ranks)
    assert result.ga_metadata is not None
    assert result.ga_metadata["evaluations"] == result.n_candidates_evaluated
    assert result.ga_metadata["config"]["min_size"] == cardinality
    assert result.ga_metadata["config"]["max_size"] == cardinality
    assert result.ga_metadata["history"][-1]["evaluations"] == len(calls)


def test_ga_all_failures_remain_visible_even_when_not_in_ga_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cmig.core import search_ga

    ids = [f"m{i}" for i in range(8)]
    genomes = [tuple(ids[offset : offset + 3]) for offset in range(3)]
    _install_fake_evaluator(monkeypatch, failed=set(genomes))

    def fake_genetic_search(
        _ids: list[str],
        fitness_fn: Any,
        _config: GAConfig,
        *,
        top_k: int,
    ) -> SimpleNamespace:
        assert top_k == 1
        for genome in genomes:
            assert fitness_fn(genome) == float("-inf")
        return SimpleNamespace(
            best_members=genomes[0],
            best_fitness=float("-inf"),
            top_k=[],
            generations_run=1,
            evaluations=len(genomes),
            stop_reason="max_evaluations",
            history=[],
            warning="synthetic GA warning",
        )

    monkeypatch.setattr(search_ga, "genetic_search", fake_genetic_search)
    result = search_model_pool(
        object(),
        _Taxonomy(ids),
        SearchConfig(
            target="but",
            min_size=3,
            max_size=3,
            strategy="ga",
            n_samples=0,
            top_k=1,
        ),
    )

    assert result.ranks == []
    assert len(result.unevaluated) == result.n_candidates_evaluated == len(genomes)
    assert all(row.rank == 0 for row in result.unevaluated)
    assert any("no candidate was evaluable" in warning for warning in result.warnings)


def test_robustness_fva_runs_only_after_ranking_for_final_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cmig.core import search_product

    ids = [f"m{i}" for i in range(6)]
    calls = _install_fake_evaluator(monkeypatch)
    robust_members: list[tuple[str, ...]] = []

    def fake_add_robustness(
        _engine: Any,
        _taxonomy: Any,
        row: PoolRank,
        _spec: Any,
        **_kwargs: Any,
    ) -> PoolRank:
        robust_members.append(row.members)
        return replace(
            row,
            robustness_fva_lo=row.target_flux - 1.0,
            robustness_fva_hi=row.target_flux + 1.0,
            robustness_status="ok",
        )

    monkeypatch.setattr(search_product, "_add_robustness_fva", fake_add_robustness)
    result = search_model_pool(
        object(),
        _Taxonomy(ids),
        SearchConfig(
            target="but",
            min_size=2,
            max_size=2,
            strategy="exhaustive",
            top_k=3,
            robustness_fva=True,
        ),
    )

    assert len(calls) == math.comb(6, 2)
    assert all(not robustness for _members, robustness in calls)
    assert robust_members == [row.members for row in result.ranks]
    assert len(robust_members) == 3
    assert all(row.robustness_status == "ok" for row in result.ranks)


def test_robustness_failure_keeps_valid_ranking_and_emits_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cmig.core import search_product

    ids = [f"m{i}" for i in range(5)]
    _install_fake_evaluator(monkeypatch)

    def fake_add_robustness(
        _engine: Any,
        _taxonomy: Any,
        row: PoolRank,
        _spec: Any,
        **_kwargs: Any,
    ) -> PoolRank:
        return replace(
            row,
            diagnostic="robustness FVA failed: synthetic solver failure",
            robustness_status="failed",
        )

    monkeypatch.setattr(search_product, "_add_robustness_fva", fake_add_robustness)
    result = search_model_pool(
        object(),
        _Taxonomy(ids),
        SearchConfig(
            target="but",
            min_size=2,
            max_size=2,
            strategy="exhaustive",
            top_k=2,
            robustness_fva=True,
        ),
    )

    assert len(result.ranks) == 2
    assert all(row.status == "optimal" for row in result.ranks)
    assert all(row.robustness_status == "failed" for row in result.ranks)
    assert result.n_robustness_failed == 2
    assert any("target-max rankings were retained" in warning for warning in result.warnings)


def test_robustness_returned_failure_preserves_its_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cmig.core import search_advanced, search_product

    class _Engine:
        def build_community(self, _taxonomy: Any, *, cmig_solver: str) -> object:
            assert cmig_solver == "gurobi"
            return object()

    monkeypatch.setattr(
        search_advanced,
        "robustness_fva",
        lambda *_args, **_kwargs: SimpleNamespace(
            status="failed",
            diagnostic="synthetic FVA solver failure",
            fva_lo=0.0,
            fva_hi=0.0,
        ),
    )
    row = PoolRank(
        rank=1,
        members=("m0", "m1"),
        score=4.0,
        target_flux=4.0,
        community_growth=0.5,
        status="optimal",
    )

    updated = search_product._add_robustness_fva(
        _Engine(),
        _FilterableTaxonomy(["m0", "m1"]),
        row,
        object(),
        growth_fraction=0.5,
        solver="gurobi",
        medium_spec=None,
        strict_medium=True,
    )

    assert updated.status == "optimal"
    assert updated.robustness_status == "failed"
    assert updated.diagnostic is not None
    assert "synthetic FVA solver failure" in updated.diagnostic
