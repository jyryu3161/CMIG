"""GUI Builder/Compare — Community Builder · Constraint Sandbox · Scenario Compare (Phase 2, §11).

Design Ref: §11 / §10 G1 Sandbox / cmig-gui-builder.design. Plan SC: SC-CB1~CB3·CS1~CS3·SC1~SC3.

테이블 기반(offscreen 클린). CommunityBuilderView=멤버/abundance/tradeoff 구성,
ConstraintSandboxView=bound 제약+preview/commit(JobRunner debounce re-solve),
DeltaTable=core.delta.DeltaResult 표시(significant 강조·실패 명시), ScenarioCompareView=A/B delta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
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
        self.status = QLabel("preview (비기록)")
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
            self.status.setText(f"preview 실패: {delta.diagnostic}")
        else:
            n = len(delta.significant())
            self.status.setText(f"preview (비기록) — 변화 대사체 {n}개")

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
        self.delta_view = DeltaTable()
        self.growth_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.delta_view)
        layout.addWidget(self.growth_label)

    def load_comparison(self, delta: DeltaResult) -> None:
        """compute_delta(A, B) 결과 표시(동일조건 고정 비교)."""
        self.delta_view.load_delta(delta)
        added = ", ".join(delta.added_members) or "—"
        status = "" if delta.status == "ok" else f" [실패: {delta.diagnostic}]"
        self.growth_label.setText(
            f"growth Δ: {delta.growth_delta:+.4g} · added: {added}{status}")


class SearchView(QWidget):
    """Consortium Search — ranked candidates + Pareto/strategy warnings."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Consortium Search")
        controls = QHBoxLayout()
        self.targets_input = QLineEdit("ac,but")
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(["auto", "exhaustive", "ga"])
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 100)
        self.top_k_spin.setValue(3)
        self.run_btn = QPushButton("Run Search")
        controls.addWidget(QLabel("Targets"))
        controls.addWidget(self.targets_input)
        controls.addWidget(QLabel("Strategy"))
        controls.addWidget(self.strategy_combo)
        controls.addWidget(QLabel("Top K"))
        controls.addWidget(self.top_k_spin)
        controls.addWidget(self.run_btn)
        self.status = QLabel("")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Members", "Target", "Score", "Flux", "Status"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pareto_label = QLabel("")
        layout.addWidget(self.title)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addWidget(self.pareto_label)

    def load_summary(self, summary: dict[str, object]) -> None:
        """search_advanced_summary.json 형태를 표로 표시."""
        strategy = str(summary.get("strategy", ""))
        warnings = summary.get("warnings")
        warning_count = len(warnings) if isinstance(warnings, list) else 0
        self.status.setText(
            f"strategy: {strategy}" + (f" · warnings: {warning_count}" if warning_count else "")
        )
        ranked = summary.get("top_ranked", {})
        rows: list[tuple[str, str, float, float, str]] = []
        if isinstance(ranked, dict):
            for target, items in ranked.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    members = item.get("members", [])
                    score = _float_value(item.get("score", 0.0))
                    rows.append((
                        "+".join(str(x) for x in members) if isinstance(members, list) else "",
                        str(target),
                        score,
                        _float_value(item.get("target_flux", score)),
                        str(item.get("status", "ok")),
                    ))
        elif isinstance(ranked, list):
            for item in ranked:
                if not isinstance(item, dict):
                    continue
                members = item.get("members", [])
                score = _float_value(item.get("score", 0.0))
                rows.append((
                    "+".join(str(x) for x in members) if isinstance(members, list) else "",
                    str(summary.get("target", "")),
                    score,
                    score,
                    str(item.get("status", "ok")),
                ))
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                text = f"{value:.4g}" if isinstance(value, float) else str(value)
                self.table.setItem(r, c, QTableWidgetItem(text))
        pareto = summary.get("pareto_frontier")
        pareto_count = len(pareto) if isinstance(pareto, list) else 0
        self.pareto_label.setText(
            "" if not pareto_count else f"Pareto frontier candidates: {pareto_count}"
        )


def _float_value(value: object) -> float:
    if isinstance(value, (int, float, str)):
        return float(value)
    return 0.0
