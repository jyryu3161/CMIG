"""Phase 2 — GUI Views(Sweep View·External Profile Viewer) offscreen 검증. Plan SC: SC-GV1~GV6.

QT offscreen(conftest)에서 위젯 생성·실 backend 소비. offscreen=실행 증거지 G-7b 시각 QA 아님.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.core.sweep import SweepAxis  # noqa: E402
from cmig.gui.views import DfbaSpatialView, ExternalProfileView, SweepView  # noqa: E402
from cmig.service import JobRunner, JobStatus  # noqa: E402


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_sweep_view_runs_real_sweep():
    """SC-GV1: SweepView 가 JobRunner+make_sweep_job 으로 실 sweep 실행 → 결과 표시."""
    _app()
    runner = JobRunner(max_workers=1)
    view = SweepView(runner=runner)
    axes = [SweepAxis("tradeoff_f", [0.3, 0.5, 0.7])]
    jid = view.run_sweep(
        axes, run_hash_fn=lambda c: c.condition_id,
        solve_fn=lambda c: float(c.axis_values["tradeoff_f"]), metric="growth")
    rows = runner.result(jid, timeout=5)
    assert runner.poll(jid).status is JobStatus.DONE
    view.load_results(rows)
    assert view.table.rowCount() == 3
    assert view.table.item(0, 2).text() == "ok"        # status
    runner.shutdown()


def test_sweep_view_cache_hit_display():
    """SC-GV2: cache_hit 표시(재계산 회피 가시화)."""
    from cmig.core.sweep import SweepRow
    _app()
    view = SweepView()
    rows = [
        SweepRow("cond-0", {}, "growth", 0.5, "rh0", "ok", None, cache_hit=False),
        SweepRow("cond-1", {}, "growth", 0.5, "rh0", "ok", None, cache_hit=True),
    ]
    view.load_results(rows)
    assert view.table.item(0, 3).text() == "miss"
    assert view.table.item(1, 3).text() == "hit"


def test_sweep_view_failed_row():
    """SC-GV3: 실패 row 표시(silent 위장 금지)."""
    from cmig.core.sweep import SweepRow
    _app()
    view = SweepView()
    row = SweepRow("c0", {}, "g", None, "rh", "failed", '{"code":"infeasible"}', False)
    view.load_results([row])
    assert view.table.item(0, 1).text() == "—"          # value None
    assert view.table.item(0, 2).text() == "failed"


def test_profile_view_sign_and_fva():
    """SC-GV4: External Profile — net flux·sign·FVA 표시."""
    _app()
    view = ExternalProfileView()
    rows = [
        {"metabolite": "ac", "net_flux": 5.0, "label": "secretion", "fva_lo": 4.0, "fva_hi": 6.0},
        {"metabolite": "glc", "net_flux": -10.0, "label": "uptake", "fva_lo": None, "fva_hi": None},
    ]
    view.load_profile(rows)
    assert view.table.rowCount() == 2
    assert view.table.item(0, 2).text() == "secretion"
    assert view.table.item(0, 3).text() == "[4, 6]"     # FVA 범위
    assert view.table.item(1, 3).text() == "—"          # FVA 없음


def test_profile_view_targets():
    """SC-GV5: target readout 요약."""
    _app()
    view = ExternalProfileView()
    view.load_targets([{"metabolite": "ac", "ui_flux": 5.0}, {"metabolite": "but", "ui_flux": 3.0}])
    assert "ac=5" in view.target_label.text() and "but=3" in view.target_label.text()
    view.load_targets(None)
    assert view.target_label.text() == ""


def test_profile_view_empty():
    """SC-GV6: 빈 profile 안전."""
    _app()
    view = ExternalProfileView()
    view.load_profile([])
    assert view.table.rowCount() == 0


def test_dynamics_view_requests_and_summaries():
    """Dynamics view exposes runnable dFBA/spatial requests and result summaries."""
    _app()
    view = DfbaSpatialView()
    view.model_path_input.setText("/tmp/model.xml")
    assert view.dfba_request()["model"] == "/tmp/model.xml"
    assert view.spatial_request()["width"] == view.spatial_request()["height"]
    view.spatial_dt_spin.setValue(0.25)
    assert view.spatial_request()["dt"] == 0.25
    view.load_dfba_summary(
        {
            "status": "completed",
            "final_t": 0.5,
            "final_biomass": 0.011,
            "final_concentrations": {"EX_glc__D_e": 9.9},
        },
        run_dir=Path("/tmp"),
    )
    assert view.table.item(0, 0).text() == "dFBA"
    view.load_spatial_summary(
        {"status": "completed", "final_t": 8.0, "final_min": 0.0, "final_max": 10.0},
        run_dir=Path("/tmp"),
    )
    assert view.table.item(0, 0).text() == "Spatial"


def test_dynamics_view_loads_svg_without_tiff(tmp_path):
    pytest.importorskip("PySide6.QtSvg")

    _app()
    view = DfbaSpatialView()
    (tmp_path / "figure.svg").write_text(
        "<svg xmlns='http://www.w3.org/2000/svg' width='120' height='80'>"
        "<rect width='120' height='80' fill='white'/>"
        "<circle cx='60' cy='40' r='20' fill='#2b8cbe'/>"
        "</svg>"
    )
    view._load_figure(tmp_path, "figure.svg")
    pixmap = view.figure_label.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
