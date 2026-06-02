"""신규 모듈 적대적 리뷰(AF-1~5) 회귀 고정. Plan SC: SC-F8.

cmig-analysis-foundations 신규 모듈 적대 리뷰가 확정한 Minor 5건 수정 회귀.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from cmig.core.medium_spec import load_medium
from cmig.core.targets import SCFA

# ── AF-2: medium JSON 중복 키 fail-fast ──────────────────────────────────────

def test_af2_json_duplicate_key_fails(tmp_path):
    p = tmp_path / "dup.json"
    p.write_text('{"EX_glc__D_m": 5.0, "EX_glc__D_m": 9.0}')   # 중복 키
    with pytest.raises(ValueError, match="중복"):
        load_medium(p)


# ── AF-3: bool→float silent 강제 차단 ────────────────────────────────────────

def test_af3_bool_uptake_rejected(tmp_path):
    p = tmp_path / "bool.json"
    p.write_text('{"EX_glc__D_m": true}')                      # bool → float(True)=1.0 우회 차단
    with pytest.raises(ValueError, match="bool"):
        load_medium(p)


def test_af3_numeric_still_ok(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text('{"EX_glc__D_m": 5}')
    assert load_medium(p).uptake == {"EX_glc__D_m": 5.0}


# ── AF-4: SCFA 가 문서화된 5종(formate 'for' 제외) ───────────────────────────

def test_af4_scfa_excludes_formate():
    assert not SCFA.matches("for"), "formate(for)가 SCFA set 에 남아있음(AF-4 회귀)"
    assert SCFA.metabolites == frozenset({"ac", "ppa", "but", "lac__L", "lac__D", "succ"})


# ── AF-1: manifest artifacts 가 bundle 산출에서 파생(matrix 포함) ────────────

def test_af1_artifacts_include_matrix_when_present(tmp_path):
    pytest.importorskip("micom")
    from cmig.golden_fixture import _run_hash_components, solve
    from cmig.io.solve_output import write_solve_output

    result, bundle = solve("gurobi")
    bundle.matrix = pa.table({"x": [1.0, 2.0]})                 # matrix 산출 경로 모사
    components = _run_hash_components(result)
    mp = write_solve_output(bundle, components, tmp_path)
    manifest = json.loads(mp.read_text())
    assert "matrix.parquet" in manifest["artifacts"]           # 파생 → 누락 안 함
    assert (tmp_path / "matrix.parquet").exists()


def test_af1_artifacts_omit_matrix_when_absent(tmp_path):
    pytest.importorskip("micom")
    from cmig.golden_fixture import _run_hash_components, solve
    from cmig.io.solve_output import write_solve_output

    result, bundle = solve("gurobi")                           # matrix=None
    mp = write_solve_output(bundle, _run_hash_components(result), tmp_path)
    assert "matrix.parquet" not in json.loads(mp.read_text())["artifacts"]


def test_write_solve_output_manifest_is_publish_commit_marker(tmp_path, monkeypatch):
    pytest.importorskip("micom")
    import cmig.io.solve_output as solve_output
    from cmig.golden_fixture import _run_hash_components, solve

    result, bundle = solve("gurobi")
    stale = tmp_path / "manifest.json"
    stale.write_text('{"stale": true}\n')

    real_replace = solve_output.os.replace

    def fail_before_manifest(src, dst):
        if str(dst).endswith("edges.parquet"):
            raise RuntimeError("simulated publish failure")
        return real_replace(src, dst)

    monkeypatch.setattr(solve_output.os, "replace", fail_before_manifest)
    with pytest.raises(RuntimeError, match="simulated publish failure"):
        solve_output.write_solve_output(bundle, _run_hash_components(result), tmp_path)

    assert not stale.exists()


# ── AF-5: cli solve taxonomy 컬럼 검증 ───────────────────────────────────────

def test_af5_solve_rejects_taxonomy_missing_columns(tmp_path, capsys):
    from cmig.cli.main import main

    bad = tmp_path / "bad_tax.csv"
    bad.write_text("name,abundance\nfoo,0.5\n")                # id·file 누락
    rc = main(["solve", "--taxonomy", str(bad), "--out", str(tmp_path / "o")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "id" in err and "file" in err
