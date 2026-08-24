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
