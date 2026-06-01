"""FileSystemStore — 영속 cross-session run store (Option C, seam #3).

Design Ref: §4 (cmig-engine-service-facade.design). Plan SC: SC-S2·SC-S4.

`root/<run_hash>/` 에 artifact, `root/index.sqlite` 에 meta. core 의 RunStore Protocol 을
*구현*(service → core 방향, 레이어 정상). stdlib sqlite3 만 사용 — **run_hash 재계산 코드 0**
(run_hash 는 호출자가 인자로 준다, [HASH-SINGLE]).

[경계] sweep.RunHashCache(in-process, value replay)와 공존하나 책임 비중첩 — 둘 다 동일
단일 run_hash 로 key 하므로 hash 구현은 1개. FileSystemStore = durable meta/provenance probe
(재solve·재계산 없음), RunHashCache = ephemeral 값 replay.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path

from cmig.core.engine import SolveResult

# stdlib sqlite3 meta-index (WAL·멱등). run_hash = single-canonical(manifest 파생).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_hash       TEXT PRIMARY KEY,
    created_utc    TEXT NOT NULL,
    run_dir        TEXT NOT NULL,
    status         TEXT NOT NULL,
    objective      REAL,
    growth_solver  TEXT,
    flux_solver    TEXT,
    micom_version  TEXT,
    diagnostic     TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
"""


class FileSystemStore:
    """durable run store. core.RunStore Protocol 구현(record_run). cache_lookup 은 meta probe."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._db = self.root / "index.sqlite"
        with self._connect() as cx:
            cx.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        cx = sqlite3.connect(self._db)
        cx.execute("PRAGMA journal_mode=WAL")
        return cx

    def record_run(self, run_hash: str, result: SolveResult) -> None:
        """RunStore Protocol — COMMIT 시에만 호출(preview 비기록). 멱등(INSERT OR IGNORE).

        run_hash 는 **인자**(재계산 안 함). NaN objective → NULL.
        """
        run_dir = self.root / run_hash
        run_dir.mkdir(parents=True, exist_ok=True)
        obj = result.objective if result.objective == result.objective else None  # NaN→NULL
        with self._connect() as cx:
            cx.execute(
                "INSERT OR IGNORE INTO runs(run_hash,created_utc,run_dir,status,objective,"
                "growth_solver,flux_solver,micom_version,diagnostic) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    run_hash,
                    datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    run_hash,
                    result.status,
                    obj,
                    result.growth_solver,
                    result.flux_solver,
                    getattr(result, "micom_version", None),
                    result.diagnostic,
                ),
            )

    def cache_lookup_by_run_hash(self, run_hash: str) -> dict[str, object] | None:
        """cross-session dedup probe — 기록된 meta row(dict) 또는 None. 재solve·재계산 없음."""
        with self._connect() as cx:
            cx.row_factory = sqlite3.Row
            row = cx.execute(
                "SELECT * FROM runs WHERE run_hash=?", (run_hash,),
            ).fetchone()
        return dict(row) if row is not None else None
