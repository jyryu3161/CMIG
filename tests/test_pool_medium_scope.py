"""Pool-scoped medium: a medium row no member of a candidate can take up is not an error.

User report (GUI, bundled 5-model pool, preset ``gut_overlay_agora_high_fiber``): every
Combination Search candidate failed with "medium exchange has no counterpart in the target
model". The gut overlays are written for the whole pool (``pool_closure`` rows plus diet rows),
so any sub-community lacks some of their ids, and the old rule refused each candidate.

MICOM's own workflows filter the medium to the community's exchanges before applying it
(``micom/workflows/grow.py`` and ``tradeoff.py``): an id with no exchange in the community cannot
enter any member, so dropping it leaves the LP identical. The rule pinned here:

* an id with a counterpart in at least one model of the selected pool but not in this candidate
  is recorded as *not applicable to this community* — not ``medium_unapplied``, not degraded,
  and the candidate's status is unaffected;
* an id with no counterpart in ANY pool model is still an input error before evaluation
  (``--allow-unknown-medium`` keeps its meaning for those ids).
"""

from __future__ import annotations

import json

import pytest

cobra = pytest.importorskip("cobra")
pd = pytest.importorskip("pandas")

from cmig.core.medium_spec import MediumSpec  # noqa: E402


def _model(name: str, exchanges: list[str]) -> cobra.Model:
    model = cobra.Model(name)
    reactions = []
    for exchange_id in exchanges:
        compartment = exchange_id.rsplit("_", 1)[-1]
        metabolite = cobra.Metabolite(exchange_id.removeprefix("EX_"), compartment=compartment)
        reaction = cobra.Reaction(exchange_id)
        reaction.add_metabolites({metabolite: -1})
        reaction.bounds = (0.0, 1000.0)
        reactions.append(reaction)
    model.add_reactions(reactions)
    return model


#: member -> its own (`_e`) exchanges; a community exposes the union as `_m`.
_MEMBERS = {
    "a": ["EX_glc__D_e", "EX_ac_e"],
    "b": ["EX_ac_e", "EX_but_e"],
    "c": ["EX_ac_e", "EX_fru_e"],
}


def _pool_models() -> dict[str, cobra.Model]:
    return {member: _model(member, exchanges) for member, exchanges in _MEMBERS.items()}


class _StubEngine:
    """MICOM seam: a community exposes `EX_<met>_m` for every member exchange."""

    def build_community(self, taxonomy, cmig_solver="gurobi"):
        members = [str(x) for x in taxonomy["id"]]
        exchanges = sorted({
            exchange[: -len("_e")] + "_m" for member in members for exchange in _MEMBERS[member]
        })
        return _model("+".join(members), exchanges)


_TAXONOMY = pd.DataFrame({
    "id": ["a", "b", "c"],
    "file": ["a.xml", "b.xml", "c.xml"],
    "abundance": [1.0, 1.0, 1.0],
})

#: Every id is offered by some pool model; no candidate pair has all of them.
_POOL_MEDIUM = MediumSpec(uptake={
    "EX_glc__D_m": 10.0, "EX_ac_m": 1.0, "EX_but_m": 0.0, "EX_fru_m": 2.0,
})


# ── the pool-level / candidate-level split ─────────────────────────────────────────────────────


def test_pool_coverage_names_the_ids_no_pool_model_can_take_up():
    from cmig.core.medium_spec import pool_medium_coverage

    spec = MediumSpec(uptake={**_POOL_MEDIUM.uptake, "EX_notreal_m": 1.0})
    coverage = pool_medium_coverage(_pool_models(), spec)
    assert coverage.unknown == ("EX_notreal_m",)
    assert coverage.known == frozenset({"EX_glc__D_m", "EX_ac_m", "EX_but_m", "EX_fru_m"})
    assert coverage.by_model["a"] == frozenset({"EX_glc__D_m", "EX_ac_m"})


def test_a_candidate_missing_ids_splits_them_into_community_and_pool_not_applicable():
    from cmig.core.medium_spec import pool_medium_coverage

    spec = MediumSpec(uptake={**_POOL_MEDIUM.uptake, "EX_notreal_m": 1.0})
    coverage = pool_medium_coverage(_pool_models(), spec)
    community, pool, unknown = coverage.split(
        ["EX_but_m", "EX_fru_m", "EX_notreal_m"], members=("a",)
    )
    assert community == ("EX_but_m", "EX_fru_m")       # other pool models have them
    assert pool == ("EX_notreal_m",)                   # no pool model has it; others match
    assert unknown == ()
    assert coverage.pool_not_applicable == ("EX_notreal_m",)
    assert coverage.check_namespace() is None


def test_a_medium_that_matches_no_pool_model_at_all_is_refused():
    """The namespace-mismatch signature: not one id of the medium reaches any pool model."""
    from cmig.core.medium_spec import pool_medium_coverage

    nonsense = MediumSpec(uptake={"EX_glc_D(e)": 10.0, "EX_notreal_m": 1.0})
    coverage = pool_medium_coverage(_pool_models(), nonsense)
    assert coverage.pool_not_applicable == ()
    assert coverage.split(["EX_glc_D(e)", "EX_notreal_m"], members=("a",)) == (
        (), (), ("EX_glc_D(e)", "EX_notreal_m"),
    )
    with pytest.raises(ValueError, match="none of the medium's 2 exchange ids matches"):
        coverage.check_namespace()


def test_an_id_a_member_has_but_the_community_lacks_is_refused_not_hidden():
    """The split must never call 'not applicable' something a member of THIS candidate has."""
    from cmig.core.medium_spec import pool_medium_coverage

    coverage = pool_medium_coverage(_pool_models(), _POOL_MEDIUM)
    with pytest.raises(ValueError, match="has a counterpart in candidate member"):
        coverage.split(["EX_glc__D_m"], members=("a", "b"))


# ── search: the candidate is evaluated, the record is kept, nothing degrades ───────────────────


def _search(**kwargs):
    from cmig.core.search_product import SearchConfig, search_model_pool

    return search_model_pool(
        _StubEngine(),
        _TAXONOMY,
        SearchConfig(target="ac", min_size=2, max_size=2),
        medium_spec=_POOL_MEDIUM,
        **kwargs,
    )


def test_search_no_longer_refuses_a_candidate_for_a_pool_medium_row_it_lacks():
    from cmig.core.medium_spec import pool_medium_coverage
    from cmig.core.search_product import UNAPPLIED_MEDIUM_PREFIX

    coverage = pool_medium_coverage(_pool_models(), _POOL_MEDIUM)
    result = _search(strict_medium=True, medium_pool=coverage)
    rows = {row.members: row for row in list(result.ranks) + list(result.unevaluated)}
    assert set(rows) == {("a", "b"), ("a", "c"), ("b", "c")}
    for row in rows.values():
        assert "no counterpart" not in (row.diagnostic or ""), row.diagnostic
    assert rows[("a", "b")].medium_not_applicable == ("EX_fru_m",)
    assert rows[("a", "c")].medium_not_applicable == ("EX_but_m",)
    assert rows[("b", "c")].medium_not_applicable == ("EX_glc__D_m",)
    # not `medium_unapplied`, and not a run warning: the LP is the one the community defines
    assert not any(UNAPPLIED_MEDIUM_PREFIX in warning for warning in result.warnings)
    assert not any("EX_fru_m" in warning for warning in result.warnings)


def test_without_pool_knowledge_the_old_refusal_still_holds():
    """Callers that never said what the pool is keep the strict per-community rule."""
    result = _search(strict_medium=True)
    assert not result.ranks
    assert all("no counterpart" in (row.diagnostic or "") for row in result.unevaluated)


def test_a_pool_unknown_id_is_not_applicable_to_the_pool_with_or_without_the_flag():
    """`--allow-unknown-medium` has nothing left to drop when some ids match."""
    from cmig.core.medium_spec import pool_medium_coverage
    from cmig.core.search_product import UNAPPLIED_MEDIUM_PREFIX, SearchConfig, search_model_pool

    spec = MediumSpec(uptake={**_POOL_MEDIUM.uptake, "EX_notreal_m": 1.0})
    coverage = pool_medium_coverage(_pool_models(), spec)
    for strict in (True, False):
        result = search_model_pool(
            _StubEngine(), _TAXONOMY, SearchConfig(target="ac", min_size=2, max_size=2),
            medium_spec=spec, strict_medium=strict, medium_pool=coverage,
        )
        assert not any(UNAPPLIED_MEDIUM_PREFIX in w for w in result.warnings), result.warnings
        rows = {row.members: row for row in list(result.ranks) + list(result.unevaluated)}
        assert rows[("a", "b")].medium_not_applicable == ("EX_fru_m",)   # community level only
        for row in rows.values():
            assert "no counterpart" not in (row.diagnostic or ""), row.diagnostic


def test_allow_unknown_keeps_todays_behaviour_when_nothing_matches():
    from cmig.core.medium_spec import pool_medium_coverage
    from cmig.core.search_product import UNAPPLIED_MEDIUM_PREFIX, SearchConfig, search_model_pool

    spec = MediumSpec(uptake={"EX_notreal_m": 1.0, "EX_alsonot_m": 2.0})
    coverage = pool_medium_coverage(_pool_models(), spec)
    result = search_model_pool(
        _StubEngine(), _TAXONOMY, SearchConfig(target="ac", min_size=2, max_size=2),
        medium_spec=spec, strict_medium=False, medium_pool=coverage,
    )
    unapplied = [w for w in result.warnings if UNAPPLIED_MEDIUM_PREFIX in w]
    assert unapplied and all("EX_notreal_m" in w for w in unapplied)


def test_only_a_medium_that_matches_nothing_is_refused_from_the_model_files(tmp_path):
    from cmig.core.medium_spec import pool_medium_coverage_from_taxonomy

    paths = {}
    for member, model in _pool_models().items():
        paths[member] = tmp_path / f"{member}.json"
        cobra.io.save_json_model(model, str(paths[member]))
    taxonomy = _TAXONOMY.assign(file=[str(paths[m]) for m in _TAXONOMY["id"]])
    spec = MediumSpec(uptake={**_POOL_MEDIUM.uptake, "EX_notreal_m": 1.0})
    assert pool_medium_coverage_from_taxonomy(taxonomy, spec).check_namespace() is None
    nonsense = MediumSpec(uptake={"EX_notreal_m": 1.0})
    with pytest.raises(ValueError, match="none of the medium's 1 exchange ids matches"):
        pool_medium_coverage_from_taxonomy(taxonomy, nonsense).check_namespace()


# ── the claim the rule rests on: dropping an id the community lacks leaves the LP identical ────


def _pair_pool(tmp_path):
    """Two real MICOM members: the producer has glucose, the consumer has butyrate."""
    from cmig.synthetic_pair import build_pair_taxonomy

    return build_pair_taxonomy(tmp_path / "pair")


def test_full_pool_medium_gives_the_same_lp_as_the_medium_prefiltered_to_the_candidate(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.core.engine import MicomEngine
    from cmig.core.medium_spec import (
        cli_exact_medium,
        pool_medium_coverage_from_taxonomy,
        translate_medium_for_model,
    )
    from cmig.core.search import Direction, TargetSpec
    from cmig.core.search_product import _evaluate_members

    """Each single-member candidate lacks a row with a NON-ZERO uptake limit and is optimal.

    The producer has no butyrate exchange (EX_but_m offered at 3), the consumer no glucose
    exchange (EX_glc__D_m offered at 10); each is asked for a target it can make.
    """
    taxonomy = _pair_pool(tmp_path)
    medium = MediumSpec(uptake={
        "EX_glc__D_m": 10.0, "EX_ac_m": 5.0, "EX_but_m": 3.0,
        "EX_notreal_m": 7.0,   # no pool model has it: not applicable to the pool
    })
    coverage = pool_medium_coverage_from_taxonomy(taxonomy, medium)
    assert coverage.pool_not_applicable == ("EX_notreal_m",)
    engine = MicomEngine()
    compared = 0
    with cli_exact_medium(True):
        for members, target in ((("producer",), "ac"), (("consumer",), "but")):
            spec = TargetSpec(target, Direction.MAX_SECRETION)
            new = _evaluate_members(
                engine, taxonomy, members, spec, growth_fraction=0.5, solver="gurobi",
                medium_spec=medium, strict_medium=True, medium_pool=coverage,
            )
            community = engine.build_community(
                taxonomy[taxonomy["id"].isin(members)].copy(), cmig_solver="gurobi"
            )
            mapping = translate_medium_for_model(community, medium).mapping
            prefiltered = MediumSpec(uptake={k: medium.uptake[k] for k in mapping})
            assert len(prefiltered.uptake) < len(medium.uptake)
            old = _evaluate_members(
                engine, taxonomy, members, spec, growth_fraction=0.5, solver="gurobi",
                medium_spec=prefiltered, strict_medium=True,
            )
            assert new.status == old.status == "optimal", (new.diagnostic, old.diagnostic)
            dropped = tuple(sorted(set(medium.uptake) - set(prefiltered.uptake)))
            assert dropped and all(medium.uptake[row] > 0 for row in dropped)
            assert new.target_flux > 0
            assert "EX_notreal_m" in dropped
            assert new.medium_not_applicable == tuple(r for r in dropped if r != "EX_notreal_m")
            assert old.medium_not_applicable == ()
            assert new.target_flux == pytest.approx(old.target_flux, abs=1e-6)
            assert new.community_growth == pytest.approx(old.community_growth, abs=1e-6)
            assert new.member_growth == pytest.approx(old.member_growth, abs=1e-6)
            assert new.score == pytest.approx(old.score, abs=1e-6)
            # and the old rule really did refuse the full medium for this candidate
            refused = _evaluate_members(
                engine, taxonomy, members, spec, growth_fraction=0.5, solver="gurobi",
                medium_spec=medium, strict_medium=True,
            )
            assert refused.status == "failed" and "no counterpart" in (refused.diagnostic or "")
            compared += 1
    assert compared == 2


def test_cli_search_ranks_single_members_on_a_pool_medium_and_records_the_scope(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    taxonomy = _pair_pool(tmp_path)
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10\nEX_ac_m,5\nEX_but_m,0\n")
    out = tmp_path / "search"
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "ac",
        "--min-size", "1", "--max-size", "2", "--medium", str(medium), "--exact-medium",
        "--out", str(out),
    ])
    assert rc == 0
    summary = json.loads((out / "search_summary.json").read_text())
    # The consumer alone cannot secrete acetate (it needs it) — a real LP answer. No candidate
    # is refused for a medium row only the other member can take up.
    for row in summary["unevaluated"]:
        assert "no counterpart" not in (row["diagnostic"] or ""), row
    by_members = {tuple(row["members"]): row for row in summary["top_ranked"]}
    assert by_members[("producer",)]["medium_not_applicable"] == ["EX_but_m"]
    assert by_members[("consumer", "producer")]["medium_not_applicable"] == []
    unevaluated = {tuple(row["members"]): row for row in summary["unevaluated"]}
    assert unevaluated[("consumer",)]["medium_not_applicable"] == ["EX_glc__D_m"]
    assert summary["medium_not_applicable"] == {
        "ids": ["EX_but_m", "EX_glc__D_m"], "n_candidates": 2,
    }
    manifest = json.loads((out / "manifest.json").read_text())
    assert not any("EX_but_m" in warning for warning in manifest["warnings"])
    from cmig.core.medium_spec import MEDIUM_POLICY

    assert manifest["medium_policy"] == MEDIUM_POLICY


def test_cli_search_records_an_id_no_pool_model_has_as_not_applicable_to_the_pool(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    taxonomy = _pair_pool(tmp_path)
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10\nEX_notreal_m,1\n")
    out = tmp_path / "search"
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "ac",
        "--min-size", "1", "--max-size", "1", "--medium", str(medium), "--out", str(out),
    ])
    assert rc in (0, 3)
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert not any("EX_notreal_m" in w for w in summary["warnings"])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["summary"]["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    # inspect-run shows the manifest's free-form summary: the matched fraction belongs there too
    assert manifest["summary"]["medium_matched"] == {"matched": 1, "requested": 2, "fraction": 0.5}


@pytest.mark.parametrize("rows", [
    "EX_notreal_m,1\nEX_alsonot_m,2\n",              # nonsense ids
    "EX_glc_D(e),10\nEX_ac(e),5\nEX_but(e),1\n",   # AGORA namespace, untranslated
])
def test_cli_search_refuses_a_medium_that_matches_no_pool_model(tmp_path, capsys, rows):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    taxonomy = _pair_pool(tmp_path)
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\n" + rows)
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "ac",
        "--min-size", "1", "--max-size", "1", "--medium", str(medium),
        "--out", str(tmp_path / "search"),
    ])
    assert rc == 2
    assert "none of the medium's" in capsys.readouterr().err


def test_bundled_three_model_pool_on_the_gut_overlay_now_evaluates(tmp_path):
    """The user's case: {iAF987, iHN637, iYO844} lack 19 overlay rows (iML1515/iSFV_1184 only)."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from _gem_fixtures import ROOT, bundled_model_path

    from cmig.cli.main import main

    pool = ("iAF987", "iHN637", "iYO844")
    tax_path = tmp_path / "taxonomy.csv"
    pd.DataFrame({
        "id": list(pool), "file": [str(bundled_model_path(f"{m}.xml")) for m in pool],
        "abundance": [1.0] * 3,
    }).to_csv(tax_path, index=False)
    out = tmp_path / "search"
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "but", "--min-size", "2",
        "--max-size", "2", "--medium",
        str(ROOT / "medium_presets" / "gut_overlay_agora_high_fiber.csv"), "--out", str(out),
    ])
    assert rc == 0
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["n_candidates_ranked"] >= 1
    pool_na = summary["medium_not_applicable_to_pool"]
    assert len(pool_na) == 19 and "EX_26dap__M_m" in pool_na and "EX_pheme_m" in pool_na
    for row in summary["unevaluated"]:
        assert "no counterpart" not in str(row["diagnostic"]), row


# ── provenance and checkpoint identity ─────────────────────────────────────────────────────────


def test_the_medium_policy_marker_moved_and_is_still_not_hashed():
    from cmig.core.manifest import RUN_HASH_COMPONENTS
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.core.workflow_manifest import NON_HASHED_PROVENANCE_MARKERS

    assert MEDIUM_POLICY == "exchange_reactions_by_metabolite_pool_scoped_v3"
    assert NON_HASHED_PROVENANCE_MARKERS["medium_policy"] == MEDIUM_POLICY
    assert "medium_policy" not in RUN_HASH_COMPONENTS


def test_a_checkpoint_from_the_old_medium_rule_cannot_be_resumed(tmp_path):
    """Old checkpoints hold candidates the old rule refused; resuming would mix two rules."""
    from cmig.core.medium_spec import MEDIUM_POLICY
    from cmig.core.search_product import SearchConfig
    from cmig.service.search_service import SearchRequest, search_identity

    files = []
    for member in _TAXONOMY["id"]:
        path = tmp_path / f"{member}.xml"
        path.write_text("model bytes")
        files.append(str(path))
    identity = search_identity(
        SearchRequest(_TAXONOMY.assign(file=files), SearchConfig(target="ac"))
    )
    assert identity["medium_policy"] == MEDIUM_POLICY


def test_bundled_pool_candidate_lp_is_identical_with_and_without_the_rows_it_lacks():
    """The user's scenario at reduced size: a shipped gut overlay on a bundled sub-pool.

    ``iHN637 + iYO844`` lacks rows of the overlay that ``iAF987`` can take up (``EX_2obut_m``,
    ``EX_n2_m``, fatty acids, …). The pool-scoped rule must give exactly the answer of the overlay
    pre-filtered to the pair's own exchanges — the medium the old rule would have accepted.
    """
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from _gem_fixtures import ROOT, bundled_model_path

    from cmig.core.engine import MicomEngine
    from cmig.core.medium_spec import (
        cli_exact_medium,
        load_medium,
        pool_medium_coverage_from_taxonomy,
        translate_medium_for_model,
    )
    from cmig.core.search import Direction, TargetSpec
    from cmig.core.search_product import _evaluate_members

    pool = ("iAF987", "iHN637", "iYO844")
    taxonomy = pd.DataFrame({
        "id": list(pool),
        "file": [str(bundled_model_path(f"{name}.xml")) for name in pool],
        "abundance": [1.0] * len(pool),
    })
    overlay = load_medium(ROOT / "medium_presets" / "gut_overlay_agora_high_fiber.csv")
    known = pool_medium_coverage_from_taxonomy(taxonomy, overlay).known
    medium = MediumSpec(uptake={k: v for k, v in overlay.uptake.items() if k in known})
    coverage = pool_medium_coverage_from_taxonomy(taxonomy, medium)
    assert coverage.unknown == ()
    members = ("iHN637", "iYO844")
    spec = TargetSpec("ac", Direction.MAX_SECRETION)
    engine = MicomEngine()
    with cli_exact_medium(True):
        new = _evaluate_members(
            engine, taxonomy, members, spec, growth_fraction=0.5, solver="gurobi",
            medium_spec=medium, strict_medium=True, medium_pool=coverage,
        )
        community = engine.build_community(
            taxonomy[taxonomy["id"].isin(members)].copy(), cmig_solver="gurobi"
        )
        mapping = translate_medium_for_model(community, medium).mapping
        prefiltered = MediumSpec(uptake={k: medium.uptake[k] for k in mapping})
        old = _evaluate_members(
            engine, taxonomy, members, spec, growth_fraction=0.5, solver="gurobi",
            medium_spec=prefiltered, strict_medium=True,
        )
    dropped = tuple(sorted(set(medium.uptake) - set(prefiltered.uptake)))
    assert len(dropped) >= 5
    assert new.medium_not_applicable == dropped, (new.status, new.diagnostic)
    assert new.status == old.status == "optimal", (new.diagnostic, old.diagnostic)
    assert new.target_flux == pytest.approx(old.target_flux, abs=1e-6)
    assert new.community_growth == pytest.approx(old.community_growth, abs=1e-6)
    assert new.member_growth == pytest.approx(old.member_growth, abs=1e-6)


# ── the other workflows whose candidates are subsets of the selected pool ──────────────────────


def _pair_files(tmp_path, medium_rows: str):
    taxonomy = _pair_pool(tmp_path)
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\n" + medium_rows)
    return tax_path, medium


def test_host_coupling_treats_a_pool_row_the_candidate_lacks_as_not_applicable():
    """Core seam of Host Combination Search: one candidate, the pool's coverage."""
    from cmig.core.engine import SolveResult
    from cmig.core.host_coupling import run_bigg_host_microbe
    from cmig.core.medium_spec import PoolMediumCoverage

    class _Engine:
        def build_community(self, _taxonomy, cmig_solver="gurobi"):
            return _model("community", ["EX_glc__D_m", "EX_ac_m"])

        def cooperative_tradeoff(self, _community, _f, *, cmig_solver="gurobi"):
            return SolveResult(
                objective=0.4, member_growth={"a": 0.4}, abundances={"a": 1.0},
                external_exchange={"ac": 5.0}, member_exchange={"a": {"ac": 5.0}},
                status="optimal", flux_report_status="full",
                growth_solver="gurobi", flux_solver="gurobi", members=["a"],
            )

    host = _model("host", ["EX_ac_e"])
    coverage = PoolMediumCoverage(
        by_model={"a": frozenset({"EX_glc__D_m", "EX_ac_m"}), "b": frozenset({"EX_but_m"})},
        requested=("EX_ac_m", "EX_but_m", "EX_glc__D_m"),
    )
    medium = MediumSpec(uptake={"EX_glc__D_m": 10.0, "EX_ac_m": 0.0, "EX_but_m": 1.0})
    common = dict(
        microbial_biomass_gdw=1.0, host_biomass_gdw=1.0, biomass_basis_kind="validation",
        biomass_basis_source="pool scope fixture", exclude_metabolites=set(),
        microbe_medium=medium, engine=_Engine(),
    )
    taxonomy = pd.DataFrame({"id": ["a"], "file": ["a.xml"], "abundance": [1.0]})
    with pytest.raises(ValueError, match="no counterpart"):
        run_bigg_host_microbe(taxonomy, host.copy(), **common)        # old rule, no pool
    result = run_bigg_host_microbe(taxonomy, host.copy(), medium_pool=coverage, **common)
    assert result.medium_not_applicable == ("EX_but_m",)
    assert result.unapplied_medium_exchanges == ()
    assert not any("EX_but_m" in warning for warning in result.warnings)


def test_host_search_cli_evaluates_single_members_on_a_pool_medium(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files(tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\nEX_but_m,0\n")
    host = _model("bigg_style_host", ["EX_but_e", "EX_ac_e"])
    host.add_reactions([cobra.Reaction("BIOMASS_host")])
    host.reactions.BIOMASS_host.add_metabolites({host.metabolites.ac_e: -1})
    host.reactions.BIOMASS_host.bounds = (0.0, 1000.0)
    host.objective = "BIOMASS_host"
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(host, str(host_path))
    out = tmp_path / "host_search"
    rc = main([
        "host-search-bigg", "--host", str(host_path), "--taxonomy", str(tax_path),
        "--min-size", "1", "--max-size", "1",
        "--microbial-biomass-gdw", "1.0", "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation", "--biomass-basis-source", "pool scope fixture",
        "--microbe-medium", str(medium), "--host-objective", "BIOMASS_host",
        "--target", "ac", "--metric", "objective_value", "--out", str(out),
    ])
    summary = json.loads((out / "host_search_summary.json").read_text())
    rows = summary["top_ranked"] + summary.get("unevaluated", [])
    for row in rows:
        assert "no counterpart" not in str(row.get("diagnostic") or ""), row
    by_members = {tuple(row["members"]): row for row in rows}
    assert by_members[("producer",)]["medium_not_applicable"] == ["EX_but_m"]
    assert by_members[("consumer",)]["medium_not_applicable"] == ["EX_glc__D_m"]
    assert rc in (0, 3)


def test_host_search_cli_records_an_id_no_pool_model_has(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files(tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\nEX_notreal_m,1\n")
    host = _model("bigg_style_host", ["EX_ac_e"])
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(host, str(host_path))
    out = tmp_path / "out"
    rc = main([
        "host-search-bigg", "--host", str(host_path), "--taxonomy", str(tax_path),
        "--min-size", "1", "--max-size", "1",
        "--microbial-biomass-gdw", "1.0", "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation", "--biomass-basis-source", "pool scope fixture",
        "--microbe-medium", str(medium), "--target", "ac", "--metric", "objective_value",
        "--out", str(out),
    ])
    assert rc in (0, 3)
    summary = json.loads((out / "host_search_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    for row in summary["top_ranked"] + summary["unevaluated"]:
        assert "no counterpart" not in str(row["diagnostic"]), row


def test_sweep_member_sets_are_evaluated_on_a_pool_medium(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files(
        tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\nEX_but_m,0\nEX_notreal_m,1\n"
    )
    out = tmp_path / "sweep"
    rc = main([
        "sweep", "--taxonomy", str(tax_path), "--tradeoff-fs", "0.5", "--solvers", "gurobi",
        "--mediums", str(medium), "--member-sets", "producer;consumer",
        "--assume-bigg-namespace", "--exact-medium", "--metric", "growth", "--out", str(out),
    ])
    assert rc == 0, rc
    rows = pd.read_parquet(out / "sweep.parquet")
    assert set(rows["status"]) == {"ok"}, rows[["condition_id", "status", "diagnostic"]]
    manifests = sorted((out / "runs").glob("*/manifest.json"))
    recorded = sorted(
        tuple(json.loads(path.read_text())["provenance"]["medium_not_applicable"])
        for path in manifests
    )
    assert recorded == [("EX_but_m",), ("EX_glc__D_m",)]
    assert {
        tuple(json.loads(path.read_text())["provenance"]["medium_not_applicable_to_pool"])
        for path in manifests
    } == {("EX_notreal_m",)}


def test_medium_gap_surveys_each_pool_model_on_a_pool_medium(tmp_path):
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files(
        tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\nEX_but_m,0\nEX_notreal_m,1\n"
    )
    out = tmp_path / "gap"
    rc = main([
        "medium-gap", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--min-growth", "0.01", "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "medium_gap.json").read_text())
    by_id = {row["id"]: row for row in payload["models"]}
    assert by_id["producer"]["medium_not_applicable"] == "EX_but_m"
    assert by_id["consumer"]["medium_not_applicable"] == "EX_glc__D_m"
    assert payload["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert {row["status"] for row in payload["models"]} <= {"sufficient", "supplement_required"}


# ── review round 1: an unreadable pool model, and naming the model behind a bad exchange ───────


def _pair_files_with_broken(tmp_path, medium_rows: str):
    tax_path, medium = _pair_files(tmp_path, medium_rows)
    broken = tmp_path / "broken.xml"
    broken.write_text("<sbml>not a model</sbml>")
    taxonomy = pd.read_csv(tax_path)
    taxonomy = pd.concat(
        [taxonomy, pd.DataFrame({"id": ["broken"], "file": [str(broken)], "abundance": [0.5]})],
        ignore_index=True,
    )
    taxonomy.to_csv(tax_path, index=False)
    return tax_path, medium


def test_coverage_leaves_an_unreadable_model_out_and_names_it():
    from cmig.core.medium_spec import pool_medium_coverage_from_taxonomy

    taxonomy = pd.DataFrame({"id": ["broken"], "file": ["/nonexistent/broken.xml"]})
    coverage = pool_medium_coverage_from_taxonomy(taxonomy, _POOL_MEDIUM)
    assert coverage.by_model == {}
    assert coverage.unreadable == ("broken",)
    # Zero matches among readable models: refused, naming the models that were not consulted.
    with pytest.raises(ValueError, match="could not be read and were not consulted: broken"):
        coverage.check_namespace()


def test_medium_gap_survey_keeps_its_load_failed_row_for_an_unreadable_model(tmp_path):
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files_with_broken(tmp_path, "EX_glc__D_m,10\nEX_notreal_m,1\n")
    out = tmp_path / "gap"
    rc = main([
        "medium-gap", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--allow-unknown-medium", "--min-growth", "0.01", "--out", str(out),
    ])
    assert rc == 0
    by_id = {row["id"]: row for row in json.loads((out / "medium_gap.json").read_text())["models"]}
    assert by_id["broken"]["status"] == "load_failed"
    assert by_id["producer"]["status"] in {"sufficient", "supplement_required"}


def test_host_search_fails_only_the_candidates_with_an_unreadable_model(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files_with_broken(tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\n")
    host = _model("bigg_style_host", ["EX_ac_e"])
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(host, str(host_path))
    out = tmp_path / "hs"
    rc = main([
        "host-search-bigg", "--host", str(host_path), "--taxonomy", str(tax_path),
        "--min-size", "1", "--max-size", "1",
        "--microbial-biomass-gdw", "1.0", "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation", "--biomass-basis-source", "pool scope fixture",
        "--microbe-medium", str(medium), "--target", "ac", "--metric", "objective_value",
        "--out", str(out),
    ])
    assert rc in (0, 3)
    summary = json.loads((out / "host_search_summary.json").read_text())
    rows = {tuple(r["members"]): r for r in summary["top_ranked"] + summary["unevaluated"]}
    assert rows[("broken",)]["evaluation_status"] == "failed"
    assert rows[("producer",)]["evaluation_status"] != "failed" or "broken" not in str(
        rows[("producer",)]["diagnostic"]
    )
    assert set(rows) == {("producer",), ("consumer",), ("broken",)}


def test_gene_ko_coverage_reads_only_the_consortium_models(tmp_path, capsys):
    """An unreadable non-member must not stop the screen; the consortium is the scope."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files_with_broken(tmp_path, "EX_glc__D_m,10\nEX_ac_m,0\n")
    rc = main([
        "gene-ko-search", "--taxonomy", str(tax_path), "--members", "producer",
        "--member", "producer", "--ko-level", "reaction", "--reactions", "GLC2AC",
        "--target", "ac", "--medium", str(medium), "--exact-medium",
        "--out", str(tmp_path / "ko"),
    ])
    assert rc in (0, 3), capsys.readouterr().err
    # A row only a non-member can take up is not applicable to the consortium's scope.
    _tax, but_medium = _pair_files(tmp_path / "b", "EX_glc__D_m,10\nEX_but_m,1\n")
    rc = main([
        "gene-ko-search", "--taxonomy", str(tax_path), "--members", "producer",
        "--member", "producer", "--ko-level", "reaction", "--reactions", "GLC2AC",
        "--target", "ac", "--medium", str(but_medium), "--exact-medium",
        "--out", str(tmp_path / "ko2"),
    ])
    assert rc in (0, 3), capsys.readouterr().err
    summary = json.loads((tmp_path / "ko2" / "gene_ko_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_but_m"]


def test_an_unresolvable_pool_model_is_left_out_like_an_unreadable_one(tmp_path):
    """Review round 3: one odd model must not refuse the whole run (its candidates fail)."""
    from cmig.core.medium_spec import pool_medium_coverage_from_taxonomy

    bad = cobra.Model("bad")
    reaction = cobra.Reaction("EX_weird")
    reaction.add_metabolites({cobra.Metabolite("weird", compartment="e"): -1})
    bad.add_reactions([reaction])
    path = tmp_path / "bad.json"
    cobra.io.save_json_model(bad, str(path))
    good = tmp_path / "a.json"
    cobra.io.save_json_model(_pool_models()["a"], str(good))
    taxonomy = pd.DataFrame({"id": ["oddball", "a"], "file": [str(path), str(good)]})
    coverage = pool_medium_coverage_from_taxonomy(taxonomy, _POOL_MEDIUM)
    assert coverage.unreadable == ("oddball",)
    assert "a" in coverage.by_model and "oddball" not in coverage.by_model
    coverage.check_namespace()                         # 'a' matches: no refusal
    alone = pool_medium_coverage_from_taxonomy(taxonomy.iloc[:1], _POOL_MEDIUM)
    with pytest.raises(ValueError) as error:          # zero matches: refused, naming it
        alone.check_namespace()
    message = str(error.value)
    assert "oddball" in message and str(path) in message
    assert "unresolved exchange metabolite identity" in message


# ── review round 3: per-candidate zero match, near-miss notation, matched fraction ─────────────


def _ms_consumer():
    """The synthetic consumer with its nutrient exchange in another namespace (`ms_ac`).

    Its acetate uptake is open in the SBML (-10), so on a merge medium it grows on its own
    defaults; its butyrate exchange keeps the BiGG id so the target exists.
    """
    from cmig.synthetic_pair import build_pair_models

    _producer, consumer = build_pair_models()
    consumer.metabolites.get_by_id("ac_e").id = "ms_ac_e"
    consumer.reactions.get_by_id("EX_ac_e").id = "EX_ms_ac_e"
    consumer.repair()
    return consumer


def _pool_with_ms_consumer(tmp_path):
    from cmig.synthetic_pair import build_pair_models

    producer, _consumer = build_pair_models()
    files = {"producer": tmp_path / "producer.json", "consumer_ms": tmp_path / "consumer_ms.json"}
    cobra.io.save_json_model(producer, str(files["producer"]))
    cobra.io.save_json_model(_ms_consumer(), str(files["consumer_ms"]))
    tax_path = tmp_path / "taxonomy.csv"
    pd.DataFrame({"id": list(files), "file": [str(f) for f in files.values()],
                  "abundance": [0.5, 0.5]}).to_csv(tax_path, index=False)
    return tax_path


def test_a_candidate_no_medium_id_reaches_is_split_as_a_namespace_failure():
    from cmig.core.medium_spec import pool_medium_coverage

    coverage = pool_medium_coverage(_pool_models(), _POOL_MEDIUM)
    with pytest.raises(ValueError, match="none of the medium's 4 exchange ids reaches"):
        coverage.split(sorted(_POOL_MEDIUM.uptake), members=("z",))


def test_cli_search_fails_a_candidate_that_no_medium_id_reaches(tmp_path):
    """Reviewer's scenario: a member in another namespace grew on its SBML defaults, ranked ok."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path = _pool_with_ms_consumer(tmp_path)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10\nEX_ac_m,5\n")
    out = tmp_path / "search"
    main([
        "search", "--taxonomy", str(tax_path), "--target", "but",
        "--min-size", "1", "--max-size", "1", "--medium", str(medium), "--out", str(out),
    ])
    summary = json.loads((out / "search_summary.json").read_text())
    ranked = [tuple(r["members"]) for r in summary["top_ranked"]]
    assert ("consumer_ms",) not in ranked
    row = next(r for r in summary["unevaluated"] if r["members"] == ["consumer_ms"])
    assert row["status"] == "failed"
    assert "none of the medium's 2 exchange ids reaches" in row["diagnostic"]


def test_a_near_miss_notation_is_named_with_its_likely_counterpart():
    from cmig.core.medium_spec import pool_medium_coverage
    from cmig.io.agora2 import bigg_exchange_notation

    spec = MediumSpec(uptake={"EX_glc_D_m": 10.0, "EX_ac_m": 1.0, "EX_notreal_m": 1.0})
    coverage = pool_medium_coverage(_pool_models(), spec, notation=bigg_exchange_notation)
    assert coverage.near_misses == {"EX_glc_D_m": "EX_glc__D_m"}
    assert coverage.pool_not_applicable == ("EX_notreal_m",)   # a genuine one stays n/a
    with pytest.raises(ValueError) as error:
        coverage.check_namespace()
    assert "EX_glc_D_m" in str(error.value) and "EX_glc__D_m" in str(error.value)
    # with --allow-unknown-medium a near miss is dropped as not applied, not "not applicable"
    assert coverage.split(["EX_glc_D_m", "EX_notreal_m"], members=("a",)) == (
        (), ("EX_notreal_m",), ("EX_glc_D_m",),
    )


def test_bigg_exchange_notation_reuses_the_agora2_rules():
    from cmig.io.agora2 import bigg_exchange_notation

    assert bigg_exchange_notation("EX_glc_D_m") == "EX_glc__D_m"
    assert bigg_exchange_notation("EX_glc_D(e)") == "EX_glc__D_e"
    assert bigg_exchange_notation("EX_but(e)") == "EX_but_e"
    assert bigg_exchange_notation("EX_glc__D_m") == "EX_glc__D_m"
    assert bigg_exchange_notation("EX_ac_m") == "EX_ac_m"


def test_cli_search_refuses_a_near_miss_and_reports_the_matched_fraction(tmp_path, capsys):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium = _pair_files(tmp_path, "EX_glc_D_m,10\nEX_ac_m,5\nEX_notreal_m,1\n")
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "ac", "--min-size", "1",
        "--max-size", "1", "--medium", str(medium), "--out", str(tmp_path / "strict"),
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "EX_glc_D_m" in err and "EX_glc__D_m" in err
    out = tmp_path / "relaxed"
    rc = main([
        "search", "--taxonomy", str(tax_path), "--target", "ac", "--min-size", "1",
        "--max-size", "1", "--medium", str(medium), "--allow-unknown-medium", "--out", str(out),
    ])
    assert rc in (0, 3)
    printed = capsys.readouterr().out
    assert "not applicable to this pool" in printed and "EX_notreal_m" in printed
    summary = json.loads((out / "search_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert summary["medium_matched"] == {"matched": 1, "requested": 3, "fraction": 0.3333}
    rows = {tuple(r["members"]): r for r in summary["top_ranked"] + summary["unevaluated"]}
    assert rows[("producer",)]["medium_matched"] == {"matched": 1, "requested": 3}
    assert any("EX_glc_D_m" in w for w in summary["warnings"])   # dropped as not applied


