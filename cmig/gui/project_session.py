"""Qt wrapper around an open CMIG project: change signals, undo, run listing, recents."""

from __future__ import annotations

import contextlib
import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QTimer, Signal
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


#: how bad a run's status is when two sources disagree; anything else ranks 0
_STATUS_SEVERITY = {"cancelled": 1, "failed": 2, "unreadable": 2}


def merge_run_status(status: str, marker: str | None) -> str:
    """The worse of a run's own status and the state a job marker recorded for it.

    A marker only ever makes a run look worse: it never turns a failed run into a cancelled one
    or any run into an ok one.
    """
    if marker is None:
        return status
    if _STATUS_SEVERITY.get(marker, 0) > _STATUS_SEVERITY.get(status, 0):
        return marker
    return status


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
    try:
        mtime = run_dir.stat().st_mtime
    except OSError:
        mtime, status = 0.0, "unreadable"
    return RunEntry(
        path=run_dir,
        name=run_dir.name,
        kind=kind,
        status=status,
        label=run_label(kind, run_dir.name, _summary_hint(inspected, run_dir)),
        mtime=mtime,
    )


class _Command(QUndoCommand):
    """A project change applied and saved *before* it is pushed on the undo stack.

    ``execute`` applies, saves and only then pushes, so a failed save rolls the change back and
    leaves the stack untouched. The push's own first ``redo`` is therefore a no-op.
    """

    models = True  # which change signal a successful save emits

    def __init__(self, session: ProjectSession, text: str) -> None:
        super().__init__(text)
        self._session = session
        self._skip_redo = False

    def apply(self) -> None:
        raise NotImplementedError

    def revert(self) -> None:
        raise NotImplementedError

    def _commit(self) -> None:
        if self.models:
            self._session.commit_models()
        else:
            self._session.commit_media()

    def execute(self) -> None:
        self.apply()
        try:
            self._commit()
        except proj.ProjectError:
            self.revert()
            raise
        self._skip_redo = True
        self._session.undo_stack.push(self)

    def _replay(self, do: Callable[[], None], rollback: Callable[[], None]) -> None:
        do()
        try:
            self._commit()
        except proj.ProjectError as exc:
            rollback()
            self._session.history_save_failed(exc)

    def redo(self) -> None:
        if self._skip_redo:
            self._skip_redo = False
            return
        self._replay(self.apply, self.revert)

    def undo(self) -> None:
        self._replay(self.revert, self.apply)


class _RemoveModels(_Command):
    def __init__(self, session: ProjectSession, ids: list[str]) -> None:
        super().__init__(session, f"Remove {len(ids)} Models" if len(ids) > 1 else "Remove Model")
        self._ids = ids
        self._removed: list[tuple[int, proj.ModelEntry]] = []

    def apply(self) -> None:
        project = self._session.require()
        self._removed = [proj.remove_model(project, model_id) for model_id in self._ids]

    def revert(self) -> None:
        project = self._session.require()
        for index, entry in reversed(self._removed):
            proj.restore_model(project, index, entry)


class _AddModels(_Command):
    def __init__(self, session: ProjectSession, entries: list[proj.ModelEntry]) -> None:
        super().__init__(session, f"Add {len(entries)} Models" if len(entries) > 1 else "Add Model")
        self._entries = entries

    def apply(self) -> None:
        project = self._session.require()
        for entry in self._entries:
            if entry not in project.models:
                project.models.append(entry)

    def revert(self) -> None:
        project = self._session.require()
        project.models[:] = [m for m in project.models if m not in self._entries]


class _AddMedium(_Command):
    models = False

    def __init__(self, session: ProjectSession, entry: proj.MediumEntry) -> None:
        super().__init__(session, "Add Medium")
        self._entry = entry

    def apply(self) -> None:
        project = self._session.require()
        if self._entry not in project.media:
            project.media.append(self._entry)

    def revert(self) -> None:
        project = self._session.require()
        project.media[:] = [m for m in project.media if m is not self._entry]


class _RenameModel(_Command):
    def __init__(self, session: ProjectSession, old: str, new: str) -> None:
        super().__init__(session, "Rename Model")
        self._old, self._new = old, new
        self._settings: dict[str, dict[str, object]] | None = None

    def apply(self) -> None:
        project = self._session.require()
        self._settings = copy.deepcopy(project.analysis_settings)
        proj.rename_model(project, self._old, self._new)

    def revert(self) -> None:
        project = self._session.require()
        project.model(self._new).id = self._old
        if self._settings is not None:
            project.analysis_settings = copy.deepcopy(self._settings)


class _SetNamespaceConfirmation(_Command):
    def __init__(self, session: ProjectSession, model_id: str, confirmed: bool) -> None:
        super().__init__(
            session, "Confirm Namespace" if confirmed else "Revoke Namespace Confirmation"
        )
        self._id, self._confirmed = model_id, confirmed
        self._before: dict[str, str] | None = None
        self._after: dict[str, str] | None = None
        self._applied = False

    def apply(self) -> None:
        entry = self._session.require().model(self._id)
        if self._applied:
            # redo: put back exactly what the first apply recorded, without re-hashing the file
            entry.namespace_confirmed = None if self._after is None else dict(self._after)
            return
        project = self._session.require()
        before = entry.namespace_confirmed
        self._before = None if before is None else dict(before)
        if self._confirmed:
            proj.confirm_namespace(project, self._id)
        else:
            proj.revoke_namespace(project, self._id)
        after = entry.namespace_confirmed
        self._after = None if after is None else dict(after)
        self._applied = True

    def revert(self) -> None:
        entry = self._session.require().model(self._id)
        entry.namespace_confirmed = None if self._before is None else dict(self._before)


class ProjectSession(QObject):
    opened = Signal()
    closed = Signal()
    models_changed = Signal()
    media_changed = Signal()
    runs_changed = Signal()
    save_failed = Signal(str)  # a save failed while undoing/redoing; the change was rolled back

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

    def attach(self, project: proj.Project, lock: proj.ProjectLock) -> None:
        """Close the current project (if any) and make `project`, locked by `lock`, current."""
        try:
            self._attach(project, lock)
        except Exception:
            with contextlib.suppress(OSError):
                lock.release()  # never keep the new project's lock when it was not attached
            raise

    @staticmethod
    def lock_and_open(root: Path) -> tuple[proj.Project, proj.ProjectLock]:
        """Lock and read a project without touching the open one (`attach` makes it current)."""
        lock = proj.ProjectLock.acquire(Path(root))
        try:
            return proj.open_project(Path(root)), lock
        except proj.ProjectError:
            lock.release()
            raise

    @staticmethod
    def create_and_lock(
        root: Path, name: str | None = None
    ) -> tuple[proj.Project, proj.ProjectLock]:
        """Create and lock a project without touching the open one (`attach` makes it current)."""
        project = proj.create_project(Path(root), name)
        return project, proj.ProjectLock.acquire(project.root)

    def open(self, root: Path) -> None:
        self.attach(*self.lock_and_open(root))

    def create(self, root: Path, name: str | None = None) -> None:
        self.attach(*self.create_and_lock(root, name))

    def close(self) -> None:
        """Save and close; the session is closed and unlocked even when the final save fails."""
        if self.project is None:
            return
        try:
            self.save()
        finally:
            lock = self._lock
            self.project, self._lock = None, None
            self.undo_stack.clear()
            try:
                if lock is not None:
                    try:
                        lock.release()
                    except OSError as exc:
                        raise proj.ProjectError(
                            f"cannot remove project lock {lock.path}: {exc}"
                        ) from exc
            finally:
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

    def history_save_failed(self, exc: proj.ProjectError) -> None:
        """Undo/redo could not save: the change was rolled back, so the history is stale."""
        QTimer.singleShot(0, self.undo_stack.clear)
        self.save_failed.emit(str(exc))

    def add_entries(self, entries: list[proj.ModelEntry]) -> None:
        if entries:
            _AddModels(self, list(entries)).execute()

    def remove_models(self, ids: list[str]) -> None:
        if not ids:
            return
        known = {m.id for m in self.require().models}
        for model_id in ids:
            if model_id not in known:
                raise proj.ProjectError(f"no model {model_id!r} in this project")
        if len(set(ids)) != len(ids):
            raise proj.ProjectError("a model can only be removed once per request")
        _RemoveModels(self, list(ids)).execute()

    def rename_model(self, old: str, new: str) -> None:
        _RenameModel(self, old, new).execute()

    def confirm_namespace(self, model_id: str) -> None:
        _SetNamespaceConfirmation(self, model_id, True).execute()

    def revoke_namespace(self, model_id: str) -> None:
        _SetNamespaceConfirmation(self, model_id, False).execute()

    def add_medium(self, entry: proj.MediumEntry) -> None:
        _AddMedium(self, entry).execute()

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
        try:
            run_dirs = list(self.project.runs_dir.iterdir())
        except OSError:
            self._run_cache.clear()
            return []  # a missing or unreadable runs/ folder is an empty list, not a crash
        entries: list[RunEntry] = []
        seen: dict[Path, tuple[float, RunEntry]] = {}
        for run_dir in run_dirs:
            try:
                if not run_dir.is_dir() or run_dir.name.startswith(("_", ".")):
                    continue
                mtime = run_dir.stat().st_mtime
            except OSError:
                continue  # vanished or unreadable while listing
            cached = self._run_cache.get(run_dir)
            if cached is None or cached[0] != mtime:
                cached = (mtime, inspect_run(run_dir))
            seen[run_dir] = cached
            entry = cached[1]
            # The marker sits in runs/_inputs, so the folder's mtime does not see it change.
            status = merge_run_status(entry.status, proj.read_run_state(run_dir))
            entries.append(entry if status == entry.status else replace(entry, status=status))
        self._run_cache = seen
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
