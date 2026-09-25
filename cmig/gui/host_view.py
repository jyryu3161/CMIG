"""Host Impact Dashboard — 미생물→host 영향 GUI (Roadmap Phase 3.2, §12).

Design Ref: §12 (host impact dashboard) / cmig-host-view.design. Plan SC: SC-HV1~HV4.

테이블 기반(offscreen 클린). HostSolveResult(viability·2-interface flux) + HostImpact(microbe→host
cross-feeding)를 표시. 실 backend 산출 소비(orphan 아님). 비viable 명시(silent 위장 금지).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cmig.core.host_impact import identified_transfer_point
from cmig.gui.builder import make_read_only, read_only_item

_IFACE_COLOR = {"lumen": "#2c7fb8", "blood": "#d95f0e", "bigg_external": "#2b8cbe"}
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}
_HOST_NETWORK_CURRENCY_METABOLITES = frozenset({"h", "h2o", "co2"})


class HostImpactView(QWidget):
    """Host Impact Dashboard — viability·2-interface flux·microbe→host cross-feeding."""

    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMinimumSize(0, 0)
        content = QWidget()
        layout = QVBoxLayout(content)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self.title = QLabel("Host-Microbe Interaction")
        file_row = QHBoxLayout()
        self.host_path_input = QLineEdit("")
        self.host_path_input.setPlaceholderText("Human/host SBML/XML model")
        self.browse_host_btn = QPushButton("Host")
        self.host_objective_input = QLineEdit("")
        self.host_objective_input.setPlaceholderText("Optional host objective reaction")
        self.model_dir_input = QLineEdit("")
        self.model_dir_input.setPlaceholderText("Folder of user-prepared microbial models")
        self.browse_model_dir_btn = QPushButton("Models")
        file_row.addWidget(QLabel("Input"))
        file_row.addWidget(self.host_path_input)
        file_row.addWidget(self.browse_host_btn)
        objective_row = QHBoxLayout()
        objective_row.addWidget(QLabel("Host objective"))
        objective_row.addWidget(self.host_objective_input)
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Microbial models"))
        model_row.addWidget(self.model_dir_input)
        model_row.addWidget(self.browse_model_dir_btn)
        medium_row = QHBoxLayout()
        self.host_medium_input = QLineEdit("")
        self.host_medium_input.setPlaceholderText("Host medium CSV/JSON")
        self.browse_host_medium_btn = QPushButton("Host Medium")
        self.microbe_medium_input = QLineEdit("")
        self.microbe_medium_input.setPlaceholderText("Microbe medium CSV/JSON")
        self.browse_microbe_medium_btn = QPushButton("Microbe Medium")
        self.out_dir_input = QLineEdit("")
        self.out_dir_input.setPlaceholderText("Output folder")
        self.browse_out_dir_btn = QPushButton("Output")
        medium_row.addWidget(QLabel("Host medium"))
        medium_row.addWidget(self.host_medium_input)
        medium_row.addWidget(self.browse_host_medium_btn)
        microbe_medium_row = QHBoxLayout()
        microbe_medium_row.addWidget(QLabel("Microbe medium"))
        microbe_medium_row.addWidget(self.microbe_medium_input)
        microbe_medium_row.addWidget(self.browse_microbe_medium_btn)
        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output"))
        output_row.addWidget(self.out_dir_input)
        output_row.addWidget(self.browse_out_dir_btn)
        run_row = QHBoxLayout()
        self.tradeoff_spin = QDoubleSpinBox()
        self.tradeoff_spin.setRange(0.01, 1.0)
        self.tradeoff_spin.setSingleStep(0.05)
        self.tradeoff_spin.setValue(0.5)
        self.tradeoff_spin.setDecimals(2)
        self.microbial_biomass_spin = QDoubleSpinBox()
        self.microbial_biomass_spin.setRange(0.0, 1e9)
        self.microbial_biomass_spin.setSpecialValueText("required")
        self.microbial_biomass_spin.setValue(0.0)
        self.microbial_biomass_spin.setDecimals(6)
        self.host_biomass_spin = QDoubleSpinBox()
        self.host_biomass_spin.setRange(0.0, 1e9)
        self.host_biomass_spin.setSpecialValueText("required")
        self.host_biomass_spin.setValue(0.0)
        self.host_biomass_spin.setDecimals(6)
        self.biomass_basis_kind_combo = QComboBox()
        self.biomass_basis_kind_combo.addItems(
            ["select basis", "measured", "literature", "validation"]
        )
        self.biomass_basis_source_input = QLineEdit("")
        self.biomass_basis_source_input.setPlaceholderText(
            "Biomass measurement record or literature citation"
        )
        self.recursive_check = QCheckBox("Recursive")
        self.keep_host_uptake_check = QCheckBox("Keep host uptake")
        self.include_currency_check = QCheckBox("Currency metabolites")
        # Round 7: the GUI already offered both media, so it inherited the CLI's over-constraint
        # exactly. A capability wired into the CLI and not the GUI is the same defect one surface
        # over — round 5's whole GUI/CLI-parity finding.
        self.allow_unknown_medium_check = QCheckBox("Allow unknown medium")
        self.allow_unknown_medium_check.setToolTip(
            "Apply the medium minus the exchanges these models have no counterpart for, instead "
            "of refusing. The dropped ids are named in the run warnings and the run is reported "
            "as degraded."
        )
        self.run_btn = QPushButton("Run Host-Microbe")
        self.run_search_btn = QPushButton("Rank Combinations")
        run_row.addWidget(QLabel("tradeoff f"))
        run_row.addWidget(self.tradeoff_spin)
        run_row.addWidget(QLabel("microbe gDW"))
        run_row.addWidget(self.microbial_biomass_spin)
        run_row.addWidget(QLabel("host gDW"))
        run_row.addWidget(self.host_biomass_spin)
        run_row.addStretch(1)
        basis_row = QHBoxLayout()
        basis_row.addWidget(QLabel("Biomass basis"))
        basis_row.addWidget(self.biomass_basis_kind_combo)
        basis_row.addWidget(self.biomass_basis_source_input)
        policy_row = QHBoxLayout()
        policy_row.addWidget(self.recursive_check)
        policy_row.addWidget(self.keep_host_uptake_check)
        policy_row.addWidget(self.include_currency_check)
        policy_row.addWidget(self.allow_unknown_medium_check)
        policy_row.addStretch(1)
        run_buttons_row = QHBoxLayout()
        run_buttons_row.addWidget(self.run_btn)
        run_buttons_row.addWidget(self.run_search_btn)
        run_buttons_row.addStretch(1)
        search_row = QHBoxLayout()
        self.search_target_input = QLineEdit("ac")
        self.search_target_input.setPlaceholderText("Target transferred metabolite")
        self.search_metric_combo = QComboBox()
        self.search_metric_combo.addItems(["target_transfer", "objective_value"])
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(1, 20)
        self.min_size_spin.setValue(2)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 20)
        self.max_size_spin.setValue(2)
        search_row.addWidget(QLabel("Host Search Target"))
        search_row.addWidget(self.search_target_input)
        search_row.addWidget(QLabel("Metric"))
        search_row.addWidget(self.search_metric_combo)
        search_row.addWidget(QLabel("Size"))
        search_row.addWidget(self.min_size_spin)
        search_row.addWidget(QLabel("to"))
        search_row.addWidget(self.max_size_spin)
        search_row.addStretch(1)
        figure_row = QHBoxLayout()
        self.figure_mode_combo = QComboBox()
        self.figure_mode_combo.addItems(["Network", "Circle", "Heatmap", "Bubble", "Contribution"])
        self.export_figure_btn = QPushButton("Export Figure")
        self.figure_mode_combo.currentTextChanged.connect(self.refresh_figure_mode)
        figure_row.addWidget(QLabel("Figure Mode"))
        figure_row.addWidget(self.figure_mode_combo)
        figure_row.addWidget(self.export_figure_btn)
        figure_row.addStretch(1)
        self.viability_label = QLabel("")
        self.run_status = QLabel("")
        self.run_status.setWordWrap(True)
        self.run_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # 2-interface flux 표
        self.iface_table = QTableWidget(0, 4)
        self.iface_table.setHorizontalHeaderLabels(
            ["Interface", "Metabolite", "Flux (mmol gDW⁻¹ h⁻¹)", "Direction"])
        self.iface_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.iface_table)
        # microbe→host cross-feeding 표
        self.cross_label = QLabel("Microbe → Host cross-feeding")
        self.cross_table = QTableWidget(0, 2)
        self.cross_table.setHorizontalHeaderLabels(
            ["Metabolite", "Lumen transfer (mmol gDW⁻¹ h⁻¹)"])
        self.cross_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.cross_table)
        self.network_label = QLabel("Interaction Network")
        self.show_currency_metabolites = False
        self.current_run_dir: Path | None = None
        self.network_payload: dict[str, Any] | None = None
        try:
            from cmig.gui.graph_view import InteractionGraphView

            self.network_view: QWidget = InteractionGraphView()
        except ImportError:  # pragma: no cover - optional GUI extra
            self.network_view = QLabel("QtWebEngine is unavailable; network view disabled.")
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self.static_figure_view: QWidget = QWebEngineView()
        except ImportError:  # pragma: no cover - optional GUI extra
            self.static_figure_view = QLabel("QtWebEngine is unavailable; SVG preview disabled.")
        self.figure_stack = QStackedWidget()
        self.figure_stack.addWidget(self.network_view)
        self.figure_stack.addWidget(self.static_figure_view)
        tables = QWidget()
        tables_layout = QVBoxLayout(tables)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        for w in (self.viability_label, self.iface_table, self.cross_label, self.cross_table):
            tables_layout.addWidget(w)
        splitter = QSplitter()
        tables.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.figure_stack.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        splitter.addWidget(tables)
        splitter.addWidget(self.figure_stack)
        splitter.setSizes([450, 760])
        layout.addWidget(self.title)
        layout.addLayout(file_row)
        layout.addLayout(objective_row)
        layout.addLayout(model_row)
        layout.addLayout(medium_row)
        layout.addLayout(microbe_medium_row)
        layout.addLayout(output_row)
        layout.addLayout(run_row)
        layout.addLayout(basis_row)
        layout.addLayout(policy_row)
        layout.addLayout(run_buttons_row)
        layout.addLayout(search_row)
        layout.addLayout(figure_row)
        layout.addWidget(self.run_status)
        layout.addWidget(splitter, 1)
        # Any edit to an answer-determining input invalidates the displayed result: a host
        # viability verdict computed for model/medium A must not sit under inputs saying B.
        for line_edit in (
            self.host_path_input,
            self.host_objective_input,
            self.model_dir_input,
            self.host_medium_input,
            self.microbe_medium_input,
            self.search_target_input,
        ):
            line_edit.textChanged.connect(self.invalidate_results)
        for spin in (
            self.tradeoff_spin, self.microbial_biomass_spin, self.host_biomass_spin,
            self.min_size_spin, self.max_size_spin,
        ):
            spin.valueChanged.connect(self.invalidate_results)
        for check in (
            self.recursive_check, self.keep_host_uptake_check, self.include_currency_check,
            self.allow_unknown_medium_check,
        ):
            check.toggled.connect(self.invalidate_results)
        self.search_metric_combo.currentTextChanged.connect(self.invalidate_results)

    def invalidate_results(self, *_args: Any) -> None:
        """Drop the displayed host result when the request that produced it changed."""
        if (
            self.iface_table.rowCount() == 0
            and self.cross_table.rowCount() == 0
            and not self.viability_label.text()
        ):
            return
        self.iface_table.setRowCount(0)
        self.cross_table.setRowCount(0)
        self.viability_label.setText("")
        self.viability_label.setStyleSheet("")
        self.current_run_dir = None
        self.network_payload = None
        self.run_status.setText("Inputs changed — previous result cleared; re-run to update.")

    def request(self) -> dict[str, Any]:
        """Return the current host-microbe run request from GUI controls."""
        return {
            "host": self.host_path_input.text().strip(),
            "host_objective": self.host_objective_input.text().strip(),
            "model_dir": self.model_dir_input.text().strip(),
            "host_medium": self.host_medium_input.text().strip(),
            "microbe_medium": self.microbe_medium_input.text().strip(),
            "out_dir": self.out_dir_input.text().strip(),
            "tradeoff_f": self.tradeoff_spin.value(),
            "microbial_biomass_gdw": self.microbial_biomass_spin.value(),
            "host_biomass_gdw": self.host_biomass_spin.value(),
            "biomass_basis_kind": (
                ""
                if self.biomass_basis_kind_combo.currentIndex() == 0
                else self.biomass_basis_kind_combo.currentText()
            ),
            "biomass_basis_source": self.biomass_basis_source_input.text().strip(),
            "search_target": self.search_target_input.text().strip() or "ac",
            "search_metric": self.search_metric_combo.currentText(),
            "min_size": self.min_size_spin.value(),
            "max_size": self.max_size_spin.value(),
            "recursive": self.recursive_check.isChecked(),
            "keep_host_uptake": self.keep_host_uptake_check.isChecked(),
            "include_currency_metabolites": self.include_currency_check.isChecked(),
            "allow_unknown_medium": self.allow_unknown_medium_check.isChecked(),
        }

    def set_running(self, job_id: str) -> None:
        self.run_status.setText(f"host-microbe run started: {job_id}")

    def selected_figure_artifact(self) -> str:
        mapping = {
            "Network": "interaction_circle.svg",
            "Circle": "interaction_circle.svg",
            "Heatmap": "interaction_heatmap.svg",
            "Bubble": "interaction_bubble.svg",
            "Contribution": "member_contribution.svg",
        }
        return mapping[self.figure_mode_combo.currentText()]

    def refresh_figure_mode(self, _mode: str | None = None) -> None:
        """Switch the preview between interactive network and saved SVG figures."""
        if self.figure_mode_combo.currentText() == "Network":
            self.figure_stack.setCurrentWidget(self.network_view)
            if self.network_payload is not None and hasattr(self.network_view, "set_payload"):
                self.network_view.set_payload(self.network_payload)
            return
        self.figure_stack.setCurrentWidget(self.static_figure_view)
        if self.current_run_dir is None:
            return
        artifact = self.current_run_dir / self.selected_figure_artifact()
        if not artifact.exists():
            return
        if hasattr(self.static_figure_view, "setHtml"):
            uri = artifact.as_uri()
            self.static_figure_view.setHtml(
                "<!doctype html><html><head><style>"
                "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:white;}"
                "img{width:100%;height:100%;object-fit:contain;display:block;}"
                "</style></head><body>"
                f"<img src='{uri}' alt='{artifact.name}'>"
                "</body></html>",
                QUrl.fromLocalFile(str(artifact.parent)),
            )
        elif hasattr(self.static_figure_view, "load"):
            self.static_figure_view.load(QUrl.fromLocalFile(str(artifact)))

    def load_host_result(self, host_result: Any) -> None:
        """HostSolveResult → viability + 2-interface flux 표(interface/sign 색)."""
        if host_result.viable:
            biomass = host_result.biomass
            biomass_text = "unknown" if biomass is None else f"{biomass:.4g}"
            self.viability_label.setText(
                f"viable · host biomass = {biomass_text}")
            self.viability_label.setStyleSheet("color: #31a354;")
        else:
            self.viability_label.setText(
                f"non-viable (status={host_result.status}) — microbiome support insufficient")
            self.viability_label.setStyleSheet("color: #d62728;")
        rows = host_result.interface_fluxes
        self.iface_table.setRowCount(len(rows))
        for i, f in enumerate(rows):
            cells = [f.interface, f.metabolite, f"{f.flux:.4g}", f.label or "—"]
            for c, text in enumerate(cells):
                item = read_only_item(text)
                if c == 0 and f.interface in _IFACE_COLOR:
                    item.setForeground(QColor(_IFACE_COLOR[f.interface]))
                if c == 3 and f.label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[f.label]))
                self.iface_table.setItem(i, c, item)

    def load_impact(self, impact: Any, *, solved: bool | None = True) -> None:
        """HostImpact → microbe→host cross-feeding 표."""
        points = impact.microbe_to_host
        ranges = getattr(impact, "microbe_to_host_ranges", {})
        ambiguous = set(getattr(impact, "ambiguous_metabolites", []))
        items = sorted(set(points) | set(ranges) | ambiguous)
        self.cross_table.setRowCount(len(items))
        for i, met in enumerate(items):
            flux = identified_transfer_point(points, ranges, met) if solved is not False else None
            if solved is None and met not in points:
                flux = None  # Legacy status-free readback needs an explicit point assertion.
            self.cross_table.setItem(i, 0, read_only_item(met))
            label = "unknown" if flux is None else f"{flux:.4g}"
            interval = ranges.get(met)
            if flux is None and isinstance(interval, (list, tuple)) and len(interval) == 2:
                label += f" [{interval[0]}, {interval[1]}]"
            item = read_only_item(label)
            if flux is not None:
                item.setToolTip("Identifiability: identified")
            elif met in ambiguous:
                item.setToolTip("Identifiability: ambiguous")
            self.cross_table.setItem(i, 1, item)

    def load_bigg_summary(self, payload: dict[str, Any], *, run_dir: Path | None = None) -> None:
        """Load parsed `host_microbe_bigg_summary.json` into tables and network."""
        self.current_run_dir = None if run_dir is None else run_dir.resolve()
        self.run_status.setText(
            "Loaded host-microbe result"
            + ("" if self.current_run_dir is None else f": {self.current_run_dir}")
            + _warning_suffix(payload)
            + (f" · target identifiability: {payload['target_identifiability']}"
               if "target_identifiability" in payload else "")
            + ("\n" + "\n".join(str(w) for w in payload.get("warnings", []))
               if isinstance(payload.get("warnings"), list) and payload["warnings"] else "")
        )
        ranges = payload.get("microbe_to_host_ranges")
        states = payload.get("metabolite_identifiability")
        for row in range(self.cross_table.rowCount()):
            key_item = self.cross_table.item(row, 0)
            value_item = self.cross_table.item(row, 1)
            if key_item is None or value_item is None:
                continue
            interval = ranges.get(key_item.text()) if isinstance(ranges, dict) else None
            if (
                value_item.text() == "unknown"
                and isinstance(interval, list)
                and len(interval) == 2
            ):
                value_item.setText(f"unknown [{interval[0]}, {interval[1]}]")
            if isinstance(states, dict) and key_item.text() in states:
                value_item.setToolTip(f"Identifiability: {states[key_item.text()]}")
        self.network_payload = host_microbe_network_payload(
            payload,
            include_currency_metabolites=self.show_currency_metabolites,
        )
        if hasattr(self.network_view, "set_payload"):
            self.network_view.set_payload(self.network_payload)
        self.refresh_figure_mode()


def host_microbe_network_payload(
    summary: dict[str, Any], *, include_currency_metabolites: bool = False
) -> dict[str, Any]:
    """Build a Cytoscape payload for one-way BiGG host-microbe transfers."""
    microbial = _known_fluxes(summary.get("microbial_secretion", {}))
    host_uptake = _known_fluxes(summary.get("host", {}).get("lumen_uptake", {}))
    transfer = _known_fluxes(summary.get("microbe_to_host", {}))
    unused = _known_fluxes(summary.get("unused_secretion", {}))
    visible_microbial = {
        met: flux
        for met, flux in microbial.items()
        if (
            include_currency_metabolites
            or met not in _HOST_NETWORK_CURRENCY_METABOLITES
            or met in transfer
            or met in host_uptake
        )
    }
    visible_unused = {
        met: flux
        for met, flux in unused.items()
        if (
            include_currency_metabolites
            or met not in _HOST_NETWORK_CURRENCY_METABOLITES
            or met in transfer
            or met in host_uptake
        )
    }
    metabolites = sorted(
        set(visible_microbial) | set(host_uptake) | set(transfer) | set(visible_unused)
    )
    elements: list[dict[str, Any]] = [
        {"data": {"id": "microbiome", "label": "Microbiome", "ntype": "member"}},
        {"data": {"id": "host", "label": "Host", "ntype": "member"}},
    ]
    for met in metabolites:
        elements.append({
            "data": {"id": f"met:{met}", "label": met, "ntype": "environment_pool"}
        })
    edge_i = 0
    for met, flux in sorted(visible_microbial.items()):
        if flux <= 1e-9:
            continue
        elements.append({"data": {
            "id": f"hm-e{edge_i}",
            "source": "microbiome",
            "target": f"met:{met}",
            "etype": "secretion",
            "metabolite": met,
            "weight": flux,
            "label": "microbial secretion",
        }})
        edge_i += 1
    for met, flux in sorted(host_uptake.items()):
        if flux <= 1e-9:
            continue
        elements.append({"data": {
            "id": f"hm-e{edge_i}",
            "source": f"met:{met}",
            "target": "host",
            "etype": "uptake",
            "metabolite": met,
            "weight": flux,
            "label": "host uptake",
        }})
        edge_i += 1
    for met, flux in sorted(transfer.items()):
        if flux <= 1e-9:
            continue
        elements.append({"data": {
            "id": f"hm-e{edge_i}",
            "source": "microbiome",
            "target": "host",
            "etype": "cross_feeding",
            "metabolite": met,
            "weight": flux,
            "label": "microbe to host",
        }})
        edge_i += 1
    return {
        "elements": elements,
        "style": _host_network_stylesheet(),
        "layout": {"name": "cose", "animate": False, "padding": 42},
        "legend": [
            {"symbol": "+", "meaning": "microbial secretion"},
            {"symbol": "-", "meaning": "host uptake"},
            {"symbol": "->", "meaning": "microbe-to-host transfer"},
        ],
    }


def _known_fluxes(values: Any) -> dict[str, float]:
    """An unknown host transfer is absent from graph edges, never a fabricated zero."""
    if not isinstance(values, dict):
        raise ValueError("host flux collection must be an object")
    return {str(met): float(value) for met, value in values.items() if value is not None}


def _host_network_stylesheet() -> list[dict[str, Any]]:
    from cmig.gui.graph_data import STYLESHEET

    return STYLESHEET + [
        {"selector": "node#host",
         "style": {"background-color": "#d95f0e", "shape": "round-rectangle"}},
        {"selector": "node#microbiome",
         "style": {"background-color": "#2c7fb8", "shape": "ellipse"}},
    ]


def _warning_suffix(payload: dict[str, Any]) -> str:
    warnings = payload.get("warnings")
    if not isinstance(warnings, list) or not warnings:
        return ""
    return f" · warnings: {len(warnings)}"
