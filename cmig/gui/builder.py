"""GUI Builder/Compare — Community Builder · Constraint Sandbox · Scenario Compare (Phase 2, §11).

Design Ref: §11 / §10 G1 Sandbox / cmig-gui-builder.design. Plan SC: SC-CB1~CB3·CS1~CS3·SC1~SC3.

테이블 기반(offscreen 클린). CommunityBuilderView=멤버/abundance/tradeoff 구성,
ConstraintSandboxView=bound 제약+preview/commit(JobRunner debounce re-solve),
DeltaTable=core.delta.DeltaResult 표시(significant 강조·실패 명시), ScenarioCompareView=A/B delta.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.core.delta import DeltaResult
from cmig.core.sandbox import BoundConstraint


class CommunityBuilderView(QWidget):
    """Community Builder — 멤버 추가/제거·abundance·tradeoff f 슬라이더 → taxonomy 구성."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Community Builder")
        self.status = QLabel("Advanced preview: use Search or Host for product runs.")
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Member", "Abundance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # tradeoff f 슬라이더 (0..1, 0.01 step → 0..100)
        f_row = QHBoxLayout()
        self.f_label = QLabel("tradeoff f: 0.50")
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(1, 100)
        self.f_slider.setValue(50)
        self.f_slider.valueChanged.connect(self._on_f)
        f_row.addWidget(self.f_label)
        f_row.addWidget(self.f_slider)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addLayout(f_row)

    def _on_f(self, v: int) -> None:
        self.f_label.setText(f"tradeoff f: {v / 100:.2f}")

    def tradeoff_f(self) -> float:
        return self.f_slider.value() / 100.0

    def add_member(self, member_id: str, abundance: float = 1.0) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(member_id))
        self.table.setItem(r, 1, QTableWidgetItem(str(abundance)))

    def remove_member(self, row: int) -> None:
        self.table.removeRow(row)

    def members(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in range(self.table.rowCount()):
            mid = self.table.item(r, 0)
            ab = self.table.item(r, 1)
            if mid and mid.text().strip():
                out[mid.text().strip()] = float(ab.text()) if ab else 1.0
        return out


class DeltaTable(QTableWidget):
    """DeltaResult → 표(metabolite·baseline·modified·delta). significant 강조·실패 색."""

    _COLS = ("metabolite", "baseline", "modified", "delta")

    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Metabolite", "Baseline", "Modified", "Δ"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def load_delta(self, delta: DeltaResult, *, threshold: float = 1e-6) -> None:
        sig = {d.metabolite for d in delta.significant(threshold)}
        self.setRowCount(len(delta.profile))
        for i, d in enumerate(delta.profile):
            cells = [d.metabolite, f"{d.baseline:.4g}", f"{d.modified:.4g}", f"{d.delta:+.4g}"]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if d.metabolite in sig:
                    item.setForeground(QColor("#d62728"))    # 변화 있는 대사체 강조
                self.setItem(i, c, item)


class ConstraintSandboxView(QWidget):
    """G1 Constraint Sandbox — bound 제약 + preview/commit + debounce 재solve(JobRunner)."""

    def __init__(self, debounce_ms: int = 500) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Constraint Sandbox (preview)")
        self.bound_table = QTableWidget(0, 3)
        self.bound_table.setHorizontalHeaderLabels(["Reaction", "Lower", "Upper"])
        self.bound_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.delta_view = DeltaTable()
        btn_row = QHBoxLayout()
        self.preview_btn = QPushButton("Preview")
        self.commit_btn = QPushButton("Apply / Commit")
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.commit_btn)
        self.status = QLabel("Advanced sandbox: one bound constraint per preview run.")
        layout.addWidget(self.title)
        layout.addWidget(self.bound_table)
        layout.addLayout(btn_row)
        layout.addWidget(self.delta_view)
        layout.addWidget(self.status)
        # debounce: 슬라이더 연속 변경 → 마지막만 재solve (OD-54)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)

    def add_bound(self, reaction_id: str, lower: float, upper: float) -> None:
        r = self.bound_table.rowCount()
        self.bound_table.insertRow(r)
        self.bound_table.setItem(r, 0, QTableWidgetItem(reaction_id))
        self.bound_table.setItem(r, 1, QTableWidgetItem(str(lower)))
        self.bound_table.setItem(r, 2, QTableWidgetItem(str(upper)))

    def constraints(self) -> list[BoundConstraint]:
        out: list[BoundConstraint] = []
        for r in range(self.bound_table.rowCount()):
            rid = self.bound_table.item(r, 0)
            lo = self.bound_table.item(r, 1)
            hi = self.bound_table.item(r, 2)
            if rid and rid.text().strip():
                out.append(BoundConstraint(
                    rid.text().strip(),
                    float(lo.text()) if lo else 0.0,
                    float(hi.text()) if hi else 0.0))
        return out

    def show_preview(self, delta: DeltaResult) -> None:
        """preview 결과 표시(비기록 — store/run_hash 없음, §8.5)."""
        self.delta_view.load_delta(delta)
        if delta.status == "failed":
            self.status.setText(f"preview failed: {delta.diagnostic}")
        else:
            n = len(delta.significant())
            self.status.setText(f"preview (not recorded) — changed metabolites: {n}")

    def show_commit(self, delta: DeltaResult, run_hash: str) -> None:
        """commit 결과(run_hash 승격 — artifact 기록)."""
        self.delta_view.load_delta(delta)
        self.status.setText(f"committed (run_hash {run_hash[:12]}…)")


class ScenarioCompareView(QWidget):
    """Scenario Compare — A vs B(또는 N) delta 표 + growth Δ + 상태."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Scenario Compare (A → B)")
        self.status = QLabel("Advanced preview: open completed runs through Profile first.")
        self.delta_view = DeltaTable()
        self.growth_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addWidget(self.delta_view)
        layout.addWidget(self.growth_label)

    def load_comparison(self, delta: DeltaResult) -> None:
        """compute_delta(A, B) 결과 표시(동일조건 고정 비교)."""
        self.delta_view.load_delta(delta)
        added = ", ".join(delta.added_members) or "—"
        status = "" if delta.status == "ok" else f" [failed: {delta.diagnostic}]"
        self.growth_label.setText(
            f"growth Δ: {delta.growth_delta:+.4g} · added: {added}{status}")


class SearchView(QWidget):
    """Consortium Search — ranked candidates + Pareto/strategy warnings."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Find Best Model Combination")
        pool_row = QHBoxLayout()
        self.model_dir_input = QLineEdit("")
        self.model_dir_input.setPlaceholderText("Folder of user-prepared microbial models")
        self.browse_pool_btn = QPushButton("Browse")
        pool_row.addWidget(QLabel("Model Folder"))
        pool_row.addWidget(self.model_dir_input)
        pool_row.addWidget(self.browse_pool_btn)
        controls = QHBoxLayout()
        self.targets_input = QLineEdit("but")
        self.targets_input.setPlaceholderText("Target metabolite, e.g. but or ac")
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["auto", "exhaustive", "random", "ga"])
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(1, 20)
        self.min_size_spin.setValue(2)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 20)
        self.max_size_spin.setValue(2)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(3)
        self.robustness_check = QCheckBox("FVA")
        self.run_btn = QPushButton("Run Search")
        self.export_figure_btn = QPushButton("Export Figure")
        self.figure_mode_combo = QComboBox()
        self.figure_mode_combo.addItems(["Ranking", "Scatter"])
        self.figure_mode_combo.currentTextChanged.connect(self.refresh_figure_mode)
        controls.addWidget(QLabel("Target"))
        controls.addWidget(self.targets_input)
        controls.addWidget(QLabel("Size"))
        controls.addWidget(self.min_size_spin)
        controls.addWidget(QLabel("to"))
        controls.addWidget(self.max_size_spin)
        controls.addWidget(QLabel("Strategy"))
        controls.addWidget(self.strategy_combo)
        controls.addWidget(QLabel("Top K"))
        controls.addWidget(self.top_k_spin)
        controls.addWidget(self.robustness_check)
        controls.addWidget(self.run_btn)
        controls.addWidget(QLabel("Figure"))
        controls.addWidget(self.figure_mode_combo)
        controls.addWidget(self.export_figure_btn)
        ko_row = QHBoxLayout()
        self.ko_members_input = QLineEdit("")
        self.ko_members_input.setPlaceholderText("Fixed combo for KO, e.g. iHN637,iSFV_1184")
        self.ko_member_input = QLineEdit("")
        self.ko_member_input.setPlaceholderText("Member to edit")
        self.ko_genes_input = QLineEdit("")
        self.ko_genes_input.setPlaceholderText("Gene ids, comma-separated")
        self.run_ko_btn = QPushButton("Rank Gene KOs")
        ko_row.addWidget(QLabel("Gene KO"))
        ko_row.addWidget(self.ko_members_input)
        ko_row.addWidget(self.ko_member_input)
        ko_row.addWidget(self.ko_genes_input)
        ko_row.addWidget(self.run_ko_btn)
        self.status = QLabel("")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Members", "Target", "Score", "Flux", "Growth", "FVA Range", "Status"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pareto_label = QLabel("")
        self.current_run_dir: Path | None = None
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            self.figure_view: QWidget = QWebEngineView()
        except ImportError:  # pragma: no cover - optional GUI extra
            self.figure_view = QLabel("QtWebEngine is unavailable; figure preview disabled.")
        self.figure_stack = QStackedWidget()
        self.figure_stack.addWidget(self.figure_view)
        layout.addWidget(self.title)
        layout.addLayout(pool_row)
        layout.addLayout(controls)
        layout.addLayout(ko_row)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addWidget(self.pareto_label)
        layout.addWidget(self.figure_stack)

    def selected_figure_artifact(self) -> str:
        if (
            self.current_run_dir is not None
            and (self.current_run_dir / "host_search_plot.svg").exists()
        ):
            return "host_search_plot.svg"
        if (
            self.current_run_dir is not None
            and (self.current_run_dir / "gene_ko_plot.svg").exists()
        ):
            return "gene_ko_plot.svg"
        mapping = {"Ranking": "search_plot.svg", "Scatter": "search_scatter.svg"}
        return mapping[self.figure_mode_combo.currentText()]

    def refresh_figure_mode(self, _mode: str | None = None) -> None:
        """Load the selected saved search SVG into the preview pane."""
        if self.current_run_dir is None:
            return
        artifact = self.current_run_dir / self.selected_figure_artifact()
        if not artifact.exists():
            return
        if hasattr(self.figure_view, "setHtml"):
            uri = artifact.as_uri()
            self.figure_view.setHtml(
                "<!doctype html><html><head><style>"
                "html,body{margin:0;width:100%;height:100%;overflow:hidden;background:white;}"
                "img{width:100%;height:100%;object-fit:contain;display:block;}"
                "</style></head><body>"
                f"<img src='{uri}' alt='{artifact.name}'>"
                "</body></html>",
                QUrl.fromLocalFile(str(artifact.parent)),
            )

    def load_summary(self, summary: dict[str, object], *, run_dir: Path | None = None) -> None:
        """search_advanced_summary.json 형태를 표로 표시."""
        self.current_run_dir = None if run_dir is None else run_dir.resolve()
        strategy = str(summary.get("strategy", ""))
        warnings = summary.get("warnings")
        warning_count = len(warnings) if isinstance(warnings, list) else 0
        self.status.setText(
            f"strategy: {strategy}" + (f" · warnings: {warning_count}" if warning_count else "")
        )
        ranked = summary.get("top_ranked", {})
        rows: list[tuple[str, str, float | None, float | None, float | None, str, str]] = []
        if isinstance(ranked, dict):
            for target, items in ranked.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    members = item.get("members", [])
                    score = _optional_float(item.get("score"))
                    target_flux = _optional_float(item.get("target_flux"))
                    growth = _optional_float(item.get("community_growth"))
                    fva_range = _fva_range_text(item)
                    rows.append((
                        "+".join(str(x) for x in members) if isinstance(members, list) else "",
                        str(target),
                        score,
                        target_flux if target_flux is not None else score,
                        growth,
                        fva_range,
                        str(item.get("status", "ok")),
                    ))
        elif isinstance(ranked, list):
            target = str(summary.get("target", ""))
            for item in ranked:
                if not isinstance(item, dict):
                    continue
                members = item.get("members", [])
                score = _optional_float(item.get("score"))
                target_flux = _optional_float(item.get("target_flux"))
                growth = _optional_float(item.get("community_growth"))
                fva_range = _fva_range_text(item)
                rows.append((
                    "+".join(str(x) for x in members) if isinstance(members, list) else "",
                    target,
                    score,
                    target_flux if target_flux is not None else score,
                    growth,
                    fva_range,
                    str(item.get("status", "ok")),
                ))
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = (
                    "—" if value is None
                    else f"{value:.4g}" if isinstance(value, float)
                    else str(value)
                )
                self.table.setItem(r, c, QTableWidgetItem(text))
        pareto = summary.get("pareto_frontier")
        pareto_count = len(pareto) if isinstance(pareto, list) else 0
        self.pareto_label.setText(
            "" if not pareto_count else f"Pareto frontier candidates: {pareto_count}"
        )
        self.refresh_figure_mode()


def _float_value(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return float(value)
    return None


def _fva_range_text(item: dict[object, object]) -> str:
    lo = _optional_float(item.get("robustness_fva_lo"))
    hi = _optional_float(item.get("robustness_fva_hi"))
    status = item.get("robustness_status")
    if lo is not None and hi is not None:
        return f"{lo:.4g}..{hi:.4g}"
    return "" if status is None else str(status)
