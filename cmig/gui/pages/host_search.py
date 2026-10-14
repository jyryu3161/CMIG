"""Host Combination Search: rank microbial combinations for one host."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.host_view import HostInputs, HostInputWidgets
from cmig.gui.search_results import SearchResultsPanel


def _size_spin() -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 20)
    spin.setValue(2)
    return spin


class HostSearchPage(AnalysisPage, HostInputWidgets):
    def __init__(self) -> None:
        super().__init__(
            "Host Combination Search",
            "Rank microbial combinations by what they transfer to the host or by the host "
            "objective.",
            run_text="Rank Combinations",
            cancel=False,
        )
        self.host_inputs = HostInputs()
        self.host_inputs.attach(self)
        self.target_input = QLineEdit("ac")
        self.target_input.setPlaceholderText("Target transferred metabolite")
        self.metric_combo = QComboBox()
        self.metric_combo.addItems(["target_transfer", "objective_value"])
        self.min_size_spin = _size_spin()
        self.max_size_spin = _size_spin()
        self.add_input_row("Target", self.target_input, "Metric", self.metric_combo,
                           "Size", self.min_size_spin, "to", self.max_size_spin)
        for name, widget in (("target", self.target_input), ("metric", self.metric_combo),
                             ("min_size", self.min_size_spin),
                             ("max_size", self.max_size_spin)):
            self.register(name, widget)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for control in [*self.host_inputs.widgets(), self.target_input, self.metric_combo,
                        self.min_size_spin, self.max_size_spin]:
            connect_change(control, lambda *_a: self.results_panel.invalidate_results(True))

    def request(self) -> dict[str, Any]:
        return {
            **self.host_inputs.request(),
            "search_target": self.target_input.text().strip() or "ac",
            "search_metric": self.metric_combo.currentText(),
            "min_size": self.min_size_spin.value(),
            "max_size": self.max_size_spin.value(),
        }

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "host_search":
            return {}
        return {
            key: ",".join(value) if isinstance(value, list) else str(value)
            for key, value in self.request().items()
        }
