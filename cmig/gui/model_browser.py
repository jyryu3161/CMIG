"""Read-only browser of one model copy: reactions, metabolites, genes and exchanges, with the
model's namespace confirmation and Check Growth in its header.

Contents come from the model's index (`models/.index/<sha256>.json`); nothing here edits a
model or feeds an analysis.
"""

from __future__ import annotations

import html
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.analysis_page import hide_row_numbers
from cmig.gui.builder import make_read_only, read_only_item
from cmig.gui.pickers import MediumPicker
from cmig.io import project as proj
from cmig.io.project import ModelEntry


def _bound(value: object) -> str:
    return "unbounded" if value is None else f"{float(value):g}"  # type: ignore[arg-type]


def _bounds_text(item: dict[str, Any]) -> str:
    return f"[{_bound(item.get('lower'))}, {_bound(item.get('upper'))}]"


def _arrow(item: dict[str, Any]) -> str:
    lower = item.get("lower")
    upper = item.get("upper")
    low = float("-inf") if lower is None else float(lower)
    high = float("inf") if upper is None else float(upper)
    if low < 0 < high:
        return "⇌"
    return "←" if high <= 0 else "→"


def _side(terms: list[tuple[str, float]], label: Callable[[str], str]) -> str:
    parts = []
    for met, coef in terms:
        amount = abs(coef)
        prefix = "" if amount == 1 else f"{amount:g} "
        parts.append(prefix + label(met))
    return " + ".join(parts) or "∅"


def equation(item: dict[str, Any], label: Callable[[str], str]) -> str:
    mets = item.get("metabolites") or {}
    left = [(m, float(c)) for m, c in mets.items() if float(c) < 0]
    right = [(m, float(c)) for m, c in mets.items() if float(c) > 0]
    return f"{_side(left, label)} {_arrow(item)} {_side(right, label)}"


class _EntityTab(QWidget):
    def __init__(self, headers: list[str], detail: Callable[[str], str]) -> None:
        super().__init__()
        self._detail = detail
        self._haystack: list[str] = []
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by id or name")
        self.filter_input.setClearButtonEnabled(True)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        make_read_only(self.table)
        hide_row_numbers(self.table)
        self.detail = QTextBrowser()
        self.detail.setOpenLinks(False)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.detail)
        splitter.setSizes([400, 180])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(self.filter_input)
        layout.addWidget(splitter, 1)
        self.filter_input.textChanged.connect(self._apply_filter)
        self.table.itemSelectionChanged.connect(self._show_detail)

    def set_rows(self, rows: list[list[str]], haystack: list[str]) -> None:
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, text in enumerate(row):
                self.table.setItem(r, c, read_only_item(text))
        self._haystack = [h.lower() for h in haystack]
        self.detail.clear()
        self._apply_filter(self.filter_input.text())

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for r, hay in enumerate(self._haystack):
            self.table.setRowHidden(r, bool(needle) and needle not in hay)

    def current_id(self) -> str | None:
        row = self.table.currentRow()
        item = None if row < 0 else self.table.item(row, 0)
        return None if item is None else item.text()

    def select_id(self, item_id: str) -> bool:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if item is not None and item.text() == item_id:
                if self.table.isRowHidden(r):
                    self.filter_input.clear()
                self.table.setCurrentCell(r, 0)
                self.table.scrollToItem(item)
                self._show_detail()
                return True
        return False

    def _show_detail(self) -> None:
        item_id = self.current_id()
        self.detail.setHtml("" if item_id is None else self._detail(item_id))


class ModelBrowser(QWidget):
    confirm_requested = Signal(str)
    revoke_requested = Signal(str)
    check_growth_requested = Signal(str)
    retry_index_requested = Signal(str)

    _KINDS = ("reaction", "metabolite", "gene", "exchange")

    def __init__(self) -> None:
        super().__init__()
        self._entry: ModelEntry | None = None
        self._reactions: dict[str, dict[str, Any]] = {}
        self._metabolites: dict[str, dict[str, Any]] = {}
        self._genes: dict[str, dict[str, Any]] = {}
        self._met_reactions: dict[str, list[str]] = {}
        self._has_index = False
        self.title_label = QLabel("")
        font = QFont(self.title_label.font())
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() * 1.2)
        self.title_label.setFont(font)
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.medium_picker = MediumPicker()
        self.skip_unknown_check = QCheckBox("Skip medium metabolites this model lacks")
        self.check_growth_btn = QPushButton("Check Growth")
        self.namespace_label = QLabel("")
        self.namespace_label.setWordWrap(True)
        self.namespace_label.setTextFormat(Qt.TextFormat.PlainText)
        self.confirm_btn = QPushButton("Confirm…")
        self.revoke_btn = QPushButton("Revoke")
        self.objective_label = QLabel("")
        self.objective_label.setWordWrap(True)
        self.objective_label.setTextFormat(Qt.TextFormat.PlainText)
        self.objective_toggle = QToolButton()
        self.objective_toggle.setText("Show terms")
        self.objective_toggle.setCheckable(True)
        self.objective_terms = QLabel("")
        self.objective_terms.setWordWrap(True)
        self.objective_terms.setTextFormat(Qt.TextFormat.PlainText)
        self.objective_terms.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.objective_terms.setVisible(False)
        self.objective_toggle.toggled.connect(self.objective_terms.setVisible)
        self.growth_label = QLabel("Growth: not checked yet")
        self.growth_label.setWordWrap(True)
        self.growth_label.setTextFormat(Qt.TextFormat.PlainText)
        self.growth_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.contents_label = QLabel("")
        self.contents_label.setWordWrap(True)
        self.contents_label.setTextFormat(Qt.TextFormat.PlainText)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setVisible(False)
        self.reactions_tab = _EntityTab(["ID", "Name", "Bounds", "Subsystem"],
                                        self._reaction_detail)
        self.metabolites_tab = _EntityTab(["ID", "Name", "Formula", "Compartment"],
                                          self._metabolite_detail)
        self.genes_tab = _EntityTab(["ID", "Name", "Reactions"], self._gene_detail)
        self.exchanges_tab = _EntityTab(["ID", "Name", "Bounds"], self._reaction_detail)
        self.tabs = QTabWidget()
        for tab, title in ((self.reactions_tab, "Reactions"),
                           (self.metabolites_tab, "Metabolites"),
                           (self.genes_tab, "Genes"), (self.exchanges_tab, "Exchanges")):
            self.tabs.addTab(tab, title)
            tab.detail.anchorClicked.connect(lambda url: self._navigate(url.toString()))
        header = QHBoxLayout()
        header.addWidget(self.title_label, 1)
        header.addWidget(self.medium_picker)
        header.addWidget(self.check_growth_btn)
        namespace_row = QHBoxLayout()
        namespace_row.addWidget(self.namespace_label, 1)
        namespace_row.addWidget(self.confirm_btn)
        namespace_row.addWidget(self.revoke_btn)
        objective_row = QHBoxLayout()
        objective_row.addWidget(self.objective_label, 1)
        objective_row.addWidget(self.objective_toggle)
        contents_row = QHBoxLayout()
        contents_row.addWidget(self.contents_label, 1)
        contents_row.addWidget(self.retry_btn)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addLayout(header)
        layout.addWidget(self.skip_unknown_check, 0, Qt.AlignmentFlag.AlignRight)
        layout.addLayout(namespace_row)
        layout.addLayout(objective_row)
        layout.addWidget(self.objective_terms)
        layout.addWidget(self.growth_label)
        layout.addLayout(contents_row)
        layout.addWidget(self.tabs, 1)
        self.confirm_btn.clicked.connect(lambda: self._emit(self.confirm_requested))
        self.revoke_btn.clicked.connect(lambda: self._emit(self.revoke_requested))
        self.check_growth_btn.clicked.connect(lambda: self._emit(self.check_growth_requested))
        self.retry_btn.clicked.connect(lambda: self._emit(self.retry_index_requested))

    def _emit(self, signal: Any) -> None:
        if self._entry is not None:
            signal.emit(self._entry.id)

    def model_id(self) -> str | None:
        return None if self._entry is None else self._entry.id

    def clear_banner(self) -> None:
        """The run-recording path clears a page banner; the browser has none."""

    def snapshot(self) -> dict[str, Any]:
        entry = self._entry
        return {
            "model": None if entry is None else entry.id,
            "sha256": None if entry is None else entry.sha256,
            "medium": self.medium_picker.current_ref(),
            "skip_unknown": self.skip_unknown_check.isChecked(),
        }

    def set_growth(self, text: str) -> None:
        self.growth_label.setText(text)

    def clear(self) -> None:
        """Show no model (another project was opened, or none is)."""
        self._entry = None
        for label in (self.title_label, self.namespace_label, self.objective_label,
                      self.objective_terms):
            label.clear()
        self.growth_label.setText("Growth: not checked yet")
        self.confirm_btn.setVisible(False)
        self.revoke_btn.setVisible(False)
        self.objective_toggle.setChecked(False)
        self.objective_toggle.setVisible(False)
        self.check_growth_btn.setEnabled(False)
        self.check_growth_btn.setToolTip("")
        self.set_contents(None, "")
        self.contents_label.setVisible(False)

    # ── header ───────────────────────────────────────────────────────────────────────
    def show_model(self, entry: ModelEntry, index: dict[str, Any] | None,
                   problem: str = "") -> None:
        self._entry = entry
        counts = (f"{entry.n_reactions} reactions · {entry.n_metabolites} metabolites · "
                  f"{entry.n_genes} genes" if entry.n_reactions is not None
                  else "size not recorded")
        self.title_label.setText(f"{entry.id} · {counts}")
        self._show_namespace(entry)
        self._show_objective(entry)
        self.growth_label.setText("Growth: not checked yet")
        runnable = entry.status in ("ok", "warning") and entry.integrity == "ok"
        confirmed = proj.namespace_confirmed(entry)
        self.check_growth_btn.setEnabled(runnable and confirmed)
        self.check_growth_btn.setToolTip(
            "" if runnable and confirmed else
            ("Confirm this model's namespace first" if runnable
             else "This model cannot be run: " + proj.check_reason(entry)[1])
        )
        self.set_contents(index, problem)

    def has_index(self) -> bool:
        """True while the shown model's contents (its index) are on screen."""
        return self._has_index

    def set_contents(self, index: dict[str, Any] | None, problem: str = "") -> None:
        """Show the browsed model's contents (or why there are none); the header is kept."""
        entry = self._entry
        runnable = (entry is not None and entry.status in ("ok", "warning")
                    and entry.integrity == "ok")
        self._show_contents(index, problem)
        self._has_index = index is not None
        # Retry builds an index again; a model that cannot be read has nothing to retry.
        self.retry_btn.setVisible(index is None and bool(problem) and runnable)

    def _show_namespace(self, entry: ModelEntry) -> None:
        state = proj.confirmation_state(entry)
        counts = entry.namespace_mappings
        mapping = ("" if counts is None else
                   f" · mappings: {counts.get('resolved', 0)} of {counts.get('total', 0)} "
                   "reviewed")
        if state == "confirmed":
            when = str((entry.namespace_confirmed or {}).get("at", ""))[:10]
            text = f"✓ Namespace confirmed by you · {when}"
        elif state == "changed":
            text = "⚠ Changed since confirmed — confirm again before running it"
        elif proj.namespace_review_state(entry) in ("blocked", "review"):
            text = "⚠ Namespace not reviewed — needed before community analyses"
        else:
            text = "Namespace not confirmed — needed before community analyses"
        self.namespace_label.setText(text + mapping)
        self.confirm_btn.setVisible(state != "confirmed")
        self.revoke_btn.setVisible(state == "confirmed")

    def _show_objective(self, entry: ModelEntry) -> None:
        terms = list(entry.biomass)
        warning = proj.objective_warning_of(entry)
        self.objective_toggle.setChecked(False)
        if not terms:
            self.objective_label.setText("⚠ No objective")
            self.objective_toggle.setVisible(False)
        elif len(terms) == 1 and warning is None:
            self.objective_label.setText(f"Objective: {terms[0]} (biomass)")
            self.objective_toggle.setVisible(False)
        else:
            self.objective_label.setText(
                f"Objective: {len(terms)} {'term' if len(terms) == 1 else 'terms'} — "
                f"{warning or 'not a single biomass reaction'}"
            )
            self.objective_toggle.setVisible(True)
        self.objective_terms.setText(", ".join(terms))

    # ── contents ─────────────────────────────────────────────────────────────────────
    def _show_contents(self, index: dict[str, Any] | None, problem: str) -> None:
        if index is None:
            self.tabs.setVisible(False)
            self.contents_label.setVisible(True)
            self.contents_label.setText(
                f"Model contents unavailable: {problem}" if problem
                else "Building model contents…"
            )
            self.retry_btn.setVisible(bool(problem))
            # Never keep another model's contents behind the hidden tabs.
            self._reactions, self._metabolites, self._genes = {}, {}, {}
            self._met_reactions = {}
            for tab in (self.reactions_tab, self.metabolites_tab, self.genes_tab,
                        self.exchanges_tab):
                tab.set_rows([], [])
            return
        self.contents_label.setVisible(False)
        self.retry_btn.setVisible(False)
        self.tabs.setVisible(True)
        self._reactions = {r["id"]: r for r in index.get("reactions", [])}
        self._metabolites = {m["id"]: m for m in index.get("metabolites", [])}
        self._genes = {g["id"]: g for g in index.get("genes", [])}
        self._met_reactions = {}
        for rid, reaction in self._reactions.items():
            for met in reaction.get("metabolites") or {}:
                self._met_reactions.setdefault(met, []).append(rid)

        def ids(item: dict[str, Any]) -> str:
            return equation(item, lambda m: m)

        reactions = list(self._reactions.values())
        self.reactions_tab.set_rows(
            [[r["id"], r.get("name", ""), _bounds_text(r), r.get("subsystem", "")]
             for r in reactions],
            [f"{r['id']} {r.get('name', '')} {ids(r)}" for r in reactions],
        )
        metabolites = list(self._metabolites.values())
        self.metabolites_tab.set_rows(
            [[m["id"], m.get("name", ""), m.get("formula", ""), m.get("compartment", "")]
             for m in metabolites],
            [f"{m['id']} {m.get('name', '')}" for m in metabolites],
        )
        genes = list(self._genes.values())
        self.genes_tab.set_rows(
            [[g["id"], g.get("name", ""), str(len(g.get("reactions") or []))] for g in genes],
            [f"{g['id']} {g.get('name', '')}" for g in genes],
        )
        exchanges = [self._reactions[e] for e in index.get("exchanges", [])
                     if e in self._reactions]
        self.exchanges_tab.set_rows(
            [[r["id"], r.get("name", ""), _bounds_text(r)] for r in exchanges],
            [f"{r['id']} {r.get('name', '')} {ids(r)}" for r in exchanges],
        )

    def _met_link(self, met: str) -> str:
        name = self._metabolites.get(met, {}).get("name") or met
        return f'<a href="met:{html.escape(met)}">{html.escape(str(name))}</a>'

    def _reaction_detail(self, rid: str) -> str:
        r = self._reactions.get(rid)
        if r is None:
            return ""
        genes = [g for g in self._genes if g in str(r.get("gpr", "")).replace("(", " ")
                 .replace(")", " ").split()]
        gene_links = ", ".join(f'<a href="gene:{html.escape(g)}">{html.escape(g)}</a>'
                               for g in genes)
        return (
            f"<b>{html.escape(rid)}</b> — {html.escape(str(r.get('name', '')))}<br>"
            f"{equation(r, self._met_link)}<br>"
            f"<small>{html.escape(equation(r, lambda m: m))}</small><br>"
            f"<b>Bounds</b>: {_bounds_text(r)}<br>"
            f"<b>GPR</b>: {html.escape(str(r.get('gpr') or 'none'))}"
            + (f" ({gene_links})" if gene_links else "") + "<br>"
            f"<b>Subsystem</b>: {html.escape(str(r.get('subsystem') or 'not recorded'))}"
        )

    def _metabolite_detail(self, met: str) -> str:
        m = self._metabolites.get(met)
        if m is None:
            return ""
        links = ", ".join(f'<a href="rxn:{html.escape(r)}">{html.escape(r)}</a>'
                          for r in self._met_reactions.get(met, []))
        charge = m.get("charge")
        return (
            f"<b>{html.escape(met)}</b> — {html.escape(str(m.get('name', '')))}<br>"
            f"<b>Formula</b>: {html.escape(str(m.get('formula') or 'not recorded'))}<br>"
            f"<b>Charge</b>: {'not recorded' if charge is None else charge}<br>"
            f"<b>Compartment</b>: {html.escape(str(m.get('compartment') or 'not recorded'))}"
            f"<br><b>Reactions</b>: {links or 'none'}"
        )

    def _gene_detail(self, gid: str) -> str:
        g = self._genes.get(gid)
        if g is None:
            return ""
        links = ", ".join(f'<a href="rxn:{html.escape(r)}">{html.escape(r)}</a>'
                          for r in g.get("reactions") or [])
        return (f"<b>{html.escape(gid)}</b> — {html.escape(str(g.get('name', '')))}<br>"
                f"<b>Reactions</b>: {links or 'none'}")

    def _navigate(self, link: str) -> None:
        kind, _, item_id = link.partition(":")
        target = {"rxn": "reaction", "met": "metabolite", "gene": "gene"}.get(kind)
        if target is not None:
            self.select(target, item_id)

    def select(self, kind: str, item_id: str) -> bool:
        tab = {"reaction": self.reactions_tab, "metabolite": self.metabolites_tab,
               "gene": self.genes_tab, "exchange": self.exchanges_tab}.get(kind)
        if tab is None:
            return False
        self.tabs.setCurrentWidget(tab)
        return tab.select_id(item_id)
