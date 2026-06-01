"""Phase 0.1 — EngineService facade. Plan SC: SC-S1·SC-S3·SC-S5·NFR1.

facade 가 산재 오케스트레이션을 위임만 하고, 산출 run_hash·parquet 이 CLI 경로와 비트 일치하며,
solve_single 은 정직한 capability_missing stub 임을 검증. service 패키지는 Qt 비의존.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pandas as pd
import pyarrow.parquet as pq
import pytest

pytest.importorskip("micom")

from cmig.cli.main import main  # noqa: E402
from cmig.core.manifest import compute_run_hash  # noqa: E402
from cmig.golden_fixture import _run_hash_components, build_taxonomy, solve  # noqa: E402
from cmig.io.solve_output import file_checksum  # noqa: E402
from cmig.service import EngineService  # noqa: E402


def test_solve_fixture_run_hash_matches_library(tmp_path):
    """SC-S1: facade solve_fixture run_hash == 라이브러리 compute_run_hash([HASH-SINGLE])."""
    outcome = EngineService().solve_fixture(solver="gurobi", out_dir=tmp_path)
    assert outcome.status == "ok"
    result, _ = solve("gurobi")
    assert outcome.run_hash == compute_run_hash(_run_hash_components(result))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["run_hash"] == outcome.run_hash       # 재계산 0 (manifest 에서 read)
    assert len(manifest["components"]) == 11


def test_facade_bit_identical_to_cli(tmp_path):
    """SC-S3: facade 산출 == CLI 경로 산출 (run_hash + parquet 내용 비트 일치, gurobi 결정적)."""
    cli_dir = tmp_path / "cli"
    fac_dir = tmp_path / "fac"
    main(["solve-fixture", "--solver", "gurobi", "--out", str(cli_dir)])
    EngineService().solve_fixture(solver="gurobi", out_dir=fac_dir)

    cli_hash = json.loads((cli_dir / "manifest.json").read_text())["run_hash"]
    fac_hash = json.loads((fac_dir / "manifest.json").read_text())["run_hash"]
    assert cli_hash == fac_hash, "facade run_hash 가 CLI 경로와 불일치"
    for f in ("nodes.parquet", "edges.parquet", "profile.parquet"):
        assert pq.read_table(cli_dir / f).equals(pq.read_table(fac_dir / f)), f"{f} 내용 불일치"


def test_facade_solve_community_matches_cli(tmp_path):
    """SC-S3 (A3): user 경로(solve_community)도 CLI `solve` 와 비트 일치(gurobi 결정적)."""
    tax = tmp_path / "tax.csv"
    build_taxonomy().to_csv(tax, index=False)
    cli_dir = tmp_path / "cli"
    fac_dir = tmp_path / "fac"
    main(["solve", "--taxonomy", str(tax), "--solver", "gurobi", "--out", str(cli_dir)])
    EngineService().solve_community(
        taxonomy=pd.read_csv(tax),
        model_checksum=file_checksum(tax),
        solver="gurobi", tradeoff_f=0.5, out_dir=fac_dir,
    )
    cli_hash = json.loads((cli_dir / "manifest.json").read_text())["run_hash"]
    fac_hash = json.loads((fac_dir / "manifest.json").read_text())["run_hash"]
    assert cli_hash == fac_hash, "solve_community facade run_hash 가 CLI 경로와 불일치"
    for f in ("nodes.parquet", "edges.parquet", "profile.parquet"):
        assert pq.read_table(cli_dir / f).equals(pq.read_table(fac_dir / f)), f"{f} 내용 불일치"


def test_facade_solve_community_applies_bounds(tmp_path):
    """bounds 는 manifest/hash 뿐 아니라 실제 community solve 에도 적용된다."""
    tax = tmp_path / "tax.csv"
    build_taxonomy().to_csv(tax, index=False)
    base = EngineService().solve_community(
        taxonomy=pd.read_csv(tax),
        model_checksum=file_checksum(tax),
        solver="gurobi",
        tradeoff_f=0.5,
        out_dir=tmp_path / "base",
    )
    constrained = EngineService().solve_community(
        taxonomy=pd.read_csv(tax),
        model_checksum=file_checksum(tax),
        solver="gurobi",
        tradeoff_f=0.5,
        bounds={"EX_glc__D_e__Escherichia_coli_1": [-1.0, 1000.0]},
        out_dir=tmp_path / "constrained",
    )
    assert constrained.result is not None and base.result is not None
    assert constrained.result.objective != base.result.objective
    manifest = json.loads((tmp_path / "constrained" / "manifest.json").read_text())
    assert manifest["components"]["bounds"] == {"EX_glc__D_e__Escherichia_coli_1": [-1.0, 1000.0]}


def test_facade_targets_writes_summary(tmp_path):
    """SC-S1: --targets 위임 — target_summary.json 산출(미지 preset → ValueError)."""
    outcome = EngineService().solve_fixture(solver="gurobi", out_dir=tmp_path, targets="scfa")
    assert outcome.status == "ok"
    assert (tmp_path / "target_summary.json").exists()
    with pytest.raises(ValueError, match="preset"):
        EngineService().solve_fixture(solver="gurobi", out_dir=tmp_path / "x", targets="nope")


def test_solve_single_real_fba(tmp_path):
    """SC-AS1 (Phase 1.1): solve_single 가 실제 cobra FBA 위임 — e_coli_core obj≈0.8739."""
    import os

    import cobra
    import micom

    model = cobra.io.read_sbml_model(
        os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    )
    res = EngineService().solve_single(model, method="FBA", solver="gurobi")
    assert res.status == "optimal"
    assert abs(res.objective - 0.8739) < 1e-2
    assert res.method == "FBA" and len(res.fluxes) == 95


def test_service_is_qt_independent():
    """NFR1: cmig.service 단독 import 가 PySide6 를 끌어오지 않음(subprocess 격리)."""
    code = "import sys; import cmig.service; assert 'PySide6' not in sys.modules; print('ok')"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout
