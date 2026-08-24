"""Round 7 — the host-coupling path was over-constrained relative to every other path.

Measured on `main` @ ``e9f3b02`` with a licensed Gurobi, on the bundled 3-member pool
``iML1515 + iYO844 + iHN637``:

``cmig solve --medium medium_presets/gut_overlay_vmh_high_fiber_x100.csv
--allow-unknown-medium`` returns growth ``0.0847149208736683``; the *same* medium on
``cmig host-microbe-bigg --microbe-medium`` dies with

    medium exchange has no counterpart in the target model (matched on metabolite): ['EX_n2_m']

and there was no flag on any host command that could relax it, because
``host_coupling.run_bigg_host_microbe`` hard-coded ``strict=True``. ``EX_n2_m`` is one row
of eighty and its requested ``uptake_limit`` is ``0.0`` — the overlay asks for nitrogen gas
to be *closed* on a community that has no nitrogen-gas exchange at all.

The rule these tests pin is the one the product already applies everywhere else: strict is
the default, the flag is the opt-in, and a relaxed run must name what it dropped and report
itself as ``degraded``. Nothing is ever filtered silently.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

cobra = pytest.importorskip("cobra")

from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.medium_spec import MediumSpec  # noqa: E402

# ── doubles ────────────────────────────────────────────────────────────────────────────────────
# The "community" is a real cobra model exposing MICOM-style `EX_*_m` exchanges, because the
# medium machinery reads `.exchanges` and rewrites `model.boundary` bounds. Only the solve is
# faked, so the medium decision under test is the production one.


def _met(mid: str):
    return cobra.Metabolite(mid, compartment=mid.rsplit("_", 1)[-1])


def _rxn(rid: str, stoich: dict[str, float], bounds: tuple[float, float]):
    reaction = cobra.Reaction(rid)
    reaction.add_metabolites({_met(mid): coefficient for mid, coefficient in stoich.items()})
    reaction.bounds = bounds
    return reaction


def _community_model() -> cobra.Model:
    """A community that can be offered glucose and can secrete acetate — and has no `n2`."""
    model = cobra.Model("fake_community")
    model.add_reactions([
        _rxn("EX_glc__D_m", {"glc__D_m": -1}, (-10.0, 1000.0)),
        _rxn("EX_ac_m", {"ac_m": -1}, (0.0, 1000.0)),
    ])
    return model


def _bigg_host() -> cobra.Model:
    host = cobra.Model("bigg_host")
    host.add_reactions([
        _rxn("EX_ac_e", {"ac_e": -1}, (0.0, 1000.0)),
        _rxn("EX_o2_e", {"o2_e": -1}, (0.0, 1000.0)),
        _rxn("ACt", {"ac_e": -1, "ac_c": 1}, (-1000.0, 1000.0)),
        _rxn("O2t", {"o2_e": -1, "o2_c": 1}, (-1000.0, 1000.0)),
        _rxn("AC_OX", {"ac_c": -1, "o2_c": -1, "atp_c": 1}, (0.0, 1000.0)),
        _rxn("BIOMASS_host", {"atp_c": -1}, (0.0, 1000.0)),
    ])
    host.objective = "BIOMASS_host"
    return host


class _Engine:
    """MICOM seam double: real community model, scripted solve outcome."""

    def __init__(self, status: str = "optimal", diagnostic: str | None = None) -> None:
        self.status = status
        self.diagnostic = diagnostic
        self.community: cobra.Model | None = None

    def build_community(self, _taxonomy, cmig_solver="gurobi"):
        self.community = _community_model()
        return self.community

    def cooperative_tradeoff(self, _community, _tradeoff_f, *, cmig_solver="gurobi"):
        if self.status != "optimal":
            return SolveResult(
                objective=0.0, member_growth={}, abundances={}, external_exchange={},
                member_exchange={}, status=self.status, flux_report_status="none",
                growth_solver="gurobi", flux_solver="gurobi", members=["A"],
                diagnostic=self.diagnostic,
            )
        return SolveResult(
            objective=0.4, member_growth={"A": 0.4}, abundances={"A": 1.0},
            external_exchange={"ac": 5.0}, member_exchange={"A": {"ac": 5.0}},
            status="optimal", flux_report_status="full",
            growth_solver="gurobi", flux_solver="gurobi", members=["A"],
        )


#: One row the community can honour, one it cannot — the shape of the shipped VMH overlay.
INAPPLICABLE = MediumSpec(uptake={"EX_glc__D_m": 10.0, "EX_n2_m": 0.0})


def _run(**kwargs):
    from cmig.core.host_coupling import run_bigg_host_microbe

    defaults = dict(
        microbial_biomass_gdw=1.0,
        host_biomass_gdw=1.0,
        biomass_basis_kind="validation",
        biomass_basis_source="round-7 host medium strictness fixture",
        exclude_metabolites=set(),
    )
    defaults.update(kwargs)
    return run_bigg_host_microbe(None, _bigg_host(), **defaults)


# ── 1. strict stays the default, and the refusal names its cause and its remedy ────────────────


def test_the_host_path_refuses_an_inapplicable_medium_and_names_both_id_and_remedy():
    """`solver_failed` sends a user to debug the solver; this message sends them to their medium.

    The round-6 scenario surfaced only `microbial community solve was not optimal
    (status=solver_failed)`. The id list is the whole diagnostic value here, and so is naming
    the flag that makes the run possible — a message that names neither is why this survived.
    """
    with pytest.raises(ValueError) as excinfo:
        _run(microbe_medium=INAPPLICABLE, engine=_Engine())

    message = str(excinfo.value)
    assert "EX_n2_m" in message, message
    assert "--allow-unknown-medium" in message, message
    # It must be clear *which* of the two media a host run carries is at fault.
    assert "microbial medium" in message, message


def test_an_applicable_medium_is_still_applied_strictly_by_default():
    engine = _Engine()
    result = _run(microbe_medium=MediumSpec(uptake={"EX_glc__D_m": 3.0}), engine=engine)

    assert result.unapplied_medium_exchanges == ()
    assert engine.community is not None
    assert engine.community.reactions.get_by_id("EX_glc__D_m").lower_bound == -3.0
    assert not any("were NOT applied" in warning for warning in result.warnings)


# ── 2. the opt-in exists, and it degrades visibly ──────────────────────────────────────────────


def test_the_host_path_can_be_told_to_drop_what_the_community_cannot_offer():
    engine = _Engine()
    result = _run(microbe_medium=INAPPLICABLE, strict_medium=False, engine=engine)

    assert result.unapplied_medium_exchanges == ("EX_n2_m",)
    assert any(
        "EX_n2_m" in warning and "NOT applied" in warning for warning in result.warnings
    ), result.warnings
    # The rest of the medium really was applied — a relaxed run is not a no-medium run.
    assert engine.community is not None
    assert engine.community.reactions.get_by_id("EX_glc__D_m").lower_bound == -10.0


def test_dropped_medium_ids_are_named_even_when_the_community_solve_fails():
    """This is the branch the round-6 scenario hit, and it disclosed nothing about the medium."""
    result = _run(
        microbe_medium=INAPPLICABLE,
        strict_medium=False,
        engine=_Engine(status="solver_failed", diagnostic='{"code": "solver_error"}'),
    )

    assert result.community_status == "solver_failed"
    assert result.unapplied_medium_exchanges == ("EX_n2_m",)
    assert any("EX_n2_m" in warning for warning in result.warnings), result.warnings


# ── 3. a failed community solve names its cause, not only its status ───────────────────────────


def test_a_failed_community_solve_carries_its_diagnostic_into_the_warnings():
    """Round-6 published `status=solver_failed` with the cause reachable nowhere in the run.

    `run_bigg_host_microbe` had the diagnostic in hand (`community_result.diagnostic`) and put
    it only on the inner `HostSolveResult`, which no host command writes out. A reader of the
    manifest saw two generic lines and no cause at all.
    """
    diagnostic = json.dumps({
        "code": "solver_error",
        "message": "pFBA flux stage failed: OptimizationError: could not get community "
                   "growth rate.",
    })
    result = _run(engine=_Engine(status="solver_failed", diagnostic=diagnostic))

    assert any(
        "could not get community growth rate" in warning for warning in result.warnings
    ), result.warnings


# ── 4. the host's own medium must not be filtered silently either ──────────────────────────────


def test_a_host_medium_entry_the_host_cannot_offer_is_refused_rather_than_dropped():
    """`solve_bigg_host` silently ignored host-medium keys with no host exchange.

    `add_availability` returned `(None, flux)` and nothing recorded it, so a host background
    could be half-applied while every artifact reported a complete run.
    """
    from cmig.core.host_coupling import solve_bigg_host

    with pytest.raises(ValueError) as excinfo:
        solve_bigg_host(
            _bigg_host(),
            {"ac": 5.0},
            host_medium={"o2": 20.0, "n2": 1.0},
            solver="gurobi",
        )
    message = str(excinfo.value)
    assert "n2" in message, message
    assert "--allow-unknown-medium" in message, message


def test_a_relaxed_host_medium_names_what_it_dropped():
    from cmig.core.host_coupling import solve_bigg_host

    result = solve_bigg_host(
        _bigg_host(),
        {"ac": 5.0},
        host_medium={"o2": 20.0, "n2": 1.0},
        strict_medium=False,
        solver="gurobi",
    )
    assert result.status == "optimal"
    assert any("n2" in warning for warning in result.warnings), result.warnings


# ── 5. the census: every medium-capable command exposes the same relaxation ────────────────────


#: command -> the medium options it accepts. Round 5's medium fix reached `strain-growth` only,
#: round 6's objective guard reached some commands only, and this round found the same shape
#: again: five commands had `--allow-unknown-medium` and four did not.
MEDIUM_CAPABLE_COMMANDS = {
    "solve": ("--medium",),
    "search": ("--medium",),
    "strain-growth": ("--medium",),
    "abundance-impact": ("--medium",),
    "sweep": ("--mediums",),
    "gene-ko-search": ("--medium",),
    "host-microbe-bigg": ("--microbe-medium", "--host-medium"),
    "host-search-bigg": ("--microbe-medium", "--host-medium"),
    "host-ko-impact": ("--microbe-medium", "--host-medium"),
}


def _subparser_options(command: str) -> set[str]:
    from cmig.cli.main import build_parser

    parser = build_parser()
    actions = [
        action for action in parser._subparsers._group_actions  # noqa: SLF001 - argparse has no API
        if hasattr(action, "choices")
    ]
    for action in actions:
        if command in (action.choices or {}):
            sub = action.choices[command]
            return {option for entry in sub._actions for option in entry.option_strings}  # noqa: SLF001
    raise AssertionError(f"subcommand not found: {command}")


@pytest.mark.parametrize(("command", "medium_options"), sorted(MEDIUM_CAPABLE_COMMANDS.items()))
def test_every_medium_capable_command_can_relax_an_inapplicable_medium(command, medium_options):
    options = _subparser_options(command)
    for medium_option in medium_options:
        assert medium_option in options, f"{command} lost {medium_option}"
    assert "--allow-unknown-medium" in options, (
        f"{command} accepts a medium but cannot be told what to do when the model cannot "
        "honour it, so the medium is fatal there and merely degrading everywhere else"
    )


def test_the_workflow_map_advertises_the_relaxation_wherever_it_exists():
    """`cmig workflows` is the LLM/automation contract, and it drifted from the parser.

    Four commands' parsers accepted `--allow-unknown-medium` while the map never mentioned it, so
    anything driving CMIG from the map could not discover the one option that makes a real diet
    file usable. A capability that exists but cannot be found is the same failure one layer up.
    """
    from cmig.cli.main import GUI_CLI_WORKFLOWS

    for entry in GUI_CLI_WORKFLOWS:
        options = list(entry.get("common_options", []))
        if not any("medium" in option for option in options):
            continue
        assert "--allow-unknown-medium" in options, entry["cli_command"]


# ── 6. the flag is answer-determining, so it must move the run_hash ────────────────────────────


def test_allow_unknown_medium_is_recorded_in_the_host_workflow_manifest():
    """Two runs that differ only in this flag are different experiments and must not share a hash.

    They apply different media: one applies the whole file, the other applies it minus the rows
    the model could not honour. Round 5 already put `allow_unknown_medium` inside the `medium`
    component; `_host_medium_component` was building that component without it.
    """
    from cmig.cli.main import _host_medium_component
    from cmig.core.workflow_manifest import workflow_components_for

    def _component(allow: bool) -> dict[str, object]:
        return _host_medium_component(SimpleNamespace(
            microbe_medium=None, host_medium=None, allow_unknown_medium=allow,
        ))

    assert _component(True)["allow_unknown_medium"] is True
    assert _component(False)["allow_unknown_medium"] is False
    assert _component(True) != _component(False)
    for kind in ("host_microbe_bigg", "host_search_bigg", "host_ko_impact", "gene_ko_search"):
        assert "medium" in workflow_components_for(kind), kind


# ── 7. end to end through the CLI, which is where the defect was reachable ─────────────────────


def _component(manifest: dict, name: str):
    """`components` serializes as the ordered `[[name, value], …]` pair list it is hashed as."""
    for entry in manifest["components"]:
        if entry[0] == name:
            return entry[1]
    raise AssertionError(f"component not in manifest: {name}")


def _write_cli_fixture(tmp_path):
    from cmig.synthetic_pair import build_pair_taxonomy

    host = cobra.Model("bigg_style_host")
    host.add_reactions([
        _rxn("EX_but_e", {"but_e": -1}, (0.0, 1000.0)),
        _rxn("EX_o2_e", {"o2_e": -1}, (0.0, 1000.0)),
        _rxn("BUTt", {"but_e": -1, "but_c": 1}, (-1000.0, 1000.0)),
        _rxn("O2t", {"o2_e": -1, "o2_c": 1}, (-1000.0, 1000.0)),
        _rxn("BUT_OX", {"but_c": -1, "o2_c": -2, "atp_c": 4}, (0.0, 1000.0)),
        _rxn("BIOMASS_host", {"atp_c": -1}, (0.0, 1000.0)),
    ])
    host.objective = "BIOMASS_host"
    host_path = tmp_path / "host.xml"
    cobra.io.write_sbml_model(host, str(host_path))
    taxonomy = tmp_path / "taxonomy.csv"
    build_pair_taxonomy(tmp_path / "microbes").to_csv(taxonomy, index=False)
    host_medium = tmp_path / "host_medium.json"
    host_medium.write_text(json.dumps({"o2": 100.0}) + "\n")
    # `EX_n2_m` is the shipped VMH overlay's own unmatched row, reproduced at fixture scale.
    microbe_medium = tmp_path / "microbe_medium.csv"
    microbe_medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10.0\nEX_n2_m,0.0\n")
    return host_path, taxonomy, host_medium, microbe_medium


def _host_argv(host_path, taxonomy, host_medium, microbe_medium, out):
    return [
        "host-microbe-bigg",
        "--host", str(host_path),
        "--taxonomy", str(taxonomy),
        "--microbial-biomass-gdw", "1.0",
        "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation",
        "--biomass-basis-source", "round-7 CLI fixture",
        "--host-medium", str(host_medium),
        "--microbe-medium", str(microbe_medium),
        "--host-objective", "BIOMASS_host",
        "--out", str(out),
    ]


def test_host_microbe_bigg_cli_refuses_the_medium_by_default_and_says_why(tmp_path, capsys):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    fixture = _write_cli_fixture(tmp_path)
    rc = main(_host_argv(*fixture, tmp_path / "strict"))
    assert rc == 2
    stderr = capsys.readouterr().err
    assert "EX_n2_m" in stderr, stderr
    assert "--allow-unknown-medium" in stderr, stderr


def test_host_microbe_bigg_cli_degrades_and_names_the_dropped_exchange(tmp_path, capsys):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    fixture = _write_cli_fixture(tmp_path)
    out = tmp_path / "relaxed"
    rc = main(_host_argv(*fixture, out) + ["--allow-unknown-medium"])
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "degraded", manifest["status"]
    assert any("EX_n2_m" in warning for warning in manifest["warnings"]), manifest["warnings"]
    assert _component(manifest, "medium")["allow_unknown_medium"] is True
    summary = json.loads((out / "host_microbe_bigg_summary.json").read_text())
    assert any("EX_n2_m" in warning for warning in summary["warnings"])


def test_the_two_host_runs_do_not_share_a_run_hash(tmp_path):
    """The flag changes which medium was applied, so it has to change the fingerprint."""
    pytest.importorskip("micom")
    from cmig.cli.main import main

    host_path, taxonomy, host_medium, _bad = _write_cli_fixture(tmp_path)
    applicable = tmp_path / "applicable.csv"
    applicable.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10.0\n")

    hashes = []
    for index, flags in enumerate(([], ["--allow-unknown-medium"])):
        out = tmp_path / f"run{index}"
        assert main(
            _host_argv(host_path, taxonomy, host_medium, applicable, out) + flags
        ) == 0
        hashes.append(json.loads((out / "manifest.json").read_text())["run_hash"])
    assert hashes[0] != hashes[1]


# ── 7b. host-ko-impact: the degradation has to reach the comparison, not just one arm ─────────


def test_host_ko_impact_degrades_when_the_medium_was_only_partly_applied():
    """Baseline and every arm stand on the same medium — and it is not the file that is named.

    `assemble_result` derives the run status, so a caller that could add a warning but not a tier
    would leave `inspect-run` reporting `ok` for a knockout comparison run on a medium the
    manifest's `medium_checksum` does not describe.
    """
    from cmig.core.host_ko_impact import HostArm, assemble_result

    def _arm(label: str, objective: float) -> HostArm:
        return HostArm(
            label=label, member=None, ko_id=None, ko_level=None, run_status="ok",
            community_status="optimal", community_growth=0.4, host_status="optimal",
            host_viable=True, host_objective=objective, target_transfer=1.0,
            matched_exchanges={"ac": "EX_ac_e"},
        )

    baseline = _arm("baseline", 2.0)
    arms = [_arm("m:R1", 1.5)]
    clean = assemble_result(
        target="ac", baseline=baseline, arms=arms, biomass_basis={"kind": "measured"},
        comparability={},
    )
    assert clean.status == "ok"

    degraded = assemble_result(
        target="ac", baseline=baseline, arms=arms, biomass_basis={"kind": "measured"},
        comparability={}, degraded_reasons=["medium exchanges were NOT applied: ['EX_n2_m']"],
    )
    assert degraded.status == "degraded"
    assert any("EX_n2_m" in warning for warning in degraded.warnings), degraded.warnings


# ── 8. gene-ko-search could not be given a medium at all ───────────────────────────────────────


def test_gene_ko_search_applies_the_requested_medium_to_every_arm(tmp_path, monkeypatch):
    """The census question asked "where is the flag?"; here the whole capability was missing.

    `search_model_pool` has taken `medium_spec`/`strict_medium` since round 5 and
    `gene-ko-search` passed neither, so a knockout screen silently ran on MICOM's permissive
    default medium while its sibling `search` honoured `--medium`. Adding only the relaxation
    flag would have shipped a switch wired to nothing.
    """
    import cmig.core.search_product as search_product
    from cmig.cli import main as cli_main

    seen: list[dict[str, object]] = []
    original = search_product.search_model_pool

    def _spy(engine, taxonomy, config, *, medium_spec=None, strict_medium=True):
        seen.append({"medium_spec": medium_spec, "strict_medium": strict_medium})
        return original(
            engine, taxonomy, config, medium_spec=medium_spec, strict_medium=strict_medium
        )

    monkeypatch.setattr(search_product, "search_model_pool", _spy)

    from cmig.synthetic_pair import build_pair_taxonomy

    taxonomy = tmp_path / "taxonomy.csv"
    build_pair_taxonomy(tmp_path / "microbes").to_csv(taxonomy, index=False)
    medium = tmp_path / "medium.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_glc__D_m,10.0\nEX_n2_m,0.0\n")

    pytest.importorskip("micom")
    rc = cli_main.main([
        "gene-ko-search",
        "--taxonomy", str(taxonomy),
        "--members", "producer,consumer",
        "--member", "producer",
        "--reactions", "GLC2AC",
        "--ko-level", "reaction",
        "--target", "ac",
        "--medium", str(medium),
        "--allow-unknown-medium",
        "--out", str(tmp_path / "ko"),
    ])
    assert rc == 0
    assert seen, "gene-ko-search never reached search_model_pool"
    assert all(entry["medium_spec"] is not None for entry in seen), seen
    assert all(entry["strict_medium"] is False for entry in seen), seen
    manifest = json.loads((tmp_path / "ko" / "manifest.json").read_text())
    assert _component(manifest, "medium")["allow_unknown_medium"] is True
    assert _component(manifest, "medium")["source"] == str(medium)


# ── 9. GUI parity: the same over-constraint, one surface over ──────────────────────────────────


def test_the_gui_host_tab_can_relax_the_medium_too():
    """The Host tab already offered both media, so it inherited the identical hard stop.

    Round 5's parity finding was that the GUI's failures were *exposure* failures, not
    arithmetic ones. A control the CLI has and the GUI does not is exactly that shape.
    """
    import inspect

    pytest.importorskip("PySide6")
    from cmig.gui.host_view import HostImpactView

    source = inspect.getsource(HostImpactView)
    assert "allow_unknown_medium_check" in source
    assert '"allow_unknown_medium"' in source, "request() must carry the control to the runner"

    from cmig.gui import app as gui_app

    argv_source = inspect.getsource(gui_app)
    assert argv_source.count('argv.append("--allow-unknown-medium")') == 3, (
        "the Host tab's run, its rank-combinations run, and (round 8) the real Sweep tab all "
        "build argv, and all three take a medium"
    )


# ── 10. the sibling host commands degrade the same way, end to end ─────────────────────────────


def test_host_search_bigg_cli_degrades_and_names_the_dropped_exchange(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    host_path, taxonomy, host_medium, microbe_medium = _write_cli_fixture(tmp_path)
    out = tmp_path / "host_search"
    rc = main([
        "host-search-bigg",
        "--host", str(host_path),
        "--taxonomy", str(taxonomy),
        "--microbial-biomass-gdw", "1.0",
        "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation",
        "--biomass-basis-source", "round-7 CLI fixture",
        "--host-medium", str(host_medium),
        "--microbe-medium", str(microbe_medium),
        "--host-objective", "BIOMASS_host",
        "--target", "but",
        "--metric", "target_transfer",
        "--allow-unknown-medium",
        "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "degraded", manifest["status"]
    assert any("EX_n2_m" in warning for warning in manifest["warnings"]), manifest["warnings"]
    assert _component(manifest, "medium")["allow_unknown_medium"] is True
    # The candidate itself was evaluated — a partly applied medium degrades the run, it does not
    # disqualify the rows, which would silently shrink the ranking.
    summary = json.loads((out / "host_search_summary.json").read_text())
    assert summary["n_candidates_evaluated"] == 1
    assert summary["n_candidates_failed"] == 0


def test_host_ko_impact_cli_degrades_and_names_the_dropped_exchange(tmp_path):
    pytest.importorskip("micom")
    from cmig.cli.main import main

    host_path, taxonomy, host_medium, microbe_medium = _write_cli_fixture(tmp_path)
    out = tmp_path / "host_ko"
    rc = main([
        "host-ko-impact",
        "--host", str(host_path),
        "--taxonomy", str(taxonomy),
        "--member", "producer",
        "--ko-level", "reaction",
        "--reactions", "GLC2AC",
        "--target", "but",
        "--microbial-biomass-gdw", "1.0",
        "--host-biomass-gdw", "1.0",
        "--biomass-basis-kind", "validation",
        "--biomass-basis-source", "round-7 CLI fixture",
        "--host-medium", str(host_medium),
        "--microbe-medium", str(microbe_medium),
        "--host-objective", "BIOMASS_host",
        "--allow-unknown-medium",
        "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["status"] == "degraded", manifest["status"]
    assert any("EX_n2_m" in warning for warning in manifest["warnings"]), manifest["warnings"]
    assert _component(manifest, "medium")["allow_unknown_medium"] is True
