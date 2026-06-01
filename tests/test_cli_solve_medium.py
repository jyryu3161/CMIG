"""C6/C7 (P1) — cmig solve --taxonomy --medium. Plan SC: SC-F3·F4.

medium_checksum 이 run_hash 에 반영되어, 같은 taxonomy 라도 medium 이 다르면 run_hash 가 다름.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("micom")

from cmig.cli.main import main  # noqa: E402
from cmig.core.tidy import TidyBundle  # noqa: E402
from cmig.golden_fixture import build_taxonomy  # noqa: E402


def _taxonomy_csv(tmp_path):
    p = tmp_path / "taxonomy.csv"
    build_taxonomy().to_csv(p, index=False)
    return p


def test_solve_with_taxonomy_writes_artifacts(tmp_path):
    tax = _taxonomy_csv(tmp_path)
    out = tmp_path / "out"
    rc = main(["solve", "--taxonomy", str(tax), "--solver", "gurobi", "--out", str(out)])
    assert rc == 0
    for f in ("nodes.parquet", "edges.parquet", "profile.parquet", "manifest.json"):
        assert (out / f).exists()
    assert TidyBundle.read(out).nodes.num_rows == 4


def test_medium_changes_run_hash(tmp_path):
    """SC-F4: 동일 taxonomy + 다른 medium → run_hash 상이(medium_checksum 반영)."""
    tax = _taxonomy_csv(tmp_path)

    def run(out_name, *medium):
        out = tmp_path / out_name
        main(["solve", "--taxonomy", str(tax), "--solver", "gurobi",
              *medium, "--out", str(out)])
        return json.loads((out / "manifest.json").read_text())

    default = run("d")
    western = run("w", "--medium", "medium_presets/western_diet.csv")
    fiber = run("f", "--medium", "medium_presets/high_fiber.csv")

    # medium_checksum 이 components 에 반영 → run_hash 상이
    assert western["run_hash"] != default["run_hash"], "custom medium 이 run_hash 미반영"
    assert western["run_hash"] != fiber["run_hash"], "다른 diet 가 동일 run_hash(충돌)"
    assert western["components"]["medium_checksum"].startswith("medium:")
    assert default["components"]["medium_checksum"] == "micom_default_medium"


def test_solve_rejects_bad_tradeoff(tmp_path, capsys):
    tax = _taxonomy_csv(tmp_path)
    rc = main(["solve", "--taxonomy", str(tax), "--tradeoff-f", "1.5",
               "--out", str(tmp_path / "o")])
    assert rc == 2
    assert "tradeoff" in capsys.readouterr().err.lower()


def test_solve_missing_taxonomy(tmp_path, capsys):
    rc = main(["solve", "--taxonomy", str(tmp_path / "nope.csv"), "--out", str(tmp_path / "o")])
    assert rc == 2
    assert "taxonomy" in capsys.readouterr().err.lower()


def test_solve_blocks_unresolved_high_namespace_decision(tmp_path, capsys):
    tax = _taxonomy_csv(tmp_path)
    decisions = tmp_path / "namespace.json"
    decisions.write_text(json.dumps([{
        "metabolite": "ac",
        "source_id": "source:ac",
        "target_id": None,
        "confidence": "high",
        "status": "unresolved",
    }]))
    rc = main([
        "solve", "--taxonomy", str(tax), "--namespace-decisions", str(decisions),
        "--out", str(tmp_path / "o"),
    ])
    assert rc == 2
    assert "namespace gate blocked" in capsys.readouterr().err


def test_solve_records_namespace_decisions_in_run_hash_components(tmp_path):
    tax = _taxonomy_csv(tmp_path)
    decisions = tmp_path / "namespace.json"
    decisions.write_text(json.dumps([{
        "metabolite": "ac",
        "source_id": "source:ac",
        "target_id": "bigg:ac",
        "confidence": "high",
        "status": "resolved",
        "rationale": "manual",
    }]))
    out = tmp_path / "out"
    rc = main([
        "solve", "--taxonomy", str(tax), "--namespace-decisions", str(decisions),
        "--solver", "gurobi", "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    keys = manifest["components"]["namespace_mapping_decisions"]
    assert len(keys) == 1 and "bigg:ac" in keys[0]


def test_unknown_medium_exchange_is_strict_by_default(tmp_path, capsys):
    tax = _taxonomy_csv(tmp_path)
    medium = tmp_path / "unknown.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_not_real_m,1.0\n")
    rc = main([
        "solve", "--taxonomy", str(tax), "--medium", str(medium),
        "--out", str(tmp_path / "o"),
    ])
    assert rc == 2
    assert "community" in capsys.readouterr().err


def test_allow_unknown_medium_records_diagnostic(tmp_path):
    tax = _taxonomy_csv(tmp_path)
    medium = tmp_path / "unknown.csv"
    medium.write_text("exchange_id,uptake_limit\nEX_not_real_m,1.0\n")
    out = tmp_path / "out"
    rc = main([
        "solve", "--taxonomy", str(tax), "--medium", str(medium),
        "--allow-unknown-medium", "--solver", "gurobi", "--out", str(out),
    ])
    assert rc == 0
    manifest = json.loads((out / "manifest.json").read_text())
    diagnostic = json.loads(manifest["diagnostic"])
    assert diagnostic["code"] == "medium_unapplied"
    assert diagnostic["detail"]["exchange_ids"] == ["EX_not_real_m"]
