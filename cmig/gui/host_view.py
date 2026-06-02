"""Host Impact Dashboard — 미생물→host 영향 GUI (Roadmap Phase 3.2, §12).

Design Ref: §12 (host impact dashboard) / cmig-host-view.design. Plan SC: SC-HV1~HV4.

테이블 기반(offscreen 클린). HostSolveResult(viability·2-interface flux) + HostImpact(microbe→host
cross-feeding)를 표시. 실 backend 산출 소비(orphan 아님). 비viable 명시(silent 위장 금지).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_IFACE_COLOR = {"lumen": "#2c7fb8", "blood": "#d95f0e", "bigg_external": "#2b8cbe"}
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}
_HOST_NETWORK_CURRENCY_METABOLITES = frozenset({"h", "h2o", "co2"})


class HostImpactView(QWidget):
    """Host Impact Dashboard — viability·2-interface flux·microbe→host cross-feeding."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Host Impact")
        file_row = QHBoxLayout()
        self.host_path_input = QLineEdit("")
        self.host_path_input.setPlaceholderText("Host SBML/XML model")
        self.browse_host_btn = QPushButton("Host")
        self.model_dir_input = QLineEdit("")
        self.model_dir_input.setPlaceholderText("Microbial model folder")
        self.browse_model_dir_btn = QPushButton("Models")
        file_row.addWidget(QLabel("Input"))
        file_row.addWidget(self.host_path_input)
        file_row.addWidget(self.browse_host_btn)
        file_row.addWidget(self.model_dir_input)
        file_row.addWidget(self.browse_model_dir_btn)
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
        medium_row.addWidget(self.host_medium_input)
        medium_row.addWidget(self.browse_host_medium_btn)
        medium_row.addWidget(self.microbe_medium_input)
        medium_row.addWidget(self.browse_microbe_medium_btn)
        medium_row.addWidget(self.out_dir_input)
        medium_row.addWidget(self.browse_out_dir_btn)
        run_row = QHBoxLayout()
        self.tradeoff_spin = QDoubleSpinBox()
        self.tradeoff_spin.setRange(0.01, 1.0)
        self.tradeoff_spin.setSingleStep(0.05)
        self.tradeoff_spin.setValue(0.5)
        self.tradeoff_spin.setDecimals(2)
        self.recursive_check = QCheckBox("Recursive")
        self.keep_host_uptake_check = QCheckBox("Keep host uptake")
        self.include_currency_check = QCheckBox("Currency metabolites")
        self.run_btn = QPushButton("Run Host-Microbe")
        run_row.addWidget(QLabel("tradeoff f"))
        run_row.addWidget(self.tradeoff_spin)
        run_row.addWidget(self.recursive_check)
        run_row.addWidget(self.keep_host_uptake_check)
        run_row.addWidget(self.include_currency_check)
        run_row.addStretch(1)
        run_row.addWidget(self.run_btn)
        self.viability_label = QLabel("")
        self.run_status = QLabel("")
        # 2-interface flux 표
        self.iface_table = QTableWidget(0, 4)
        self.iface_table.setHorizontalHeaderLabels(["Interface", "Metabolite", "Flux", "Direction"])
        self.iface_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # microbe→host cross-feeding 표
        self.cross_label = QLabel("Microbe → Host cross-feeding")
        self.cross_table = QTableWidget(0, 2)
        self.cross_table.setHorizontalHeaderLabels(["Metabolite", "Flux (lumen transfer)"])
        self.cross_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.network_label = QLabel("Interaction Network")
        self.show_currency_metabolites = False
        self.network_payload: dict[str, Any] | None = None
        try:
            from cmig.gui.graph_view import InteractionGraphView

            self.network_view: QWidget = InteractionGraphView()
        except ImportError:  # pragma: no cover - optional GUI extra
            self.network_view = QLabel("QtWebEngine is unavailable; network view disabled.")
        tables = QWidget()
        tables_layout = QVBoxLayout(tables)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        for w in (self.viability_label, self.iface_table, self.cross_label, self.cross_table):
            tables_layout.addWidget(w)
        splitter = QSplitter()
        splitter.addWidget(tables)
        splitter.addWidget(self.network_view)
        splitter.setSizes([430, 570])
        layout.addWidget(self.title)
        layout.addLayout(file_row)
        layout.addLayout(medium_row)
        layout.addLayout(run_row)
        layout.addWidget(self.run_status)
        layout.addWidget(splitter)

    def request(self) -> dict[str, Any]:
        """Return the current host-microbe run request from GUI controls."""
        return {
            "host": self.host_path_input.text().strip(),
            "model_dir": self.model_dir_input.text().strip(),
            "host_medium": self.host_medium_input.text().strip(),
            "microbe_medium": self.microbe_medium_input.text().strip(),
            "out_dir": self.out_dir_input.text().strip(),
            "tradeoff_f": self.tradeoff_spin.value(),
            "recursive": self.recursive_check.isChecked(),
            "keep_host_uptake": self.keep_host_uptake_check.isChecked(),
            "include_currency_metabolites": self.include_currency_check.isChecked(),
        }

    def set_running(self, job_id: str) -> None:
        self.run_status.setText(f"host-microbe run started: {job_id}")

    def load_host_result(self, host_result: Any) -> None:
        """HostSolveResult → viability + 2-interface flux 표(interface/sign 색)."""
        if host_result.viable:
            self.viability_label.setText(
                f"viable · host biomass = {host_result.biomass:.4g}")
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
                item = QTableWidgetItem(text)
                if c == 0 and f.interface in _IFACE_COLOR:
                    item.setForeground(QColor(_IFACE_COLOR[f.interface]))
                if c == 3 and f.label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[f.label]))
                self.iface_table.setItem(i, c, item)

    def load_impact(self, impact: Any) -> None:
        """HostImpact → microbe→host cross-feeding 표."""
        items = sorted(impact.microbe_to_host.items())
        self.cross_table.setRowCount(len(items))
        for i, (met, flux) in enumerate(items):
            self.cross_table.setItem(i, 0, QTableWidgetItem(met))
            self.cross_table.setItem(i, 1, QTableWidgetItem(f"{flux:.4g}"))

    def load_bigg_summary(self, payload: dict[str, Any], *, run_dir: Path | None = None) -> None:
        """Load parsed `host_microbe_bigg_summary.json` into tables and network."""
        self.run_status.setText(
            "Loaded host-microbe result"
            + ("" if run_dir is None else f": {run_dir}")
            + _warning_suffix(payload)
        )
        self.network_payload = host_microbe_network_payload(
            payload,
            include_currency_metabolites=self.show_currency_metabolites,
        )
        if hasattr(self.network_view, "set_payload"):
            self.network_view.set_payload(self.network_payload)


def host_microbe_network_payload(
    summary: dict[str, Any], *, include_currency_metabolites: bool = False
) -> dict[str, Any]:
    """Build a Cytoscape payload for one-way BiGG host-microbe transfers."""
    microbial = {
        str(met): float(value)
        for met, value in dict(summary.get("microbial_secretion", {})).items()
    }
    host_uptake = {
        str(met): float(value)
        for met, value in dict(summary.get("host", {}).get("lumen_uptake", {})).items()
    }
    transfer = {
        str(met): float(value)
        for met, value in dict(summary.get("microbe_to_host", {})).items()
    }
    unused = {
        str(met): float(value)
        for met, value in dict(summary.get("unused_secretion", {})).items()
    }
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
        "layout": {"name": "cose", "animate": False, "padding": 110},
        "legend": [
            {"symbol": "+", "meaning": "microbial secretion"},
            {"symbol": "-", "meaning": "host uptake"},
            {"symbol": "->", "meaning": "microbe-to-host transfer"},
        ],
    }


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
