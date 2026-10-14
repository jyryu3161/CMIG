"""Strain Growth: each member's growth alone and inside the community."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel


def tradeoff_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.01, 1.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setValue(0.5)
    return spin


class StrainGrowthPage(AnalysisPage):
    REQUEST_FIELDS = ("models", "medium", "cooperative_tradeoff")

    def __init__(self) -> None:
        super().__init__(
            "Strain Growth",
            "Growth of each selected strain alone and in the community. A chosen medium is "
            "applied exactly.",
            run_text="Run Strain Growth",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.cooperative_tradeoff_spin = tradeoff_spin()
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.advanced.add_row("Cooperative tradeoff f", self.cooperative_tradeoff_spin)
        self.advanced.track(self.cooperative_tradeoff_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (("models", self.model_picker), ("medium", self.medium_picker),
                             ("tradeoff", self.cooperative_tradeoff_spin)):
            self.register(name, widget)
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "strain_growth":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "medium": self.medium_picker.current_ref(),
            "cooperative_tradeoff": str(self.cooperative_tradeoff_spin.value()),
        }
