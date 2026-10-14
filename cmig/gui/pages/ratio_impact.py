"""Ratio Impact: how one member's share of the community changes a target metabolite."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLineEdit

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.pages.strain_growth import tradeoff_spin
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel

CHOOSE = "choose…"


class RatioImpactPage(AnalysisPage):
    REQUEST_FIELDS = ("models", "target", "growth_member", "fractions", "medium",
                      "cooperative_tradeoff")

    def __init__(self) -> None:
        super().__init__(
            "Ratio Impact",
            "Change one member's share of the community and see how a target metabolite "
            "responds. A chosen medium is applied exactly.",
            run_text="Run Ratio Impact",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.member_combo = QComboBox()
        self.member_combo.addItem(CHOOSE, "")
        self.fractions_input = QLineEdit("0.1,0.25,0.5,0.75")
        self.fractions_input.setPlaceholderText("Fractions, e.g. 0.1,0.25,0.5,0.75")
        self.target_input = QLineEdit("but")
        self.target_input.setPlaceholderText("Target metabolite, e.g. but")
        self.cooperative_tradeoff_spin = tradeoff_spin()
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.add_input_row("Member", self.member_combo, "Fractions", self.fractions_input)
        self.add_input_row("Target", self.target_input)
        self.advanced.add_row("Cooperative tradeoff f", self.cooperative_tradeoff_spin)
        self.advanced.track(self.cooperative_tradeoff_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (("models", self.model_picker), ("medium", self.medium_picker),
                             ("member", self.member_combo), ("fractions", self.fractions_input),
                             ("target", self.target_input),
                             ("tradeoff", self.cooperative_tradeoff_spin)):
            self.register(name, widget)
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))
        self.model_picker.selection_changed.connect(self._pool_changed)

    def _pool_changed(self) -> None:
        current = str(self.member_combo.currentData() or "")
        pool = self.model_picker.selected_ids()
        blocked = self.member_combo.blockSignals(True)
        try:
            self.member_combo.clear()
            self.member_combo.addItem(CHOOSE, "")
            for member in pool:
                self.member_combo.addItem(member, member)
            index = self.member_combo.findData(current) if current in pool else 0
            self.member_combo.setCurrentIndex(max(index, 0))
        finally:
            self.member_combo.blockSignals(blocked)

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "abundance_impact":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "target": self.target_input.text().strip(),
            "growth_member": str(self.member_combo.currentData() or ""),
            "fractions": self.fractions_input.text().strip(),
            "medium": self.medium_picker.current_ref(),
            "cooperative_tradeoff": str(self.cooperative_tradeoff_spin.value()),
        }
