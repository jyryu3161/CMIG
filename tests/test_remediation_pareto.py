"""SC-05: every Pareto slice is accounted for without losing feasible points."""

from __future__ import annotations

import json
from unittest.mock import patch

import cobra
import pandas as pd
import pytest

from cmig.cli.main import _inspect_run_dir, main
from cmig.core.search import (
    Direction,
    MultiTargetSolveResult,
    TargetMaxResult,
    epsilon_constrained_solve,
)
from cmig.core.search_execution import SearchCancelled, SearchControl
from cmig.core.search_product import (
    MultiTargetConfig,
    search_model_pool_multi,
    target_max_solve,
)
from cmig.service.search_service import SearchRequest, SearchService, search_identity


def tradeoff_model() -> cobra.Model:
    model = cobra.Model("tradeoff")
    precursor = cobra.Metabolite("p_c", compartment="c")
    growth = cobra.Metabolite("g_c", compartment="c")
    for rid, stoich, bounds in [
        ("SOURCE", {precursor: 1}, (0, 20)),
        ("GROWTH_SOURCE", {growth: 1}, (0, 1)),
        ("GROWTH", {growth: -1}, (0, 1)),
        ("EX_a_m", {precursor: -2}, (-10, 100)),
        ("EX_b_m", {precursor: -1}, (-10, 100)),
    ]:
        reaction = cobra.Reaction(rid)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "GROWTH"
    return model


class Engine:
    def build_community(self, taxonomy, cmig_solver="gurobi"):
        return tradeoff_model()


def request():
    taxonomy = pd.DataFrame({"id": ["toy"]})
    config = MultiTargetConfig(
        targets=["a", "b"],
        directions=dict.fromkeys(["a", "b"], Direction.MAX_SECRETION),
        weights={"a": 3, "b": 1},
        min_size=1,
        max_size=1,
        metric="pareto",
        top_k=1,
    )
    return taxonomy, config


@pytest.mark.parametrize("controlled", [False, True])
def test_one_optimal_fifteen_injected_timeouts_preserves_point_and_ledger(controlled):
    taxonomy, config = request()
    calls = 0

    def injected(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            return MultiTargetSolveResult({}, {}, 0, "time_limit", "injected timeout")
        return epsilon_constrained_solve(*args, **kwargs)

    with patch("cmig.core.search.epsilon_constrained_solve", side_effect=injected):
        result = search_model_pool_multi(
            Engine(), taxonomy, config, control=SearchControl() if controlled else None
        )
    assert calls == 16
    assert len(result.ranks) == 1
    assert result.ranks[0].status == "optimal"
    assert result.candidate_sampling_status == {"toy": "partial"}
    assert len(result.pareto_attempts) == 20  # two baselines, two capabilities, sixteen slices
    assert sum(a["outcome"] == "timeout" for a in result.pareto_attempts) == 15
    assert result.pareto_attempts[1]["achieved_vector"] is None
    assert result.pareto_attempts[4]["achieved_vector"] is not None
    assert all(
        2 * row.target_fluxes["a"] + row.target_fluxes["b"] <= 20 + 1e-7
        for row in result.pareto_archive
    )


def test_exception_after_optimum_preserves_feasible_point():
    taxonomy, config = request()
    calls = 0

    def injected(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("injected slice exception")
        return epsilon_constrained_solve(*args, **kwargs)

    with patch("cmig.core.search.epsilon_constrained_solve", side_effect=injected):
        result = search_model_pool_multi(Engine(), taxonomy, config)
    assert len(result.ranks) == 1
    assert result.candidate_sampling_status["toy"] == "partial"
    assert sum(a["outcome"] == "error" for a in result.pareto_attempts) == 15


def test_all_injected_timeouts_have_no_rank_and_one_failed_candidate():
    taxonomy, config = request()
    timeout = MultiTargetSolveResult({}, {}, 0, "time_limit", "injected timeout")
    with patch("cmig.core.search.epsilon_constrained_solve", return_value=timeout):
        result = search_model_pool_multi(Engine(), taxonomy, config)
    assert result.ranks == []
    assert len(result.unevaluated) == 1
    assert result.candidate_sampling_status == {"toy": "failed"}
    assert sum(a["outcome"] == "timeout" for a in result.pareto_attempts) == 16


def test_infeasible_slices_are_resolved_and_duplicates_remain_attempts():
    taxonomy, config = request()
    calls = 0

    def injected(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return epsilon_constrained_solve(*args, **kwargs)
        if calls == 2:
            return epsilon_constrained_solve(*args, **kwargs)  # may duplicate weighted point
        return MultiTargetSolveResult({}, {}, 0, "infeasible", "injected infeasible")

    with patch("cmig.core.search.epsilon_constrained_solve", side_effect=injected):
        result = search_model_pool_multi(Engine(), taxonomy, config)
    assert result.candidate_sampling_status == {"toy": "complete"}
    assert len(result.pareto_attempts) == 20
    assert sum(a["outcome"] == "infeasible" for a in result.pareto_attempts) == 14


def test_cooperative_cancellation_propagates():
    taxonomy, config = request()
    with patch(
        "cmig.core.search.epsilon_constrained_solve", side_effect=SearchCancelled("injected")
    ):
        with pytest.raises(SearchCancelled, match="injected"):
            search_model_pool_multi(Engine(), taxonomy, config)


@pytest.mark.parametrize("controlled", [False, True])
def test_actual_lp_attempt_ledger_has_each_baseline_and_separate_capabilities(controlled):
    taxonomy, config = request()
    actual_statuses = []
    optimize = cobra.Model.optimize

    def observed(model, *args, **kwargs):
        solution = optimize(model, *args, **kwargs)
        actual_statuses.append(solution.status)
        return solution

    with patch.object(cobra.Model, "optimize", observed):
        result = search_model_pool_multi(
            Engine(), taxonomy, config, control=SearchControl() if controlled else None
        )
    assert len(actual_statuses) == len(result.pareto_attempts) == 20
    assert [a["raw_status"] for a in result.pareto_attempts] == actual_statuses
    assert [a["phase"] for a in result.pareto_attempts[:4]] == [
        "baseline", "capability", "capability", "baseline",
    ]
    capabilities = result.pareto_attempts[1:3]
    assert [a["target"] for a in capabilities] == ["a", "b"]
    assert all(a["achieved_vector"] is None for a in capabilities)
    assert all(a["measured_result"]["target_flux"] > 0 for a in capabilities)
    assert 2 * capabilities[0]["measured_result"]["target_flux"] + capabilities[1][
        "measured_result"
    ]["target_flux"] > 20
    assert all(
        2 * row.target_fluxes["a"] + row.target_fluxes["b"] <= 20 + 1e-7
        for row in result.pareto_archive
    )


@pytest.mark.parametrize("controlled", [False, True])
def test_frontier_baseline_return_exception_preserves_attempt_identity(controlled):
    taxonomy, config = request()
    observed_statuses: list[str] = []
    optimize = cobra.Model.optimize

    def return_failure(model, *args, **kwargs):
        solution = optimize(model, *args, **kwargs)
        observed_statuses.append(str(solution.status))
        if len(observed_statuses) == 4:
            raise RuntimeError("injected failure returning solved frontier baseline")
        return solution

    with patch.object(cobra.Model, "optimize", return_failure):
        result = search_model_pool_multi(
            Engine(), taxonomy, config, control=SearchControl() if controlled else None
        )
    assert observed_statuses == ["optimal"] * 4
    assert len(result.pareto_attempts) == 4
    assert [row["phase"] for row in result.pareto_attempts] == [
        "baseline", "capability", "capability", "baseline",
    ]
    assert [row["raw_status"] for row in result.pareto_attempts[:3]] == [
        "optimal", "optimal", "optimal",
    ]
    failed = result.pareto_attempts[-1]
    assert failed["raw_status"] == "solver_error"
    assert failed["outcome"] == "error"
    assert failed["solve_started"] is True
    assert failed["solve_executed"] is None
    assert failed["measured_result"] is None
    assert failed["constraint_floors"] == {
        "min_member_growth": 0.0, "min_community_growth": 0.0,
    }
    assert "injected failure returning solved frontier baseline" in failed["diagnostic"]
    assert result.ranks == []
    assert result.candidate_sampling_status == {"toy": "failed"}


@pytest.mark.parametrize("controlled", [False, True])
def test_frontier_baseline_readout_exception_retains_raw_solver_status(controlled):
    from cmig.core.search import _community_growth_star

    taxonomy, config = request()
    baselines = 0

    def failed_readout(*args, **kwargs):
        nonlocal baselines
        baselines += 1
        value = _community_growth_star(*args, **kwargs)
        if baselines == 2:
            raise RuntimeError("injected failure after baseline readout")
        return value

    with patch("cmig.core.search._community_growth_star", side_effect=failed_readout):
        result = search_model_pool_multi(
            Engine(), taxonomy, config, control=SearchControl() if controlled else None
        )
    assert len(result.pareto_attempts) == 4
    row = result.pareto_attempts[-1]
    assert row["phase"] == "baseline"
    assert row["raw_status"] == "optimal"
    assert row["outcome"] == "error"
    assert row["solve_started"] is True
    assert row["solve_executed"] is True
    assert "injected failure after baseline readout" in row["diagnostic"]
    assert result.ranks == []
    assert result.candidate_sampling_status == {"toy": "failed"}


@pytest.mark.parametrize("controlled", [False, True])
def test_injected_capability_timeout_is_failed_sampling_with_separate_status(controlled):
    taxonomy, config = request()
    def injected(*args, **kwargs):
        spec = args[1]
        if spec.metabolite == "a":
            return TargetMaxResult(spec.exchange_id(), spec.direction.value, 0, 0,
                                   "time_limit", "injected capability timeout")
        return target_max_solve(*args, **kwargs)

    with patch("cmig.core.search_product.target_max_solve", side_effect=injected):
        result = search_model_pool_multi(
            Engine(), taxonomy, config, control=SearchControl() if controlled else None
        )
    assert result.ranks == []
    assert result.candidate_sampling_status == {"toy": "failed"}
    assert [a["phase"] for a in result.pareto_attempts] == [
        "baseline", "capability", "capability",
    ]
    assert result.pareto_attempts[1]["outcome"] == "timeout"
    assert result.pareto_attempts[2]["raw_status"] == "optimal"


@pytest.mark.parametrize("controlled", [False, True])
def test_injected_capability_cancellation_propagates(controlled):
    taxonomy, config = request()
    with patch("cmig.core.search_product.target_max_solve",
               side_effect=SearchCancelled("injected capability cancellation")):
        with pytest.raises(SearchCancelled, match="injected capability cancellation"):
            search_model_pool_multi(
                Engine(), taxonomy, config, control=SearchControl() if controlled else None
            )


def test_failed_capability_checkpoint_resume_keeps_one_attempt_per_solve(tmp_path):
    taxonomy, config = request()
    checkpoint = tmp_path / "failed-capability.json"
    control = SearchControl(checkpoint=checkpoint)
    control.bind({"policy": "attempt_ledger_v3", "fixture": "failed-capability"})
    timed_out = TargetMaxResult("EX_a_m", Direction.MAX_SECRETION.value, 0, 0,
                                "time_limit", "injected capability timeout")
    with patch("cmig.core.search_product.target_max_solve", return_value=timed_out):
        first = search_model_pool_multi(Engine(), taxonomy, config, control=control)
    assert first.candidate_sampling_status == {"toy": "failed"}
    assert len(first.pareto_attempts) == 3
    resumed = SearchControl(checkpoint=checkpoint, resume=True)
    resumed.bind({"policy": "attempt_ledger_v3", "fixture": "failed-capability"})
    with patch("cmig.core.search_product.target_max_solve",
               side_effect=AssertionError("resume unexpectedly solved")):
        second = search_model_pool_multi(Engine(), taxonomy, config, control=resumed)
    assert second.pareto_attempts == first.pareto_attempts
    assert second.candidate_sampling_status == first.candidate_sampling_status


def test_nonviable_capability_keeps_distinct_outcome_and_no_rank():
    taxonomy, config = request()

    class NonviableEngine:
        def build_community(self, taxonomy, cmig_solver="gurobi"):
            model = tradeoff_model()
            model.reactions.GROWTH_SOURCE.upper_bound = 0
            return model

    result = search_model_pool_multi(NonviableEngine(), taxonomy, config)
    assert result.ranks == []
    assert result.candidate_sampling_status == {"toy": "failed"}
    assert [attempt["outcome"] for attempt in result.pareto_attempts] == [
        "optimal", "non_viable", "non_viable",
    ]
    assert [attempt["solve_executed"] for attempt in result.pareto_attempts] == [
        True, False, False,
    ]


def test_checkpoint_preserves_attempts_and_rejects_old_policy(tmp_path):
    taxonomy, config = request()
    checkpoint = tmp_path / "pareto.json"
    control = SearchControl(checkpoint=checkpoint)
    context = {"policy": "attempt_ledger_v3", "fixture": "tradeoff"}
    control.bind(context)
    first = search_model_pool_multi(Engine(), taxonomy, config, control=control)
    payload = json.loads(checkpoint.read_text())
    assert payload["evaluations"][0]["points"][0]["pareto_attempts"]
    resumed = SearchControl(checkpoint=checkpoint, resume=True)
    resumed.bind(context)
    second = search_model_pool_multi(Engine(), taxonomy, config, control=resumed)
    assert first.pareto_attempts == second.pareto_attempts
    with pytest.raises(ValueError, match="policy mismatch"):
        SearchControl(checkpoint=checkpoint, resume=True).bind({"policy": "old"})


def two_product_taxonomy(tmp_path):
    model = cobra.Model("two_products")
    e = cobra.Metabolite("glc_e", compartment="e")
    c = cobra.Metabolite("carbon_c", compartment="c")
    a = cobra.Metabolite("a_e", compartment="e")
    b = cobra.Metabolite("b_e", compartment="e")
    for rid, stoich, bounds in [
        ("EX_glc_e", {e: -1}, (-10, 1000)),
        ("GLCt", {e: -1, c: 1}, (0, 1000)),
        ("BIOMASS", {c: -1}, (0, 4)),
        ("PROD_a", {c: -1, a: 1}, (0, 1000)),
        ("PROD_b", {c: -1, b: 1}, (0, 1000)),
        ("EX_a_e", {a: -1}, (0, 1000)),
        ("EX_b_e", {b: -1}, (0, 1000)),
    ]:
        reaction = cobra.Reaction(rid)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "BIOMASS"
    filename = tmp_path / "member.json"
    cobra.io.save_json_model(model, str(filename))
    return pd.DataFrame([{"id": "A", "file": str(filename), "abundance": 1.0}])


def test_real_micom_pareto_worker_transfer_matches_single_worker(tmp_path):
    taxonomy = two_product_taxonomy(tmp_path)
    _, config = request()
    request_obj = SearchRequest(taxonomy, config)
    one = SearchService().run(request_obj, control=SearchControl(workers=1))
    two = SearchService().run(request_obj, control=SearchControl(workers=2))
    assert one.candidate_sampling_status == two.candidate_sampling_status
    assert one.pareto_attempts == two.pareto_attempts
    assert [(r.members, r.target_fluxes) for r in one.pareto_archive] == [
        (r.members, r.target_fluxes) for r in two.pareto_archive
    ]


def test_previous_pareto_ledger_checkpoint_policy_is_rejected(tmp_path):
    taxonomy = two_product_taxonomy(tmp_path)
    _, config = request()
    request_obj = SearchRequest(taxonomy, config)
    identity = search_identity(request_obj)
    assert identity["pareto_evaluation_policy"] == "attempt_ledger_v3"
    checkpoint = tmp_path / "previous-ledger.json"
    prior = SearchControl(checkpoint=checkpoint)
    prior.bind({**identity, "pareto_evaluation_policy": "attempt_ledger_v2"})
    prior.save()
    with pytest.raises(ValueError, match="policy mismatch"):
        SearchService().run(
            request_obj, control=SearchControl(checkpoint=checkpoint, resume=True)
        )


def test_pareto_cancel_after_completed_candidate_resumes_with_ledger(tmp_path):
    taxonomy, config = request()
    taxonomy = pd.DataFrame({"id": ["one", "two"]})
    checkpoint = tmp_path / "cancelled.json"
    control = SearchControl(checkpoint=checkpoint)
    control.bind({"policy": "attempt_ledger_v3", "fixture": "cancel"})
    control.cancelled = lambda: len(control.records) >= 1
    with pytest.raises(SearchCancelled):
        search_model_pool_multi(Engine(), taxonomy, config, control=control)
    saved = json.loads(checkpoint.read_text())
    assert len(saved["evaluations"]) == 1
    assert saved["evaluations"][0]["points"][0]["pareto_attempts"]
    resumed = SearchControl(checkpoint=checkpoint, resume=True)
    resumed.bind({"policy": "attempt_ledger_v3", "fixture": "cancel"})
    result = search_model_pool_multi(Engine(), taxonomy, config, control=resumed)
    uninterrupted = search_model_pool_multi(Engine(), taxonomy, config, control=SearchControl())
    assert result.pareto_attempts == uninterrupted.pareto_attempts
    assert result.candidate_sampling_status == uninterrupted.candidate_sampling_status


def test_partial_pareto_cli_artifact_digest_and_degraded_status(tmp_path):
    taxonomy = two_product_taxonomy(tmp_path)
    taxonomy_file = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_file, index=False)
    out = tmp_path / "run"
    calls = 0

    def injected(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            return MultiTargetSolveResult({}, {}, 0, "time_limit", "injected timeout")
        return epsilon_constrained_solve(*args, **kwargs)

    with patch("cmig.core.search.epsilon_constrained_solve", side_effect=injected):
        rc = main([
            "search", "--taxonomy", str(taxonomy_file), "--targets", "a,b",
            "--multi-metric", "pareto", "--min-size", "1", "--max-size", "1",
            "--top-k", "1", "--out", str(out),
        ])
    assert rc == 0  # degraded science keeps the established nonfatal CLI exit policy
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["status"] == "degraded"
    assert summary["n_pareto_attempts"] == 20
    assert summary["n_pareto_failed_attempts"] == 15
    assert summary["n_candidates_evaluated"] == 1
    assert summary["n_candidates_ranked"] == 1
    assert summary["top_ranked"][0]["sampling_status"] == "partial"
    evaluation = json.loads((out / "search_evaluations.json").read_text())
    assert len(evaluation["pareto_attempts"]) == 20
    inspection = _inspect_run_dir(out)
    assert inspection["status"] == "degraded"
    assert inspection["artifact_integrity"] == "verified"
    assert inspection["result_digest"]["match"] is True


def test_injected_capability_timeout_cli_reports_failed_sampling(tmp_path):
    taxonomy = two_product_taxonomy(tmp_path)
    taxonomy_file = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(taxonomy_file, index=False)
    out = tmp_path / "failed-capability-run"

    def injected(*args, **kwargs):
        spec = args[1]
        if spec.metabolite == "a":
            return TargetMaxResult(
                spec.exchange_id(), spec.direction.value, 0, 0,
                "time_limit", "injected capability timeout",
            )
        return target_max_solve(*args, **kwargs)

    with patch("cmig.core.search_product.target_max_solve", side_effect=injected):
        rc = main([
            "search", "--taxonomy", str(taxonomy_file), "--targets", "a,b",
            "--multi-metric", "pareto", "--min-size", "1", "--max-size", "1",
            "--top-k", "1", "--allow-failed-run", "--out", str(out),
        ])
    assert rc == 0  # explicit artifact publication; scientific summary remains failed
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["n_candidates_ranked"] == 0
    assert summary["candidate_sampling_status"] == {"A": "failed"}
    assert summary["n_pareto_attempts"] == 3
    assert summary["n_pareto_failed_attempts"] == 1
    evaluation = json.loads((out / "search_evaluations.json").read_text())
    assert [a["phase"] for a in evaluation["pareto_attempts"]] == [
        "baseline", "capability", "capability",
    ]
    assert "search_plot.svg" not in summary["artifacts"]
    assert "search_plot.tiff" not in summary["artifacts"]
    assert not (out / "search_plot.svg").exists()
    assert not (out / "search_plot.tiff").exists()
    inspection = _inspect_run_dir(out)
    assert inspection["status"] == "failed"
    assert inspection["artifact_integrity"] == "verified"
    assert inspection["result_digest"]["match"] is True
    assert inspection["result_digest"]["missing_artifacts"] == []
