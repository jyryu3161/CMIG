"""Round-9 V3 handoff: `cmig render-figure --panel` contract (rejection paths).

The happy path (real R renders of network/heatmap/chord with sidecars) is
exercised by the render-pipeline tests and was verified live at integration;
these tests pin the CLI contract that must hold WITHOUT an R environment:
panel mode is R-only, svg/tiff-only, and never silently substitutes matplotlib.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pyarrow")

from cmig.cli.main import build_parser, main


def _run_dir_with_profile(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(pa.table({"metabolite": ["ac"]}), tmp_path / "profile.parquet")
    return tmp_path


def test_panel_flag_is_repeatable_ordered_and_choice_checked():
    args = build_parser().parse_args([
        "render-figure", "--run-dir", "r", "--out", "o",
        "--panel", "chord", "--panel", "network",
    ])
    assert args.panels == ["chord", "network"]
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "render-figure", "--run-dir", "r", "--out", "o", "--panel", "volcano",
        ])


def test_panel_mode_rejects_matplotlib_renderer(tmp_path, capsys):
    run_dir = _run_dir_with_profile(tmp_path)
    rc = main([
        "render-figure", "--run-dir", str(run_dir), "--out", str(tmp_path / "figs"),
        "--panel", "network", "--renderer", "matplotlib",
    ])
    assert rc == 2
    assert "R-only" in capsys.readouterr().err


def test_panel_mode_rejects_pdf_eps_formats(tmp_path, capsys):
    run_dir = _run_dir_with_profile(tmp_path)
    rc = main([
        "render-figure", "--run-dir", str(run_dir), "--out", str(tmp_path / "figs"),
        "--panel", "heatmap", "--format", "pdf",
    ])
    assert rc == 2
    assert "svg/tiff only" in capsys.readouterr().err


def test_panel_mode_requires_rscript(tmp_path, capsys, monkeypatch):
    # _cmd_render_figure imports rscript_available from cmig.render.client at call
    # time, so patching the module attribute is authoritative.
    import cmig.render.client as render_client

    monkeypatch.setattr(render_client, "rscript_available", lambda: False)
    run_dir = _run_dir_with_profile(tmp_path)
    rc = main([
        "render-figure", "--run-dir", str(run_dir), "--out", str(tmp_path / "figs"),
        "--panel", "chord",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "R-only" in err
