"""Round-5 P1 (domain accuracy) regressions.

Each test here pins a defect that produced a *silently wrong published number*. They are grouped
by the coordinator's finding id so a future reader can trace the contract back to the review.

No solver is required for the medium/namespace units — plain cobra Models only.
"""

from __future__ import annotations

from pathlib import Path

import pytest

cobra = pytest.importorskip("cobra")

from cmig.core.medium_spec import (  # noqa: E402
    MediumSpec,
    apply_medium,
    apply_medium_checked,
    effective_medium_by_metabolite,
    unknown_medium_exchanges,
)
from cmig.core.namespace import _normalize_metabolite_id  # noqa: E402


def _model(name: str, exchanges: dict[str, float]) -> cobra.Model:
    """Model whose exchanges are open (bound>0) or closed (bound==0), like a real GEM."""
    model = cobra.Model(name)
    reactions = []
    for exchange_id, open_uptake in exchanges.items():
        metabolite = cobra.Metabolite(exchange_id.removeprefix("EX_"), compartment="e")
        reaction = cobra.Reaction(exchange_id)
        reaction.add_metabolites({metabolite: -1})
        reaction.bounds = (-open_uptake, 1000.0)
        reactions.append(reaction)
    model.add_reactions(reactions)
    return model


# ─────────────────────────────────────────────────────────────────────────────────
# CC-11 — a custom medium was silently not applied.
#
# `apply_medium_checked` gated on `dict(model.medium)`, which enumerates only the *currently open*
# uptakes. A closed exchange could therefore never be opened: ~90% of nutrients (acetate, butyrate,
# lactate, succinate, glycerol) were unreachable. With `--allow-unknown-medium` they were silently
# dropped while the manifest still stamped the requested medium_checksum and minted a distinct
# run_hash — publishing a run as being on a medium it never used.
# ─────────────────────────────────────────────────────────────────────────────────


def test_checked_medium_opens_a_currently_closed_exchange():
    """The core defect: a nutrient the model *has* but currently keeps shut must be openable."""
    model = _model("member", {"EX_ac_e": 0.0, "EX_glc__D_e": 10.0})
    original, unknown = apply_medium_checked(
        model, MediumSpec(uptake={"EX_ac_e": 7.0}), strict=True
    )
    assert unknown == []
    assert model.reactions.EX_ac_e.lower_bound == pytest.approx(-7.0)
    assert effective_medium_by_metabolite(model)["ac"] == pytest.approx(7.0)
    assert "EX_ac_e" not in original            # it really was closed before


def test_checked_medium_strict_no_longer_lies_about_a_present_exchange():
    """`strict=True` used to raise 'not present in the target model' for a present reaction."""
    model = _model("member", {"EX_ac_e": 0.0})
    apply_medium(model, MediumSpec(uptake={"EX_ac_e": 3.0}))   # strict=True, must not raise
    assert model.reactions.EX_ac_e.lower_bound == pytest.approx(-3.0)


def test_checked_medium_still_refuses_a_genuinely_absent_metabolite():
    model = _model("member", {"EX_glc__D_e": 10.0})
    with pytest.raises(ValueError, match="no exchange reaction|no counterpart"):
        apply_medium_checked(model, MediumSpec(uptake={"EX_fru_e": 5.0}), strict=True)


def test_checked_medium_permissive_reports_only_truly_absent_metabolites():
    model = _model("member", {"EX_ac_e": 0.0, "EX_glc__D_e": 10.0})
    _original, unknown = apply_medium_checked(
        model, MediumSpec(uptake={"EX_ac_e": 7.0, "EX_fru_e": 5.0}), strict=False
    )
    assert unknown == ["EX_fru_e"]                       # fru genuinely absent
    assert model.reactions.EX_ac_e.lower_bound == pytest.approx(-7.0)   # ac WAS applied


def test_checked_medium_bridges_the_m_to_e_namespace():
    """A community preset (`EX_*_m`) applied to a member model (`EX_*_e`) must reach it.

    Before the fix this applied to *nothing* while the caller recorded a custom medium_checksum.
    """
    model = _model("member", {"EX_ac_e": 0.0, "EX_glc__D_e": 10.0})
    _original, unknown = apply_medium_checked(
        model, MediumSpec(uptake={"EX_ac_m": 7.0, "EX_glc__D_m": 5.0}), strict=True
    )
    assert unknown == []
    assert model.reactions.EX_ac_e.lower_bound == pytest.approx(-7.0)
    assert model.reactions.EX_glc__D_e.lower_bound == pytest.approx(-5.0)


def test_unknown_medium_exchanges_agrees_with_apply():
    """The pre-flight query and the applier must not disagree about what is unknown."""
    model = _model("member", {"EX_ac_e": 0.0, "EX_glc__D_e": 10.0})
    spec = MediumSpec(uptake={"EX_ac_m": 7.0, "EX_fru_m": 5.0})
    assert unknown_medium_exchanges(model, spec) == ["EX_fru_m"]
    _original, unknown = apply_medium_checked(model, spec, strict=False)
    assert unknown == unknown_medium_exchanges(model, spec)


def test_checked_and_translated_media_agree_exactly():
    """One medium semantics across the product: the same file must mean the same physics.

    Measured divergence before the fix: community growth 0.881561 via `solve`/`search`
    (apply_medium_checked) vs 1.125065 via `strain-growth` (apply_medium_translated) — 27.6% apart.
    """
    from cmig.core.medium_spec import apply_medium_translated

    spec = MediumSpec(uptake={"EX_ac_m": 10.0, "EX_glc__D_m": 5.0})
    exchanges = {"EX_ac_e": 0.0, "EX_glc__D_e": 1.7, "EX_o2_e": 20.0}

    a = _model("a", dict(exchanges))
    apply_medium_checked(a, spec, strict=False)
    b = _model("b", dict(exchanges))
    apply_medium_translated(b, spec, strict=False)

    assert effective_medium_by_metabolite(a) == effective_medium_by_metabolite(b)
    assert {r.id: r.lower_bound for r in a.exchanges} == {r.id: r.lower_bound for r in b.exchanges}


# ─────────────────────────────────────────────────────────────────────────────────
# CC-7 — the id normalizer destroyed D/L stereochemistry.
#
# The "last __token starts uppercase ⇒ MICOM taxon suffix" heuristic also stripped BiGG stereo
# descriptors, so `lac__D_e` and `lac__L_e` both normalized to `lac`. Because `solve_bigg_host`
# normalizes BOTH the reviewed interface-map keys AND the microbial availability with this
# function, a reviewed D-isomer mapping matched L-isomer availability and opened the D exchange —
# fabricating host uptake and biomass for a molecule the host cannot transport.
# ─────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("base", ["lac", "arab", "ala", "glc", "asp", "glu", "mal"])
def test_d_and_l_isomers_normalize_differently(base):
    d = _normalize_metabolite_id(f"{base}__D_e")
    l_ = _normalize_metabolite_id(f"{base}__L_e")
    assert d != l_, f"{base}__D_e and {base}__L_e collapsed to {d!r}"
    assert d == f"{base}__d"
    assert l_ == f"{base}__l"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("EX_lac__D_m", "lac__d"),          # community namespace, stereo preserved
        ("EX_lac__L_e", "lac__l"),          # member namespace, stereo preserved
        ("glc__D_e", "glc__d"),             # most common carbon source in the bundled models
        ("ac_e", "ac"),                     # no stereo, no taxon
        ("EX_ac_m", "ac"),
        ("etoh_lumen", "etoh"),             # host interface compartment
        ("glc__D_e__Bacteroides", "glc__d"),   # real MICOM taxon suffix still stripped
        ("lac__L_e__Roseburia", "lac__l"),     # taxon stripped, stereo kept
        ("ac_e__Escherichia_coli_1", "ac"),
    ],
)
def test_normalization_keeps_stereo_and_still_strips_taxa(raw, expected):
    assert _normalize_metabolite_id(raw) == expected


def _stereo_host(base: str) -> cobra.Model:
    """Host that can transport ONLY the D isomer; the L exchange exists but leads nowhere."""
    model = cobra.Model(base)
    d_e = cobra.Metabolite(f"{base}__D_e", compartment="e")
    l_e = cobra.Metabolite(f"{base}__L_e", compartment="e")
    d_c = cobra.Metabolite(f"{base}__D_c", compartment="c")
    ex_d = cobra.Reaction(f"EX_{base}__D_e")
    ex_l = cobra.Reaction(f"EX_{base}__L_e")
    transport = cobra.Reaction(f"T_{base}__D")
    biomass = cobra.Reaction("BIOMASS")
    ex_d.add_metabolites({d_e: -1})
    ex_l.add_metabolites({l_e: -1})
    transport.add_metabolites({d_e: -1, d_c: 1})
    biomass.add_metabolites({d_c: -1})
    ex_d.bounds = ex_l.bounds = (-1000.0, 1000.0)
    transport.bounds = biomass.bounds = (0.0, 1000.0)
    model.add_reactions([ex_d, ex_l, transport, biomass])
    model.objective = biomass
    return model


@pytest.mark.parametrize("base", ["arab", "lac", "ala"])
def test_l_availability_cannot_feed_a_d_only_host(base):
    """End-to-end: a D-only host offered L-only microbial availability must NOT grow.

    Before the fix all three returned biomass 10.0 with `{base: 10.0}` of fabricated uptake.
    """
    from cmig.core.host import solve_bigg_host

    result = solve_bigg_host(
        _stereo_host(base),
        {f"{base}__L": 10.0},
        interface_map={f"{base}__D": f"EX_{base}__D_e"},
        solver="gurobi",
    )
    assert result.biomass == pytest.approx(0.0)
    assert result.lumen_uptake == {}


@pytest.mark.parametrize("base", ["arab", "lac", "ala"])
def test_d_availability_still_feeds_a_d_only_host(base):
    """The guard must not break the legitimate match it exists to serve."""
    from cmig.core.host import solve_bigg_host

    result = solve_bigg_host(
        _stereo_host(base),
        {f"{base}__D": 10.0},
        interface_map={f"{base}__D": f"EX_{base}__D_e"},
        solver="gurobi",
    )
    assert result.biomass == pytest.approx(10.0)
    assert result.lumen_uptake == {f"{base}__d": pytest.approx(10.0)}


# ─────────────────────────────────────────────────────────────────────────────────
# opus F5 — `flux_report_status` claimed "Full (LP pFBA)" for flux that was not pFBA (or absent).
# ─────────────────────────────────────────────────────────────────────────────────


def test_failed_solve_claims_no_flux_report_tier():
    from cmig.core.diagnostics import DiagnosticCode
    from cmig.core.engine import FLUX_REPORT_LABEL, solver_failed_result

    result = solver_failed_result("gurobi", [(DiagnosticCode.SOLVER_ERROR, "boom")])
    assert result.flux_normalization_method == "none"
    assert result.flux_report_status == "none"
    assert "No flux" in FLUX_REPORT_LABEL[result.flux_report_status]


def test_pfba_fallback_is_not_reported_as_pfba():
    """The pFBA stage can fail while the plain-FBA retry succeeds.

    A non-parsimonious community FBA vector is one arbitrary vertex of a highly degenerate optimal
    face, so every member<->pool exchange and cross-feeding edge derived from it is one arbitrary
    representative. Labelling it "Full (LP pFBA)" misdescribes the method for the whole run.
    """
    from cmig.core.engine import FLUX_REPORT_LABEL, MicomEngine

    class _Members:
        columns: list[str] = []
        index: list[str] = []

    class _Fluxes:
        index: list[str] = []
        columns: list[str] = []

    class _Solution:
        members = _Members()
        fluxes = _Fluxes()
        growth_rate = 0.5

    engine = MicomEngine()
    pfba = engine._solve_result_from_solution(
        _Solution(), cmig_solver="gurobi", flux_normalization="pfba"
    )
    fba = engine._solve_result_from_solution(
        _Solution(), cmig_solver="gurobi", flux_normalization="fba"
    )
    assert pfba.flux_report_status == "full"
    assert fba.flux_report_status == "fba_non_parsimonious"
    assert "NON-parsimonious" in FLUX_REPORT_LABEL[fba.flux_report_status]


# ─────────────────────────────────────────────────────────────────────────────────
# opus F6 — `--multi-metric pareto` labelled a plain mmol sum as a carbon-equivalent score.
# ─────────────────────────────────────────────────────────────────────────────────


def test_pareto_score_unit_does_not_claim_carbon_equivalence():
    from cmig.core.search_product import MULTI_METRIC_UNITS

    unit = MULTI_METRIC_UNITS["pareto"]
    assert "mmol C gDW^-1 h^-1" not in unit          # the carbon claim is gone
    assert "mmol gDW^-1 h^-1" in unit
    assert MULTI_METRIC_UNITS["carbon_equivalent"] == "mmol C gDW^-1 h^-1"


# ─────────────────────────────────────────────────────────────────────────────────
# opus F8 — micom's NaN (taxon has no such exchange) poisoned every community share.
# ─────────────────────────────────────────────────────────────────────────────────


def test_a_member_without_the_exchange_contributes_zero_not_nan():
    import math

    from cmig.core.metrics import (
        community_contributions,
        target_secretion_share,
        target_turnover_share,
    )

    member_exchange = {"A": {"succ": float("nan")}, "B": {"succ": -4.0}}
    abundances = {"A": 0.5, "B": 0.5}
    contributions = community_contributions(member_exchange, abundances, "succ")
    assert contributions == {"A": 0.0, "B": -2.0}
    share = target_turnover_share(contributions, "B")
    assert not math.isnan(share)
    assert share == pytest.approx(1.0)
    assert target_turnover_share(contributions, "A") == pytest.approx(0.0)
    assert target_secretion_share(contributions, "B") == pytest.approx(0.0)


# ─────────────────────────────────────────────────────────────────────────────────
# opus F7 [P1] — importing cmig.core.host_coupling first raised ImportError (circular).
# ─────────────────────────────────────────────────────────────────────────────────


def test_host_coupling_is_importable_as_the_first_import():
    import subprocess
    import sys

    for statement in (
        "import cmig.core.host_coupling",
        "from cmig.core.host import solve_bigg_host, run_bigg_host_microbe",
        "import cmig.core.host, cmig.core.host_coupling",
    ):
        proc = subprocess.run(
            [sys.executable, "-c", statement], capture_output=True, text=True, check=False
        )
        assert proc.returncode == 0, f"{statement!r} failed: {proc.stderr}"


def test_host_module_still_rejects_unknown_attributes():
    import cmig.core.host as host

    with pytest.raises(AttributeError):
        getattr(host, "definitely_not_a_real_symbol")  # noqa: B009


# ─────────────────────────────────────────────────────────────────────────────────
# codex F4 — a nonexistent knockout was emitted as a numeric rank-1 scientific result.
# ─────────────────────────────────────────────────────────────────────────────────


def test_explicit_unknown_knockout_id_is_an_input_error():
    from cmig.cli.main import _select_ko_targets

    model = cobra.Model("m")
    reaction = cobra.Reaction("ACKr")
    reaction.add_metabolites({cobra.Metabolite("ac_c", compartment="c"): -1})
    model.add_reactions([reaction])

    assert _select_ko_targets(
        model, ko_level="reaction", explicit=["ACKr"], max_n=0, selection="id", seed=0
    ) == (["ACKr"], 1, "explicit")
    with pytest.raises(ValueError, match="unknown reaction id"):
        _select_ko_targets(
            model, ko_level="reaction", explicit=["DOES_NOT_EXIST"],
            max_n=0, selection="id", seed=0,
        )


def test_unevaluated_knockouts_get_rank_zero_and_never_enter_top_ranked(tmp_path):
    """Failed rows stay visible as diagnostics but must not be ranked or announced as a hit.

    This asserts on the WRITTEN artifacts, not on the `_ko_ranked_rows` helper: a mutation test
    showed that deleting the `top_ranked` filter left the whole suite green because the old
    version of this test only exercised the helper.
    """
    import csv
    import json

    from cmig.cli.main import _write_gene_ko_search_outputs

    class _Baseline:
        score = 12.0
        target_flux = 12.0
        community_growth = 0.5
        status = "optimal"
        diagnostic = None

    nan = float("nan")
    rows = [
        {"member": "m", "gene": "good1", "evaluation_status": "ok", "status": "optimal",
         "score": 9.0, "score_delta": -3.0, "target_flux": 9.0, "target_flux_delta": -3.0,
         "community_growth": 0.4, "community_growth_delta": -0.1, "diagnostic": None},
        {"member": "m", "gene": "bad", "evaluation_status": "failed", "status": "failed",
         "score": nan, "score_delta": nan, "target_flux": nan, "target_flux_delta": nan,
         "community_growth": nan, "community_growth_delta": nan, "diagnostic": "KeyError"},
        {"member": "m", "gene": "good2", "evaluation_status": "ok", "status": "optimal",
         "score": 11.0, "score_delta": -1.0, "target_flux": 11.0, "target_flux_delta": -1.0,
         "community_growth": 0.45, "community_growth_delta": -0.05, "diagnostic": None},
    ]
    _write_gene_ko_search_outputs(
        rows, tmp_path, baseline=_Baseline(), members=("m",), target="ac", member="m",
        n_genes_evaluated=3, n_genes_total=3, ko_level="reaction", gene_selection="id",
        seed=0, direction="max_secretion", warnings=[],
    )
    payload = json.loads((tmp_path / "gene_ko_summary.json").read_text())

    ranked_genes = [row["gene"] for row in payload["top_ranked"]]
    assert "bad" not in ranked_genes, "an unevaluated knockout entered top_ranked"
    assert ranked_genes == ["good1", "good2"]
    assert [row["rank"] for row in payload["top_ranked"]] == [1, 2]
    assert [row["gene"] for row in payload["unevaluated"]] == ["bad"]
    assert payload["status"] == "degraded"          # mixed screen is not "ok"

    with open(tmp_path / "gene_ko_rankings.csv") as handle:
        csv_rows = {row["gene"]: row for row in csv.DictReader(handle)}
    assert csv_rows["bad"]["rank"] == "0"           # rank 0 == "no rank"
    assert csv_rows["bad"]["score_delta"] == ""     # no fabricated delta
    assert csv_rows["good1"]["rank"] == "1"


def test_failed_knockout_evaluation_does_not_fabricate_a_delta():
    """The old failure row was `score=0, score_delta=-baseline` — the baseline, negated.

    That is the strongest possible "effect" manufactured out of an exception, and it was then
    printed as `rank 1 (largest effect) ... delta=-12.15`.
    """
    import math

    from cmig.cli.main import _evaluate_ko_target

    class _Baseline:
        score = 12.148013826564465
        target_flux = 12.148013826564465
        community_growth = 0.11222727106361158

    def _boom(*_args, **_kwargs):
        raise KeyError("DOES_NOT_EXIST")

    row = _evaluate_ko_target(
        (0, "m1", "DOES_NOT_EXIST"),
        ko_level="reaction",
        base_models={"m1": cobra.Model("m1")},
        sub_taxonomy=None,
        config=None,
        baseline=_Baseline(),
        tmp_dir=None,
        write_sbml_model=_boom,
        search_model_pool=_boom,
        engine_factory=_boom,
    )
    assert row["evaluation_status"] == "failed"
    for field in (
        "score", "score_delta", "target_flux", "target_flux_delta",
        "community_growth", "community_growth_delta",
    ):
        assert math.isnan(float(row[field])), f"{field} was fabricated as {row[field]!r}"


# ─────────────────────────────────────────────────────────────────────────────────
# codex F5 / opus F14 — matplotlib SVGs were not byte-reproducible.
# ─────────────────────────────────────────────────────────────────────────────────


def test_matplotlib_svg_writers_are_configured_for_byte_reproducibility():
    from cmig.cli import main as cli_main
    from cmig.core import interaction_figures

    for module in (cli_main, interaction_figures):
        assert module.SVG_METADATA == {"Date": None}
        assert module.SVG_HASHSALT == "cmig-svg-v1"
    plt = cli_main._load_matplotlib_pyplot()
    assert plt.rcParams["svg.hashsalt"] == "cmig-svg-v1"


def test_screening_svg_bytes_are_identical_across_writes(tmp_path):
    from cmig.cli.main import _load_matplotlib_pyplot, _save_screening_figure

    plt = _load_matplotlib_pyplot()
    digests = []
    for name in ("a", "b"):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.barh(["x", "y"], [1.0, 2.0])
        ax.set_title("reproducibility")
        _save_screening_figure(fig, tmp_path / f"{name}.svg", tmp_path / f"{name}.tiff")
        plt.close(fig)
        digests.append((tmp_path / f"{name}.svg").read_bytes())
    assert digests[0] == digests[1]


# ─────────────────────────────────────────────────────────────────────────────────
# codex F3 (part 2) — search discarded the "could not be applied" medium list entirely.
# ─────────────────────────────────────────────────────────────────────────────────


class _StubEngine:
    """Minimal engine seam: `search_model_pool` only needs `build_community`."""

    def build_community(self, taxonomy, *, cmig_solver="gurobi"):
        return _model("consortium", {"EX_ac_m": 0.0, "EX_glc__D_m": 10.0})


def test_search_surfaces_medium_exchanges_it_could_not_apply():
    """Run the REAL search entry point, not the medium helper.

    A mutation test showed that deleting `warnings.extend(sorted(medium_notes))` from
    `search_model_pool` left the suite green, because the old version of this test only called
    `_apply_search_medium` directly. The point of the finding is that the note reaches the RUN's
    warnings, so that is what is asserted here.
    """
    import pandas as pd

    from cmig.core.medium_spec import MediumSpec
    from cmig.core.search_product import (
        UNAPPLIED_MEDIUM_PREFIX,
        SearchConfig,
        search_model_pool,
    )

    taxonomy = pd.DataFrame({"id": ["a", "b"], "file": ["a.xml", "b.xml"], "abundance": [0.5, 0.5]})
    result = search_model_pool(
        _StubEngine(),
        taxonomy,
        SearchConfig(target="ac", min_size=2, max_size=2),
        medium_spec=MediumSpec(uptake={"EX_ac_m": 7.0, "EX_notreal_m": 1.0}),
        strict_medium=False,
    )
    unapplied = [w for w in result.warnings if UNAPPLIED_MEDIUM_PREFIX in w]
    assert unapplied, f"the dropped medium exchange never reached run warnings: {result.warnings}"
    assert "EX_notreal_m" in unapplied[0]
    # and it is also on the candidate row, so a per-consortium reader sees it too
    rows = list(result.ranks) + list(result.unevaluated)
    assert any(UNAPPLIED_MEDIUM_PREFIX in (row.diagnostic or "") for row in rows)


def test_apply_search_medium_helper_applies_what_it_can():
    from cmig.core.medium_spec import MediumSpec
    from cmig.core.search_product import UNAPPLIED_MEDIUM_PREFIX, _apply_search_medium

    model = _model("consortium", {"EX_ac_m": 0.0, "EX_glc__D_m": 10.0})
    notes: set[str] = set()
    note = _apply_search_medium(
        model,
        MediumSpec(uptake={"EX_ac_m": 7.0, "EX_notreal_m": 1.0}),
        strict_medium=False,
        notes=notes,
    )
    assert note is not None and UNAPPLIED_MEDIUM_PREFIX in note
    assert "EX_notreal_m" in note
    assert notes == {note}
    assert model.reactions.EX_ac_m.lower_bound == pytest.approx(-7.0)   # the rest still applied


def test_search_is_silent_when_the_whole_medium_was_applied():
    from cmig.core.medium_spec import MediumSpec
    from cmig.core.search_product import _apply_search_medium

    model = _model("consortium", {"EX_ac_m": 0.0})
    notes: set[str] = set()
    assert _apply_search_medium(
        model, MediumSpec(uptake={"EX_ac_m": 7.0}), strict_medium=True, notes=notes
    ) is None
    assert notes == set()


# ─────────────────────────────────────────────────────────────────────────────────
# opus F9 — a min_* direction reaching 0 is the answer, not "the target cannot be produced".
# ─────────────────────────────────────────────────────────────────────────────────


def test_all_zero_scores_are_explained_as_the_expected_optimum_for_a_min_direction():
    from cmig.core.search_product import _ranking_degeneracy_warnings

    scored = [(("a", "b"), 0.0, "optimal"), (("a", "c"), -0.0, "optimal")]
    minimisation = _ranking_degeneracy_warnings(scored, direction="min_secretion")[0]
    assert "EXPECTED optimum" in minimisation
    assert "does NOT mean the target cannot be produced" in minimisation
    maximisation = _ranking_degeneracy_warnings(scored, direction="max_secretion")[0]
    assert "no candidate achieved a non-zero target flux" in maximisation


def test_a_nonzero_max_search_is_still_not_warned_about():
    from cmig.core.search_product import _ranking_degeneracy_warnings

    scored = [(("a", "b"), 12.1, "optimal"), (("a", "c"), 3.0, "optimal")]
    assert _ranking_degeneracy_warnings(scored, direction="max_secretion") == []


# ─────────────────────────────────────────────────────────────────────────────────
# opus F13 — figure noise floor had drifted away from the single declared constant.
# ─────────────────────────────────────────────────────────────────────────────────


def test_interaction_figures_share_the_single_noise_floor():
    from pathlib import Path

    from cmig.core import interaction_figures
    from cmig.core.sign import NOISE_FLOOR

    assert interaction_figures.NOISE_FLOOR == NOISE_FLOOR
    code = [
        line for line in Path(interaction_figures.__file__).read_text().splitlines()
        if not line.lstrip().startswith("#")
    ]
    drifted = [line for line in code if "1e-9" in line]
    assert not drifted, f"a hard-coded threshold drifted back in: {drifted}"


# ─────────────────────────────────────────────────────────────────────────────────
# opus F3 / codex F2 (DEFERRED fix) — the per-taxon edge weight must at least be labelled.
# ─────────────────────────────────────────────────────────────────────────────────


def test_manifest_states_the_edge_weight_basis(tmp_path):
    """The value is unchanged (see report_fix), but its basis can no longer be misread.

    Asserted on the WRITTEN manifest, not by grepping the source: a source grep passes even if the
    field never reaches an artifact.
    """
    import json

    pytest.importorskip("micom")
    from cmig.golden_fixture import _run_hash_components, solve
    from cmig.io.solve_output import write_solve_output

    result, bundle = solve("gurobi")
    manifest_path = write_solve_output(bundle, _run_hash_components(result), tmp_path)
    attribution = json.loads(manifest_path.read_text())["edge_attribution"]

    assert attribution["weight_basis"] == "per_taxon_unweighted"
    assert attribution["weight_is_magnitude"] is True
    assert "gDW_taxon" in attribution["weight_unit"]
    note = attribution["weight_basis_note"]
    assert "NOT comparable to profile.net_flux" in note
    # The note must rule OUT the naive reading, which is what made a reviewer call it false.
    assert "Summing the unsigned weights" in note
    assert "cross_feeding" in note


# ─────────────────────────────────────────────────────────────────────────────────
# BLOCKER 1 — medium alias collapse: CSV row order silently changed the answer while
# `medium_checksum` (which sorts, and hashes both entries) stayed byte-identical.
# ─────────────────────────────────────────────────────────────────────────────────


def _alias_model():
    return _model("m", {"EX_glc__D_e": 0.0, "EX_ac_e": 0.0})


def test_conflicting_namespace_aliases_are_refused_not_silently_resolved():
    """Measured before the fix: growth 1.125065 vs 0.954612 for the SAME file, same checksum."""
    from cmig.core.medium_spec import apply_medium_checked

    forward = MediumSpec(uptake={"EX_ac_e": 3.0, "EX_ac_m": 10.0})
    reverse = MediumSpec(uptake={"EX_ac_m": 10.0, "EX_ac_e": 3.0})
    # The two orders are the same request, so they must not be distinguishable by outcome...
    from cmig.core.medium_spec import medium_checksum

    assert medium_checksum(forward) == medium_checksum(reverse)
    # ...and since the request is self-contradictory, BOTH must be refused.
    for spec in (forward, reverse):
        with pytest.raises(ValueError, match="conflicting uptake limits"):
            apply_medium_checked(_alias_model(), spec, strict=True)
        with pytest.raises(ValueError, match="conflicting uptake limits"):
            # permissive mode is about *unknown* nutrients, never about picking between two
            # contradictory values the user actually asked for
            apply_medium_checked(_alias_model(), spec, strict=False)


def test_agreeing_namespace_aliases_merge_deterministically():
    """Asking for the same thing twice is not ambiguous — it must apply, in either order."""
    from cmig.core.medium_spec import apply_medium_checked

    applied = []
    for uptake in (
        {"EX_glc__D_m": 7.0, "EX_glc__D_e": 7.0},
        {"EX_glc__D_e": 7.0, "EX_glc__D_m": 7.0},
    ):
        model = _alias_model()
        _original, unknown = apply_medium_checked(model, MediumSpec(uptake=uptake), strict=True)
        assert unknown == []
        applied.append(model.reactions.EX_glc__D_e.lower_bound)
    assert applied == [pytest.approx(-7.0), pytest.approx(-7.0)]


def test_medium_row_order_cannot_change_the_applied_medium():
    """Row-order independence, pinned directly: the property the hash silently failed to protect."""
    from cmig.core.medium_spec import apply_medium_checked, effective_medium_by_metabolite

    rows = [("EX_glc__D_m", 5.0), ("EX_ac_m", 10.0)]
    seen = []
    for order in (rows, list(reversed(rows))):
        model = _alias_model()
        apply_medium_checked(model, MediumSpec(uptake=dict(order)), strict=True)
        seen.append(effective_medium_by_metabolite(model))
    assert seen[0] == seen[1]
    assert seen[0] == {"glc__D": pytest.approx(5.0), "ac": pytest.approx(10.0)}


# ─────────────────────────────────────────────────────────────────────────────────
# BLOCKER 2 — an all-infeasible dt x Km grid was certified `interpretable: true`, exit 0.
# ─────────────────────────────────────────────────────────────────────────────────


def _sensitivity_rows(statuses, *, untracked=None):
    from cmig.core.dfba import DfbaConfig, DfbaSensitivityResult, DfbaSensitivityRow

    rows = [
        DfbaSensitivityRow(
            dt=0.1, km=0.01, status=status, n_steps=3, final_t=0.3, final_biomass=0.01,
            final_concentrations={}, depletion_times={}, max_concentration_residual=0.0,
            max_biomass_residual=0.0, relative_biomass_error_to_finest_dt=0.0,
            untracked_uptake=dict(untracked or {}),
        )
        for status in statuses
    ]
    config = DfbaConfig(t_end=0.3, initial_concentrations={"EX_glc__D_e": 10.0}, dt=0.1)
    return DfbaSensitivityResult(rows=rows, source_config=config)


def test_an_all_infeasible_grid_is_not_interpretable():
    """Residuals of 0.0 mean nothing was integrated, not that the experiment was clean."""
    from cmig.io.dfba_output import sensitivity_acceptance

    acceptance = sensitivity_acceptance(_sensitivity_rows(["infeasible"] * 4))
    assert acceptance["balance_passed"] is True          # the numerics really were fine
    assert acceptance["no_untracked_uptake"] is True     # and uptake really was controlled
    assert acceptance["all_statuses_completed"] is False
    assert acceptance["interpretable"] is False          # but the grid still answers nothing
    assert acceptance["n_infeasible"] == 4
    assert any("produced no trajectory" in r for r in acceptance["not_interpretable_because"])


def test_a_partially_infeasible_grid_is_not_interpretable():
    from cmig.io.dfba_output import sensitivity_acceptance

    acceptance = sensitivity_acceptance(_sensitivity_rows(["completed", "infeasible"]))
    assert acceptance["interpretable"] is False


def test_a_clean_grid_is_interpretable_with_no_reasons():
    from cmig.io.dfba_output import sensitivity_acceptance

    acceptance = sensitivity_acceptance(_sensitivity_rows(["completed"] * 4))
    assert acceptance["interpretable"] is True
    assert acceptance["not_interpretable_because"] == []


def test_untracked_uptake_still_blocks_interpretability():
    from cmig.io.dfba_output import sensitivity_acceptance

    acceptance = sensitivity_acceptance(
        _sensitivity_rows(["completed"] * 2, untracked={"EX_o2_e": 21.8})
    )
    assert acceptance["all_statuses_completed"] is True
    assert acceptance["interpretable"] is False
    assert any("untracked" in r for r in acceptance["not_interpretable_because"])


# ─────────────────────────────────────────────────────────────────────────────────
# BLOCKER 3 — a one-term DEMAND objective was reported as growth, status ok, no warning.
# Reachable through shipped `strain-growth`; my first-pass deferral called it unreachable.
# ─────────────────────────────────────────────────────────────────────────────────


def _objective_reactions(model):
    from cobra.util.solver import linear_reaction_coefficients

    return list(linear_reaction_coefficients(model))


def _demand_objective_model():
    model = cobra.Model("demand_only")
    glc = cobra.Metabolite("glc__D_e", compartment="e")
    inner = cobra.Metabolite("x_c", compartment="c")
    ex = cobra.Reaction("EX_glc__D_e")
    ex.add_metabolites({glc: -1})
    ex.bounds = (-10.0, 1000.0)
    transport = cobra.Reaction("GLCt")
    transport.add_metabolites({glc: -1, inner: 1})
    transport.bounds = (0.0, 1000.0)
    demand = cobra.Reaction("DM_ac")
    demand.add_metabolites({inner: -1})
    demand.bounds = (0.0, 1000.0)
    model.add_reactions([ex, transport, demand])
    model.objective = demand
    return model


def test_a_demand_objective_is_not_reported_as_growth():
    from cmig.io.model_import import objective_structure_warning

    model = _demand_objective_model()
    reactions = _objective_reactions(model)
    assert len(reactions) == 1                       # the count-only check saw nothing wrong
    assert objective_structure_warning(1) is None    # ...and still does, for back-compat
    warning = objective_structure_warning(len(reactions), reactions)
    assert warning is not None
    assert "boundary reaction DM_ac" in warning
    assert "NOT a growth rate" in warning


def test_a_biomass_demand_objective_is_accepted():
    """`DM_biomass_c` as the objective is a documented pattern and really is growth."""
    from cmig.io.model_import import objective_structure_warning

    model = cobra.Model("biomass_demand")
    biomass_c = cobra.Metabolite("biomass_c", compartment="c")
    demand = cobra.Reaction("DM_biomass_c")
    demand.add_metabolites({biomass_c: -1})
    demand.bounds = (0.0, 1000.0)
    model.add_reactions([demand])
    model.objective = demand
    assert demand.boundary is True
    assert objective_structure_warning(1, _objective_reactions(model)) is None


def test_an_unrecognisable_single_objective_is_flagged_but_not_refused():
    from cmig.io.model_import import objective_structure_warning

    model = cobra.Model("odd")
    a = cobra.Metabolite("a_c", compartment="c")
    b = cobra.Metabolite("b_c", compartment="c")
    reaction = cobra.Reaction("SOMEREACTION")
    reaction.add_metabolites({a: -1, b: 1})
    reaction.bounds = (0.0, 1000.0)
    model.add_reactions([reaction])
    model.objective = reaction
    warning = objective_structure_warning(1, _objective_reactions(model))
    assert warning is not None
    assert "not identifiable as a biomass reaction" in warning


@pytest.mark.parametrize("biomass_id", [
    "BIOMASS_Cl_DSM_WT_46p666M1", "BIOMASS_Ec_iML1515_core_75p37M", "BIOMASS_BS_10", "Growth",
])
def test_a_real_biomass_objective_stays_silent(biomass_id):
    """The guard must not add noise to the models people actually run."""
    from cmig.io.model_import import objective_structure_warning

    model = cobra.Model("m")
    a = cobra.Metabolite("a_c", compartment="c")
    b = cobra.Metabolite("b_c", compartment="c")
    biomass = cobra.Reaction(biomass_id)
    biomass.add_metabolites({a: -1, b: -1})     # a real biomass reaction consumes precursors
    biomass.bounds = (0.0, 1000.0)
    model.add_reactions([biomass])
    model.objective = biomass
    assert objective_structure_warning(1, _objective_reactions(model)) is None


# ─────────────────────────────────────────────────────────────────────────────────
# BLOCKER 5 — the medium fix changed published numbers without moving run_hash.
# A non-hashed marker records the discontinuity; it must NOT become a hash component.
# ─────────────────────────────────────────────────────────────────────────────────


def test_medium_policy_marker_is_recorded_but_never_hashed():
    from cmig.core.manifest import RUN_HASH_COMPONENTS
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.core.workflow_manifest import (
        WORKFLOW_COMPONENT_VOCABULARY,
        WORKFLOW_HASH_COMPONENTS,
    )

    assert MEDIUM_POLICY == "exchange_reactions_by_metabolite_v2"
    # It must not be smuggled into either hash contract.
    assert "medium_policy" not in set(RUN_HASH_COMPONENTS)
    assert "medium_policy" not in WORKFLOW_COMPONENT_VOCABULARY
    for components in WORKFLOW_HASH_COMPONENTS.values():
        assert "medium_policy" not in components


def test_workflow_manifest_carries_the_medium_policy_without_moving_its_hash():
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.core.workflow_manifest import build_workflow_manifest

    components = {
        "workflow_kind": "dfba",
        "cmig_core_version": "0.1.0",
        "dependency_versions": {"cobra": "0.31.1"},
        "solver_setting": {"solver": "gurobi"},
        "model_checksum": "sha256:abc",
        "medium": {"medium_checksum": "micom_default_medium"},
        "dfba_spec": {"t_end": 1.0},
    }
    manifest = build_workflow_manifest("dfba", components)
    payload = manifest.to_payload()
    assert payload["medium_policy"] == MEDIUM_POLICY
    assert "medium_policy" not in payload["hash_components"]
    # the hash is a function of the components only, so the marker cannot have moved it
    assert build_workflow_manifest("dfba", components).run_hash == manifest.run_hash


def test_solve_manifest_records_the_medium_policy(tmp_path):
    import json

    pytest.importorskip("micom")
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.golden_fixture import _run_hash_components, solve
    from cmig.io.solve_output import write_solve_output

    result, bundle = solve("gurobi")
    manifest_path = write_solve_output(bundle, _run_hash_components(result), tmp_path)
    manifest = json.loads(manifest_path.read_text())
    assert manifest["provenance"]["medium_policy"] == MEDIUM_POLICY
    # and the frozen contract is untouched
    assert manifest["run_hash"] == (
        "29844e29103603324d118cc9a8b9ae4fa2a79070418860cfc2ed70095cef29ab"
    )


# ─────────────────────────────────────────────────────────────────────────────────
# BLOCKER 4 (condition a) — the basis must reach the surfaces consumers actually read.
# ─────────────────────────────────────────────────────────────────────────────────


def test_edge_weight_basis_reaches_the_figure_caption():
    from cmig.render.composer import (
        EDGE_WEIGHT_BASIS_CAPTION,
        PanelSpec,
        panel_title_with_basis,
    )

    network = panel_title_with_basis(PanelSpec(kind="network", title="Cross-feeding"))
    assert EDGE_WEIGHT_BASIS_CAPTION in network
    assert "per-taxon" in network
    chord = panel_title_with_basis(PanelSpec(kind="chord", title="Transfers"))
    assert EDGE_WEIGHT_BASIS_CAPTION in chord
    # a heatmap does not plot edge weights, so it must not gain a misleading caption
    assert panel_title_with_basis(PanelSpec(kind="heatmap", title="Fluxes")) == "Fluxes"
    # idempotent: re-rendering the same spec must not stack the caption
    assert panel_title_with_basis(PanelSpec(kind="network", title=network)) == network


def test_inspect_run_reports_the_edge_weight_basis(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import _inspect_run_dir
    from cmig.golden_fixture import _run_hash_components, solve
    from cmig.io.solve_output import write_solve_output

    result, bundle = solve("gurobi")
    write_solve_output(bundle, _run_hash_components(result), tmp_path)
    basis = _inspect_run_dir(tmp_path)["edge_weight_basis"]
    assert basis is not None, "inspect-run dropped the unit basis consumers need"
    assert basis["weight_basis"] == "per_taxon_unweighted"
    assert basis["weight_is_magnitude"] is True


# ─────────────────────────────────────────────────────────────────────────────────
# Two behaviours the fix pass claimed but never pinned (mutation-check gaps).
# ─────────────────────────────────────────────────────────────────────────────────


def test_cmd_solve_refuses_to_report_a_failed_solve_as_a_result(tmp_path, monkeypatch):
    """`solve` printed `완료 … growth: 0.0000` and exited 0 for a solver_failed community.

    Monkeypatched at the facade so the guard is exercised without paying for a real infeasible
    MICOM solve; the guard is the thing under test, not micom.
    """
    from cmig.cli import main as cli_main
    from cmig.core.diagnostics import DiagnosticCode
    from cmig.core.engine import solver_failed_result
    from cmig.service.outcome import SolveOutcome

    failed = solver_failed_result(
        "gurobi", [(DiagnosticCode.SOLVER_ERROR, "could not get community growth rate")]
    )
    manifest_path = tmp_path / "out" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}")

    def _fake_solve_community(self, **kwargs):
        return SolveOutcome(
            result=failed, bundle=None, components=None,
            run_hash="deadbeef" * 8, manifest_path=manifest_path, status="ok",
        )

    from cmig.service.engine_service import EngineService

    monkeypatch.setattr(EngineService, "solve_community", _fake_solve_community)

    # A real model file, so every step before the solve runs for real and only the solve is faked.
    taxonomy = tmp_path / "tax.csv"
    taxonomy.write_text(f"id,file,abundance\niHN637,{Path('models/iHN637.xml').resolve()},1.0\n")
    argv = [
        "solve", "--taxonomy", str(taxonomy), "--assume-bigg-namespace",
        "--out", str(tmp_path / "out"),
    ]
    assert cli_main.main(argv) == 3, "a solver_failed solve must not exit 0"
    assert cli_main.main([*argv, "--allow-failed-run"]) == 0, "--allow-failed-run must override"


def test_dfba_workflow_manifest_degrades_on_untracked_uptake(tmp_path):
    """`inspect-run` certified an uninterpretable dFBA run as `status: ok, warnings: []`."""
    import json

    pytest.importorskip("micom")
    from cmig.cli.main import main

    model = "models/iHN637.xml"
    open_dir = tmp_path / "open"
    assert main([
        "dfba", "--model", model, "--initial", "EX_glc__D_e=10",
        "--t-end", "0.4", "--dt", "0.2", "--out", str(open_dir),
    ]) == 0
    manifest = json.loads((open_dir / "manifest.json").read_text())
    assert manifest["status"] == "degraded", "an uninterpretable dFBA run was certified ok"
    assert manifest["warnings"], "the untracked-uptake verdict never reached the manifest"
    assert any("UNCONSTRAINED" in w for w in manifest["warnings"])

    closed_dir = tmp_path / "closed"
    main([
        "dfba", "--model", model, "--initial", "EX_glc__D_e=10",
        "--t-end", "0.4", "--dt", "0.2", "--close-untracked-uptake", "--out", str(closed_dir),
    ])
    closed = json.loads((closed_dir / "manifest.json").read_text())
    assert not any("UNCONSTRAINED" in w for w in closed["warnings"])


def test_contradictory_aliases_are_rejected_at_load_time(tmp_path):
    """The contradiction belongs to the request, not to a model, so it is an INPUT error.

    Caught in `MediumSpec.validate()` so every subcommand classifies it as exit 2. Detected
    per-model instead, `search` reported it as an analysis failure (exit 3) buried in per-candidate
    diagnostics, which is the wrong story to tell a user about a bad CSV.
    """
    from cmig.core.medium_spec import load_medium

    path = tmp_path / "conflict.csv"
    path.write_text("exchange_id,uptake_limit\nEX_ac_e,3.0\nEX_ac_m,10.0\n")
    with pytest.raises(ValueError, match="conflicting uptake limits"):
        load_medium(path)

    agreeing = tmp_path / "agree.csv"
    agreeing.write_text("exchange_id,uptake_limit\nEX_ac_e,10.0\nEX_ac_m,10.0\n")
    spec = load_medium(agreeing)                      # agreeing aliases are not a contradiction
    assert spec.uptake == {"EX_ac_e": 10.0, "EX_ac_m": 10.0}


def test_a_contradictory_medium_is_an_input_error_on_every_subcommand(tmp_path):
    from cmig.cli.main import main

    medium = tmp_path / "conflict.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_ac_e,3.0\nEX_ac_m,10.0\n")
    taxonomy = tmp_path / "tax.csv"
    taxonomy.write_text(f"id,file,abundance\niHN637,{Path('models/iHN637.xml').resolve()},1.0\n")

    assert main([
        "solve", "--taxonomy", str(taxonomy), "--assume-bigg-namespace",
        "--medium", str(medium), "--out", str(tmp_path / "s"),
    ]) == 2
    assert main([
        "search", "--taxonomy", str(taxonomy), "--target", "ac",
        "--min-size", "1", "--max-size", "1",
        "--medium", str(medium), "--out", str(tmp_path / "q"),
    ]) == 2


def test_stalled_and_infeasible_are_not_treated_as_the_same_failure():
    """A stalled run integrated; an infeasible one did not. Only the latter is always fatal.

    Measured on e_coli_core: `--close-untracked-uptake` with glucose alone gives 4/4 `stalled`
    at the initial biomass (nothing to be sensitive to), while tracking the required substrates
    gives 4/4 `completed` with biomass varying by dt. But a grid that MIXES stalled and completed
    runs does have dynamics to compare — stalling partway is often the finding itself — so it must
    stay interpretable rather than being refused along with the vacuous case.
    """
    from cmig.io.dfba_output import sensitivity_acceptance

    every_run_stalled = sensitivity_acceptance(_sensitivity_rows(["stalled"] * 4))
    assert every_run_stalled["interpretable"] is False
    assert every_run_stalled["n_stalled"] == 4
    assert any("every run stalled" in r for r in every_run_stalled["not_interpretable_because"])

    mixed = sensitivity_acceptance(_sensitivity_rows(["completed", "stalled", "completed"]))
    assert mixed["interpretable"] is True, "a partly-stalled grid still has dynamics to compare"
    assert mixed["all_statuses_completed"] is False      # still visible in the artifact
    assert mixed["n_stalled"] == 1

    any_infeasible = sensitivity_acceptance(_sensitivity_rows(["completed", "infeasible"]))
    assert any_infeasible["interpretable"] is False
    assert any_infeasible["n_infeasible"] == 1
    assert any("produced no trajectory" in r for r in any_infeasible["not_interpretable_because"])
