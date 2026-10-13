"""On-disk CMIG project: models, media and runs for one study (Qt-free).

A project is a folder holding ``cmig-project.json`` plus ``models/``, ``media/`` and ``runs/``.
Paths inside the JSON are project-relative so a moved project still opens; absolute paths are
computed when a run is prepared. User source files are only ever read.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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


def open_project(root: Path) -> Project:
    """Read and validate a project; refuses corrupt or newer formats without writing anything."""
    root = Path(root).expanduser().resolve()
    path = root / PROJECT_FILE
    if not path.is_file():
        raise ProjectError(f"no cmig-project.json in {root}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
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
        project = Project(
            root=root,
            name=str(raw["name"]),
            created=str(raw["created"]),
            models=[_model_from_json(item) for item in raw.get("models", [])],
            media=[_medium_from_json(item) for item in raw.get("media", [])],
            analysis_settings=dict(raw.get("analysis_settings", {})),
        )
    except (TypeError, AttributeError) as exc:
        raise ProjectError(f"{path} has malformed entries: {exc}") from exc
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    return project


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


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
                try:
                    held = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    held = {}
                host = str(held.get("host", "unknown host"))
                pid = held.get("pid")
                if host == socket.gethostname() and isinstance(pid, int) and not _pid_alive(pid):
                    path.unlink(missing_ok=True)
                    continue
                raise ProjectError(
                    f"this project is already open in another window (pid {pid} on {host}); "
                    f"close it there first"
                ) from None
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return cls(path)
        raise ProjectError(f"could not acquire project lock {path}")

    def release(self) -> None:
        self.path.unlink(missing_ok=True)
