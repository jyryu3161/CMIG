"""Round-7 T1 regressions for the CLI exact-medium contract and manifest schema."""

from __future__ import annotations

import argparse
import json

import pytest

import cmig.cli.main as cli
from cmig.core.medium_spec import (
    MEDIUM_APPLICATION_EXACT,
    MEDIUM_APPLICATION_MERGE,
    MediumSpec,
    cli_exact_medium,
    medium_application_report,
    requested_medium_application_mode,
)
from cmig.core.workflow_envelope_golden import golden_components
from cmig.core.workflow_manifest import (
    WORKFLOW_MANIFEST_SCHEMA_VERSION,
    compute_workflow_hash,
    medium_component,
)


def _top_level_commands() -> dict[str, argparse.ArgumentParser]:
    parser = cli.build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    return subparsers.choices


def _options(parser: argparse.ArgumentParser) -> set[str]:
    return {
        option
        for action in parser._actions
        for option in action.option_strings
    }


def test_every_medium_bearing_command_accepts_exact_medium():
    commands = _top_level_commands()
    medium_options = {"--medium", "--microbe-medium", "--mediums"}
    medium_commands = {
        name for name, parser in commands.items() if _options(parser) & medium_options
    }
    exact_commands = {
        name for name, parser in commands.items() if "--exact-medium" in _options(parser)
    }

    assert medium_commands == {
        "solve",
        "search",
        "strain-growth",
        "abundance-impact",
        "gene-ko-search",
        "host-microbe-bigg",
        "host-ko-impact",
        "host-search-bigg",
        "sweep",
    }
    assert exact_commands == medium_commands


def test_cli_flag_routes_existing_medium_callers_to_exact_translation(monkeypatch):
    cobra = pytest.importorskip("cobra")
    seen: list[dict[str, object]] = []

    def fake_solve(_args: argparse.Namespace) -> int:
        model = cobra.Model("round7-exact-medium")
        glucose = cobra.Metabolite("glc__D_e", compartment="e")
        oxygen = cobra.Metabolite("o2_e", compartment="e")
        glucose_exchange = cobra.Reaction("EX_glc__D_e")
        oxygen_exchange = cobra.Reaction("EX_o2_e")
        glucose_exchange.add_metabolites({glucose: -1})
        oxygen_exchange.add_metabolites({oxygen: -1})
        glucose_exchange.bounds = (-10.0, 1000.0)
        oxygen_exchange.bounds = (-20.0, 1000.0)
        model.add_reactions([glucose_exchange, oxygen_exchange])
        translation = medium_application_report(
            model, MediumSpec(uptake={"EX_glc__D_m": 7.0})
        )
        seen.append(translation.as_provenance())
        seen[-1]["oxygen_lower_bound"] = oxygen_exchange.lower_bound
        return 0

    monkeypatch.setattr(cli, "_cmd_solve", fake_solve)
    common = ["solve", "--taxonomy", "unused.csv", "--out", "unused"]

    assert cli.main([*common, "--exact-medium"]) == 0
    assert seen[-1]["medium_application_mode"] == MEDIUM_APPLICATION_EXACT
    assert seen[-1]["oxygen_lower_bound"] == 0.0

    # The ContextVar is reset at command exit: the following default run stays a merge.
    assert cli.main(common) == 0
    assert seen[-1]["medium_application_mode"] == MEDIUM_APPLICATION_MERGE
    assert seen[-1]["oxygen_lower_bound"] == -20.0


def test_workflow_medium_mode_is_hashed_and_schema_announces_the_drift():
    assert WORKFLOW_MANIFEST_SCHEMA_VERSION == "1.2"
    merge = golden_components("model_pool_search")
    exact = golden_components("model_pool_search")
    merge["medium"] = medium_component(
        "diet.csv", "medium:sha256", application_mode=MEDIUM_APPLICATION_MERGE
    )
    exact["medium"] = medium_component(
        "diet.csv", "medium:sha256", application_mode=MEDIUM_APPLICATION_EXACT
    )

    assert merge["medium"]["medium_application_mode"] == MEDIUM_APPLICATION_MERGE
    assert exact["medium"]["medium_application_mode"] == MEDIUM_APPLICATION_EXACT
    assert compute_workflow_hash("model_pool_search", merge) != compute_workflow_hash(
        "model_pool_search", exact
    )


def test_parallel_gene_ko_arms_inherit_the_exact_medium_context():
    with cli_exact_medium(True):
        rows = cli._map_ko_evaluations(
            ["a", "b"],
            lambda item: {
                "item": item,
                "mode": requested_medium_application_mode(has_custom_medium=True),
            },
            jobs=2,
        )

    assert [row["mode"] for row in rows] == [
        MEDIUM_APPLICATION_EXACT,
        MEDIUM_APPLICATION_EXACT,
    ]


def test_inspect_run_keeps_pre_1_2_workflow_manifests_readable(tmp_path, capsys):
    old_manifest = {
        "manifest_schema_version": "1.1",
        "manifest_scope": "workflow",
        "workflow_kind": "model_pool_search",
        "run_hash": "old-run-hash",
        "status": "ok",
        "artifacts": [],
        "components": {
            "medium": {
                "source": "diet.csv",
                "checksum": "medium:old",
                "allow_unknown_medium": False,
                "namespace_bridge": {},
            }
        },
    }
    (tmp_path / "manifest.json").write_text(json.dumps(old_manifest))

    assert cli.main(["inspect-run", "--run-dir", str(tmp_path), "--format", "json"]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["kind"] == "model_pool_search"
    assert inspected["run_hash"] == "old-run-hash"
    assert inspected["manifest"]["manifest_schema_version"] == "1.1"
    assert "medium_application_mode" not in inspected["manifest"]["components"]["medium"]
