"""On-disk CMIG project: models, media and runs for one study (Qt-free).

A project is a folder holding ``cmig-project.json`` plus ``models/``, ``media/`` and ``runs/``.
Paths inside the JSON are project-relative so a moved project still opens; absolute paths are
computed when a run is prepared. User source files are only ever read.
"""

from __future__ import annotations

import contextlib
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import socket
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, BinaryIO

from cmig.core.model_pool import is_supported_model_file, member_id_from_path
from cmig.io.atomic import atomic_write_binary, atomic_write_text

FORMAT_VERSION = 1
PROJECT_FILE = "cmig-project.json"
LOCK_FILE = ".cmig-project.lock"
_SUBDIRS = ("models", "media", "runs", "runs/_inputs")
MEDIUM_SUFFIXES = (".csv", ".json")
_MODEL_SUFFIXES = (".xml.gz", ".sbml.gz", ".xml", ".sbml", ".json", ".mat")
_ID_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KIND_RE = re.compile(r"[a-z][a-z0-9_-]*")
_RUNNABLE_STATUSES = ("ok", "warning")


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
    try:
        atomic_write_text(project.project_file, text)
    except OSError as exc:
        raise ProjectError(f"cannot save {project.project_file}: {exc}") from exc


def create_project(root: Path, name: str | None = None) -> Project:
    """Create a new project folder (absent or empty) and write its first project file."""
    requested = Path(root)
    try:
        root = requested.expanduser().resolve()
        occupied = root.exists() and (not root.is_dir() or any(root.iterdir()))
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f"cannot create project in {requested}: {exc}") from exc
    if occupied:
        raise ProjectError(f"project folder is not empty: {root}")
    try:
        for sub in _SUBDIRS:
            (root / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProjectError(f"cannot create project in {root}: {exc}") from exc
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
    requested = Path(root)
    try:
        root = requested.expanduser().resolve()
        path = root / PROJECT_FILE
        is_file = path.is_file()
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f"cannot open project folder {requested}: {exc}") from exc
    if not is_file:
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
    verify_checksums(project)
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


class DuplicateModelError(ProjectError):
    def __init__(self, existing_id: str) -> None:
        super().__init__(f"this file is already in the project as {existing_id!r}")
        self.existing_id = existing_id


@dataclass(frozen=True)
class ModelCheck:
    status: str
    error: str | None
    n_reactions: int | None
    n_metabolites: int | None
    n_genes: int | None
    biomass: list[str]
    namespace_coverage_pct: float | None
    warnings: list[str]


def check_model_file(path: Path) -> ModelCheck:
    """Read a GEM with the existing importer and review; never raises."""
    from cmig.io.model_import import build_import_review, import_model

    try:
        summary = import_model(path)
        review = build_import_review(summary)
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
        return ModelCheck("failed", f"{type(exc).__name__}: {exc}", None, None, None, [], None, [])
    warnings = [str(w) for w in review.warnings]
    coverage = review.namespace.get("coverage_pct")
    return ModelCheck(
        status="warning" if warnings else "ok",
        error=None,
        n_reactions=summary.n_reactions,
        n_metabolites=summary.n_metabolites,
        n_genes=summary.n_genes,
        biomass=list(summary.biomass_reactions),
        namespace_coverage_pct=None if coverage is None else float(coverage),
        warnings=warnings,
    )


def apply_check(entry: ModelEntry, check: ModelCheck) -> None:
    entry.status = check.status
    entry.error = check.error
    entry.n_reactions = check.n_reactions
    entry.n_metabolites = check.n_metabolites
    entry.n_genes = check.n_genes
    entry.biomass = list(check.biomass)
    entry.namespace_coverage_pct = check.namespace_coverage_pct
    entry.warnings = list(check.warnings)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum(path: Path) -> str:
    """``_sha256`` for a file the user handed us: a read failure is a ``ProjectError``."""
    try:
        return _sha256(path)
    except OSError as exc:
        raise ProjectError(f"cannot read {path}: {exc}") from exc


def _resolve_source(source: Path) -> Path:
    try:
        return Path(source).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ProjectError(f"cannot read {source}: {exc}") from exc


def _integrity(path: Path, sha256: str) -> str:
    """``ok`` / ``changed`` / ``missing`` for one project copy; an unreadable copy is missing."""
    try:
        if not path.is_file():
            return "missing"
        return "ok" if _sha256(path) == sha256 else "changed"
    except OSError:
        return "missing"


def _split_suffix(name: str, suffixes: Iterable[str]) -> tuple[str, str]:
    lower = name.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return name[: -len(suffix)], name[-len(suffix):]
    return Path(name).stem, Path(name).suffix


def _free_name(folder: Path, stem: str, suffix: str) -> Path:
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._") or "file"
    candidate = folder / f"{safe_stem}{suffix}"
    n = 2
    try:
        while candidate.exists():
            candidate = folder / f"{safe_stem}-{n}{suffix}"
            n += 1
    except OSError as exc:
        raise ProjectError(f"cannot inspect {folder}: {exc}") from exc
    return candidate


def _copy_into(source: Path, target: Path) -> None:
    def write(handle: BinaryIO) -> None:
        with source.open("rb") as src:
            shutil.copyfileobj(src, handle, 1 << 20)

    try:
        atomic_write_binary(target, write)
    except OSError as exc:
        raise ProjectError(f"could not copy {source} into the project: {exc}") from exc


def _safe_id(text: str) -> str:
    """Same id rules as model member ids: letters, digits, _; starts with a letter or _."""
    value = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_") or "item"
    return value if re.match(r"^[A-Za-z_]", value) else f"m_{value}"


def _unique_id(taken: set[str], base: str, sha: str) -> str:
    if base not in taken:
        return base
    candidate = f"{base}_{sha[:8]}"
    n = 2
    while candidate in taken:
        candidate = f"{base}_{sha[:8]}_{n}"
        n += 1
    return candidate


def add_model_file(
    project: Project,
    source: Path,
    *,
    check: Callable[[Path], ModelCheck] | None = check_model_file,
) -> ModelEntry:
    """Copy one GEM into ``models/`` and register it (caller saves the project)."""
    source = _resolve_source(source)
    try:
        supported = is_supported_model_file(source)
    except OSError as exc:
        raise ProjectError(f"cannot read {source}: {exc}") from exc
    if not supported:
        raise ProjectError(f"not a supported model file: {source.name}")
    sha = _checksum(source)
    for entry in project.models:
        if entry.sha256 == sha:
            raise DuplicateModelError(entry.id)
    stem, suffix = _split_suffix(source.name, _MODEL_SUFFIXES)
    target = _free_name(project.models_dir, stem, suffix)
    _copy_into(source, target)
    if _checksum(target) != sha:
        with contextlib.suppress(OSError):
            target.unlink(missing_ok=True)
        raise ProjectError(f"copy of {source.name} does not match its source checksum")
    entry = ModelEntry(
        id=_unique_id({m.id for m in project.models}, member_id_from_path(source), sha),
        file=target.relative_to(project.root).as_posix(),
        source_path=str(source),
        sha256=sha,
        format=suffix.lstrip(".").lower(),
        added=_now(),
    )
    if check is not None:
        apply_check(entry, check(target))
    project.models.append(entry)
    return entry


def add_medium_file(project: Project, source: Path) -> MediumEntry:
    source = _resolve_source(source)
    try:
        is_file = source.is_file()
    except OSError as exc:
        raise ProjectError(f"cannot read {source}: {exc}") from exc
    if source.suffix.lower() not in MEDIUM_SUFFIXES or not is_file:
        raise ProjectError(f"a medium must be a CSV or JSON file: {source.name}")
    sha = _checksum(source)
    for entry in project.media:
        if entry.sha256 == sha:
            raise ProjectError(f"this medium is already in the project as {entry.id!r}")
    target = _free_name(project.media_dir, source.stem, source.suffix.lower())
    _copy_into(source, target)
    taken = {m.id for m in project.media}
    medium = MediumEntry(
        id=_unique_id(taken, _safe_id(source.stem), sha),
        file=target.relative_to(project.root).as_posix(),
        source_path=str(source),
        sha256=sha,
        added=_now(),
    )
    project.media.append(medium)
    return medium


def remove_model(project: Project, model_id: str) -> tuple[int, ModelEntry]:
    entry = project.model(model_id)
    index = project.models.index(entry)
    project.models.pop(index)
    return index, entry


def restore_model(project: Project, index: int, entry: ModelEntry) -> None:
    project.models.insert(min(index, len(project.models)), entry)


def rename_model(project: Project, model_id: str, new_id: str) -> None:
    """Rename a model and every remembered analysis selection of it (`models` id lists)."""
    entry = project.model(model_id)
    if not _ID_RE.fullmatch(new_id):
        raise ProjectError("a model id starts with a letter or _ and uses letters, digits, _")
    if any(m.id == new_id for m in project.models if m is not entry):
        raise ProjectError(f"another model already uses the id {new_id!r}")
    entry.id = new_id
    for values in project.analysis_settings.values():
        chosen = values.get("models")
        if isinstance(chosen, list) and model_id in chosen:
            values["models"] = [new_id if item == model_id else item for item in chosen]


def model_path(project: Project, entry: ModelEntry) -> Path:
    return project.root / entry.file


def medium_path(project: Project, entry: MediumEntry) -> Path:
    return project.root / entry.file


def verify_checksums(project: Project) -> list[str]:
    """Recompute sha256 of every copy; mark ``changed``/``missing`` and return those ids.

    A copy that cannot be read counts as ``missing``: it cannot be used for a run either way.
    """
    changed: list[str] = []
    items: list[ModelEntry | MediumEntry] = [*project.models, *project.media]
    for item in items:
        item.integrity = _integrity(project.root / item.file, item.sha256)
        if item.integrity != "ok":
            changed.append(item.id)
    return changed


def refresh_integrity(project: Project, entry: ModelEntry | MediumEntry) -> str:
    """Re-hash one project copy now and store the result on it (``ok``/``changed``/``missing``).

    For inputs a run passes as a single path (``--host``, ``--model``, ``--medium``), the same
    check ``write_run_taxonomy`` applies to every taxonomy row.
    """
    entry.integrity = _integrity(project.root / entry.file, entry.sha256)
    return entry.integrity


def selectable_models(project: Project) -> list[ModelEntry]:
    return [
        m for m in project.models if m.status in _RUNNABLE_STATUSES and m.integrity == "ok"
    ]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def new_run_dir(project: Project, kind: str) -> Path:
    if not _KIND_RE.fullmatch(kind):
        raise ProjectError(f"invalid run kind {kind!r}")
    base = f"{kind}-{_stamp()}"
    n = 1
    while True:
        candidate = project.runs_dir / (base if n == 1 else f"{base}-{n}")
        try:
            candidate.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            n += 1
            continue
        except OSError as exc:
            raise ProjectError(f"cannot create run folder {candidate}: {exc}") from exc
        return candidate


def _abundance(model_id: str, value: object) -> float:
    number = math.nan
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        with contextlib.suppress(OverflowError):  # an int too large for a float
            number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ProjectError(
            f"abundance for {model_id!r} must be a finite number greater than 0, got {value!r}"
        )
    return number


def write_run_taxonomy(
    project: Project,
    run_dir: Path,
    model_ids: list[str],
    abundances: dict[str, float] | None = None,
) -> Path:
    """Write ``runs/_inputs/<run>-taxonomy.csv`` (id,file,abundance) for the CLI.

    Each chosen model's copy is re-hashed first (``integrity`` is refreshed), so a file edited
    since the project was opened cannot reach a run.
    """
    if not model_ids:
        raise ProjectError("no models selected for this run")
    duplicates = sorted(m for m, count in Counter(model_ids).items() if count > 1)
    if duplicates:
        raise ProjectError(f"duplicate model ids in this run: {', '.join(map(repr, duplicates))}")
    stray = sorted(set(abundances or {}) - set(model_ids))
    if stray:
        raise ProjectError(
            f"abundances given for models not in this run: {', '.join(map(repr, stray))}"
        )
    by_id = {m.id: m for m in project.models}
    problems: list[str] = []
    rows: list[list[str]] = []
    for model_id in model_ids:
        entry = by_id.get(model_id)
        if entry is None:
            problems.append(f"model {model_id!r} is not selectable: no such model in this project")
            continue
        entry.integrity = _integrity(model_path(project, entry), entry.sha256)
        if entry.integrity == "changed":
            problems.append(
                f"model {model_id!r} is not selectable: its file changed since it was added"
            )
        elif entry.integrity == "missing":
            problems.append(f"model {model_id!r} is not selectable: its file is missing")
        elif entry.status not in _RUNNABLE_STATUSES:
            problems.append(
                f"model {model_id!r} is not selectable: its check status is {entry.status!r}"
            )
        else:
            abundance = _abundance(model_id, (abundances or {}).get(model_id, 1.0))
            rows.append([model_id, str(model_path(project, entry)), repr(abundance)])
    if problems:
        raise ProjectError("; ".join(problems))
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "file", "abundance"])
    writer.writerows(rows)
    path = project.inputs_dir / f"{Path(run_dir).name}-taxonomy.csv"
    try:
        atomic_write_text(path, buffer.getvalue())
    except OSError as exc:
        raise ProjectError(f"cannot write run inputs {path}: {exc}") from exc
    return path


#: how a job can end without a result; the only states a run marker may record
RUN_STATE_STATUSES = ("failed", "cancelled")


def run_state_path(run_dir: Path) -> Path:
    """``runs/_inputs/<run>-state.json``: beside the run's inputs, never inside the CLI's folder."""
    run_dir = Path(run_dir)
    return run_dir.parent / "_inputs" / f"{run_dir.name}-state.json"


def write_run_state(run_dir: Path, status: str, job_kind: str) -> Path:
    """Record that the job writing ``run_dir`` ended ``failed`` or ``cancelled``.

    The marker lets a later session list the folder as failed or cancelled instead of unknown.
    It only ever records a bad ending: it never makes a run look better than its own summary.
    """
    if status not in RUN_STATE_STATUSES:
        raise ProjectError(f"a run state must be one of {RUN_STATE_STATUSES}, got {status!r}")
    if not Path(run_dir).is_dir():
        raise ProjectError(f"run folder {run_dir} does not exist")
    path = run_state_path(run_dir)
    payload = {"status": status, "job_kind": job_kind, "recorded": _now()}
    try:
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
    except OSError as exc:
        raise ProjectError(f"cannot record the state of {run_dir}: {exc}") from exc
    return path


def read_run_state(run_dir: Path) -> str | None:
    """``failed`` or ``cancelled`` when a marker says so; anything else is no marker."""
    try:
        payload = json.loads(run_state_path(run_dir).read_text())
    except (OSError, ValueError):
        return None
    status = payload.get("status") if isinstance(payload, dict) else None
    return status if status in RUN_STATE_STATUSES else None


def _files_under(folder: Path, recursive: bool) -> list[Path]:
    """Sorted files in ``folder``; an unreadable folder (or subfolder) raises ``ProjectError``."""

    def fail(exc: OSError) -> None:
        raise ProjectError(
            f"cannot read folder {exc.filename or folder}: {exc.strerror or exc}"
        ) from exc

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder, onerror=fail):
        files.extend(Path(dirpath) / name for name in filenames)
        if not recursive:
            dirnames.clear()
    return sorted(files)


def supported_model_paths(
    paths: list[Path], *, recursive: bool = True
) -> tuple[list[Path], int]:
    """Expand files and folders to supported GEM files; count everything skipped."""
    found: list[Path] = []
    skipped = 0
    for raw in paths:
        path = Path(raw)
        try:
            if path.is_dir():
                for item in _files_under(path, recursive):
                    if not item.is_file():
                        continue
                    if item.name.startswith(".") or not is_supported_model_file(item):
                        skipped += 1
                    else:
                        found.append(item)
            elif (
                path.is_file()
                and not path.name.startswith(".")
                and is_supported_model_file(path)
            ):
                found.append(path)
            else:
                skipped += 1
        except OSError as exc:
            raise ProjectError(f"cannot read {path}: {exc}") from exc
    return found, skipped
