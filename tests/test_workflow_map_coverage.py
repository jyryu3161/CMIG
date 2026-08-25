"""Keep ``cmig workflows`` complete as top-level commands are added."""

from __future__ import annotations

import argparse

from cmig.cli.main import GUI_CLI_WORKFLOWS, build_parser

# Bootstrap/UI commands describe the CLI itself rather than an executable analysis workflow.
_NON_WORKFLOW_COMMANDS = {"version", "solvers", "workflows", "gui"}


def test_every_non_fixture_subcommand_is_in_the_workflow_map():
    parser = build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    commands = {
        name
        for name in subparsers.choices
        if "fixture" not in name and name not in _NON_WORKFLOW_COMMANDS
    }
    mapped = {
        entry["cli_command"].removeprefix("cmig ").split()[0]
        for entry in GUI_CLI_WORKFLOWS
    }

    assert commands <= mapped, (
        f"commands missing from `cmig workflows`: {sorted(commands - mapped)}"
    )


def test_round7_user_facing_commands_are_mapped_exactly_once():
    required = {
        "host-map",
        "dfba-sensitivity",
        "model-quality",
        "publication-benchmark",
        "render-figure",
        "stats-sweep",
        "stats-demo",
        "namespace-suggest",
        "golden",
    }
    mapped = [
        entry["cli_command"].removeprefix("cmig ").split()[0]
        for entry in GUI_CLI_WORKFLOWS
    ]

    assert all(mapped.count(command) == 1 for command in required)


def test_round8_pair_delta_single_commands_are_mapped_with_medium_controls():
    required = {"pair", "delta", "single", "minimal-medium"}
    by_command = {
        entry["cli_command"].removeprefix("cmig ").split()[0]: entry
        for entry in GUI_CLI_WORKFLOWS
    }

    assert required <= set(by_command)
    for command in ("pair", "single", "minimal-medium"):
        options = set(by_command[command]["common_options"])
        assert {"--medium", "--exact-medium", "--allow-unknown-medium"} <= options


def test_round9_community_dfba_is_mapped_with_its_interpretability_controls():
    by_command = {
        entry["cli_command"].removeprefix("cmig ").split()[0]: entry
        for entry in GUI_CLI_WORKFLOWS
    }

    mapped = by_command["dfba-community"]
    assert set(mapped["required_args"]) == {
        "--taxonomy", "--t-end", "--initial", "--initial-biomass", "--out",
    }
    assert {
        "--member-vmax", "--close-untracked-uptake", "--allow-failed-run",
    } <= set(mapped["common_options"])
