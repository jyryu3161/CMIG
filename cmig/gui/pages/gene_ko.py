"""Gene Knockout: rank single-gene knockouts of one fixed combination."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox

from cmig.gui.analysis_page import AnalysisPage, connect_change
from cmig.gui.builder import TARGET_DIRECTIONS
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import SearchResultsPanel

ALL_MEMBERS = "All members"


class GeneKoPage(AnalysisPage):
    REQUEST_FIELDS = (
        "models", "target", "ko_members", "ko_member", "ko_genes", "max_genes", "ko_top_k",
        "medium", "direction", "growth_fraction",
    )

    def __init__(self) -> None:
        super().__init__(
            "Gene Knockout",
            "Rank single-gene knockouts of one fixed combination. A chosen medium is "
            "applied exactly.",
            run_text="Rank Gene KOs",
            cancel=False,
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        self.members_picker = ModelPicker("Combination")
        self.member_combo = QComboBox()
        self.member_combo.addItem(ALL_MEMBERS, "")
        self.target_input = QLineEdit("but")
        self.target_input.setPlaceholderText("Target metabolite, e.g. but")
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(list(TARGET_DIRECTIONS))
        self.genes_input = QLineEdit("")
        self.genes_input.setPlaceholderText("Optional gene ids; blank = auto genes")
        self.max_genes_spin = QSpinBox()
        self.max_genes_spin.setRange(0, 10000)
        self.max_genes_spin.setValue(50)
        self.top_k_spin = QSpinBox()  # gene-ko-search default 20, separate from Search top-k
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(20)
        self.growth_fraction_spin = QDoubleSpinBox()
        self.growth_fraction_spin.setRange(0.001, 1.0)
        self.growth_fraction_spin.setDecimals(3)
        self.growth_fraction_spin.setValue(0.5)
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.add_input_row(self.members_picker, "Edited member", self.member_combo)
        self.add_input_row("Target", self.target_input, "Direction", self.direction_combo)
        self.advanced.add_row("Gene IDs", self.genes_input)
        self.advanced.add_row("Max genes/member", self.max_genes_spin, "KO Top K",
                              self.top_k_spin, "Target growth fraction",
                              self.growth_fraction_spin)
        self.advanced.track(self.genes_input, self.max_genes_spin, self.top_k_spin,
                            self.growth_fraction_spin)
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        for name, widget in (
            ("models", self.model_picker), ("medium", self.medium_picker),
            ("members", self.members_picker), ("member", self.member_combo),
            ("target", self.target_input), ("direction", self.direction_combo),
            ("genes", self.genes_input), ("max_genes", self.max_genes_spin),
            ("top_k", self.top_k_spin), ("growth_fraction", self.growth_fraction_spin),
        ):
            self.register(name, widget)
        self.model_picker.selection_changed.connect(self._pool_changed)
        self.members_picker.selection_changed.connect(self._combination_changed)
        for widget in (self.model_picker, self.medium_picker, self.members_picker,
                       self.member_combo, self.target_input, self.direction_combo,
                       self.genes_input, self.max_genes_spin, self.top_k_spin,
                       self.growth_fraction_spin):
            connect_change(widget, lambda *_a: self.results_panel.invalidate_results(True))

    def _pool_changed(self) -> None:
        kept = self.members_picker.selected_ids()
        pool = self.model_picker.selected_ids()
        self.members_picker.set_choices([(model_id, True, "") for model_id in pool])
        self.members_picker.set_selected([m for m in kept if m in pool])

    def _combination_changed(self) -> None:
        current = str(self.member_combo.currentData() or "")
        members = self.members_picker.selected_ids()
        blocked = self.member_combo.blockSignals(True)
        try:
            self.member_combo.clear()
            self.member_combo.addItem(ALL_MEMBERS, "")
            for member in members:
                self.member_combo.addItem(member, member)
            index = self.member_combo.findData(current) if current in members else 0
            self.member_combo.setCurrentIndex(max(index, 0))
        finally:
            self.member_combo.blockSignals(blocked)

    def request_fields(self, kind: str) -> dict[str, str]:
        if kind != "gene_ko":
            return {}
        return {
            "models": ",".join(self.model_picker.selected_ids()),
            "target": self.target_input.text().strip(),
            "ko_members": ",".join(self.members_picker.selected_ids()),
            "ko_member": str(self.member_combo.currentData() or ""),
            "ko_genes": self.genes_input.text().strip(),
            "max_genes": str(self.max_genes_spin.value()),
            "ko_top_k": str(self.top_k_spin.value()),
            "medium": self.medium_picker.current_ref(),
            "direction": self.direction_combo.currentText(),
            "growth_fraction": str(self.growth_fraction_spin.value()),
        }
