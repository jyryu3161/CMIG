from __future__ import annotations

import json
from pathlib import Path

import pytest
from gui_project_helpers import make_project, textbook_sbml

from cmig.io import project as proj


def test_check_records_structured_namespace_and_objective(tmp_path: Path) -> None:
    check = proj.check_model_file(textbook_sbml(tmp_path / "textbook.xml"))
    assert check.namespace_mappings == {
        "total": 20, "resolved": 0, "unresolved_high": 20, "warned_low": 0,
    }
    assert check.objective_warning is None  # one biomass term


def test_apply_check_copies_structured_values(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, textbook_sbml(tmp_path / "src" / "t.xml"))
    assert entry.namespace_mappings is not None and entry.namespace_mappings["total"] == 20
    proj.save_project(project)
    again = proj.open_project(project.root).model(entry.id)
    assert again.namespace_mappings == entry.namespace_mappings
    assert again.objective_warning is None


def _entry(**overrides: object) -> proj.ModelEntry:
    base: dict[str, object] = dict(
        id="m", file="models/m.xml", source_path="/x/m.xml", sha256="abc", format="xml",
        added="t", status="warning", biomass=["BIOMASS_X"],
        warnings=["20 unresolved high-confidence namespace mappings block solve"],
    )
    base.update(overrides)
    return proj.ModelEntry(**base)  # type: ignore[arg-type]


def test_namespace_state_from_structured_values_or_legacy_text() -> None:
    assert proj.namespace_review_state(_entry()) == "blocked"  # legacy: from warning text
    assert proj.namespace_review_state(_entry(warnings=[])) == "clear"
    assert proj.namespace_review_state(
        _entry(namespace_mappings={"total": 3, "resolved": 1, "unresolved_high": 0,
                                   "warned_low": 2})
    ) == "review"
    assert proj.namespace_review_state(_entry(status="failed")) == "unknown"


def test_confirm_and_revoke(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    assert proj.confirmation_state(entry) == "none"
    proj.confirm_namespace(project, "a", at="2026-10-14T00:00:00+00:00")
    assert entry.namespace_confirmed == {"sha256": entry.sha256,
                                         "at": "2026-10-14T00:00:00+00:00"}
    assert proj.namespace_confirmed(entry)
    proj.revoke_namespace(project, "a")
    assert entry.namespace_confirmed is None


def test_confirmation_void_after_file_change(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    proj.confirm_namespace(project, "a")
    proj.confirm_namespace(project, "b")
    assert proj.confirmation_summary(project, ["a", "b"]) == (True, [])
    (project.root / project.model("b").file).write_text("<sbml id='edited'/>")
    proj.verify_checksums(project)
    assert proj.confirmation_state(project.model("b")) == "changed"
    assert proj.confirmation_summary(project, ["a", "b"]) == (False, ["b"])
    with pytest.raises(proj.ProjectError):
        proj.confirm_namespace(project, "b")  # a changed copy cannot be confirmed


def test_confirmation_summary_of_nothing_is_not_all_confirmed(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    assert proj.confirmation_summary(project, []) == (False, [])


def test_check_reasons_worst_first() -> None:
    assert proj.check_reason(_entry(status="failed")) == ("✗", "Unreadable")
    assert proj.check_reason(_entry(integrity="changed")) == ("⚠", "File changed")
    assert proj.check_reason(_entry(integrity="missing")) == ("⚠", "File missing")
    assert proj.check_reason(_entry()) == ("⚠", "Namespace not reviewed")
    assert proj.check_reason(_entry(warnings=[], biomass=[])) == ("⚠", "No objective")
    many = [f"R{i}" for i in range(283)]
    assert proj.check_reason(_entry(warnings=[], biomass=many)) == (
        "⚠", "Objective is not growth"
    )
    assert proj.check_reason(_entry(warnings=[])) == ("✓", "Ready")
    confirmed = _entry(namespace_confirmed={"sha256": "abc", "at": "t"})
    assert proj.check_reason(confirmed) == ("✓", "Ready · namespace confirmed")
    both = _entry(biomass=[])
    assert [text for _s, text in proj.check_reasons(both)] == [
        "Namespace not reviewed", "No objective",
    ]


def test_run_request_round_trip(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "search-20261014-101010"
    run_dir.mkdir(parents=True)
    path = proj.write_run_request(
        run_dir, "search", {"min_size": 2, "models": ["a", "b"]},
        models=["a", "b"], media=["preset:western_diet"], cmig_version="0.3.0",
    )
    assert path == tmp_path / "runs" / "_inputs" / "search-20261014-101010-request.json"
    payload, problem = proj.read_run_request(run_dir)
    assert problem == ""
    assert payload is not None
    assert payload["analysis"] == "search" and payload["values"]["min_size"] == 2
    assert payload["schema_version"] == proj.REQUEST_SCHEMA_VERSION
    assert payload["models"] == ["a", "b"] and payload["cmig_version"] == "0.3.0"


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("{not json", "could not be read"),
        (json.dumps({"schema_version": 9, "analysis": "search", "values": {}}), "schema 9"),
        (json.dumps({"schema_version": 1, "analysis": 3, "values": {}}), "malformed"),
        (json.dumps([1, 2]), "malformed"),
    ],
)
def test_bad_run_request_is_a_problem_not_an_exception(
    tmp_path: Path, text: str, needle: str
) -> None:
    run_dir = tmp_path / "runs" / "search-1"
    run_dir.mkdir(parents=True)
    proj.run_request_path(run_dir).parent.mkdir(parents=True)
    proj.run_request_path(run_dir).write_text(text)
    payload, problem = proj.read_run_request(run_dir)
    assert payload is None and needle in problem


def test_missing_run_request_is_no_record(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "dfba-1"
    run_dir.mkdir(parents=True)
    assert proj.read_run_request(run_dir) == (None, "")


def test_unserialisable_request_is_refused(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "x-1"
    run_dir.mkdir(parents=True)
    with pytest.raises(proj.ProjectError):
        proj.write_run_request(run_dir, "x", {"bad": object()}, models=[], media=[],
                               cmig_version="0")


def test_migrate_analysis_settings() -> None:
    old = {
        "search": {"models": ["a"], "medium": "preset:western_diet"},
        "dynamics": {"models": ["b"]},
        "host": {"models": ["a"], "host_medium": "preset:high_fiber"},
        "host_model": {"models": ["h"]},
        "growth": {"models": ["c"]},
        "community": {"models": ["a", "b"]},
    }
    new = proj.migrate_analysis_settings(old)
    assert new["gene_ko"] == new["search"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["strain_growth"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["ratio_impact"] == {"models": ["a"], "medium": "preset:western_diet"}
    assert new["dfba"] == {"models": ["b"]}
    assert new["host_search"] == {"models": ["a"], "host_medium": "preset:high_fiber"}
    assert new["host_search_model"] == {"models": ["h"]}
    assert new["community"] == {"models": ["a", "b"]}
    assert "dynamics" not in new and "growth" not in new
    new["gene_ko"]["models"].append("z")
    assert new["search"]["models"] == ["a"], "copies, not shared lists"


def test_phase1_project_opens_with_migrated_settings(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    project.analysis_settings = {"search": {"models": ["a"]}, "dynamics": {"models": ["b"]}}
    proj.save_project(project)
    again = proj.open_project(project.root)
    assert again.analysis_settings["gene_ko"] == {"models": ["a"]}
    assert again.analysis_settings["dfba"] == {"models": ["b"]}
    assert "dynamics" not in again.analysis_settings


def test_rename_onto_removed_remembered_id_drops_the_stale_id(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    project.analysis_settings["search"] = {"models": ["a", "b"]}
    proj.remove_model(project, "a")  # "a" stays remembered, as phase 1 keeps it
    proj.rename_model(project, "b", "a")
    assert project.analysis_settings["search"]["models"] == ["a"]  # the renamed b, once
