"""Round 9 V5 — StatsConfig provenance and seeded/gated embedding pipeline."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from cmig.core.stats import ClusteringConfig, DimredConfig, StatsConfig
from cmig.core.stats_embed import StatsEmbeddingGateError, run_embedding_pipeline

pytest.importorskip("sklearn")


def _feature_rows(n_per_group: int = 5) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_index, group in enumerate(("fiber", "western")):
        for replicate in range(n_per_group):
            offset = float(group_index * 5)
            rows.append({
                "condition_id": f"{group}-r{replicate}",
                "group": group,
                "acetate": offset + replicate * 0.13,
                "butyrate": offset * 0.4 + (replicate % 3) * 0.31,
                "growth": offset * 0.2 + replicate * replicate * 0.07,
            })
    return rows


def test_stats_config_is_frozen_canonical_and_json_deterministic():
    groups = ["fiber", "western"]
    dimred = {"method": "umap", "n_components": 2, "n_neighbors": 4}
    clustering = {"method": "kmeans", "k": 2}
    config = StatsConfig(
        groups=groups,  # type: ignore[arg-type]
        methods=("robust", "parametric"),
        fdr_method="fdr_by",
        seed=19,
        dimred=dimred,
        clustering=clustering,
    )
    groups.append("mutated-after-construction")
    dimred["n_components"] = 99
    clustering["k"] = 99

    expected = {
        "groups": ["fiber", "western"],
        "methods": ["robust", "parametric"],
        "fdr_method": "fdr_by",
        "seed": 19,
        "dimred": {"method": "umap", "n_components": 2, "n_neighbors": 4},
        "clustering": {"method": "kmeans", "k": 2},
    }
    assert config.as_provenance() == expected
    assert json.dumps(config.as_provenance(), sort_keys=True) == json.dumps(
        expected, sort_keys=True
    )
    with pytest.raises(FrozenInstanceError):
        config.seed = 7  # type: ignore[misc]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"groups": ()}, "groups"),
        ({"groups": ("fiber", "fiber")}, "duplicates"),
        ({"groups": ("fiber",), "methods": ()}, "methods"),
        ({"groups": ("fiber",), "methods": ("invented",)}, "unsupported"),
        ({"groups": ("fiber",), "fdr_method": "bonferroni"}, "fdr_method"),
        ({"groups": ("fiber",), "seed": True}, "seed"),
        ({"groups": ("fiber",), "seed": -1}, "seed"),
        ({"groups": ("fiber",), "dimred": {"method": "tsne"}}, "dimred.method"),
        ({"groups": ("fiber",), "clustering": {"method": "dbscan"}},
         "clustering.method"),
    ],
)
def test_stats_config_rejects_invalid_fields(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        StatsConfig(**kwargs)  # type: ignore[arg-type]


def test_nested_configs_validate_algorithm_parameters():
    with pytest.raises(ValueError, match="n_components"):
        DimredConfig(method="pca", n_components=0)
    with pytest.raises(ValueError, match="n_neighbors"):
        DimredConfig(method="umap", n_neighbors=1)
    with pytest.raises(ValueError, match="clustering.k"):
        ClusteringConfig(method="kmeans", k=0)


def test_seeded_pca_kmeans_pipeline_returns_identical_tidy_tables():
    config = StatsConfig(
        groups=("fiber", "western"),
        seed=31,
        dimred=DimredConfig(method="pca", n_components=2),
        clustering=ClusteringConfig(method="kmeans", k=2),
    )
    first = run_embedding_pipeline(
        _feature_rows(),
        config,
        feature_columns=("acetate", "butyrate", "growth"),
        independent_replicates=True,
    )
    second = run_embedding_pipeline(
        _feature_rows(),
        config,
        feature_columns=("acetate", "butyrate", "growth"),
        independent_replicates=True,
    )

    assert first == second
    assert len(first.embedding_table) == 20
    assert len(first.cluster_table) == 10
    assert len(first.explained_variance_table) == 2
    assert {row["basis"] for row in first.cluster_table} == {"pca"}
    assert first.provenance["seed"] == 31


def test_different_pipeline_seed_is_recorded_in_every_output_table():
    common = {
        "groups": ("fiber", "western"),
        "dimred": DimredConfig(method="pca", n_components=2),
        "clustering": ClusteringConfig(method="kmeans", k=2),
    }
    seed_1 = run_embedding_pipeline(
        _feature_rows(),
        StatsConfig(seed=1, **common),  # type: ignore[arg-type]
        feature_columns=("acetate", "butyrate", "growth"),
        independent_replicates=True,
    )
    seed_2 = run_embedding_pipeline(
        _feature_rows(),
        StatsConfig(seed=2, **common),  # type: ignore[arg-type]
        feature_columns=("acetate", "butyrate", "growth"),
        independent_replicates=True,
    )
    assert seed_1.provenance != seed_2.provenance
    assert {row["seed"] for row in seed_1.embedding_table} == {1}
    assert {row["seed"] for row in seed_2.embedding_table} == {2}
    assert {row["seed"] for row in seed_1.cluster_table} == {1}
    assert {row["seed"] for row in seed_2.cluster_table} == {2}


def test_umap_same_seed_is_exact_and_different_seed_changes_coordinates():
    pytest.importorskip("umap")
    common = {
        "groups": ("fiber", "western"),
        "dimred": DimredConfig(method="umap", n_components=2, n_neighbors=4),
    }

    def run(seed: int):
        return run_embedding_pipeline(
            _feature_rows(n_per_group=6),
            StatsConfig(seed=seed, **common),  # type: ignore[arg-type]
            feature_columns=("acetate", "butyrate", "growth"),
            independent_replicates=True,
        )

    first = run(41)
    repeat = run(41)
    different = run(42)
    assert first.embedding_table == repeat.embedding_table
    assert first.embedding_table != different.embedding_table
    assert first.provenance["seed"] == 41
    assert different.provenance["seed"] == 42


def test_pipeline_refuses_pseudo_replicates_with_existing_named_reason():
    config = StatsConfig(
        groups=("fiber", "western"),
        dimred=DimredConfig(method="pca", n_components=2),
    )
    with pytest.raises(StatsEmbeddingGateError) as captured:
        run_embedding_pipeline(
            _feature_rows(),
            config,
            feature_columns=("acetate", "butyrate", "growth"),
        )
    assert captured.value.reason == "not_run_no_independent_replicates"


def test_pipeline_refuses_observations_fewer_than_components():
    config = StatsConfig(
        groups=("fiber", "western"),
        dimred=DimredConfig(method="pca", n_components=3),
    )
    with pytest.raises(StatsEmbeddingGateError) as captured:
        run_embedding_pipeline(
            _feature_rows(n_per_group=1),
            config,
            feature_columns=("acetate", "butyrate", "growth"),
            independent_replicates=True,
        )
    assert captured.value.reason == "not_run_observations_fewer_than_components"


def test_pipeline_refuses_umap_neighbors_that_exceed_available_data():
    config = StatsConfig(
        groups=("fiber", "western"),
        dimred=DimredConfig(method="umap", n_components=2, n_neighbors=4),
    )
    with pytest.raises(StatsEmbeddingGateError) as captured:
        run_embedding_pipeline(
            _feature_rows(n_per_group=2),
            config,
            feature_columns=("acetate", "butyrate", "growth"),
            independent_replicates=True,
        )
    assert captured.value.reason == "not_run_umap_neighbors_exceed_observations"


def test_no_embedding_or_clustering_returns_empty_tables_without_claiming_inference():
    result = run_embedding_pipeline(
        _feature_rows(n_per_group=1),
        StatsConfig(groups=("fiber", "western")),
        feature_columns=("acetate", "butyrate", "growth"),
    )
    assert result.embedding_table == ()
    assert result.cluster_table == ()
    assert result.provenance["input"] == {
        "observation_count": 2,
        "feature_columns": ["acetate", "butyrate", "growth"],
        "independent_replicates_confirmed": False,
    }
