"""Qt wrapper around an open CMIG project: change signals, undo, run listing, recents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from cmig.io import project as proj

_KIND_LABELS = {
    "search": "Search",
    "gene_ko_search": "Gene KO",
    "gene-ko": "Gene KO",
    "strain_growth": "Strain Growth",
    "strain-growth": "Strain Growth",
    "abundance_impact": "Ratio Impact",
    "abundance-impact": "Ratio Impact",
    "host_microbe_bigg": "Host–Microbe",
    "host-microbe": "Host–Microbe",
    "host_search_bigg": "Host Search",
    "host-search": "Host Search",
    "dfba": "dFBA",
    "spatial": "Spatial",
    "community_solve": "Community",
    "community": "Community",
    "sweep": "Sweep",
    "medium-growth": "Medium Growth",
    "minimal_medium": "Minimal Medium",
    "minimal-medium": "Minimal Medium",
}
_TIME_RE = re.compile(r"-(\d{8})-(\d{2})(\d{2})(\d{2})(?:-\d+)?$")


def run_label(kind: str, run_name: str, summary_hint: str) -> str:
    match = _TIME_RE.search(run_name)
    prefix = run_name[: match.start()] if match else run_name
    title = _KIND_LABELS.get(kind) or _KIND_LABELS.get(prefix)
    if title is None or match is None:
        return run_name
    clock = f"{match.group(2)}:{match.group(3)}"
    return " · ".join(part for part in (title, summary_hint, clock) if part)


@dataclass(frozen=True)
class RunEntry:
    path: Path
    name: str
    kind: str
    status: str
    label: str
    mtime: float


def _summary_hint(inspected: dict[str, object], run_dir: Path) -> str:
    import json

    summary_file = inspected.get("summary_file")
    if not isinstance(summary_file, str):
        return ""
    try:
        summary = json.loads((run_dir / summary_file).read_text())
    except (OSError, ValueError):
        return ""
    if not isinstance(summary, dict):
        return ""
    targets = summary.get("targets")
    if isinstance(targets, list) and targets:
        return ",".join(str(t) for t in targets)
    target = summary.get("target")
    return str(target) if isinstance(target, str) else ""


def inspect_run(run_dir: Path) -> RunEntry:
    from cmig.cli.main import _inspect_run_dir

    inspected: dict[str, object]
    try:
        inspected = _inspect_run_dir(run_dir)
        kind = str(inspected.get("kind") or "unknown")
        status = str(inspected.get("status") or "unknown")
        if inspected.get("artifact_integrity") == "mismatch":
            status = "failed"
    except Exception:  # noqa: BLE001 - an unreadable run is listed, never raised
        inspected, kind, status = {}, "unknown", "unreadable"
    return RunEntry(
        path=run_dir,
        name=run_dir.name,
        kind=kind,
        status=status,
        label=run_label(kind, run_dir.name, _summary_hint(inspected, run_dir)),
        mtime=run_dir.stat().st_mtime,
    )


class _RemoveModels(QUndoCommand):
    def __init__(self, session: ProjectSession, ids: list[str]) -> None:
        super().__init__(f"Remove {len(ids)} Models" if len(ids) > 1 else "Remove Model")
        self._session = session
        self._ids = ids
        self._removed: list[tuple[int, proj.ModelEntry]] = []

    def redo(self) -> None:
        project = self._session.require()
        self._removed = [proj.remove_model(project, model_id) for model_id in self._ids]
        self._session.commit_models()

    def undo(self) -> None:
        project = self._session.require()
        for index, entry in reversed(self._removed):
            proj.restore_model(project, index, entry)
        self._session.commit_models()


class _AddModels(QUndoCommand):
    def __init__(self, session: ProjectSession, entries: list[proj.ModelEntry]) -> None:
        super().__init__(f"Add {len(entries)} Models" if len(entries) > 1 else "Add Model")
        self._session, self._entries = session, entries

    def redo(self) -> None:
        project = self._session.require()
        for entry in self._entries:
            if entry not in project.models:
                project.models.append(entry)
        self._session.commit_models()

    def undo(self) -> None:
        project = self._session.require()
        project.models[:] = [m for m in project.models if m not in self._entries]
        self._session.commit_models()


class _AddMedium(QUndoCommand):
    def __init__(self, session: ProjectSession, entry: proj.MediumEntry) -> None:
        super().__init__("Add Medium")
        self._session, self._entry = session, entry

    def redo(self) -> None:
        project = self._session.require()
        if self._entry not in project.media:
            project.media.append(self._entry)
        self._session.commit_media()

    def undo(self) -> None:
        project = self._session.require()
        project.media[:] = [m for m in project.media if m is not self._entry]
        self._session.commit_media()


class _RenameModel(QUndoCommand):
    def __init__(self, session: ProjectSession, old: str, new: str) -> None:
        super().__init__("Rename Model")
        self._session, self._old, self._new = session, old, new

    def redo(self) -> None:
        proj.rename_model(self._session.require(), self._old, self._new)
        self._session.commit_models()

    def undo(self) -> None:
        proj.rename_model(self._session.require(), self._new, self._old)
        self._session.commit_models()


class ProjectSession(QObject):
    opened = Signal()
    closed = Signal()
    models_changed = Signal()
    media_changed = Signal()
    runs_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.project: proj.Project | None = None
        self.undo_stack = QUndoStack(self)
        self._lock: proj.ProjectLock | None = None
        self._run_cache: dict[Path, tuple[float, RunEntry]] = {}

    def require(self) -> proj.Project:
        if self.project is None:
            raise proj.ProjectError("open or create a project first")
        return self.project

    def _attach(self, project: proj.Project, lock: proj.ProjectLock) -> None:
        self.close()
        self.project, self._lock = project, lock
        self.undo_stack.clear()
        self._run_cache.clear()
        self.opened.emit()

    def open(self, root: Path) -> None:
        lock = proj.ProjectLock.acquire(Path(root))
        try:
            project = proj.open_project(Path(root))
        except proj.ProjectError:
            lock.release()
            raise
        self._attach(project, lock)

    def create(self, root: Path, name: str | None = None) -> None:
        project = proj.create_project(Path(root), name)
        self._attach(project, proj.ProjectLock.acquire(project.root))

    def close(self) -> None:
        if self.project is None:
            return
        self.save()
        if self._lock is not None:
            self._lock.release()
        self.project, self._lock = None, None
        self.undo_stack.clear()
        self.closed.emit()

    def save(self) -> None:
        if self.project is not None:
            proj.save_project(self.project)

    def commit_models(self) -> None:
        self.save()
        self.models_changed.emit()

    def commit_media(self) -> None:
        self.save()
        self.media_changed.emit()

    def add_entries(self, entries: list[proj.ModelEntry]) -> None:
        if entries:
            self.undo_stack.push(_AddModels(self, list(entries)))

    def remove_models(self, ids: list[str]) -> None:
        if ids:
            self.undo_stack.push(_RemoveModels(self, list(ids)))

    def rename_model(self, old: str, new: str) -> None:
        project = self.require()
        probe = proj.Project(
            project.root,
            project.name,
            project.created,
            [proj.ModelEntry(**vars(m)) for m in project.models],
        )
        proj.rename_model(probe, old, new)  # validate before pushing an undo step
        self.undo_stack.push(_RenameModel(self, old, new))

    def add_medium(self, entry: proj.MediumEntry) -> None:
        self.undo_stack.push(_AddMedium(self, entry))

    def settings(self, analysis: str) -> dict[str, object]:
        if self.project is None:
            return {}
        return dict(self.project.analysis_settings.get(analysis, {}))

    def store_settings(self, analysis: str, values: dict[str, object]) -> None:
        project = self.require()
        project.analysis_settings[analysis] = dict(values)
        self.save()

    def runs(self) -> list[RunEntry]:
        if self.project is None:
            return []
        entries: list[RunEntry] = []
        for run_dir in self.project.runs_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith(("_", ".")):
                continue
            mtime = run_dir.stat().st_mtime
            cached = self._run_cache.get(run_dir)
            if cached is None or cached[0] != mtime:
                cached = (mtime, inspect_run(run_dir))
                self._run_cache[run_dir] = cached
            entries.append(cached[1])
        return sorted(entries, key=lambda entry: (entry.mtime, entry.name), reverse=True)

    def refresh_runs(self) -> None:
        self.runs_changed.emit()


class RecentProjects:
    KEY = "recentProjects"
    LIMIT = 10

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else QSettings("CMIG", "CMIG")

    def paths(self) -> list[Path]:
        raw = self._settings.value(self.KEY, [])
        values: list[object] = (
            [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, (list, tuple)) else []
        )
        return [Path(str(value)) for value in values if str(value)]

    def add(self, path: Path) -> None:
        resolved = Path(path).resolve()
        current = [p for p in self.paths() if p.resolve() != resolved]
        self._settings.setValue(self.KEY, [str(resolved), *map(str, current)][: self.LIMIT])
        self._settings.sync()

    def clear(self) -> None:
        self._settings.setValue(self.KEY, [])
        self._settings.sync()
