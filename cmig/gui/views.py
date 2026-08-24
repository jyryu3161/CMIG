"""GUI Views — Sweep View · External Profile Viewer (Roadmap Phase 2, §11).

Design Ref: §11 (Sweep View·External Profile Viewer) / cmig-gui-views.design. Plan SC: SC-GV1~GV6.

테이블 기반 인터랙티브 뷰(QWebEngine 비의존 → offscreen 클린 검증). 실 backend 소비:
SweepView 가 JobRunner+make_sweep_job 으로 sweep 실행, ExternalProfileView 가 sign/FVA/target
산출을 표시. offscreen = 실행 증거지 human 시각 QA(G-7b) 아님(별도 carry, 정직).
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
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
    QVBoxLayout,
    QWidget,
)

from cmig.gui.builder import make_read_only, read_only_item
from cmig.service import JobRunner, make_sweep_job

# sign 라벨 → UI 색 (secretion=초록 / uptake=보라, §11 diverging)
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}

_MAX_CHART_ROWS = 12
_MEMBER_COLORS = (
    "#2c7fb8",
    "#d95f0e",
    "#41ab5d",
    "#756bb1",
    "#e7298a",
    "#636363",
    "#66c2a4",
    "#e6ab02",
)


def _finite_float(value: Any) -> float | None:
    """Return a finite float without turning missing/invalid measurements into zero."""
    if value is None:
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if math.isfinite(converted) else None


class DivergingProfileChart(QWidget):
    """Qt-native horizontal net-flux chart with optional FVA whiskers."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self.has_fva = False
        self.setMinimumHeight(250)
        self.setToolTip(
            "Positive/green = secretion; negative/purple = uptake. "
            "Whiskers are drawn only when both FVA bounds are recorded."
        )

    def sizeHint(self) -> QSize:
        return QSize(620, 280)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        measured: list[dict[str, Any]] = []
        for row in rows:
            net = _finite_float(row.get("net_flux"))
            if net is None:
                continue
            item = dict(row)
            item["net_flux"] = net
            item["fva_lo"] = _finite_float(row.get("fva_lo"))
            item["fva_hi"] = _finite_float(row.get("fva_hi"))
            measured.append(item)
        measured.sort(key=lambda row: (-abs(float(row["net_flux"])), str(row.get("metabolite"))))
        self.rows = measured[:_MAX_CHART_ROWS]
        self.has_fva = any(
            row.get("fva_lo") is not None and row.get("fva_hi") is not None for row in self.rows
        )
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        title = "Net exchange flux (+ secretion / − uptake)"
        if self.has_fva:
            title += " · FVA whiskers"
        painter.drawText(8, 18, title)
        if not self.rows:
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(8, 45, "No measured profile fluxes")
            return

        left = min(150.0, max(92.0, self.width() * 0.25))
        right = 18.0
        top = 32.0
        bottom = 10.0
        plot_width = max(40.0, self.width() - left - right)
        zero_x = left + plot_width / 2.0
        row_height = max(16.0, (self.height() - top - bottom) / len(self.rows))
        bounds = [abs(float(row["net_flux"])) for row in self.rows]
        for row in self.rows:
            for key in ("fva_lo", "fva_hi"):
                value = row.get(key)
                if value is not None:
                    bounds.append(abs(float(value)))
        max_abs = max(bounds) if bounds else 1.0
        if max_abs == 0.0:
            max_abs = 1.0
        scale = (plot_width / 2.0 - 6.0) / max_abs

        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawLine(QPointF(zero_x, top - 3.0), QPointF(zero_x, self.height() - bottom))
        metrics = painter.fontMetrics()
        for index, row in enumerate(self.rows):
            centre_y = top + row_height * (index + 0.5)
            label = metrics.elidedText(
                str(row.get("metabolite", "")), Qt.TextElideMode.ElideRight, int(left - 14)
            )
            painter.setPen(self.palette().text().color())
            painter.drawText(
                QRectF(4.0, centre_y - row_height / 2.0, left - 12.0, row_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            net = float(row["net_flux"])
            bar_x = zero_x if net >= 0 else zero_x + net * scale
            bar_width = max(1.0, abs(net * scale))
            color = QColor(_LABEL_COLOR["secretion" if net >= 0 else "uptake"])
            color.setAlpha(210)
            painter.fillRect(
                QRectF(
                    bar_x,
                    centre_y - min(7.0, row_height * 0.3),
                    bar_width,
                    min(14.0, row_height * 0.6),
                ),
                color,
            )

            lo, hi = row.get("fva_lo"), row.get("fva_hi")
            if lo is None or hi is None:
                continue
            lo_x = zero_x + float(lo) * scale
            hi_x = zero_x + float(hi) * scale
            painter.setPen(QPen(QColor("#1f2933"), 1.5))
            painter.drawLine(QPointF(lo_x, centre_y), QPointF(hi_x, centre_y))
            painter.drawLine(QPointF(lo_x, centre_y - 4.0), QPointF(lo_x, centre_y + 4.0))
            painter.drawLine(QPointF(hi_x, centre_y - 4.0), QPointF(hi_x, centre_y + 4.0))


class MemberContributionChart(QWidget):
    """Qt-native signed stacked bars for abundance-weighted member contributions."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict[str, Any]] = []
        self.members: list[str] = []
        self.setMinimumHeight(250)
        self.setToolTip(
            "Direct member↔pool edge flux multiplied by member abundance. "
            "Allocated cross-feeding edges are excluded."
        )

    def sizeHint(self) -> QSize:
        return QSize(620, 280)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        measured: list[dict[str, Any]] = []
        members: set[str] = set()
        for row in rows:
            contributions: list[dict[str, Any]] = [
                {"member": str(item["member"]), "value": value}
                for item in row.get("contributions", [])
                if (value := _finite_float(item.get("value"))) is not None
            ]
            if not contributions:
                continue
            members.update(item["member"] for item in contributions)
            measured.append(
                {"metabolite": str(row.get("metabolite", "")), "contributions": contributions}
            )
        measured.sort(
            key=lambda row: (
                -sum(abs(float(item["value"])) for item in row["contributions"]),
                row["metabolite"],
            )
        )
        self.rows = measured[:_MAX_CHART_ROWS]
        self.members = sorted(members)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.palette().base())
        painter.setPen(self.palette().text().color())
        painter.drawText(8, 18, "Per-member contribution (direct flux × abundance)")
        if not self.rows:
            painter.setPen(self.palette().placeholderText().color())
            painter.drawText(8, 45, "No abundance-weighted member contributions")
            return

        left = min(150.0, max(92.0, self.width() * 0.25))
        right = 18.0
        top = 32.0
        legend_height = 24.0
        plot_width = max(40.0, self.width() - left - right)
        zero_x = left + plot_width / 2.0
        row_height = max(16.0, (self.height() - top - legend_height - 8.0) / len(self.rows))
        max_side = 0.0
        for row in self.rows:
            positive = sum(max(0.0, float(item["value"])) for item in row["contributions"])
            negative = -sum(min(0.0, float(item["value"])) for item in row["contributions"])
            max_side = max(max_side, positive, negative)
        if max_side == 0.0:
            max_side = 1.0
        scale = (plot_width / 2.0 - 6.0) / max_side
        member_colors = {
            member: QColor(_MEMBER_COLORS[index % len(_MEMBER_COLORS)])
            for index, member in enumerate(self.members)
        }

        painter.setPen(QPen(self.palette().mid().color(), 1.0))
        painter.drawLine(
            QPointF(zero_x, top - 3.0),
            QPointF(zero_x, self.height() - legend_height - 5.0),
        )
        metrics = painter.fontMetrics()
        for index, row in enumerate(self.rows):
            centre_y = top + row_height * (index + 0.5)
            label = metrics.elidedText(
                row["metabolite"], Qt.TextElideMode.ElideRight, int(left - 14)
            )
            painter.setPen(self.palette().text().color())
            painter.drawText(
                QRectF(4.0, centre_y - row_height / 2.0, left - 12.0, row_height),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            negative_x = zero_x
            positive_x = zero_x
            for item in sorted(row["contributions"], key=lambda value: value["member"]):
                value = float(item["value"])
                width = abs(value) * scale
                if width == 0.0:
                    continue
                if value < 0:
                    negative_x -= width
                    x = negative_x
                else:
                    x = positive_x
                    positive_x += width
                color = member_colors[item["member"]]
                color.setAlpha(210)
                painter.fillRect(
                    QRectF(
                        x,
                        centre_y - min(7.0, row_height * 0.3),
                        max(1.0, width),
                        min(14.0, row_height * 0.6),
                    ),
                    color,
                )

        legend_y = self.height() - 9.0
        legend_x = 8.0
        for member in self.members:
            label = metrics.elidedText(member, Qt.TextElideMode.ElideRight, 90)
            painter.fillRect(QRectF(legend_x, legend_y - 9.0, 8.0, 8.0), member_colors[member])
            painter.setPen(self.palette().text().color())
            painter.drawText(int(legend_x + 12.0), int(legend_y), label)
            legend_x += min(115.0, metrics.horizontalAdvance(label) + 28.0)
            if legend_x > self.width() - 100.0:
                break


def member_contribution_rows(bundle: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Build signed community-basis member contributions from a tidy bundle.

    ``edges.weight`` is per-taxon flux, so the GUI must multiply each direct member↔pool
    edge by that member's recorded abundance. Cross-feeding rows are proportional shared-pool
    allocations and are intentionally excluded. Missing/non-finite values are omitted and
    returned as warnings; they are never replaced with measured-looking zeros.
    """
    abundances: dict[str, float] = {}
    warnings: set[str] = set()
    for node in bundle.nodes.to_pylist():
        if node.get("node_type") != "member":
            continue
        member = str(node.get("node_id", ""))
        abundance = _finite_float(node.get("abundance"))
        if abundance is None:
            warnings.add(f"{member}: abundance not recorded")
            continue
        abundances[member] = abundance

    values: dict[str, dict[str, float]] = {}
    for index, edge in enumerate(bundle.edges.to_pylist()):
        edge_type = str(edge.get("edge_type", ""))
        if edge_type == "cross_feeding":
            continue
        if edge_type == "secretion":
            member = str(edge.get("source_id", ""))
            sign = 1.0
        elif edge_type == "uptake":
            member = str(edge.get("target_id", ""))
            sign = -1.0
        else:
            continue
        weight = _finite_float(edge.get("weight"))
        if weight is None:
            warnings.add(f"edge {index}: flux not recorded")
            continue
        abundance = abundances.get(member)
        if abundance is None:
            warnings.add(f"{member}: direct edge omitted because abundance is unavailable")
            continue
        metabolite = str(edge.get("metabolite", ""))
        by_member = values.setdefault(metabolite, {})
        by_member[member] = by_member.get(member, 0.0) + sign * weight * abundance

    rows = [
        {
            "metabolite": metabolite,
            "contributions": [
                {"member": member, "value": value} for member, value in sorted(by_member.items())
            ],
        }
        for metabolite, by_member in sorted(values.items())
    ]
    return rows, sorted(warnings)


class SweepView(QWidget):
    """Sweep View — 축·값 정의 → JobRunner sweep → 결과 매트릭스(+cache-hit). 실 backend 소비."""

    _COLS = ("condition_id", "value", "status", "cache_hit")

    def __init__(self, runner: JobRunner | None = None) -> None:
        super().__init__()
        self.runner = runner if runner is not None else JobRunner(max_workers=2)
        layout = QVBoxLayout(self)
        self.title = QLabel("Sweep")
        self.status = QLabel("Advanced result view: configure a fixture sweep, then Run Sweep.")
        config_row = QHBoxLayout()
        self.tradeoff_fs_input = QLineEdit("0.3,0.5")
        self.tradeoff_fs_input.setPlaceholderText("Comma-separated tradeoff f values")
        self.solvers_input = QLineEdit("gurobi")
        self.solvers_input.setPlaceholderText("Comma-separated solvers")
        self.run_btn = QPushButton("Run Sweep")
        config_row.addWidget(QLabel("tradeoff f"))
        config_row.addWidget(self.tradeoff_fs_input)
        config_row.addWidget(QLabel("solvers"))
        config_row.addWidget(self.solvers_input)
        config_row.addWidget(self.run_btn)
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(["Condition", "Value", "Status", "Cache"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.table)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addLayout(config_row)
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
                item = read_only_item(text)
                if r.status == "failed":
                    item.setForeground(QColor("#d62728"))
                self.table.setItem(i, c, item)


class ExternalProfileView(QWidget):
    """External profile table plus Qt-native net/FVA and member-contribution charts."""

    _COLS = ("metabolite", "net_flux", "label", "fva")

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("External Profile")
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(
            ["Metabolite", "Net flux (mmol gDW⁻¹ h⁻¹)", "Direction", "FVA [lo, hi]"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.table)
        self.net_chart = DivergingProfileChart()
        self.member_chart = MemberContributionChart()
        chart_row = QHBoxLayout()
        chart_row.addWidget(self.net_chart, 1)
        chart_row.addWidget(self.member_chart, 1)
        self.chart_note = QLabel(
            f"Charts show up to {_MAX_CHART_ROWS} metabolites by magnitude. "
            "FVA whiskers appear only when both bounds are recorded."
        )
        self.chart_note.setWordWrap(True)
        self.contribution_basis_label = QLabel(
            "Member basis: direct member↔pool edge flux × recorded abundance; "
            "allocated cross-feeding edges excluded."
        )
        self.contribution_basis_label.setWordWrap(True)
        self.target_label = QLabel("")
        layout.addWidget(self.title)
        layout.addLayout(chart_row)
        layout.addWidget(self.chart_note)
        layout.addWidget(self.contribution_basis_label)
        layout.addWidget(self.table)
        layout.addWidget(self.target_label)

    def load_profile(
        self,
        rows: list[dict[str, Any]],
        *,
        member_contributions: list[dict[str, Any]] | None = None,
        contribution_warnings: list[str] | None = None,
    ) -> None:
        """profile rows → 표(secretion=초록/uptake=보라 색). FVA 있으면 [lo, hi] 표시."""
        self.net_chart.set_rows(rows)
        self.member_chart.set_rows(member_contributions or [])
        basis = (
            "Member basis: direct member↔pool edge flux × recorded abundance; "
            "allocated cross-feeding edges excluded."
        )
        if member_contributions is None:
            basis += " Load a complete tidy run to populate this chart."
        if contribution_warnings:
            basis += " Omitted: " + "; ".join(contribution_warnings)
        self.contribution_basis_label.setText(basis)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            net = _finite_float(r.get("net_flux"))
            label = r.get("label") or "—"
            lo, hi = _finite_float(r.get("fva_lo")), _finite_float(r.get("fva_hi"))
            fva = f"[{lo:.3g}, {hi:.3g}]" if lo is not None and hi is not None else "—"
            cells = [
                str(r.get("metabolite", "")),
                "—" if net is None else f"{net:.4g}",
                label,
                fva,
            ]
            for c, text in enumerate(cells):
                item = read_only_item(text)
                if c == 2 and label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[label]))
                self.table.setItem(i, c, item)

    def load_bundle(self, bundle: Any) -> None:
        """Load the complete tidy presentation contract, including member-basis charts."""
        contributions, warnings = member_contribution_rows(bundle)
        self.load_profile(
            bundle.profile.to_pylist(),
            member_contributions=contributions,
            contribution_warnings=warnings,
        )

    def load_targets(self, target_summary: list[dict[str, Any]] | None) -> None:
        """target readout(SCFA 등) 요약 라벨."""
        if not target_summary:
            self.target_label.setText("")
            return
        parts = [
            f"{t.get('metabolite')}={t.get('ui_flux', t.get('value', 0)):.3g}"
            for t in target_summary
        ]
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
        self.t_end_spin.setSuffix(" h")
        self.dt_spin = QDoubleSpinBox()
        self.dt_spin.setRange(1e-5, 1000.0)
        self.dt_spin.setValue(0.1)
        self.dt_spin.setDecimals(5)
        self.dt_spin.setSuffix(" h")
        self.biomass_spin = QDoubleSpinBox()
        self.biomass_spin.setRange(1e-9, 1000.0)
        self.biomass_spin.setValue(0.01)
        self.biomass_spin.setDecimals(6)
        self.biomass_spin.setSuffix(" gDW L⁻¹")
        # Without this, growth can be fed by unconstrained default-medium substrates that are
        # never depleted, and the CLI's own summary declares the run NOT interpretable. The
        # control has to be reachable so the user can make the run interpretable, not only be
        # told that it is not (round-5 coordinator CC-6).
        self.close_untracked_check = QCheckBox("Close untracked uptake")
        self.close_untracked_check.setToolTip(
            "Close every uptake exchange outside 'Initial' before integrating, so a "
            "substrate/Km experiment is actually controlled."
        )
        self.run_dfba_btn = QPushButton("Run dFBA")
        dfba_row.addWidget(QLabel("Initial (mmol L⁻¹)"))
        dfba_row.addWidget(self.initial_input)
        dfba_row.addWidget(QLabel("T end"))
        dfba_row.addWidget(self.t_end_spin)
        dfba_row.addWidget(QLabel("dt"))
        dfba_row.addWidget(self.dt_spin)
        dfba_row.addWidget(QLabel("Biomass"))
        dfba_row.addWidget(self.biomass_spin)
        dfba_row.addWidget(self.close_untracked_check)
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
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setStyleSheet("color: #d62728;")
        self.warning_label.setVisible(False)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Run", "Status", "Final time (h)", "Readout"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(130)
        make_read_only(self.table)
        self.figure_label = QLabel("No dynamics figure loaded.")
        self.figure_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.figure_label.setMinimumHeight(460)
        self.figure_label.setStyleSheet("background: white; border: 1px solid #d9dee3;")

        layout.addWidget(self.title)
        layout.addLayout(model_row)
        layout.addLayout(dfba_row)
        layout.addLayout(spatial_row)
        layout.addWidget(self.status)
        layout.addWidget(self.warning_label)
        layout.addWidget(self.table)
        layout.addWidget(self.figure_label)
        for line_edit in (self.model_path_input, self.initial_input, self.spatial_metabolite_input):
            line_edit.textChanged.connect(self.invalidate_results)
        for spin in (
            self.t_end_spin,
            self.dt_spin,
            self.biomass_spin,
            self.grid_size_spin,
            self.steps_spin,
            self.spatial_dt_spin,
            self.diffusion_spin,
        ):
            spin.valueChanged.connect(self.invalidate_results)
        for combo in (self.source_combo, self.sink_combo):
            combo.currentTextChanged.connect(self.invalidate_results)
        self.close_untracked_check.toggled.connect(self.invalidate_results)

    def invalidate_results(self, *_args: Any) -> None:
        """Drop the displayed timecourse when its inputs no longer describe it."""
        if self.table.rowCount() == 0:
            return
        self.table.setRowCount(0)
        self.warning_label.setVisible(False)
        self.warning_label.setText("")
        self.figure_label.setPixmap(QPixmap())
        self.figure_label.setText("Inputs changed — previous result cleared; re-run to update.")
        self.status.setText("Inputs changed — previous result cleared; re-run to update.")

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
            "close_untracked_uptake": self.close_untracked_check.isChecked(),
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
        """Render a dFBA run — including its own verdict on whether it is interpretable.

        `cmig dfba` records `warnings` and `n_untracked_uptake` when growth was supported by
        unconstrained default-medium substrates outside the tracked set; in that case its own
        artifact says a substrate/Km result is NOT interpretable. Presenting such a run as an
        ordinary `completed` row with a biomass number is the presentation layer discarding
        the honest signal (round-5 coordinator CC-6), so the warning is shown prominently and
        the status cell is flagged rather than reading plain `completed`.
        """
        final_conc = payload.get("final_concentrations", {})
        readout = ", ".join(f"{k}={float(v):.3g}" for k, v in dict(final_conc).items())
        warnings = [str(w) for w in (payload.get("warnings") or [])]
        n_untracked = payload.get("n_untracked_uptake")
        status = str(payload.get("status", ""))
        self._set_single_row(
            "dFBA",
            f"{status} ⚠ see warnings" if warnings else status,
            float(payload.get("final_t", 0.0)),
            f"biomass={float(payload.get('final_biomass', 0.0)):.3g}"
            + (f"; {readout}" if readout else ""),
        )
        untracked_note = (
            f" · {n_untracked} untracked uptake substrate(s)"
            if isinstance(n_untracked, int) and n_untracked > 0
            else ""
        )
        self.status.setText(
            f"dFBA loaded: {run_dir}"
            + (f" · {len(warnings)} warning(s){untracked_note}" if warnings else untracked_note)
        )
        self._show_warnings(warnings)
        self._load_figure(run_dir, "dfba_timecourse.svg")

    def load_spatial_summary(self, payload: dict[str, Any], *, run_dir: Any) -> None:
        warnings = [str(w) for w in (payload.get("warnings") or [])]
        status = str(payload.get("status", ""))
        self._set_single_row(
            "Spatial",
            f"{status} ⚠ see warnings" if warnings else status,
            float(payload.get("final_t", 0.0)),
            f"range={float(payload.get('final_min', 0.0)):.3g}.."
            f"{float(payload.get('final_max', 0.0)):.3g}",
        )
        self.status.setText(
            f"Spatial preview loaded: {run_dir}"
            + (f" · {len(warnings)} warning(s)" if warnings else "")
        )
        self._show_warnings(warnings)
        self._load_figure(run_dir, "spatial_snapshots.svg")

    def _show_warnings(self, warnings: list[str]) -> None:
        if not warnings:
            self.warning_label.setVisible(False)
            self.warning_label.setText("")
            return
        self.warning_label.setText("⚠ " + "\n⚠ ".join(warnings))
        self.warning_label.setVisible(True)

    def _set_single_row(self, run_type: str, status: str, final_t: float, readout: str) -> None:
        self.table.setRowCount(1)
        values = [run_type, status, f"{final_t:.4g}", readout]
        for idx, value in enumerate(values):
            self.table.setItem(0, idx, read_only_item(value))

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
