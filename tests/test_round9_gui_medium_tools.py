"""Round-9 V4 acceptance: complete CLI-backed Medium Editor tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

import cmig.gui.app as app_module  # noqa: E402
import cmig.gui.editors as editors_module  # noqa: E402
import cmig.gui.graph_view as graph_view_module  # noqa: E402
from cmig.core.engine import SolveResult  # noqa: E402
from cmig.core.interactions import build_tidy  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.editors import MediumEditor  # noqa: E402
from cmig.service import JobRunner  # noqa: E402

_QT_APP: QApplication | None = None


def _app() -> QApplication:
    global _QT_APP
    _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    yield
    app = QApplication.instance()
    if app is not None:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.processEvents()


def _stub_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep QWidget acceptance independent of sandbox-blocked QtWebEngine."""

    import PySide6.QtWebEngineWidgets as webengine_widgets

    class GraphStub(QWidget):
        def set_bundle(self, _bundle, gate=None):
            return None

        def set_payload(self, _payload):
            return None

        def clear(self):
            return None

    monkeypatch.setattr(app_module, "InteractionGraphView", GraphStub)
    monkeypatch.setattr(graph_view_module, "InteractionGraphView", GraphStub)
    monkeypatch.setattr(webengine_widgets, "QWebEngineView", GraphStub)


def _write_solve_run(
    out_dir: Path,
    *,
    growth: float,
    flux: float,
    dropped: list[str] | None = None,
) -> None:
    result = SolveResult(
        objective=growth,
        member_growth={"A": growth},
        abundances={"A": 1.0},
        external_exchange={"ac": flux},
        member_exchange={"A": {"ac": flux}},
        status="optimal",
        flux_report_status="full",
        growth_solver="gurobi",
        flux_solver="gurobi",
        members=["A"],
    )
    build_tidy(result).write(out_dir)
    diagnostic = None
    if dropped:
        diagnostic = json.dumps(
            {
                "code": "medium_unapplied",
                "message": "some medium exchanges were not applied",
                "detail": {"exchange_ids": dropped},
            }
        )
    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                "run_hash": f"run-{growth}",
                "diagnostic": diagnostic,
                "provenance": {},
            }
        )
    )


def _taxonomy(path: Path) -> Path:
    taxonomy = path / "taxonomy.csv"
    taxonomy.write_text("id,file,abundance\nA,A.xml,1.0\n")
    return taxonomy


def test_preset_picker_roles_filter_and_file_integrity(monkeypatch, tmp_path):
    _app()
    preset = tmp_path / "role_preset.csv"
    preset.write_bytes(
        b"exchange_id,uptake_limit,row_role\n"
        b"EX_glc__D_m,2.5,nutrient\n"
        b"EX_o2_m,0,pool_closure\n"
    )
    before = preset.read_bytes()
    real_loader = editors_module.load_medium
    loaded: list[Path] = []

    def recording_loader(path):
        loaded.append(Path(path))
        return real_loader(path)

    monkeypatch.setattr(editors_module, "load_medium", recording_loader)
    editor = MediumEditor(preset_dir=tmp_path)
    editor.preset_combo.setCurrentIndex(editor.preset_combo.findText(preset.name))
    assert editor.load_selected_preset() is True
    assert loaded == [preset]
    assert editor.table.isColumnHidden(2) is False
    assert editor.pool_closure_warning.isHidden() is False
    assert "exact-medium" in editor.pool_closure_warning.text()
    assert editor.table.item(1, 0).background().color().name() == "#fff1bf"

    editor.nutrients_only_check.setChecked(True)
    assert editor.table.isRowHidden(0) is False
    assert editor.table.isRowHidden(1) is True
    assert editor.to_spec().uptake == {"EX_glc__D_m": 2.5}
    assert "Exact medium" in editor.medium_mode_error()
    editor.exact_medium_check.setChecked(True)
    assert editor.medium_mode_error() == ""
    assert preset.read_bytes() == before


def test_csv_paste_uses_loader_validation_and_names_invalid_rows(monkeypatch, tmp_path):
    _app()
    editor = MediumEditor(preset_dir=tmp_path)
    real_loader = editors_module.load_medium
    calls = 0

    def recording_loader(path):
        nonlocal calls
        calls += 1
        return real_loader(path)

    monkeypatch.setattr(editors_module, "load_medium", recording_loader)
    assert editor.paste_csv(
        "exchange_id,uptake_limit,row_role\n"
        "EX_glc__D_m,4,nutrient\n"
        "EX_o2_m,0,pool_closure\n"
    )
    assert calls == 1
    assert editor.table.rowCount() == 2
    assert editor.table.item(1, 2).text() == "pool_closure"

    assert not editor.paste_csv("EX_bad_m,-1,nutrient\n")
    assert "1 (EX_bad_m)" in editor.status.text()
    assert "≥0" in editor.status.text()
    assert calls == 2

    assert not editor.paste_csv("EX_dup_m,1\nEX_dup_m,2\n")
    assert "row 2" in editor.status.text()
    assert "EX_dup_m" in editor.status.text()


def test_check_growth_runs_solve_with_explicit_medium_mode_and_dropped_ids(
    monkeypatch,
    tmp_path,
):
    import cmig.cli.main

    _app()
    _stub_graph(monkeypatch)
    taxonomy = _taxonomy(tmp_path)
    seen: dict[str, list[str]] = {}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        _write_solve_run(out, growth=0.73, flux=1.5, dropped=["EX_unknown_m"])
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    editor = window.medium_editor
    editor.taxonomy_input.setText(str(taxonomy))
    editor.assume_bigg_check.setChecked(True)
    editor.exact_medium_check.setChecked(True)
    editor.allow_unknown_check.setChecked(True)
    editor.add_row("EX_glc__D_m", 3.0)

    jid = window.run_medium_growth_check()
    runner.result(jid, timeout=5)
    window._poll_completed_jobs()

    argv = seen["argv"]
    assert argv[0] == "solve"
    assert argv[argv.index("--taxonomy") + 1] == str(taxonomy)
    assert "--exact-medium" in argv
    assert "--allow-unknown-medium" in argv
    assert "--assume-bigg-namespace" in argv
    medium_path = Path(argv[argv.index("--medium") + 1])
    assert json.loads(medium_path.read_text()) == {"EX_glc__D_m": 3.0}
    assert "0.73" in editor.growth_label.text()
    assert "optimal" in editor.growth_label.text()
    assert "EX_unknown_m" in editor.dropped_ids_label.text()
    assert editor.check_growth_btn.isEnabled()
    runner.shutdown()


def test_modified_medium_activates_previous_check_profile_delta_then_clears(
    monkeypatch,
    tmp_path,
):
    import cmig.cli.main

    _app()
    _stub_graph(monkeypatch)
    taxonomy = _taxonomy(tmp_path)
    invocation = 0

    def fake_main(argv):
        nonlocal invocation
        invocation += 1
        out = Path(argv[argv.index("--out") + 1])
        _write_solve_run(
            out,
            growth=0.4 + invocation / 10,
            flux=1.0 if invocation == 1 else -2.0,
        )
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    editor = window.medium_editor
    editor.taxonomy_input.setText(str(taxonomy))
    editor.assume_bigg_check.setChecked(True)
    editor.exact_medium_check.setChecked(True)
    editor.add_row("EX_glc__D_m", 1.0)

    first = window.run_medium_growth_check()
    runner.result(first, timeout=5)
    window._poll_completed_jobs()
    assert window.profile_view.net_chart.delta_active is False

    editor.table.item(0, 1).setText("2.0")
    second = window.run_medium_growth_check()
    runner.result(second, timeout=5)
    window._poll_completed_jobs()
    assert window.profile_view.net_chart.delta_active is True
    assert window.profile_view.heatmap.columns == [
        "Previous medium check",
        "Current medium check",
    ]
    assert "previous medium check" in editor.profile_delta_label.text().lower()

    editor.table.item(0, 1).setText("3.0")
    assert window.profile_view.net_chart.delta_active is False
    assert "cleared" in editor.profile_delta_label.text().lower()
    runner.shutdown()


def test_minimal_medium_button_wires_current_medium_and_displays_cli_result(
    monkeypatch,
    tmp_path,
):
    import cmig.cli.main

    _app()
    _stub_graph(monkeypatch)
    model = tmp_path / "model.xml"
    model.write_text("<sbml/>")
    seen: dict[str, list[str]] = {}

    def fake_main(argv):
        seen["argv"] = list(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "minimal_medium_summary.json").write_text(
            json.dumps(
                {
                    "status": "ok",
                    "achieved_growth": 0.2,
                    "components": ["EX_glc__D_e", "EX_nh4_e"],
                    "uptake_bounds": {"EX_glc__D_e": 3.0, "EX_nh4_e": 1.0},
                    "limiting_nutrients": ["EX_glc__D_e"],
                    "warnings": [],
                }
            )
        )
        (out / "manifest.json").write_text('{"run_hash":"minimal"}')
        return 0

    monkeypatch.setattr(cmig.cli.main, "main", fake_main)
    runner = JobRunner(max_workers=1)
    window = build_main_window(runner=runner)
    editor = window.medium_editor
    editor.model_path_input.setText(str(model))
    editor.assume_bigg_check.setChecked(True)
    editor.exact_medium_check.setChecked(True)
    editor.min_growth_spin.setValue(0.2)
    editor.add_row("EX_glc__D_e", 3.0)

    jid = window.run_minimal_medium()
    runner.result(jid, timeout=5)
    window._poll_completed_jobs()

    argv = seen["argv"]
    assert argv[0] == "minimal-medium"
    assert argv[argv.index("--model") + 1] == str(model)
    assert argv[argv.index("--min-growth") + 1] == "0.2"
    assert "--medium" in argv and "--exact-medium" in argv
    assert editor.minimal_table.rowCount() == 2
    assert editor.minimal_table.item(0, 2).text() == "Yes"
    assert "2 components" in editor.minimal_status.text()
    assert editor.minimal_medium_btn.isEnabled()
    runner.shutdown()


def test_medium_tools_have_real_korean_catalogue(monkeypatch):
    _app()
    _stub_graph(monkeypatch)
    window = build_main_window(lang="ko")
    editor = window.medium_editor
    assert editor.title.text() == "배지 편집기"
    assert editor.paste_btn.text() == "CSV 붙여넣기"
    assert editor.nutrients_only_check.text() == "영양소만 보기"
    assert editor.check_growth_btn.text() == "성장 확인"
    assert editor.minimal_medium_btn.text() == "최소 배지 찾기"
    window.runner.shutdown()
