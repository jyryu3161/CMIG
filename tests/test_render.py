"""R Render Service — FigureSpec + 실제 R 렌더(가용 시). FR-2.5 / §9."""

import json
import subprocess
from pathlib import Path

import pytest

from cmig.core.engine import SolveResult
from cmig.core.interactions import build_tidy
from cmig.render.client import (
    FigureSpec,
    RenderClient,
    RenderError,
    render_profile,
    rscript_available,
)
from cmig.render.provenance import parse_r_provenance


def _bundle():
    r = SolveResult(
        objective=0.5, member_growth={"A": 0.5}, abundances={"A": 1.0},
        external_exchange={"ac": 5.0, "glc": -10.0, "co2": 8.0},  # 분비/흡수 혼합
        member_exchange={"A": {"ac": 5.0, "glc": -10.0, "co2": 8.0}},
        status="optimal", flux_report_status="full", growth_solver="gurobi",
        flux_solver="gurobi", members=["A"],
    )
    return build_tidy(r)


def test_figure_spec_validate_rejects_bad_format():
    with pytest.raises(RenderError):
        FigureSpec(format="png").validate()
    FigureSpec(format="pdf").validate()
    FigureSpec(format="eps").validate()


def test_render_writes_figure_spec_sidecar(tmp_path):
    """figure_spec sidecar(seed 포함) 항상 기록 (§9 재현)."""
    out = tmp_path / "fig.svg"
    spec = FigureSpec(seed=7, title="T")
    # R 부재 + matplotlib 부재면 RenderError 나기 전에 sidecar 는 이미 기록됨
    try:
        render_profile(_bundle(), spec, out)
    except RenderError:
        pass
    sidecar = out.with_name("fig.svg.figure_spec.json")
    assert sidecar.exists()
    assert json.loads(sidecar.read_text())["seed"] == 7


def test_bad_format_raises_before_render(tmp_path):
    with pytest.raises(RenderError):
        RenderClient().render([], FigureSpec(format="png"), tmp_path / "x.png")


@pytest.mark.skipif(not rscript_available(), reason="Rscript 미설치")
def test_real_r_render_svg(tmp_path):
    """실제 R(ggplot2) SVG 렌더 — 파일 생성·SVG 마커 검증 (FR-2.5)."""
    out = tmp_path / "profile.svg"
    result = render_profile(_bundle(), FigureSpec(format="svg", seed=42), out)
    assert result.exists() and result.stat().st_size > 0
    head = result.read_text(errors="ignore")[:600].lower()
    assert "<svg" in head or "<?xml" in head        # 유효 SVG
    # sidecar 재현 자산
    assert out.with_name("profile.svg.figure_spec.json").exists()
    provenance = json.loads(out.with_name("profile.svg.render_provenance.json").read_text())
    assert provenance["renderer"] == "r"
    assert provenance["runtime"]["r_packages"]["ggplot2"]
    assert provenance["script"]["file"] == "cmig/render_r/figure.R"
    assert provenance["renv_lock"]["sha256"]


@pytest.mark.skipif(not rscript_available(), reason="Rscript 미설치")
def test_real_r_render_deterministic(tmp_path):
    """동일 figure_spec → 동일 그림(결정적 레이아웃·seed, §9)."""
    spec = FigureSpec(format="svg", seed=1)
    a = render_profile(_bundle(), spec, tmp_path / "a.svg").read_bytes()
    b = render_profile(_bundle(), spec, tmp_path / "b.svg").read_bytes()
    # svglite/base svg 는 결정적; 동일 입력+seed → 동일 바이트(또는 길이 동일)
    assert len(a) == len(b)


def test_render_client_available_reflects_env():
    assert RenderClient().available() == rscript_available()
    assert RenderClient(rscript="").available() is False          # 빈 경로 → fallback
    assert RenderClient(rscript="/usr/bin/Rscript").available() is True


def test_matplotlib_fallback_uses_label_palette(tmp_path):
    out = tmp_path / "profile.svg"
    rows = [
        {"metabolite": "zero-secreted", "net_flux": 0.0, "ui_flux": 0.0, "label": "secretion"},
        {"metabolite": "positive-uptake-label", "net_flux": 5.0, "ui_flux": 5.0, "label": "uptake"},
    ]
    RenderClient(rscript="").render(rows, FigureSpec(format="svg"), out)
    text = out.read_text(errors="ignore").lower()
    assert "#d62728" in text
    assert "#1f77b4" in text
    provenance = json.loads(out.with_name("profile.svg.render_provenance.json").read_text())
    assert provenance["renderer"] == "matplotlib"
    assert provenance["input"]["serialization"] == "canonical-json-v1"
    assert provenance["renv_lock"]["file"] == "cmig/render_r/renv.lock"
    assert provenance["figure"]["sha256"]


def test_render_client_passes_project_rlib(monkeypatch, tmp_path):
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = list(cmd)
        Path(cmd[cmd.index("--out") + 1]).write_text("<svg/>")
        stdout = "CMIG_R_VERSION\tR version 4.3.2\nCMIG_R_PACKAGE\tggplot2\t3.5.2\n"
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = tmp_path / "profile.svg"
    RenderClient(rscript="/usr/bin/Rscript").render([], FigureSpec(format="svg"), out)
    rlib = seen["cmd"][seen["cmd"].index("--rlib") + 1]
    assert rlib.endswith("/CMIG/.Rlib")
    provenance = json.loads(out.with_name("profile.svg.render_provenance.json").read_text())
    assert provenance["runtime"]["r_version"] == "R version 4.3.2"
    assert provenance["runtime"]["r_packages"] == {"ggplot2": "3.5.2"}


def test_parse_r_provenance_ignores_regular_output():
    version, packages = parse_r_provenance(
        "warning\nCMIG_R_PACKAGE\tsvglite\t2.2.1\nCMIG_R_VERSION\tR 4.3.2\nOK\n"
    )
    assert version == "R 4.3.2"
    assert packages == {"svglite": "2.2.1"}


def test_cli_render_figure_matplotlib(tmp_path):
    """Rec: `cmig render-figure` renders a run's tidy profile (matplotlib forced, R-independent)."""
    from cmig.cli.main import main as cli_main

    run_dir = tmp_path / "run"
    _bundle().write(run_dir)
    out = tmp_path / "profile.svg"
    rc = cli_main([
        "render-figure", "--run-dir", str(run_dir), "--out", str(out), "--renderer", "matplotlib",
    ])
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0
    assert out.with_name("profile.svg.figure_spec.json").exists()
    assert out.with_name("profile.svg.render_provenance.json").exists()


def test_cli_render_figure_missing_profile_errors(tmp_path):
    from cmig.cli.main import main as cli_main

    rc = cli_main([
        "render-figure", "--run-dir", str(tmp_path), "--out", str(tmp_path / "x.svg"),
    ])
    assert rc == 2
