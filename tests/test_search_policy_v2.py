"""Scientific regressions from the September search review, with actual LPs."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from random import Random

import pytest

from cmig.core.search import (
    Direction,
    TargetSpec,
    epsilon_constrained_solve,
    joint_target_solve,
    target_max_solve,
)
from cmig.core.search_constraints import GrowthPolicy
from cmig.core.search_ga import _tournament
from cmig.core.search_product import (
    MultiTargetConfig,
    SearchConfig,
    _ComboEval,
    _joint_lp_scales,
    rank_multi_target,
    search_model_pool,
    search_model_pool_multi,
)


def test_pareto_archive_keeps_extremes_independently_of_top_k():
    from dataclasses import replace

    from cmig.core.search_execution import SearchControl

    pd = pytest.importorskip("pandas")

    class Engine:
        def build_community(self, taxonomy, cmig_solver="gurobi"):
            return tradeoff_model()

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
    small = search_model_pool_multi(Engine(), taxonomy, config, control=SearchControl())
    large = search_model_pool_multi(
        Engine(), taxonomy, replace(config, top_k=100), control=SearchControl()
    )
    assert small.pareto_archive == large.pareto_archive
    assert len(small.ranks) == 1 < len(small.pareto_archive)
    vectors = [(row.target_fluxes["a"], row.target_fluxes["b"]) for row in small.pareto_archive]
    assert any(a == pytest.approx(10) and b == pytest.approx(0) for a, b in vectors)
    assert any(a == pytest.approx(0) and b == pytest.approx(20) for a, b in vectors)
    assert all(2 * a + b <= 20 + 1e-7 for a, b in vectors)


def test_minimisation_pareto_sweep_has_relaxed_interior_slices():
    from cmig.core.search_product import _pareto_points_for_members

    pd = pytest.importorskip("pandas")

    class Engine:
        def build_community(self, taxonomy, cmig_solver="gurobi"):
            return tradeoff_model()

    points = _pareto_points_for_members(
        Engine(),
        pd.DataFrame({"id": ["toy"]}),
        ("toy",),
        [TargetSpec("a", Direction.MIN_UPTAKE), TargetSpec("b")],
        capability={"a": 0, "b": 40},
        growth_fraction=0.5,
        solver="gurobi",
        medium_spec=None,
        strict_medium=True,
    )
    assert all(point.fluxes["a"] <= 1e-8 and point.fluxes["b"] >= -1e-8 for point in points)
    assert any(-10 < point.fluxes["a"] < 0 and point.fluxes["b"] > 20 for point in points)


def test_growth_only_baseline_matches_cooperative_growth_optimum():
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.core.search import _community_growth_star
    from cmig.golden_fixture import build_taxonomy

    community = MicomEngine().build_community(build_taxonomy())
    expected = community.cooperative_tradeoff(fraction=1.0).growth_rate
    assert _community_growth_star(community) == pytest.approx(expected, rel=1e-7)


def tradeoff_model():
    cobra = pytest.importorskip("cobra")
    model = cobra.Model("review_tradeoff")
    precursor = cobra.Metabolite("p_c", compartment="c")
    growth_met = cobra.Metabolite("g_c", compartment="c")
    for name, stoich, bounds in (
        ("SOURCE", {precursor: 1}, (0, 20)),
        ("GROWTH_SOURCE", {growth_met: 1}, (0, 1)),
        ("GROWTH", {growth_met: -1}, (0, 1)),
        ("EX_a_m", {precursor: -2}, (-10, 100)),
        ("EX_b_m", {precursor: -1}, (-10, 100)),
    ):
        reaction = cobra.Reaction(name)
        reaction.add_metabolites(stoich)
        reaction.bounds = bounds
        model.add_reactions([reaction])
    model.objective = "GROWTH"
    return model


@pytest.mark.parametrize("direction", list(Direction))
def test_epsilon_direction_domain_matches_joint(direction):
    model = tradeoff_model()
    specs = [TargetSpec("a", direction), TargetSpec("b", direction)]
    result = epsilon_constrained_solve(
        model,
        specs,
        {},
        normalization_scales={"a": 1, "b": 1},
        mu_community=1,
    )
    assert result.status == "optimal"
    for flux in result.target_fluxes.values():
        if direction in (Direction.MAX_SECRETION, Direction.MIN_SECRETION):
            assert flux >= -1e-8
        else:
            assert flux <= 1e-8
    if direction in (Direction.MIN_SECRETION, Direction.MIN_UPTAKE):
        assert all(abs(flux) < 1e-8 for flux in result.target_fluxes.values())


def test_epsilon_mixed_directions_obey_signed_upper_bound():
    model = tradeoff_model()
    result = epsilon_constrained_solve(
        model,
        [TargetSpec("a", Direction.MIN_UPTAKE), TargetSpec("b")],
        {"a": -2},
        normalization_scales={"a": 1, "b": 1},
        mu_community=1,
    )
    assert result.status == "optimal"
    assert -2 - 1e-8 <= result.target_fluxes["a"] <= 1e-8
    assert result.target_fluxes["b"] >= 0


def test_reported_normalized_score_is_the_optimized_affine_score():
    model = tradeoff_model()
    specs = [TargetSpec("a"), TargetSpec("b", weight=2)]
    ranges = {"a": (8, 10), "b": (0, 20)}
    result = joint_target_solve(
        model,
        specs,
        normalization_scales=_joint_lp_scales("normalized_weighted", ranges),
        mu_community=1,
    )
    vertices = [(10, 0), (0, 20), (0, 0)]
    evals = [
        _ComboEval(
            ("optimum",),
            "optimal",
            1,
            result.target_fluxes,
            result.signed_values,
            None,
        )
    ] + [
        _ComboEval(
            (str(i),),
            "optimal",
            1,
            {"a": a, "b": b},
            {"a": a, "b": b},
            None,
        )
        for i, (a, b) in enumerate(vertices)
    ]
    rows, _ = rank_multi_target(evals, specs, normalization_ranges=ranges)
    chosen = next(row for row in rows if row.members == ("optimum",))
    assert all(chosen.weighted_score >= row.weighted_score - 1e-8 for row in rows)


def test_nonviable_gate_is_shared_by_all_target_solvers():
    model = tradeoff_model()
    model.reactions.GROWTH.upper_bound = 0
    specs = [TargetSpec("a"), TargetSpec("b")]
    assert target_max_solve(model, specs[0], mu_community=0).status == "non_viable"
    assert (
        joint_target_solve(
            model,
            specs,
            normalization_scales={"a": 1, "b": 1},
            mu_community=0,
        ).status
        == "non_viable"
    )
    assert (
        epsilon_constrained_solve(
            model,
            specs,
            {},
            normalization_scales={"a": 1, "b": 1},
            mu_community=0,
        ).status
        == "non_viable"
    )


def test_filtered_member_never_receives_a_rank():
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.golden_fixture import build_taxonomy

    taxonomy = build_taxonomy().iloc[:2].copy()
    taxonomy["abundance"] = [1, 1e-8]
    result = search_model_pool(MicomEngine(), taxonomy, SearchConfig(target="ac"))
    assert not result.ranks
    assert len(result.unevaluated) == 1
    failed = result.unevaluated[0]
    assert len(failed.members) == 2 and len(failed.effective_members) == 1
    assert "membership mismatch" in failed.diagnostic


@pytest.mark.parametrize("abundance", [0, -1, float("nan"), float("inf")])
def test_invalid_abundance_is_rejected_before_build(abundance):
    pd = pytest.importorskip("pandas")
    taxonomy = pd.DataFrame({"id": ["a", "b"], "abundance": [1, abundance]})
    with pytest.raises(ValueError, match="abundance"):
        search_model_pool(object(), taxonomy, SearchConfig(target="ac"))


def test_equal_fitness_tournament_has_no_name_based_exclusion():
    rng = Random(7)
    population = [(f"s{i:02}",) for i in range(10)]
    counts = Counter(_tournament(population, lambda _: 0, rng, 3) for _ in range(10000))
    assert set(counts) == set(population)
    assert all(800 < count < 1200 for count in counts.values())


@pytest.mark.parametrize(
    "suffix",
    [
        ".xml",
        ".sbml",
        ".json",
        ".mat",
        ".SBML",
        ".XML",
        ".JSON",
        ".MAT",
        ".xml.gz",
        ".sbml.gz",
        ".XML.GZ",
        ".SBML.GZ",
    ],
)
def test_import_formats_build_real_communities(tmp_path: Path, suffix: str):
    cobra = pytest.importorskip("cobra")
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.core.model_pool import taxonomy_from_model_dir
    from cmig.golden_fixture import build_taxonomy
    from cmig.io.model_import import load_cobra_model

    model = load_cobra_model(build_taxonomy().iloc[0]["file"])
    source = tmp_path / f"strain{suffix}"
    if suffix.lower().endswith(".gz"):
        import gzip
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp:
            uncompressed = Path(temp) / "source.xml"
            cobra.io.write_sbml_model(model, uncompressed)
            source.write_bytes(gzip.compress(uncompressed.read_bytes()))
    elif suffix.lower() == ".json":
        cobra.io.save_json_model(model, source)
    elif suffix.lower() == ".mat":
        cobra.io.save_matlab_model(model, source)
    else:
        cobra.io.write_sbml_model(model, source)
    original = source.read_bytes()
    community = MicomEngine().build_community(taxonomy_from_model_dir(tmp_path))
    assert community.taxa == ["strain"]
    assert source.read_bytes() == original


def test_member_growth_constraints_are_measured_and_restored():
    pytest.importorskip("micom")
    from cmig.core.engine import MicomEngine
    from cmig.golden_fixture import build_taxonomy

    community = MicomEngine().build_community(build_taxonomy())
    result = target_max_solve(
        community,
        TargetSpec("ac"),
        growth_policy=GrowthPolicy(min_member_growth=0.1),
    )
    assert result.status == "optimal"
    assert len(result.member_growth) == 3
    assert all(value >= 0.1 - 1e-8 for value in result.member_growth.values())
    assert all(community.constraints[f"objective_{member}"].lb == 0 for member in community.taxa)
