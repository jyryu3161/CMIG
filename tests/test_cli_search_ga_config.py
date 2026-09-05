"""CLI-only coverage for GA search configuration and provenance.

These tests deliberately avoid MICOM and solver calls. They exercise argument parsing,
the workflow-manifest search policy, and search-summary serialization.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cmig.cli import main as cli
from cmig.core.search_product import PoolRank, PoolSearchResult


def _search_args(*extra: str):
    return cli.build_parser().parse_args([
        "search",
        "--taxonomy",
        "pool.csv",
        "--out",
        "run",
        *extra,
    ])


def test_search_parser_builds_complete_ga_config_and_manifest_policy():
    args = _search_args(
        "--target", "but",
        "--min-size", "3",
        "--max-size", "3",
        "--strategy", "ga",
        "--exhaustive-max", "17",
        "--n-samples", "23",
        "--seed", "19",
        "--top-k", "7",
        "--ga-pop-size", "41",
        "--ga-generations", "37",
        "--ga-mutation-rate", "0.35",
        "--ga-immigrant-fraction", "0.15",
        "--ga-tournament-k", "5",
        "--ga-elitism", "3",
        "--ga-max-evaluations", "511",
        "--ga-patience", "8",
        "--robustness-fva",
    )

    ga_config = cli._ga_config_from_search_args(args)
    result = SimpleNamespace(strategy="ga")
    config = SimpleNamespace(exhaustive_max=args.exhaustive_max, ga_config=ga_config)
    search_spec = cli._single_target_search_spec(args, result, config)

    assert search_spec == {
        **cli._search_policy_settings(args),
        "min_size": 3,
        "max_size": 3,
        "strategy_requested": "ga",
        "strategy_resolved": "ga",
        "exhaustive_max": 17,
        "seed": 19,
        "top_k": 7,
        "robustness_fva": True,
        "ga_config": {
            "pop_size": 41,
            "generations": 37,
            "min_size": 3,
            "max_size": 3,
            "mutation_rate": 0.35,
            "immigrant_fraction": 0.15,
            "tournament_k": 5,
            "elitism": 3,
            "seed": 19,
            "max_evaluations": 511,
            "patience": 8,
        },
    }
    # The exact manifest component must be strict JSON, including optional budget fields.
    json.dumps(search_spec, allow_nan=False)


def test_manifest_omits_ga_knobs_when_the_resolved_strategy_does_not_use_ga():
    args = _search_args(
        "--strategy", "exhaustive",
        "--ga-mutation-rate", "nan",
        "--n-samples", "23",
        "--seed", "19",
    )
    ga_config = cli._ga_config_from_search_args(args)
    config = SimpleNamespace(exhaustive_max=args.exhaustive_max, ga_config=ga_config)

    exhaustive = cli._single_target_search_spec(
        args,
        SimpleNamespace(strategy="exhaustive"),
        config,
    )
    assert "ga_config" not in exhaustive
    assert "n_samples" not in exhaustive
    assert "seed" not in exhaustive
    json.dumps(exhaustive, allow_nan=False)

    random_policy = cli._single_target_search_spec(
        args,
        SimpleNamespace(strategy="random"),
        config,
    )
    assert random_policy["n_samples"] == 23
    assert random_policy["seed"] == 19
    assert "ga_config" not in random_policy
    json.dumps(random_policy, allow_nan=False)


def test_multi_target_rejects_single_target_only_fva_before_solving():
    with pytest.raises(ValueError, match="single-target"):
        cli._run_multi_target_search(
            SimpleNamespace(strategy="auto", robustness_fva=True),
            object(),
            None,
        )


def test_search_parser_ga_defaults_follow_core_contract():
    from cmig.core.search_ga import GAConfig

    args = _search_args()
    defaults = GAConfig()

    assert args.exhaustive_max == 100
    assert args.seed == defaults.seed
    assert args.ga_pop_size == defaults.pop_size
    assert args.ga_generations == defaults.generations
    assert args.ga_mutation_rate == defaults.mutation_rate
    assert args.ga_immigrant_fraction == defaults.immigrant_fraction
    assert args.ga_tournament_k == defaults.tournament_k
    assert args.ga_elitism == defaults.elitism
    assert args.ga_max_evaluations == defaults.max_evaluations
    assert args.ga_patience == defaults.patience


class _Taxonomy:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def __getitem__(self, key: str) -> list[str]:
        assert key == "id"
        return self._ids

    def to_csv(self, path: Path, *, index: bool) -> None:
        assert index is False
        path.write_text("id\n" + "\n".join(self._ids) + "\n")


def test_search_summary_serializes_ga_metadata_without_solver(tmp_path, monkeypatch):
    metadata = {
        "config": {
            "pop_size": 41,
            "generations": 37,
            "min_size": 3,
            "max_size": 3,
            "mutation_rate": 0.35,
            "immigrant_fraction": 0.15,
            "tournament_k": 5,
            "elitism": 3,
            "seed": 19,
            "max_evaluations": 511,
            "patience": 8,
        },
        "generations_run": 12,
        "evaluations": 203,
        "stop_reason": "patience",
        "history": [
            {
                "generation": 0,
                "best_fitness": float("-inf"),
                "mean_fitness": float("nan"),
                "unique_genomes": 38,
                "evaluations": 203,
            }
        ],
        "warning": "GA approximate search; global optimum is not guaranteed",
    }
    result = PoolSearchResult(
        target="but",
        target_exchange="EX_but_m",
        direction="max_secretion",
        strategy="ga",
        n_pool_members=200,
        n_candidates_total=1_313_400,
        n_candidates_evaluated=203,
        ranks=[
            PoolRank(
                rank=1,
                members=("a", "b", "c"),
                score=8.5,
                target_flux=8.5,
                community_growth=0.4,
                status="optimal",
                diagnostic="robustness FVA failed: synthetic solver failure",
                robustness_status="failed",
            )
        ],
        warnings=[
            "GA approximate search; global optimum is not guaranteed",
            "robustness FVA was unavailable for 1 reported candidate",
        ],
        unevaluated=[],
        ga_metadata=metadata,
    )
    for name in (
        "_write_search_svg",
        "_write_search_scatter_svg",
        "_write_search_tiff",
        "_write_search_scatter_tiff",
        "_prune_stale_workflow_artifacts",
    ):
        monkeypatch.setattr(cli, name, lambda *args, **kwargs: None)

    cli._write_search_outputs(result, _Taxonomy(["a", "b", "c"]), [], tmp_path)

    summary = json.loads((tmp_path / "search_summary.json").read_text())
    assert summary["ga_metadata"]["config"] == metadata["config"]
    assert summary["ga_metadata"]["stop_reason"] == "patience"
    assert summary["ga_metadata"]["history"] == [{
        "generation": 0,
        "best_fitness": None,
        "mean_fitness": None,
        "unique_genomes": 38,
        "evaluations": 203,
    }]
    assert summary["n_candidates_total"] == 1_313_400
    assert summary["top_ranked"][0]["members"] == ["a", "b", "c"]
    assert summary["status"] == "degraded"
    assert summary["n_robustness_failed"] == 1
