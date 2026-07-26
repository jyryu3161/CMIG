"""RunStore Protocol — commit 시에만 호출되는 영구 store 계약.

Design Ref: §2 (seam #3 Store) · cmig-engine-service-facade.design §4.1.

[레이어 불변] 이 Protocol 은 **core 에 canonical 정의**된다 — `cmig/service/store.py` 의
FileSystemStore 가 이를 *구현*(service → core 방향). core 가 service 를 import 하지 않으므로
"core 는 외부 의존 없는 순수 도메인" 불변(core/__init__) 유지. sandbox.py 는 back-compat 으로
이 이름을 re-export 한다(`from cmig.core.run_store import RunStore`).
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from cmig.core.engine import SolveResult

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def validate_run_hash(run_hash: str) -> str:
    """Enforce the RunStore contract: a run_hash is a canonical SHA-256 hex digest.

    R5-P3 (codex F13): FileSystemStore built ``root / run_hash`` from an unchecked string, so
    ``../escaped`` created a directory outside the store root. The rule lives here, next to the
    Protocol, so every implementation enforces the same thing — a test double that accepts what
    production rejects is how a contract violation reaches production untested.
    """
    if _SHA256_RE.fullmatch(run_hash) is None:
        raise ValueError(
            f"run_hash must be a 64-character lowercase SHA-256 hex digest, got {run_hash!r}"
        )
    return run_hash


@runtime_checkable
class RunStore(Protocol):
    """commit 시에만 호출되는 영구 store. preview 는 절대 호출하지 않는다 (SC-8).

    구현체: InMemoryRunStore(core/sandbox, 테스트/preview double) · FileSystemStore(service, prod).
    run_hash 는 **인자로 받는다** — store 는 run_hash 를 재계산하지 않는다([HASH-SINGLE]).
    """

    def record_run(
        self, run_hash: str, result: SolveResult, *, micom_version: str | None = None
    ) -> None: ...
