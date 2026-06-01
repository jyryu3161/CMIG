"""F3 — cmig solve --targets scfa → target_summary.json. Plan SC: SC-C2."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("micom")

from cmig.cli.main import main  # noqa: E402
from cmig.golden_fixture import build_taxonomy  # noqa: E402


def test_solve_fixture_targets_writes_summary(tmp_path):
    """SC-C2: --targets scfa → target_summary.json 산출 + manifest artifacts 반영."""
    rc = main(["solve-fixture", "--solver", "gurobi", "--targets", "scfa", "--out", str(tmp_path)])
    assert rc == 0
    ts = tmp_path / "target_summary.json"
    assert ts.exists()
    summary = json.loads(ts.read_text())
    mets = {r["metabolite"] for r in summary}
    assert "ac" in mets                                    # 실 profile 의 acetate(SCFA)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert "target_summary.json" in manifest["artifacts"]  # AF-1 일관 파생


def test_no_targets_omits_summary(tmp_path):
    main(["solve-fixture", "--solver", "gurobi", "--out", str(tmp_path)])
    assert not (tmp_path / "target_summary.json").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert "target_summary.json" not in manifest["artifacts"]


def test_unknown_target_preset_fails(tmp_path, capsys):
    rc = main(["solve-fixture", "--solver", "gurobi", "--targets", "nope", "--out", str(tmp_path)])
    assert rc == 2
    assert "preset" in capsys.readouterr().err.lower()


def test_solve_taxonomy_targets(tmp_path):
    tax = tmp_path / "tax.csv"
    build_taxonomy().to_csv(tax, index=False)
    out = tmp_path / "out"
    rc = main(["solve", "--taxonomy", str(tax), "--targets", "scfa", "--out", str(out)])
    assert rc == 0
    assert (out / "target_summary.json").exists()
