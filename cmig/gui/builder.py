"""GUI Builder/Compare — Community Builder · Constraint Sandbox · Scenario Compare (Phase 2, §11).

Design Ref: §11 / §10 G1 Sandbox / cmig-gui-builder.design. Plan SC: SC-CB1~CB3·CS1~CS3·SC1~SC3.

테이블 기반(offscreen 클린). CommunityBuilderView=멤버/abundance/tradeoff 구성,
ConstraintSandboxView=bound 제약+preview/commit(JobRunner debounce re-solve),
DeltaTable=core.delta.DeltaResult 표시(significant 강조·실패 명시), ScenarioCompareView=A/B delta.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
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
from cmig.core.targets import TARGET_PRESETS, preset_targets
from cmig.gui.analysis_page import AnalysisPage
from cmig.gui.pickers import MediumPicker, ModelPicker
from cmig.gui.search_results import (
    MERGE_MEDIUM_WARNING,
    SEARCH_COLUMNS,
    SearchResultsPanel,
    _matching_evaluation,
    make_read_only,
    medium_mode_text,
    read_only_item,
    validate_search_summary,
)

# The result-table helpers moved to cmig.gui.search_results; these names stay importable from
# here, and the explicit __all__ entries make them public re-exports for strict mypy.
__all__ = [
    "MERGE_MEDIUM_WARNING",
    "SEARCH_COLUMNS",
    "_matching_evaluation",
    "make_read_only",
    "medium_mode_text",
    "read_only_item",
    "validate_search_summary",
]

#: The four `--direction` / `--target-directions` choices of `cmig search`, in CLI order.
TARGET_DIRECTIONS = ("max_secretion", "min_secretion", "max_uptake", "min_uptake")
#: Multi-target metrics whose score uses the per-target weights (`--target-weights`).
WEIGHTED_METRICS = ("normalized_weighted", "carbon_equivalent", "raw_sum")
REFERENCE_WARNING = (
    "If the search runs as GA or random, normalized_weighted needs a Reference for every "
    "target."
)


class CommunityBuilderView(AnalysisPage):
    """Community Solve: the picked members are the table's rows; only abundances are edited."""

    def __init__(self) -> None:
        super().__init__(
            "Community Solve",
            "Community FBA of the selected members. Abundances start at 1; edit them in the "
            "table.",
            run_text="Run Community",
            cancel=False,
        )
        self.model_picker = ModelPicker("Members")
        # `cmig solve` refuses to run without an explicit namespace decision. Mirror that gate
        # here instead of failing at rc=2 with the real reason hidden on the process's stdout.
        self.assume_bigg_check = QCheckBox(
            "I reviewed these models and confirm they are already in BiGG namespace"
        )
        self.namespace_decisions_input = QLineEdit("")
        self.namespace_decisions_input.setPlaceholderText(
            "…or a reviewed namespace-decisions JSON file"
        )
        self.browse_namespace_decisions_btn = QPushButton("Decisions")
        self.namespace_note = QLabel("")
        self.namespace_note.setWordWrap(True)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Member", "Abundance"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMaximumHeight(220)
        #: rows whose abundance could not be parsed on the last members() call
        self.invalid_rows: list[int] = []
        self.add_input_row(self.model_picker)
        self.inputs.addWidget(self.table)
        self.add_input_row(self.assume_bigg_check)
        self.add_input_row(self.namespace_decisions_input, self.browse_namespace_decisions_btn)
        self.inputs.addWidget(self.namespace_note)
        # tradeoff f 슬라이더 (0..1, 0.01 step → 0..100)
        self.f_label = QLabel("tradeoff f: 0.50")
        self.f_slider = QSlider(Qt.Orientation.Horizontal)
        self.f_slider.setRange(1, 100)
        self.f_slider.setValue(50)
        self.f_slider.valueChanged.connect(self._on_f)
        self.advanced.add_row(self.f_label, self.f_slider)
        self.advanced.track(self.f_slider)
        self.model_picker.selection_changed.connect(self._sync_rows)
        # A shown result describes the inputs it ran with; any later change makes it stale.
        self.model_picker.selection_changed.connect(self.invalidate_results)
        self.table.itemChanged.connect(self.invalidate_results)
        self.f_slider.valueChanged.connect(self.invalidate_results)
        self.register("members", self.model_picker)
        self.register_custom("abundances", self.members_snapshot, self._restore_abundances)
        self.register_custom("tradeoff", lambda: self.f_slider.value(), self._restore_tradeoff)
        self.register("assume_bigg", self.assume_bigg_check)
        self.register("namespace_decisions", self.namespace_decisions_input)
        self._sync_rows()

    def _on_f(self, v: int) -> None:
        self.f_label.setText(f"tradeoff f: {v / 100:.2f}")

    def _sync_rows(self) -> None:
        """One row per picked member; a member that stays picked keeps its abundance."""
        kept: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            member, value = self.table.item(row, 0), self.table.item(row, 1)
            if member is not None and value is not None:
                kept[member.text()] = value.text()
        chosen = self.model_picker.selected_ids()
        self.table.setRowCount(len(chosen))
        for row, member_id in enumerate(chosen):
            self.table.setItem(row, 0, read_only_item(member_id))
            self.table.setItem(row, 1, QTableWidgetItem(kept.get(member_id, "1")))

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

    def invalidate_results(self, *_args: object) -> None:
        if not self.results.has_results():
            return
        self.results.show_empty()
        self.status.setText("Inputs changed — previous result cleared; re-run to update.")

    def _commit_open_editor(self) -> None:
        """An abundance still being typed is the one on screen, so it is the one that runs.

        Run Community (and ⌘R) does not take focus on macOS, so the cell editor is not
        committed by the click itself.
        """
        if self.table.state() != QAbstractItemView.State.EditingState:
            return
        for editor in self.table.viewport().findChildren(QLineEdit):
            self.table.commitData(editor)
            self.table.closeEditor(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def set_abundance(self, member_id: str, value: float) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.text() == member_id:
                self.table.setItem(row, 1, QTableWidgetItem(f"{value:g}"))
                return
        raise KeyError(f"{member_id!r} is not a selected member")

    def members(self) -> dict[str, float]:
        """Return member→abundance for every row. Unparseable rows are recorded, never skipped.

        Silently dropping a row the user typed would run a *different* community than the
        one on screen, so `invalid_rows` is populated and the caller must refuse to run.
        """
        self._commit_open_editor()
        out: dict[str, float] = {}
        self.invalid_rows = []
        for r in range(self.table.rowCount()):
            mid = self.table.item(r, 0)
            ab = self.table.item(r, 1)
            if mid is None:
                continue
            try:
                out[mid.text()] = float(ab.text()) if ab else 1.0
            except ValueError:
                self.invalid_rows.append(r + 1)
        return out

    def members_snapshot(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for row in range(self.table.rowCount()):
            member, value = self.table.item(row, 0), self.table.item(row, 1)
            if member is not None and value is not None:
                out[member.text()] = value.text()
        return out

    def _restore_abundances(self, values: object) -> str | None:
        if not isinstance(values, dict):
            return "abundances could not be restored"
        for row in range(self.table.rowCount()):
            member = self.table.item(row, 0)
            if member is not None and member.text() in values:
                self.table.setItem(row, 1, QTableWidgetItem(str(values[member.text()])))
        return None

    def _restore_tradeoff(self, value: object) -> str | None:
        try:
            self.f_slider.setValue(int(value))  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return "tradeoff f could not be restored"
        return None


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

    #: the debounce after a bound edit expired: an automatic preview, not a Preview click
    auto_preview_requested = Signal()

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
        # 타이머 만료 시 auto_preview_requested 를 내보내 app.py 가 preview 를 실행한다. 명시적
        # Preview 클릭과 구분해야 자동 preview 가 화면을 바꾸지 않는다(뷰는 Qt 전용 —
        # JobRunner/EngineService 는 app.py 가 소유).
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.auto_preview_requested.emit)
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


class SearchView(AnalysisPage):
    """Combination Search — ranked candidates + Pareto/strategy warnings."""

    def __init__(self) -> None:
        super().__init__(
            "Combination Search", "Rank model combinations by a target metabolite.",
            run_text="Run Search",
        )
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        # Per-target rows replace the old comma box + shared Direction + References inputs:
        # every row carries its own direction, weight and fixed reference, exactly like the
        # CLI's --targets/--target-directions/--target-weights/--target-scales.
        self.target_table = QTableWidget(0, 4)
        self.target_table.setHorizontalHeaderLabels(["Target", "Direction", "Weight", "Reference"])
        self.target_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.target_table.setMaximumHeight(150)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.add_target_btn = QPushButton("Add target")
        self.remove_target_btn = QPushButton("Remove selected")
        self.add_target_btn.clicked.connect(lambda: self.add_target_row(""))
        self.remove_target_btn.clicked.connect(self._remove_selected_target)
        self.target_preset_combo = QComboBox()
        self.target_preset_combo.addItem("Fill from preset…", "")
        for preset in sorted(TARGET_PRESETS):
            self.target_preset_combo.addItem(preset, preset)
        self.target_preset_combo.activated.connect(self._fill_from_preset)
        self.multi_metric_combo = QComboBox()
        self.multi_metric_combo.addItems([
            "normalized_weighted", "carbon_equivalent", "raw_sum", "pareto",
        ])
        self.multi_metric_label = QLabel("Multi-target metric")
        target_btn_row = QHBoxLayout()
        target_btn_row.addWidget(self.add_target_btn)
        target_btn_row.addWidget(self.remove_target_btn)
        target_btn_row.addWidget(self.target_preset_combo)
        target_btn_row.addWidget(self.multi_metric_label)
        target_btn_row.addWidget(self.multi_metric_combo)
        target_btn_row.addStretch(1)
        target_note = QLabel(
            "Each row is a target. Weight and Reference apply when there are two or more rows."
        )
        target_note.setWordWrap(True)
        self.weight_note = QLabel("Weights do not affect Pareto ranking.")
        self.weight_note.setWordWrap(True)
        self.weight_note.setVisible(False)
        self.reference_warning_label = QLabel("")
        self.reference_warning_label.setWordWrap(True)
        self.reference_warning_label.setVisible(False)
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
        # Search top-k: CLI default 10; 0 is refused by the CLI, so the floor is 1 and there
        # is no artificial ceiling.
        self.search_top_k_spin = QSpinBox()
        self.search_top_k_spin.setRange(1, 2_147_483_647)
        self.search_top_k_spin.setValue(10)
        self.robustness_check = QCheckBox("FVA")
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 2_000_000_000)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 32)
        self.growth_fraction_spin = QDoubleSpinBox()
        self.growth_fraction_spin.setRange(0.001, 1.0)
        self.growth_fraction_spin.setDecimals(3)
        self.growth_fraction_spin.setValue(0.5)
        self.min_member_growth_spin = QDoubleSpinBox()
        self.min_member_growth_spin.setRange(0, 100)
        self.min_member_growth_spin.setDecimals(5)
        # Medium mode lives in the collapsed advanced box; this line keeps the exact/merge
        # choice visible on screen at all times.
        self.medium_mode_summary = QLabel("")
        self.medium_mode_summary.setWordWrap(True)
        self.checkpoint_input = QLineEdit("")
        self.checkpoint_input.setPlaceholderText("Checkpoint JSON path")
        self.browse_checkpoint_btn = QPushButton("Browse")
        self.resume_check = QCheckBox("Resume")
        self.validation_top_spin = QSpinBox()
        self.validation_top_spin.setRange(0, 100)
        self.validation_top_spin.setSpecialValueText("Off")
        self.min_community_growth_spin = QDoubleSpinBox()
        self.min_community_growth_spin.setRange(0, 1000)
        self.min_community_growth_spin.setDecimals(6)
        self.solve_timeout_spin = QSpinBox()
        self.solve_timeout_spin.setRange(0, 86400)
        self.solve_timeout_spin.setSpecialValueText("No limit")
        self.add_input_row(self.model_picker, "Medium", self.medium_picker)
        self.inputs.addWidget(self.medium_mode_summary)
        self.inputs.addWidget(target_note)
        self.inputs.addWidget(self.target_table)
        self.inputs.addLayout(target_btn_row)
        self.inputs.addWidget(self.weight_note)
        self.inputs.addWidget(self.reference_warning_label)
        self.add_input_row("Size", self.min_size_spin, "to", self.max_size_spin)
        self.advanced.add_row("Strategy", self.strategy_combo, "Top K", self.search_top_k_spin,
                              self.robustness_check)
        self.advanced.add_row("Seed", self.seed_spin, "Workers", self.workers_spin)
        self.advanced.add_row("Growth fraction", self.growth_fraction_spin,
                              "Member growth ≥", self.min_member_growth_spin,
                              "Community growth ≥", self.min_community_growth_spin)
        self.advanced.add_row("Validate top (extra solves)", self.validation_top_spin,
                              "Per-solve timeout (s)", self.solve_timeout_spin)
        self.advanced.add_row("Checkpoint", self.checkpoint_input, self.browse_checkpoint_btn,
                              self.resume_check)
        self._build_advanced_settings()
        self.advanced.track(
            self.strategy_combo, self.search_top_k_spin, self.robustness_check, self.seed_spin,
            self.workers_spin, self.growth_fraction_spin, self.min_member_growth_spin,
            self.min_community_growth_spin, self.validation_top_spin, self.solve_timeout_spin,
            self.checkpoint_input, self.resume_check, self.exhaustive_max_spin,
            self.n_samples_spin, self.ga_pop_size_spin, self.ga_generations_spin,
            self.ga_mutation_rate_spin, self.ga_immigrant_fraction_spin,
            self.ga_tournament_k_spin, self.ga_elitism_spin, self.ga_budget_spin,
            self.ga_patience_spin, self.ga_restart_after_spin,
            self.ga_local_search_fraction_spin, self.ga_preserve_common_check,
            self.solver_threads_spin, self.pareto_resolution_spin, self.medium_mode_combo,
            self.allow_unknown_medium_check,
        )
        self.results_panel = SearchResultsPanel(self.request_fields, status=self.status,
                                                area=self.results)
        self.results.add(self.results_panel, 1)
        panel = self.results_panel
        self.status: QLabel = panel.status
        self.details: QPlainTextEdit = panel.details
        self.table: QTableWidget = panel.table
        self.pareto_label: QLabel = panel.pareto_label
        self.inspector_label: QLabel = panel.inspector_label
        self.inspector: QPlainTextEdit = panel.inspector
        self.figure_mode_combo: QComboBox = panel.figure_mode_combo
        self.export_figure_btn: QPushButton = panel.export_figure_btn
        self.figure_view: QWidget = panel.figure_view
        self.figure_placeholder: QLabel = panel.figure_placeholder
        self.figure_stack: QStackedWidget = panel.figure_stack
        # The CLI's own default request: one row, `--target but --direction max_secretion`.
        self.add_target_row("but")
        # Any edit to an answer-determining input invalidates the displayed ranking: a table
        # computed for pool/target/size A must never sit under inputs that now say B.
        self.checkpoint_input.textChanged.connect(self.invalidate_results)
        for spin in (
            self.min_size_spin,
            self.max_size_spin,
            self.search_top_k_spin,
            self.seed_spin,
            self.workers_spin,
            self.growth_fraction_spin,
            self.min_member_growth_spin,
            self.min_community_growth_spin,
            self.validation_top_spin,
            self.solve_timeout_spin,
            self.exhaustive_max_spin,
            self.n_samples_spin,
            self.ga_pop_size_spin,
            self.ga_generations_spin,
            self.ga_mutation_rate_spin,
            self.ga_immigrant_fraction_spin,
            self.ga_tournament_k_spin,
            self.ga_elitism_spin,
            self.ga_budget_spin,
            self.ga_patience_spin,
            self.ga_restart_after_spin,
            self.ga_local_search_fraction_spin,
            self.solver_threads_spin,
            self.pareto_resolution_spin,
        ):
            spin.valueChanged.connect(self.invalidate_results)
        for check in (
            self.robustness_check,
            self.resume_check,
            self.ga_preserve_common_check,
            self.allow_unknown_medium_check,
        ):
            check.toggled.connect(self.invalidate_results)
        for combo in (
            self.strategy_combo,
            self.multi_metric_combo,
            self.medium_mode_combo,
        ):
            combo.currentTextChanged.connect(self.invalidate_results)
        # The model and medium choice determine the answer like any other input. Passing an
        # argument makes the invalidation compare the request, so a picker rebuild that keeps
        # the same choice never clears a result.
        self.model_picker.selection_changed.connect(lambda: self.invalidate_results(True))
        self.medium_picker.currentIndexChanged.connect(self.invalidate_results)
        self.target_table.itemChanged.connect(self._on_target_item_changed)
        self.multi_metric_combo.currentTextChanged.connect(self._refresh_target_notes)
        self.strategy_combo.currentTextChanged.connect(self._refresh_target_notes)
        self.medium_picker.currentIndexChanged.connect(self._refresh_medium_notes)
        self.medium_mode_combo.currentIndexChanged.connect(self._refresh_medium_notes)
        self.allow_unknown_medium_check.toggled.connect(self._refresh_medium_notes)
        self._refresh_target_notes()
        self._refresh_medium_notes()
        # Inputs a reopened run restores, the model picker first.
        self.register("models", self.model_picker)
        self.register("medium", self.medium_picker)
        self.register_custom("targets", lambda: [list(r) for r in self.target_rows()],
                             self._restore_targets)
        for name, widget in (
            ("multi_metric", self.multi_metric_combo), ("min_size", self.min_size_spin),
            ("max_size", self.max_size_spin), ("strategy", self.strategy_combo),
            ("top_k", self.search_top_k_spin), ("fva", self.robustness_check),
            ("seed", self.seed_spin), ("workers", self.workers_spin),
            ("growth_fraction", self.growth_fraction_spin),
            ("min_member_growth", self.min_member_growth_spin),
            ("min_community_growth", self.min_community_growth_spin),
            ("validate_top", self.validation_top_spin), ("timeout", self.solve_timeout_spin),
            ("checkpoint", self.checkpoint_input), ("resume", self.resume_check),
            ("exhaustive_max", self.exhaustive_max_spin), ("n_samples", self.n_samples_spin),
            ("ga_pop_size", self.ga_pop_size_spin), ("ga_generations", self.ga_generations_spin),
            ("ga_mutation_rate", self.ga_mutation_rate_spin),
            ("ga_immigrant_fraction", self.ga_immigrant_fraction_spin),
            ("ga_tournament_k", self.ga_tournament_k_spin), ("ga_elitism", self.ga_elitism_spin),
            ("ga_budget", self.ga_budget_spin), ("ga_patience", self.ga_patience_spin),
            ("ga_restart_after", self.ga_restart_after_spin),
            ("ga_local_search_fraction", self.ga_local_search_fraction_spin),
            ("ga_preserve_common", self.ga_preserve_common_check),
            ("solver_threads", self.solver_threads_spin),
            ("pareto_resolution", self.pareto_resolution_spin),
            ("medium_mode", self.medium_mode_combo),
            ("allow_unknown_medium", self.allow_unknown_medium_check),
        ):
            self.register(name, widget)

    def _restore_targets(self, rows: object) -> str | None:
        try:
            self.set_target_rows([tuple(str(cell) for cell in row) for row in rows])  # type: ignore[attr-defined]
        except (TypeError, ValueError) as exc:
            return f"targets could not be restored ({exc})"
        return None

    def _build_advanced_settings(self) -> None:
        """The strategy, GA, solver and medium-mode rows of the Advanced options section.

        Defaults equal the `cmig search` parser / `GAConfig` defaults. An option whose
        applicability condition does not hold on screen (e.g. GA options with the exhaustive
        strategy) is left out of the argv by the caller.
        """
        self.advanced_toggle = self.advanced.toggle
        self.advanced_box = self.advanced.body
        box = self.advanced.body_layout

        def note(text: str) -> QLabel:
            label = QLabel(text)
            label.setWordWrap(True)
            return label

        def int_spin(low: int, high: int, value: int, off: str = "") -> QSpinBox:
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(value)
            if off:
                spin.setSpecialValueText(off)
            return spin

        def float_spin(value: float, high: float = 1.0) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, high)
            spin.setDecimals(3)
            spin.setSingleStep(0.05)
            spin.setValue(value)
            return spin

        # Strategy-specific limits.
        self.exhaustive_max_spin = int_spin(1, 2_000_000_000, 100)
        self.n_samples_spin = int_spin(1, 2_000_000_000, 100)
        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel("Exhaustive max (auto only)"))
        strategy_row.addWidget(self.exhaustive_max_spin)
        strategy_row.addWidget(QLabel("Samples (random only)"))
        strategy_row.addWidget(self.n_samples_spin)
        strategy_row.addStretch(1)
        box.addLayout(strategy_row)

        # GA options (GAConfig defaults).
        from cmig.core.search_ga import GAConfig

        ga = GAConfig()
        self.ga_pop_size_spin = int_spin(1, 1_000_000, ga.pop_size)
        self.ga_generations_spin = int_spin(1, 1_000_000, ga.generations)
        self.ga_mutation_rate_spin = float_spin(ga.mutation_rate)
        self.ga_immigrant_fraction_spin = float_spin(ga.immigrant_fraction)
        self.ga_tournament_k_spin = int_spin(1, 1_000_000, ga.tournament_k)
        self.ga_elitism_spin = int_spin(0, 1_000_000, ga.elitism)
        self.ga_budget_spin = int_spin(0, 2_000_000_000, 0, "Generation limit only")
        self.ga_patience_spin = int_spin(0, 1_000_000, 0, "Off")
        self.ga_restart_after_spin = int_spin(0, 1_000_000, 0, "Off")
        self.ga_local_search_fraction_spin = float_spin(ga.local_search_fraction)
        self.ga_preserve_common_check = QCheckBox("Preserve shared members (experimental)")
        self.ga_preserve_common_check.setChecked(ga.preserve_common)
        box.addWidget(note(
            "GA options — apply only when the strategy is ga, or auto falls back to GA."
        ))
        ga_grid = QGridLayout()
        ga_fields: tuple[tuple[str, QWidget], ...] = (
            ("Population", self.ga_pop_size_spin),
            ("Generations", self.ga_generations_spin),
            ("Mutation rate", self.ga_mutation_rate_spin),
            ("Immigrant fraction", self.ga_immigrant_fraction_spin),
            ("Tournament k", self.ga_tournament_k_spin),
            ("Elitism", self.ga_elitism_spin),
            ("Max evaluations", self.ga_budget_spin),
            ("Patience", self.ga_patience_spin),
            ("Restart after", self.ga_restart_after_spin),
            ("Local search fraction", self.ga_local_search_fraction_spin),
        )
        for index, (label, widget) in enumerate(ga_fields):
            row, column = divmod(index, 2)
            ga_grid.addWidget(QLabel(label), row, column * 2)
            ga_grid.addWidget(widget, row, column * 2 + 1)
        ga_grid.addWidget(self.ga_preserve_common_check, len(ga_fields) // 2, 0, 1, 4)
        box.addLayout(ga_grid)

        # Solver threads and Pareto resolution.
        self.solver_threads_spin = int_spin(1, 1024, 1)
        self.pareto_resolution_spin = int_spin(2, 1_000_000, 5)
        solver_row = QHBoxLayout()
        solver_row.addWidget(QLabel("Solver threads per worker"))
        solver_row.addWidget(self.solver_threads_spin)
        solver_row.addWidget(QLabel("Pareto resolution (pareto metric only)"))
        solver_row.addWidget(self.pareto_resolution_spin)
        solver_row.addStretch(1)
        box.addLayout(solver_row)

        # Medium mode and unknown-medium relaxation (Search only).
        self.medium_mode_combo = QComboBox()
        self.medium_mode_combo.addItem("exact", "exact")
        self.medium_mode_combo.addItem("merge", "merge")
        self.allow_unknown_medium_check = QCheckBox("Allow unknown medium metabolites")
        medium_row = QHBoxLayout()
        medium_row.addWidget(QLabel("Medium mode"))
        medium_row.addWidget(self.medium_mode_combo)
        medium_row.addWidget(self.allow_unknown_medium_check)
        medium_row.addStretch(1)
        box.addLayout(medium_row)
        self.medium_mode_note = note("")
        self.allow_unknown_note = note(
            "Unknown medium metabolites are dropped and named in warnings; the run is "
            "reported as degraded."
        )
        box.addWidget(self.medium_mode_note)
        box.addWidget(self.allow_unknown_note)
        box.addWidget(note(
            "Medium mode and unknown-medium apply to Search only; Gene KO, Strain Growth "
            "and Ratio Impact always use exact medium."
        ))

    def _refresh_medium_notes(self, *_args: object) -> None:
        if not self.medium_picker.current_ref():
            self.medium_mode_note.setText(
                "Medium mode is not applied: no medium file is set (model default medium)."
            )
        elif self.medium_mode_combo.currentData() == "merge":
            self.medium_mode_note.setText(MERGE_MEDIUM_WARNING)
        else:
            self.medium_mode_note.setText(
                "exact: the medium file is the complete set of mass sources."
            )
        self.allow_unknown_note.setVisible(self.allow_unknown_medium_check.isChecked())
        self.medium_mode_summary.setText(
            "Search " + medium_mode_text(self.medium_picker.current_ref(),
                                         str(self.medium_mode_combo.currentData()))
        )

    # ------------------------------------------------------------------ target rows

    def target_direction_combo(self, row: int) -> QComboBox:
        widget = self.target_table.cellWidget(row, 1)
        if not isinstance(widget, QComboBox):
            raise IndexError(f"no target row {row}")
        return widget

    def add_target_row(
        self,
        target: str = "",
        direction: str = "max_secretion",
        weight: str = "1",
        reference: str = "",
    ) -> int:
        """Append one target row (default direction max_secretion, weight 1, no reference)."""
        if direction not in TARGET_DIRECTIONS:
            raise ValueError(f"unknown direction: {direction}")
        row = self.target_table.rowCount()
        self.target_table.blockSignals(True)
        try:
            self.target_table.insertRow(row)
            self.target_table.setItem(row, 0, QTableWidgetItem(target))
            self.target_table.setItem(row, 2, QTableWidgetItem(weight))
            self.target_table.setItem(row, 3, QTableWidgetItem(reference))
        finally:
            self.target_table.blockSignals(False)
        combo = QComboBox()
        combo.addItems(list(TARGET_DIRECTIONS))
        combo.setCurrentText(direction)
        combo.currentTextChanged.connect(self.invalidate_results)
        self.target_table.setCellWidget(row, 1, combo)
        self._targets_changed()
        return row

    def set_target_rows(self, rows: Sequence[str | Sequence[str]]) -> None:
        """Replace the table; each row is a target or (target, direction, weight, reference)."""
        self.target_table.setRowCount(0)
        for row in rows:
            if isinstance(row, str):
                self.add_target_row(row)
            else:
                self.add_target_row(*row)
        self._targets_changed()

    def target_rows(self) -> list[tuple[str, str, str, str]]:
        """Raw (target, direction, weight, reference) text per row, in table order."""
        out: list[tuple[str, str, str, str]] = []
        for row in range(self.target_table.rowCount()):
            cells = []
            for column in (0, 2, 3):
                item = self.target_table.item(row, column)
                cells.append("" if item is None else item.text().strip())
            out.append((cells[0], self.target_direction_combo(row).currentText(),
                        cells[1], cells[2]))
        return out

    def _remove_selected_target(self) -> None:
        row = self.target_table.currentRow()
        if row >= 0:
            self.target_table.removeRow(row)
            self._targets_changed()

    def _fill_from_preset(self, index: int) -> None:
        name = str(self.target_preset_combo.itemData(index) or "")
        if not name:
            return
        self.set_target_rows(preset_targets(name))
        self.target_preset_combo.setCurrentIndex(0)

    def _on_target_item_changed(self, _item: QTableWidgetItem) -> None:
        self._refresh_target_notes()
        self.invalidate_results(_item)

    def _targets_changed(self) -> None:
        self._refresh_target_notes()
        self.invalidate_results(True)

    def _refresh_target_notes(self, *_args: object) -> None:
        # FVA robustness is a single-target option; with 2+ rows it is not passed.
        single = self.target_table.rowCount() <= 1
        self.robustness_check.setEnabled(single)
        self.robustness_check.setToolTip("" if single else "FVA is single-target only")
        weighted = self.multi_metric_combo.currentText() in WEIGHTED_METRICS
        self.weight_note.setVisible(not weighted)
        self.target_table.blockSignals(True)
        try:
            for row in range(self.target_table.rowCount()):
                item = self.target_table.item(row, 2)
                if item is None:
                    continue
                flags = item.flags()
                if weighted:
                    flags |= Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable
                else:
                    flags &= ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable)
                item.setFlags(flags)
        finally:
            self.target_table.blockSignals(False)
        warning = self.reference_warning()
        self.reference_warning_label.setText(warning)
        self.reference_warning_label.setVisible(bool(warning))
        multi = self.target_table.rowCount() >= 2
        self.multi_metric_label.setVisible(multi)
        self.multi_metric_combo.setVisible(multi)

    def reference_warning(self) -> str:
        """Pre-run warning (never a block): normalized_weighted without References.

        The GUI does not count combinations, so it cannot know whether `auto` will fall back
        to GA; the CLI makes that call and reports its own error if References are needed.
        """
        rows = self.target_rows()
        if (
            len(rows) >= 2
            and self.multi_metric_combo.currentText() == "normalized_weighted"
            and self.strategy_combo.currentText() in ("auto", "ga", "random")
            and not any(row[3] for row in rows)
        ):
            return REFERENCE_WARNING
        return ""

    #: which inputs actually determine each Search-tab workflow's answer. Used to tell the
    #: user when an arriving result was computed for a request they have since edited —
    #: scoped per workflow so an irrelevant edit never raises a false alarm.
    REQUEST_FIELDS: dict[str, tuple[str, ...]] = {
        "search": ("models", "target", "direction", "target_weights", "target_scales",
                   "min_size", "max_size", "strategy", "top_k", "fva", "medium",
                   "medium_mode", "allow_unknown_medium", "seed", "workers",
                   "solver_threads", "growth_fraction", "min_member_growth", "multi_metric",
                   "pareto_resolution", "exhaustive_max", "n_samples", "ga_pop_size",
                   "ga_generations", "ga_mutation_rate", "ga_immigrant_fraction",
                   "ga_tournament_k", "ga_elitism", "ga_budget", "ga_patience",
                   "ga_restart_after", "ga_local_search_fraction", "ga_preserve_common",
                   "checkpoint", "resume", "min_community_growth", "validate_top", "timeout"),
        "host_search": (),  # driven by the Host tab's own controls, not these
    }

    def request_fields(self, kind: str) -> dict[str, str]:
        """Snapshot the answer-determining inputs for one workflow."""
        rows = self.target_rows()
        snapshot = {
            "models": ",".join(self.model_picker.selected_ids()),
            "target": ",".join(row[0] for row in rows),
            "direction": ",".join(row[1] for row in rows),
            "target_weights": ",".join(row[2] for row in rows),
            "target_scales": ",".join(row[3] for row in rows),
            "min_size": str(self.min_size_spin.value()),
            "max_size": str(self.max_size_spin.value()),
            "strategy": self.strategy_combo.currentText(),
            "top_k": str(self.search_top_k_spin.value()),
            "fva": str(self.robustness_check.isChecked()),
            "medium": self.medium_picker.current_ref(),
            "medium_mode": str(self.medium_mode_combo.currentData()),
            "allow_unknown_medium": str(self.allow_unknown_medium_check.isChecked()),
            "seed": str(self.seed_spin.value()),
            "workers": str(self.workers_spin.value()),
            "solver_threads": str(self.solver_threads_spin.value()),
            "growth_fraction": str(self.growth_fraction_spin.value()),
            "min_member_growth": str(self.min_member_growth_spin.value()),
            "multi_metric": self.multi_metric_combo.currentText(),
            "pareto_resolution": str(self.pareto_resolution_spin.value()),
            "exhaustive_max": str(self.exhaustive_max_spin.value()),
            "n_samples": str(self.n_samples_spin.value()),
            "ga_pop_size": str(self.ga_pop_size_spin.value()),
            "ga_generations": str(self.ga_generations_spin.value()),
            "ga_mutation_rate": str(self.ga_mutation_rate_spin.value()),
            "ga_immigrant_fraction": str(self.ga_immigrant_fraction_spin.value()),
            "ga_tournament_k": str(self.ga_tournament_k_spin.value()),
            "ga_elitism": str(self.ga_elitism_spin.value()),
            "ga_budget": str(self.ga_budget_spin.value()),
            "ga_patience": str(self.ga_patience_spin.value()),
            "ga_restart_after": str(self.ga_restart_after_spin.value()),
            "ga_local_search_fraction": str(self.ga_local_search_fraction_spin.value()),
            "ga_preserve_common": str(self.ga_preserve_common_check.isChecked()),
            "checkpoint": self.checkpoint_input.text().strip(),
            "resume": str(self.resume_check.isChecked()),
            "min_community_growth": str(self.min_community_growth_spin.value()),
            "validate_top": str(self.validation_top_spin.value()),
            "timeout": str(self.solve_timeout_spin.value()),
        }
        return {k: snapshot[k] for k in self.REQUEST_FIELDS.get(kind, ())}

    # ── the ranked result lives in self.results_panel ────────────────────────────────
    @property
    def current_run_dir(self) -> Path | None:
        return self.results_panel.current_run_dir

    @current_run_dir.setter
    def current_run_dir(self, value: Path | None) -> None:
        self.results_panel.current_run_dir = value

    @property
    def _displayed_kind(self) -> str | None:
        return self.results_panel._displayed_kind

    @_displayed_kind.setter
    def _displayed_kind(self, value: str | None) -> None:
        self.results_panel._displayed_kind = value

    @property
    def _displayed_request(self) -> dict[str, str] | None:
        return self.results_panel._displayed_request

    @_displayed_request.setter
    def _displayed_request(self, value: dict[str, str] | None) -> None:
        self.results_panel._displayed_request = value

    def invalidate_results(self, *args: object) -> None:
        self.results_panel.invalidate_results(*args)

    def superseded_note(self, requested: dict[str, str], kind: str) -> str:
        return self.results_panel.superseded_note(requested, kind)

    def effective_note(self, requested: dict[str, str], kind: str) -> str:
        return self.results_panel.effective_note(requested, kind)

    def row_record(self, row: int) -> dict[object, object] | None:
        return self.results_panel.row_record(row)

    def selected_figure_artifact(self) -> str:
        return self.results_panel.selected_figure_artifact()

    def refresh_figure_mode(self, mode: str | None = None) -> None:
        self.results_panel.refresh_figure_mode(mode)

    def load_summary(self, summary: dict[str, object], **kwargs: Any) -> None:
        self.results_panel.load_summary(summary, **kwargs)
