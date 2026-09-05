"""Real solver integration for resumable, parallel and multi-target product search."""

from dataclasses import replace

import pytest

from cmig.core.search import Direction
from cmig.core.search_execution import SearchCancelled, SearchControl
from cmig.core.search_ga import GAConfig
from cmig.core.search_product import MultiTargetConfig, SearchConfig
from cmig.service.search_service import SearchRequest, SearchService


@pytest.fixture
def pool():
    pd = pytest.importorskip("pandas")
    pytest.importorskip("micom")
    from cmig.golden_fixture import build_taxonomy

    tax = build_taxonomy().copy()
    extra = tax.iloc[:1].copy()
    extra["id"] = "additional_strain"
    return pd.concat([tax, extra], ignore_index=True)


def config_for(metric):
    common = dict(
        min_size=2,
        max_size=2,
        strategy="ga",
        seed=19,
        top_k=2,
        ga_config=GAConfig(pop_size=4, generations=20, max_evaluations=5),
    )
    if metric == "single":
        return SearchConfig(target="ac", **common)
    return MultiTargetConfig(
        targets=["ac", "but"],
        directions=dict.fromkeys(["ac", "but"], Direction.MAX_SECRETION),
        weights={"ac": 1, "but": 1},
        metric=metric,
        reference_scales={"ac": 20, "but": 10},
        **common,
    )


@pytest.mark.parametrize("metric", ["single", "raw_sum", "normalized_weighted", "pareto"])
def test_parallel_matches_serial_budget_and_selection(pool, metric):
    request = SearchRequest(pool, config_for(metric))
    serial = SearchService().run(request, control=SearchControl())
    parallel = SearchService().run(request, control=SearchControl(workers=2))
    assert serial.n_candidates_evaluated == parallel.n_candidates_evaluated == 5
    assert serial.ga_metadata["history"] == parallel.ga_metadata["history"]
    assert [row.members for row in serial.ranks] == [row.members for row in parallel.ranks]
    for a, b in zip(serial.ranks, parallel.ranks, strict=True):
        if metric == "single":
            assert a.score == pytest.approx(b.score)
        else:
            assert a.target_fluxes == pytest.approx(b.target_fluxes)
        assert set(a.effective_members) == set(a.members)
        assert set(a.member_growth) == set(a.members)
        assert sum(a.abundances.values()) == pytest.approx(1)
    assert parallel.profile["completed_evaluation_totals"]["build_calls"] >= 5


@pytest.mark.parametrize("metric", ["single", "raw_sum", "pareto"])
def test_checkpoint_resume_matches_uninterrupted_search(pool, tmp_path, metric):
    checkpoint = tmp_path / "checkpoint.json"
    completed = [0]
    control = SearchControl(
        checkpoint=checkpoint,
        cancelled=lambda: completed[0] >= 2,
        progress=lambda done, total: completed.__setitem__(0, done),
    )
    request = SearchRequest(pool, config_for(metric))
    with pytest.raises(SearchCancelled):
        SearchService().run(request, control=control)
    assert checkpoint.exists()
    resumed = SearchService().run(
        request, control=SearchControl(checkpoint=checkpoint, resume=True)
    )
    uninterrupted = SearchService().run(request, control=SearchControl())
    assert resumed.ga_metadata == uninterrupted.ga_metadata
    assert resumed.ranks == uninterrupted.ranks


def test_post_search_validation_has_separate_budget_and_resumes(pool, tmp_path):
    checkpoint = tmp_path / "validation.json"
    config = replace(config_for("single"), validation_top=1)
    request = SearchRequest(pool, config)
    result = SearchService().run(request, control=SearchControl(checkpoint=checkpoint))
    assert result.n_candidates_evaluated == 5
    report = result.validation_report
    assert report["additional_evaluations"] == 11
    assert len(report["combinations"]) == 1
    comparison = report["combinations"][0]
    assert len(comparison["scenarios"]) == 10
    assert comparison["best_tested_abundance"] is not None
    resumed = SearchService().run(
        request, control=SearchControl(checkpoint=checkpoint, resume=True)
    )
    assert resumed.validation_report == report


def test_approximate_normalization_requires_fixed_references(pool):
    config = replace(config_for("normalized_weighted"), reference_scales={})
    with pytest.raises(ValueError, match="fixed --target-scales"):
        SearchService().run(SearchRequest(pool, config))


def test_bad_model_fails_preflight_before_using_budget(pool, tmp_path):
    path = tmp_path / "invalid.sbml"
    path.write_text("not an SBML model")
    pool.loc[0, "file"] = str(path)
    control = SearchControl()
    with pytest.raises(ValueError, match="model preflight failed"):
        SearchService().run(SearchRequest(pool, config_for("single")), control=control)
    assert not control.records


def test_cli_multi_ga_publishes_verified_bundle_and_resumes(pool, tmp_path):
    import json

    from cmig.cli import main as cli

    taxonomy = tmp_path / "pool.csv"
    pool.iloc[:3].to_csv(taxonomy, index=False)
    out = tmp_path / "out"
    args = [
        "search",
        "--taxonomy",
        str(taxonomy),
        "--targets",
        "ac,but",
        "--multi-metric",
        "raw_sum",
        "--strategy",
        "ga",
        "--ga-max-evaluations",
        "3",
        "--top-k",
        "1",
        "--validate-top",
        "1",
        "--min-member-growth",
        "0.0001",
        "--checkpoint",
        str(tmp_path / "checkpoint.json"),
        "--out",
        str(out),
    ]
    assert cli.main(args) == 0
    summary = json.loads((out / "search_summary.json").read_text())
    manifest = json.loads((out / "manifest.json").read_text())
    assert cli._verify_result_digest(out, manifest)["match"]
    assert summary["n_candidates_evaluated"] == 3
    assert all(
        value >= 0.0001 - 1e-8 for value in summary["top_ranked"][0]["member_growth"].values()
    )
    assert (out / "search_validation.json").is_file()
    assert cli.main(args + ["--resume"]) == 0
    resumed = json.loads((out / "search_summary.json").read_text())
    assert resumed["top_ranked"] == summary["top_ranked"]


@pytest.mark.parametrize("metric", ["single", "raw_sum", "pareto"])
def test_medium_warnings_survive_resume_and_parallelism(pool, tmp_path, metric):
    from cmig.core.medium_spec import MediumSpec

    checkpoint = tmp_path / "medium.json"
    config = replace(config_for(metric), ga_config=GAConfig(max_evaluations=2))
    request = SearchRequest(pool, config, MediumSpec({"EX_unknown_m": 1}), strict_medium=False)
    serial = SearchService().run(request, control=SearchControl(checkpoint=checkpoint))
    resumed = SearchService().run(
        request, control=SearchControl(checkpoint=checkpoint, resume=True)
    )
    parallel = SearchService().run(request, control=SearchControl(workers=2))
    assert any("medium" in warning for warning in serial.warnings)
    assert serial.warnings == resumed.warnings == parallel.warnings


def test_fva_resume_keeps_original_budget_and_phase_counts(pool, tmp_path, monkeypatch):
    from cmig.core import search_advanced

    calls = []
    original = search_advanced.robustness_fva

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(search_advanced, "robustness_fva", tracked)
    checkpoint = tmp_path / "fva.json"
    config = replace(config_for("single"), robustness_fva=True, top_k=1)
    request = SearchRequest(pool, config)
    result = SearchService().run(request, control=SearchControl(checkpoint=checkpoint))
    resumed = SearchService().run(
        request, control=SearchControl(checkpoint=checkpoint, resume=True)
    )
    assert len(calls) == 1
    assert result.n_candidates_evaluated == resumed.n_candidates_evaluated == 5
    assert result.ranks == resumed.ranks
    assert result.profile == resumed.profile
