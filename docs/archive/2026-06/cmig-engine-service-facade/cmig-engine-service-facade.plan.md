<!--
  PDCA Plan — cmig-engine-service-facade (Roadmap Phase 0.1)
  Roadmap: ~/.claude/plans/snoopy-spinning-castle.md
  Predecessors (archived): cmig-community-core → baseline-hardening → analysis-foundations → analysis-completion
-->

# cmig-engine-service-facade Planning Document

> Roadmap Phase 0.1 — MVP-0 Foundation 인프라의 불가피한 critical path 1순위.
> 모든 GUI(§11)·JobRunner(0.2)·PART II가 이 facade 경계에 의존.

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Option C 아키텍처의 핵심인 **EngineService facade·Store seam이 명시 클래스로 존재하지 않는다** — solve/sandbox/sweep/io 오케스트레이션이 `cli/main.py`·`golden_fixture.py`·`io/solve_output.py`에 산재. GUI·JobRunner·search·host가 전부 이 경계를 필요로 하나 단일 진입점이 없어 중복·표류 위험. |
| **Solution** | `cmig/service/` 신규 패키지에 **명시 `EngineService` facade**(기존 함수를 *위임만*, 계산 신규 0)와 **`FileSystemStore`**(run_hash별 parquet artifact + stdlib sqlite3 meta index + `cache_lookup_by_run_hash`, 기존 `RunStore` Protocol 승격)를 도입하고, **CLI를 facade 소비로 리팩터**. |
| **Function UX Effect** | CLI·GUI·JobRunner가 동일 facade 메서드(`solve_community`·`run_sweep`·`run_sandbox_preview`·`commit_sandbox`)를 호출. 동일 run_hash 재요청은 Store cache로 재계산 회피. `solve_single`은 정직한 capability_missing 시그니처(실제 분석은 1.1). |
| **Core Value** | "한 번 계산한 결과는 한 곳에서, 같은 입력은 한 번만" — 재현성(run_hash 단일 canonical 유지)·정직성(가짜 라벨 없음)·후속 16 feature의 공통 토대. |

## Context Anchor

| 항목 | 내용 |
|------|------|
| **WHY** | facade/Store 부재로 GUI·PART II 착수 불가 — Option C 4 seam 중 #3(Store)·facade 경계를 실체화해야 전 로드맵이 이를 소비 가능. |
| **WHO** | CLI 사용자(현재)·GUI app shell(0.3)·JobRunner(0.2)·consortium search·host dashboard(PART II) — 전부 facade 소비자. |
| **RISK** | facade가 위임이 아니라 *재구현*하면 run_hash 단일 canonical([HASH-SINGLE]) 위반 → 191 tests·golden 회귀. Store와 sweep `RunHashCache` 중복/표류. |
| **SUCCESS** | facade 경유 산출 run_hash·parquet이 현 CLI 경로와 **비트 일치** + 191 tests green + Store cache_lookup hit/miss 정확 + CLI가 facade 소비. |
| **SCOPE** | facade(위임) + FileSystemStore(seam #3) + CLI 리팩터. **OUT**: solve_single 실제 로직(1.1)·JobRunner(0.2)·GUI(0.3+)·SBML import(0.4). |

## 1. Overview

### 1.1 Purpose
Option C의 **single EngineService facade**와 **Store seam(#3)**을 명시 클래스로 실체화하여, 산재된 community solve 오케스트레이션을 단일 진입점으로 통합하고 영속 결과 저장/캐시 조회를 제공한다. headless core(engine·tidy·manifest·sweep·sandbox)는 그대로 두고 **위임 계층만 신설**한다.

### 1.2 Background — 현 구조 (probe 검증)
- `cli/main.py` 의 `_cmd_solve`/`_cmd_solve_fixture` 가 직접 `MicomEngine.build_community → cooperative_tradeoff → build_tidy → (community_fva) → build_run_components → write_solve_output` 를 인라인 오케스트레이션 (docstring은 이미 "§4.1 EngineService facade 소비"를 *주장*하나 클래스 부재).
- `core/sandbox.py` 에 **`RunStore` Protocol**(`record_run`) + `InMemoryRunStore` 이미 존재 → FileSystemStore가 이 Protocol을 구현·승격.
- `core/sweep.py` 에 **`RunHashCache`**(in-memory run_hash→entry) 존재 → Store는 *영속* 계층으로 공존(중복 hash 구현 금지).
- `io/solve_output.py` 의 `build_run_components`·`write_solve_output` 가 단일 canonical run_hash 경로([HASH-SINGLE]).

### 1.3 Related Documents
- Roadmap: `~/.claude/plans/snoopy-spinning-castle.md` (Phase 0.1)
- Design (Option C): `docs/archive/2026-05/cmig-community-core/cmig-community-core.design.md` §2(facade·4 seam·JobRunner)·§4.1(facade 메서드표)
- 결정: `docs/decisions/2026-06-01-golden-solver-list.md` (gurobi-only)
- 명세: `CMIG_명세서_v3.0.md` §3(아키텍처: sidecar + job runner)·§7(RunManifest/run_hash)

## 2. Scope

### 2.1 In Scope
1. **`cmig/service/engine_service.py`** — `EngineService` 클래스(Qt 비의존). 메서드(전부 기존 함수 위임):
   - `solve_community(taxonomy, *, medium, solver, tradeoff_f, fva, targets) -> SolveOutcome`
   - `solve_fixture(solver, *, fva, targets) -> SolveOutcome` (golden_fixture 위임)
   - `run_sweep(...)`·`run_sandbox_preview(...)`·`commit_sandbox(...)` (sweep/sandbox 위임)
   - `solve_single(...)` — **정직한 stub**: 구조화 `capability_missing` diagnostic 반환(실제 1.1).
   - `SolveOutcome` dataclass: `(result, bundle, components, run_hash, community?)`.
2. **`cmig/service/store.py`** — `FileSystemStore`:
   - `RunStore` Protocol 승격(service로 이동 + sandbox back-compat re-export).
   - `write_outcome(outcome) -> Path`(run_hash별 디렉터리 parquet+manifest, `write_solve_output` 위임).
   - `record_run(run_hash, result)`(Protocol)·`cache_lookup_by_run_hash(run_hash) -> StoredRun | None`.
   - **stdlib sqlite3 meta index**: `runs(run_hash PK, scenario_id, state, artifacts_json, created_at)`.
3. **CLI 리팩터** — `_cmd_solve`/`_cmd_solve_fixture` 를 `EngineService` 소비로 전환(인라인 오케스트레이션 제거). 출력 **비트 일치** 유지.
4. **테스트** — `tests/test_engine_service.py`(위임·비트 일치)·`tests/test_store.py`(cache hit/miss·sqlite meta·Protocol 충족).

### 2.2 Out of Scope
- `solve_single` 실제 cobra FBA/pFBA/knockout 로직 → **Phase 1.1** `cmig-an-single`.
- JobRunner(비차단 실행·cancel) → **Phase 0.2**.
- GUI app shell·ProjectExplorer·Runtime&Jobs → **Phase 0.3**.
- SBML/JSON/MAT import·Model Manager·Medium Editor GUI → **Phase 0.4**.
- 신규 solver/과학 로직 일체(gurobi-only 유지).

## 3. Requirements

### 3.1 Functional Requirements
- **FR1**: `EngineService.solve_community` 가 현 `_cmd_solve` 와 **동일 산출**(run_hash·nodes/edges/profile parquet·manifest) — 위임만.
- **FR2**: `FileSystemStore.write_outcome` 가 run_hash별 디렉터리에 artifact 저장 + sqlite meta upsert. `cache_lookup_by_run_hash` 가 hit 시 `StoredRun`(경로+meta), miss 시 `None`.
- **FR3**: `FileSystemStore` 가 기존 `RunStore` Protocol 충족 → `sandbox.commit` 이 FileSystemStore로 영속 가능(record_run).
- **FR4**: CLI `solve`·`solve-fixture` 가 facade 소비. 기존 CLI 동작·플래그(`--solver/--medium/--tradeoff-f/--targets/--fva/--out`) 불변.
- **FR5**: `solve_single` 호출 시 구조화 `capability_missing` diagnostic(가짜 success 금지) — honest stub.

### 3.2 Non-Functional
- **NFR1 (Qt 비의존)**: `cmig/service/*` 는 PySide6 import 0 (import-linter/grep 검증).
- **NFR2 (무회귀)**: 기존 191 tests green + facade 경유 run_hash가 현 경로와 **비트 일치**.
- **NFR3 (품질)**: `mypy cmig` strict clean · `ruff check` clean · 0 placeholder.
- **NFR4 (정직성)**: stub·미연결은 capability_missing diagnostic으로 명시(누적 교훈 — "테스트 green ≠ 기능 연결").

## 4. Success Criteria (단계화)

| ID | 단계 | 기준 | 증거 |
|----|----|------|------|
| **SC-S1** | P0 | `EngineService.solve_community`/`solve_fixture` 산출 run_hash·parquet == 현 CLI 경로(비트 일치) | `test_engine_service` 비교 assert |
| **SC-S2** | P0 | `FileSystemStore`: run_hash별 parquet+manifest 저장 + sqlite meta upsert + `cache_lookup` hit/miss 정확 | `test_store` |
| **SC-S3** | P0 | CLI `solve`/`solve-fixture` facade 소비로 리팩터, 기존 CLI 테스트 출력 불변 | 기존 CLI 테스트 green |
| **SC-S4** | P0 | `RunStore` Protocol 승격 + FileSystemStore 충족 → sandbox commit 영속 가능 | `test_store` Protocol·sandbox commit |
| **SC-S5** | P1 | `solve_single` 구조화 capability_missing diagnostic(honest stub) | `test_engine_service` |
| **SC-S6** | P0 | 191 기존 tests green + 신규 service tests + mypy strict + ruff clean | CI 전량 |

## 5. Risks and Mitigation

| 위험 | 영향 | 완화 |
|------|------|------|
| facade가 위임 아닌 *재구현* → run_hash 표류 | Critical(전 golden·191 tests) | `build_run_components`/`write_solve_output`/`compute_run_hash` 그대로 호출 + **비트 일치 회귀 테스트** |
| Store sqlite ↔ sweep `RunHashCache` 중복/표류 | Important | 경계 분리: RunHashCache=in-process sweep replay, FileSystemStore=영속 artifact+meta. cache_lookup은 parquet 존재+meta 조회지 3번째 hash 구현 아님 |
| CLI 리팩터로 출력 키/순서 변동 | Important | `write_solve_output` 미수정 + golden manifest 비교 |
| `RunStore` Protocol 이동이 sandbox import 파손 | Minor | sandbox에 back-compat re-export 유지 |

## 6. Impact Analysis

### 6.1 Changed/New
- **New**: `cmig/service/__init__.py`·`engine_service.py`·`store.py` · `tests/test_engine_service.py`·`tests/test_store.py`
- **Modified**: `cmig/cli/main.py`(facade 소비 리팩터) · `cmig/core/sandbox.py`(Protocol re-export) · `pyproject.toml`(신규 런타임 의존 **없음** — sqlite3 stdlib)

### 6.2 Consumers
- 즉시: CLI. 후속: JobRunner(0.2)·GUI app shell(0.3)·Model import/editor(0.4)·AN-SINGLE(1.1)·consortium search·host dashboard.

## 7. Architecture Considerations
- Option C facade·seam #3(Store) 실체화. **계산 신규 0** — 순수 위임/영속 계층.
- `cmig/service/`(Qt 비의존) = core(순수 계산)와 GUI(Qt) 사이 경계. CLI·GUI 공통 소비(SC-7).
- sqlite meta는 명세 §3(YAML+SQLite 메타) 정합.

## 8. Convention Prerequisites
- [HASH-SINGLE]/[HASH-11] run_hash 단일 canonical 불변.
- gurobi-only(full=gurobi, osqp=qp_only_approximate).
- 구조화 Diagnostic(`{code,message,detail}`, DiagnosticCode enum) — solve_single stub은 `capability_missing`.
- tidy v1.1 단일 계약(nodes/edges/profile, `read_legacy_or_upgrade`).

## 9. Next Steps
1. `/pdca design cmig-engine-service-facade` — 3 아키텍처 옵션(facade 위치·Store Protocol 경계·SolveOutcome 형태) → Checkpoint 3.
2. `/pdca do` — service 패키지 + Store + CLI 리팩터(비트 일치 게이트).
3. 이후 Phase 0.2 `cmig-jobrunner`.

## Version History
| 버전 | 일자 | 내용 |
|------|------|------|
| v1.0 | 2026-06-01 | 초안 — Roadmap Phase 0.1. Checkpoint 1·2 확정(facade+Store+CLI 리팩터, sqlite meta, cmig/service/ 패키지, solve_single=honest stub). |
