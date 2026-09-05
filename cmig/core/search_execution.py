"""Cooperative search control and resumable, strict-JSON evaluation checkpoints."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cmig.io.atomic import atomic_write_text


class SearchCancelled(Exception):
    """A cancellation boundary between evaluations; never a failed consortium."""


@dataclass
class SearchControl:
    checkpoint: Path | None = None
    resume: bool = False
    cancelled: Callable[[], bool] | None = None
    progress: Callable[[int, int], None] | None = None
    workers: int = 1
    solver_threads: int = 1
    solve_timeout: float | None = None
    records: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    algorithm_state: dict[str, Any] | None = None
    timings: dict[str, float] = field(default_factory=dict)
    validation_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    _identity: str = ""
    _context: dict[str, Any] = field(default_factory=dict)

    @contextmanager
    def session(self) -> Iterator[None]:
        if self.checkpoint is None:
            yield
            return
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        lock = self.checkpoint.with_name(self.checkpoint.name + ".lock")
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ValueError(f"checkpoint is in use (or has a stale lock): {lock}") from error
        os.close(descriptor)
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def check(self) -> None:
        if self.cancelled is not None and self.cancelled():
            suffix = "; completed evaluations are checkpointed" if self.checkpoint else ""
            raise SearchCancelled(f"search cancelled{suffix}")

    def bind(self, context: dict[str, Any]) -> None:
        if self.workers < 1 or self.solver_threads < 1:
            raise ValueError("workers and solver_threads must be positive")
        if self.solve_timeout is not None:
            import math

            if not math.isfinite(self.solve_timeout) or self.solve_timeout <= 0:
                raise ValueError("solve_timeout must be finite and > 0")
        encoded = json.dumps(context, sort_keys=True, allow_nan=False, separators=(",", ":"))
        self._identity = hashlib.sha256(encoded.encode()).hexdigest()
        self._context = context
        if self.resume:
            if self.checkpoint is None or not self.checkpoint.is_file():
                raise ValueError("--resume requires an existing search checkpoint")
            payload = json.loads(self.checkpoint.read_text())
            if payload.get("schema") != 1 or payload.get("identity") != self._identity:
                raise ValueError("checkpoint input/configuration/policy mismatch; start a new run")
            self.records = {tuple(row["members"]): row for row in payload["evaluations"]}
            self.algorithm_state = payload.get("algorithm_state")
            self.validation_records = payload.get("validation_records", {})
        else:
            self.records = {}
            self.algorithm_state = None
            self.validation_records = {}
            if self.checkpoint is not None and self.checkpoint.exists():
                raise ValueError("checkpoint already exists; use --resume or a new checkpoint path")
        self.check()

    def save(self) -> None:
        if self.checkpoint is None:
            return
        payload = {
            "schema": 1,
            "identity": self._identity,
            "request": self._context,
            "algorithm_state": self.algorithm_state,
            "evaluations": list(self.records.values()),
            "validation_records": self.validation_records,
        }
        self.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.checkpoint,
            json.dumps(payload, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n",
        )

    def save_algorithm(self, state: dict[str, Any]) -> None:
        self.algorithm_state = state
        self.save()

    def report(self, done: int, total: int) -> None:
        if self.progress is not None:
            self.progress(done, total)
