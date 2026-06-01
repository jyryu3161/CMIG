"""C7 — cmig solve-fixture 산출 경로. Plan SC: SC-F2.

Design Ref(foundations): §3 — solve-fixture 가 parquet + manifest 를 산출하고,
manifest run_hash 가 라이브러리 경로(compute_run_hash)와 일치([HASH-SINGLE]).
micom 미설치 시 skip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("micom")

from cmig.cli.main import main  # noqa: E402
from cmig.core.manifest import compute_run_hash  # noqa: E402
from cmig.core.tidy import TidyBundle  # noqa: E402
from cmig.golden_fixture import _run_hash_components, solve  # noqa: E402


def test_solve_fixture_writes_artifacts(tmp_path):
    """solve-fixture → nodes/edges/profile.parquet + manifest.json 산출."""
    rc = main(["solve-fixture", "--solver", "gurobi", "--out", str(tmp_path)])
    assert rc == 0
    for f in ("nodes.parquet", "edges.parquet", "profile.parquet", "manifest.json"):
        assert (tmp_path / f).exists(), f"{f} 미산출"
    # parquet 재로드 가능(유효 tidy)
    bundle = TidyBundle.read(tmp_path)
    assert bundle.nodes.num_rows == 4          # 3 member + environment_pool


def test_manifest_run_hash_matches_library(tmp_path):
    """SC-F2 핵심: 산출 manifest run_hash == 라이브러리 compute_run_hash([HASH-SINGLE])."""
    main(["solve-fixture", "--solver", "gurobi", "--out", str(tmp_path)])
    manifest = json.loads((tmp_path / "manifest.json").read_text())

    result, _ = solve("gurobi")
    lib_hash = compute_run_hash(_run_hash_components(result))
    assert manifest["run_hash"] == lib_hash, "manifest run_hash 가 라이브러리 경로와 불일치"
    # manifest 계약: 11 구성요소 + artifacts 목록
    assert len(manifest["components"]) == 11
    assert "nodes.parquet" in manifest["artifacts"]


def test_solve_fixture_osqp_qp_only(tmp_path):
    """F1: osqp solve-fixture 는 qp_only_approximate(LP 부재) — hybrid 폐기 후 무라이선스 경로."""
    main(["solve-fixture", "--solver", "osqp", "--out", str(tmp_path)])
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["components"]["solver_setting"]["flux_solver"] is None


def test_solve_subcommand_requires_taxonomy():
    """solve 는 C6 에서 구현됨(P1) — --taxonomy 필수(argparse 오류)."""
    with pytest.raises(SystemExit):
        main(["solve"])                         # --taxonomy 누락 → argparse SystemExit(2)


def test_solve_fixture_out_is_path(tmp_path):
    assert isinstance(tmp_path, Path)
