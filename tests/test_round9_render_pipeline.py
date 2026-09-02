"""Round 9 V3 — staged R publication and completed-run Figure Composer service."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from cmig.core.engine import SolveResult
from cmig.core.interactions import build_tidy
from cmig.render import render_panels_from_run
from cmig.render.client import FigureSpec, RenderClient, RenderError
from cmig.render.composer import (
    EDGE_WEIGHT_BASIS_CAPTION,
    FigureComposer,
    PanelSpec,
    panel_title_with_basis,
)
from cmig.render.publication import render_artifacts

_PROFILE_ROWS = [
    {"metabolite": "ac", "net_flux": 2.0, "ui_flux": 2.0, "label": "secretion"},
    {"metabolite": "glc", "net_flux": -3.0, "ui_flux": 3.0, "label": "uptake"},
]
_PANEL_ROWS = [
    {"source_id": "A", "target_id": "pool", "weight": 2.0, "edge_type": "secretion"},
]


def _write_previous_set(figure: Path) -> dict[Path, bytes]:
    artifacts = render_artifacts(figure)
    previous = {
        artifacts.figure: b"previous figure",
        artifacts.figure_spec: b'{"previous": "spec"}\n',
        artifacts.provenance: b'{"previous": "provenance"}\n',
    }
    for path, data in previous.items():
        path.write_bytes(data)
    return previous


def _assert_previous_set(previous: dict[Path, bytes]) -> None:
    for path, data in previous.items():
        assert path.read_bytes() == data
    assert {path.name for path in next(iter(previous)).parent.iterdir()} == {
        path.name for path in previous
    }


_REAL_SUBPROCESS_RUN = subprocess.run


def _successful_fake_r(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    if "--out" not in cmd:
        # `cmig.render.client.subprocess` is the stdlib module, so this fake also sees the
        # `uname -p` that `platform.processor()` runs from write_render_provenance on a cold
        # platform cache; only the Rscript invocation is faked.
        return _REAL_SUBPROCESS_RUN(cmd, **kwargs)
    output = Path(cmd[cmd.index("--out") + 1])
    output.write_bytes(b"<svg>complete staged figure</svg>\n")
    stdout = "CMIG_R_VERSION\tR 4.3.2\nCMIG_R_PACKAGE\tggplot2\t3.5.2\n"
    return subprocess.CompletedProcess(cmd, 0, stdout, "")


def test_r_writer_failure_preserves_previous_artifact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "profile.svg"
    previous = _write_previous_set(output)

    def fail_after_partial_write(
        cmd: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        if "--out" not in cmd:
            return _REAL_SUBPROCESS_RUN(cmd, **kwargs)
        staged = Path(cmd[cmd.index("--out") + 1])
        staged.write_bytes(b"partial R output")
        return subprocess.CompletedProcess(cmd, 1, "", "injected R writer failure")

    monkeypatch.setattr("cmig.render.client.subprocess.run", fail_after_partial_write)
    with pytest.raises(RenderError, match="injected R writer failure"):
        RenderClient(rscript="Rscript").render(_PROFILE_ROWS, FigureSpec(), output)

    _assert_previous_set(previous)


def test_matplotlib_writer_failure_preserves_previous_artifact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "profile.svg"
    previous = _write_previous_set(output)

    def fail_after_partial_write(_figure: object, destination: Path, **_kwargs: Any) -> None:
        Path(destination).write_bytes(b"partial matplotlib output")
        raise OSError("injected matplotlib writer failure")

    monkeypatch.setattr("matplotlib.figure.Figure.savefig", fail_after_partial_write)
    with pytest.raises(OSError, match="injected matplotlib writer failure"):
        RenderClient(rscript="").render(_PROFILE_ROWS, FigureSpec(), output)

    _assert_previous_set(previous)


def test_publish_copy_failure_preserves_previous_artifact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "profile.svg"
    previous = _write_previous_set(output)
    real_copyfile = shutil.copyfile

    def fail_after_partial_copy(source: Path, destination: Path, **kwargs: Any) -> str:
        Path(destination).write_bytes(b"partial publication copy")
        raise OSError("injected publication writer failure")

    monkeypatch.setattr("cmig.render.client.subprocess.run", _successful_fake_r)
    monkeypatch.setattr("cmig.render.publication.shutil.copyfile", fail_after_partial_copy)
    with pytest.raises(OSError, match="injected publication writer failure"):
        RenderClient(rscript="Rscript").render(_PROFILE_ROWS, FigureSpec(), output)

    _assert_previous_set(previous)
    monkeypatch.setattr("cmig.render.publication.shutil.copyfile", real_copyfile)


def test_publish_replace_failure_preserves_previous_artifact_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "profile.svg"
    previous = _write_previous_set(output)
    real_replace = os.replace

    def fail_final_figure_replace(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == output:
            raise OSError("injected publication replace failure")
        real_replace(source, destination)

    monkeypatch.setattr("cmig.render.client.subprocess.run", _successful_fake_r)
    monkeypatch.setattr("cmig.io.atomic.os.replace", fail_final_figure_replace)
    with pytest.raises(OSError, match="injected publication replace failure"):
        RenderClient(rscript="Rscript").render(_PROFILE_ROWS, FigureSpec(), output)

    _assert_previous_set(previous)


def test_staged_profile_publishes_exact_figure_and_logical_sidecar_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "profile.svg"
    monkeypatch.setattr("cmig.render.client.subprocess.run", _successful_fake_r)

    RenderClient(rscript="Rscript").render(
        _PROFILE_ROWS,
        FigureSpec(title="Atomic regression", seed=9),
        output,
    )

    artifacts = render_artifacts(output)
    assert artifacts.figure.read_bytes() == b"<svg>complete staged figure</svg>\n"
    spec = json.loads(artifacts.figure_spec.read_text())
    provenance = json.loads(artifacts.provenance.read_text())
    assert spec["title"] == "Atomic regression" and spec["seed"] == 9
    assert provenance["figure"]["file"] == "profile.svg"
    assert provenance["figure_spec"]["file"] == "profile.svg.figure_spec.json"
    assert {path.name for path in tmp_path.iterdir()} == {
        "profile.svg",
        "profile.svg.figure_spec.json",
        "profile.svg.render_provenance.json",
    }


class _RecordingComposer(FigureComposer):
    def __init__(self) -> None:
        self.panels: list[tuple[PanelSpec, list[dict[str, Any]]]] = []

    def render_panels(
        self,
        panels: list[tuple[PanelSpec, list[dict[str, Any]]]],
        out_dir: str | Path,
    ) -> list[Path]:
        self.panels = panels
        directory = Path(out_dir)
        return [
            directory / f"panel_{index:02d}_{spec.kind}.{spec.format}"
            for index, (spec, _rows) in enumerate(panels)
        ]


def _completed_run(run_dir: Path) -> None:
    result = SolveResult(
        objective=0.5,
        member_growth={"A": 0.5, "B": 0.5},
        abundances={"A": 0.6, "B": 0.4},
        external_exchange={"ac": 2.0, "glc": -6.0, "but": 1.6},
        member_exchange={
            "A": {"ac": 5.0, "glc": -10.0},
            "B": {"ac": -3.0, "but": 4.0},
        },
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A", "B"],
    )
    build_tidy(result).write(run_dir)


def test_completed_run_entry_point_projects_all_panels_and_applies_journal(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    _completed_run(run_dir)
    recorder = _RecordingComposer()

    outputs = render_panels_from_run(
        run_dir,
        ["network", "heatmap", PanelSpec(kind="chord", title="Transfers")],
        tmp_path / "panels",
        journal_preset="nature",
        composer=recorder,
    )

    assert [path.name for path in outputs] == [
        "panel_00_network.svg",
        "panel_01_heatmap.svg",
        "panel_02_chord.svg",
    ]
    specs = [spec for spec, _rows in recorder.panels]
    assert [(spec.width_in, spec.height_in, spec.dpi) for spec in specs] == [
        (3.5, 3.0, 300),
        (3.5, 3.0, 300),
        (3.5, 3.0, 300),
    ]
    assert all(spec.journal_preset == "nature" for spec in specs)
    assert EDGE_WEIGHT_BASIS_CAPTION in panel_title_with_basis(specs[0])
    assert EDGE_WEIGHT_BASIS_CAPTION in panel_title_with_basis(specs[2])
    assert panel_title_with_basis(specs[1]) == "Heatmap"

    by_kind = {spec.kind: rows for spec, rows in recorder.panels}
    assert len(by_kind["network"]) == 5  # four direct edges + one allocated cross-feeding edge
    assert by_kind["chord"] == by_kind["network"]
    heatmap = {
        (row["row_key"], row["col_key"]): row["value"]
        for row in by_kind["heatmap"]
    }
    assert heatmap == {
        ("A", "ac"): pytest.approx(3.0),
        ("A", "glc"): pytest.approx(-6.0),
        ("B", "ac"): pytest.approx(-1.2),
        ("B", "but"): pytest.approx(1.6),
    }


def test_composer_publishes_figure_and_sidecars_through_atomic_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cmig.render.publication as publication

    output = tmp_path / "network.svg"
    calls: list[Path] = []
    real_atomic_write_path = publication.atomic_write_path

    def recording_atomic_write_path(path: str | Path, writer: Any) -> Path:
        calls.append(Path(path))
        return real_atomic_write_path(path, writer)

    monkeypatch.setattr("cmig.render.client.subprocess.run", _successful_fake_r)
    monkeypatch.setattr(publication, "atomic_write_path", recording_atomic_write_path)

    FigureComposer(rscript="Rscript").render_panel(
        _PANEL_ROWS,
        PanelSpec(kind="network"),
        output,
    )

    artifacts = render_artifacts(output)
    assert calls == [artifacts.figure, artifacts.figure_spec, artifacts.provenance]
    assert all(path.is_file() for path in calls)
    assert {path.name for path in tmp_path.iterdir()} == {path.name for path in calls}


def test_completed_run_entry_point_rejects_empty_panel_list(tmp_path: Path) -> None:
    with pytest.raises(RenderError, match="panel list"):
        render_panels_from_run(tmp_path, [], tmp_path / "panels")
