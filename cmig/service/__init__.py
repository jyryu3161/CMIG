"""cmig.service — Qt 비의존 facade 계층 (Option C, seam 경계).

core(순수 계산)와 GUI(Qt) 사이의 **단일 진입점**. CLI·GUI·JobRunner 공통 소비.
이 패키지는 PySide6 를 import 하지 않는다(NFR1) — import 격리 테스트로 lock.

- EngineService: solve_fixture·solve_community·solve_single 위임 facade.
- SolveOutcome: 한 solve 의 산출 묶음 값객체(run_hash 는 manifest 에서 read).
- FileSystemStore: run_hash별 artifact + sqlite meta + cache_lookup (seam #3).
"""

from __future__ import annotations

from cmig.service.engine_service import EngineService
from cmig.service.jobrunner import (
    Job,
    JobCancelled,
    JobContext,
    JobRunner,
    JobStatus,
    make_sweep_job,
)
from cmig.service.outcome import SolveOutcome
from cmig.service.store import FileSystemStore

__all__ = [
    "EngineService", "SolveOutcome", "FileSystemStore", "JobRunner",
    "Job", "JobStatus", "JobContext", "JobCancelled", "make_sweep_job",
]
