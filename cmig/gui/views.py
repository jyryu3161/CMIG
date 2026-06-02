"""GUI Views — Sweep View · External Profile Viewer (Roadmap Phase 2, §11).

Design Ref: §11 (Sweep View·External Profile Viewer) / cmig-gui-views.design. Plan SC: SC-GV1~GV6.

테이블 기반 인터랙티브 뷰(QWebEngine 비의존 → offscreen 클린 검증). 실 backend 소비:
SweepView 가 JobRunner+make_sweep_job 으로 sweep 실행, ExternalProfileView 가 sign/FVA/target
산출을 표시. offscreen = 실행 증거지 human 시각 QA(G-7b) 아님(별도 carry, 정직).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cmig.service import JobRunner, make_sweep_job

# sign 라벨 → UI 색 (secretion=초록 / uptake=보라, §11 diverging)
_LABEL_COLOR = {"secretion": "#31a354", "uptake": "#756bb1"}


class SweepView(QWidget):
    """Sweep View — 축·값 정의 → JobRunner sweep → 결과 매트릭스(+cache-hit). 실 backend 소비."""

    _COLS = ("condition_id", "value", "status", "cache_hit")

    def __init__(self, runner: JobRunner | None = None) -> None:
        super().__init__()
        self.runner = runner if runner is not None else JobRunner(max_workers=2)
        layout = QVBoxLayout(self)
        self.title = QLabel("Sweep")
        self.status = QLabel("Advanced result view: configure product sweeps from the CLI.")
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(["Condition", "Value", "Status", "Cache"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.title)
        layout.addWidget(self.status)
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
                item = QTableWidgetItem(text)
                if r.status == "failed":
                    item.setForeground(QColor("#d62728"))
                self.table.setItem(i, c, item)


class ExternalProfileView(QWidget):
    """External Profile Viewer — metabolite별 net flux + sign 색 + FVA 범위 + target 요약."""

    _COLS = ("metabolite", "net_flux", "label", "fva")

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.title = QLabel("External Profile")
        self.table = QTableWidget(0, len(self._COLS))
        self.table.setHorizontalHeaderLabels(
            ["Metabolite", "Net flux", "Direction", "FVA [lo, hi]"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.target_label = QLabel("")
        layout.addWidget(self.title)
        layout.addWidget(self.table)
        layout.addWidget(self.target_label)

    def load_profile(self, rows: list[dict[str, Any]]) -> None:
        """profile rows → 표(secretion=초록/uptake=보라 색). FVA 있으면 [lo, hi] 표시."""
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            net = r.get("net_flux")
            label = r.get("label") or "—"
            lo, hi = r.get("fva_lo"), r.get("fva_hi")
            fva = f"[{lo:.3g}, {hi:.3g}]" if lo is not None and hi is not None else "—"
            cells = [
                str(r.get("metabolite", "")),
                "—" if net is None else f"{net:.4g}",
                label, fva,
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c == 2 and label in _LABEL_COLOR:
                    item.setForeground(QColor(_LABEL_COLOR[label]))
                self.table.setItem(i, c, item)

    def load_targets(self, target_summary: list[dict[str, Any]] | None) -> None:
        """target readout(SCFA 등) 요약 라벨."""
        if not target_summary:
            self.target_label.setText("")
            return
        parts = [f"{t.get('metabolite')}={t.get('ui_flux', t.get('value', 0)):.3g}"
                 for t in target_summary]
        self.target_label.setText("Targets: " + ", ".join(parts))
