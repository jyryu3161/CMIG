<!--
  PDCA Design — cmig-engine-service-facade (Roadmap Phase 0.1)
  Plan: docs/01-plan/features/cmig-engine-service-facade.plan.md
  Architecture: Option C (Pragmatic) — selected at Checkpoint 3.
  Validated by 10-agent design workflow (4 ground · 3 option-design · 3 adversarial purity critics).
-->

# cmig-engine-service-facade Design Document

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | Option C의 EngineService facade·Store seam(#3)이 명시 클래스로 부재 → GUI·JobRunner·PART II 착수 불가. |
| **WHO** | CLI(현재)·GUI app shell(0.3)·JobRunner(0.2)·AN-SINGLE(1.1)·search·host dashboard. |
| **RISK** | facade가 위임 아닌 재구현 시 run_hash 단일 canonical([HASH-SINGLE]) 위반 → 191 tests·golden 회귀. |
| **SUCCESS** | facade 경유 run_hash·parquet 비트 일치 + 191 green + Store cache hit/miss 정확 + CLI facade 소비. |
| **SCOPE** | facade(위임) + FileSystemStore(seam #3, sqlite meta) + CLI 리팩터. OUT: solve_single 실로직(1.1)·JobRunner(0.2)·GUI(0.3+). |

## Architecture Selection (Checkpoint 3)

선택 = **Option C (Pragmatic)**. 10-agent workflow가 3안을 독립 설계 후 적대 검증:

| | A Minimal | B Clean | **C Pragmatic** ⭐ |
|---|---|---|---|
| facade | free funcs | full ports/adapters | **explicit class + 단일 engine/store 주입** |
| Store 경계 | clear(얕음) | ❌ dual-role 결함(`boundaryClear=False`) | ✅ clean |
| 복잡도/effort | Low/S | High/L | Medium/M |
| 유지보수/risk | Med/Low | High/**Med** | **High/Low** |
| 적대 검증 | sound-with-fixes | sound-with-fixes | **sound-with-fixes** |

3안 모두 `recomputesRunHash=False · bitIdentity=True · qtIndependent=True · honestStub=True`. C가 경계 clean + risk Low + maintainability High로 16 downstream 소비자 토대에 최적. **적대 검증이 잡은 2개 개선을 본 설계에 반영**(아래 §2.4·§3.3).

## 1. Overview

### 1.1 Module Map (Option C)

| 모듈 | 신규/수정 | 역할 | 위임 대상(재구현 금지) |
|------|----------|------|----------------------|
| `cmig/service/__init__.py` | 신규 | 패키지(Qt 비의존 선언) | — |
| `cmig/service/engine_service.py` | 신규 | **EngineService** facade — solve_fixture·solve_community·solve_single(stub) | engine·interactions·medium_spec·fva·targets·io.solve_output |
| `cmig/service/outcome.py` | 신규 | **SolveOutcome** 값객체 — run_hash는 manifest에서 read | manifest(간접) |
| `cmig/service/store.py` | 신규 | **FileSystemStore** — run_hash별 artifact + sqlite meta + cache_lookup | io.write_solve_output(간접)·sqlite3(stdlib) |
| `cmig/core/run_store.py` | 신규 | **RunStore Protocol** canonical 정의(core 유지, 레이어 불변) | — |
| `cmig/core/sandbox.py` | 수정 | RunStore를 core/run_store에서 re-export(back-compat) | — |
| `cmig/cli/main.py` | 수정 | `_cmd_solve`/`_cmd_solve_fixture`를 facade 소비로 축소(~50→~15줄) | EngineService |
| `tests/test_service_facade.py` | 신규 | 위임·비트 일치·honest stub·Qt-import 격리 | — |
| `tests/test_filesystem_store.py` | 신규 | record_run idempotent·cache_lookup hit/miss·Protocol·sandbox commit | — |

### 1.2 데이터 흐름 (불변)
```
CLI ─argparse검증→ EngineService.solve_community(taxonomy, model_checksum=file_checksum(path), …)
  └ build_community → [apply_medium] → cooperative_tradeoff → build_tidy
       → [community_fva→attach] → [target_summary] → build_run_components
       → write_solve_output(parquet+manifest)            ← run_hash = compute_run_hash (단일 canonical)
  └ SolveOutcome.from_manifest(...)  ← run_hash = json.load(manifest)["run_hash"]  (재계산 0)
선택적: store.record_run(outcome.run_hash, outcome.result)   ← COMMIT 시에만, opt-in
```

## 2. EngineService facade (`cmig/service/engine_service.py`)

### 2.1 클래스 형태
- `EngineService(engine: MicomEngine | None = None)` — 단일 `MicomEngine` 보유(주입 가능 → 테스트·GUI·JobRunner 공용). `micom_version` property.
- **순수 위임**: 모든 메서드가 기존 core/io 함수를 *동일 순서·동일 인자*로 호출. 신규 계산·신규 hash 코드 0.

### 2.2 `solve_fixture(*, solver="gurobi", out_dir, fva=False, targets=None) -> SolveOutcome`
- `golden_fixture.solve_with_community(solver)` → (result, bundle, community).
- `fva` → `fva.community_fva(community, fraction_of_optimum=TRADEOFF_F)` + `attach_community_fva_to_bundle`.
- `targets` → `_target_summary_or_none`(미지 preset → ValueError, CLI가 rc2 처리).
- components = **`golden_fixture._run_hash_components(result)`** (fixture 고정 11구성, build_run_components와 분리 유지).
- `write_solve_output(bundle, components, out_dir, diagnostic=result.diagnostic, target_summary=tsum)` → manifest_path.
- `SolveOutcome.from_manifest(...)`.

### 2.3 `solve_community(*, taxonomy, solver="gurobi", tradeoff_f=0.5, medium_path=None, model_checksum, fva=False, targets=None, out_dir, env_lock=None) -> SolveOutcome`
- `load_medium(medium_path)` if medium_path → `build_community` → `apply_medium`(spec 있으면) → `cooperative_tradeoff` → `build_tidy` → [fva] → [targets].
- components = **`io.build_run_components(result, model_checksum=…, medium_checksum=medium_checksum(spec), tradeoff_f=…, micom_version=…)`** (user 경로 — `_run_hash_components` 아님).
- `model_checksum`은 CLI가 `file_checksum(tax_path)`로 산출해 주입(파일 I/O는 edge 유지, facade는 path-agnostic).
- `env_lock` 기본 None — **CLI shim은 env_lock를 전달하지 않음**(오늘과 동일, manifest bytes 불변). [적대 검증 MINOR 반영]

### 2.4 `solve_single(...)` — HONEST stub (적대 검증 DEFECT 반영)
- **수정 전(워크플로 초안)**: `cap.supports("MILP")` 게이트 — **오류**. AN-SINGLE은 단일-GEM FBA/pFBA/FVA = **LP/QP**, MILP 아님(§5.3·fva.py). osqp-only 환경에서 "MILP unavailable"은 잘못된 근거(osqp는 QP 가능).
- **수정 후(확정)**: MILP/MILPUnavailableError 기제 제거. **무조건** `CAPABILITY_MISSING` 반환:
  ```python
  def solve_single(self, *, gem, mode="FBA", solver="gurobi") -> SolveOutcome:
      diag = diagnostic_from_parts([(DiagnosticCode.CAPABILITY_MISSING,
          "solve_single (AN-SINGLE) not implemented — Phase 1.1; facade stub")])
      return SolveOutcome.capability_missing(diag)
  ```
- 가짜 SolveResult/run_hash/manifest 절대 생성 금지(누적 교훈 "테스트 green ≠ 기능 연결").

## 3. SolveOutcome 값객체 (`cmig/service/outcome.py`)

### 3.1 형태
`@dataclass(frozen=True) SolveOutcome`:
- `result: SolveResult | None` · `bundle: Any | None` · `components: RunHashComponents | None`
- `run_hash: str | None` (**manifest에서 read**) · `manifest_path: Path | None` · `community: Any | None`
- `status: str` ∈ {`ok`, `capability_missing`} · `diagnostic: str | None`

### 3.2 생성자
- `from_manifest(result, bundle, components, manifest_path, *, community=None)`: `run_hash = json.loads(manifest_path.read_text())["run_hash"]` ([HASH-SINGLE], 재계산 0), status="ok".
- `capability_missing(diagnostic)`: result/bundle/run_hash=None, status="capability_missing".

### 3.3 호출 규율 (적대 검증 Optional-looseness 반영)
- Optional 필드는 stub 수용을 위함. **소비자는 dereference 전 `status`/`run_hash is not None` 분기 필수**(타입 시스템 미강제 → docstring + 테스트로 강제). CLI: `if outcome.status != "ok": print(diag); return 2`.

## 4. FileSystemStore (`cmig/service/store.py`) — Store seam #3

### 4.1 RunStore Protocol 위치 (적대 검증 ARCH-INVERSION 반영)
- **수정 전(초안)**: Protocol을 service로 이동 + sandbox re-export → **core가 service를 import**(레이어 역전, `core/__init__.py` "외부 의존 없는 순수 도메인" 위반).
- **수정 후(확정)**: Protocol canonical은 **core 유지** — `cmig/core/run_store.py`에 `@runtime_checkable class RunStore(Protocol): record_run(run_hash, result)`. `core/sandbox.py`는 `from cmig.core.run_store import RunStore` re-export(back-compat). `service.FileSystemStore`가 core의 RunStore를 *구현*. **방향: service → core (정상)**, 역전 없음.
- `InMemoryRunStore`는 sandbox에 유지(테스트/preview double). 순환 import 없음(run_store는 SolveResult만 의존, sandbox 미의존).

### 4.2 FileSystemStore API
- `__init__(root)`: `root/<run_hash>/` artifact 디렉터리 + `root/index.sqlite` meta. 스키마 멱등 생성(WAL).
- `record_run(run_hash, result)` (Protocol): `INSERT OR IGNORE` → 멱등 dedup. run_hash는 **인자**(절대 계산 안 함). NaN objective → NULL.
- `cache_lookup_by_run_hash(run_hash) -> dict | None`: 영속 meta row(status/objective/diagnostic/run_dir) 반환 또는 None. **재solve·재계산 없음**(존재/provenance probe).

### 4.3 sqlite meta 스키마
```sql
CREATE TABLE IF NOT EXISTS runs (
  run_hash TEXT PRIMARY KEY, created_utc TEXT NOT NULL, run_dir TEXT NOT NULL,
  status TEXT NOT NULL, objective REAL, growth_solver TEXT, flux_solver TEXT,
  micom_version TEXT, diagnostic TEXT);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
```

### 4.4 Store ↔ sweep RunHashCache 경계 (불변)
- **RunHashCache**(sweep.py): in-process, value replay(growth 값 캐시). **변경 없음**.
- **FileSystemStore**: 영속 cross-session, meta/dedup probe. 둘 다 **동일 단일 run_hash**로 key → **hash 구현 1개**, 책임 비중첩. 비대칭(ephemeral=value replay vs durable=meta probe)은 명시 문서화.

## 5. CLI 리팩터 (`cmig/cli/main.py`)
- `_cmd_solve_fixture`/`_cmd_solve`: (1) argparse 검증(파일 존재·`0<f≤1`·`{id,file}` 컬럼·ImportError→rc2)은 **CLI 유지**. (2) `EngineService()` 생성. (3) `svc.solve_fixture(...)` / `svc.solve_community(..., model_checksum=file_checksum(tax_path))` 호출(ValueError→rc2 try/except 동일). (4) `outcome.run_hash`/`outcome.result.objective`로 기존 print.
- **인자명·choices·default·rc·stdout/stderr 문자열 전부 불변** → `test_cli_solve.py`/`test_cli_solve_medium.py`/`test_cli_targets.py` green.
- Phase 0.1 default CLI 경로에 **persistence 미연결**(FileSystemStore는 opt-in, 후속 `--store DIR`) → artifact 집합 불변 → 비트 일치.

## 6. Qt-independence
- `cmig/service/*` import 집합 = engine·interactions·medium_spec·diagnostics·solve_output·fva·targets·golden_fixture + stdlib(sqlite3·json·pathlib·dataclasses·pandas). **PySide6 0**. import 격리 테스트로 lock(`test_service_facade`가 `import cmig.service.*` 후 `sys.modules`에 PySide6 부재 assert).

## 7. Test Plan

| 레벨 | 테스트 | 검증 |
|------|--------|------|
| 비트 일치 | `test_facade_solve_fixture_bit_identical` | facade solve_fixture 산출 run_hash·nodes/edges/profile parquet bytes == 현 `_cmd_solve_fixture`(또는 golden config.json) |
| 비트 일치 | `test_facade_solve_community_matches_cli` | facade solve_community manifest run_hash == `build_run_components`+`compute_run_hash` |
| Store | `test_record_run_idempotent` | 동일 run_hash 2회 → 1 row(INSERT OR IGNORE) |
| Store | `test_cache_lookup_hit_miss` | 기록 후 hit(meta dict)·미기록 miss(None) |
| Store | `test_filesystem_store_satisfies_runstore` | `isinstance(FileSystemStore(...), RunStore)`(runtime_checkable) |
| Store | `test_sandbox_commit_via_filesystem_store` | `evaluate_sandbox(..., store=FileSystemStore)` commit → record_run 영속 |
| honest stub | `test_solve_single_capability_missing` | status="capability_missing"·DiagnosticCode.CAPABILITY_MISSING·run_hash None·가짜 success 없음 |
| Qt 격리 | `test_service_qt_independent` | service import 후 PySide6 미로드 |
| 회귀 | 기존 191 + CLI 전량 | green 유지 |

## 8. Implementation Guide

### 8.1 순서
1. `cmig/core/run_store.py`(Protocol) + `sandbox.py` re-export → 기존 sandbox 테스트 green 확인.
2. `cmig/service/outcome.py`(SolveOutcome).
3. `cmig/service/engine_service.py`(solve_fixture·solve_community·solve_single stub).
4. `cmig/service/store.py`(FileSystemStore + sqlite).
5. `cmig/cli/main.py` 리팩터(facade 소비) → **비트 일치 회귀 즉시 확인**.
6. 신규 테스트 + `ruff`/`mypy strict`/전량 pytest.

### 8.2 Session Guide (`/pdca do --scope`)
| scope | 모듈 | SC |
|-------|------|----|
| `protocol` | core/run_store.py + sandbox re-export | SC-S4 |
| `outcome` | service/outcome.py | SC-S1·SC-S5 |
| `facade` | service/engine_service.py | SC-S1·SC-S5 |
| `store` | service/store.py | SC-S2·SC-S4 |
| `cli` | cli/main.py 리팩터 | SC-S3·SC-S6 |

(단일 세션 권장 — 모듈이 작고 비트 일치 게이트가 전 모듈 동시 검증.)

### 8.3 Conventions
- `// Design Ref: §N — 결정`·`// Plan SC: SC-Sx` 주석.
- [HASH-SINGLE] 위임 / gurobi-only / 구조화 Diagnostic / tidy v1.1.

## 9. Risks
| 위험 | 완화 |
|------|------|
| facade 재구현 → run_hash 표류 | write_solve_output·compute_run_hash 그대로 호출 + 비트 일치 테스트(최우선) |
| Protocol 위치 역전 | **core 유지**(run_store.py) + service가 구현 — 역전 제거(§4.1) |
| solve_single 오류 게이트 | MILP 기제 제거, 무조건 CAPABILITY_MISSING(§2.4) |
| SolveOutcome Optional deref | status 분기 규율 + 테스트(§3.3) |
| env_lock manifest leak | CLI shim env_lock 미전달(§2.3) |

## 10. Next Steps
1. `/pdca do cmig-engine-service-facade` — Checkpoint 4 후 §8.1 순서 구현.
2. `/pdca analyze` — gap + 비트 일치 회귀 + (선택) 적대 리뷰.
3. Phase 0.2 `cmig-jobrunner`(facade 소비).

## Version History
| 버전 | 일자 | 내용 |
|------|------|------|
| v1.0 | 2026-06-01 | Option C 선택(Checkpoint 3). 10-agent workflow 검증 + 적대 개선 2건 반영(solve_single MILP→무조건 CAPABILITY_MISSING; RunStore Protocol core 유지로 레이어 역전 제거). |
