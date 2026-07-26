"""Round-5 track P3 regressions — I/O, exception handling, reproducibility identity.

Each test here pins a defect that two independent reviewers reproduced and the coordinator
confirmed. They are grouped by the class of wrongness rather than by module, because the same
mistake ("a failed computation is published as a real number") shows up in several commands.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

# ── 1. A failed computation must never be published as a real measurement ─────────────


def test_gene_ko_exception_branch_reports_no_effect_size():
    """CC-2 / opus F2 / codex F5.

    ``_evaluate_ko_target`` has two failure paths for one semantic event ("this knockout could
    not be evaluated"). The "no evaluable consortium" path already returns NaN. The generic
    ``except`` path used to return ``score_delta = -baseline.score`` — a finite, large-magnitude,
    entirely fabricated effect size that lands in ``gene_ko_rankings.csv`` with a rank number.
    """
    from types import SimpleNamespace

    from cmig.cli.main import _evaluate_ko_target

    baseline = SimpleNamespace(score=12.148, target_flux=12.148, community_growth=0.1122)

    def boom(*_args, **_kwargs):
        raise RuntimeError("MICOM community build failed: solver out of memory")

    row = _evaluate_ko_target(
        (0, "iHN637", "b0008"),
        ko_level="gene",
        base_models={"iHN637": SimpleNamespace(copy=boom)},
        sub_taxonomy=None,
        config=None,
        baseline=baseline,
        tmp_dir=Path("."),
        write_sbml_model=None,
        search_model_pool=None,
        engine_factory=lambda: None,
    )

    assert row["evaluation_status"] == "failed"
    for field in (
        "score",
        "score_delta",
        "target_flux",
        "target_flux_delta",
        "community_growth",
        "community_growth_delta",
    ):
        value = float(row[field])
        assert math.isnan(value), (
            f"{field}={value!r} is a fabricated finite effect size for a knockout that was "
            "never evaluated"
        )


def test_abundance_impact_figure_drops_points_that_were_never_solved(tmp_path):
    """CC-2 / opus F1 / codex F6.

    The figure writer filtered only on ``target_abundance`` and then applied ``... or 0.0``, so a
    failed sweep point was drawn as a genuine zero-growth measurement, connected by a line to the
    points that really were solved.
    """
    pytest.importorskip("matplotlib")
    from cmig.cli.main import _abundance_impact_plot_series

    rows = [
        {"target_abundance": 0.1, "community_growth": 0.30, "status": "optimal"},
        {"target_abundance": 0.3, "community_growth": 0.28, "status": "optimal"},
        {"target_abundance": 0.5, "community_growth": None, "status": "failed"},
        {"target_abundance": 0.7, "community_growth": 0.26, "status": "optimal"},
    ]
    plotted, n_dropped = _abundance_impact_plot_series(rows)

    assert n_dropped == 1
    assert [row["target_abundance"] for row in plotted] == [0.1, 0.3, 0.7]
    assert 0.5 not in [row["target_abundance"] for row in plotted]


def test_abundance_impact_failed_point_is_blank_not_zero(tmp_path):
    """CC-2 end-to-end: a solver failure must leave the scientific columns empty, not zero."""
    pytest.importorskip("micom")
    from unittest.mock import patch

    from cmig.cli.main import main
    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = tmp_path / "taxonomy.csv"
    build_pair_taxonomy(tmp_path / "microbes").to_csv(taxonomy, index=False)
    out = tmp_path / "impact"

    real = None
    calls = {"n": 0}

    def flaky(self, community, tradeoff_f, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("injected solver fault")
        return real(self, community, tradeoff_f, **kwargs)

    from cmig.core.engine import MicomEngine

    real = MicomEngine.cooperative_tradeoff
    with patch.object(MicomEngine, "cooperative_tradeoff", flaky):
        rc = main([
            "abundance-impact",
            "--taxonomy", str(taxonomy),
            "--member", "producer",
            "--fractions", "0.2,0.8",
            "--target", "ac",
            "--out", str(out),
        ])
    assert rc in (0, 3)

    payload = json.loads((out / "abundance_impact_summary.json").read_text())
    failed = [row for row in payload["rows"] if row["status"] == "failed"]
    assert failed, "the injected fault did not produce a failed sweep point"
    for row in failed:
        for field in (
            "community_growth",
            "target_member_exchange",
            "community_target_exchange",
            "target_influence_share",
            "target_secretion_share",
            "target_member_contribution",
        ):
            assert row[field] is None, (
                f"{field}={row[field]!r} was fabricated for a point that never solved"
            )

    # Audit note: an earlier version of this asserted `"0.0" not in cells`, which was useless —
    # `_finite_csv` renders 0.0 as "0", so it passed even with the fabricated zeros present. The
    # real contract is that the scientific cells of a failed row are EMPTY, so assert exactly that.
    import csv as _csv

    with (out / "abundance_impact.csv").open(newline="") as handle:
        csv_rows = list(_csv.DictReader(handle))
    failed_csv = [row for row in csv_rows if row["status"] == "failed"]
    assert failed_csv, "no failed row in abundance_impact.csv"
    for row in failed_csv:
        for field in (
            "community_growth",
            "target_member_exchange",
            "community_target_exchange",
            "target_influence_share",
            "target_secretion_share",
            "target_member_contribution",
        ):
            assert row[field] == "", (
                f"failed CSV row published {field}={row[field]!r}; a point that never solved "
                "must leave the cell empty"
            )


def test_gene_ko_summary_status_is_derived_not_a_literal():
    """opus F12(a): ``gene_ko_summary.json`` hardcoded ``"status": "ok"``."""
    from cmig.cli.main import _gene_ko_summary_status

    assert _gene_ko_summary_status([{"evaluation_status": "ok"}]) == "ok"
    assert _gene_ko_summary_status(
        [{"evaluation_status": "ok"}, {"evaluation_status": "failed"}]
    ) == "degraded"
    assert _gene_ko_summary_status([{"evaluation_status": "failed"}]) == "failed"
    assert _gene_ko_summary_status([]) == "failed"


# ── 2. Reproducibility identity (CC-4) ────────────────────────────────────────────────


FROZEN_GOLDEN_SOLVE_RUN_HASH = (
    "29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab"
)
FROZEN_KNOWN_SOLVE_RUN_HASH = (
    "cf3c73d97be5c3555d5d9e228c08e5088661cc6f1ba36fc7a333d2a9b2aaa633"
)


def _frozen_components():
    from cmig.core.manifest import RunHashComponents

    return RunHashComponents(
        model_checksum="micom_test_taxonomy_3",
        medium_checksum="micom_default_medium",
        member_set=["a", "b", "c"],
        abundance={"a": 0.333333, "b": 0.333333, "c": 0.333333},
        bounds={},
        tradeoff_f=0.5,
        solver_setting={"growth_solver": "gurobi", "flux_solver": "gurobi"},
        micom_version="0.39.0",
        cmig_core_version="0.1.0",
        namespace_mapping_decisions=[],
        flux_normalization_method="pfba",
    )


def test_frozen_solve_hash_does_not_move():
    """The CC-4 guard rail: the backward-compatible canonicalization must preserve every value
    that was already exactly six-decimal, which is what the frozen fixtures contain."""
    from cmig.core.manifest import compute_run_hash

    assert compute_run_hash(_frozen_components()) == FROZEN_KNOWN_SOLVE_RUN_HASH


# Every shipped golden variant, not just gurobi. Round-5 round 1 pinned only gurobi and a real
# regression slipped through: the osqp golden hashes at 4 decimals while its components are
# pre-rounded at 6, so the new canonicalization moved it from a422eb89… to 6a30a02a… in silence.
FROZEN_GOLDEN_RUN_HASHES = {
    "gurobi": "29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab",
    "osqp": "a422eb89d019f917f7fc334db8e9a2eff7d89ce49031ccbf215df7bd404d3d9d",
}


def _golden_config(solver: str) -> dict:
    config = Path(f"fixtures/community_3_member/expected/{solver}/config.json")
    if not config.exists():
        pytest.skip(f"{solver} golden fixture not present")
    return json.loads(config.read_text())


@pytest.mark.parametrize("solver", sorted(FROZEN_GOLDEN_RUN_HASHES))
def test_frozen_golden_fixture_config_hash_does_not_move(solver):
    assert _golden_config(solver)["run_hash"] == FROZEN_GOLDEN_RUN_HASHES[solver]


@pytest.mark.parametrize("solver", sorted(FROZEN_GOLDEN_RUN_HASHES))
def test_shipped_golden_components_still_hash_to_their_stored_value(solver):
    """The check that would have caught the osqp regression immediately.

    Recompute the hash from the *stored* components at the *stored* decimals. This needs no
    solver and no re-solve, so it is a pure serialization-drift gate: if the canonicalization
    changes in a way that moves a published hash, this fails.
    """
    from cmig.core.manifest import RunHashComponents, compute_run_hash

    config = _golden_config(solver)
    components = RunHashComponents(**config["components"])
    recomputed = compute_run_hash(components, config["golden_decimals"])
    assert recomputed == FROZEN_GOLDEN_RUN_HASHES[solver], (
        f"{solver}: stored components no longer hash to the published run_hash at "
        f"decimals={config['golden_decimals']}"
    )


@pytest.mark.parametrize("solver", sorted(FROZEN_GOLDEN_RUN_HASHES))
def test_golden_builder_rounds_at_the_decimals_its_hash_uses(solver):
    """The invariant the osqp regression violated.

    A component the builder pre-rounds must be a *fixed point at the decimals the hash uses*, not
    at some other constant. `_run_hash_components` rounded at golden.DEFAULT_DECIMALS (6) while
    osqp hashes at VARIANT_DECIMALS['osqp'] (4); `round(0.333333, 4) != 0.333333`, so the value
    took the lossless branch and the published hash moved.
    """
    pytest.importorskip("micom")
    from cmig.core.manifest import compute_run_hash
    from cmig.golden_fixture import VARIANT_DECIMALS, _run_hash_components, solve

    decimals = VARIANT_DECIMALS[solver]
    result, _bundle = solve(solver)
    components = _run_hash_components(result, decimals)

    for member, value in components.abundance.items():
        assert round(value, decimals) == value, (
            f"{solver}: abundance[{member}]={value!r} is not a fixed point at decimals="
            f"{decimals}, so it will serialize losslessly and move the published hash"
        )
    assert compute_run_hash(components, decimals) == FROZEN_GOLDEN_RUN_HASHES[solver]


def test_solve_hash_separates_inputs_below_the_rounding_floor():
    """codex F1. ``round(x, 6)`` maps everything below 1e-6 to 0.0, so a solver tolerance of
    1e-7 and one of 4e-7 — which give different answers — shared a run_hash."""
    from dataclasses import replace

    from cmig.core.manifest import compute_run_hash

    base = _frozen_components()
    lo = compute_run_hash(replace(base, bounds={"R": [0.0, 1e-7]}))
    hi = compute_run_hash(replace(base, bounds={"R": [0.0, 4e-7]}))
    assert lo != hi, "distinct answer-determining bounds still collide on one run_hash"

    lo = compute_run_hash(replace(base, tradeoff_f=0.5000001))
    hi = compute_run_hash(replace(base, tradeoff_f=0.5000004))
    assert lo != hi, "distinct tradeoff fractions still collide on one run_hash"


def test_six_decimal_exact_values_keep_their_current_serialization():
    """The backward-compatibility property that keeps the frozen hashes still.

    Anything already representable in six decimals must serialize as the plain number it does
    today; only values that the old rule would have destroyed get the lossless form.
    """
    from cmig.core.manifest import canonicalize_floats

    for value in (0.5, 0.333333, 0.0, -1.25, 123456.75):
        assert canonicalize_floats(value) == round(value, 6) + 0.0
    assert canonicalize_floats(1e-7) != canonicalize_floats(4e-7)
    assert canonicalize_floats(float("nan")) == "NaN"
    assert canonicalize_floats(float("inf")) == "Infinity"
    assert canonicalize_floats(-0.0) == 0.0


def test_workflow_envelope_separates_sub_micro_growth_fraction_and_weights():
    """CC-4 step 1 — the realistic-risk collisions live in the workflow envelope."""
    from cmig.core.workflow_manifest import compute_workflow_hash

    def components(growth_fraction, weight, tolerance):
        return {
            "workflow_kind": "model_pool_search",
            "cmig_core_version": "0.1.0",
            "dependency_versions": {"micom": "0.39.0"},
            "solver_setting": {"solver": "gurobi", "tolerance": tolerance},
            "model_checksum": "sha256:abc",
            "medium": {"checksum": "sha256:def"},
            "target_spec": {"target": "but", "weights": {"but": weight}},
            "search_spec": {"strategy": "exhaustive"},
            "growth_fraction": growth_fraction,
        }

    a = compute_workflow_hash("model_pool_search", components(0.5000001, 1e-7, 1.1e-7))
    b = compute_workflow_hash("model_pool_search", components(0.5000004, 4e-7, 4.4e-7))
    assert a != b, (
        "the workflow envelope still collides on growth_fraction / target weight / solver "
        "tolerance differences below 1e-6"
    )


def test_workflow_envelope_schema_version_records_the_canonicalization_change():
    from cmig.core.workflow_manifest import WORKFLOW_MANIFEST_SCHEMA_VERSION

    assert WORKFLOW_MANIFEST_SCHEMA_VERSION == "1.1", (
        "changing the hash serialization must bump the schema version so a stored hash is "
        "never silently compared across two different rules"
    )


def test_a_string_cannot_impersonate_a_lossless_float_token():
    """The lossless float form is a string, so a string component could in principle equal it.

    No reachable path produces such a component today, but "unreachable" is not "impossible" and
    this is the wrong-number class, so the mapping is made injective instead of merely improbable.
    """
    from cmig.core.manifest import canonicalize_floats

    float_token = canonicalize_floats(1.0 / 3.0)
    assert isinstance(float_token, str) and float_token.startswith("f64:")
    assert canonicalize_floats(float_token) != float_token, (
        "a string equal to a float's lossless token still serializes identically to that float"
    )
    # The escape is itself escaped, so the scheme stays reversible rather than merely shifting
    # the collision one level up.
    assert canonicalize_floats("str:f64:1.5") != canonicalize_floats("f64:1.5")
    # Ordinary strings are untouched — this is what keeps every existing hash still.
    for ordinary in ("sha256:abc", "micom_default_medium", "pfba", "gurobi", "medium:xyz", ""):
        assert canonicalize_floats(ordinary) == ordinary


def test_solve_level_abundance_collision_is_a_known_documented_limit():
    """V1, honest bound on the CC-4 claim.

    "Every sub-1e-6 input now separates" is NOT true, and this pins where it stops being true.
    ``build_run_components`` deliberately pre-rounds the *solve-derived* abundance vector to
    absorb micom's noise, so two solves whose abundances differ below the sixth decimal still
    share a run_hash. That rounding is load-bearing: removing it would move the frozen fixture
    hashes, which are a published contract. Recorded as a limit rather than silently left.

    Everything the reviewers actually raised — bounds, tradeoff_f, growth_fraction, target
    weights, solver tolerance, medium uptake — does separate, and the neighbouring tests pin that.
    """
    from cmig.io.solve_output import build_run_components

    def components(abundance_a):
        result = SimpleNamespace(
            abundances={"a": abundance_a, "b": 1.0 - abundance_a},
            members=["a", "b"],
            growth_solver="gurobi",
            flux_solver="gurobi",
            flux_normalization_method="pfba",
        )
        return build_run_components(
            result, model_checksum="m", medium_checksum="d", tradeoff_f=0.5,
            micom_version="0.39.0", dependency_versions={},
        )

    from cmig.core.manifest import compute_run_hash

    # KNOWN LIMIT: below the sixth decimal the abundance vector is not distinguished.
    assert compute_run_hash(components(0.5)) == compute_run_hash(components(0.5 + 1e-9))
    # But a difference the rounding can represent is still separated.
    assert compute_run_hash(components(0.5)) != compute_run_hash(components(0.5001))


def test_medium_checksum_separates_uptake_values_below_the_rounding_floor():
    """V1. ``medium_checksum`` rounded uptake to 6 decimals, so two genuinely different media —
    a *user-supplied, answer-determining* input — produced one checksum and therefore one
    run_hash. Same defect class as CC-4, hiding in the checksum builder instead of the
    canonicalizer."""
    from cmig.core.medium_spec import MediumSpec, medium_checksum

    lo = MediumSpec(uptake={"EX_glc__D_e": 1e-7})
    hi = MediumSpec(uptake={"EX_glc__D_e": 4e-7})
    assert medium_checksum(lo) != medium_checksum(hi), (
        "two different media still share one medium_checksum"
    )

    near = MediumSpec(uptake={"EX_glc__D_e": 10.0})
    near2 = MediumSpec(uptake={"EX_glc__D_e": 10.0 + 1e-9})
    assert medium_checksum(near) != medium_checksum(near2)

    # Identical media are still identical, and the format is unchanged.
    assert medium_checksum(lo) == medium_checksum(MediumSpec(uptake={"EX_glc__D_e": 1e-7}))
    assert medium_checksum(lo).startswith("medium:")
    assert len(medium_checksum(lo).removeprefix("medium:")) == 64
    assert medium_checksum(None) == "micom_default_medium"


def test_sweep_cache_key_never_replays_one_point_as_another():
    """V2 [P0]. ``_sweep_condition_content_key`` rounded ``tradeoff_f`` to 6 decimals and
    ``abundance`` to 9, so two distinct sweep points shared one cache key. On the second point the
    solve was **skipped** and the first point's value *and run_hash* were republished under the
    second point's condition_id — a number attributed to inputs it was never computed for.

    The function's own docstring claims it is "a faithful superset of the run_hash components" so
    that "replaying the cached result is exact rather than an approximation". This pins that claim.
    """
    pd = pytest.importorskip("pandas")
    from cmig.cli.main import _sweep_condition_content_key

    def key(tradeoff_f=0.5, abundance=0.5):
        taxonomy = pd.DataFrame([
            {"id": "a", "abundance": abundance},
            {"id": "b", "abundance": 1.0 - abundance},
        ])
        return _sweep_condition_content_key(
            model_checksum="sha256:x",
            taxonomy_variant=taxonomy,
            solver="gurobi",
            tradeoff_f=tradeoff_f,
            medium_path=None,
            bounds=None,
            fva=False,
            fva_metabolites=None,
            namespace_decisions=None,
        )

    assert key(tradeoff_f=0.5000001) != key(tradeoff_f=0.5000004), (
        "two distinct tradeoff fractions share a sweep cache key — the second point replays the "
        "first point's solve"
    )
    assert key(tradeoff_f=0.5) != key(tradeoff_f=0.5000004)
    assert key(abundance=0.5) != key(abundance=0.5 + 1e-10), (
        "two distinct abundance vectors share a sweep cache key"
    )
    # Identical conditions must still hit the cache, or the sweep stops deduplicating at all.
    assert key() == key()
    assert key(tradeoff_f=0.7, abundance=0.25) == key(tradeoff_f=0.7, abundance=0.25)


def test_sweep_parquet_records_the_tradeoff_it_was_actually_given():
    """V2, artifact half. ``axis_tradeoff_f`` rounded a determining input before recording it, so
    two different sweep points were written to sweep.parquet as the same 0.5 — the artifact could
    not reveal the substitution even in principle."""
    from cmig.core.sweep import _axis_tradeoff_f

    assert _axis_tradeoff_f({"tradeoff_f": 0.5000001}) != _axis_tradeoff_f(
        {"tradeoff_f": 0.5000004}
    )
    assert _axis_tradeoff_f({"tradeoff_f": 0.5}) == 0.5
    assert _axis_tradeoff_f({"tradeoff_f": float("nan")}) is None
    assert _axis_tradeoff_f({"tradeoff_f": float("inf")}) is None
    assert _axis_tradeoff_f({}) is None


def test_failed_gene_ko_row_is_not_given_a_rank_or_counted_as_evaluated():
    """V4. Every scientific field of a failed knockout is blank, but the row was still numbered
    ``rank=1`` and counted in the evaluated total, so the CSV asserted an ordinal position for a
    knockout that was never evaluated.

    Merge note (round-5 integration): tracks P1 and P3 fixed this same defect independently and
    reached the same conclusion, differing only in the sentinel for "no rank" — P3 wrote a blank
    cell, P1 wrote ``0``. Integration kept ``0`` and P1's ``_ko_ranked_rows``, because every other
    ranked artifact CMIG publishes (all four search paths, see ``core/search_product.py``)
    already uses ``rank 0 == no rank`` with the unevaluated rows in their own block. A consumer
    should need one rule for "was this row measured?", not one per subcommand. The property this
    test asserts is unchanged; only the sentinel it reads moved.
    """
    from cmig.cli.main import _ko_ranked_rows, _n_ko_evaluated

    rows = [
        {"evaluation_status": "ok", "member": "m", "gene": "g1"},
        {"evaluation_status": "failed", "member": "m", "gene": "g2"},
        {"evaluation_status": "ok", "member": "m", "gene": "g3"},
    ]
    ranks = [rank for rank, _ in _ko_ranked_rows(rows)]
    assert ranks[0] == 1
    assert ranks[1] == 0, "a failed knockout was given an ordinal rank"
    assert ranks[2] == 2, "a failed row consumed a rank number from a real result"
    assert _n_ko_evaluated(rows) == 2, "a failed knockout was counted as evaluated"

    # A screen in which everything failed has no rank 1 at all.
    all_failed = [{"evaluation_status": "failed", "member": "m", "gene": "g"}]
    assert [rank for rank, _ in _ko_ranked_rows(all_failed)] == [0]
    assert _n_ko_evaluated(all_failed) == 0


def test_gene_ko_artifacts_do_not_rank_a_knockout_that_failed(tmp_path):
    """V4, at the writer rather than the helper.

    Audit note: testing ``_ko_ranked_rows`` alone would still pass if the CSV/JSON writer went
    back to ``enumerate(rows, start=1)``. This drives the real writer and reads the real
    artifacts.

    Merge note: see the sentinel discussion on
    ``test_failed_gene_ko_row_is_not_given_a_rank_or_counted_as_evaluated``. Integration also
    adopted P1's stronger JSON shape — an unevaluated knockout is not in ``top_ranked`` at all,
    it is published under ``unevaluated`` — because the GUI table and ``_resolve_run_status``
    both iterate ``top_ranked`` without inspecting ``rank``, so a failure sitting there with a
    null ordinal is still read as a result. The assertion below is therefore made on
    ``unevaluated`` rather than on a null rank inside ``top_ranked``; it is the same claim, made
    where a careless consumer cannot miss it.
    """
    import csv as _csv
    from types import SimpleNamespace

    from cmig.cli.main import _write_gene_ko_search_outputs

    def row(gene, status, score):
        return {
            "gene": gene, "member": "m", "evaluation_status": status,
            "score": score, "score_delta": score, "target_flux": score,
            "target_flux_delta": score, "community_growth": score,
            "community_growth_delta": score,
            "status": "optimal" if status == "ok" else "failed", "diagnostic": "",
        }

    rows = [row("g1", "ok", 1.0), row("g2", "failed", float("nan")), row("g3", "ok", 0.5)]
    baseline = SimpleNamespace(
        score=2.0, target_flux=2.0, community_growth=0.3, status="optimal", diagnostic=None
    )
    _write_gene_ko_search_outputs(
        rows, tmp_path, baseline=baseline, members=("m",), target="ac", member="m",
        n_genes_evaluated=2, n_genes_attempted=3, n_genes_total=10, ko_level="gene",
        gene_selection="explicit", seed=0, direction="max_secretion", warnings=[],
    )

    with (tmp_path / "gene_ko_rankings.csv").open(newline="") as handle:
        csv_rows = {r["gene"]: r for r in _csv.DictReader(handle)}
    assert csv_rows["g1"]["rank"] == "1"
    assert csv_rows["g2"]["rank"] == "0", "a failed knockout was numbered in gene_ko_rankings.csv"
    assert csv_rows["g2"]["score_delta"] == "", "a failed knockout carried a fabricated delta"
    assert csv_rows["g3"]["rank"] == "2", "a failed row consumed a rank number"

    payload = json.loads((tmp_path / "gene_ko_summary.json").read_text())
    ranked = {entry["gene"]: entry["rank"] for entry in payload["top_ranked"]}
    assert ranked == {"g1": 1, "g3": 2}, "a failed knockout entered top_ranked"
    assert [entry["gene"] for entry in payload["unevaluated"]] == ["g2"]
    assert payload["n_genes_evaluated"] == 2
    assert payload["n_genes_attempted"] == 3
    assert payload["status"] == "degraded"


def test_golden_verify_fails_when_a_published_run_hash_moves(tmp_path):
    """The gate that was missing. ``golden verify`` compared only micom_version, so the osqp
    hash regression passed it. It must now fail when a published run_hash no longer matches the
    components it was derived from — and this test proves the gate fires, not just that it is
    green today."""
    pytest.importorskip("micom")
    from cmig.golden_fixture import (
        GoldenVersionMismatch,
        assert_golden_versions,
        verify_golden_versions,
    )

    # A faithful copy of the shipped fixture passes.
    src = Path("fixtures/community_3_member/expected")
    if not src.exists():
        pytest.skip("golden fixtures not present")
    base = tmp_path / "community_3_member"
    (base / "expected").mkdir(parents=True)
    for solver in ("gurobi", "osqp"):
        dst = base / "expected" / solver
        dst.mkdir()
        (dst / "config.json").write_text((src / solver / "config.json").read_text())
    report = verify_golden_versions(base)
    assert all(r["hash_ok"] for r in report.values())
    assert_golden_versions(base)

    # Now move a published hash the way a serialization change would.
    cfg_path = base / "expected" / "osqp" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["components"]["abundance"] = {
        k: v + 1e-9 for k, v in cfg["components"]["abundance"].items()
    }
    cfg_path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n")

    report = verify_golden_versions(base)
    assert report["osqp"]["hash_ok"] is False
    assert report["osqp"]["ok"] is False
    assert report["gurobi"]["hash_ok"] is True
    with pytest.raises(GoldenVersionMismatch, match="run_hash"):
        assert_golden_versions(base)


def test_atomic_write_text_never_destroys_the_previous_file(tmp_path):
    """V3. The shared helper the artifact writers now use."""
    from unittest.mock import patch

    from cmig.io.atomic import atomic_write_text

    target = tmp_path / "artifact.json"
    atomic_write_text(target, '{"v": 1}\n')
    assert target.read_text() == '{"v": 1}\n'

    for injection in ("cmig.io.atomic.os.fsync", "cmig.io.atomic.os.replace"):
        with patch(injection, side_effect=OSError("[Errno 28] No space left on device")):
            with pytest.raises(OSError):
                atomic_write_text(target, '{"v": 2}\n')
        assert target.read_text() == '{"v": 1}\n', f"{injection} destroyed the previous file"
        assert [p.name for p in tmp_path.iterdir()] == ["artifact.json"], "temp file left behind"

    atomic_write_text(target, '{"v": 3}\n')
    assert target.read_text() == '{"v": 3}\n'


def test_render_provenance_and_cli_json_survive_a_failed_rewrite(tmp_path):
    """V3, at the two call sites the reviewers named."""
    from unittest.mock import patch

    from cmig.cli.main import _write_json_or_print
    from cmig.render.provenance import write_render_provenance

    figure = tmp_path / "figure.svg"
    figure.write_text("<svg/>")
    spec_path = tmp_path / "figure.svg.figure_spec.json"
    spec_path.write_text("{}\n")
    sidecar = write_render_provenance(
        figure, renderer="matplotlib", input_sha256="a" * 64,
        input_serialization="canonical-json-v1", spec_path=spec_path,
    )
    good_provenance = sidecar.read_text()

    _write_json_or_print({"status": "ok"}, str(tmp_path), "summary.json")
    good_summary = (tmp_path / "summary.json").read_text()

    with patch("cmig.io.atomic.os.replace", side_effect=OSError("injected")):
        with pytest.raises(OSError):
            write_render_provenance(
                figure, renderer="matplotlib", input_sha256="b" * 64,
                input_serialization="canonical-json-v1", spec_path=spec_path,
            )
        with pytest.raises(OSError):
            _write_json_or_print({"status": "degraded"}, str(tmp_path), "summary.json")

    assert sidecar.read_text() == good_provenance
    assert (tmp_path / "summary.json").read_text() == good_summary


# ── 3. Artifact hygiene ───────────────────────────────────────────────────────────────


def test_rerun_removes_the_previous_runs_optional_search_artifact(tmp_path):
    """CC-3 / opus F3. ``search_unevaluated.csv`` is written only when a run has unevaluable
    candidates, and nothing removed a previous run's copy, so a directory could assert that the
    current run's rank-1 member was unevaluable."""
    from cmig.io.solve_output import prune_stale_artifacts

    out = tmp_path / "run"
    out.mkdir()
    (out / "search_unevaluated.csv").write_text("members,status\niHN637,missing\n")
    (out / "search_rankings.csv").write_text("rank,members\n1,iHN637\n")

    removed = prune_stale_artifacts(
        out,
        known={"search_unevaluated.csv", "search_rankings.csv", "pool_diagnostics.csv"},
        written={"search_rankings.csv"},
    )

    assert removed == ["search_unevaluated.csv"]
    assert not (out / "search_unevaluated.csv").exists()
    assert (out / "search_rankings.csv").exists()


def test_search_rerun_into_the_same_directory_leaves_no_orphan(tmp_path):
    """End-to-end form of CC-3 against the real writer."""
    pytest.importorskip("micom")
    from types import SimpleNamespace

    import pandas as pd

    from cmig.cli.main import _write_search_outputs

    taxonomy = pd.DataFrame([{"id": "m1", "file": "m1.xml"}])
    out = tmp_path / "run"

    def result(unevaluated):
        return SimpleNamespace(
            ranks=[],
            unevaluated=unevaluated,
            target="ac",
            target_exchange="EX_ac_m",
            direction="max_secretion",
            strategy="exhaustive",
            n_pool_members=1,
            n_candidates_total=1,
            n_candidates_evaluated=1,
            warnings=[],
        )

    bad = SimpleNamespace(members=("m1",), status="missing", diagnostic="no target")
    _write_search_outputs(result([bad]), taxonomy, [], out)
    assert (out / "search_unevaluated.csv").exists()

    _write_search_outputs(result([]), taxonomy, [], out)
    assert not (out / "search_unevaluated.csv").exists(), (
        "a previous run's search_unevaluated.csv survived into a run that declared none"
    )


def test_workflow_manifest_write_failure_keeps_the_previous_manifest(tmp_path):
    """opus F4 / codex F8. ``write_text`` truncates first, so a failure mid-write destroyed the
    only reproducibility record the run had."""
    from unittest.mock import patch

    from cmig.core.workflow_manifest import write_workflow_manifest

    components = {
        "workflow_kind": "dfba",
        "cmig_core_version": "0.1.0",
        "dependency_versions": {"micom": "0.39.0"},
        "solver_setting": {"solver": "gurobi"},
        "model_checksum": "sha256:abc",
        "medium": {"checksum": "sha256:def"},
        "dfba_spec": {"steps": 10},
    }
    write_workflow_manifest(tmp_path, "dfba", components)
    before = (tmp_path / "manifest.json").read_text()
    assert json.loads(before)["run_hash"]

    # Two ways the write can die: part-way through the bytes (disk full at flush) and at the
    # final swap. Neither may touch the previous manifest, and neither may leave a temp file.
    for target in ("cmig.core.workflow_manifest.os.fsync",
                   "cmig.core.workflow_manifest.os.replace"):
        with patch(target, side_effect=OSError("[Errno 28] No space left on device")):
            with pytest.raises(OSError):
                write_workflow_manifest(
                    tmp_path, "dfba", {**components, "dfba_spec": {"steps": 20}}
                )

        after = (tmp_path / "manifest.json").read_text()
        assert after == before, f"a failure at {target} destroyed the previous manifest"
        assert json.loads(after)["run_hash"]
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".manifest.")]
        assert leftovers == [], f"temporary files left behind by {target}: {leftovers}"

    # And the happy path still replaces it.
    write_workflow_manifest(tmp_path, "dfba", {**components, "dfba_spec": {"steps": 20}})
    assert (tmp_path / "manifest.json").read_text() != before


# ── 4. Exception handlers that invented a scientific claim ────────────────────────────


def test_objective_inspection_failure_is_not_reported_as_a_zero_objective():
    """codex F3. Any exception from ``linear_reaction_coefficients`` became the scientific claim
    "no objective reaction detected; this model cannot report growth"."""
    from unittest.mock import patch

    from cmig.io.model_import import _biomass_reactions

    # Audit note: this used to assert only `pytest.raises(Exception)`, which would have been
    # satisfied by any unrelated failure (a bad import, a typo). Assert that the *injected* error
    # is the one that propagates, and that a healthy model still returns its objective terms.
    model = object()
    for error in (RuntimeError("solver"), ValueError("bad objective"), AttributeError("drift")):
        with patch("cobra.util.solver.linear_reaction_coefficients", side_effect=error):
            with pytest.raises(type(error)) as excinfo:
                _biomass_reactions(model)
            assert str(error) in str(excinfo.value)

    # The success path is untouched: no objective is still an empty list, not an exception.
    class _Rxn:
        def __init__(self, rid):
            self.id = rid

    with patch("cobra.util.solver.linear_reaction_coefficients", return_value={}):
        assert _biomass_reactions(model) == []
    with patch(
        "cobra.util.solver.linear_reaction_coefficients",
        return_value={_Rxn("BIOMASS"): 1.0},
    ):
        assert _biomass_reactions(model) == ["BIOMASS"]


def test_absent_exchange_is_blocked_but_a_backend_error_is_not_swallowed():
    """codex F4. ``_is_blocked`` treated *every* lookup failure as "nutrient unavailable", so an
    unrelated backend error silently produced a different minimal medium."""
    from types import SimpleNamespace

    from cmig.core.medium import _is_blocked

    class Reactions:
        def __init__(self, error):
            self._error = error

        def get_by_id(self, _ex_id):
            raise self._error

    # A genuinely absent reaction is still "unavailable".
    assert _is_blocked(SimpleNamespace(reactions=Reactions(KeyError("EX_h2o_e"))), "EX_h2o_e")

    # Anything else must surface rather than silently drop a nutrient.
    for error in (RuntimeError("backend"), OSError("io"), TypeError("api drift")):
        with pytest.raises(type(error)):
            _is_blocked(SimpleNamespace(reactions=Reactions(error)), "EX_h2o_e")


def test_renderer_csv_does_not_zero_small_fluxes():
    """opus F10 / codex F2. The CSVs handed to R used ``.6f`` — six decimal *places* — so a flux
    of 3.7e-7 arrived as ``0.000000`` while its ``label`` column still read "secretion"."""
    from cmig.render.client import _csv_cell as profile_cell
    from cmig.render.composer import _csv_cell as panel_cell

    for cell, col in ((profile_cell, "net_flux"), (panel_cell, "value")):
        for value in (3.7e-7, 1e-8, -4.9e-7):
            rendered = cell(col, value)
            assert float(rendered) != 0.0, (
                f"{cell.__module__}._csv_cell turned {value!r} into {rendered!r}"
            )
            # and it still round-trips to the same sign and order of magnitude
            assert (float(rendered) > 0) == (value > 0)

        # Non-finite values are still blanked rather than becoming a fake zero.
        assert cell(col, float("nan")) == ""
        assert cell(col, float("inf")) == ""
        assert cell(col, None) == ""
        # Ordinary magnitudes are unchanged in value.
        assert float(cell(col, 123.456789)) == pytest.approx(123.456789)


# ── 5. Input validation ───────────────────────────────────────────────────────────────


def test_store_rejects_a_run_hash_that_is_not_a_sha256(tmp_path):
    """codex F13: ``FileSystemStore.record_run`` built ``root / run_hash`` from an unchecked
    string, so ``../escaped`` created a directory outside the store root."""
    from cmig.core.engine import SolveResult
    from cmig.service.store import FileSystemStore

    root = tmp_path / "store"
    store = FileSystemStore(root)
    result = SolveResult(1.0, {}, {}, {}, {}, "optimal", "full", "gurobi", "gurobi")

    for bad in ("../escaped", "/tmp/escaped", "NOTAHASH", "a" * 63, "A" * 64):
        with pytest.raises(ValueError):
            store.record_run(bad, result)
    assert not (root.parent / "escaped").exists()

    good = "0" * 64
    store.record_run(good, result)
    assert (root / good).is_dir()


def test_malformed_taxonomy_and_parquet_give_a_message_not_a_traceback(tmp_path, capsys):
    """codex F10: ``pd.read_csv`` ran outside the guarded block and ``render-figure`` caught only
    ``OSError``, so an empty CSV or a corrupt parquet produced a raw library traceback."""
    pytest.importorskip("micom")
    from cmig.cli.main import main

    empty = tmp_path / "empty.csv"
    empty.write_text("")
    rc = main([
        "solve", "--taxonomy", str(empty), "--assume-bigg-namespace",
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2
    assert "taxonomy CSV" in capsys.readouterr().err

    run_dir = tmp_path / "badrun"
    run_dir.mkdir()
    for name in ("nodes.parquet", "edges.parquet", "profile.parquet"):
        (run_dir / name).write_bytes(b"")
    rc = main([
        "render-figure", "--run-dir", str(run_dir), "--renderer", "matplotlib",
        "--out", str(tmp_path / "x.svg"),
    ])
    assert rc == 2
    assert "failed to read run" in capsys.readouterr().err


def test_inspect_run_reports_a_corrupt_manifest_instead_of_calling_it_unknown(tmp_path, capsys):
    """codex F11: an empty / truncated / wrong-type manifest.json was indistinguishable from a
    run that simply had no manifest, and ``inspect-run`` exited 0."""
    from cmig.cli.main import main

    for content in ("[]", "{", ""):
        run_dir = tmp_path / f"bad_{len(content)}_{content[:1] or 'empty'}"
        run_dir.mkdir()
        (run_dir / "manifest.json").write_text(content)
        rc = main(["inspect-run", "--run-dir", str(run_dir), "--format", "json"])
        assert rc == 2, f"corrupt manifest {content!r} was accepted with rc={rc}"
        err = capsys.readouterr().err
        assert "manifest.json" in err
