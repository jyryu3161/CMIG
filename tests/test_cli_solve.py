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
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["manifest_schema_version"] == "1.0"
    assert manifest["inputs"]["model_checksum"]
    assert manifest["solver"]["flux_report_status"] == "full"
    assert manifest["software"]["cmig_core_version"]


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


def test_solve_fixture_osqp_records_hybrid_flux_solver(tmp_path):
    """F1: osqp solve-fixture 는 optlang hybrid의 HiGHS LP flux solver 를 기록한다."""
    main(["solve-fixture", "--solver", "osqp", "--out", str(tmp_path)])
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["components"]["solver_setting"]["growth_solver"] == "osqp"
    assert manifest["components"]["solver_setting"]["flux_solver"] == "highs"


def test_solve_subcommand_requires_taxonomy():
    """solve 는 C6 에서 구현됨(P1) — --taxonomy 필수(argparse 오류)."""
    with pytest.raises(SystemExit):
        main(["solve"])                         # --taxonomy 누락 → argparse SystemExit(2)


def test_solve_fixture_out_is_path(tmp_path):
    assert isinstance(tmp_path, Path)


def test_sweep_fixture_writes_store(tmp_path):
    rc = main(["sweep-fixture", "--solvers", "gurobi", "--out", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "sweep.parquet").exists()
    assert json.loads((tmp_path / "sweep_summary.json").read_text())["n_runs"] == 2


def test_sweep_user_taxonomy_writes_runs(tmp_path):
    from cmig.golden_fixture import build_taxonomy

    taxonomy = tmp_path / "taxonomy.csv"
    build_taxonomy().to_csv(taxonomy, index=False)
    out = tmp_path / "sweep"
    rc = main([
        "sweep",
        "--taxonomy", str(taxonomy),
        "--tradeoff-fs", "0.5",
        "--solvers", "gurobi",
        "--out", str(out),
    ])
    assert rc == 0
    assert (out / "sweep.parquet").exists()
    assert (out / "runs" / "cond-0000" / "manifest.json").exists()
    assert json.loads((out / "sweep_summary.json").read_text())["n_runs"] == 1


def test_sweep_user_taxonomy_records_member_abundance_and_bounds_axes(tmp_path):
    import pyarrow.parquet as pq

    from cmig.golden_fixture import build_taxonomy

    tax_df = build_taxonomy()
    taxonomy = tmp_path / "taxonomy.csv"
    tax_df.to_csv(taxonomy, index=False)
    member_set = "+".join(str(x) for x in tax_df["id"])
    abundance = tmp_path / "abundance.json"
    abundance.write_text(json.dumps({str(x): 1.0 for x in tax_df["id"]}) + "\n")
    bounds = tmp_path / "bounds.json"
    bounds.write_text(json.dumps({"EX_glc__D_e__Escherichia_coli_1": [-1.0, 1000.0]}) + "\n")
    out = tmp_path / "sweep"
    rc = main([
        "sweep",
        "--taxonomy", str(taxonomy),
        "--tradeoff-fs", "0.5",
        "--solvers", "gurobi",
        "--member-sets", member_set,
        "--abundance-variants", str(abundance),
        "--bounds-variants", str(bounds),
        "--out", str(out),
    ])
    assert rc == 0
    row = pq.read_table(out / "sweep.parquet").to_pylist()[0]
    assert row["axis_member_set"] == member_set
    assert row["axis_abundance"] == str(abundance)
    assert row["axis_bounds"] == str(bounds)


def test_sandbox_fixture_preview_and_commit(tmp_path):
    rxn = "EX_glc__D_e__Escherichia_coli_1"
    rc = main([
        "sandbox-fixture", "--reaction", rxn, "--lower", "-1", "--upper", "1000",
        "--out", str(tmp_path / "preview"),
    ])
    assert rc == 0
    preview = json.loads((tmp_path / "preview" / "sandbox_summary.json").read_text())
    assert preview["state"] == "preview" and preview["run_hash"] is None

    out = tmp_path / "commit"
    rc = main([
        "sandbox-fixture", "--reaction", rxn, "--lower", "-1", "--upper", "1000",
        "--commit", "--out", str(out),
    ])
    assert rc == 0
    committed = json.loads((out / "sandbox_summary.json").read_text())
    assert committed["committed"] is True and committed["run_hash"]
    assert (out / "manifest.json").exists()


def test_model_review_cli_writes_payload(tmp_path):
    import os

    import micom

    model = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    out = tmp_path / "review"
    rc = main(["model-review", "--model", model, "--out", str(out)])
    assert rc == 0
    payload = json.loads((out / "model_review.json").read_text())
    assert payload["model"]["model_id"] == "e_coli_core"
    assert "namespace" in payload and payload["next_actions"]


def test_host_benchmark_cli_writes_measurement(tmp_path):
    import os

    import micom

    model = os.path.join(os.path.dirname(micom.__file__), "data", "e_coli_core.xml.gz")
    out = tmp_path / "host"
    rc = main(["host-benchmark", "--model", model, "--out", str(out)])
    assert rc == 0
    payload = json.loads((out / "host_benchmark.json").read_text())
    assert payload["model"]["n_reactions"] == 95
    assert payload["benchmark"]["solve_seconds"] >= 0.0
    assert payload["quantitative_coupling_ready"] is False


def test_search_advanced_fixture_cli_writes_pareto(tmp_path):
    out = tmp_path / "search"
    rc = main([
        "search-advanced-fixture",
        "--metabolites", "ac,but",
        "--top-k", "3",
        "--out", str(out),
    ])
    assert rc == 0
    payload = json.loads((out / "search_advanced_summary.json").read_text())
    assert payload["strategy"] == "exhaustive"
    assert set(payload["targets"]) == {"ac", "but"}
    assert "pareto_frontier" in payload
