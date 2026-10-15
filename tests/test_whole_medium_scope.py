"""The medium rule for workflows that solve the selected models as ONE community (or one model).

User decision (2026-10-15): "일부만 없으면 빼고 진행" applies to every medium-taking workflow, not
only to the pool workflows (search, host search, gene KO, sweep member sets, pool medium-gap).
For Community Solve, strain growth, ratio impact, host-microbe coupling, host KO impact, pair,
a sweep without member sets, single, minimal medium and a single-model medium-gap the "pool" is
the selected models themselves (one model for a single-model command):

* a medium id that none of the selected models can take up is *not applicable* — dropped with
  the LP unchanged (it has no exchange to bound), recorded as ``medium_not_applicable_to_pool``,
  status unaffected;
* a medium none of whose ids matches is refused (exit 2) — the namespace-mismatch signature;
* an id that matches after the AGORA2 notation rules (a near miss, e.g. ``EX_glc_D_m``) is refused
  (exit 2) naming the likely counterpart;
* ``--allow-unknown-medium`` drops zero-match media / near misses as *not applied* (degraded).
"""

from __future__ import annotations

import json
from pathlib import Path

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


def _notation(exchange_id: str) -> str:
    from cmig.io.agora2 import bigg_exchange_notation

    return bigg_exchange_notation(exchange_id)


# ── core: the selected models are the pool ─────────────────────────────────────────────────────


def test_an_id_no_selected_model_has_is_not_applicable_and_the_rest_is_applied():
    from cmig.core.medium_spec import apply_medium_scoped

    community = _model("community", ["EX_glc__D_m", "EX_ac_m"])
    spec = MediumSpec(uptake={"EX_glc__D_m": 4.0, "EX_ac_m": 0.0, "EX_notreal_m": 7.0})
    translation, scoped = apply_medium_scoped(community, spec, strict=True, notation=_notation)
    assert scoped.not_applicable == ("EX_notreal_m",)
    assert scoped.not_applied == ()
    assert scoped.as_record() == {
        "medium_not_applicable_to_pool": ["EX_notreal_m"],
        "medium_matched": {"matched": 2, "requested": 3, "fraction": 0.6667},
    }
    assert translation.unmatched == ("EX_notreal_m",)
    assert community.reactions.EX_glc__D_m.lower_bound == -4.0


def test_a_fully_matched_medium_records_nothing_not_applicable():
    from cmig.core.medium_spec import apply_medium_scoped

    community = _model("community", ["EX_glc__D_m", "EX_ac_m"])
    _translation, scoped = apply_medium_scoped(
        community, MediumSpec(uptake={"EX_glc__D_m": 4.0}), strict=True, notation=_notation
    )
    assert scoped.as_record() == {
        "medium_not_applicable_to_pool": [],
        "medium_matched": {"matched": 1, "requested": 1, "fraction": 1.0},
    }


@pytest.mark.parametrize(("rows", "message"), [
    ({"EX_notreal_m": 1.0, "EX_alsonot_m": 2.0}, "none of the medium's 2 exchange ids matches"),
    ({"EX_glc_D_m": 10.0, "EX_ac_m": 1.0}, "EX_glc_D_m -> EX_glc__D_m"),
])
def test_a_zero_match_or_near_miss_medium_is_refused_in_strict_mode(rows, message):
    from cmig.core.medium_spec import apply_medium_scoped

    community = _model("community", ["EX_glc__D_m", "EX_ac_m"])
    before = {r.id: r.bounds for r in community.reactions}
    with pytest.raises(ValueError, match=message.replace("(", r"\(").replace(")", r"\)")):
        apply_medium_scoped(community, MediumSpec(uptake=rows), strict=True, notation=_notation)
    assert {r.id: r.bounds for r in community.reactions} == before   # refused before applying


def test_allow_unknown_drops_a_zero_match_medium_or_a_near_miss_as_not_applied():
    from cmig.core.medium_spec import apply_medium_scoped

    community = _model("community", ["EX_glc__D_m", "EX_ac_m"])
    _t, nothing = apply_medium_scoped(
        community, MediumSpec(uptake={"EX_notreal_m": 1.0}), strict=False, notation=_notation
    )
    assert nothing.not_applied == ("EX_notreal_m",) and nothing.not_applicable == ()
    _t, near = apply_medium_scoped(
        community, MediumSpec(uptake={"EX_glc_D_m": 10.0, "EX_ac_m": 1.0, "EX_zz_m": 1.0}),
        strict=False, notation=_notation,
    )
    assert near.not_applied == ("EX_glc_D_m",)
    assert near.not_applicable == ("EX_zz_m",)


# ── CLI fixtures: the synthetic producer/consumer pair (glucose -> acetate -> butyrate) ─────────


def _pair(tmp_path: Path, medium_rows: str) -> tuple[Path, Path, Path]:
    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = build_pair_taxonomy(tmp_path / "pair")
    tax_path = tmp_path / "taxonomy.csv"
    taxonomy.to_csv(tax_path, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\n" + medium_rows)
    producer = Path(str(taxonomy.loc[taxonomy["id"] == "producer", "file"].iloc[0]))
    return tax_path, medium, producer


_WITH_UNKNOWN = "EX_glc__D_m,10\nEX_ac_m,5\nEX_notreal_m,7\n"
_NONSENSE = "EX_notreal_m,1\nEX_alsonot_m,2\n"
_NEAR_MISS = "EX_glc_D_m,10\nEX_ac_m,5\n"


def _solve(tmp_path: Path, tax_path: Path, medium: Path, out: str, *flags: str) -> int:
    from cmig.cli.main import main

    return main([
        "solve", "--taxonomy", str(tax_path), "--medium", str(medium), "--assume-bigg-namespace",
        "--out", str(tmp_path / out), *flags,
    ])


def test_solve_records_an_id_no_selected_model_has_and_stays_ok(tmp_path, capsys):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    rc = _solve(tmp_path, tax_path, medium, "solve")
    printed = capsys.readouterr().out
    assert rc == 0
    manifest = json.loads((tmp_path / "solve" / "manifest.json").read_text())
    provenance = manifest["provenance"]
    assert provenance["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert provenance["medium_matched"] == {"matched": 2, "requested": 3, "fraction": 0.6667}
    assert "medium_unapplied" not in str(manifest.get("diagnostic") or "")
    assert "not applicable" in printed and "EX_notreal_m" in printed


@pytest.mark.parametrize(("rows", "message"), [
    (_NONSENSE, "none of the medium's 2 exchange ids matches"),
    (_NEAR_MISS, "EX_glc_D_m -> EX_glc__D_m"),
])
def test_solve_refuses_a_zero_match_or_near_miss_medium(tmp_path, capsys, rows, message):
    pytest.importorskip("micom")
    tax_path, medium, _producer = _pair(tmp_path, rows)
    assert _solve(tmp_path, tax_path, medium, "solve") == 2
    assert message in capsys.readouterr().err


def test_solve_allow_unknown_keeps_todays_behaviour_for_a_zero_match_medium(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    tax_path, medium, _producer = _pair(tmp_path, _NONSENSE)
    assert _solve(tmp_path, tax_path, medium, "solve", "--allow-unknown-medium") == 0
    manifest = json.loads((tmp_path / "solve" / "manifest.json").read_text())
    assert "medium_unapplied" in str(manifest["diagnostic"])
    assert "EX_alsonot_m" in str(manifest["diagnostic"])
    assert manifest["provenance"]["medium_not_applicable_to_pool"] == []


@pytest.mark.parametrize("exact", [False, True])
def test_solve_lp_is_identical_with_the_full_medium_and_the_prefiltered_one(tmp_path, exact):
    """Bundled iHN637 + iYO844 on a shipped gut overlay: 32 rows neither model can take up."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from _gem_fixtures import ROOT, bundled_model_path

    from cmig.core.medium_spec import load_medium
    from cmig.core.tidy import TidyBundle

    pool = ("iHN637", "iYO844")
    tax_path = tmp_path / "taxonomy.csv"
    pd.DataFrame({
        "id": list(pool), "file": [str(bundled_model_path(f"{m}.xml")) for m in pool],
        "abundance": [1.0] * len(pool),
    }).to_csv(tax_path, index=False)
    overlay_path = ROOT / "medium_presets" / "gut_overlay_agora_high_fiber.csv"
    flags = ["--exact-medium"] if exact else []
    assert _solve(tmp_path, tax_path, overlay_path, "full", *flags) == 0
    full = json.loads((tmp_path / "full" / "manifest.json").read_text())["provenance"]
    dropped = full["medium_not_applicable_to_pool"]
    assert len(dropped) >= 5 and "EX_pheme_m" in dropped
    overlay = load_medium(overlay_path)
    assert any(overlay.uptake[row] > 0 for row in dropped)
    prefiltered = tmp_path / "prefiltered.csv"
    prefiltered.write_text("exchange_id,uptake_limit\n" + "".join(
        f"{k},{v!r}\n" for k, v in overlay.uptake.items() if k not in dropped
    ))
    assert _solve(tmp_path, tax_path, prefiltered, "pre", *flags) == 0
    pre = json.loads((tmp_path / "pre" / "manifest.json").read_text())["provenance"]
    assert pre["medium_not_applicable_to_pool"] == []

    def _numbers(run: str):
        bundle = TidyBundle.read(tmp_path / run)
        growth = {r["node_id"]: r["growth"] for r in bundle.nodes.to_pylist()
                  if r.get("node_type") == "member"}
        profile = {r["metabolite"]: r["net_flux"] for r in bundle.profile.to_pylist()}
        return growth, profile

    full_growth, full_profile = _numbers("full")
    pre_growth, pre_profile = _numbers("pre")
    assert set(full_growth) == set(pool) and sum(full_growth.values()) > 0
    assert full_growth == pytest.approx(pre_growth, abs=1e-9)
    assert set(full_profile) == set(pre_profile)
    assert full_profile == pytest.approx(pre_profile, abs=1e-9)


def test_bundled_three_model_community_solve_no_longer_refuses_the_overlay_rows(tmp_path, capsys):
    """The user's selection {iAF987, iHN637, iYO844} with gut_overlay_agora_high_fiber.

    Before: exit 2, "medium exchange has no counterpart in the target model" (19 ids, rows only
    iML1515/iSFV_1184 have). Now those 19 rows are not applicable and the community is solved.
    It still fails — exit 3, solver_failed — for a different, real reason: iAF987's SBML forces
    Fe3+ uptake (>= 49.21) and the overlay caps EX_fe3_m at 0.1. Lifting only that cap makes the
    same three models solve, which pins the cause.
    """
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from _gem_fixtures import ROOT, bundled_model_path

    pool = ("iAF987", "iHN637", "iYO844")
    tax_path = tmp_path / "taxonomy.csv"
    pd.DataFrame({
        "id": list(pool), "file": [str(bundled_model_path(f"{m}.xml")) for m in pool],
        "abundance": [1.0] * len(pool),
    }).to_csv(tax_path, index=False)
    overlay = ROOT / "medium_presets" / "gut_overlay_agora_high_fiber.csv"
    rc = _solve(tmp_path, tax_path, overlay, "solve")
    err = capsys.readouterr().err
    assert "no counterpart" not in err, err
    assert rc == 3 and "solver_failed" in err, (rc, err)
    provenance = json.loads((tmp_path / "solve" / "manifest.json").read_text())["provenance"]
    pool_na = provenance["medium_not_applicable_to_pool"]
    assert len(pool_na) == 19 and "EX_26dap__M_m" in pool_na and "EX_pheme_m" in pool_na
    assert provenance["medium_matched"] == {"matched": 114, "requested": 133, "fraction": 0.8571}

    lifted = tmp_path / "overlay_fe3_lifted.csv"
    lines = overlay.read_text().splitlines()
    assert "EX_fe3_m,0.1,nutrient" in lines
    lifted.write_text("\n".join(
        "EX_fe3_m,100,nutrient" if line == "EX_fe3_m,0.1,nutrient" else line for line in lines
    ) + "\n")
    assert _solve(tmp_path, tax_path, lifted, "lifted") == 0, capsys.readouterr().err


# ── single-model commands: the model is the pool ──────────────────────────────────────────────


def _single(tmp_path: Path, model: Path, medium: Path, out: str, *flags: str) -> int:
    from cmig.cli.main import main

    return main([
        "single", "--model", str(model), "--fba", "--medium", str(medium), "--exact-medium",
        "--assume-bigg-namespace", "--out", str(tmp_path / out), *flags,
    ])


def test_single_records_an_id_the_model_lacks_and_matches_the_prefiltered_answer(tmp_path):
    pytest.importorskip("gurobipy")
    _tax, medium, producer = _pair(tmp_path, "EX_glc__D_m,10\nEX_but_m,3\nEX_notreal_m,7\n")
    assert _single(tmp_path, producer, medium, "full") == 0
    summary = json.loads((tmp_path / "full" / "single_summary.json").read_text())
    assert summary["status"] == "ok"
    assert summary["medium_not_applicable_to_pool"] == ["EX_but_m", "EX_notreal_m"]
    assert summary["medium_matched"] == {"matched": 1, "requested": 3, "fraction": 0.3333}
    prefiltered = tmp_path / "pre.csv"
    prefiltered.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10\n")
    assert _single(tmp_path, producer, prefiltered, "pre") == 0
    pre = json.loads((tmp_path / "pre" / "single_summary.json").read_text())
    assert summary["methods"]["FBA"]["objective"] > 0
    assert summary["methods"]["FBA"]["objective"] == pytest.approx(
        pre["methods"]["FBA"]["objective"], abs=1e-9
    )
    manifest = json.loads((tmp_path / "full" / "manifest.json").read_text())
    assert manifest["summary"]["medium_not_applicable_to_pool"] == ["EX_but_m", "EX_notreal_m"]


@pytest.mark.parametrize(("rows", "message"), [
    (_NONSENSE, "none of the medium's 2 exchange ids matches"),
    (_NEAR_MISS, "EX_glc_D_m -> EX_glc__D_m"),
])
def test_single_refuses_a_zero_match_or_near_miss_medium(tmp_path, capsys, rows, message):
    _tax, medium, producer = _pair(tmp_path, rows)
    assert _single(tmp_path, producer, medium, "out") == 2
    assert message in capsys.readouterr().err


def test_single_allow_unknown_names_a_dropped_near_miss_and_degrades(tmp_path):
    pytest.importorskip("gurobipy")
    _tax, medium, producer = _pair(tmp_path, "EX_glc_D_m,10\nEX_ac_m,5\nEX_glc__D_m,10\n")
    # EX_glc__D_m matches, so EX_glc_D_m duplicates it in another notation: not applied.
    rc = _single(tmp_path, producer, medium, "out", "--allow-unknown-medium")
    assert rc == 0
    summary = json.loads((tmp_path / "out" / "single_summary.json").read_text())
    assert summary["status"] == "degraded"
    assert summary["medium_unapplied"] == ["EX_glc_D_m"]
    assert any("EX_glc_D_m" in w for w in summary["warnings"])


def test_minimal_medium_records_an_id_the_model_lacks(tmp_path):
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    _tax, medium, producer = _pair(tmp_path, "EX_glc__D_m,10\nEX_but_m,3\nEX_notreal_m,7\n")
    out = tmp_path / "mm"
    rc = main([
        "minimal-medium", "--model", str(producer), "--min-growth", "0.01",
        "--medium", str(medium), "--assume-bigg-namespace", "--out", str(out),
    ])
    assert rc == 0
    summary = json.loads((out / "minimal_medium_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_but_m", "EX_notreal_m"]
    assert summary["medium_matched"]["matched"] == 1


def test_minimal_medium_refuses_a_near_miss(tmp_path, capsys):
    from cmig.cli.main import main

    _tax, medium, producer = _pair(tmp_path, _NEAR_MISS)
    rc = main([
        "minimal-medium", "--model", str(producer), "--min-growth", "0.01",
        "--medium", str(medium), "--assume-bigg-namespace", "--out", str(tmp_path / "mm"),
    ])
    assert rc == 2
    assert "EX_glc_D_m -> EX_glc__D_m" in capsys.readouterr().err


def test_medium_gap_on_one_model_records_an_id_it_lacks(tmp_path):
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    _tax, medium, producer = _pair(tmp_path, "EX_glc__D_m,10\nEX_but_m,3\nEX_notreal_m,7\n")
    out = tmp_path / "gap"
    rc = main([
        "medium-gap", "--model", str(producer), "--medium", str(medium),
        "--min-growth", "0.01", "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "medium_gap.json").read_text())
    assert payload["medium_not_applicable_to_pool"] == ["EX_but_m", "EX_notreal_m"]
    assert payload["models"][0]["status"] in {"sufficient", "supplement_required"}


def test_medium_gap_on_one_model_refuses_a_zero_match_medium(tmp_path, capsys):
    from cmig.cli.main import main

    _tax, medium, producer = _pair(tmp_path, _NONSENSE)
    rc = main([
        "medium-gap", "--model", str(producer), "--medium", str(medium),
        "--min-growth", "0.01", "--out", str(tmp_path / "gap"),
    ])
    assert rc == 2
    assert "none of the medium's 2 exchange ids matches" in capsys.readouterr().err


# ── the other whole-community workflows ────────────────────────────────────────────────────────


def test_pair_records_an_id_neither_member_has(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    out = tmp_path / "pair_out"
    rc = main([
        "pair", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--assume-bigg-namespace", "--out", str(out),
    ])
    summary = json.loads((out / "pair_summary.json").read_text())
    assert rc == 0, summary
    condition = summary["conditions"][0]
    assert condition["status"] == "ok", condition
    assert condition["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert condition["medium_matched"] == {"matched": 2, "requested": 3, "fraction": 0.6667}
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]


def test_pair_refuses_a_near_miss(tmp_path, capsys):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _NEAR_MISS)
    rc = main([
        "pair", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--assume-bigg-namespace", "--out", str(tmp_path / "pair_out"),
    ])
    assert rc == 2
    assert "EX_glc_D_m -> EX_glc__D_m" in capsys.readouterr().err


def test_strain_growth_records_an_id_no_member_has(tmp_path, capsys):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    out = tmp_path / "sg"
    rc = main([
        "strain-growth", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--exact-medium", "--out", str(out),
    ])
    assert rc in (0, 3)
    summary = json.loads((out / "strain_growth_summary.json").read_text())
    assert summary["community_status"] == "optimal", summary
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert summary["medium_matched"] == {"matched": 2, "requested": 3, "fraction": 0.6667}
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["summary"]["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert "not applicable" in capsys.readouterr().out


def test_strain_growth_refuses_a_zero_match_medium(tmp_path, capsys):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _NONSENSE)
    rc = main([
        "strain-growth", "--taxonomy", str(tax_path), "--medium", str(medium),
        "--out", str(tmp_path / "sg"),
    ])
    assert rc == 2
    assert "none of the medium's 2 exchange ids matches" in capsys.readouterr().err


def test_abundance_impact_records_an_id_no_member_has(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    out = tmp_path / "ai"
    rc = main([
        "abundance-impact", "--taxonomy", str(tax_path), "--member", "producer",
        "--fractions", "0.25,0.5", "--target", "ac", "--medium", str(medium),
        "--out", str(out),
    ])
    assert rc == 0
    summary = json.loads((out / "abundance_impact_summary.json").read_text())
    assert {row["status"] for row in summary["rows"]} == {"optimal"}, summary["rows"]
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert summary["medium_matched"]["matched"] == 2


def test_abundance_impact_allow_unknown_names_what_it_dropped(tmp_path):
    """It used to drop unknown ids without any record at all."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, "EX_glc_D_m,10\nEX_ac_m,5\n")
    out = tmp_path / "ai"
    rc = main([
        "abundance-impact", "--taxonomy", str(tax_path), "--member", "producer",
        "--fractions", "0.5", "--target", "ac", "--medium", str(medium),
        "--allow-unknown-medium", "--out", str(out),
    ])
    assert rc == 0
    summary = json.loads((out / "abundance_impact_summary.json").read_text())
    assert summary["medium_unapplied"] == ["EX_glc_D_m"]
    assert summary["status"] == "degraded"
    assert any("EX_glc_D_m" in w for w in summary["warnings"])


def _host_fixture(tmp_path: Path, microbe_rows: str):
    host = _model("bigg_style_host", ["EX_but_e", "EX_ac_e"])
    host.add_reactions([cobra.Reaction("BIOMASS_host")])
    host.reactions.BIOMASS_host.add_metabolites({host.metabolites.ac_e: -1})
    host.reactions.BIOMASS_host.bounds = (0.0, 1000.0)
    host.objective = "BIOMASS_host"
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(host, str(host_path))
    tax_path, medium, _producer = _pair(tmp_path, microbe_rows)
    common = [
        "--host", str(host_path), "--taxonomy", str(tax_path),
        "--microbial-biomass-gdw", "1.0", "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation", "--biomass-basis-source", "whole-medium fixture",
        "--microbe-medium", str(medium), "--host-objective", "BIOMASS_host",
    ]
    return common


def test_host_microbe_records_an_id_no_member_has_without_degrading(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    out = tmp_path / "hm"
    rc = main(["host-microbe-bigg", *_host_fixture(tmp_path, _WITH_UNKNOWN), "--out", str(out)])
    assert rc == 0
    summary = json.loads((out / "host_microbe_bigg_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert summary["medium_matched"] == {"matched": 2, "requested": 3, "fraction": 0.6667}
    assert not any("EX_notreal_m" in w for w in summary["warnings"])
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "ok", manifest["status"]
    assert manifest["summary"]["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert manifest["summary"]["unapplied_medium_exchanges"] == []


def test_host_microbe_refuses_a_near_miss_microbial_medium(tmp_path, capsys):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    rc = main([
        "host-microbe-bigg", *_host_fixture(tmp_path, _NEAR_MISS), "--out", str(tmp_path / "hm"),
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "microbial medium" in err and "EX_glc_D_m -> EX_glc__D_m" in err, err


def test_host_ko_impact_records_an_id_no_member_has(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    out = tmp_path / "hko"
    rc = main([
        "host-ko-impact", *_host_fixture(tmp_path, _WITH_UNKNOWN), "--member", "producer",
        "--ko-level", "reaction", "--reactions", "GLC2AC", "--target", "ac", "--out", str(out),
    ])
    assert rc in (0, 3)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["summary"]["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert not any("EX_notreal_m" in w for w in manifest["warnings"])


def test_sweep_without_member_sets_records_an_id_no_member_has(tmp_path):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    out = tmp_path / "sweep"
    rc = main([
        "sweep", "--taxonomy", str(tax_path), "--tradeoff-fs", "0.5", "--solvers", "gurobi",
        "--mediums", str(medium), "--assume-bigg-namespace", "--metric", "growth",
        "--out", str(out),
    ])
    assert rc == 0
    rows = pd.read_parquet(out / "sweep.parquet")
    assert set(rows["status"]) == {"ok"}, rows[["condition_id", "status", "diagnostic"]]
    manifests = sorted((out / "runs").glob("*/manifest.json"))
    assert manifests
    for path in manifests:
        provenance = json.loads(path.read_text())["provenance"]
        assert provenance["medium_not_applicable_to_pool"] == ["EX_notreal_m"]


# ── review round 5: console and sweep summary ──────────────────────────────────────────────────


def test_solve_prints_the_ids_it_dropped_under_the_flag_and_the_match(tmp_path, capsys):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    tax_path, medium, _producer = _pair(tmp_path, "EX_glc_D_m,10\nEX_ac_m,5\nEX_notreal_m,1\n")
    assert _solve(tmp_path, tax_path, medium, "solve", "--allow-unknown-medium") == 0
    out = capsys.readouterr().out
    assert "NOT applied" in out and "EX_glc_D_m" in out, out
    assert "medium ids matched: 1/3" in out, out
    assert "only 1 of 3 medium ids match" in out, out     # < 50 %: warned, status unaffected
    manifest = json.loads((tmp_path / "solve" / "manifest.json").read_text())
    assert manifest["provenance"]["medium_unapplied"] == ["EX_glc_D_m"]


def test_solve_prints_the_not_applicable_ids_when_the_solve_fails(tmp_path, capsys, monkeypatch):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    import cmig.cli.main as cli

    monkeypatch.setattr(cli, "_solve_artifact_consistency", lambda _bundle: {
        "consistent": False, "n_failing": 1, "n_keys": 1, "max_residual": 9.0,
        "worst": [{"metabolite": "ac", "edge_sum": 1.0, "net_flux": 2.0}],
    })
    rc = _solve(tmp_path, tax_path, medium, "solve")
    captured = capsys.readouterr()
    assert rc == 3
    assert "EX_notreal_m" in captured.out + captured.err
    assert "medium ids matched: 2/3" in captured.out + captured.err


def test_single_model_console_says_not_applicable_to_this_model(tmp_path, capsys):
    pytest.importorskip("gurobipy")
    _tax, medium, producer = _pair(tmp_path, "EX_glc__D_m,10\nEX_but_m,3\nEX_notreal_m,7\n")
    assert _single(tmp_path, producer, medium, "out") == 0
    out = capsys.readouterr().out
    assert "2 medium ids are not applicable to this model" in out, out
    assert "this pool" not in out
    assert "medium ids matched: 1/3" in out


def test_sweep_summary_and_console_carry_the_not_applicable_ids(tmp_path, capsys):
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(tmp_path, _WITH_UNKNOWN)
    out = tmp_path / "sweep"
    assert main([
        "sweep", "--taxonomy", str(tax_path), "--tradeoff-fs", "0.5,0.6", "--solvers", "gurobi",
        "--mediums", str(medium), "--assume-bigg-namespace", "--metric", "growth",
        "--out", str(out),
    ]) == 0
    summary = json.loads((out / "sweep_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
    assert summary["medium_matched"] == {
        "medium.csv": {"matched": 2, "requested": 3, "fraction": 0.6667}
    }
    printed = capsys.readouterr().out
    assert "not applicable" in printed and "EX_notreal_m" in printed


def test_sweep_member_sets_with_namespace_decisions_use_the_pool_labels(tmp_path):
    """An id another member set has is not applicable to THIS community, not to the pool."""
    pytest.importorskip("micom")
    pytest.importorskip("gurobipy")
    from cmig.cli.main import main

    tax_path, medium, _producer = _pair(
        tmp_path, "EX_glc__D_m,10\nEX_ac_m,5\nEX_but_m,0\nEX_notreal_m,1\n"
    )
    decisions = tmp_path / "namespace.json"
    decisions.write_text(json.dumps([{
        "metabolite": "ac", "source_id": "source:ac", "target_id": "bigg:ac",
        "confidence": "high", "status": "resolved", "rationale": "manual",
    }]))
    out = tmp_path / "sweep"
    assert main([
        "sweep", "--taxonomy", str(tax_path), "--tradeoff-fs", "0.5", "--solvers", "gurobi",
        "--mediums", str(medium), "--member-sets", "producer;consumer",
        "--namespace-decisions", str(decisions), "--exact-medium", "--metric", "growth",
        "--out", str(out),
    ]) == 0
    manifests = sorted((out / "runs").glob("*/manifest.json"))
    provenance = [json.loads(path.read_text())["provenance"] for path in manifests]
    assert sorted(tuple(p["medium_not_applicable"]) for p in provenance) == [
        ("EX_but_m",), ("EX_glc__D_m",),
    ]
    assert {tuple(p["medium_not_applicable_to_pool"]) for p in provenance} == {("EX_notreal_m",)}
    summary = json.loads((out / "sweep_summary.json").read_text())
    assert summary["medium_not_applicable_to_pool"] == ["EX_notreal_m"]
