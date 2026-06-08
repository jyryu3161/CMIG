"""GUI Views — Sweep View · External Profile Viewer (Roadmap Phase 2, §11).

Design Ref: §11 (Sweep View·External Profile Viewer) / cmig-gui-views.design. Plan SC: SC-GV1~GV6.

테이블 기반 인터랙티브 뷰(QWebEngine 비의존 → offscreen 클린 검증). 실 backend 소비:
SweepView 가 JobRunner+make_sweep_job 으로 sweep 실행, ExternalProfileView 가 sign/FVA/target
산출을 표시. offscreen = 실행 증거지 human 시각 QA(G-7b) 아님(별도 carry, 정직).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.service import JobRunner, make_sweep_job

# sign 라벨 → UI 색 (secretion=초록 / uptake=보라, §11 diverging)
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}


class SweepView(QWidget):
    """Sweep View — 축·값 정의 → JobRunner sweep → 결과 매트릭스(+cache-hit). 실 backend 소비."""

    _COLS = ("condition_id", "value", "status", "cache_hit")

    def __init__(self, runner: JobRunner | None = None) -> None:
        super().__init__()
        self.runner = runner if runner is not None else JobRunner(max_workers=2)
        layout = QVBoxLayout(self)
        self.title = QLabel("Sweep")
        self.status = QLabel("Advanced result view: configure product sweeps from the CLI.")
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(["Condition", "Value", "Status", "Cache"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        self._job_id: str | None = None

    def run_sweep(self, axes: Any, *, run_hash_fn: Any, solve_fn: Any, metric: str) -> str:
        """JobRunner 로 sweep 비차단 제출(실 wiring). job_id 반환."""
        job = make_sweep_job(axes, run_hash_fn=run_hash_fn, solve_fn=solve_fn, metric=metric)
        self._job_id = self.runner.submit("sweep", job)
        return self._job_id

    def load_results(self, rows: list[Any]) -> None:
        """SweepRow 목록 → 결과 매트릭스. cache_hit 표시(재계산 회피 가시화)."""
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            val = "—" if r.value is None else f"{r.value:.4g}"
            cells = [r.condition_id, val, r.status, "hit" if r.cache_hit else "miss"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if r.status == "failed":
                    item.setForeground(QColor("#d62728"))
                self.table.setItem(i, c, item)


class ExternalProfileView(QWidget):
    """External Profile Viewer — metabolite별 net flux + sign 색 + FVA 범위 + target 요약."""

    _COLS = ("metabolite", "net_flux", "label", "fva")

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("External Profile")
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(
            ["Metabolite", "Net flux", "Direction", "FVA [lo, hi]"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.target_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.table)
        layout.addWidget(self.target_label)

    def load_profile(self, rows: list[dict[str, Any]]) -> None:
        """profile rows → 표(secretion=초록/uptake=보라 색). FVA 있으면 [lo, hi] 표시."""
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            net = r.get("net_flux")
            label = r.get("label") or "—"
            lo, hi = r.get("fva_lo"), r.get("fva_hi")
            fva = f"[{lo:.3g}, {hi:.3g}]" if lo is not None and hi is not None else "—"
            cells = [
                str(r.get("metabolite", "")),
                "—" if net is None else f"{net:.4g}",
                label, fva,
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 2 and label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[label]))
                self.table.setItem(i, c, item)

    def load_targets(self, target_summary: list[dict[str, Any]] | None) -> None:
        """target readout(SCFA 등) 요약 라벨."""
        if not target_summary:
            self.target_label.setText("")
            return
        parts = [f"{t.get('metabolite')}={t.get('ui_flux', t.get('value', 0)):.3g}"
                 for t in target_summary]
        self.target_label.setText("Targets: " + ", ".join(parts))


class DfbaSpatialView(QWidget):
    """Dynamics tab — user-model dFBA plus lightweight spatial medium preview."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Dynamics")

        model_row = QHBoxLayout()
        self.model_path_input = QLineEdit("")
        self.model_path_input.setPlaceholderText("SBML model for well-mixed dFBA")
        self.browse_model_btn = QPushButton("Model")
        self.out_dir_input = QLineEdit("")
        self.out_dir_input.setPlaceholderText("Optional output folder")
        self.browse_out_btn = QPushButton("Output")
        model_row.addWidget(QLabel("dFBA"))
        model_row.addWidget(self.model_path_input)
        model_row.addWidget(self.browse_model_btn)
        model_row.addWidget(self.out_dir_input)
        model_row.addWidget(self.browse_out_btn)

        dfba_row = QHBoxLayout()
        self.initial_input = QLineEdit("EX_glc__D_e=10,EX_o2_e=20,EX_ac_e=0,EX_lac__D_e=0")
        self.initial_input.setPlaceholderText("EX_glc__D_e=10,EX_o2_e=20,EX_ac_e=0")
        self.t_end_spin = QDoubleSpinBox()
        self.t_end_spin.setRange(0.01, 10000.0)
        self.t_end_spin.setValue(5.0)
        self.t_end_spin.setDecimals(3)
        self.dt_spin = QDoubleSpinBox()
        self.dt_spin.setRange(1e-5, 1000.0)
        self.dt_spin.setValue(0.1)
        self.dt_spin.setDecimals(5)
        self.biomass_spin = QDoubleSpinBox()
        self.biomass_spin.setRange(1e-9, 1000.0)
        self.biomass_spin.setValue(0.01)
        self.biomass_spin.setDecimals(6)
        self.run_dfba_btn = QPushButton("Run dFBA")
        dfba_row.addWidget(QLabel("Initial"))
        dfba_row.addWidget(self.initial_input)
        dfba_row.addWidget(QLabel("T end"))
        dfba_row.addWidget(self.t_end_spin)
        dfba_row.addWidget(QLabel("dt"))
        dfba_row.addWidget(self.dt_spin)
        dfba_row.addWidget(QLabel("Biomass"))
        dfba_row.addWidget(self.biomass_spin)
        dfba_row.addWidget(self.run_dfba_btn)

        spatial_row = QHBoxLayout()
        self.spatial_metabolite_input = QLineEdit("EX_glc__D_e")
        self.spatial_metabolite_input.setPlaceholderText("Metabolite")
        self.grid_size_spin = QSpinBox()
        self.grid_size_spin.setRange(8, 256)
        self.grid_size_spin.setValue(32)
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 10000)
        self.steps_spin.setValue(80)
        self.spatial_dt_spin = QDoubleSpinBox()
        self.spatial_dt_spin.setRange(1e-5, 1000.0)
        self.spatial_dt_spin.setValue(0.1)
        self.spatial_dt_spin.setDecimals(5)
        self.diffusion_spin = QDoubleSpinBox()
        self.diffusion_spin.setRange(0.0, 1000.0)
        self.diffusion_spin.setValue(0.15)
        self.diffusion_spin.setDecimals(5)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["left", "right", "top", "bottom", "center", "none"])
        self.sink_combo = QComboBox()
        self.sink_combo.addItems(["right", "left", "top", "bottom", "center", "none"])
        self.run_spatial_btn = QPushButton("Preview Spatial Medium")
        spatial_row.addWidget(QLabel("Spatial"))
        spatial_row.addWidget(self.spatial_metabolite_input)
        spatial_row.addWidget(QLabel("Grid"))
        spatial_row.addWidget(self.grid_size_spin)
        spatial_row.addWidget(QLabel("Steps"))
        spatial_row.addWidget(self.steps_spin)
        spatial_row.addWidget(QLabel("dt"))
        spatial_row.addWidget(self.spatial_dt_spin)
        spatial_row.addWidget(QLabel("Diffusion"))
        spatial_row.addWidget(self.diffusion_spin)
        spatial_row.addWidget(QLabel("Source"))
        spatial_row.addWidget(self.source_combo)
        spatial_row.addWidget(QLabel("Sink"))
        spatial_row.addWidget(self.sink_combo)
        spatial_row.addWidget(self.run_spatial_btn)

        self.status = QLabel("")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Run", "Status", "Final time", "Readout"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(130)
        self.figure_label = QLabel("No dynamics figure loaded.")
        self.figure_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.figure_label.setMinimumHeight(460)
        self.figure_label.setStyleSheet("background: white; border: 1px solid #d9dee3;")

        layout.addWidget(self.title)
        layout.addLayout(model_row)
        layout.addLayout(dfba_row)
        layout.addLayout(spatial_row)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addWidget(self.figure_label)

    def browse_model(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select dFBA Model", "", "Models (*.xml *.sbml *.xml.gz *.sbml.gz)"
        )
        if path:
            self.model_path_input.setText(path)

    def browse_out(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Dynamics Output Folder")
        if path:
            self.out_dir_input.setText(path)

    def dfba_request(self) -> dict[str, Any]:
        return {
            "model": self.model_path_input.text().strip(),
            "out_dir": self.out_dir_input.text().strip(),
            "initial": self.initial_input.text().strip(),
            "t_end": self.t_end_spin.value(),
            "dt": self.dt_spin.value(),
            "initial_biomass": self.biomass_spin.value(),
        }

    def spatial_request(self) -> dict[str, Any]:
        size = self.grid_size_spin.value()
        return {
            "metabolite": self.spatial_metabolite_input.text().strip() or "EX_glc__D_e",
            "out_dir": self.out_dir_input.text().strip(),
            "width": size,
            "height": size,
            "steps": self.steps_spin.value(),
            "dt": self.spatial_dt_spin.value(),
            "diffusion": self.diffusion_spin.value(),
            "source_edge": self.source_combo.currentText(),
            "sink_edge": self.sink_combo.currentText(),
        }

    def load_dfba_summary(self, payload: dict[str, Any], *, run_dir: Any) -> None:
        final_conc = payload.get("final_concentrations", {})
        readout = ", ".join(f"{k}={float(v):.3g}" for k, v in dict(final_conc).items())
        self._set_single_row(
            "dFBA",
            str(payload.get("status", "")),
            float(payload.get("final_t", 0.0)),
            f"biomass={float(payload.get('final_biomass', 0.0)):.3g}"
            + (f"; {readout}" if readout else ""),
        )
        self.status.setText(f"dFBA loaded: {run_dir}")
        self._load_figure(run_dir, "dfba_timecourse.svg")

    def load_spatial_summary(self, payload: dict[str, Any], *, run_dir: Any) -> None:
        self._set_single_row(
            "Spatial",
            str(payload.get("status", "")),
            float(payload.get("final_t", 0.0)),
            f"range={float(payload.get('final_min', 0.0)):.3g}.."
            f"{float(payload.get('final_max', 0.0)):.3g}",
        )
        self.status.setText(f"Spatial preview loaded: {run_dir}")
        self._load_figure(run_dir, "spatial_snapshots.svg")

    def _set_single_row(self, run_type: str, status: str, final_t: float, readout: str) -> None:
        self.table.setRowCount(1)
        values = [run_type, status, f"{final_t:.4g}", readout]
        for idx, value in enumerate(values):
            self.table.setItem(0, idx, QTableWidgetItem(value))

    def _load_figure(self, run_dir: Any, artifact: str) -> None:
        path = run_dir / artifact
        tiff = path.with_suffix(".tiff")
        if tiff.exists():
            path = tiff
        if not path.exists():
            return
        pixmap = _load_pixmap(path)
        if pixmap.isNull():
            self.figure_label.setText(f"Could not load figure: {path.name}")
            return
        target_width = max(600, self.figure_label.width() - 20)
        target_height = max(280, self.figure_label.height() - 20)
        self.figure_label.setPixmap(
            pixmap.scaled(
                target_width,
                target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


def _load_pixmap(path: Any) -> QPixmap:
    if str(path).lower().endswith(".svg"):
        try:
            from PySide6.QtSvg import QSvgRenderer
        except ImportError:
            return QPixmap(str(path))
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            return QPixmap()
        size = renderer.defaultSize()
        if size.isEmpty():
            size = QSize(1000, 700)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap
    return QPixmap(str(path))
