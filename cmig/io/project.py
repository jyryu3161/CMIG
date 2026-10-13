"""On-disk CMIG project: models, media and runs for one study (Qt-free).

A project is a folder holding ``cmig-project.json`` plus ``models/``, ``media/`` and ``runs/``.
Paths inside the JSON are project-relative so a moved project still opens; absolute paths are
computed when a run is prepared. User source files are only ever read.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from cmig.io.atomic import atomic_write_text

FORMAT_VERSION = 1
PROJECT_FILE = "cmig-project.json"
LOCK_FILE = ".cmig-project.lock"
_SUBDIRS = ("models", "media", "runs", "runs/_inputs")


class ProjectError(RuntimeError):
    """A project cannot be created, opened, locked or changed as requested."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ModelEntry:
    id: str
    file: str
    source_path: str
    sha256: str
    format: str
    added: str
    status: str = "pending"
    error: str | None = None
    n_reactions: int | None = None
    n_metabolites: int | None = None
    n_genes: int | None = None
    biomass: list[str] = field(default_factory=list)
    namespace_coverage_pct: float | None = None
    warnings: list[str] = field(default_factory=list)
    integrity: str = "ok"


@dataclass
class MediumEntry:
    id: str
    file: str
    source_path: str
    sha256: str
    added: str
    integrity: str = "ok"


@dataclass
class Project:
    root: Path
    name: str
    created: str
    models: list[ModelEntry] = field(default_factory=list)
    media: list[MediumEntry] = field(default_factory=list)
    analysis_settings: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def project_file(self) -> Path:
        return self.root / PROJECT_FILE

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def media_dir(self) -> Path:
        return self.root / "media"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def inputs_dir(self) -> Path:
        return self.root / "runs" / "_inputs"

    def model(self, model_id: str) -> ModelEntry:
        for entry in self.models:
            if entry.id == model_id:
                return entry
        raise ProjectError(f"no model {model_id!r} in this project")

    def medium(self, medium_id: str) -> MediumEntry:
        for entry in self.media:
            if entry.id == medium_id:
                return entry
        raise ProjectError(f"no medium {medium_id!r} in this project")


def _payload(project: Project) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "name": project.name,
        "created": project.created,
        "models": [asdict(entry) for entry in project.models],
        "media": [asdict(entry) for entry in project.media],
        "analysis_settings": project.analysis_settings,
    }


def save_project(project: Project) -> None:
    """Atomically publish ``cmig-project.json``; the previous file survives any failure."""
    text = json.dumps(_payload(project), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    atomic_write_text(project.project_file, text)


def create_project(root: Path, name: str | None = None) -> Project:
    """Create a new project folder (absent or empty) and write its first project file."""
    root = Path(root).expanduser().resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise ProjectError(f"project folder is not empty: {root}")
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    project = Project(root=root, name=(name or root.name).strip() or root.name, created=_now())
    save_project(project)
    return project


def _model_from_json(raw: dict[str, Any]) -> ModelEntry:
    known = {name for name in ModelEntry.__dataclass_fields__}
    return ModelEntry(**{key: value for key, value in raw.items() if key in known})


def _medium_from_json(raw: dict[str, Any]) -> MediumEntry:
    known = {name for name in MediumEntry.__dataclass_fields__}
    return MediumEntry(**{key: value for key, value in raw.items() if key in known})


def _check_entries(root: Path, label: str, items: object) -> list[dict[str, Any]]:
    """Validate the shape of a ``models``/``media`` list; return it, or raise ``ValueError``.

    ``id`` and ``file`` must be strings, ids are unique within the list, and ``file`` must be a
    relative path that stays inside the project. Absolute paths are rejected for either path
    flavour (a project may be moved between Windows and POSIX); ``..`` is judged after
    resolution, so a symlink leading out of the project is rejected too.
    """
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{label} entry is not an object: {item!r}")
        entry_id, file = item.get("id"), item.get("file")
        if not isinstance(entry_id, str) or not isinstance(file, str):
            raise ValueError(f"{label} entry needs string 'id' and 'file': {item!r}")
        if entry_id in seen:
            raise ValueError(f"duplicate {label} id {entry_id!r}")
        seen.add(entry_id)
        if PurePosixPath(file).anchor or PureWindowsPath(file).anchor:
            raise ValueError(f"{label} {entry_id!r} file must be project-relative: {file!r}")
        try:
            target = (root / file).resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            raise ValueError(f"{label} {entry_id!r} has an unusable file path {file!r}") from exc
        if target == root or not target.is_relative_to(root):
            raise ValueError(f"{label} {entry_id!r} file leaves the project: {file!r}")
    return items


def open_project(root: Path) -> Project:
    """Read and validate a project; refuses corrupt or newer formats without writing anything."""
    root = Path(root).expanduser().resolve()
    path = root / PROJECT_FILE
    if not path.is_file():
        raise ProjectError(f"no cmig-project.json in {root}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProjectError(f"cannot read {path}: {exc}") from exc
    except (ValueError, RecursionError) as exc:
        raise ProjectError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProjectError(f"{path} is not a JSON object")
    version = raw.get("format_version")
    if isinstance(version, int) and version > FORMAT_VERSION:
        raise ProjectError(
            f"{path} was written by a newer CMIG (format {version}); this version reads "
            f"format {FORMAT_VERSION}"
        )
    missing = [key for key in ("format_version", "name", "created") if key not in raw]
    if version != FORMAT_VERSION or missing:
        raise ProjectError(f"{path} is missing required fields: {missing or ['format_version']}")
    try:
        models = _check_entries(root, "models", raw.get("models", []))
        media = _check_entries(root, "media", raw.get("media", []))
        settings = raw.get("analysis_settings", {})
        if not isinstance(settings, dict) or not all(
            isinstance(value, dict) for value in settings.values()
        ):
            raise ValueError("analysis_settings must be an object of objects")
        project = Project(
            root=root,
            name=str(raw["name"]),
            created=str(raw["created"]),
            models=[_model_from_json(item) for item in models],
            media=[_medium_from_json(item) for item in media],
            analysis_settings=settings,
        )
    except (TypeError, ValueError) as exc:
        raise ProjectError(f"{path} has malformed entries: {exc}") from exc
    try:
        for sub in _SUBDIRS:
            (root / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(f"cannot prepare project folders in {root}: {exc}") from exc
    return project


def _pid_alive(pid: int) -> bool:
    """Whether ``pid`` may still be running; ``True`` whenever that cannot be established."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        if pid > 0xFFFFFFFF:  # not a DWORD: ctypes would silently truncate it
            return True
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OverflowError, OSError):  # includes PermissionError: the process exists
        return True
    return True


def _read_lock(path: Path) -> dict[str, Any]:
    """Return the lock owner record, or ``{}`` if the file is unreadable or not an object."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return held if isinstance(held, dict) else {}


class ProjectLock:
    """Exclusive per-project lock file holding the owner's pid and host."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def acquire(cls, root: Path) -> ProjectLock:
        path = Path(root).resolve() / LOCK_FILE
        payload = json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created": _now()})
        for _attempt in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                held = _read_lock(path)
                host = str(held.get("host", "unknown host"))
                pid = held.get("pid")
                # Only a well-formed lock from a dead process on this host is reclaimed; an
                # empty or garbage lock is reported, never silently taken over.
                if (
                    host == socket.gethostname()
                    and isinstance(pid, int)
                    and not isinstance(pid, bool)
                    and pid > 0
                    and not _pid_alive(pid)
                ):
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as exc:
                        raise ProjectError(
                            f"cannot replace stale project lock {path}: {exc}"
                        ) from exc
                    continue
                owner = f"pid {pid} on {host}" if held else "owner unknown"
                raise ProjectError(
                    f"this project is already open in another window ({owner}); if no other "
                    f"CMIG window has it open, delete {path}"
                ) from None
            except OSError as exc:
                raise ProjectError(f"cannot create project lock {path}: {exc}") from exc
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
            except OSError as exc:
                with contextlib.suppress(OSError):
                    path.unlink(missing_ok=True)
                raise ProjectError(f"cannot write project lock {path}: {exc}") from exc
            return cls(path)
        raise ProjectError(f"could not acquire project lock {path}")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)
