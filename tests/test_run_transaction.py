"""Directory publication must never mix old and partial new search results."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from cmig.io.run_transaction import staged_run


@pytest.mark.parametrize("stage_name", ["search_rankings.csv", "search_plot.svg", "manifest.json"])
def test_cli_output_failure_preserves_previous_run(tmp_path, monkeypatch, stage_name):
    from cmig.cli import main as cli

    target = tmp_path / "out"
    target.mkdir()
    (target / "manifest.json").write_text("old manifest")
    (target / "search_rankings.csv").write_text("old rankings")
    (target / "notes.txt").write_text("user notes")
    previous = {path.name: path.read_bytes() for path in target.iterdir()}

    def fail(args):
        (Path(args.out) / stage_name).write_text("partial new output")
        raise OSError(f"injected {stage_name} failure")

    monkeypatch.setattr(cli, "_cmd_search_impl", fail)
    assert cli._cmd_search(SimpleNamespace(out=str(target))) == 2
    assert {path.name: path.read_bytes() for path in target.iterdir()} == previous


def test_publish_preserves_notes_without_following_old_artifact_symlink(tmp_path):
    target = tmp_path / "out"
    target.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("do not touch")
    (target / "result.json").symlink_to(external)
    (target / "notes.txt").write_text("my notes")
    with staged_run(target, artifacts=frozenset({"result.json"})) as stage:
        (stage / "result.json").write_text("new result")
    assert external.read_text() == "do not touch"
    assert (target / "result.json").read_text() == "new result"
    assert not (target / "result.json").is_symlink()
    assert (target / "notes.txt").read_text() == "my notes"


def test_publication_rename_failure_rolls_back(tmp_path, monkeypatch):
    from cmig.io import run_transaction as module

    target = tmp_path / "out"
    target.mkdir()
    (target / "old").write_text("previous complete run")
    replace = module.os.replace

    def fail_once(source, destination):
        if Path(source).name == "run":
            raise OSError("injected publication failure")
        return replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_once)
    with pytest.raises(OSError, match="publication failure"), staged_run(target) as stage:
        (stage / "new").write_text("new")
    assert (target / "old").read_text() == "previous complete run"
    assert not (target / "new").exists()


def test_failed_rollback_keeps_recoverable_backup(tmp_path, monkeypatch):
    from cmig.io import run_transaction as module

    target = tmp_path / "out"
    target.mkdir()
    (target / "old").write_text("recoverable")
    replace = module.os.replace

    def fail_restore(source, destination):
        if Path(source) != target:
            raise OSError("injected failure")
        return replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_restore)
    with pytest.raises(OSError, match="previous run is preserved"), staged_run(target):
        pass
    backups = list(tmp_path.glob(".out.previous-*"))
    assert len(backups) == 1
    assert (backups[0] / "old").read_text() == "recoverable"


def test_concurrent_publisher_is_rejected(tmp_path):
    with staged_run(tmp_path / "out"):
        with pytest.raises(ValueError, match="writer holds"), staged_run(tmp_path / "out"):
            pytest.fail("concurrent writer entered")


def test_context_checkpoint_cannot_be_inside_published_output(tmp_path):
    from cmig.cli import main as cli
    from cmig.core.search_execution import SearchControl
    from cmig.service.search_service import search_control

    out = tmp_path / "out"
    with search_control(SearchControl(checkpoint=out / "state.json")):
        assert cli._cmd_search(SimpleNamespace(out=str(out))) == 2
    assert not out.exists()
