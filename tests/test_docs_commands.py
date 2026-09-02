"""Every command line printed in the README or the usage guide must be runnable.

Documentation drifts silently: a flag is renamed, the example that used it keeps
being copy-pasted by readers, and the first thing a new user meets is an argparse
error. The old README carried exactly that — a `host-microbe-bigg` example with a
`--target` and an `--assume-bigg-namespace` the command has never had.

This parses the shell blocks out of the docs and checks each `uv run cmig …`
invocation against the real parser, so a renamed flag fails the build instead of
the reader.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from cmig.cli.main import GUI_CLI_WORKFLOWS, build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.md", "docs/USAGE.md")
#: `cmig <command>` in a template line, not a real invocation.
_PLACEHOLDER = re.compile(r"^[<$]")
_INVOCATION = re.compile(r"^\s*uv run cmig\s+(?P<rest>.+)$")


def _subcommands() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    action = next(
        item for item in parser._actions if isinstance(item, argparse._SubParsersAction)
    )
    return dict(action.choices)


def _invocations(text: str) -> list[list[str]]:
    """Every `uv run cmig …` command in the document, with line continuations joined."""
    joined = text.replace("\\\n", " ")
    commands = []
    for line in joined.splitlines():
        match = _INVOCATION.match(line)
        if match is None:
            continue
        tokens = match.group("rest").split()
        if tokens and not _PLACEHOLDER.match(tokens[0]):
            commands.append(tokens)
    return commands


@pytest.mark.parametrize("document", DOCUMENTS)
def test_documented_commands_and_flags_exist(document: str) -> None:
    subcommands = _subcommands()
    problems: list[str] = []
    invocations = _invocations((REPO_ROOT / document).read_text(encoding="utf-8"))
    assert invocations, f"{document} shows no `uv run cmig` example at all"

    for tokens in invocations:
        command, *arguments = tokens
        if command not in subcommands:
            problems.append(f"unknown command `cmig {command}`")
            continue
        options = {
            option
            for action in subcommands[command]._actions
            for option in action.option_strings
        }
        problems += [
            f"`cmig {command}` has no {argument}"
            for argument in arguments
            if argument.startswith("--") and argument not in options
        ]
    assert not problems, f"{document} documents commands that do not exist: {problems}"


def test_readme_points_at_the_usage_guide_and_it_exists() -> None:
    """The README delegates usage; a dangling pointer would leave a reader nowhere."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/USAGE.md" in readme
    for relative in re.findall(r"\]\((?!https?:)([^)#]+)", readme):
        assert (REPO_ROOT / relative).exists(), f"README links to a missing path: {relative}"


def test_usage_guide_links_resolve() -> None:
    usage_path = REPO_ROOT / "docs" / "USAGE.md"
    usage = usage_path.read_text(encoding="utf-8")
    for relative in re.findall(r"\]\((?!https?:|#)([^)#]+)", usage):
        assert (usage_path.parent / relative).resolve().exists(), (
            f"docs/USAGE.md links to a missing path: {relative}"
        )


def test_readme_workflow_count_matches_the_catalogue() -> None:
    """The README states how many analyses exist; that number has to be the real one."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    stated = re.search(r"all (\d+) analyses", readme)
    assert stated is not None, "README no longer states the analysis count"
    assert int(stated.group(1)) == len(GUI_CLI_WORKFLOWS)
