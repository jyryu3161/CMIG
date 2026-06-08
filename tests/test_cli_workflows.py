from __future__ import annotations

import json

from cmig.cli.main import main


def test_workflows_cli_exposes_gui_cli_map(capsys):
    rc = main(["workflows"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1.0"
    surfaces = {item["gui_surface"]: item for item in payload["workflows"]}
    assert surfaces["Search / Find Best Model Combination"]["cli_command"] == "cmig search"
    assert surfaces["Toolbar / Run Fixture"]["cli_command"] == "cmig solve-fixture"
    assert surfaces["Community / MICOM Taxonomy Solve"]["cli_command"] == "cmig solve"
    assert surfaces["Search / Rank Gene KOs"]["cli_command"] == "cmig gene-ko-search"
    assert surfaces["Host / Run Host-Microbe"]["cli_command"] == "cmig host-microbe-bigg"
    assert surfaces["Dynamics / Run dFBA"]["cli_command"] == "cmig dfba"
    assert surfaces["Profile / Open Run"]["cli_command"] == "cmig inspect-run"
    assert "search_summary.json" in surfaces["Search / Find Best Model Combination"]["key_outputs"]


def test_workflows_text_format_is_human_readable(capsys):
    rc = main(["workflows", "--format", "text"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "CMIG GUI-to-CLI workflow map" in out
    assert "cmig host-search-bigg" in out


def test_inspect_run_detects_search_summary(tmp_path, capsys):
    (tmp_path / "search_summary.json").write_text(json.dumps({
        "status": "ok",
        "target": "but",
        "artifacts": ["search_plot.svg"],
    }))
    (tmp_path / "search_plot.svg").write_text("<svg/>")
    rc = main(["inspect-run", "--run-dir", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "model_pool_search"
    assert payload["status"] == "ok"
    assert payload["summary_file"] == "search_summary.json"
    assert "search_plot.svg" in payload["artifacts"]
    assert "target" in payload["summary_keys"]


def test_inspect_run_reports_manifest_metadata(tmp_path, capsys):
    (tmp_path / "manifest.json").write_text(json.dumps({
        "manifest_schema_version": "1.0",
        "status": "completed",
        "run_hash": "abc123",
        "artifacts": ["profile.parquet"],
        "solver": {"growth_solver": "gurobi"},
    }))
    (tmp_path / "profile.parquet").write_bytes(b"PAR1")
    rc = main(["inspect-run", "--run-dir", str(tmp_path), "--format", "json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "community_solve"
    assert payload["status"] == "completed"
    assert payload["run_hash"] == "abc123"
    assert payload["manifest"]["solver"]["growth_solver"] == "gurobi"
