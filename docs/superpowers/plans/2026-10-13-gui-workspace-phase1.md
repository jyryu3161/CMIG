# GUI 작업 공간 개편 1단계 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CMIG 데스크톱 GUI를 디스크 프로젝트(모델·배지·실행 기록) 중심의 작업 공간으로 바꾼다. 구성 요소는 표준 메뉴, 툴바, 사이드바, 상세 패널, 작업 창이고, 모델은 여러 개를 한 번에 가져오며 모든 분석이 프로젝트 모델 목록에서 모델을 고른다.

**Architecture:** Qt 없는 `cmig/io/project.py`가 프로젝트 폴더 형식을 맡는다. 형식, 잠금, 모델 복사·checksum·점검, run 폴더, run 입력 taxonomy가 여기에 들어간다. GUI 쪽은 다음 파일들로 나눈다.
- `cmig/gui/project_session.py`: Qt 신호와 Undo를 감싼다.
- `sidebar.py`, `inspector.py`, `activity.py`, `pickers.py`, `agora2_dialog.py`: 화면 부품
- `app.py`의 `CmigMainWindow`: 위 부품을 조립하고 메뉴·툴바·가운데 화면 전환을 맡는다.

분석 실행 경로(CLI argv → `JobRunner` → `cmig.cli.main.main`)는 그대로다. 모델 폴더 대신 프로젝트 모델로 만든 `--taxonomy`를 넘기고, 출력은 프로젝트 `runs/`로 보낸다.

**Tech Stack:** Python 3.10–3.12, PySide6(Qt 6: `QUndoStack`은 `PySide6.QtGui`), pytest(offscreen Qt), `uv run --no-sync`.

**Spec:** `docs/superpowers/specs/2026-10-13-gui-workspace-phase1-design.md`

## Global Constraints

- GUI는 과학 계산을 하지 않는다. 모든 분석은 CLI argv → `JobRunner` → `cmig.cli.main.main`으로 실행한다. CLI 옵션, `run_hash`, envelope, 산출물은 바꾸지 않는다.
- 사용자 원본 GEM·배지 파일은 읽기만 한다. 프로젝트 파일 쓰기는 `cmig.io.atomic`(`atomic_write_text`, `atomic_write_binary`)로 한다.
- `cmig/io/project.py`는 `cmig.gui`, `cmig.cli`, `cmig.service`, PySide6를 import하지 않는다. 네트워크 코드도 넣지 않는다(AGORA2는 CLI `agora2-fetch` 경유).
- 프로젝트 형식: 파일 이름 `cmig-project.json`, `format_version: 1`, 하위 폴더 `models/`, `media/`, `runs/`, `runs/_inputs/`, 잠금 파일 `.cmig-project.lock`
- run 폴더 이름은 `<kind>-YYYYMMDD-HHMMSS[-N]`이며 기존 폴더를 재사용하지 않는다. run 입력 taxonomy는 `runs/_inputs/<run 이름>-taxonomy.csv`이고 열은 `id,file,abundance`이다.
- 새 UI 문구는 영어만 쓴다. `I18N` 새 키는 `"en"`과 `"ko"`에 같은 영어 문구로 넣는다.
- strict mypy(`graph_view.py` 제외), Ruff(line 100, `E,F,I,B,UP,TID`), pickle 금지
- 실패·non-viable·취소·checksum 문제를 성공처럼 표시하지 않는다.
- main window 전체가 1280×800·1500×950을 넘어 강제로 커지면 안 된다.
- GUI 테스트는 `QT_QPA_PLATFORM=offscreen`에서 돌린다. 새 GUI 테스트 파일은 `from gui_project_helpers import _deterministic_qt_teardown`으로 autouse teardown fixture를 가져온다. `tests/`에는 `__init__.py`가 없고 pytest가 `tests/`를 `sys.path`에 넣으므로 `tests.` 접두 없이 import한다.
- 커밋은 기능 브랜치 `gui-workspace-phase1`에만 한다. 메시지 끝에 다음 두 줄을 붙인다:
  ```
  Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX
  ```

## Review Focus

1. 같은 파일 이름(stem)이 다른 폴더에서 여러 개 들어오거나, 이름에 공백·한글·점이 들어 있어도 모델 id가 유일하고 taxonomy가 유효해야 한다. → Task 2 `test_ids_unique_for_same_stem_and_odd_names`
2. 프로젝트 폴더를 통째로 다른 위치로 옮긴 뒤 열어도 모델·배지·run 입력이 동작해야 한다(상대 경로 저장, 실행 시 절대 경로 계산). → Task 2 `test_project_survives_move`
3. 모델 200개를 한 번에 가져올 때도 화면이 멈추지 않고 진행이 보이며, 작업 창의 Cancel이 남은 파일 처리를 멈춰야 한다. → Task 7 `test_import_reports_progress_and_cancel_stops_remaining`
4. 쓰기 권한 없는 위치나 복사 중 오류: 부분 사본이 남지 않고, 다른 파일은 계속되고, 사유가 보여야 한다. → Task 2 `test_copy_failure_leaves_no_partial_file`
5. 모델 파일이 아닌 것(`.txt`, cobra JSON이 아닌 `.json`, 숨김 파일)이 섞인 폴더를 끌어다 놓으면 건너뛰고 몇 개를 건너뛰었는지 알려야 한다. → Task 4 `test_drop_filters_unsupported_and_reports_skipped`

---

## 파일 구조

| 파일 | 책임 |
|---|---|
| `cmig/io/project.py` (새) | 프로젝트 형식·저장·열기·잠금, 모델/배지 추가(복사·sha256·id), 점검(`check_model_file`), checksum 재확인, run 폴더·taxonomy |
| `cmig/gui/project_session.py` (새) | `ProjectSession(QObject)`: 열린 프로젝트, 변경 신호, `QUndoStack`, run 목록 스캔(`RunEntry`), 최근 프로젝트(`RecentProjects`) |
| `cmig/gui/sidebar.py` (새) | `WorkspaceSidebar(QTreeWidget)`: MODELS/MEDIA/ANALYSES/RUNS, 상태 아이콘, 여러 개 선택, 우클릭 메뉴, 끌어다 놓기. `droppable_paths()` |
| `cmig/gui/inspector.py` (새) | `InspectorPanel`: 모델·배지·run·분석 상세, exchange 검색, Copy Command, Show in Finder |
| `cmig/gui/activity.py` (새) | `ActivityPane`: 기존 `RuntimeJobsPanel` + Cancel + 로그 + `cmig` 명령 |
| `cmig/gui/pickers.py` (새) | `ModelPicker`(여러 개/하나 선택), `MediumPicker`(model default / preset / 프로젝트 배지) |
| `cmig/gui/agora2_dialog.py` (새) | AGORA2 카탈로그 검색·선택 창 |
| `cmig/gui/app.py` | 메뉴·툴바·가운데 `QStackedWidget`·빈 화면·창 조립, 탭/Explorer 제거, 분석 run의 입력·출력 연결 |
| `cmig/gui/builder.py`, `host_view.py`, `views.py`, `editors.py` | 모델·배지·출력 입력칸을 선택기로 교체, 잘리는 줄 정리 |
| `tests/test_project_io.py` (새) | `cmig/io/project.py` 단위 테스트 |
| `tests/gui_project_helpers.py` (새) | GUI 테스트용 프로젝트·가짜 모델 생성 |
| `tests/test_workspace_*.py` (새) | 각 GUI 부품·흐름 테스트 |
| 기존 GUI 테스트 | 탭·Explorer·폴더 입력에 기대는 부분을 새 구조로 옮김 |
| 문서 | `docs/USER_GUIDE.md`, `CHANGELOG.md`, `docs/tracking/status.md`, `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md` |

---

### Task 0: 브랜치 준비

- [ ] **Step 1: 기능 브랜치 만들기**

Run:
```bash
cd /Users/jaeyongryu/Projects/CMIG && git status --short && git checkout -b gui-workspace-phase1
```
Expected: 작업 트리가 깨끗하고(`docs/superpowers/` 아래 새 문서만 untracked), 새 브랜치로 전환된다.

- [ ] **Step 2: 설계·계획 문서 커밋**

```bash
git add docs/superpowers/specs/2026-10-13-gui-workspace-phase1-design.md docs/superpowers/plans/2026-10-13-gui-workspace-phase1.md
git commit -m "docs: GUI workspace phase-1 design and plan

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 1: 프로젝트 형식·저장·열기·잠금 (`cmig/io/project.py` 1부)

**Files:**
- Create: `cmig/io/project.py`
- Test: `tests/test_project_io.py`

**Interfaces:**
- Produces:
  - `FORMAT_VERSION: int = 1`, `PROJECT_FILE = "cmig-project.json"`, `LOCK_FILE = ".cmig-project.lock"`
  - `class ProjectError(RuntimeError)`
  - `@dataclass class ModelEntry`: `id: str, file: str, source_path: str, sha256: str, format: str, added: str, status: str = "pending", error: str | None = None, n_reactions: int | None = None, n_metabolites: int | None = None, n_genes: int | None = None, biomass: list[str] = [], namespace_coverage_pct: float | None = None, warnings: list[str] = [], integrity: str = "ok"`
  - `@dataclass class MediumEntry`: `id: str, file: str, source_path: str, sha256: str, added: str, integrity: str = "ok"`
  - `@dataclass class Project`: `root: Path, name: str, created: str, models: list[ModelEntry], media: list[MediumEntry], analysis_settings: dict[str, dict[str, object]]`. 속성 `models_dir`, `media_dir`, `runs_dir`, `inputs_dir`, `project_file`. 메서드 `model(id) -> ModelEntry`, `medium(id) -> MediumEntry`.
  - `create_project(root: Path, name: str | None = None) -> Project`
  - `open_project(root: Path) -> Project`(checksum 재확인 포함, 잠금 없음)
  - `save_project(project: Project) -> None`
  - `class ProjectLock`: `acquire(root: Path) -> ProjectLock`(classmethod), `release() -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_project_io.py`:
```python
"""Qt-free tests for the on-disk CMIG project format."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from cmig.io import project as proj


def test_create_writes_layout_and_reopens(tmp_path: Path) -> None:
    root = tmp_path / "study"
    created = proj.create_project(root, name="Butyrate study")
    assert (root / "cmig-project.json").is_file()
    for sub in ("models", "media", "runs", "runs/_inputs"):
        assert (root / sub).is_dir()
    reopened = proj.open_project(root)
    assert reopened.name == "Butyrate study"
    assert reopened.created == created.created
    assert reopened.models == [] and reopened.media == []
    payload = json.loads((root / "cmig-project.json").read_text())
    assert payload["format_version"] == 1


def test_create_refuses_non_empty_folder(tmp_path: Path) -> None:
    root = tmp_path / "busy"
    root.mkdir()
    (root / "notes.txt").write_text("mine")
    with pytest.raises(proj.ProjectError, match="not empty"):
        proj.create_project(root)
    assert (root / "notes.txt").read_text() == "mine"
    assert not (root / "cmig-project.json").exists()


def test_create_defaults_name_to_folder(tmp_path: Path) -> None:
    assert proj.create_project(tmp_path / "gut-2026").name == "gut-2026"


@pytest.mark.parametrize(
    "content, message",
    [
        ("{not json", "not valid JSON"),
        ('{"format_version": 99, "name": "x"}', "newer CMIG"),
        ('{"format_version": 1}', "missing"),
        ("[]", "not a JSON object"),
    ],
)
def test_open_rejects_bad_project_without_touching_it(
    tmp_path: Path, content: str, message: str
) -> None:
    root = tmp_path / "bad"
    root.mkdir()
    (root / "cmig-project.json").write_text(content)
    with pytest.raises(proj.ProjectError, match=message):
        proj.open_project(root)
    assert (root / "cmig-project.json").read_text() == content


def test_open_missing_project_file(tmp_path: Path) -> None:
    with pytest.raises(proj.ProjectError, match="no cmig-project.json"):
        proj.open_project(tmp_path)


def test_save_is_atomic_and_round_trips_settings(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "s")
    project.analysis_settings["search"] = {"models": ["a", "b"], "medium": "preset:western"}
    proj.save_project(project)
    again = proj.open_project(tmp_path / "s")
    assert again.analysis_settings == {"search": {"models": ["a", "b"], "medium": "preset:western"}}
    leftovers = [p.name for p in (tmp_path / "s").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_lock_blocks_second_open_and_releases(tmp_path: Path) -> None:
    root = tmp_path / "locked"
    proj.create_project(root)
    lock = proj.ProjectLock.acquire(root)
    with pytest.raises(proj.ProjectError, match="already open"):
        proj.ProjectLock.acquire(root)
    lock.release()
    assert not (root / ".cmig-project.lock").exists()
    proj.ProjectLock.acquire(root).release()


def test_stale_lock_from_dead_process_is_replaced(tmp_path: Path) -> None:
    root = tmp_path / "stale"
    proj.create_project(root)
    (root / ".cmig-project.lock").write_text(
        json.dumps({"pid": 2**22 + 12345, "host": socket.gethostname(), "created": "x"})
    )
    lock = proj.ProjectLock.acquire(root)
    held = json.loads((root / ".cmig-project.lock").read_text())
    assert held["pid"] == os.getpid()
    lock.release()


def test_lock_from_other_host_is_respected(tmp_path: Path) -> None:
    root = tmp_path / "remote"
    proj.create_project(root)
    (root / ".cmig-project.lock").write_text(
        json.dumps({"pid": 1, "host": "some-other-machine", "created": "x"})
    )
    with pytest.raises(proj.ProjectError, match="some-other-machine"):
        proj.ProjectLock.acquire(root)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_project_io.py`
Expected: FAIL. `ImportError: cannot import name 'project' from 'cmig.io'` 또는 `ModuleNotFoundError`.

- [ ] **Step 3: 구현**

`cmig/io/project.py`:
```python
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
        payload = json.dumps(
            {"pid": os.getpid(), "host": socket.gethostname(), "created": _now()}
        )
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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_project_io.py && uv run --no-sync mypy cmig/io/project.py && uv run --no-sync ruff check cmig/io/project.py tests/test_project_io.py`
Expected: 모든 테스트 PASS, mypy·ruff 오류 없음.

- [ ] **Step 5: 커밋**

```bash
git add cmig/io/project.py tests/test_project_io.py
git commit -m "feat(io): on-disk CMIG project format with lock

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 2: 모델·배지 추가, 점검, checksum, run 폴더·taxonomy (`cmig/io/project.py` 2부)

**Files:**
- Modify: `cmig/io/project.py`(아래 코드 추가)
- Test: `tests/test_project_io.py`(아래 테스트 추가)

**Interfaces:**
- Consumes: Task 1의 `Project`, `ModelEntry`, `MediumEntry`, `ProjectError`, `save_project`
- Produces:
  - `class DuplicateModelError(ProjectError)`: 속성 `existing_id: str`
  - `@dataclass(frozen=True) class ModelCheck`: `status, error, n_reactions, n_metabolites, n_genes, biomass, namespace_coverage_pct, warnings`
  - `check_model_file(path: Path) -> ModelCheck`: 예외를 내지 않고 `failed`를 돌려준다.
  - `add_model_file(project, source: Path, *, check: Callable[[Path], ModelCheck] | None = check_model_file) -> ModelEntry`: 목록에 추가만 하고 저장은 하지 않는다.
  - `apply_check(entry: ModelEntry, check: ModelCheck) -> None`
  - `add_medium_file(project, source: Path) -> MediumEntry`
  - `remove_model(project, model_id) -> tuple[int, ModelEntry]`, `restore_model(project, index, entry) -> None`, `rename_model(project, model_id, new_id) -> None`
  - `verify_checksums(project) -> list[str]`(바뀐 항목 id)
  - `selectable_models(project) -> list[ModelEntry]`
  - `model_path(project, entry) -> Path`, `medium_path(project, entry) -> Path`
  - `new_run_dir(project, kind: str) -> Path`
  - `write_run_taxonomy(project, run_dir: Path, model_ids: list[str], abundances: dict[str, float] | None = None) -> Path`
  - `supported_model_paths(paths: list[Path], *, recursive: bool = True) -> tuple[list[Path], int]`(지원 파일 목록, 건너뛴 개수)
  - `MEDIUM_SUFFIXES = (".csv", ".json")`

- [ ] **Step 1: 실패하는 테스트 추가**

`tests/test_project_io.py` 끝에 추가:
```python
import csv
import hashlib


def _fake_model(path: Path, body: str = "<sbml/>") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _ok_check(_path: Path) -> proj.ModelCheck:
    return proj.ModelCheck(
        status="ok", error=None, n_reactions=10, n_metabolites=8, n_genes=3,
        biomass=["BIOMASS"], namespace_coverage_pct=97.5, warnings=[],
    )


def test_add_model_copies_and_never_touches_source(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "in" / "E_rectale.xml", "<sbml>rectale</sbml>")
    before = src.read_bytes()
    entry = proj.add_model_file(project, src, check=_ok_check)
    assert entry.id == "E_rectale"
    assert entry.file == "models/E_rectale.xml"
    assert entry.sha256 == hashlib.sha256(before).hexdigest()
    assert entry.status == "ok" and entry.n_reactions == 10
    assert (project.root / entry.file).read_bytes() == before
    assert src.read_bytes() == before
    assert proj.model_path(project, entry) == project.root / "models" / "E_rectale.xml"


def test_duplicate_content_is_refused(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = _fake_model(tmp_path / "a" / "x.xml", "same")
    b = _fake_model(tmp_path / "b" / "y.xml", "same")
    proj.add_model_file(project, a, check=_ok_check)
    with pytest.raises(proj.DuplicateModelError) as info:
        proj.add_model_file(project, b, check=_ok_check)
    assert info.value.existing_id == "x"
    assert len(project.models) == 1


def test_ids_unique_for_same_stem_and_odd_names(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    first = proj.add_model_file(project, _fake_model(tmp_path / "1" / "model.xml", "1"), check=None)
    second = proj.add_model_file(project, _fake_model(tmp_path / "2" / "model.xml", "2"), check=None)
    odd = proj.add_model_file(
        project, _fake_model(tmp_path / "3" / "B. longum 이름.json.xml", "3"), check=None
    )
    gz = proj.add_model_file(project, _fake_model(tmp_path / "4" / "Akk.xml.gz", "4"), check=None)
    ids = [first.id, second.id, odd.id, gz.id]
    assert len(set(ids)) == 4
    assert first.id == "model" and second.id.startswith("model_")
    assert all(i[0].isalpha() or i[0] == "_" for i in ids)
    assert second.file != first.file and second.file.endswith(".xml")
    assert gz.file.endswith(".xml.gz")
    assert first.status == "pending" and first.integrity == "ok"


def test_unsupported_model_suffix_is_refused(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    with pytest.raises(proj.ProjectError, match="not a supported model file"):
        proj.add_model_file(project, _fake_model(tmp_path / "notes.txt"), check=None)


def test_copy_failure_leaves_no_partial_file(tmp_path: Path, monkeypatch) -> None:
    project = proj.create_project(tmp_path / "p")
    src = _fake_model(tmp_path / "big.xml", "x" * 1000)

    def boom(path, writer):
        raise OSError("disk full")

    monkeypatch.setattr(proj, "atomic_write_binary", boom)
    with pytest.raises(proj.ProjectError, match="disk full"):
        proj.add_model_file(project, src, check=None)
    assert list(project.models_dir.iterdir()) == []
    assert project.models == []


def test_check_model_file_never_raises(tmp_path: Path) -> None:
    result = proj.check_model_file(_fake_model(tmp_path / "broken.xml", "not sbml"))
    assert result.status == "failed"
    assert result.error


def test_verify_checksums_flags_changed_and_missing(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    b = proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    (project.root / a.file).write_text("tampered")
    (project.root / b.file).unlink()
    changed = proj.verify_checksums(project)
    assert sorted(changed) == ["a", "b"]
    assert project.model("a").integrity == "changed"
    assert project.model("b").integrity == "missing"
    assert proj.selectable_models(project) == []


def test_selectable_excludes_failed_and_pending(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    ok = proj.add_model_file(project, _fake_model(tmp_path / "ok.xml", "1"), check=_ok_check)
    warn = proj.add_model_file(project, _fake_model(tmp_path / "w.xml", "2"), check=_ok_check)
    warn.status = "warning"
    bad = proj.add_model_file(project, _fake_model(tmp_path / "bad.xml", "3"), check=None)
    bad.status = "failed"
    proj.add_model_file(project, _fake_model(tmp_path / "pend.xml", "4"), check=None)
    assert [m.id for m in proj.selectable_models(project)] == [ok.id, warn.id]


def test_open_project_reverifies_checksums(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    entry = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.save_project(project)
    (project.root / entry.file).write_text("edited elsewhere")
    assert proj.open_project(project.root).model("a").integrity == "changed"


def test_remove_restore_rename(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    b = proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    index, removed = proj.remove_model(project, "a")
    assert [m.id for m in project.models] == ["b"]
    assert (project.root / removed.file).exists(), "files stay on disk for run references"
    proj.restore_model(project, index, removed)
    assert [m.id for m in project.models] == ["a", "b"]
    proj.rename_model(project, "b", "Bifido_longum")
    assert project.model("Bifido_longum").sha256 == b.sha256
    for bad in ("a", "1abc", "has space", ""):
        with pytest.raises(proj.ProjectError):
            proj.rename_model(project, "Bifido_longum", bad)


def test_add_medium(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    entry = proj.add_medium_file(project, src)
    assert entry.id == "diet" and entry.file == "media/diet.csv"
    assert proj.medium_path(project, entry).read_text() == src.read_text()
    with pytest.raises(proj.ProjectError, match="CSV or JSON"):
        proj.add_medium_file(project, _fake_model(tmp_path / "x.xml"))


def test_new_run_dir_never_reuses(tmp_path: Path, monkeypatch) -> None:
    project = proj.create_project(tmp_path / "p")
    monkeypatch.setattr(proj, "_stamp", lambda: "20261013-103100")
    first = proj.new_run_dir(project, "search")
    second = proj.new_run_dir(project, "search")
    assert first.name == "search-20261013-103100"
    assert second.name == "search-20261013-103100-2"
    assert first.is_dir() and second.is_dir()
    with pytest.raises(proj.ProjectError):
        proj.new_run_dir(project, "../escape")


def test_write_run_taxonomy(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    a = proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.add_model_file(project, _fake_model(tmp_path / "b.xml", "b"), check=_ok_check)
    run = proj.new_run_dir(project, "community")
    path = proj.write_run_taxonomy(project, run, ["b", "a"], abundances={"a": 0.25})
    assert path == project.inputs_dir / f"{run.name}-taxonomy.csv"
    rows = list(csv.DictReader(path.open()))
    assert [r["id"] for r in rows] == ["b", "a"]
    assert rows[1]["file"] == str(project.root / a.file)
    assert [float(r["abundance"]) for r in rows] == [1.0, 0.25]
    assert list(run.iterdir()) == [], "nothing is pre-written into the CLI's run folder"
    with pytest.raises(proj.ProjectError, match="not selectable"):
        project.model("a").integrity = "changed"
        proj.write_run_taxonomy(project, run, ["a"])
    with pytest.raises(proj.ProjectError, match="no models"):
        proj.write_run_taxonomy(project, run, [])


def test_project_survives_move(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "old")
    proj.add_model_file(project, _fake_model(tmp_path / "a.xml", "a"), check=_ok_check)
    proj.save_project(project)
    (tmp_path / "old").rename(tmp_path / "new")
    moved = proj.open_project(tmp_path / "new")
    assert moved.model("a").integrity == "ok"
    run = proj.new_run_dir(moved, "search")
    rows = list(csv.DictReader(proj.write_run_taxonomy(moved, run, ["a"]).open()))
    assert rows[0]["file"].startswith(str(tmp_path / "new"))


def test_supported_model_paths_filters_and_counts(tmp_path: Path) -> None:
    folder = tmp_path / "pool"
    _fake_model(folder / "a.xml")
    _fake_model(folder / "sub" / "b.mat")
    _fake_model(folder / "readme.txt")
    _fake_model(folder / ".hidden.xml")
    (folder / "notcobra.json").write_text('{"hello": 1}')
    files, skipped = proj.supported_model_paths([folder])
    assert sorted(p.name for p in files) == ["a.xml", "b.mat"]
    assert skipped == 3
    flat, _ = proj.supported_model_paths([folder], recursive=False)
    assert [p.name for p in flat] == ["a.xml"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run --no-sync pytest tests/test_project_io.py`
Expected: 새 테스트가 `AttributeError: module 'cmig.io.project' has no attribute 'add_model_file'` 등으로 FAIL. Task 1 테스트는 계속 PASS.

- [ ] **Step 3: 구현**

`cmig/io/project.py`에 추가(import는 파일 위쪽 import 블록에 합친다):
```python
import csv
import hashlib
import io
import re
import shutil
from collections.abc import Callable, Iterable

from cmig.core.model_pool import is_supported_model_file, member_id_from_path
from cmig.io.atomic import atomic_write_binary

MEDIUM_SUFFIXES = (".csv", ".json")
_MODEL_SUFFIXES = (".xml.gz", ".sbml.gz", ".xml", ".sbml", ".json", ".mat")
_ID_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


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
    while candidate.exists():
        candidate = folder / f"{safe_stem}-{n}{suffix}"
        n += 1
    return candidate


def _copy_into(source: Path, target: Path) -> None:
    def write(handle: io.BufferedWriter) -> None:  # type: ignore[type-arg]
        with source.open("rb") as src:
            shutil.copyfileobj(src, handle, 1 << 20)

    try:
        atomic_write_binary(target, write)  # type: ignore[arg-type]
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
    source = Path(source).expanduser().resolve()
    if not is_supported_model_file(source):
        raise ProjectError(f"not a supported model file: {source.name}")
    sha = _sha256(source)
    for entry in project.models:
        if entry.sha256 == sha:
            raise DuplicateModelError(entry.id)
    stem, suffix = _split_suffix(source.name, _MODEL_SUFFIXES)
    target = _free_name(project.models_dir, stem, suffix)
    _copy_into(source, target)
    if _sha256(target) != sha:
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
    source = Path(source).expanduser().resolve()
    if source.suffix.lower() not in MEDIUM_SUFFIXES or not source.is_file():
        raise ProjectError(f"a medium must be a CSV or JSON file: {source.name}")
    sha = _sha256(source)
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
    entry = project.model(model_id)
    if not _ID_RE.match(new_id):
        raise ProjectError("a model id starts with a letter or _ and uses letters, digits, _")
    if any(m.id == new_id for m in project.models if m is not entry):
        raise ProjectError(f"another model already uses the id {new_id!r}")
    entry.id = new_id


def model_path(project: Project, entry: ModelEntry) -> Path:
    return project.root / entry.file


def medium_path(project: Project, entry: MediumEntry) -> Path:
    return project.root / entry.file


def verify_checksums(project: Project) -> list[str]:
    """Recompute sha256 of every copy; mark ``changed``/``missing`` and return those ids."""
    changed: list[str] = []
    for item in [*project.models, *project.media]:
        path = project.root / item.file
        if not path.is_file():
            item.integrity = "missing"
        elif _sha256(path) != item.sha256:
            item.integrity = "changed"
        else:
            item.integrity = "ok"
            continue
        changed.append(item.id)
    return changed


def selectable_models(project: Project) -> list[ModelEntry]:
    return [
        m for m in project.models if m.status in ("ok", "warning") and m.integrity == "ok"
    ]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def new_run_dir(project: Project, kind: str) -> Path:
    if not _KIND_RE.match(kind):
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
        return candidate


def write_run_taxonomy(
    project: Project,
    run_dir: Path,
    model_ids: list[str],
    abundances: dict[str, float] | None = None,
) -> Path:
    """Write ``runs/_inputs/<run>-taxonomy.csv`` (id,file,abundance) for the CLI."""
    if not model_ids:
        raise ProjectError("no models selected for this run")
    selectable = {m.id: m for m in selectable_models(project)}
    rows: list[list[str]] = []
    for model_id in model_ids:
        entry = selectable.get(model_id)
        if entry is None:
            raise ProjectError(f"model {model_id!r} is not selectable (failed, changed or missing)")
        abundance = (abundances or {}).get(model_id, 1.0)
        rows.append([model_id, str(model_path(project, entry)), repr(float(abundance))])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "file", "abundance"])
    writer.writerows(rows)
    path = project.inputs_dir / f"{Path(run_dir).name}-taxonomy.csv"
    atomic_write_text(path, buffer.getvalue())
    return path


def supported_model_paths(
    paths: list[Path], *, recursive: bool = True
) -> tuple[list[Path], int]:
    """Expand files and folders to supported GEM files; count everything skipped."""
    found: list[Path] = []
    skipped = 0
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            candidates = sorted(path.rglob("*") if recursive else path.iterdir())
            for item in candidates:
                if not item.is_file():
                    continue
                if item.name.startswith(".") or not is_supported_model_file(item):
                    skipped += 1
                else:
                    found.append(item)
        elif path.is_file() and not path.name.startswith(".") and is_supported_model_file(path):
            found.append(path)
        else:
            skipped += 1
    return found, skipped
```

`open_project` 끝의 `return project` 직전에 다음 줄을 넣는다:
```python
    verify_checksums(project)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run --no-sync pytest tests/test_project_io.py && uv run --no-sync mypy cmig/io/project.py && uv run --no-sync ruff check cmig/io/project.py tests/test_project_io.py`
Expected: 모든 테스트 PASS(`test_check_model_file_never_raises`는 engine extra의 cobra 사용), mypy·ruff 오류 없음.
`_copy_into`의 `type: ignore`가 mypy에서 "unused ignore"로 걸리면 그 주석을 지운다.

- [ ] **Step 5: 커밋**

```bash
git add cmig/io/project.py tests/test_project_io.py
git commit -m "feat(io): project model/medium registry, checksums and run inputs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 3: `ProjectSession`과 최근 프로젝트 (`cmig/gui/project_session.py`)

**Files:**
- Create: `cmig/gui/project_session.py`
- Create: `tests/gui_project_helpers.py`
- Test: `tests/test_workspace_session.py`

**Interfaces:**
- Consumes: Task 1·2의 `cmig.io.project` 전체
- Produces:
  - `@dataclass(frozen=True) class RunEntry`: `path: Path, name: str, kind: str, status: str, label: str, mtime: float`
  - `run_label(kind: str, run_name: str, summary_hint: str) -> str`
  - `class ProjectSession(QObject)`:
    - 신호: `opened`, `closed`, `models_changed`, `media_changed`, `runs_changed`(인자 없음)
    - 속성: `project: Project | None`, `undo_stack: QUndoStack`
    - 메서드: `open(root: Path) -> None`, `create(root: Path, name: str | None) -> None`, `close() -> None`, `save() -> None`, `add_entries(entries: list[ModelEntry]) -> None`(Undo 가능, 저장, 신호), `remove_models(ids: list[str]) -> None`(Undo 가능), `rename_model(old: str, new: str) -> None`(Undo 가능), `add_medium(entry: MediumEntry) -> None`(Undo 가능), `runs() -> list[RunEntry]`, `refresh_runs() -> None`, `settings(analysis: str) -> dict[str, object]`, `store_settings(analysis: str, values: dict[str, object]) -> None`
  - `class RecentProjects`: `__init__(settings: QSettings | None = None)`, `paths() -> list[Path]`, `add(path: Path) -> None`, `clear() -> None`. 최대 10개, 최신순.
  - `tests/gui_project_helpers.py`: `make_project(root: Path, model_names: list[str], *, statuses: dict[str, str] | None = None) -> Project`, `ok_check(path) -> ModelCheck`, autouse fixture `_deterministic_qt_teardown`(아래 코드)

- [ ] **Step 1: 실패하는 테스트와 helper 작성**

`tests/gui_project_helpers.py`:
```python
"""Shared helpers for GUI workspace tests: fake projects and deterministic Qt teardown."""

from __future__ import annotations

import gc
from pathlib import Path

import pytest

from cmig.io import project as proj


def ok_check(_path: Path) -> proj.ModelCheck:
    return proj.ModelCheck("ok", None, 10, 8, 3, ["BIOMASS"], 99.0, [])


def make_project(
    root: Path, model_names: list[str], *, statuses: dict[str, str] | None = None
) -> proj.Project:
    """A saved project whose models are tiny placeholder files marked as checked."""
    project = proj.create_project(root)
    source = root.parent / f"{root.name}-sources"
    source.mkdir(parents=True, exist_ok=True)
    for name in model_names:
        path = source / f"{name}.xml"
        path.write_text(f"<sbml id='{name}'/>")
        entry = proj.add_model_file(project, path, check=ok_check)
        entry.status = (statuses or {}).get(name, "ok")
    proj.save_project(project)
    return project


@pytest.fixture(autouse=True)
def _deterministic_qt_teardown():
    """Close and delete top-level Qt widgets after each test (avoids macOS exit segfaults)."""
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.processEvents()
    gc.collect()
```

`tests/test_workspace_session.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.project_session import ProjectSession, RecentProjects, run_label  # noqa: E402
from cmig.io import project as proj  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


def test_open_locks_and_close_releases(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b"])
    session = ProjectSession()
    events: list[str] = []
    session.opened.connect(lambda: events.append("opened"))
    session.closed.connect(lambda: events.append("closed"))
    session.open(tmp_path / "p")
    assert session.project is not None and len(session.project.models) == 2
    assert (tmp_path / "p" / ".cmig-project.lock").exists()
    other = ProjectSession()
    with pytest.raises(proj.ProjectError, match="already open"):
        other.open(tmp_path / "p")
    session.close()
    assert session.project is None
    assert not (tmp_path / "p" / ".cmig-project.lock").exists()
    assert events == ["opened", "closed"]


def test_remove_and_rename_are_undoable_and_saved(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a", "b", "c"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    session.remove_models(["a", "c"])
    assert [m.id for m in session.project.models] == ["b"]
    assert session.undo_stack.undoText() == "Remove 2 Models"
    assert [m.id for m in proj.open_project(tmp_path / "p").models] == ["b"]
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a", "b", "c"]
    session.rename_model("b", "Bifido")
    assert session.undo_stack.undoText() == "Rename Model"
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a", "b", "c"]
    with pytest.raises(proj.ProjectError):
        session.rename_model("a", "c")
    session.close()


def test_adding_models_and_media_is_undoable(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    project = session.project
    src = tmp_path / "new.xml"
    src.write_text("<sbml id='new'/>")
    entry = proj.add_model_file(
        proj.Project(project.root, project.name, project.created, list(project.models)),
        src, check=None,
    )
    session.add_entries([entry])
    assert [m.id for m in session.project.models] == ["a", "new"]
    assert session.undo_stack.undoText() == "Add Model"
    session.undo_stack.undo()
    assert [m.id for m in session.project.models] == ["a"]
    assert (project.root / entry.file).exists(), "undo keeps the copied file"
    medium_src = tmp_path / "diet.csv"
    medium_src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    medium = proj.add_medium_file(
        proj.Project(project.root, project.name, project.created, media=list(project.media)),
        medium_src,
    )
    session.add_medium(medium)
    assert session.undo_stack.undoText() == "Add Medium"
    session.undo_stack.undo()
    assert session.project.media == []
    session.close()


def test_runs_listing_newest_first_with_status(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    old = project.runs_dir / "search-20261001-090000"
    old.mkdir()
    (old / "search_summary.json").write_text('{"status": "failed", "top_ranked": []}')
    new = project.runs_dir / "search-20261013-103100"
    new.mkdir()
    (new / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    os.utime(old, (1, 1))
    session = ProjectSession()
    session.open(tmp_path / "p")
    runs = session.runs()
    assert [r.name for r in runs] == [new.name, old.name]
    assert [r.status for r in runs] == ["ok", "failed"]
    assert runs[0].label == "Search · but · 10:31"
    assert all(r.path.parent.name == "runs" for r in runs)
    session.close()


def test_run_label_fallbacks() -> None:
    assert run_label("gene_ko_search", "gene-ko-20261013-091502", "") == "Gene KO · 09:15"
    assert run_label("unknown", "odd-name", "") == "odd-name"


def test_settings_round_trip(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    session = ProjectSession()
    session.open(tmp_path / "p")
    session.store_settings("search", {"models": ["a"]})
    session.close()
    session.open(tmp_path / "p")
    assert session.settings("search") == {"models": ["a"]}
    assert session.settings("host") == {}
    session.close()


def test_recent_projects_order_and_limit(tmp_path: Path) -> None:
    store = QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat)
    recent = RecentProjects(store)
    for i in range(12):
        recent.add(tmp_path / f"p{i}")
    recent.add(tmp_path / "p3")
    paths = recent.paths()
    assert paths[0] == (tmp_path / "p3").resolve()
    assert len(paths) == 10
    recent.clear()
    assert recent.paths() == []
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_session.py`
Expected: FAIL (`ModuleNotFoundError: cmig.gui.project_session`).

- [ ] **Step 3: 구현**

`cmig/gui/project_session.py`:
```python
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
        probe = proj.Project(project.root, project.name, project.created,
                             [proj.ModelEntry(**vars(m)) for m in project.models])
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
        values = [raw] if isinstance(raw, str) else list(raw or [])
        return [Path(str(value)) for value in values if str(value)]

    def add(self, path: Path) -> None:
        resolved = Path(path).resolve()
        current = [p for p in self.paths() if p.resolve() != resolved]
        self._settings.setValue(self.KEY, [str(resolved), *map(str, current)][: self.LIMIT])
        self._settings.sync()

    def clear(self) -> None:
        self._settings.setValue(self.KEY, [])
        self._settings.sync()
```

`test_runs_listing_newest_first_with_status`의 `os.utime(old, (1, 1))`는 `old`의 mtime을 아주 오래전으로 바꿔 정렬 순서를 고정한다.

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_session.py && uv run --no-sync mypy cmig/gui/project_session.py && uv run --no-sync ruff check cmig/gui/project_session.py tests/test_workspace_session.py tests/gui_project_helpers.py`
Expected: PASS, mypy·ruff 오류 없음.

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/project_session.py tests/gui_project_helpers.py tests/test_workspace_session.py
git commit -m "feat(gui): project session with undo, run listing and recents

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 4: 사이드바 (`cmig/gui/sidebar.py`)

**Files:**
- Create: `cmig/gui/sidebar.py`
- Test: `tests/test_workspace_sidebar.py`

**Interfaces:**
- Consumes: `ModelEntry`, `MediumEntry`(Task 1), `RunEntry`(Task 3), `supported_model_paths`(Task 2)
- Produces:
  - `ANALYSES: list[tuple[str, str]]`: (key, label) 순서는 `search` Combination Search, `gene_ko` Gene Knockout, `growth` Strain Growth & Ratio, `host` Host–Microbe, `dynamics` Dynamics, 그다음 `None` 구분선, `community` Community Solve, `medium` Medium Editor, `sweep` Sweep, `sandbox` Constraint Sandbox, `compare` Compare Runs. 구분선은 `ANALYSIS_SEPARATOR_AFTER = "dynamics"`로 표현한다.
  - `status_symbol(status: str, integrity: str = "ok") -> str`: `"✓"`, `"⚠"`, `"✗"`, `"⊘"`, `"…"`, `"?"`
  - `droppable_paths(urls: list[QUrl]) -> tuple[list[Path], int]`
  - `class WorkspaceSidebar(QTreeWidget)`:
    - 신호: `selection_changed(str, str)`(group, key), `files_dropped(list)`(Path 목록), `context_requested(str, list)`(group, keys)
    - 메서드: `set_models(entries, pending: list[str])`, `set_media(presets: list[str], user: list[MediumEntry])`, `set_runs(entries: list[RunEntry], external: list[RunEntry])`, `select(group: str, key: str)`, `selected_keys(group: str) -> list[str]`
    - group 이름: `"models"`, `"media"`, `"analyses"`, `"runs"`. media key는 `preset:<name>` / `medium:<id>`, run key는 경로 문자열이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_sidebar.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.project_session import RunEntry  # noqa: E402
from cmig.gui.sidebar import (  # noqa: E402
    ANALYSES,
    WorkspaceSidebar,
    droppable_paths,
    status_symbol,
)
from cmig.io import project as proj  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


def _group_texts(sidebar: WorkspaceSidebar) -> list[str]:
    return [sidebar.topLevelItem(i).text(0) for i in range(sidebar.topLevelItemCount())]


def test_groups_and_models_with_status(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b", "c"], statuses={"b": "warning", "c": "failed"})
    sidebar = WorkspaceSidebar()
    sidebar.set_models(project.models, pending=["loading.xml"])
    assert _group_texts(sidebar) == ["MODELS (3)", "MEDIA", "ANALYSES", "RUNS"]
    models = sidebar.topLevelItem(0)
    texts = [models.child(i).text(0) for i in range(models.childCount())]
    assert texts == ["✓ a", "⚠ b", "✗ c", "… loading.xml"]


def test_status_symbols() -> None:
    assert status_symbol("ok") == "✓"
    assert status_symbol("ok", "changed") == "⚠"
    assert status_symbol("degraded") == "⚠"
    assert status_symbol("failed") == "✗"
    assert status_symbol("cancelled") == "⊘"
    assert status_symbol("pending") == "…"
    assert status_symbol("weird") == "?"


def test_analyses_listed_with_separator_and_selection_signal() -> None:
    sidebar = WorkspaceSidebar()
    seen: list[tuple[str, str]] = []
    sidebar.selection_changed.connect(lambda g, k: seen.append((g, k)))
    group = sidebar.topLevelItem(2)
    keys = [group.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(group.childCount())]
    assert keys[:5] == ["search", "gene_ko", "growth", "host", "dynamics"]
    assert None in keys, "a disabled separator row follows the primary analyses"
    sidebar.select("analyses", "host")
    assert seen[-1] == ("analyses", "host")
    assert [k for k, _ in ANALYSES][-1] == "compare"


def test_runs_and_multi_select(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a", "b"])
    sidebar = WorkspaceSidebar()
    sidebar.set_models(project.models, pending=[])
    runs = [RunEntry(tmp_path / "r1", "r1", "search", "ok", "Search · but · 10:31", 2.0),
            RunEntry(tmp_path / "r2", "r2", "search", "failed", "Search · ac · 09:00", 1.0)]
    sidebar.set_runs(runs, external=[])
    run_group = sidebar.topLevelItem(3)
    assert run_group.child(0).text(0) == "✓ Search · but · 10:31"
    assert run_group.child(1).text(0) == "✗ Search · ac · 09:00"
    models = sidebar.topLevelItem(0)
    models.child(0).setSelected(True)
    models.child(1).setSelected(True)
    assert sidebar.selected_keys("models") == ["a", "b"]


def test_drop_filters_unsupported_and_reports_skipped(tmp_path: Path) -> None:
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "a.xml").write_text("<sbml/>")
    (pool / "readme.txt").write_text("x")
    (pool / ".DS_Store").write_text("x")
    paths, skipped = droppable_paths([QUrl.fromLocalFile(str(pool))])
    assert [p.name for p in paths] == ["a.xml"] and skipped == 2

    sidebar = WorkspaceSidebar()
    received: list[list[Path]] = []
    sidebar.files_dropped.connect(lambda files: received.append(files))
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pool / "readme.txt"))])
    enter = QDragEnterEvent(sidebar.rect().center(), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    sidebar.dragEnterEvent(enter)
    assert not enter.isAccepted(), "a drop with no model file is not accepted"
    mime.setUrls([QUrl.fromLocalFile(str(pool))])
    drop = QDropEvent(QPointF(sidebar.rect().center()), Qt.DropAction.CopyAction, mime,
                      Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    sidebar.dropEvent(drop)
    assert received == [[pool]]


def test_media_presets_and_user(tmp_path: Path) -> None:
    project = proj.create_project(tmp_path / "p")
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    entry = proj.add_medium_file(project, src)
    sidebar = WorkspaceSidebar()
    sidebar.set_media(["western", "high_fiber"], [entry])
    media = sidebar.topLevelItem(1)
    keys = [media.child(i).data(0, Qt.ItemDataRole.UserRole) for i in range(media.childCount())]
    assert keys == ["preset:western", "preset:high_fiber", "medium:diet"]
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_sidebar.py`
Expected: FAIL (`ModuleNotFoundError: cmig.gui.sidebar`).

- [ ] **Step 3: 구현**

`cmig/gui/sidebar.py`:
```python
"""Workspace source list: MODELS, MEDIA, ANALYSES and RUNS (two levels, HIG sidebar)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QUrl, Signal
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QFont
from PySide6.QtWidgets import QAbstractItemView, QTreeWidget, QTreeWidgetItem

from cmig.gui.project_session import RunEntry
from cmig.io.project import MediumEntry, ModelEntry, supported_model_paths

ANALYSES: list[tuple[str, str]] = [
    ("search", "Combination Search"),
    ("gene_ko", "Gene Knockout"),
    ("growth", "Strain Growth & Ratio"),
    ("host", "Host–Microbe"),
    ("dynamics", "Dynamics"),
    ("community", "Community Solve"),
    ("medium", "Medium Editor"),
    ("sweep", "Sweep"),
    ("sandbox", "Constraint Sandbox"),
    ("compare", "Compare Runs"),
]
ANALYSIS_SEPARATOR_AFTER = "dynamics"
_GROUPS = ("models", "media", "analyses", "runs")
_ROLE = Qt.ItemDataRole.UserRole


def status_symbol(status: str, integrity: str = "ok") -> str:
    if integrity != "ok":
        return "⚠"
    return {
        "ok": "✓",
        "warning": "⚠",
        "degraded": "⚠",
        "failed": "✗",
        "unreadable": "✗",
        "cancelled": "⊘",
        "pending": "…",
    }.get(status, "?")


def droppable_paths(urls: list[QUrl]) -> tuple[list[Path], int]:
    """Model files found under the dropped URLs (folders recurse) and the skipped count."""
    local = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
    skipped = len(urls) - len(local)
    files, unsupported = supported_model_paths(local)
    return files, skipped + unsupported


class WorkspaceSidebar(QTreeWidget):
    selection_changed = Signal(str, str)
    files_dropped = Signal(list)
    context_requested = Signal(str, list)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)
        self._groups: dict[str, QTreeWidgetItem] = {}
        bold = QFont()
        bold.setBold(True)
        for name in _GROUPS:
            item = QTreeWidgetItem([name.upper()])
            item.setFont(0, bold)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(0, _ROLE, None)
            self.addTopLevelItem(item)
            item.setExpanded(True)
            self._groups[name] = item
        self._fill_analyses()
        self.currentItemChanged.connect(self._emit_selection)
        self.customContextMenuRequested.connect(self._emit_context)

    def _fill_analyses(self) -> None:
        group = self._groups["analyses"]
        for key, label in ANALYSES:
            item = QTreeWidgetItem([label])
            item.setData(0, _ROLE, key)
            group.addChild(item)
            if key == ANALYSIS_SEPARATOR_AFTER:
                separator = QTreeWidgetItem(["──────────"])
                separator.setFlags(Qt.ItemFlag.NoItemFlags)
                separator.setData(0, _ROLE, None)
                group.addChild(separator)

    def _reset(self, name: str) -> QTreeWidgetItem:
        group = self._groups[name]
        group.takeChildren()
        return group

    def set_models(self, entries: list[ModelEntry], pending: list[str]) -> None:
        group = self._reset("models")
        group.setText(0, f"MODELS ({len(entries)})")
        for entry in entries:
            item = QTreeWidgetItem([f"{status_symbol(entry.status, entry.integrity)} {entry.id}"])
            item.setData(0, _ROLE, entry.id)
            item.setToolTip(0, entry.error or entry.source_path)
            group.addChild(item)
        for name in pending:
            item = QTreeWidgetItem([f"… {name}"])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setData(0, _ROLE, None)
            group.addChild(item)

    def set_media(self, presets: list[str], user: list[MediumEntry]) -> None:
        group = self._reset("media")
        for name in presets:
            item = QTreeWidgetItem([name])
            item.setData(0, _ROLE, f"preset:{name}")
            item.setToolTip(0, "Installed medium preset")
            group.addChild(item)
        for entry in user:
            item = QTreeWidgetItem([f"{status_symbol('ok', entry.integrity)} {entry.id}"])
            item.setData(0, _ROLE, f"medium:{entry.id}")
            item.setToolTip(0, entry.source_path)
            group.addChild(item)

    def set_runs(self, entries: list[RunEntry], external: list[RunEntry]) -> None:
        group = self._reset("runs")
        for entry in [*entries, *external]:
            suffix = " (opened)" if entry in external else ""
            item = QTreeWidgetItem([f"{status_symbol(entry.status)} {entry.label}{suffix}"])
            item.setData(0, _ROLE, str(entry.path))
            item.setToolTip(0, f"{entry.status} · {entry.path}")
            group.addChild(item)

    def _group_of(self, item: QTreeWidgetItem | None) -> str | None:
        parent = None if item is None else item.parent()
        for name, group in self._groups.items():
            if parent is group:
                return name
        return None

    def _emit_selection(self, current: QTreeWidgetItem | None, _previous: object) -> None:
        group = self._group_of(current)
        key = None if current is None else current.data(0, _ROLE)
        if group is not None and isinstance(key, str):
            self.selection_changed.emit(group, key)

    def select(self, group: str, key: str) -> None:
        parent = self._groups[group]
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, _ROLE) == key:
                self.setCurrentItem(child)
                return

    def selected_keys(self, group: str) -> list[str]:
        parent = self._groups[group]
        return [
            str(parent.child(i).data(0, _ROLE))
            for i in range(parent.childCount())
            if parent.child(i).isSelected() and isinstance(parent.child(i).data(0, _ROLE), str)
        ]

    def _emit_context(self, point: QPoint) -> None:
        item = self.itemAt(point)
        group = self._group_of(item)
        if group is not None:
            keys = self.selected_keys(group) or [str(item.data(0, _ROLE))] if item else []
            self.context_requested.emit(group, keys)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt override
        files, _skipped = droppable_paths(list(event.mimeData().urls()))
        if files:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt override
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt override
        local = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if local:
            self.files_dropped.emit(local)
            event.acceptProposedAction()
        else:
            event.ignore()
```

`files_dropped`는 사용자가 놓은 원래 경로(폴더 포함)를 보낸다. 지원 파일로 펼치고 건너뛴 수를 세는 일은 가져오기 작업(Task 7)이 `supported_model_paths`로 한다. 그래서 drop 테스트의 기대값은 `[[pool]]`이다.

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_sidebar.py && uv run --no-sync mypy cmig/gui/sidebar.py && uv run --no-sync ruff check cmig/gui/sidebar.py tests/test_workspace_sidebar.py`
Expected: PASS, mypy·ruff 오류 없음.

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/sidebar.py tests/test_workspace_sidebar.py
git commit -m "feat(gui): workspace sidebar with models, media, analyses and runs

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 5: 상세 패널과 작업 창 (`cmig/gui/inspector.py`, `cmig/gui/activity.py`)

**Files:**
- Create: `cmig/gui/inspector.py`, `cmig/gui/activity.py`
- Modify: `cmig/gui/app.py`(`RuntimeJobsPanel` 클래스를 `activity.py`로 옮기고, app.py에서는 `from cmig.gui.activity import RuntimeJobsPanel`로 다시 내보냄)
- Test: `tests/test_workspace_panels.py`

**Interfaces:**
- Consumes: `ModelEntry`, `MediumEntry`, `RunEntry`, `model_path`
- Produces:
  - `class InspectorPanel(QWidget)`:
    - 메서드: `show_model(project: Project, entry: ModelEntry, exchanges: list[str] | None)`, `show_medium(title: str, rows: list[tuple[str, str]], source: str)`, `show_run(entry: RunEntry, inspected: dict[str, object], command: str)`, `show_analysis(title: str, description: str, cli: str)`, `clear()`
    - 속성: `title_label`, `details`(QTextBrowser), `exchange_filter`(QLineEdit), `exchange_list`(QListWidget), `copy_command_btn`, `reveal_btn`, `current_command() -> str`, `current_path() -> Path | None`
  - `class ActivityPane(QWidget)`:
    - 속성: `jobs: RuntimeJobsPanel`, `cancel_btn`, `log_view`(QPlainTextEdit), `command_label`(QLineEdit, read-only)
    - 메서드: `set_job_detail(log: str, command: str)`, `expand()`
    - 신호: `cancel_requested(str)`(job id)
  - `command_line(argv: list[str]) -> str`: `"cmig " + shlex.join(argv)`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_panels.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.activity import ActivityPane, command_line  # noqa: E402
from cmig.gui.inspector import InspectorPanel  # noqa: E402
from cmig.gui.project_session import RunEntry  # noqa: E402
from cmig.service.jobrunner import JobRunner  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


def test_model_inspector_shows_counts_checksum_and_filters_exchanges(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["E_rectale"])
    entry = project.model("E_rectale")
    panel = InspectorPanel()
    panel.show_model(project, entry, ["EX_but_e", "EX_ac_e", "EX_glc__D_e"])
    text = panel.details.toPlainText()
    assert "E_rectale" in panel.title_label.text()
    assert "10 reactions" in text and entry.sha256[:12] in text and "99.0%" in text
    panel.exchange_filter.setText("but")
    visible = [panel.exchange_list.item(i).text() for i in range(panel.exchange_list.count())
               if not panel.exchange_list.item(i).isHidden()]
    assert visible == ["EX_but_e"]
    assert panel.current_path() == project.root / entry.file


def test_model_inspector_marks_changed_copy(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    entry = project.model("a")
    entry.integrity = "changed"
    panel = InspectorPanel()
    panel.show_model(project, entry, None)
    assert "changed since it was added" in panel.details.toPlainText()
    assert panel.exchange_list.count() == 0


def test_run_inspector_shows_status_integrity_solver_and_command(tmp_path: Path) -> None:
    panel = InspectorPanel()
    entry = RunEntry(tmp_path, "search-20261013-103100", "search", "degraded", "Search", 1.0)
    inspected = {"status": "degraded", "artifact_integrity": "verified",
                 "run_hash": "abc123", "manifest": {"solver": "osqp"}}
    panel.show_run(entry, inspected, "cmig search --taxonomy t.csv --out runs/x")
    text = panel.details.toPlainText()
    assert "degraded" in text and "verified" in text and "abc123" in text
    assert "OSQP QP-only approximation" in text
    assert panel.current_command() == "cmig search --taxonomy t.csv --out runs/x"


def test_activity_pane_cancel_and_command() -> None:
    runner = JobRunner(max_workers=1)
    pane = ActivityPane()
    requested: list[str] = []
    pane.cancel_requested.connect(requested.append)
    jid = runner.submit("demo", lambda ctx: {"ok": True})
    pane.jobs.refresh(runner, [jid])
    pane.jobs.selectRow(0)
    pane.cancel_btn.click()
    assert requested == [jid]
    pane.set_job_detail("line1\nline2", command_line(["search", "--out", "a b"]))
    assert pane.command_label.text() == "cmig search --out 'a b'"
    assert pane.log_view.toPlainText() == "line1\nline2"
    runner.shutdown(wait=True)
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_panels.py`
Expected: FAIL (`ModuleNotFoundError: cmig.gui.activity`).

- [ ] **Step 3: 구현**

`cmig/gui/activity.py`. `RuntimeJobsPanel`은 `app.py`의 현재 클래스를 그대로 옮긴다(`__init__`, `refresh`, `selected_job_id` 본문 동일, import는 `make_read_only`·`read_only_item`을 `cmig.gui.builder`에서, `JobRunner`·`JobStatus`를 `cmig.service.jobrunner`에서 가져온다). 생성자의 `tr` 인자는 선택 인자로 바꾼다:
```python
"""Bottom activity pane: running jobs, cancel, log and the equivalent cmig command."""

from __future__ import annotations

import shlex

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

    # refresh(...) and selected_job_id(...) : copy the existing bodies from app.py verbatim.


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
```
`JobRunner`과 `JobStatus` import는 옮긴 `refresh` 본문이 쓰므로 그대로 둔다.

`cmig/gui/inspector.py`:
```python
"""Right-hand inspector: details of the selected model, medium, run or analysis."""

from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from cmig.gui.project_session import RunEntry
from cmig.io.project import ModelEntry, Project, model_path

_SOLVER_TEXT = {
    "gurobi": "Gurobi full-flux",
    "osqp": "OSQP QP-only approximation",
}


def _row(label: str, value: object) -> str:
    shown = "not recorded" if value in (None, "", []) else value
    return f"<b>{html.escape(label)}</b>: {html.escape(str(shown))}<br>"


class InspectorPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(240)
        self.setMaximumWidth(420)
        self.title_label = QLabel("Nothing selected")
        self.title_label.setWordWrap(True)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.exchange_filter = QLineEdit("")
        self.exchange_filter.setPlaceholderText("Filter exchanges")
        self.exchange_filter.textChanged.connect(self._filter_exchanges)
        self.exchange_list = QListWidget()
        self.copy_command_btn = QPushButton("Copy Command")
        self.copy_command_btn.clicked.connect(self._copy_command)
        self.reveal_btn = QPushButton("Show in Finder")
        self.reveal_btn.clicked.connect(self._reveal)
        buttons = QHBoxLayout()
        buttons.addWidget(self.copy_command_btn)
        buttons.addWidget(self.reveal_btn)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.details, 2)
        layout.addWidget(self.exchange_filter)
        layout.addWidget(self.exchange_list, 1)
        layout.addLayout(buttons)
        self._command = ""
        self._path: Path | None = None
        self.clear()

    def clear(self) -> None:
        self.title_label.setText("Nothing selected")
        self.details.setHtml("<i>Select a model, medium, analysis or run.</i>")
        self._set_exchanges(None)
        self._set_actions("", None)

    def _set_actions(self, command: str, path: Path | None) -> None:
        self._command, self._path = command, path
        self.copy_command_btn.setEnabled(bool(command))
        self.reveal_btn.setEnabled(path is not None)

    def _set_exchanges(self, exchanges: list[str] | None) -> None:
        self.exchange_list.clear()
        visible = exchanges is not None
        self.exchange_filter.setVisible(visible)
        self.exchange_list.setVisible(visible)
        self.exchange_filter.setText("")
        for exchange in exchanges or []:
            self.exchange_list.addItem(exchange)

    def _filter_exchanges(self, text: str) -> None:
        needle = text.strip().lower()
        for i in range(self.exchange_list.count()):
            item = self.exchange_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def show_model(
        self, project: Project, entry: ModelEntry, exchanges: list[str] | None
    ) -> None:
        self.title_label.setText(f"Model · {entry.id}")
        integrity = {
            "ok": "matches the checksum recorded when it was added",
            "changed": "changed since it was added — excluded from analyses",
            "missing": "missing from the project folder — excluded from analyses",
        }.get(entry.integrity, entry.integrity)
        counts = (
            f"{entry.n_reactions} reactions · {entry.n_metabolites} metabolites · "
            f"{entry.n_genes} genes"
            if entry.n_reactions is not None else None
        )
        coverage = (
            None if entry.namespace_coverage_pct is None
            else f"{entry.namespace_coverage_pct:.1f}%"
        )
        body = (
            _row("Check", entry.status)
            + _row("Error", entry.error)
            + _row("Size", counts)
            + _row("Biomass", ", ".join(entry.biomass))
            + _row("BiGG namespace coverage", coverage)
            + _row("Warnings", "; ".join(entry.warnings))
            + _row("File", integrity)
            + _row("SHA-256", entry.sha256[:12] + "…")
            + _row("Original", entry.source_path)
            + _row("Format", entry.format)
        )
        self.details.setHtml(body)
        self._set_exchanges(exchanges)
        self._set_actions("", model_path(project, entry))

    def show_medium(self, title: str, rows: list[tuple[str, str]], source: str) -> None:
        self.title_label.setText(f"Medium · {title}")
        table = "".join(
            f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td></tr>" for a, b in rows
        )
        self.details.setHtml(
            _row("Source", source)
            + f"<table><tr><th>Exchange</th><th>Uptake</th></tr>{table}</table>"
        )
        self._set_exchanges(None)
        self._set_actions("", Path(source) if source and Path(source).exists() else None)

    def show_run(self, entry: RunEntry, inspected: dict[str, object], command: str) -> None:
        self.title_label.setText(f"Run · {entry.label}")
        manifest = inspected.get("manifest")
        solver = manifest.get("solver") if isinstance(manifest, dict) else None
        body = (
            _row("Status", inspected.get("status", entry.status))
            + _row("Artifact integrity", inspected.get("artifact_integrity"))
            + _row("run_hash", inspected.get("run_hash"))
            + _row("Solver", _SOLVER_TEXT.get(str(solver), solver))
            + _row("Folder", entry.path)
        )
        self.details.setHtml(body)
        self._set_exchanges(None)
        self._set_actions(command, entry.path)

    def show_analysis(self, title: str, description: str, cli: str) -> None:
        self.title_label.setText(title)
        self.details.setHtml(f"{html.escape(description)}<br><br>" + _row("CLI", cli))
        self._set_exchanges(None)
        self._set_actions("", None)

    def current_command(self) -> str:
        return self._command

    def current_path(self) -> Path | None:
        return self._path

    def _copy_command(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None and self._command:
            clipboard.setText(self._command)

    def _reveal(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if self._path is not None:
            target = self._path if self._path.is_dir() else self._path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
```

`cmig/gui/app.py`: `class RuntimeJobsPanel(QTableWidget): ...` 블록 전체를 지우고, import 블록에 다음 줄을 추가한다. 기존 테스트와 `JobsBridge`가 같은 이름을 쓴다:
```python
from cmig.gui.activity import RuntimeJobsPanel
```

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_panels.py tests/test_app_shell.py && uv run --no-sync mypy cmig && uv run --no-sync ruff check .`
Expected: PASS. 이 단계에서는 `test_app_shell.py`도 그대로 통과해야 한다(클래스를 옮기기만 했음).

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/activity.py cmig/gui/inspector.py cmig/gui/app.py tests/test_workspace_panels.py
git commit -m "feat(gui): inspector panel and activity pane

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 6: 주 창 개편 — 메뉴, 툴바, 사이드바·가운데·상세·작업 창, 빈 화면 (`cmig/gui/app.py`)

**Files:**
- Modify: `cmig/gui/app.py`(`CmigMainWindow.__init__`의 화면 조립부, `_install_workflow_actions`, `_set_advanced_tabs_visible`, `_open_explorer_item`, `_register_run_output`, `self.tabs.setCurrentWidget(...)` 호출 18곳, `load_run_dir`의 `self.explorer.add_run` 호출, `I18N` 새 키)
- Modify: `cmig/gui/__main__.py`(시작 시 마지막 프로젝트 다시 열기)
- Test: `tests/test_workspace_shell.py`
- Modify tests: `tests/test_app_shell.py`, `tests/test_gui_round5_p2.py`, `tests/test_gui_audit_regressions.py`, `tests/test_round7_gui_graph_profile.py`, `tests/test_gui_search_output.py`, `tests/test_gui_search_parity.py`, `tests/test_gui_search_inspector.py`, `tests/test_gui_search_cancel.py`

**Interfaces:**
- Consumes: Task 3 `ProjectSession`, `RecentProjects`, Task 4 `WorkspaceSidebar`, `ANALYSES`, Task 5 `InspectorPanel`, `ActivityPane`, `command_line`
- Produces (`CmigMainWindow`):
  - 속성:
    - `session: ProjectSession`, `recent: RecentProjects`, `sidebar: WorkspaceSidebar`, `inspector: InspectorPanel`, `activity: ActivityPane`, `jobs_panel`(= `activity.jobs`, 기존 이름 유지)
    - `pages: QStackedWidget`, `welcome_page`, `empty_models_page`, `community_result_page`(QTabWidget: Profile, Graph)
    - `analysis_pages: dict[str, QWidget]`, `current_analysis: str | None`
  - 액션(`QAction`):
    - File·Edit·View: `new_project_action`, `open_project_action`, `close_project_action`, `add_models_action`, `add_models_folder_action`, `add_agora2_action`, `add_medium_action`, `open_run_action`, `show_project_action`, `rename_action`, `remove_action`, `undo_action`, `redo_action`, `toggle_sidebar_action`, `toggle_inspector_action`, `toggle_activity_action`
    - 실행: `run_action`, `cancel_job_action`, `demo_run_action`
    - 분석: `analysis_actions: dict[str, QAction]`
  - 메서드:
    - `show_analysis(key: str) -> None`, `_show_page(widget: QWidget) -> None`
    - `open_project(path: Path) -> bool`, `create_project(path: Path, name: str | None) -> bool`, `close_project() -> None`
    - `refresh_workspace() -> None`
  - `self.tabs`, `self.explorer`, `advanced_tools_action`, `import_model_action`, `run_fixture_action`를 제거한다. `_set_advanced_tabs_visible`도 제거한다.
  - 분석 key → 화면: `search`·`gene_ko`·`growth` → `search_view`(gene_ko·growth는 해당 줄로 스크롤), `host` → `host_view`, `dynamics` → `dynamics_view`, `community` → `community_builder`, `medium` → `medium_editor`, `sweep` → `sweep_view`, `sandbox` → `sandbox_view`, `compare` → `scenario_compare`
  - Run(⌘R) 대상: `search` → `run_search_fixture`, `gene_ko` → `run_gene_ko_search`, `host` → `run_host_microbe_bigg`, `dynamics` → `run_dfba`, `community` → `run_community_solve`, `medium` → `run_medium_growth_check`, `sweep` → `run_sweep_from_view`. 나머지(`growth`, `sandbox`, `compare`)는 Run을 흐리게 하고 tooltip에 "Use the buttons on this page"를 단다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_shell.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.gui.project_session import RecentProjects  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def window(tmp_path: Path):
    w = build_main_window()
    w.recent = RecentProjects(QSettings(str(tmp_path / "recent.ini"), QSettings.Format.IniFormat))
    yield w
    w.close_project()


def _menu(w, title: str) -> list[str]:
    for action in w.menuBar().actions():
        if action.text().replace("&", "") == title:
            return [a.text() for a in action.menu().actions() if not a.isSeparator()]
    raise AssertionError(f"no {title} menu")


def test_standard_menus_and_shortcuts(window) -> None:
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert titles == ["File", "Edit", "View", "Analysis", "Window", "Help"]
    assert _menu(window, "File")[:4] == [
        "New Project…", "Open Project…", "Open Recent", "Close Project",
    ]
    assert "Add Models…" in _menu(window, "File")
    assert "Add Models from AGORA2…" in _menu(window, "File")
    assert window.add_models_action.shortcut().toString() == "Ctrl+Shift+A"
    assert window.run_action.shortcut().toString() == "Ctrl+R"
    assert window.toggle_inspector_action.shortcut().toString() == "Ctrl+Alt+I"
    analysis = _menu(window, "Analysis")
    assert analysis[:5] == [
        "Combination Search", "Gene Knockout", "Strain Growth & Ratio", "Host–Microbe", "Dynamics",
    ]
    assert analysis[-2:] == ["Run", "Cancel"]
    assert "Try Demo Run" in _menu(window, "Help")


def test_no_project_shows_welcome_and_dims_project_actions(window) -> None:
    assert window.pages.currentWidget() is window.welcome_page
    assert not window.add_models_action.isEnabled()
    assert not window.run_action.isEnabled()
    assert window.open_run_action.isEnabled()
    assert window.windowTitle() == "CMIG"


def test_open_project_shows_models_and_title(window, tmp_path: Path) -> None:
    make_project(tmp_path / "study", ["a", "b"])
    assert window.open_project(tmp_path / "study")
    assert window.windowTitle() == "study — CMIG"
    assert window.add_models_action.isEnabled()
    assert window.sidebar.topLevelItem(0).text(0) == "MODELS (2)"
    assert window.recent.paths()[0] == (tmp_path / "study").resolve()


def test_open_locked_or_corrupt_project_reports_on_welcome(window, tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "cmig-project.json").write_text("{broken")
    assert not window.open_project(bad)
    assert "not valid JSON" in window.welcome_message.text()
    assert window.pages.currentWidget() is window.welcome_page


def test_empty_project_shows_drop_hint(window, tmp_path: Path) -> None:
    make_project(tmp_path / "empty", [])
    window.open_project(tmp_path / "empty")
    assert window.pages.currentWidget() is window.empty_models_page


def test_selecting_analysis_switches_page_and_inspector(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["a"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("analyses", "host")
    assert window.pages.currentWidget() is window.host_view
    assert window.inspector.title_label.text() == "Host–Microbe"
    assert window.run_action.isEnabled()
    window.sidebar.select("analyses", "growth")
    assert window.pages.currentWidget() is window.search_view
    assert not window.run_action.isEnabled()


def test_selecting_model_updates_inspector(window, tmp_path: Path) -> None:
    make_project(tmp_path / "s", ["E_rectale"])
    window.open_project(tmp_path / "s")
    window.sidebar.select("models", "E_rectale")
    assert window.inspector.title_label.text() == "Model · E_rectale"


def test_view_toggles(window) -> None:
    window.show()
    window.toggle_inspector_action.trigger()
    assert not window.inspector.isVisible()
    assert window.toggle_inspector_action.text() == "Show Inspector"
    window.toggle_inspector_action.trigger()
    assert window.inspector.isVisible()
    assert window.toggle_inspector_action.text() == "Hide Inspector"


def test_every_toolbar_command_is_also_in_a_menu(window) -> None:
    from PySide6.QtWidgets import QWidgetAction

    menu_actions = set()
    for top in window.menuBar().actions():
        menu_actions.update(top.menu().actions())
    commands = [a for a in window.workspace_toolbar.actions()
                if not a.isSeparator() and not isinstance(a, QWidgetAction)]
    assert {a.text() for a in commands} == {
        "Hide Sidebar", "Add Models…", "Hide Inspector", "Run",
    }
    for action in commands:
        assert action in menu_actions, action.text()


def test_korean_mode_opens_every_page_without_missing_strings(tmp_path: Path) -> None:
    from cmig.gui.sidebar import ANALYSES

    make_project(tmp_path / "ko", ["a"])
    w = build_main_window(lang="ko")
    w.recent = RecentProjects(QSettings(str(tmp_path / "r.ini"), QSettings.Format.IniFormat))
    assert w.open_project(tmp_path / "ko")
    for key, _label in ANALYSES:
        w.show_analysis(key)
    w.sidebar.select("models", "a")
    w.close_project()


@pytest.mark.parametrize("size", [(1280, 800), (1500, 950)])
def test_window_fits_target_sizes(window, tmp_path: Path, size: tuple[int, int]) -> None:
    make_project(tmp_path / "g", [f"m{i}" for i in range(12)])
    window.open_project(tmp_path / "g")
    window.resize(*size)
    window.show()
    for key in ("search", "host", "dynamics", "community", "medium", "sweep"):
        window.show_analysis(key)
        APP.processEvents()
        assert window.width() <= size[0] and window.height() <= size[1], key
```


- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_shell.py`
Expected: FAIL (`AttributeError: 'CmigMainWindow' object has no attribute 'recent'` 등).

- [ ] **Step 3: 구현 — 화면 조립부 교체**

`CmigMainWindow.__init__`에서 `self.explorer = ProjectExplorer(self.tr_map)`와 `self.jobs_panel = RuntimeJobsPanel(self.tr_map)` 두 줄을 다음으로 바꾼다:
```python
        from cmig.gui.activity import ActivityPane
        from cmig.gui.inspector import InspectorPanel
        from cmig.gui.project_session import ProjectSession, RecentProjects
        from cmig.gui.sidebar import WorkspaceSidebar

        self.session = ProjectSession(self)
        self.recent = RecentProjects()
        self.sidebar = WorkspaceSidebar()
        self.inspector = InspectorPanel()
        self.activity = ActivityPane(self.tr_map)
        self.jobs_panel = self.activity.jobs
        self._external_runs: list[Any] = []
```

`center = QWidget()`부터 `self.setCentralWidget(splitter)`까지(탭 생성, 고급 탭 목록, splitter)를 다음으로 바꾼다. 분석 화면 객체 생성 줄(`self.model_manager = ...`부터 `self.dynamics_view = DfbaSpatialView()`까지)은 그대로 두고, `self._primary_tabs`, `self._advanced_tabs`, `self._advanced_tabs_visible`, `self.tabs` 관련 줄만 지운다:
```python
        self.central_stack = QStackedWidget()      # kept: set_central() still docks extra views
        self.pages = self.central_stack
        self.welcome_page = self._build_welcome_page()
        self.empty_models_page = self._build_empty_models_page()
        self.community_result_page = QTabWidget()
        self.community_result_page.addTab(self.profile_view, "Profile")
        self.community_result_page.addTab(self.graph_tab, "Graph")
        self.analysis_pages: dict[str, QWidget] = {
            "search": self.search_view,
            "gene_ko": self.search_view,
            "growth": self.search_view,
            "host": self.host_view,
            "dynamics": self.dynamics_view,
            "community": self.community_builder,
            "medium": self.medium_editor,
            "sweep": self.sweep_view,
            "sandbox": self.sandbox_view,
            "compare": self.scenario_compare,
        }
        for page in [self.welcome_page, self.empty_models_page, self.community_result_page,
                     self.model_manager, *dict.fromkeys(self.analysis_pages.values())]:
            self.pages.addWidget(page)
        self.current_analysis: str | None = None

        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        horizontal.setChildrenCollapsible(False)
        horizontal.addWidget(self.sidebar)
        horizontal.addWidget(self.pages)
        horizontal.addWidget(self.inspector)
        horizontal.setStretchFactor(1, 1)
        horizontal.setSizes([220, 760, 280])
        vertical.addWidget(horizontal)
        vertical.addWidget(self.activity)
        vertical.setStretchFactor(0, 1)
        vertical.setSizes([640, 160])
        self.activity.setVisible(False)
        self.setCentralWidget(vertical)
        self.setAcceptDrops(True)
```
`self.statusBar()`의 `integrity_label`과 `integrity_details_btn` 두 위젯 추가 줄은 지운다(무결성은 상세 패널로 옮김). 대신 솔버 상태 label을 추가한다:
```python
        self.solver_label = QLabel("")
        self.statusBar().addPermanentWidget(self.solver_label)
        self._refresh_solver_label()
```
`_install_workflow_actions()` 다음 줄 `self.explorer.itemDoubleClicked.connect(self._open_explorer_item)`은 지우고, 다음을 넣는다:
```python
        self.sidebar.selection_changed.connect(self._on_sidebar_selection)
        self.sidebar.files_dropped.connect(self.add_model_paths)
        self.sidebar.context_requested.connect(self._show_sidebar_menu)
        self.activity.cancel_requested.connect(self._cancel_job_id)
        self.jobs_panel.itemSelectionChanged.connect(self._show_selected_job_detail)
        self.session.opened.connect(self.refresh_workspace)
        self.session.closed.connect(self.refresh_workspace)
        self.session.models_changed.connect(self.refresh_workspace)
        self.session.media_changed.connect(self.refresh_workspace)
        self.session.runs_changed.connect(self.refresh_workspace)
        self.refresh_workspace()
```
`self.integrity_label`과 `self._integrity_detail`을 쓰던 곳(`_inspect_gui_run` 등)은 다음 메서드 호출로 바꾼다. `self.integrity_label.setText(x)` 형태의 모든 줄을 `self._last_integrity = x`로 바꾸고, `_integrity_detail` 대입은 그대로 둔다(상세 패널이 읽음):
```python
        self._last_integrity = "Integrity: no run loaded"
```

- [ ] **Step 4: 구현 — 새 메서드 추가**

`CmigMainWindow`에 다음 메서드를 추가한다(`_install_workflow_actions`와 `_set_advanced_tabs_visible`, `_open_explorer_item`, `_import_model_dialog`, `_run_fixture_dialog`는 이것으로 대체하고 지운다):
```python
    # ── pages ────────────────────────────────────────────────────────────────────────────
    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        title = QLabel("<h2>CMIG</h2>Community metabolic interaction analysis")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.welcome_message = QLabel("")
        self.welcome_message.setWordWrap(True)
        self.welcome_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        new_btn = QPushButton("New Project…")
        new_btn.clicked.connect(self._new_project_dialog)
        open_btn = QPushButton("Open Project…")
        open_btn.clicked.connect(self._open_project_dialog)
        run_btn = QPushButton("Open Run…")
        run_btn.clicked.connect(self._open_run_dialog)
        for button in (new_btn, open_btn, run_btn):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.welcome_recent = QListWidget()
        self.welcome_recent.setMaximumWidth(420)
        self.welcome_recent.itemActivated.connect(
            lambda item: self.open_project(Path(item.data(Qt.ItemDataRole.UserRole)))
        )
        recent_row = QHBoxLayout()
        recent_row.addStretch(1)
        recent_row.addWidget(self.welcome_recent)
        recent_row.addStretch(1)
        layout.addWidget(title)
        layout.addLayout(buttons)
        layout.addWidget(self.welcome_message)
        layout.addLayout(recent_row)
        layout.addStretch(2)
        return page

    def _build_empty_models_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        hint = QLabel("Drop SBML, JSON or MAT files or folders here")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        add_btn = QPushButton("Add Models…")
        add_btn.clicked.connect(self._add_models_dialog)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(add_btn)
        row.addStretch(1)
        layout.addWidget(hint)
        layout.addLayout(row)
        layout.addStretch(2)
        return page

    def _show_page(self, widget: QWidget) -> None:
        if self.pages.indexOf(widget) == -1:
            self.pages.addWidget(widget)
        self.pages.setCurrentWidget(widget)

    def _show_models_overview(self) -> None:
        project = self.session.project
        if project is None:
            self._show_page(self.welcome_page)
        elif not project.models:
            self._show_page(self.empty_models_page)
        else:
            self._show_page(self.model_manager)

    # ── actions & menus ──────────────────────────────────────────────────────────────────
    def _action(self, text: str, slot: Any, shortcut: Any = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _install_workflow_actions(self) -> None:
        from cmig.gui.sidebar import ANALYSES, ANALYSIS_SEPARATOR_AFTER

        self.new_project_action = self._action("New Project…", self._new_project_dialog,
                                               QKeySequence.StandardKey.New)
        self.open_project_action = self._action("Open Project…", self._open_project_dialog,
                                                QKeySequence.StandardKey.Open)
        self.recent_menu = QMenu("Open Recent", self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.close_project_action = self._action("Close Project", self.close_project,
                                                 QKeySequence.StandardKey.Close)
        self.add_models_action = self._action("Add Models…", self._add_models_dialog,
                                              "Ctrl+Shift+A")
        self.add_models_folder_action = self._action("Add Models from Folder…",
                                                     self._add_models_folder_dialog)
        self.add_agora2_action = self._action("Add Models from AGORA2…", self._agora2_dialog)
        self.add_medium_action = self._action("Add Medium…", self._add_medium_dialog)
        self.open_run_action = self._action("Open Run…", self._open_run_dialog, "Ctrl+Shift+O")
        self.show_project_action = self._action("Show Project in Finder", self._reveal_project)
        self.undo_action = self.session.undo_stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.session.undo_stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self.rename_action = self._action("Rename…", self._rename_selected_model)
        self.remove_action = self._action("Remove from Project", self._remove_selected_models,
                                          QKeySequence.StandardKey.Delete)
        self.toggle_sidebar_action = self._action("Hide Sidebar",
                                                  lambda: self._toggle(self.sidebar, "Sidebar"),
                                                  "Ctrl+Meta+S")
        self.toggle_inspector_action = self._action(
            "Hide Inspector", lambda: self._toggle(self.inspector, "Inspector"), "Ctrl+Alt+I")
        self.toggle_activity_action = self._action(
            "Show Activity", lambda: self._toggle(self.activity, "Activity"), "Ctrl+Shift+Y")
        self.analysis_actions = {
            key: self._action(label, lambda _=False, k=key: self.show_analysis(k))
            for key, label in ANALYSES
        }
        self.run_action = self._action("Run", self._run_current_analysis, "Ctrl+R")
        self.cancel_job_action = self._action("Cancel", self._cancel_selected_job, "Ctrl+.")
        self.demo_run_action = self._action("Try Demo Run", self._run_fixture_dialog)
        guide = self._action("CMIG User Guide", self._open_user_guide)

        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addActions([self.new_project_action, self.open_project_action])
        file_menu.addMenu(self.recent_menu)
        file_menu.addAction(self.close_project_action)
        file_menu.addSeparator()
        file_menu.addActions([self.add_models_action, self.add_models_folder_action,
                              self.add_agora2_action, self.add_medium_action])
        file_menu.addSeparator()
        file_menu.addActions([self.open_run_action, self.show_project_action])
        edit_menu = bar.addMenu("&Edit")
        edit_menu.addActions([self.undo_action, self.redo_action])
        edit_menu.addSeparator()
        edit_menu.addActions([self.rename_action, self.remove_action])
        view_menu = bar.addMenu("&View")
        view_menu.addActions([self.toggle_sidebar_action, self.toggle_inspector_action,
                              self.toggle_activity_action])
        analysis_menu = bar.addMenu("&Analysis")
        for key, _label in ANALYSES:
            analysis_menu.addAction(self.analysis_actions[key])
            if key == ANALYSIS_SEPARATOR_AFTER:
                analysis_menu.addSeparator()
        analysis_menu.addSeparator()
        analysis_menu.addActions([self.run_action, self.cancel_job_action])
        window_menu = bar.addMenu("&Window")
        window_menu.addAction(self._action("Minimize", self.showMinimized, "Ctrl+M"))
        window_menu.addAction(self._action("Zoom", self._zoom))
        help_menu = bar.addMenu("&Help")
        help_menu.addActions([guide, self.demo_run_action])

        toolbar = self.addToolBar("Workspace")
        toolbar.setObjectName("workspace_toolbar")
        toolbar.setMovable(False)
        self.workspace_toolbar = toolbar
        toolbar.addAction(self.toggle_sidebar_action)
        self.project_title = QLabel("No Project")
        toolbar.addWidget(self.project_title)
        toolbar.addSeparator()
        toolbar.addAction(self.add_models_action)
        new_analysis = QToolButton()
        new_analysis.setText("New Analysis")
        new_analysis.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        new_analysis.setMenu(analysis_menu)
        toolbar.addWidget(new_analysis)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addAction(self.toggle_inspector_action)
        toolbar.addAction(self.run_action)

    def _toggle(self, widget: QWidget, name: str) -> None:
        widget.setVisible(not widget.isVisible())
        verb = "Hide" if widget.isVisible() else "Show"
        action = {"Sidebar": self.toggle_sidebar_action, "Inspector": self.toggle_inspector_action,
                  "Activity": self.toggle_activity_action}[name]
        action.setText(f"{verb} {name}")

    def _zoom(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _open_user_guide(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl("https://github.com/jyryu3161/CMIG/blob/main/docs/USER_GUIDE.md"))

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        for path in self.recent.paths():
            action = self.recent_menu.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(lambda _=False, p=path: self.open_project(p))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("Clear Menu")
        clear.triggered.connect(self.recent.clear)

    # ── project lifecycle ────────────────────────────────────────────────────────────────
    def open_project(self, path: Path) -> bool:
        from cmig.io.project import ProjectError

        try:
            self.session.open(Path(path))
        except ProjectError as exc:
            self.welcome_message.setText(f"Could not open {Path(path).name}: {exc}")
            self._show_page(self.welcome_page)
            return False
        self.recent.add(Path(path))
        return True

    def create_project(self, path: Path, name: str | None = None) -> bool:
        from cmig.io.project import ProjectError

        try:
            self.session.create(Path(path), name)
        except ProjectError as exc:
            self.welcome_message.setText(f"Could not create the project: {exc}")
            return False
        self.recent.add(Path(path))
        return True

    def close_project(self) -> None:
        """Cancel queued/running jobs (cooperative; an in-flight solve finishes) and unlock."""
        for job_id in list(self.bridge._job_ids):
            if self.runner.poll(job_id).status in (JobStatus.PENDING, JobStatus.RUNNING):
                self._cancel_job_id(job_id)
        self.session.close()

    def _new_project_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "New Project", "", "CMIG project folder")
        if path:
            self.create_project(Path(path))

    def _open_project_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open Project")
        if path:
            self.open_project(Path(path))

    def _reveal_project(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        if self.session.project is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.session.project.root)))

    def refresh_workspace(self) -> None:
        from cmig.gui.editors import installed_medium_presets

        project = self.session.project
        has_project = project is not None
        for action in (self.add_models_action, self.add_models_folder_action,
                       self.add_agora2_action, self.add_medium_action, self.close_project_action,
                       self.show_project_action, self.rename_action, self.remove_action):
            action.setEnabled(has_project)
        for action in self.analysis_actions.values():
            action.setEnabled(has_project)
        self.setWindowTitle("CMIG" if project is None else f"{project.name} — CMIG")
        self.project_title.setText("No Project" if project is None else project.name)
        pending = list(getattr(self, "_pending_imports", []))
        self.sidebar.set_models([] if project is None else project.models, pending)
        self.sidebar.set_media(installed_medium_presets(), [] if project is None else project.media)
        self.sidebar.set_runs(self.session.runs(), self._external_runs)
        self.welcome_recent.clear()
        for path in self.recent.paths():
            item = QListWidgetItem(f"{path.name}  —  {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.welcome_recent.addItem(item)
        self._refresh_pickers()
        if project is None:
            self.current_analysis = None
            self._show_page(self.welcome_page)
            self.inspector.clear()
        elif self.pages.currentWidget() in (self.welcome_page, self.empty_models_page):
            self._show_models_overview()
        self._update_run_action()

    def _refresh_pickers(self) -> None:
        """Populated in Task 9 once the pickers exist."""

    # ── selection → page + inspector ─────────────────────────────────────────────────────
    _RUNNERS = {
        "search": "run_search_fixture",
        "gene_ko": "run_gene_ko_search",
        "host": "run_host_microbe_bigg",
        "dynamics": "run_dfba",
        "community": "run_community_solve",
        "medium": "run_medium_growth_check",
        "sweep": "run_sweep_from_view",
    }
    _DESCRIPTIONS = {
        "search": ("Rank model combinations by a target metabolite.", "cmig search"),
        "gene_ko": ("Rank single-gene knockouts of a fixed combination.", "cmig gene-ko-search"),
        "growth": ("Per-strain growth and one-member ratio sweep.",
                   "cmig strain-growth / abundance-impact"),
        "host": ("Couple a host model with microbial models.", "cmig host-microbe-bigg"),
        "dynamics": ("Well-mixed dFBA and spatial medium preview.",
                     "cmig dfba / spatial-preview"),
        "community": ("Community FBA of selected members.", "cmig solve"),
        "medium": ("Edit a medium, check growth, find a minimal medium.",
                   "cmig solve / minimal-medium"),
        "sweep": ("Parameter sweep across media, abundances and solvers.", "cmig sweep"),
        "sandbox": ("Preview one bound change before committing it.", "cmig sandbox-fixture"),
        "compare": ("Compare two completed runs.", "cmig inspect-run"),
    }

    def show_analysis(self, key: str) -> None:
        from cmig.gui.sidebar import ANALYSES

        page = self.analysis_pages[key]
        self.current_analysis = key
        self._show_page(page)
        if key == "gene_ko":
            self.search_view.scroll_area.ensureWidgetVisible(self.search_view.ko_members_input)
        elif key == "growth":
            self.search_view.scroll_area.ensureWidgetVisible(self.search_view.growth_member_input)
        title = dict(ANALYSES)[key]
        description, cli = self._DESCRIPTIONS[key]
        self.inspector.show_analysis(title, description, cli)
        self._update_run_action()

    def _update_run_action(self) -> None:
        key = self.current_analysis
        enabled = (self.session.project is not None and key in self._RUNNERS
                   and self.pages.currentWidget() is self.analysis_pages.get(key or ""))
        self.run_action.setEnabled(bool(enabled))
        self.run_action.setToolTip(
            "Run this analysis (⌘R)" if enabled else "Use the buttons on this page"
        )

    def _run_current_analysis(self) -> None:
        if self.current_analysis in self._RUNNERS:
            getattr(self, self._RUNNERS[self.current_analysis])()

    def _on_sidebar_selection(self, group: str, key: str) -> None:
        project = self.session.project
        if group == "analyses":
            self.show_analysis(key)
        elif group == "models" and project is not None:
            entry = project.model(key)
            self.inspector.show_model(project, entry, self._model_exchanges(entry))
            self._show_models_overview()
            self.current_analysis = None
            self._update_run_action()
        elif group == "media":
            self._inspect_medium(key)
        elif group == "runs":
            self._open_run_entry(Path(key))

    def _model_exchanges(self, entry: Any) -> list[str] | None:
        from cmig.io.model_import import import_model
        from cmig.io.project import model_path

        if self.session.project is None or entry.status == "failed" or entry.integrity != "ok":
            return None
        cache = getattr(self, "_exchange_cache", {})
        self._exchange_cache = cache
        if entry.sha256 not in cache:
            try:
                cache[entry.sha256] = list(import_model(model_path(self.session.project, entry)).exchanges)
            except Exception:  # noqa: BLE001 - inspector shows what it can
                cache[entry.sha256] = None
        return cache[entry.sha256]

    def _inspect_medium(self, key: str) -> None:
        import csv

        from cmig.gui.editors import installed_medium_preset_path
        from cmig.io.project import medium_path

        project = self.session.project
        if key.startswith("preset:"):
            path = installed_medium_preset_path(key.split(":", 1)[1])
            title = key.split(":", 1)[1]
        elif project is not None:
            entry = project.medium(key.split(":", 1)[1])
            path, title = medium_path(project, entry), entry.id
        else:
            return
        rows: list[tuple[str, str]] = []
        if path.suffix.lower() == ".csv":
            with path.open(newline="") as handle:
                for record in csv.reader(handle):
                    if len(record) >= 2 and record[0] and not record[0].startswith("#"):
                        rows.append((record[0], record[1]))
        self.inspector.show_medium(title, rows[1:] if rows else rows, str(path))

    def _open_run_entry(self, run_dir: Path) -> None:
        from cmig.cli.main import _inspect_run_dir
        from cmig.gui.project_session import inspect_run

        self.load_run_dir(run_dir)
        try:
            inspected = _inspect_run_dir(run_dir)
        except Exception:  # noqa: BLE001
            inspected = {}
        command = getattr(self, "_run_commands", {}).get(str(run_dir), "")
        self.inspector.show_run(inspect_run(run_dir), inspected, command)

    def _show_sidebar_menu(self, group: str, keys: list[str]) -> None:
        if group != "models" or not keys:
            return
        menu = QMenu(self)
        search = menu.addAction("Search with Selected…")
        search.triggered.connect(lambda: self._search_with_models(keys))
        menu.addSeparator()
        menu.addAction(self.rename_action)
        menu.addAction(self.remove_action)
        menu.addSeparator()
        reveal = menu.addAction("Show in Finder")
        reveal.triggered.connect(self.inspector._reveal)
        menu.exec(QCursor.pos())

    def _search_with_models(self, keys: list[str]) -> None:
        """Populated in Task 9 (sets the Search model picker), then shows the page."""
        self.show_analysis("search")

    def _remove_selected_models(self) -> None:
        self.session.remove_models(self.sidebar.selected_keys("models"))

    def _rename_selected_model(self) -> None:
        from cmig.io.project import ProjectError

        keys = self.sidebar.selected_keys("models")
        if len(keys) != 1:
            return
        new_id, ok = QInputDialog.getText(self, "Rename Model", "New model id:", text=keys[0])
        if ok and new_id and new_id != keys[0]:
            try:
                self.session.rename_model(keys[0], new_id.strip())
            except ProjectError as exc:
                self.statusBar().showMessage(str(exc), 8000)

    def _cancel_job_id(self, job_id: str) -> None:
        if job_id in self._search_jobs:
            self.cancel_search()
            return
        self.bridge.cancelling.add(job_id)
        self.runner.cancel(job_id)
        self.bridge.refresh()

    def _show_selected_job_detail(self) -> None:
        job_id = self.jobs_panel.selected_job_id()
        if not job_id:
            return
        job = self.runner.poll(job_id)
        log = job.error or ""
        if isinstance(job.result, dict):
            log = str(job.result.get("cli_error") or job.result.get("input_diagnostic") or log)
        self.activity.set_job_detail(log, getattr(self, "_job_commands", {}).get(job_id, ""))

    def _refresh_solver_label(self) -> None:
        try:
            import gurobipy  # noqa: F401

            self.solver_label.setText("Solver: Gurobi (full-flux)")
        except ImportError:
            self.solver_label.setText("Solver: Gurobi not available")

    # ── drag & drop on the whole window ─────────────────────────────────────────────────
    def dragEnterEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        from cmig.gui.sidebar import droppable_paths

        files, _ = droppable_paths(list(event.mimeData().urls()))
        if files and self.session.project is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
        local = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if local and self.session.project is not None:
            self.add_model_paths(local)
            event.acceptProposedAction()

    def add_model_paths(self, paths: list[Path]) -> str:
        """Implemented in Task 7 (background import)."""
        return ""

    def _add_models_dialog(self) -> None:
        """Implemented in Task 7."""

    def _add_models_folder_dialog(self) -> None:
        """Implemented in Task 7."""

    def _add_medium_dialog(self) -> None:
        """Implemented in Task 7."""

    def _agora2_dialog(self) -> None:
        """Implemented in Task 8."""
```

`cmig/gui/editors.py`에 preset helper 두 개를 추가한다. 기존 `MediumEditor`의 preset 목록 읽기와 같은 자원(`cmig.resources/medium_presets/*.csv`)을 쓴다:
```python
def installed_medium_presets() -> list[str]:
    """Names (file stems) of the medium presets shipped inside the package."""
    from importlib import resources

    folder = resources.files("cmig.resources").joinpath("medium_presets")
    return sorted(item.name[:-4] for item in folder.iterdir() if item.name.endswith(".csv"))


def installed_medium_preset_path(name: str) -> Path:
    from importlib import resources

    if name not in installed_medium_presets():
        raise ValueError(f"unknown medium preset {name!r}")
    return Path(str(resources.files("cmig.resources").joinpath("medium_presets", f"{name}.csv")))
```

`cmig/gui/app.py` import 블록에 `QInputDialog`, `QListWidget`, `QListWidgetItem`, `QMenu`, `QSizePolicy`, `QToolButton`(QtWidgets)과 `QCursor`(QtGui)를 추가한다.

- [ ] **Step 5: 구현 — 기존 호출부 정리**

1. `self.tabs.setCurrentWidget(X)` 호출 18곳을 아래 규칙으로 바꾼다(정확한 위치는 `grep -n "self.tabs" cmig/gui/app.py`로 찾는다):
   - `X`가 `self.profile_view`이면 `self._show_page(self.community_result_page); self.community_result_page.setCurrentWidget(self.profile_view)`
   - `X`가 `self.graph_tab`이면 같은 방식으로 Graph 쪽
   - 나머지는 `self._show_page(X)`
2. `self.explorer.add_run(name, path)` 호출(`load_run_dir`, `load_search_dir` 등)과 `_register_run_output` 본문을 다음으로 바꾼다:
```python
    def _register_run_output(self, out_dir: Path) -> None:
        """A completed run inside the project appears in RUNS; an outside run is listed as opened."""
        from cmig.gui.project_session import inspect_run

        project = self.session.project
        if project is not None and out_dir.resolve().parent == project.runs_dir.resolve():
            self.session.refresh_runs()
            return
        if all(entry.path != out_dir for entry in self._external_runs):
            self._external_runs.append(inspect_run(out_dir))
        self.refresh_workspace()
```
   `load_*` 메서드 안의 `self.explorer.add_run(run_dir.name, run_dir)`는 `self._register_run_output(run_dir)`로 바꾼다.
3. `import_model_file`은 지우지 않는다(Task 7에서 대체). `self.explorer.add_model(...)`과 `self.tabs.setCurrentWidget(self.model_manager)` 두 줄만 지운다.
4. `_cancel_selected_job`의 본문을 `job_id = self.jobs_panel.selected_job_id()` 다음 `if job_id: self._cancel_job_id(job_id)`로 줄인다.
5. `ProjectExplorer` 클래스를 지운다.
6. `closeEvent`의 `super().closeEvent(event)` 직전에 `self.session.close()`를 넣는다.

`cmig/gui/__main__.py`에서 창을 띄운 직후(`window.show()` 다음)에 다음을 넣는다:
```python
    recents = window.recent.paths()
    if recents and recents[0].exists():
        window.open_project(recents[0])
```

- [ ] **Step 6: 기존 GUI 테스트 옮기기**

`grep -nE "\.tabs\b|\.explorer\b|ProjectExplorer|import_model_action|advanced_tools_action|_set_advanced_tabs_visible|run_fixture_action|integrity_label|integrity_details_btn" tests/*.py`로 나온 줄을 다음 규칙으로 바꾼다. 테스트의 의도(무엇을 확인하는지)는 유지한다.

| 기존 | 새 |
|---|---|
| `w.tabs.currentWidget() is X` | `w.pages.currentWidget() is X`. `X`가 `w.profile_view`/`w.graph_tab`이면 `w.pages.currentWidget() is w.community_result_page and w.community_result_page.currentWidget() is X` |
| `w.tabs.setCurrentWidget(X)` | `w._show_page(X)` |
| `w.tabs.count()`·탭 이름 목록 | `[label for _key, label in ANALYSES]`(`from cmig.gui.sidebar import ANALYSES`) |
| `w.explorer.add_run(...)` / Explorer 자식 확인 | `w.sidebar.topLevelItem(3)`(RUNS)의 자식 텍스트·data 확인 |
| `w._open_explorer_item(item, 0)` | `w._open_run_entry(Path(path))` |
| `w.import_model_action.trigger()` | 프로젝트를 연 뒤 `w.add_models_action` 사용 테스트로 바꾼다(Task 7에서 동작). 이 단계에서는 해당 테스트에 `pytest.mark.skip(reason="replaced in Task 7")`을 붙이지 말고, Task 7의 새 테스트가 같은 의도를 덮으므로 테스트를 지운다. 지운 이유를 커밋 메시지에 적는다. |
| `w.advanced_tools_action`·`_set_advanced_tabs_visible` | 고급 화면이 `ANALYSES`에 있고 `w.show_analysis(key)`로 열리는지 확인으로 바꾼다 |
| `w.run_fixture_action` | `w.demo_run_action` |
| `w.integrity_label.text()` | `w._last_integrity` |
| `w.integrity_details_btn` | 상세 패널: `w.inspector.details.toPlainText()`에 무결성 문구 확인 |

- [ ] **Step 7: 통과 확인**

Run:
```bash
QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_shell.py tests/test_app_shell.py tests/test_gui_round5_p2.py tests/test_gui_audit_regressions.py tests/test_round7_gui_graph_profile.py tests/test_gui_search_output.py tests/test_gui_search_parity.py tests/test_gui_search_inspector.py tests/test_gui_search_cancel.py tests/test_gui_editors_builder.py tests/test_gui_render.py tests/test_gui_views.py tests/test_round8_gui_sweep_overlays.py tests/test_round9_gui_medium_tools.py tests/test_gui_launcher.py tests/test_host_medium_strictness.py ; echo rc=$?
uv run --no-sync mypy cmig && uv run --no-sync ruff check .
```
Expected: 실패 0개, mypy·ruff 오류 없음. 종료 시 rc=139가 나오면 실패 개수로 판정한다(알려진 macOS 종료 문제, `docs/tracking/findings.md`).

- [ ] **Step 8: 화면 캡처 확인**

Run(스크래치 디렉터리에 캡처):
```bash
mkdir -p /tmp/cmig-shots && QT_QPA_PLATFORM=offscreen uv run --no-sync python - <<'EOF'
import os, sys
from pathlib import Path
sys.path.insert(0, "tests")
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
from cmig.gui.app import build_main_window
from gui_project_helpers import make_project
import tempfile
root = Path(tempfile.mkdtemp()) / "Butyrate study"
make_project(root, [f"Strain_{i:02d}" for i in range(12)])
w = build_main_window(); w.resize(1280, 800); w.show()
def snap(name):
    for _ in range(5): app.processEvents()
    w.grab().save(f"/tmp/cmig-shots/{name}.png")
snap("01_welcome")
w.open_project(root); snap("02_project")
for key in ("search", "host", "dynamics", "community", "medium"):
    w.show_analysis(key); snap(f"03_{key}")
w.close_project(); os._exit(0)
EOF
```
캡처한 PNG를 열어 다음을 확인한다:
- 메뉴 막대와 툴바가 세 묶음으로 나뉘어 보이는지
- 사이드바 네 그룹과 상세 패널이 보이는지
- 글자가 잘리거나 겹치지 않는지
- 시작 화면 가운데에 버튼 세 개가 있는지

문제가 보이면 고친 뒤 다시 캡처한다.

- [ ] **Step 9: 커밋**

```bash
git add cmig/gui/app.py cmig/gui/editors.py cmig/gui/__main__.py tests/
git commit -m "feat(gui): workspace window with menus, toolbar, sidebar, inspector and activity

Replaces the tab bar, Project Explorer and right-hand jobs table. Tests that drove the
removed Import Model / Show Advanced Tools buttons move to the new menu actions.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 7: 여러 모델·배지 가져오기 (백그라운드, 진행, 취소, 실패 격리)

**Files:**
- Modify: `cmig/gui/app.py`(`add_model_paths`, `_add_models_dialog`, `_add_models_folder_dialog`, `_add_medium_dialog`, `_poll_completed_jobs`에 import job 처리, `import_model_file` 제거)
- Test: `tests/test_workspace_import.py`

**Interfaces:**
- Consumes:
  - `supported_model_paths`, `add_model_file`, `check_model_file`, `DuplicateModelError`, `add_medium_file`, `ProjectError`(Task 2)
  - `ProjectSession.add_entries`, `add_medium`(Task 3)
  - `JobRunner`·`JobContext`(`ctx.report_progress(done, total)`, `ctx.cancelled`)
- Produces:
  - `CmigMainWindow.add_model_paths(paths: list[Path], *, recursive: bool = True) -> str`(job id, 프로젝트 없거나 파일 없으면 `""`)
  - `self._pending_imports: list[str]`
  - `self._import_jobs: dict[str, list[Path]]`
  - import job 결과: `{"added": [ModelEntry], "failed": [(name, reason)], "duplicates": [(name, existing_id)], "skipped": int, "cancelled_remaining": int}`
  - 가져오기가 끝나면 추가된 모델 전체를 `session.add_entries`로 한 번에 넣는다. Edit > Undo "Add N Models"로 목록에서 뺄 수 있고, 복사한 파일은 남는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_import.py`:
```python
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from cmig.io import project as proj  # noqa: E402
from gui_project_helpers import (  # noqa: E402,F401
    _deterministic_qt_teardown,
    make_project,
    ok_check,
)

APP = QApplication.instance() or QApplication([])


def _wait(window, job_id: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while job_id in window._import_jobs and time.time() < deadline:
        APP.processEvents()
        window._poll_completed_jobs()
        time.sleep(0.02)
    assert job_id not in window._import_jobs, "import job did not finish"


@pytest.fixture
def window(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(proj, "check_model_file", ok_check)
    w = build_main_window()
    make_project(tmp_path / "p", [])
    assert w.open_project(tmp_path / "p")
    yield w
    w.close_project()


def _models(folder: Path, names: list[str]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for name in names:
        path = folder / name
        path.write_text(f"<sbml id='{name}'/>")
        out.append(path)
    return out


def test_add_models_dialog_imports_many_files(window, tmp_path: Path, monkeypatch) -> None:
    files = _models(tmp_path / "in", ["a.xml", "b.json.xml", "c.mat"])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([str(p) for p in files], ""))
    window.add_models_action.trigger()
    _wait(window, next(iter(window._import_jobs)))
    assert [m.id for m in window.session.project.models] == ["a", "b_json", "c"]
    assert window.sidebar.topLevelItem(0).text(0) == "MODELS (3)"
    assert window._pending_imports == []
    assert proj.open_project(window.session.project.root).models[0].status == "ok"


def test_folder_import_reports_skipped_failed_and_duplicates(
    window, tmp_path: Path, monkeypatch
) -> None:
    folder = tmp_path / "pool"
    _models(folder, ["good.xml", "dup1.xml"])
    (folder / "dup2.xml").write_text("<sbml id='dup1.xml'/>")  # same bytes as dup1
    (folder / "readme.txt").write_text("x")

    def flaky(path: Path) -> proj.ModelCheck:
        if path.name.startswith("good"):
            return ok_check(path)
        return proj.ModelCheck("failed", "ValueError: bad SBML", None, None, None, [], None, [])

    monkeypatch.setattr(proj, "check_model_file", flaky)
    job = window.add_model_paths([folder])
    _wait(window, job)
    statuses = {m.id: m.status for m in window.session.project.models}
    assert statuses == {"dup1": "failed", "good": "ok"}
    message = window.statusBar().currentMessage()
    assert "2 added" in message and "1 duplicate" in message and "1 skipped" in message
    assert "1 failed" in message


def test_import_reports_progress_and_cancel_stops_remaining(
    window, tmp_path: Path, monkeypatch
) -> None:
    files = _models(tmp_path / "many", [f"m{i:03d}.xml" for i in range(200)])
    gate = threading.Event()

    def slow(path: Path) -> proj.ModelCheck:
        if path.name == "m002.xml":
            gate.wait(5)
        return ok_check(path)

    monkeypatch.setattr(proj, "check_model_file", slow)
    job = window.add_model_paths(files)
    deadline = time.time() + 5
    while time.time() < deadline:
        APP.processEvents()
        progress = window.runner.poll(job).progress
        if progress and progress[0] >= 2:
            break
        time.sleep(0.01)
    assert window.runner.poll(job).progress[1] == 200
    assert not window.activity.isHidden(), "activity pane opens when an import starts"
    window._cancel_job_id(job)
    gate.set()
    _wait(window, job)
    count = len(window.session.project.models)
    assert 2 <= count < 200
    assert "cancelled" in window.statusBar().currentMessage()


def test_drop_on_window_starts_import(window, tmp_path: Path, monkeypatch) -> None:
    files = _models(tmp_path / "drop", ["x.xml"])
    window.sidebar.files_dropped.emit(files)
    _wait(window, next(iter(window._import_jobs)))
    assert [m.id for m in window.session.project.models] == ["x"]


def test_add_medium_dialog(window, tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "diet.csv"
    src.write_text("exchange,uptake\nEX_glc__D_e,10\n")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: ([str(src)], ""))
    window.add_medium_action.trigger()
    assert [m.id for m in window.session.project.media] == ["diet"]


def test_without_project_import_is_refused(tmp_path: Path) -> None:
    w = build_main_window()
    assert w.add_model_paths([tmp_path]) == ""
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_import.py`
Expected: FAIL (`AttributeError: ... '_import_jobs'`).

- [ ] **Step 3: 구현**

`CmigMainWindow.__init__`의 job dict 정의부에 다음을 추가한다:
```python
        self._import_jobs: dict[str, list[Path]] = {}
        self._pending_imports: list[str] = []
```

Task 6의 빈 메서드 `add_model_paths`, `_add_models_dialog`, `_add_models_folder_dialog`, `_add_medium_dialog`를 다음으로 바꾼다:
```python
    def add_model_paths(self, paths: list[Path], *, recursive: bool = True) -> str:
        from cmig.io import project as proj

        project = self.session.project
        if project is None:
            self.statusBar().showMessage("Open or create a project before adding models.", 8000)
            return ""
        files, skipped = proj.supported_model_paths([Path(p) for p in paths], recursive=recursive)
        if not files:
            self.statusBar().showMessage(
                f"No SBML, JSON or MAT model files found ({skipped} skipped).", 8000
            )
            return ""
        working = proj.Project(project.root, project.name, project.created,
                               list(project.models), list(project.media),
                               dict(project.analysis_settings))

        def _job(ctx: Any) -> dict[str, Any]:
            added: list[Any] = []
            failed: list[tuple[str, str]] = []
            duplicates: list[tuple[str, str]] = []
            total = len(files)
            for index, path in enumerate(files):
                if ctx.cancelled:
                    return {"added": added, "failed": failed, "duplicates": duplicates,
                            "skipped": skipped, "cancelled_remaining": total - index}
                ctx.report_progress(index, total)
                try:
                    added.append(proj.add_model_file(working, path, check=proj.check_model_file))
                except proj.DuplicateModelError as exc:
                    duplicates.append((path.name, exc.existing_id))
                except proj.ProjectError as exc:
                    failed.append((path.name, str(exc)))
            ctx.report_progress(total, total)
            return {"added": added, "failed": failed, "duplicates": duplicates,
                    "skipped": skipped, "cancelled_remaining": 0}

        job_id = self.submit_job("import_models", _job)
        self._import_jobs[job_id] = files
        self._pending_imports.extend(path.name for path in files)
        self._job_commands = getattr(self, "_job_commands", {})
        self._job_commands[job_id] = f"Add {len(files)} model file(s) to {project.name}"
        self.activity.setVisible(True)
        self.toggle_activity_action.setText("Hide Activity")
        self.refresh_workspace()
        return job_id

    def _finish_import(self, job_id: str, result: dict[str, Any] | None, status: str) -> None:
        files = self._import_jobs.pop(job_id, [])
        names = {path.name for path in files}
        self._pending_imports = [n for n in self._pending_imports if n not in names]
        if result is None:
            self.statusBar().showMessage(f"Model import {status}.", 8000)
            self.refresh_workspace()
            return
        self.session.add_entries(list(result["added"]))
        n_failed = sum(1 for e in result["added"] if e.status == "failed") + len(result["failed"])
        parts = [f"{len(result['added'])} added"]
        if result["duplicates"]:
            parts.append(f"{len(result['duplicates'])} duplicate")
        if n_failed:
            parts.append(f"{n_failed} failed")
        if result["skipped"]:
            parts.append(f"{result['skipped']} skipped")
        if result["cancelled_remaining"]:
            parts.append(f"cancelled with {result['cancelled_remaining']} not imported")
        self.statusBar().showMessage("Models: " + ", ".join(parts), 15000)
        details = [f"{name}: {reason}" for name, reason in result["failed"]]
        details += [f"{name}: already in the project as {eid}" for name, eid in result["duplicates"]]
        self.activity.set_job_detail("\n".join(details), self._job_commands.get(job_id, ""))
        self.refresh_workspace()

    def _add_models_dialog(self) -> None:
        dialog = QFileDialog(self, "Add Models")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept, "Add")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Models", "",
            "Models (*.xml *.sbml *.xml.gz *.sbml.gz *.json *.mat)",
        )
        if paths:
            self.add_model_paths([Path(p) for p in paths])

    def _add_models_folder_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add Models from Folder")
        if path:
            include = QMessageBox.question(
                self, "Add Models from Folder", "Include subfolders?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes
            self.add_model_paths([Path(path)], recursive=include)

    def _add_medium_dialog(self) -> None:
        from cmig.io import project as proj

        project = self.session.project
        if project is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Medium", "", "Media (*.csv *.json)")
        errors: list[str] = []
        for path in paths:
            try:
                self.session.add_medium(proj.add_medium_file(project, Path(path)))
            except proj.ProjectError as exc:
                errors.append(f"{Path(path).name}: {exc}")
        if errors:
            self.statusBar().showMessage("; ".join(errors), 15000)
```
`_add_models_dialog`의 앞 세 줄(`dialog = QFileDialog(...)`부터 `setLabelText`까지)은 쓰지 않으므로 지운다. 정적 `getOpenFileNames`를 쓴다. 대신 "Add" 버튼 문구는 `options=QFileDialog.Option(0)`에서 지정할 수 없으므로 macOS 기본 "Open"을 그대로 둔다.

`_poll_completed_jobs`의 맨 앞에 import job 처리를 추가한다:
```python
        for jid in list(self._import_jobs):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._finish_import(jid, job.result, "done")
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._finish_import(jid, None, job.status.value)
```
`import_model_file` 메서드와 이를 쓰던 `ModelManagerPanel` 연결을 지운다. `model_manager` 화면은 프로젝트 모델 개요로 쓴다. `refresh_workspace` 끝에 다음을 넣어 개요 표를 채운다:
```python
        self.model_manager.show_project_models([] if project is None else project.models)
```
`cmig/gui/editors.py`의 `ModelManagerPanel`에 메서드를 추가한다:
```python
    def show_project_models(self, models: list[Any]) -> None:
        """Overview of the project's models (id, status, size)."""
        self.summary_label.setText(f"{len(models)} models in this project")
        self.exchange_table.setColumnCount(4)
        self.exchange_table.setHorizontalHeaderLabels(["Model", "Check", "Reactions", "File"])
        self.exchange_table.setRowCount(len(models))
        for row, entry in enumerate(models):
            values = [entry.id, entry.status if entry.integrity == "ok" else entry.integrity,
                      "—" if entry.n_reactions is None else str(entry.n_reactions), entry.file]
            for col, value in enumerate(values):
                self.exchange_table.setItem(row, col, read_only_item(value))
        self.biomass_label.setText("Select a model in the sidebar for its details.")
```

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_import.py tests/test_workspace_shell.py tests/test_app_shell.py ; echo rc=$?` 그리고 `uv run --no-sync mypy cmig && uv run --no-sync ruff check .`
Expected: 실패 0개, mypy·ruff 오류 없음.

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/app.py cmig/gui/editors.py tests/test_workspace_import.py tests/
git commit -m "feat(gui): add many models and media to a project in the background

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 8: AGORA2에서 모델 받기 (`cmig/gui/agora2_dialog.py`)

**Files:**
- Create: `cmig/gui/agora2_dialog.py`
- Modify: `cmig/gui/app.py`(`_agora2_dialog`)
- Test: `tests/test_workspace_agora2.py`

**Interfaces:**
- Consumes: CLI `agora2-list --format json --out <dir>`(카탈로그 JSON을 stdout으로 쓴다. 정확한 출력 구조는 Step 1 전에 `uv run --no-sync cmig agora2-list --genus Roseburia --format json`으로 확인하고, 아래 `_parse_catalogue`를 그 구조에 맞춘다), `agora2-fetch --strain <ids> --out <dir> --format json --yes`, Task 7의 `add_model_paths`
- Produces:
  - `class Agora2Dialog(QDialog)`:
    - `__init__(list_fn: Callable[[str], list[str]])`. `list_fn(query)`가 균주 id 목록을 돌려준다.
    - 속성: `search_input`, `results`(QListWidget, 여러 개 선택), `add_btn`
    - 메서드: `selected_strains() -> list[str]`
  - `CmigMainWindow._agora2_list(query: str) -> list[str]`: CLI `agora2-list`를 같은 프로세스에서 실행하고 stdout JSON을 해석한다.
  - `CmigMainWindow._agora2_fetch(strains: list[str]) -> str`(job id). 받은 파일은 `models/agora2/`에 두고 끝나면 `add_model_paths`로 등록한다.

- [ ] **Step 1: CLI 출력 형식 확인**

Run: `uv run --no-sync cmig agora2-list --genus Roseburia --limit 3 --format json | head -40`
Expected: JSON. 균주 id 목록이 들어 있는 키 이름(예: `strains` 또는 객체 배열의 `id`)을 확인해 Step 3의 `_parse_catalogue`에 반영한다.
네트워크가 없거나 카탈로그 캐시가 없으면 테스트는 monkeypatch만 쓰므로 진행에 지장이 없다. 실제 형식은 `cmig/cli/main.py`의 `_cmd_agora2_list` 구현에서 읽어 확인한다.

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/test_workspace_agora2.py`:
```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.agora2_dialog import Agora2Dialog  # noqa: E402
from cmig.gui.app import build_main_window  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


def test_dialog_searches_and_returns_selection() -> None:
    queries: list[str] = []

    def list_fn(query: str) -> list[str]:
        queries.append(query)
        return ["Roseburia_hominis_A2_183", "Roseburia_intestinalis_L1_82"]

    dialog = Agora2Dialog(list_fn)
    dialog.search_input.setText("Roseburia")
    dialog.search_btn.click()
    assert queries == ["Roseburia"]
    assert dialog.results.count() == 2
    assert not dialog.add_btn.isEnabled()
    dialog.results.item(1).setSelected(True)
    assert dialog.add_btn.isEnabled()
    assert dialog.selected_strains() == ["Roseburia_intestinalis_L1_82"]


def test_fetch_uses_cli_into_project_agora2_folder(tmp_path: Path, monkeypatch) -> None:
    make_project(tmp_path / "p", [])
    w = build_main_window()
    w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    def fake_main(argv: list[str]) -> int:
        calls.append(argv)
        out = Path(argv[argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "Roseburia_hominis_A2_183.json").write_text('{"id": "x", "reactions": []}')
        return 0

    monkeypatch.setattr("cmig.cli.main.main", fake_main)
    added: list[list[Path]] = []
    monkeypatch.setattr(w, "add_model_paths", lambda paths, **k: added.append(paths) or "job")
    job = w._agora2_fetch(["Roseburia_hominis_A2_183"])
    w.runner.result(job, timeout=10)
    w._poll_completed_jobs()
    argv = calls[0]
    assert argv[:1] == ["agora2-fetch"]
    assert argv[argv.index("--strain") + 1] == "Roseburia_hominis_A2_183"
    assert Path(argv[argv.index("--out") + 1]) == w.session.project.models_dir / "agora2"
    assert "--yes" in argv and argv[argv.index("--format") + 1] == "json"
    assert added and added[0][0].parent == w.session.project.models_dir / "agora2"
    w.close_project()
```

- [ ] **Step 3: 구현**

`cmig/gui/agora2_dialog.py`:
```python
"""Search the AGORA2 catalogue and choose strains to download into the project."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)


class Agora2Dialog(QDialog):
    def __init__(self, list_fn: Callable[[str], list[str]]) -> None:
        super().__init__()
        self.setWindowTitle("Add Models from AGORA2")
        self._list_fn = list_fn
        self.search_input = QLineEdit("")
        self.search_input.setPlaceholderText("Genus or strain, e.g. Roseburia")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._search)
        self.search_input.returnPressed.connect(self._search)
        self.status = QLabel("Downloads come from vmh.life (AGORA2 v2.01) and are converted to "
                             "BiGG-style ids.")
        self.status.setWordWrap(True)
        self.results = QListWidget()
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results.itemSelectionChanged.connect(self._update_buttons)
        self.add_btn = QPushButton("Add to Project")
        self.add_btn.setDefault(True)
        self.add_btn.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        top = QHBoxLayout()
        top.addWidget(self.search_input)
        top.addWidget(self.search_btn)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(cancel)
        bottom.addWidget(self.add_btn)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.status)
        layout.addWidget(self.results)
        layout.addLayout(bottom)
        self._update_buttons()

    def _search(self) -> None:
        query = self.search_input.text().strip()
        if not query:
            return
        try:
            strains = self._list_fn(query)
        except Exception as exc:  # noqa: BLE001 - shown to the user, never raised
            self.status.setText(f"Catalogue lookup failed: {exc}")
            return
        self.results.clear()
        self.results.addItems(strains)
        self.status.setText(f"{len(strains)} strain(s) match {query!r}.")
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.add_btn.setEnabled(bool(self.results.selectedItems()))

    def selected_strains(self) -> list[str]:
        return [item.text() for item in self.results.selectedItems()]
```

`CmigMainWindow`에서 Task 6의 빈 `_agora2_dialog`를 바꾸고, 메서드 세 개와 `_agora2_jobs` 처리를 추가한다:
```python
    def _agora2_list(self, query: str) -> list[str]:
        import contextlib
        import io

        from cmig.cli.main import main

        buffer = io.StringIO()
        args = ["agora2-list", "--format", "json", "--limit", "500"]
        args += ["--genus", query] if query[:1].isupper() and "_" not in query else ["--match", query]
        with contextlib.redirect_stdout(buffer):
            rc = main(args)
        if rc != 0:
            raise RuntimeError(f"agora2-list exited {rc}")
        return _parse_catalogue(buffer.getvalue())

    def _agora2_dialog(self) -> None:
        from cmig.gui.agora2_dialog import Agora2Dialog

        if self.session.project is None:
            return
        dialog = Agora2Dialog(self._agora2_list)
        if dialog.exec() and dialog.selected_strains():
            self._agora2_fetch(dialog.selected_strains())

    def _agora2_fetch(self, strains: list[str]) -> str:
        from cmig.cli.main import main

        project = self.session.require()
        out_dir = project.models_dir / "agora2"
        argv = ["agora2-fetch", "--strain", ",".join(strains), "--out", str(out_dir),
                "--format", "json", "--yes"]

        def _job(ctx: Any) -> dict[str, Any]:
            ctx.report_progress(0, 1)
            rc = main(argv)
            if rc != 0:
                raise RuntimeError(f"agora2-fetch exited {rc}")
            return {"files": [str(out_dir / f"{s}.json") for s in strains]}

        job_id = self.submit_job("agora2_fetch", _job)
        self._agora2_jobs[job_id] = out_dir
        self._job_commands = getattr(self, "_job_commands", {})
        from cmig.gui.activity import command_line

        self._job_commands[job_id] = command_line(argv)
        self.activity.setVisible(True)
        return job_id
```
모듈 수준(클래스 밖)에 `_parse_catalogue`를 추가한다. Step 1에서 확인한 키에 맞춘다. 문자열 목록과 `{"id": ...}` 객체 목록 둘 다 받는다:
```python
def _parse_catalogue(text: str) -> list[str]:
    payload = json.loads(text)
    items = payload.get("strains", payload.get("selected", [])) if isinstance(payload, dict) else payload
    out: list[str] = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            out.append(item["id"])
    return out
```
`__init__`의 job dict에 `self._agora2_jobs: dict[str, Path] = {}`를 추가한다. `_poll_completed_jobs` 맨 앞(import job 처리 다음)에 다음을 넣는다:
```python
        for jid, out_dir in list(self._agora2_jobs.items()):
            job = self.runner.poll(jid)
            if job.status is JobStatus.DONE and isinstance(job.result, dict):
                self._agora2_jobs.pop(jid)
                files = [Path(f) for f in job.result["files"] if Path(f).exists()]
                if files:
                    self.add_model_paths(files)
            elif job.status in (JobStatus.FAILED, JobStatus.CANCELLED):
                self._agora2_jobs.pop(jid)
                self.statusBar().showMessage(f"AGORA2 download {job.status.value}: {job.error}",
                                             15000)
```
`add_model_paths`는 파일을 `models/` 아래 이름으로 한 번 더 복사한다. `models/agora2/`의 원본 다운로드는 남는다. 출처 기록은 `source_path`가 `models/agora2/<id>.json`을 가리켜 남는다. 복사본이 생기는 것은 1단계에서 받아들인다.

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_agora2.py tests/test_agora2.py ; echo rc=$?` 그리고 `uv run --no-sync mypy cmig && uv run --no-sync ruff check .`
Expected: 실패 0개.

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/agora2_dialog.py cmig/gui/app.py tests/test_workspace_agora2.py
git commit -m "feat(gui): add AGORA2 strains to a project

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 9: 모델·배지 선택기와 분석 연결, 출력은 프로젝트 `runs/`

**Files:**
- Create: `cmig/gui/pickers.py`
- Modify:
  - `cmig/gui/builder.py`: `SearchView`에서 `model_dir_input`, `browse_pool_btn`, `model_source_combo`, `taxonomy_input`, `recursive_check`, `medium_input`, `browse_medium_btn`, `output_dir_input`, `browse_output_btn`, `output_dir_label`, `output_dir_note`를 제거하고 `model_picker`, `medium_picker`를 추가한다. `CommunityBuilderView`의 `model_dir_input`, `browse_model_dir_btn`도 같은 방식으로 바꾼다.
  - `cmig/gui/host_view.py`: `host_path_input`, `model_dir_input`, `host_medium_input`, `microbe_medium_input`, `out_dir_input`, 각 Browse 버튼, `recursive_check`
  - `cmig/gui/views.py`: `SweepView`의 `taxonomy_input`, `model_dir_input`, `DfbaSpatialView`의 `model_path_input`, `out_dir_input`
  - `cmig/gui/editors.py`: `MediumEditor`의 `taxonomy_input`, `model_path_input`
  - `cmig/gui/app.py`: 각 `run_*`의 입력·출력 결정, `_browse_*` 중 지운 입력칸을 쓰던 메서드 제거, `_refresh_pickers`, `_search_with_models`, `_prepare_run`, `_medium_arg`
- Test: `tests/test_workspace_analysis_inputs.py`, 기존 GUI 테스트 수정

**Interfaces:**
- Consumes:
  - `selectable_models`, `new_run_dir`, `write_run_taxonomy`, `medium_path`, `ProjectError`(Task 2)
  - `installed_medium_preset_path`(Task 6)
  - `ProjectSession.settings`·`store_settings`(Task 3)
- Produces:
  - `class ModelPicker(QToolButton)`:
    - `__init__(label: str = "Models", single: bool = False)`
    - 메서드: `set_choices(entries: list[tuple[str, bool, str]])`(id, selectable, 이유), `selected_ids() -> list[str]`, `set_selected(ids: list[str]) -> None`
    - 신호: `selection_changed`
    - 단일 선택 모드는 하나만 고른다. 여러 개 모드에서 고를 수 없는 항목은 흐리게 보이고 tooltip에 이유를 단다.
  - `class MediumPicker(QComboBox)`: `set_choices(presets: list[str], user: list[tuple[str, bool]])`, `current_ref() -> str`(`""` = model default, `preset:<name>`, `medium:<id>`), `set_ref(ref: str)`
  - `CmigMainWindow._prepare_run(kind: str, model_ids: list[str], *, abundances: dict[str, float] | None = None) -> tuple[Path, Path | None]`: (run_dir, taxonomy 경로. `model_ids`가 비면 None). 프로젝트가 없거나 모델 오류면 `ProjectError`를 낸다.
  - `CmigMainWindow._medium_arg(ref: str) -> str | None`
  - `CmigMainWindow._model_file(model_id: str) -> Path`
  - 분석별 저장 key(`analysis_settings`): `search`, `gene_ko`, `growth`, `host`, `dynamics`, `community`, `medium`, `sweep`. 값은 `{"models": [...], "medium": ref, "host": id}`이다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_analysis_inputs.py`. 각 분석 run 메서드를 실제 CLI 대신 기록용 `main`으로 실행한다. 기존 `tests/test_gui_audit_regressions.py`의 recorder 방식과 같다:
```python
from __future__ import annotations

import csv
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    make_project(tmp_path / "p", ["a", "b", "c", "host"], statuses={"c": "failed"})
    w = build_main_window()
    w.open_project(tmp_path / "p")
    calls: list[list[str]] = []

    def recorder(argv: list[str]) -> int:
        calls.append(list(argv))
        return 2  # stop after argv is recorded; the failure path is exercised elsewhere

    monkeypatch.setattr("cmig.cli.main.main", recorder)
    yield w, calls
    w.close_project()


def _wait_calls(w, calls, n: int = 1) -> list[str]:
    deadline = time.time() + 10
    while len(calls) < n and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    w._poll_completed_jobs()
    assert len(calls) >= n
    return calls[-1]


def _taxonomy_ids(argv: list[str]) -> list[str]:
    path = Path(argv[argv.index("--taxonomy") + 1])
    return [row["id"] for row in csv.DictReader(path.open())]


def test_search_uses_selected_models_and_project_runs(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.show_analysis("search")
    assert w.search_view.model_picker.selected_ids() == ["a", "b", "host"], \
        "default = every selectable model; failed c is excluded"
    w.search_view.model_picker.set_selected(["a", "b"])
    w.search_view.medium_picker.set_ref("preset:western")
    w.run_search_fixture()
    argv = _wait_calls(w, calls)
    assert argv[0] == "search" and "--model-dir" not in argv
    assert _taxonomy_ids(argv) == ["a", "b"]
    out = Path(argv[argv.index("--out") + 1])
    assert out.parent == project.runs_dir and out.name.startswith("search-")
    assert Path(argv[argv.index("--medium") + 1]).name == "western.csv"
    assert (project.inputs_dir / f"{out.name}-taxonomy.csv").exists()
    assert w.session.settings("search")["models"] == ["a", "b"]


def test_no_models_selected_is_refused_before_running(setup) -> None:
    w, calls = setup
    w.show_analysis("search")
    w.search_view.model_picker.set_selected([])
    assert w.run_search_fixture() == ""
    assert "Select at least one model" in w.search_view.status.text()
    assert calls == []


def test_gene_ko_strain_ratio_use_taxonomy(setup) -> None:
    w, calls = setup
    w.search_view.model_picker.set_selected(["a", "b"])
    w.search_view.ko_members_input.setText("a,b")
    w.run_gene_ko_search()
    argv = _wait_calls(w, calls, 1)
    assert argv[0] == "gene-ko-search" and _taxonomy_ids(argv) == ["a", "b"]
    assert Path(argv[argv.index("--out") + 1]).name.startswith("gene-ko-")
    w.run_strain_growth_report()
    argv = _wait_calls(w, calls, 2)
    assert argv[0] == "strain-growth" and "--taxonomy" in argv


def test_host_uses_host_and_microbe_pickers(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.show_analysis("host")
    w.host_view.host_picker.set_selected(["host"])
    w.host_view.model_picker.set_selected(["a", "b"])
    w.host_view.biomass_basis_kind_combo.setCurrentIndex(1)
    w.host_view.biomass_basis_source_input.setText("lab record 12")
    w.host_view.microbial_biomass_spin.setValue(0.5)
    w.host_view.host_biomass_spin.setValue(10.0)
    w.run_host_microbe_bigg()
    argv = _wait_calls(w, calls)
    assert Path(argv[argv.index("--host") + 1]) == project.root / project.model("host").file
    assert _taxonomy_ids(argv) == ["a", "b"]
    assert Path(argv[argv.index("--out") + 1]).parent == project.runs_dir


def test_host_cannot_be_a_microbe_too(setup) -> None:
    w, calls = setup
    w.host_view.host_picker.set_selected(["host"])
    w.host_view.model_picker.set_selected(["a", "host"])
    assert w.run_host_microbe_bigg() == ""
    assert "also selected as a microbe" in w.host_view.run_status.text()


def test_dfba_uses_single_model(setup) -> None:
    w, calls = setup
    project = w.session.project
    w.dynamics_view.model_picker.set_selected(["a"])
    w.run_dfba()
    argv = _wait_calls(w, calls)
    assert Path(argv[argv.index("--model") + 1]) == project.root / project.model("a").file
    assert Path(argv[argv.index("--out") + 1]).name.startswith("dfba-")


def test_community_writes_abundances(setup) -> None:
    w, calls = setup
    w.community_builder.model_picker.set_selected(["a", "b"])
    w.community_builder.add_member("a", 0.25)
    w.community_builder.assume_bigg_check.setChecked(True)
    w.run_community_solve()
    argv = _wait_calls(w, calls)
    path = Path(argv[argv.index("--taxonomy") + 1])
    rows = {r["id"]: float(r["abundance"]) for r in csv.DictReader(path.open())}
    assert rows == {"a": 0.25, "b": 1.0}


def test_selection_change_invalidates_displayed_search(setup) -> None:
    w, _calls = setup
    w.search_view.table.setRowCount(1)
    w.search_view.current_run_dir = Path("/tmp/x")
    w.search_view._displayed_kind = "search"
    w.search_view._displayed_request = w.search_view.request_fields("search")
    w.search_view.model_picker.set_selected(["a"])
    assert w.search_view.table.rowCount() == 0


def test_picker_choices_follow_project_changes(setup) -> None:
    w, _calls = setup
    w.session.remove_models(["b"])
    assert "b" not in w.search_view.model_picker.selected_ids()
    w.session.undo_stack.undo()
    labels = [a.text() for a in w.search_view.model_picker.menu().actions() if a.isCheckable()]
    assert "b" in labels


def test_search_with_selected_from_sidebar(setup) -> None:
    w, _calls = setup
    w._search_with_models(["b", "host"])
    assert w.pages.currentWidget() is w.search_view
    assert w.search_view.model_picker.selected_ids() == ["b", "host"]
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_analysis_inputs.py`
Expected: FAIL (`AttributeError: 'SearchView' object has no attribute 'model_picker'`).

- [ ] **Step 3: 선택기 구현**

`cmig/gui/pickers.py`:
```python
"""Project model and medium pickers used by every analysis page."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QComboBox, QMenu, QToolButton


class ModelPicker(QToolButton):
    selection_changed = Signal()

    def __init__(self, label: str = "Models", single: bool = False) -> None:
        super().__init__()
        self._label = label
        self._single = single
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setMenu(QMenu(self))
        self._actions: dict[str, QAction] = {}
        self._group = QActionGroup(self)
        self._group.setExclusive(single)
        self._update_text()

    def set_choices(self, entries: list[tuple[str, bool, str]]) -> None:
        previous = set(self.selected_ids())
        first = not self._actions
        menu = self.menu()
        menu.clear()
        self._actions.clear()
        self._group = QActionGroup(self)
        self._group.setExclusive(self._single)
        if not self._single:
            menu.addAction("Select All", lambda: self.set_selected(
                [k for k, a in self._actions.items() if a.isEnabled()]))
            menu.addAction("Select None", lambda: self.set_selected([]))
            menu.addSeparator()
        for model_id, selectable, reason in entries:
            action = QAction(model_id, menu)
            action.setCheckable(True)
            action.setEnabled(selectable)
            if not selectable:
                action.setToolTip(reason)
            keep = model_id in previous or (first and not self._single)
            action.setChecked(selectable and keep)
            action.toggled.connect(self._changed)
            self._group.addAction(action)
            menu.addAction(action)
            self._actions[model_id] = action
        self._update_text()

    def selected_ids(self) -> list[str]:
        return [k for k, a in self._actions.items() if a.isChecked() and a.isEnabled()]

    def set_selected(self, ids: list[str]) -> None:
        wanted = set(ids)
        for model_id, action in self._actions.items():
            action.blockSignals(True)
            action.setChecked(model_id in wanted and action.isEnabled())
            action.blockSignals(False)
        self._changed()

    def _changed(self, *_args: object) -> None:
        self._update_text()
        self.selection_changed.emit()

    def _update_text(self) -> None:
        chosen = self.selected_ids()
        if self._single:
            self.setText(f"{self._label}: {chosen[0] if chosen else 'choose…'}")
        else:
            self.setText(f"{self._label}: {len(chosen)} selected")


class MediumPicker(QComboBox):
    def __init__(self) -> None:
        super().__init__()
        self.addItem("Model default (no medium file)", "")

    def set_choices(self, presets: list[str], user: list[tuple[str, bool]]) -> None:
        current = self.current_ref()
        self.blockSignals(True)
        self.clear()
        self.addItem("Model default (no medium file)", "")
        for name in presets:
            self.addItem(f"Preset · {name}", f"preset:{name}")
        for medium_id, ok in user:
            self.addItem(f"Project · {medium_id}" + ("" if ok else " (changed)"),
                         f"medium:{medium_id}")
        self.blockSignals(False)
        self.set_ref(current)

    def current_ref(self) -> str:
        return str(self.currentData() or "")

    def set_ref(self, ref: str) -> None:
        index = self.findData(ref)
        self.setCurrentIndex(index if index >= 0 else 0)
```

- [ ] **Step 4: 분석 화면 입력 교체**

각 화면에서 지울 입력칸을 지우고, 같은 줄 자리에 선택기를 넣는다. 화면별 코드:

`SearchView.__init__`(builder.py). `pool_row`(Model Folder 줄) 전체를 다음으로 바꾼다:
```python
        from cmig.gui.pickers import MediumPicker, ModelPicker

        pool_row = QHBoxLayout()
        self.model_picker = ModelPicker("Models")
        self.medium_picker = MediumPicker()
        pool_row.addWidget(self.model_picker)
        pool_row.addWidget(QLabel("Medium"))
        pool_row.addWidget(self.medium_picker, 1)
```
`settings` 줄에서 `("Medium", self.medium_input)`과 `browse_medium_btn`을 지운다. 배지 모드 요약 줄(`medium_mode_summary`)과 `medium_mode_text(...)` 호출의 첫 인자는 `self.medium_picker.current_ref()`로 바꾼다. 고급 설정의 model source 줄(`model_source_combo`, `taxonomy_input`, `recursive_check`)과 출력 폴더 줄(`output_dir_*`, `browse_output_btn`)을 지운다. `REQUEST_FIELDS["search"]`·`["gene_ko"]`·`["strain_growth"]`·`["abundance_impact"]`에서 `"pool"`, `"model_source"`, `"taxonomy"`, `"recursive"`를 `"models"`로, `"medium"`은 그대로 둔다. `request_fields`의 해당 값은 다음과 같다:
```python
            "models": ",".join(self.model_picker.selected_ids()),
            "medium": self.medium_picker.current_ref(),
```
무효화 연결에 `self.model_picker.selection_changed.connect(self.invalidate_results)`와 `self.medium_picker.currentIndexChanged.connect(self.invalidate_results)`를 추가하고, 지운 입력칸의 연결 줄은 지운다.

`CommunityBuilderView.__init__`: `pool_row`를 다음으로 바꾼다:
```python
        from cmig.gui.pickers import ModelPicker

        pool_row = QHBoxLayout()
        self.model_picker = ModelPicker("Members")
        pool_row.addWidget(self.model_picker)
        pool_row.addStretch(1)
        pool_row.addWidget(self.run_btn)
```
상태 문구는 `"Pick members, set abundances below (default 1), then Run Community."`로 바꾼다.

`HostImpactView.__init__`(host_view.py): host·microbe·medium·output 다섯 줄을 다음 두 줄로 바꾼다. `request()`의 `"host"`, `"model_dir"`, `"host_medium"`, `"microbe_medium"`, `"out_dir"`, `"recursive"` 키를 `"host_id"`, `"models"`, `"host_medium"`, `"microbe_medium"`(ref 문자열)로 바꾼다:
```python
        from cmig.gui.pickers import MediumPicker, ModelPicker

        self.host_picker = ModelPicker("Host model", single=True)
        self.model_picker = ModelPicker("Microbes")
        self.host_medium_picker = MediumPicker()
        self.microbe_medium_picker = MediumPicker()
        models_row = QHBoxLayout()
        models_row.addWidget(self.host_picker)
        models_row.addWidget(self.model_picker)
        models_row.addStretch(1)
        media_row = QHBoxLayout()
        media_row.addWidget(QLabel("Host medium"))
        media_row.addWidget(self.host_medium_picker, 1)
        media_row.addWidget(QLabel("Microbe medium"))
        media_row.addWidget(self.microbe_medium_picker, 1)
```
```python
            "host_id": (self.host_picker.selected_ids() or [""])[0],
            "models": self.model_picker.selected_ids(),
            "host_medium": self.host_medium_picker.current_ref(),
            "microbe_medium": self.microbe_medium_picker.current_ref(),
```
체크박스 줄(Recursive, Keep host uptake, Currency, Allow unknown)은 `recursive_check`를 지우고 나머지 세 개를 남긴다. 1280 폭에서 잘리는 Edges 줄(`Cross-feeding`, `+ secretion`, `− uptake`, `Aggregate`)은 두 줄 `QGridLayout`(2열)로 바꾼다.

`DfbaSpatialView.__init__`(views.py): `model_row`의 `model_path_input`, `browse_model_btn`, `out_dir_input`, `browse_out_btn`을 `self.model_picker = ModelPicker("Model", single=True)` 하나로 바꾼다. `dfba_request()`의 `"model"`은 `(self.model_picker.selected_ids() or [""])[0]`로, `"out_dir"`과 `spatial_request()`의 `"out_dir"` 키는 지운다. 잘리는 dFBA 입력 줄(Initial, T end, dt, Biomass, Close)과 Spatial 줄은 각각 두 줄 `QGridLayout`으로 나눈다.

`SweepView.__init__`(views.py): `taxonomy_input`·`model_dir_input`과 각 Browse를 `self.model_picker = ModelPicker("Models")`로 바꾸고, `request()`의 `"taxonomy"`, `"model_dir"`를 `"models": self.model_picker.selected_ids()`로 바꾼다. `mediums_input`(여러 배지 변형)은 그대로 둔다.

`MediumEditor.__init__`(editors.py): taxonomy 줄을 `self.model_picker = ModelPicker("Models")`로, model 줄의 `model_path_input`과 Browse를 `self.single_model_picker = ModelPicker("Model", single=True)`로 바꾼다.

- [ ] **Step 5: 실행부 연결 (`app.py`)**

공용 helper를 추가한다:
```python
    def _prepare_run(
        self, kind: str, model_ids: list[str], *, abundances: dict[str, float] | None = None
    ) -> tuple[Path, Path | None]:
        from cmig.io import project as proj

        project = self.session.require()
        run_dir = proj.new_run_dir(project, kind)
        taxonomy = (
            proj.write_run_taxonomy(project, run_dir, model_ids, abundances)
            if model_ids else None
        )
        return run_dir.resolve(), taxonomy

    def _medium_arg(self, ref: str) -> str | None:
        from cmig.gui.editors import installed_medium_preset_path
        from cmig.io.project import medium_path

        if not ref:
            return None
        kind, _, name = ref.partition(":")
        if kind == "preset":
            return str(installed_medium_preset_path(name))
        return str(medium_path(self.session.require(), self.session.require().medium(name)))

    def _model_file(self, model_id: str) -> Path:
        from cmig.io.project import model_path

        project = self.session.require()
        return model_path(project, project.model(model_id)).resolve()

    def _refresh_pickers(self) -> None:
        from cmig.gui.editors import installed_medium_presets

        project = self.session.project
        models = [] if project is None else project.models
        choices = [
            (m.id, m.status in ("ok", "warning") and m.integrity == "ok",
             m.error or f"{m.status}/{m.integrity}")
            for m in models
        ]
        pickers = {
            "search": self.search_view.model_picker,
            "community": self.community_builder.model_picker,
            "host": self.host_view.model_picker,
            "host_model": self.host_view.host_picker,
            "dynamics": self.dynamics_view.model_picker,
            "sweep": self.sweep_view.model_picker,
            "medium": self.medium_editor.model_picker,
            "medium_single": self.medium_editor.single_model_picker,
        }
        for key, picker in pickers.items():
            picker.set_choices(choices)
            saved = self.session.settings(key).get("models")
            if isinstance(saved, list):
                picker.set_selected([str(x) for x in saved])
        presets = installed_medium_presets()
        user = [] if project is None else [(m.id, m.integrity == "ok") for m in project.media]
        for medium_picker in (self.search_view.medium_picker, self.host_view.host_medium_picker,
                              self.host_view.microbe_medium_picker):
            medium_picker.set_choices(presets, user)

    def _remember(self, key: str, picker: Any) -> None:
        if self.session.project is not None:
            values = self.session.settings(key)
            values["models"] = picker.selected_ids()
            self.session.store_settings(key, values)

    def _search_with_models(self, keys: list[str]) -> None:
        self.search_view.model_picker.set_selected(keys)
        self.show_analysis("search")
```

각 `run_*`에서 출력 폴더 결정과 모델 입력을 바꾼다. 공통 규칙:
- `tempfile.mkdtemp(...)`, `_search_temp_root()`, `_new_search_run_dir(...)`, `out_dir_text` 분기를 지우고 `self._prepare_run(<kind>, <ids>)`를 쓴다. `ProjectError`는 해당 화면의 status label에 보이고 `""`를 돌려준다.
- `"--model-dir", model_dir`는 `"--taxonomy", str(taxonomy)`로 바꾼다.
- 배지는 `self._medium_arg(ref)`로 경로를 얻는다.
- 선택된 모델이 없으면 실행 전에 "Select at least one model." 문구로 거부한다.

`run_search_fixture` 앞부분(현재 `output_parent_text = ...`부터 `model_dir = ...`까지)을 다음으로 바꾼다:
```python
        from cmig.io.project import ProjectError

        model_ids = self.search_view.model_picker.selected_ids()
        if not model_ids:
            self.search_view.status.setText("Select at least one model.")
            return ""
        try:
            out_dir, taxonomy = self._prepare_run("search", model_ids)
            medium_file = self._medium_arg(self.search_view.medium_picker.current_ref())
        except (ProjectError, ValueError) as exc:
            self.search_view.status.setText(str(exc))
            return ""
        requested = dict(requested)
        requested["model_source"] = "taxonomy"
        requested["taxonomy"] = str(taxonomy)
        requested["medium"] = medium_file or ""
        self._remember("search", self.search_view.model_picker)
        model_dir = None
```
`_search_argv`와 기존 checkpoint 검사는 그대로 쓴다(`requested["taxonomy"]` 경로를 사용). checkpoint가 out 안인지 검사는 `out_dir` 기준으로 그대로 둔다.

`run_gene_ko_search`·`run_strain_growth_report`·`run_abundance_impact`: `model_dir = requested["pool"]` 줄과 `if not model_dir ...` 검사를 다음으로 바꾼다:
```python
        model_ids = self.search_view.model_picker.selected_ids()
        if not model_ids:
            self.search_view.status.setText("Select at least one model.")
            return ""
        try:
            out_dir, taxonomy = self._prepare_run("gene-ko", model_ids)   # strain-growth / abundance-impact
            medium_file = self._medium_arg(self.search_view.medium_picker.current_ref())
        except (ProjectError, ValueError) as exc:
            self.search_view.status.setText(str(exc))
            return ""
```
argv의 `"--model-dir", model_dir`를 `"--taxonomy", str(taxonomy)`로 바꾸고, `if requested["medium"]:` 블록을 `if medium_file: argv.extend(["--medium", medium_file, "--exact-medium"])`로 바꾼다. kind는 각각 `"gene-ko"`, `"strain-growth"`, `"abundance-impact"`이다.

`run_host_microbe_bigg`·`run_host_search_bigg`:
```python
        request = self.host_view.request()
        if not request["host_id"]:
            self.host_view.run_status.setText("Choose a host model.")
            return ""
        if not request["models"]:
            self.host_view.run_status.setText("Select at least one microbial model.")
            return ""
        if request["host_id"] in request["models"]:
            self.host_view.run_status.setText(
                f"{request['host_id']} is also selected as a microbe; pick it only as the host."
            )
            return ""
        try:
            out_dir, taxonomy = self._prepare_run("host-microbe", request["models"])  # host-search
            host = str(self._model_file(request["host_id"]))
            host_medium = self._medium_arg(request["host_medium"])
            microbe_medium = self._medium_arg(request["microbe_medium"])
        except (ProjectError, ValueError) as exc:
            self.host_view.run_status.setText(str(exc))
            return ""
```
argv에서 `"--model-dir", str(model_dir)`를 `"--taxonomy", str(taxonomy)`로 바꾸고, `--recursive` 추가 줄을 지운다. 기존 host medium·microbe medium 인자 줄은 `host_medium`·`microbe_medium` 변수(값이 있을 때만)로 바꾼다.

`run_dfba`: `model = str(request["model"])`와 출력 분기를 다음으로 바꾼다. `run_spatial_preview`는 `self._prepare_run("spatial", [])`의 run_dir만 쓴다:
```python
        if not request["model"]:
            self.dynamics_view.status.setText("Choose a model.")
            return ""
        try:
            out_dir, _ = self._prepare_run("dfba", [])
            model = str(self._model_file(str(request["model"])))
        except (ProjectError, ValueError) as exc:
            self.dynamics_view.status.setText(str(exc))
            return ""
```

`run_community_solve`: `model_dir` 읽기, `taxonomy_from_model_dir`, run 폴더 안 `taxonomy.csv` 작성을 다음으로 바꾼다:
```python
        model_ids = self.community_builder.model_picker.selected_ids()
        members = self.community_builder.members()
        unknown = sorted(set(members) - set(model_ids))
        if not model_ids:
            self.community_builder.status.setText("Select at least one member model.")
            return ""
        if unknown:
            self.community_builder.status.setText(
                f"abundance rows for unselected models: {unknown}; select them or remove the rows"
            )
            return ""
        try:
            out_dir, tax_path = self._prepare_run("community", model_ids, abundances=members)
        except (ProjectError, ValueError) as exc:
            self.community_builder.status.setText(str(exc))
            return ""
```
argv의 `"--taxonomy", str(tax_path)`는 그대로 쓴다.

`run_sweep`: `taxonomy`/`model_dir` 분기를 `model_ids = request["models"]`와 `self._prepare_run("sweep", model_ids)`로 바꾸고, `taxonomy_path` 대신 돌려받은 taxonomy를 쓴다. `run_sweep_fixture`는 출력만 `self._prepare_run("sweep", [])`로 바꾼다.

`run_medium_growth_check`: `taxonomy_input` 대신 `self.medium_editor.model_picker.selected_ids()`와 `self._prepare_run("medium-growth", ids)`를 쓴다. 편집한 배지는 지금처럼 `out_dir / "medium.json"`에 쓰지 않고 `project.inputs_dir / f"{out_dir.name}-medium.json"`에 `atomic_write_text`로 쓴다(run 폴더에 미리 쓰지 않음).

`run_minimal_medium`: `model_path_input` 대신 `self.medium_editor.single_model_picker.selected_ids()`와 `self._model_file(...)`, `self._prepare_run("minimal-medium", [])`를 쓴다. 배지 파일은 위와 같이 `inputs_dir`에 쓴다.

지운 입력칸을 쓰던 Browse 메서드는 지우고, `_connect_view_actions`의 해당 `clicked.connect` 줄도 지운다. 대상은 `_browse_search_model_dir`, `_browse_search_output_dir`, `_browse_search_medium`, `_browse_sweep_taxonomy`, `_browse_sweep_model_dir`, `_browse_host_model`, `_browse_host_microbe_model_dir`, `_browse_host_medium`, `_browse_microbe_medium`, `_browse_host_microbe_out_dir`, `_browse_community_model_dir`, `_browse_medium_taxonomy`, `_browse_medium_model`이다. `_search_temp_root`, `_output_parent_error`, `_new_search_run_dir`, `_search_run_stamp` 함수도 더 쓰지 않으면 지운다.

각 화면의 picker 선택이 바뀌면 설정을 저장하도록 `_connect_view_actions` 끝에 다음을 넣는다:
```python
        for key, picker in (("search", self.search_view.model_picker),
                            ("community", self.community_builder.model_picker),
                            ("host", self.host_view.model_picker),
                            ("host_model", self.host_view.host_picker),
                            ("dynamics", self.dynamics_view.model_picker),
                            ("sweep", self.sweep_view.model_picker),
                            ("medium", self.medium_editor.model_picker),
                            ("medium_single", self.medium_editor.single_model_picker)):
            picker.selection_changed.connect(lambda k=key, p=picker: self._remember(k, p))
```
명령 기록: 각 `_job` 안에서 argv를 만든 직후 `self._run_commands[str(out_dir)] = command_line(argv)`를 넣는다. 이 기록은 run 상세 패널의 Copy Command가 쓴다. `__init__`에서 `self._run_commands: dict[str, str] = {}`로 시작한다. 같은 값을 `self._job_commands[jid]`에도 넣는다(작업 창).

- [ ] **Step 6: 기존 테스트 옮기기**

`grep -nE "model_dir_input|taxonomy_input|output_dir_input|out_dir_input|host_path_input|model_path_input|medium_input|browse_pool_btn|browse_output_btn|model_source_combo|recursive_check|_search_temp_root|_new_search_run_dir" tests/*.py`로 나온 테스트를 고친다. 각 테스트는 `make_project(tmp_path / "p", [...])`와 `w.open_project(...)`로 시작하고, 아래 표대로 바꾼다.

| 기존 | 새 |
|---|---|
| `search_view.model_dir_input.setText(str(folder))` | `search_view.model_picker.set_selected([...])` |
| `assert "--model-dir" in argv` | `assert "--taxonomy" in argv` |
| `model_dir` 값 비교 | `_taxonomy_ids(argv)` 비교 |
| `search_view.medium_input.setText(path)` | 배지를 `proj.add_medium_file`로 넣고 `medium_picker.set_ref("medium:<id>")` |
| 출력 폴더 테스트(`tests/test_gui_search_output.py` 중 output folder 부분) | "프로젝트 `runs/` 아래에 매번 새 폴더"를 확인하는 테스트로 바꾼다. 출력 폴더 칸 자체의 테스트(빈 칸=임시, 하위 폴더, 홈 폴더)는 기능이 없어졌으므로 지운다 |
| `out_dir_input` 기반 host/dfba 테스트 | 출력이 `project.runs_dir` 아래인지 확인 |

checkpoint 테스트(out 안의 checkpoint 거부, Resume 없이 존재 거부)는 그대로 유지한다. 단, out 경로를 프로젝트 run 폴더 기준으로 계산하도록 바꾼다.

- [ ] **Step 7: 통과 확인**

Run:
```bash
QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_analysis_inputs.py tests/test_workspace_shell.py tests/test_workspace_import.py tests/test_gui_search_parity.py tests/test_gui_search_output.py tests/test_gui_search_inspector.py tests/test_gui_search_cancel.py tests/test_gui_audit_regressions.py tests/test_gui_editors_builder.py tests/test_app_shell.py tests/test_gui_render.py tests/test_gui_views.py tests/test_gui_round5_p2.py tests/test_round9_gui_medium_tools.py tests/test_round7_gui_graph_profile.py tests/test_round8_gui_sweep_overlays.py tests/test_host_view.py tests/test_host_medium_strictness.py ; echo rc=$?
uv run --no-sync mypy cmig && uv run --no-sync ruff check .
```
Expected: 실패 0개, mypy·ruff 오류 없음.

- [ ] **Step 8: 화면 캡처 확인**

Task 6 Step 8의 캡처 스크립트를 다시 돌린다. `03_search`, `03_host`, `03_dynamics`에서 다음을 확인한다:
- 선택기("Models: 12 selected", "Host model: choose…")가 보이는지
- 1280 폭에서 잘리는 입력칸이 없는지

Host의 Edges 줄과 Dynamics의 입력 줄이 두 줄로 정리됐는지도 본다.

- [ ] **Step 9: 커밋**

```bash
git add cmig/gui/ tests/
git commit -m "feat(gui): analyses pick project models and media; runs go to project runs/

Model-folder, taxonomy, medium-path and output-folder fields are replaced by project pickers.
Each run writes runs/_inputs/<run>-taxonomy.csv and passes --taxonomy to the unchanged CLI.

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 10: 취소 표시를 모든 작업에 적용, run 목록 갱신

**Files:**
- Modify: `cmig/gui/app.py`(`_cancel_job_id`, `_poll_completed_jobs`)
- Test: `tests/test_workspace_activity_flow.py`

**Interfaces:**
- Consumes: Task 5 `ActivityPane`, Task 3 `ProjectSession.refresh_runs`, Task 9 `_prepare_run`
- Produces: 작업이 끝날 때마다 `self.session.refresh_runs()` 호출. Cancel을 누르면 그 작업 행에 "cancelling (solver still running)"이 즉시 보이고 끝날 때까지 유지된다(`bridge.cancelling` 사용).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_workspace_activity_flow.py`:
```python
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cmig.gui.app import build_main_window  # noqa: E402
from gui_project_helpers import _deterministic_qt_teardown, make_project  # noqa: E402,F401

APP = QApplication.instance() or QApplication([])


def test_cancel_marks_any_job_pending_until_it_ends(tmp_path: Path) -> None:
    make_project(tmp_path / "p", ["a"])
    w = build_main_window()
    w.open_project(tmp_path / "p")
    gate = threading.Event()
    jid = w.submit_job("strain_growth", lambda ctx: gate.wait(5) and {"ok": True})
    w.jobs_panel.selectRow(0)
    w.activity.cancel_btn.click()
    status = w.jobs_panel.item(0, 2).text()
    assert status == "cancelling (solver still running)"
    w._poll_completed_jobs()
    assert w.jobs_panel.item(0, 2).text() == "cancelling (solver still running)"
    gate.set()
    deadline = time.time() + 5
    while w.runner.poll(jid).status.value in ("pending", "running") and time.time() < deadline:
        APP.processEvents()
        time.sleep(0.02)
    w.bridge.refresh()
    assert w.jobs_panel.item(0, 2).text() in ("cancelled", "done")
    w.close_project()


def test_finished_run_appears_in_runs(tmp_path: Path) -> None:
    project = make_project(tmp_path / "p", ["a"])
    w = build_main_window()
    w.open_project(tmp_path / "p")
    run = project.runs_dir / "search-20261013-120000"
    run.mkdir()
    (run / "search_summary.json").write_text('{"status": "ok", "targets": ["but"]}')
    w._register_run_output(run)
    runs = w.sidebar.topLevelItem(3)
    assert runs.child(0).text(0) == "✓ Search · but · 12:00"
    w.close_project()
```

- [ ] **Step 2: 실패 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_activity_flow.py`
Expected: 첫 테스트가 FAIL(`bridge.refresh()`가 cancel 직후 호출되지 않아 상태 문구가 "running"으로 남음). 또는 Task 6의 `_cancel_job_id` 구현에 따라 이미 PASS할 수 있다. PASS면 Step 3은 `_poll_completed_jobs`의 run 갱신만 확인한다.

- [ ] **Step 3: 구현**

`_poll_completed_jobs`의 각 완료 분기(DONE/FAILED/CANCELLED)에서 run 폴더가 있는 경우 이미 `_register_run_output(out_dir)`를 부른다. 부르지 않는 분기(Host, Gene KO, Strain, Ratio, dFBA, Spatial, Community, Sweep, Medium growth, Minimal medium)에도 `out_dir`이 존재하면 `self._register_run_output(out_dir)`를 추가한다. `_poll_completed_jobs` 끝에 다음을 넣는다. 끝난 작업을 `bridge.cancelling`에서 지우는 줄이다:
```python
        for jid in list(self.bridge.cancelling):
            if self.runner.poll(jid).status not in (JobStatus.PENDING, JobStatus.RUNNING):
                self.bridge.cancelling.discard(jid)
```

- [ ] **Step 4: 통과 확인**

Run: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest tests/test_workspace_activity_flow.py tests/test_gui_search_cancel.py ; echo rc=$?`
Expected: 실패 0개.

- [ ] **Step 5: 커밋**

```bash
git add cmig/gui/app.py tests/test_workspace_activity_flow.py
git commit -m "feat(gui): pending cancel for every job and finished runs listed in RUNS

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

---

### Task 11: 문서, 화면 최종 확인, 전체 검증

**Files:**
- Modify: `docs/USER_GUIDE.md`(GUI 절), `CHANGELOG.md`(`[Unreleased]`), `docs/tracking/status.md`, `cmig/gui/AGENTS.md`, `cmig/io/AGENTS.md`, `README.md`(GUI 빠른 시작 문단이 있으면)

- [ ] **Step 1: 사용 설명서 GUI 절 다시 쓰기**

`docs/USER_GUIDE.md`에서 GUI 사용법을 설명하는 절(`grep -n "GUI" docs/USER_GUIDE.md`로 찾음. 2026-09-29 주기에 추가한 Search 문단 포함)을 다음 내용으로 고친다. 모두 영어로 쓴다(이 문서는 영어):
- Projects: New/Open/Open Recent, 폴더 구조(`cmig-project.json`, `models/`, `media/`, `runs/`, `runs/_inputs/`), 잠금, 프로젝트를 옮겨도 열린다는 점
- Adding models: Add Models…(여러 개), from Folder, drag & drop, AGORA2. 점검 상태 ✓/⚠/✗, 중복 거부, checksum 변경 감지
- The window: sidebar 그룹, Analysis 메뉴, Run ⌘R, Inspector, Activity, 단축키 표
- Analyses: 모델·배지 선택기. 출력은 항상 `runs/<kind>-YYYYMMDD-HHMMSS`. Search Output folder 칸은 없어졌다
- run_hash 주의: GUI는 `--taxonomy`로 넘기므로 같은 모델이라도 이전 `--model-dir` 실행과 hash가 다를 수 있다
- Open Run…: 프로젝트 밖 run은 읽기 전용으로 RUNS에 "(opened)"로 보인다

- [ ] **Step 2: CHANGELOG, 상태 문서, AGENTS 문서**

`CHANGELOG.md` `[Unreleased]` 맨 위에 다음을 추가한다:
```markdown
### Changed — GUI workspace (phase 1)

- The desktop GUI is organised around an on-disk project folder (`cmig-project.json`,
  `models/`, `media/`, `runs/`). Models are copied in with SHA-256 checks; several files,
  whole folders, drag-and-drop and AGORA2 strains can be added at once, in the background.
- Standard File/Edit/View/Analysis/Window/Help menus, a three-group toolbar, a sidebar of
  models, media, analyses and runs, a selection-following inspector and a bottom activity
  pane replace the tab bar, Project Explorer, jobs table and the Import Model / Run Fixture /
  Show Advanced Tools buttons.
- Every analysis picks models and media from the project and writes to a new
  `runs/<kind>-YYYYMMDD-HHMMSS` folder; the GUI passes `--taxonomy runs/_inputs/<run>-taxonomy.csv`
  to the unchanged CLI. Runs started this way can have a different `run_hash` from earlier GUI
  runs of the same models that used `--model-dir`. The Search "Output folder" field is removed.
```
`docs/tracking/status.md`:
- 완료 기능 표의 GUI 행을 새 구조로 고친다.
- 남은 작업에 "GUI 2단계: 분석 화면 재구성(Search·Gene KO·Growth 분리 등)"과 "GUI 3단계: 결과 보기·비교 통일"을 1·2번으로 넣는다.
- 검증 증거 표에 이번 실행 결과를 Step 4 후에 추가한다.

`cmig/gui/AGENTS.md`:
- 범위 목록에 새 파일(`project_session.py`, `sidebar.py`, `inspector.py`, `activity.py`, `pickers.py`, `agora2_dialog.py`)을 넣는다.
- 불변식을 추가한다:
  - 분석은 프로젝트가 있어야 실행된다.
  - 모델 입력은 선택기에서 받고, run 입력 taxonomy는 `runs/_inputs/`에 둔다. run 폴더에 미리 쓰지 않는다.
  - 출력은 `runs/` 새 폴더다.
  - 툴바의 모든 항목은 메뉴에도 있다.
  - 모델 추가는 백그라운드 작업이고, 실패한 파일만 격리한다.
- 지난 주기의 "출력 폴더 지정 시 하위 폴더" 불변식은 지운다.

`cmig/io/AGENTS.md`:
- 범위 목록에 `project.py`를 넣고 한 줄 설명을 단다: 프로젝트 형식, 잠금, 모델·배지 사본과 sha256, run 폴더와 입력 taxonomy.
- 불변식을 추가한다: 프로젝트 JSON 경로는 상대 경로로 둔다. 손상되거나 미래 형식인 파일은 쓰지 않고 거부한다.

- [ ] **Step 3: 최종 화면 캡처 확인**

Task 6 Step 8 스크립트에 다음 상태를 더해 1280×800과 1500×950 두 크기로 캡처하고 PNG를 직접 연다:
- 모델 선택 후 상세 패널
- 작업 창을 펼친 상태
- AGORA2 창(`Agora2Dialog(lambda q: [...])`)

잘림, 겹침, 의미 없는 빈 공간이 있으면 고친 뒤 다시 캡처한다.

- [ ] **Step 4: 전체 검증**

Run:
```bash
uv run --no-sync python scripts/harness_checks.py --tier quality ; echo quality_rc=$?
QT_QPA_PLATFORM=offscreen uv run --no-sync pytest -ra --junitxml=/tmp/cmig-full.xml > /tmp/cmig-full.log 2>&1 ; echo pytest_rc=$?
grep -E "passed|failed" /tmp/cmig-full.log | tail -1
uv run --no-sync cmig golden verify ; echo golden_rc=$?
uv run --no-sync cmig golden verify-envelope ; echo envelope_rc=$?
```
Expected:
- `quality_rc=0`, `golden_rc=0`, `envelope_rc=0`
- pytest 요약이 `0 failed`이고, `/tmp/cmig-full.xml`의 failures=0, errors=0
- skip은 기존 인간 GEM fixture 18개만 허용한다.
- `pytest_rc=139`는 알려진 macOS 종료 문제다. 요약과 junit으로 판정하고 결과 보고에 그대로 적는다.

- [ ] **Step 5: 상태 문서에 증거 기록 후 커밋**

```bash
git add docs/ CHANGELOG.md cmig/gui/AGENTS.md cmig/io/AGENTS.md README.md
git commit -m "docs: document the project-based GUI workspace

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KCH3KEG7mnsrB2q9cHACUX"
```

- [ ] **Step 6: 사용자 확인 요청**

`uv run --no-sync cmig gui`로 실제 화면을 띄운다. 사용자에게 다음 흐름 확인을 부탁한다:
1. 새 프로젝트를 만든다.
2. 폴더째 모델을 끌어다 놓는다.
3. Search에서 모델 일부를 골라 실행한다.
4. RUNS에서 결과를 다시 연다.
5. 상세 패널에서 Copy Command를 눌러 본다.
