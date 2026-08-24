"""GUI Builder/Compare — Community Builder · Constraint Sandbox · Scenario Compare (Phase 2, §11).

Design Ref: §11 / §10 G1 Sandbox / cmig-gui-builder.design. Plan SC: SC-CB1~CB3·CS1~CS3·SC1~SC3.

테이블 기반(offscreen 클린). CommunityBuilderView=멤버/abundance/tradeoff 구성,
ConstraintSandboxView=bound 제약+preview/commit(JobRunner debounce re-solve),
DeltaTable=core.delta.DeltaResult 표시(significant 강조·실패 명시), ScenarioCompareView=A/B delta.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, QTimer, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
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
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.core.delta import DeltaResult
from cmig.core.sandbox import BoundConstraint

#: Default SearchView column labels. Adapters may override them per workflow so a growth
#: rate is never displayed under a header that says "Flux" (round-5 P2 F7/F21).
SEARCH_COLUMNS = ("Members", "Target", "Score", "Flux", "Growth", "FVA Range", "Status")

_DIAGNOSTIC_COLOR = QColor("#d62728")


class _NoEditorDelegate(QStyledItemDelegate):
    """Item delegate that can never produce an editor.

    `setEditTriggers(NoEditTriggers)` closes every *user* path into edit mode, but it is not
    the whole guarantee: `QAbstractItemView.edit(index, AllEditTriggers, None)` bypasses the
    trigger check entirely, and the items themselves still carry `ItemIsEditable`. Refusing
    to build an editor closes the remaining door in one place, for every read-only table,
    without touching the ~15 population loops that create the items.
    """

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QWidget:
        # Qt accepts a null QWidget pointer to refuse editing, while PySide6's stub declares
        # a non-optional QWidget return. The cast keeps the exact override signature without
        # changing the runtime null-pointer contract.
        return cast(QWidget, None)


def make_read_only(table: QTableWidget) -> QTableWidget:
    """Mark a table as *computed output*: the user must not be able to type into it.

    A hand-typed 999.9 is visually indistinguishable from a solved flux, so every table
    that renders a computed number is read-only. Input tables (medium, bounds, community
    members) deliberately stay editable.

    Two layers, because neither alone is sufficient (see `_NoEditorDelegate`): edit triggers
    close the user paths, and the delegate closes the programmatic `edit()` path. Populate
    these tables with `read_only_item()` so the *model* also reports the cell as
    non-editable — that third layer is per-item because doing it from here (via an
    `itemChanged` hook) costs a Python round trip per cell and measured 46 ms on a 2712-row
    profile against a 3 ms baseline.
    """
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setItemDelegate(_NoEditorDelegate(table))  # parented, so it outlives this call
    return table


def read_only_item(text: str) -> QTableWidgetItem:
    """Build a cell for a computed value, with `ItemIsEditable` already cleared.

    Clearing the flag before the item is inserted costs one C++ call and emits nothing,
    where clearing it afterwards would emit `itemChanged` for every cell in the table.
    """
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class CommunityBuilderView(QWidget):
    """Community Builder — 멤버 추가/제거·abundance·tradeoff f 슬라이더 → taxonomy 구성."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Community Builder")
        self.status = QLabel(
            "Advanced preview: point Model Folder at prepared GEMs, then Run Community."
        )
        pool_row = QHBoxLayout()
        self.model_dir_input = QLineEdit("")
        self.model_dir_input.setPlaceholderText("Folder of user-prepared microbial models")
        self.browse_model_dir_btn = QPushButton("Browse")
        self.run_btn = QPushButton("Run Community")
        pool_row.addWidget(QLabel("Model Folder"))
        pool_row.addWidget(self.model_dir_input)
        pool_row.addWidget(self.browse_model_dir_btn)
        pool_row.addWidget(self.run_btn)
        # `cmig solve` refuses to run without an explicit namespace decision. Mirror that gate
        # here instead of failing at rc=2 with the real reason hidden on the process's stdout.
        namespace_row = QHBoxLayout()
        self.assume_bigg_check = QCheckBox(
            "I reviewed these models and confirm they are already in BiGG namespace"
        )
        self.namespace_decisions_input = QLineEdit("")
        self.namespace_decisions_input.setPlaceholderText(
            "…or a reviewed namespace-decisions JSON file"
        )
        self.browse_namespace_decisions_btn = QPushButton("Decisions")
        namespace_row.addWidget(self.assume_bigg_check)
        namespace_row.addWidget(self.namespace_decisions_input)
        namespace_row.addWidget(self.browse_namespace_decisions_btn)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Member", "Abundance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        member_btn_row = QHBoxLayout()
        self.add_member_btn = QPushButton("Add member")
        self.remove_member_btn = QPushButton("Remove selected")
        self.add_member_btn.clicked.connect(lambda: self.add_member("", 1.0))
        self.remove_member_btn.clicked.connect(self._remove_selected_member)
        member_btn_row.addWidget(self.add_member_btn)
        member_btn_row.addWidget(self.remove_member_btn)
        member_btn_row.addStretch(1)
        #: rows whose abundance could not be parsed on the last members() call
        self.invalid_rows: list[int] = []
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
        layout.addLayout(pool_row)
        layout.addLayout(namespace_row)
        layout.addWidget(self.table)
        layout.addLayout(member_btn_row)
        layout.addLayout(f_row)

    def _on_f(self, v: int) -> None:
        self.f_label.setText(f"tradeoff f: {v / 100:.2f}")

    def _remove_selected_member(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def namespace_policy(self) -> tuple[list[str], str]:
        """Return (extra argv, error message) for the CLI's namespace gate.

        Never guesses: without an explicit confirmation or a reviewed decisions file the
        run is refused in the GUI, with the same reason the CLI would have printed.
        """
        decisions = self.namespace_decisions_input.text().strip()
        assumed = self.assume_bigg_check.isChecked()
        if assumed and decisions:
            return [], (
                "Choose one namespace policy: either the reviewed decisions file or the "
                "explicit BiGG confirmation, not both."
            )
        if assumed:
            return ["--assume-bigg-namespace"], ""
        if decisions:
            return ["--namespace-decisions", decisions], ""
        return [], (
            "Namespace review required: provide a reviewed namespace-decisions file, or tick "
            "the checkbox to confirm these models are already in BiGG namespace. "
            "`cmig solve` refuses to run without one of the two."
        )

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
        """Return member→abundance overrides. Unparseable rows are recorded, never skipped.

        Silently dropping a row the user typed would run a *different* community than the
        one on screen, so `invalid_rows` is populated and the caller must refuse to run.
        """
        out: dict[str, float] = {}
        self.invalid_rows = []
        for r in range(self.table.rowCount()):
            mid = self.table.item(r, 0)
            ab = self.table.item(r, 1)
            if not (mid and mid.text().strip()):
                continue
            try:
                value = float(ab.text()) if ab else 1.0
            except ValueError:
                self.invalid_rows.append(r + 1)
                continue
            out[mid.text().strip()] = value
        return out


class DeltaTable(QTableWidget):
    """DeltaResult → 표(metabolite·baseline·modified·delta). significant 강조·실패 색."""

    _COLS = ("metabolite", "baseline", "modified", "delta")

    def __init__(self) -> None:
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["Metabolite", "Baseline", "Modified", "Δ"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self)

    def load_delta(self, delta: DeltaResult, *, threshold: float = 1e-6) -> None:
        sig = {d.metabolite for d in delta.significant(threshold)}
        self.setRowCount(len(delta.profile))
        for i, d in enumerate(delta.profile):
            cells = [d.metabolite, f"{d.baseline:.4g}", f"{d.modified:.4g}", f"{d.delta:+.4g}"]
            for c, text in enumerate(cells):
                item = read_only_item(text)
                if d.metabolite in sig:
                    item.setForeground(QColor("#d62728"))  # 변화 있는 대사체 강조
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
        self.add_bound_btn = QPushButton("Add bound")
        self.remove_bound_btn = QPushButton("Remove selected")
        self.add_bound_btn.clicked.connect(lambda: self.add_bound("", 0.0, 0.0))
        self.remove_bound_btn.clicked.connect(self._remove_selected_bound)
        self.preview_btn = QPushButton("Preview")
        self.commit_btn = QPushButton("Apply / Commit")
        btn_row.addWidget(self.add_bound_btn)
        btn_row.addWidget(self.remove_bound_btn)
        btn_row.addWidget(self.preview_btn)
        btn_row.addWidget(self.commit_btn)
        self.status = QLabel("Advanced sandbox: one bound constraint per preview run.")
        #: rows whose lower/upper bound could not be parsed on the last constraints() call
        self.invalid_rows: list[int] = []
        layout.addWidget(self.title)
        layout.addWidget(self.bound_table)
        layout.addLayout(btn_row)
        layout.addWidget(self.delta_view)
        layout.addWidget(self.status)
        # debounce: bound 편집 연속 변경 → 마지막만 재solve (OD-54). itemChanged 마다 재무장하고,
        # 타이머 만료 시 preview_btn 을 프로그램적으로 click() 해 app.py 의 기존 preview 배선을
        # 그대로 재사용한다(뷰는 Qt 전용 — JobRunner/EngineService 는 app.py 가 소유).
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.preview_btn.click)
        self.bound_table.itemChanged.connect(self._on_bound_edited)

    def _on_bound_edited(self, _item: QTableWidgetItem) -> None:
        """Restart the debounce timer on any bound edit (last edit wins)."""
        self._debounce.start()

    def _remove_selected_bound(self) -> None:
        row = self.bound_table.currentRow()
        if row >= 0:
            self.bound_table.removeRow(row)

    def add_bound(self, reaction_id: str, lower: float, upper: float) -> None:
        r = self.bound_table.rowCount()
        self.bound_table.insertRow(r)
        self.bound_table.setItem(r, 0, QTableWidgetItem(reaction_id))
        self.bound_table.setItem(r, 1, QTableWidgetItem(str(lower)))
        self.bound_table.setItem(r, 2, QTableWidgetItem(str(upper)))

    def constraints(self) -> list[BoundConstraint]:
        """Return parsed bounds. A half-typed number ('-') is recorded, not raised.

        A raw `float()` ValueError used to escape the Qt slot (the debounce fires 500 ms
        after each keystroke), leaving the *previous* run's delta on screen next to the
        newly typed bound. The caller checks `invalid_rows` and refuses to solve.
        """
        out: list[BoundConstraint] = []
        self.invalid_rows = []
        for r in range(self.bound_table.rowCount()):
            rid = self.bound_table.item(r, 0)
            lo = self.bound_table.item(r, 1)
            hi = self.bound_table.item(r, 2)
            if not (rid and rid.text().strip()):
                continue
            try:
                lower = float(lo.text()) if lo else 0.0
                upper = float(hi.text()) if hi else 0.0
            except ValueError:
                self.invalid_rows.append(r + 1)
                continue
            out.append(BoundConstraint(rid.text().strip(), lower, upper))
        return out

    def describe_bound(self, constraint: BoundConstraint) -> str:
        """Human-readable identity of the bound a result belongs to."""
        return f"{constraint.reaction_id} [{constraint.lower:.6g}, {constraint.upper:.6g}]"

    def _provenance_suffix(self, constraint: BoundConstraint | None) -> str:
        """Name the bound a delta was computed for, and flag it if the table has moved on.

        The sandbox became asynchronous, so the user can retype a bound while the solve is
        in flight; without this the delta for the OLD bound would land silently under the
        NEW one. The result is never discarded — it is a real solve — it is just labelled.
        """
        if constraint is None:
            return ""
        suffix = f" · bound: {self.describe_bound(constraint)}"
        current = self.constraints()
        if (
            self.invalid_rows
            or len(current) != 1
            or (
                current[0].reaction_id != constraint.reaction_id
                or current[0].lower != constraint.lower
                or current[0].upper != constraint.upper
            )
        ):
            suffix += " ⚠ the bound table has changed since this preview started"
        return suffix

    def show_preview(self, delta: DeltaResult, constraint: BoundConstraint | None = None) -> None:
        """preview 결과 표시(비기록 — store/run_hash 없음, §8.5)."""
        self.delta_view.load_delta(delta)
        suffix = self._provenance_suffix(constraint)
        if delta.status == "failed":
            self.status.setText(f"preview failed: {delta.diagnostic}{suffix}")
        else:
            n = len(delta.significant())
            self.status.setText(f"preview (not recorded) — changed metabolites: {n}{suffix}")

    def show_commit(
        self, delta: DeltaResult, run_hash: str, constraint: BoundConstraint | None = None
    ) -> None:
        """commit 결과(run_hash 승격 — artifact 기록)."""
        self.delta_view.load_delta(delta)
        self.status.setText(
            f"committed (run_hash {run_hash[:12]}…){self._provenance_suffix(constraint)}"
        )


class ScenarioCompareView(QWidget):
    """Scenario Compare — A vs B(또는 N) delta 표 + growth Δ + 상태."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("Scenario Compare (A → B)")
        self.status = QLabel("Advanced preview: pick two completed run folders, then Compare.")
        run_a_row = QHBoxLayout()
        self.run_a_input = QLineEdit("")
        self.run_a_input.setPlaceholderText("Run A directory (baseline)")
        self.browse_a_btn = QPushButton("Browse A")
        run_a_row.addWidget(QLabel("Run A"))
        run_a_row.addWidget(self.run_a_input)
        run_a_row.addWidget(self.browse_a_btn)
        run_b_row = QHBoxLayout()
        self.run_b_input = QLineEdit("")
        self.run_b_input.setPlaceholderText("Run B directory (modified)")
        self.browse_b_btn = QPushButton("Browse B")
        self.compare_btn = QPushButton("Compare")
        run_b_row.addWidget(QLabel("Run B"))
        run_b_row.addWidget(self.run_b_input)
        run_b_row.addWidget(self.browse_b_btn)
        run_b_row.addWidget(self.compare_btn)
        self.delta_view = DeltaTable()
        self.growth_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.status)
        layout.addLayout(run_a_row)
        layout.addLayout(run_b_row)
        layout.addWidget(self.delta_view)
        layout.addWidget(self.growth_label)

    def load_comparison(self, delta: DeltaResult) -> None:
        """compute_delta(A, B) 결과 표시(동일조건 고정 비교)."""
        self.delta_view.load_delta(delta)
        added = ", ".join(delta.added_members) or "—"
        status = "" if delta.status == "ok" else f" [failed: {delta.diagnostic}]"
        self.growth_label.setText(f"growth Δ: {delta.growth_delta:+.4g} · added: {added}{status}")


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
        # The model pool, not the widget, is the authoritative upper bound.  A hard
        # limit of 20 made the otherwise generic choose-k search impossible to
        # configure for larger consortia (for example choose 30 from a 200-model
        # pool).  Validation against the actual pool happens in the search core.
        self.min_size_spin.setRange(1, 10_000)
        self.min_size_spin.setValue(2)
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 10_000)
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
        self.ko_member_input.setPlaceholderText("Optional member; blank = all")
        self.ko_genes_input = QLineEdit("")
        self.ko_genes_input.setPlaceholderText("Optional gene ids; blank = auto genes")
        self.ko_max_genes_spin = QSpinBox()
        self.ko_max_genes_spin.setRange(0, 10000)
        self.ko_max_genes_spin.setValue(50)
        self.run_ko_btn = QPushButton("Rank Gene KOs")
        ko_row.addWidget(QLabel("Gene KO"))
        ko_row.addWidget(self.ko_members_input)
        ko_row.addWidget(self.ko_member_input)
        ko_row.addWidget(self.ko_genes_input)
        ko_row.addWidget(QLabel("Max genes/member"))
        ko_row.addWidget(self.ko_max_genes_spin)
        ko_row.addWidget(self.run_ko_btn)
        growth_row = QHBoxLayout()
        self.growth_member_input = QLineEdit("")
        self.growth_member_input.setPlaceholderText("Member for ratio sweep, e.g. iML1515")
        self.abundance_fractions_input = QLineEdit("0.1,0.25,0.5,0.75")
        self.abundance_fractions_input.setPlaceholderText("Fractions, e.g. 0.1,0.25,0.5,0.75")
        self.run_growth_btn = QPushButton("Strain Growth")
        self.run_abundance_btn = QPushButton("Ratio Impact")
        growth_row.addWidget(QLabel("Growth/Ratio"))
        growth_row.addWidget(self.growth_member_input)
        growth_row.addWidget(self.abundance_fractions_input)
        growth_row.addWidget(self.run_growth_btn)
        growth_row.addWidget(self.run_abundance_btn)
        self.status = QLabel("")
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(list(SEARCH_COLUMNS))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self.table)
        self.pareto_label = QLabel("")
        self.current_run_dir: Path | None = None
        try:
            from PySide6.QtSvgWidgets import QSvgWidget

            self.figure_view: QWidget = QSvgWidget()
        except ImportError:  # pragma: no cover - optional GUI extra
            try:
                from PySide6.QtWebEngineWidgets import QWebEngineView

                self.figure_view = QWebEngineView()
            except ImportError:
                self.figure_view = QLabel("SVG preview is unavailable.")
        self.figure_placeholder = QLabel("No search result loaded.")
        self.figure_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.figure_stack = QStackedWidget()
        self.figure_stack.setMinimumHeight(320)
        self.figure_stack.addWidget(self.figure_view)
        self.figure_stack.addWidget(self.figure_placeholder)
        self.figure_stack.setCurrentWidget(self.figure_placeholder)
        layout.addWidget(self.title)
        layout.addLayout(pool_row)
        layout.addLayout(controls)
        layout.addLayout(ko_row)
        layout.addLayout(growth_row)
        layout.addWidget(self.status)
        layout.addWidget(self.table)
        layout.addWidget(self.pareto_label)
        layout.addWidget(self.figure_stack)
        # Any edit to an answer-determining input invalidates the displayed ranking: a table
        # computed for pool/target/size A must never sit under inputs that now say B.
        for line_edit in (
            self.model_dir_input,
            self.targets_input,
            self.ko_members_input,
            self.ko_member_input,
            self.ko_genes_input,
            self.growth_member_input,
            self.abundance_fractions_input,
        ):
            line_edit.textChanged.connect(self.invalidate_results)
        for spin in (
            self.min_size_spin,
            self.max_size_spin,
            self.top_k_spin,
            self.ko_max_genes_spin,
        ):
            spin.valueChanged.connect(self.invalidate_results)
        self.strategy_combo.currentTextChanged.connect(self.invalidate_results)
        self.robustness_check.toggled.connect(self.invalidate_results)

    #: which inputs actually determine each Search-tab workflow's answer. Used to tell the
    #: user when an arriving result was computed for a request they have since edited —
    #: scoped per workflow so an irrelevant edit never raises a false alarm.
    REQUEST_FIELDS: dict[str, tuple[str, ...]] = {
        "search": ("pool", "target", "min_size", "max_size", "strategy", "top_k", "fva"),
        "gene_ko": ("pool", "target", "ko_members", "ko_member", "ko_genes", "max_genes", "top_k"),
        "strain_growth": ("pool",),
        "abundance_impact": ("pool", "target", "growth_member", "fractions"),
        "host_search": (),  # driven by the Host tab's own controls, not these
    }

    def request_fields(self, kind: str) -> dict[str, str]:
        """Snapshot the answer-determining inputs for one workflow."""
        snapshot = {
            "pool": self.model_dir_input.text().strip(),
            "target": self.targets_input.text().strip(),
            "min_size": str(self.min_size_spin.value()),
            "max_size": str(self.max_size_spin.value()),
            "strategy": self.strategy_combo.currentText(),
            "top_k": str(self.top_k_spin.value()),
            "fva": str(self.robustness_check.isChecked()),
            "ko_members": self.ko_members_input.text().strip(),
            "ko_member": self.ko_member_input.text().strip(),
            "ko_genes": self.ko_genes_input.text().strip(),
            "max_genes": str(self.ko_max_genes_spin.value()),
            "growth_member": self.growth_member_input.text().strip(),
            "fractions": self.abundance_fractions_input.text().strip(),
        }
        return {k: snapshot[k] for k in self.REQUEST_FIELDS.get(kind, ())}

    def superseded_note(self, requested: dict[str, str], kind: str) -> str:
        """Describe how the inputs on screen have moved away from a completed request.

        Invalidation only covers the *idle* case. A search that is already solving keeps its
        result, so on completion the numbers for the OLD inputs would repopulate the table
        under the NEW ones with nothing to say so. The run is real and stays on screen — it
        is labelled, not discarded.
        """
        current = self.request_fields(kind)
        changed = [
            (key, was, current[key])
            for key, was in requested.items()
            if key in current and current[key] != was
        ]
        if not changed:
            return ""
        detail = "; ".join(f"{key}: {was} → {now}" for key, was, now in changed)
        return (
            f" ⚠ computed for a superseded request ({detail}) — "
            f"the inputs on screen have changed since; re-run to match them"
        )

    def invalidate_results(self, *_args: object) -> None:
        """Drop the displayed ranking when the request that produced it no longer applies."""
        if self.table.rowCount() == 0 and self.current_run_dir is None:
            return
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(list(SEARCH_COLUMNS))
        self.pareto_label.setText("")
        self.current_run_dir = None
        self.figure_stack.setCurrentWidget(self.figure_placeholder)
        self.status.setText("Inputs changed — previous result cleared; re-run to update.")

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
        if (
            self.current_run_dir is not None
            and (self.current_run_dir / "strain_growth_plot.svg").exists()
        ):
            return "strain_growth_plot.svg"
        if (
            self.current_run_dir is not None
            and (self.current_run_dir / "abundance_impact_plot.svg").exists()
        ):
            return "abundance_impact_plot.svg"
        mapping = {"Ranking": "search_plot.svg", "Scatter": "search_scatter.svg"}
        return mapping[self.figure_mode_combo.currentText()]

    def refresh_figure_mode(self, _mode: str | None = None) -> None:
        """Load the selected saved search SVG into the preview pane."""
        if self.current_run_dir is None:
            return
        artifact = self.current_run_dir / self.selected_figure_artifact()
        if not artifact.exists():
            return
        self.figure_stack.setCurrentWidget(self.figure_view)
        if hasattr(self.figure_view, "load"):
            self.figure_view.load(str(artifact))
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

    def load_summary(
        self,
        summary: dict[str, object],
        *,
        run_dir: Path | None = None,
        request_note: str = "",
    ) -> None:
        """search_advanced_summary.json 형태를 표로 표시.

        `request_note` names the request the numbers belong to when the user has edited the
        inputs while the run was in flight (see `superseded_note`).
        """
        self.current_run_dir = None if run_dir is None else run_dir.resolve()
        labels = summary.get("column_labels")
        headers = (
            [str(x) for x in labels]
            if isinstance(labels, list) and len(labels) == self.table.columnCount()
            else list(SEARCH_COLUMNS)
        )
        self.table.setHorizontalHeaderLabels(headers)
        strategy = str(summary.get("strategy", ""))
        warnings = summary.get("warnings")
        warning_list = [str(w) for w in warnings] if isinstance(warnings, list) else []
        status_text = f"strategy: {strategy}"
        if warning_list:
            # Never a bare count: the CLI's warning text is the scientific caveat itself.
            status_text += f" · warnings: {len(warning_list)} — {warning_list[0]}"
        ranked = summary.get("top_ranked", {})
        rows: list[tuple[str, str, float | None, float | None, float | None, str, str]] = []
        diagnostics: list[object] = []
        if isinstance(ranked, dict):
            groups = [
                (str(target), items) for target, items in ranked.items() if isinstance(items, list)
            ]
        elif isinstance(ranked, list):
            groups = [(str(summary.get("target", "")), ranked)]
        else:
            groups = []
        for target, items in groups:
            for item in items:
                if not isinstance(item, dict):
                    continue
                members = item.get("members", [])
                score = _optional_float(item.get("score"))
                target_flux = _optional_float(item.get("target_flux"))
                growth = _optional_float(item.get("community_growth"))
                aux = item.get("aux_text")
                aux_text = _fva_range_text(item) if aux is None else str(aux)
                diagnostic = item.get("diagnostic")
                diagnostics.append(diagnostic)
                status = str(item.get("status", "ok"))
                if diagnostic:
                    # The CSV/JSON carry the diagnostic; the table used to print a bare
                    # "optimal" for a row whose flux stage had actually failed.
                    status = f"{status} ⚠ diagnostic"
                rows.append(
                    (
                        "+".join(str(x) for x in members) if isinstance(members, list) else "",
                        target,
                        score,
                        # No fallback to `score`: a missing target_flux renders as "—" like every
                        # other missing value, never as a different quantity wearing its label.
                        target_flux,
                        growth,
                        aux_text,
                        status,
                    )
                )
        n_flagged = sum(1 for d in diagnostics if d)
        if n_flagged:
            status_text += f" · {n_flagged} row(s) carry a solver diagnostic"
        self.status.setText(status_text + request_note)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            diagnostic = diagnostics[r]
            tooltip = "" if not diagnostic else _diagnostic_text(diagnostic)
            for c, value in enumerate(row):
                text = (
                    "—"
                    if value is None
                    else f"{value:.4g}"
                    if isinstance(value, float)
                    else str(value)
                )
                item_widget = read_only_item(text)
                if diagnostic:
                    item_widget.setForeground(_DIAGNOSTIC_COLOR)
                    item_widget.setToolTip(tooltip)
                self.table.setItem(r, c, item_widget)
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


def _diagnostic_text(diagnostic: object) -> str:
    """Render a structured Diagnostic (or free text) for a table tooltip, losslessly enough
    that the researcher can see *why* the row is flagged without opening the CSV."""
    if isinstance(diagnostic, dict):
        code = diagnostic.get("code", "diagnostic")
        message = diagnostic.get("message") or diagnostic.get("detail") or ""
        return f"{code}: {message}".strip().rstrip(":")
    return str(diagnostic)


def _fva_range_text(item: dict[object, object]) -> str:
    lo = _optional_float(item.get("robustness_fva_lo"))
    hi = _optional_float(item.get("robustness_fva_hi"))
    status = item.get("robustness_status")
    if lo is not None and hi is not None:
        return f"{lo:.4g}..{hi:.4g}"
    return "" if status is None else str(status)
