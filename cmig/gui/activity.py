"""Bottom activity pane: running jobs, cancel, log and the equivalent cmig command."""

from __future__ import annotations

import shlex
from collections.abc import Mapping

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.builder import make_read_only, read_only_item
from cmig.service.jobrunner import JobRunner, JobStatus

_DEFAULT_HEADERS = {"col_job": "Job", "col_kind": "Kind", "col_status": "Status",
                    "col_progress": "Progress"}


#: what the Kind column calls each job; an unknown kind is shown as it is
JOB_KIND_NAMES = {
    "search_fixture": "Search",
    "gene_ko_search": "Gene KO",
    "strain_growth": "Strain Growth",
    "abundance_impact": "Ratio Impact",
    "host_microbe_bigg": "Host–Microbe",
    "host_search_bigg": "Host Search",
    "dfba": "dFBA",
    "spatial_preview": "Spatial Preview",
    "community_solve": "Community Solve",
    "sweep": "Sweep",
    "sweep_fixture": "Sweep Demo",
    "medium_growth_check": "Medium Growth Check",
    "minimal_medium": "Minimal Medium",
    "sandbox_fixture": "Constraint Sandbox",
    "solve_fixture": "Demo Run",
    "import_models": "Import Models",
    "agora2_fetch": "AGORA2 Download",
}


def command_line(argv: list[str]) -> str:
    return "cmig " + shlex.join(argv)


class RuntimeJobsPanel(QTableWidget):
    """JobRunner job states (moved from app.py; behaviour unchanged)."""

    def __init__(self, tr: dict[str, str] | None = None) -> None:
        super().__init__(0, 4)
        labels = {**_DEFAULT_HEADERS, **(tr or {})}
        self.setHorizontalHeaderLabels(
            [labels["col_job"], labels["col_kind"], labels["col_status"], labels["col_progress"]]
        )
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        make_read_only(self)

    def refresh(
        self,
        runner: JobRunner,
        job_ids: list[str],
        cancelling: frozenset[str] | set[str] = frozenset(),
        status_labels: Mapping[str, str] | None = None,
    ) -> None:
        """JobRunner.poll 로 각 job 의 실제 상태를 표에 반영(orphan 아님).

        A job whose cancel has been *requested* but which is still inside a non-interruptible
        solver call is shown as `cancelling (solver still running)` rather than plain
        `running` — the previous label made the cancel look like it had done nothing.
        A job id in `status_labels` shows that text instead of any of these (a job that ended
        cancelled but returned normally would otherwise read `done`).
        """
        self.setRowCount(len(job_ids))
        for row, jid in enumerate(job_ids):
            job = runner.poll(jid)
            # GUI jobs only check cancellation at run boundaries, so an in-flight MICOM/Gurobi
            # call keeps burning CPU after cancel(); say so instead of implying it stopped.
            progress = (
                f"{job.progress[0]}/{job.progress[1]}"
                if job.progress and job.progress[1] > 1
                # 0/1 → 1/1 is a two-state placeholder, not measured progress.
                else "—"
            )
            status = job.status.value
            if jid in cancelling and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                status = "cancelling (solver still running)"
            status = (status_labels or {}).get(jid, status)
            kind = JOB_KIND_NAMES.get(job.kind, job.kind)
            for col, text in enumerate([job.job_id, kind, status, progress]):
                item = read_only_item(text)
                if job.error:
                    item.setToolTip(job.error)
                if isinstance(job.result, dict) and job.result.get("output_dir"):
                    item.setToolTip(
                        f"{job.error or status}\nOutput: {job.result['output_dir']}"
                    )
                self.setItem(row, col, item)

    def selected_job_id(self) -> str | None:
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return None if item is None else item.text()


class ActivityPane(QWidget):
    cancel_requested = Signal(str)

    def __init__(self, tr: dict[str, str] | None = None) -> None:
        super().__init__()
        self.jobs = RuntimeJobsPanel(tr)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setToolTip("Cancel the selected job (⌘.)")
        self.cancel_btn.clicked.connect(self._cancel_selected)
        self.command_label = QLineEdit("")
        self.command_label.setReadOnly(True)
        self.command_label.setPlaceholderText("Equivalent cmig command")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("Select a job to see its log and errors.")
        top = QHBoxLayout()
        top.addWidget(QLabel("Activity"))
        top.addStretch(1)
        top.addWidget(self.cancel_btn)
        split = QSplitter()
        split.addWidget(self.jobs)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.command_label)
        right_layout.addWidget(self.log_view)
        split.addWidget(right)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.addLayout(top)
        layout.addWidget(split)

    def _cancel_selected(self) -> None:
        job_id = self.jobs.selected_job_id()
        if job_id:
            self.cancel_requested.emit(job_id)

    def set_job_detail(self, log: str, command: str) -> None:
        self.log_view.setPlainText(log)
        self.command_label.setText(command)

    def expand(self) -> None:
        self.setVisible(True)
