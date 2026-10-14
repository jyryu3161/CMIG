"""Spatial Preview: how one metabolite spreads across a grid (no growth)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.views import DynamicsResults, _finite_float, _number_text


class SpatialPage(AnalysisPage, DynamicsResults):
    def __init__(self) -> None:
        super().__init__(
            "Spatial Preview",
            "Preview how one metabolite spreads across a grid (no growth).",
            run_text="Preview Spatial Medium",
            cancel=False,
        )
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
        self.run_spatial_btn = self.run_btn
        self.add_input_row("Metabolite", self.spatial_metabolite_input,
                           "Grid", self.grid_size_spin, "Steps", self.steps_spin)
        self.advanced.add_row("dt", self.spatial_dt_spin, "Diffusion", self.diffusion_spin)
        self.advanced.add_row("Source", self.source_combo, "Sink", self.sink_combo)
        self.advanced.track(self.spatial_dt_spin, self.diffusion_spin, self.source_combo,
                            self.sink_combo)
        self._build_dynamics_results()
        for name, widget in (("metabolite", self.spatial_metabolite_input),
                             ("grid", self.grid_size_spin), ("steps", self.steps_spin),
                             ("dt", self.spatial_dt_spin), ("diffusion", self.diffusion_spin),
                             ("source", self.source_combo), ("sink", self.sink_combo)):
            self.register(name, widget)
            connect_change(widget, self.invalidate_results)

    def invalidate_results(self, *_args: Any) -> None:
        """Drop the displayed preview when its inputs no longer describe it."""
        if self.table.rowCount() == 0:
            return
        self._clear_dynamics("Inputs changed — previous result cleared; re-run to update.")

    def spatial_request(self) -> dict[str, Any]:
        size = self.grid_size_spin.value()
        return {
            "metabolite": self.spatial_metabolite_input.text().strip() or "EX_glc__D_e",
            "width": size,
            "height": size,
            "steps": self.steps_spin.value(),
            "dt": self.spatial_dt_spin.value(),
            "diffusion": self.diffusion_spin.value(),
            "source_edge": self.source_combo.currentText(),
            "sink_edge": self.sink_combo.currentText(),
        }

    def load_spatial_summary(self, payload: dict[str, Any], *, run_dir: Path) -> None:
        warnings = [str(w) for w in (payload.get("warnings") or [])]
        status = str(payload.get("status", ""))
        self._set_single_row(
            "Spatial",
            f"{status} ⚠ see warnings" if warnings else status,
            _finite_float(payload.get("final_t")),
            "range=" + _number_text(payload.get("final_min"))
            + ".." + _number_text(payload.get("final_max")),
        )
        self.status.setText(
            f"Spatial preview loaded: {run_dir}"
            + (f" · {len(warnings)} warning(s)" if warnings else "")
        )
        self._show_warnings(warnings)
        self._load_figure(run_dir, "spatial_snapshots.svg")
