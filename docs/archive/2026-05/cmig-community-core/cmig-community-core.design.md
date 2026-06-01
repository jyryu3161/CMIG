---
template: design
version: 1.3
feature: cmig-community-core
project: CMIG (Community Metabolic Interaction GUI)
author: PDCA Design
date: 2026-05-31
status: Draft
architecture: Option C — Pragmatic (layered headless core + EngineService facade + thin SC-driven seams)
---

# cmig-community-core Design Document

> **Summary**: Option C(Pragmatic) — community FBA를 MICOM(정확 pin·public API only)에 위임하고, layered headless `core/` + 단일 EngineService facade + SC가 요구하는 곳에만 thin seam(SolverBackend·MICOM wrapper·Store·RenderClient)을 두는 PySide6 네이티브 데스크톱 설계.
>
> **Project**: CMIG (Community Metabolic Interaction GUI) — native desktop scientific app (NOT SaaS/web)
> **Author**: PDCA Design · **Date**: 2026-05-31 · **Status**: Draft
> **Planning Doc**: [cmig-community-core.plan.md](../../01-plan/features/cmig-community-core.plan.md)
> **Authoritative ground truth**: `CMIG_명세서_v3.0.md` · Schema: [schema.md](../../01-plan/schema.md) · Glossary: [glossary.md](../../01-plan/glossary.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | [Schema Definition](../../01-plan/schema.md) | ✅ |
| Phase 1 | [Glossary](../../01-plan/glossary.md) | ✅ |
| Phase 2 | Coding Conventions | ❌ (pending) |

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 핸드오프 시 전략 컨텍스트 유지.

| Key | Value |
|-----|-------|
| **WHY** | community 대사 상호작용 분석이 스크립트 전용에 갇혀 인터랙티브 가설형성·재현성·출판품질이 단절됨 |
| **WHO** | 전산/시스템 생물학자, microbiome·gut-microbiota 연구자, 미생물 community 대사공학자 |
| **RISK** | (R1) MICOM API/버전 drift → golden 승격 게이트, (R2) namespace mismatch/sign 혼동 → hard gate + sign 테스트 CI, (R3) OSQP LP 정확도/alternate-optima → growth QP→flux LP 재계산 + float tolerance hash |
| **SUCCESS** | solver별 golden 통과 · sign-test CI · namespace gate 차단 · run_hash 캐시 · MICOM-version golden regression |
| **SCOPE** | MVP-0 → MVP-1a(headless core, 1순위) → MVP-1b GUI graph → MVP-1c validation → MVP-2 delta/medium/R/G1 sandbox/G4 sweep. PART II 범위 외. |

---

## 1. Overview

### 1.1 Design Goals

CMIG Baseline(MVP-0~2)의 설계 목표는, community FBA solve를 **MICOM(정확 pin·public API + documented flux only)** 에 위임하면서(Plan §7.2 결정·schema §1.2), CMIG가 **namespace gate·sign 정규화·tidy 계약·delta·sandbox·sweep·R 그림**이라는 부가가치 계층(value-added layer)을 소유하는 **PySide6 네이티브 데스크톱 과학앱**의 headless core를 설계하는 것이다. 본 설계는 9개 Success Criteria(Plan §4.2 SC-1~SC-9)를 **구조적으로 충족**하는 것을 최상위 제약으로 삼는다.

| # | Goal | 충족 SC / 앵커 |
|---|------|----------------|
| G-1 | **엔진 위임 경계 고정** — community FBA는 MICOM 단일 wrapper만 경유(public API + `cooperative_tradeoff(fluxes=True, pfba=...)`), internal API 금지. MICOM 버전 상향은 solver별 golden 전부 통과 시에만 승격. | SC-5 / §4.1·Plan §7.2 |
| G-2 | **정확성 무결성(correctness integrity)** — 모든 solve는 namespace hard gate 통과 후에만 MICOM 호출. sign 변환은 단일 진입점(single entry point)만 경유. | SC-2·SC-3 / §4.3·§4.7·§4.8 |
| G-3 | **재현성 일급화(reproducibility as first-class)** — run_hash 11구성요소(schema §4.2)가 sweep 캐시 키이자 재현 자산. `AggregationStore.run_hash = RunManifest.run_hash = Scenario.run_hash` 비트 단위 일치([HASH-SINGLE], schema §8.4). | SC-1·SC-4·SC-6 / §5·§7·§10 |
| G-4 | **단일 출력 계약(single output contract)** — 전 분석 산출은 `nodes/edges/profile/matrix/timecourse` tidy(parquet)로만 출력, 전 소비자는 단일 reader 경유. sweep store는 §5 카브아웃. | SC-9 / §4.6·schema §2·§6 |
| G-5 | **preview 비오염(non-contamination)** — G1 sandbox preview solve는 store/cache/sweep에 비기록, Apply/Save 시에만 artifact 승격. | SC-8 / §8·A11·schema §8.5 |
| G-6 | **CLI/GUI 공통 headless core** — `core/`는 GUI/CLI/엔진과 독립(headless·테스트 가능). CLI(MVP-1a 산출 진입점)와 GUI가 동일 경계 소비. | SC-7 / Plan §7.3 |
| G-7 | **solver 다변성·강등(capability degradation)** — growth=QP(OSQP) / flux=LP(Gurobi/HiGHS) 분리, LP 부재 시 `QP-only approximate` 표기. capability 부재 시 해당 분석만 비활성화(앱 전체 강등 아님, [disable_analysis_on_missing], schema §5.3). | SC-1·SC-6 / §4.2·§2·A6 |

### 1.2 Design Principles

1. **Delegate the engine, own the value-added layer (§4.1·Plan §1.2)** — community FBA 계산 자체는 buy(MICOM Apache-2.0), 그 위의 정확성·해석·탐색·재현·출판은 own. MICOM은 `core/engine/`의 단일 wrapper로만 호출(public API only)하여 버전 drift(R1)를 golden 승격 게이트로 흡수한다.

2. **Gate before solve, always (§4.8·schema §8.6 [GATE-BLOCK])** — unresolved high-confidence exchange mapping이 1건이라도 있으면 어떤 MICOM solve도 실행되지 않는다([Gate-순서], schema §7.3). gate 통과는 RunManifest/run_hash 정상 산출의 선행조건(precondition)이다.

3. **Single entry point for sign (§4.3·§4.7·schema §8.1 [SIGN-2])** — 모든 `raw_flux → (ui_flux, label)` 변환은 sign 부기 계층 단일 진입점만 경유한다(우회 금지). `ui_flux`는 항상 ≥0인 magnitude. sign_expected.tsv 회귀가 CI gate(SC-2).

4. **Reproducibility by construction (§7·schema §4.2)** — run_hash는 정확히 11개 구성요소(빠짐·추가 금지, [HASH-11]). `env_lock`은 manifest inputs에만 기록하고 run_hash에는 미포함([HASH-ENVLOCK]). float 구성요소는 hash 전 rounding/tolerance 적용([HASH-FLOAT])하여 alternate-optima 잡음(R3)을 흡수한다.

5. **One contract, one reader (§4.6·schema §1.3)** — tidy 5종은 `schema_version` 필드를 갖고 단일 reader로만 소비된다. 스키마 변경 시 bump + 계약 테스트(Plan §6.2·§6.3). sweep.parquet은 §4.6이 §5로 위임한 별개 store([CARVE-OUT]).

6. **Preview is ephemeral, commit is durable (§8·A11)** — Scenario.state 기본값=preview([STATE-DEFAULT]), preview solve는 비기록([PREVIEW-NOWRITE]), run_hash는 commit에서만 영구 산출([RUNHASH-COMMIT]).

7. **No pickle, ever (§5·§8 [NO-PICKLE])** — 일반 직렬화는 Parquet/Arrow/JSON/YAML/SQLite만. TSV는 golden fixture(growth_expected/sign_expected) 전용. 보안(NFR-Security)·import 경로 린트로 강제.

8. **Thin seam only where SC demands it (Option C)** — 추상화는 SC가 필요로 하는 4곳(SolverBackend·MICOM engine wrapper·Store·RenderClient)에만 두고, 나머지는 직접 구현하여 과설계(over-engineering)를 회피한다.

9. **Degrade the analysis, not the app (§2·schema §5.3)** — solver capability 부재는 해당 분석만 비활성화하며 앱 전체를 강등하지 않는다(disable_analysis_on_missing=true).

---

## 2. Architecture (Option C)

### 2.0 Architecture Comparison

세 가지 구조 옵션을 SC 충족도·과설계 위험으로 비교한다. 모두 PySide6 + in-process Python sidecar(Plan §7.2 GUI↔Engine 경계 결정)라는 불변 전제를 공유하며, 차이는 **core 내부의 계층화·seam(이음매) 수준**이다.

| 기준 | **A. Monolithic sidecar** | **B. Full hexagonal (ports & adapters)** | **C. Pragmatic layered + thin seams (Selected)** |
|------|---------------------------|-------------------------------------------|--------------------------------------------------|
| core 구조 | GUI/엔진/계약이 한 모듈에 혼재 | 모든 의존(solver·MICOM·store·render·io)을 port 인터페이스로 추상화 | layered headless `core/` + 단일 EngineService facade + in-process JobRunner |
| seam(인터페이스) 수 | 0 (직접 호출) | 6+ (전 외부 의존 port화) | **4** (SolverBackend·MICOM engine wrapper·Store·RenderClient) |
| SC-1·SC-6 (solver별 golden·OSQP→LP) | ✕ solver 교체 불가(하드코딩) | ◎ 과다 추상화 | ◎ `SolverBackend`로 gurobi/highs/osqp_growth_highs_flux swap |
| SC-5 (MICOM-version golden) | △ 호출 산재→회귀 어려움 | ◎ | ◎ MICOM 단일 진입점 wrapper로 버전 회귀 격리 |
| SC-4·SC-8·SC-9 (캐시·preview 비오염·tidy) | ✕ 기록 경로 산재→preview 누수 위험 | ◎ | ◎ `Store` writer 단일 경유로 tidy/sweep/preview 분리 강제 |
| CLI/GUI 공통(SC-7) | △ GUI 결합 | ◎ | ◎ 둘 다 EngineService 소비 |
| 과설계 위험(R6 scope creep) | 낮음(단순)이나 SC 미충족 | **높음** — port 폭증·테스트 더블 폭증·일정 위협 | **낮음** — seam을 SC 필요처로 한정 |
| 원격 전환(future FastAPI) | ✕ | ◎ | ○ facade 경계가 이미 형성됨 |

> **Selected = C (Pragmatic)**. **Rationale**: 옵션 A는 단순하나 SolverBackend·MICOM wrapper·Store 분리 부재로 SC-1/SC-5/SC-6/SC-8을 구조적으로 충족할 수 없다. 옵션 B는 모든 SC를 충족하나 6+ port·전면 adapter로 과설계(R6)를 유발하고 baseline 일정·검증 초점을 흐린다. 옵션 C는 **SC가 명시적으로 요구하는 4개 seam만** thin하게 두고(SolverBackend·MICOM engine wrapper·Store·RenderClient) 나머지는 직접 구현하여, **9개 SC를 전부 직접 충족하면서 과설계를 회피**한다. facade(EngineService) 경계는 향후 FastAPI/remote 전환의 접합부로도 재사용된다(Plan §7.2 "원격은 optional FastAPI").

### 2.1 Component Diagram

```
┌─────────────────────────────┐     ┌─────────────────────────────┐
│  gui/ (PySide6, presentation)│     │  cli/ (headless 산출 진입점) │
│  explorer·models·medium·     │     │  MVP-1a CLI (스크립트 0줄)   │
│  community_builder·graph·    │     │                              │
│  profile·scenario·sweep_view │     │                              │
└──────────────┬──────────────┘     └──────────────┬──────────────┘
               │  (consume same boundary)           │
               └─────────────────┬──────────────────┘
                                 ▼
              ┌──────────────────────────────────────┐
              │   EngineService  (single facade)      │  ← 유일 진입점
              │   - community_solve / single_solve    │     (§4.1 위임 경계)
              │   - sandbox_preview / commit          │
              │   - sweep_run                         │
              └──────────────────┬───────────────────┘
                                 │ submit/cancel/retry job
                                 ▼
              ┌──────────────────────────────────────┐
              │   JobRunner (in-process, cancel/retry)│  ← Plan §7.2
              │   진행률·취소·non-blocking (NFR-Perf) │
              └──────────────────┬───────────────────┘
                                 ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  core/  (engine-agnostic, headless, mypy-strict)                │
  │  ┌───────────┐  ┌───────────┐  ┌──────────┐  ┌──────────────┐   │
  │  │ namespace │→ │  engine   │→ │   sign   │→ │     tidy     │   │
  │  │ (gate §4.8)  │ (orchestr.)  │ (§4.3·4.7)│ │ (계약 §4.6)  │   │
  │  └───────────┘  └─────┬─────┘  └──────────┘  └──────────────┘   │
  │  ┌─────────────┐ ┌────┴─────┐ ┌────────┐ ┌──────┐ ┌─────────┐   │
  │  │interactions │ │  delta   │ │sandbox │ │sweep │ │manifest │   │
  │  │(cross-feed· │ │(AN-DELTA)│ │  (G1)  │ │ (G4· │ │(run_hash│   │
  │  │ MIP/MRO)    │ │          │ │preview/│ │cache)│ │ 11구성) │   │
  │  └─────────────┘ └──────────┘ │ commit)│ └──────┘ └─────────┘   │
  │                               └────────┘                        │
  └───┬───────────────┬──────────────────┬───────────────┬─────────┘
      │ seam #1        │ seam #2          │ seam #3       │ seam #4
      ▼                ▼                  ▼               ▼
┌───────────┐  ┌────────────────┐  ┌───────────┐  ┌──────────────┐
│SolverBackend│ │ MICOM engine   │  │  Store     │  │ RenderClient │
│ gurobi/    │  │ wrapper        │  │ writer     │  │ (R subprocess│
│ highs/osqp │  │ (public API    │  │ tidy parquet  │ 격리, §9)    │
│ (LP/QP/MILP│  │  only, 단일    │  │ /sqlite/   │  │ SVG/TIFF     │
│ §2·SC-1·6) │  │  진입점 §4.1)  │  │ sweep.parquet │ figure_spec  │
└───────────┘  └────────┬───────┘  │ §4.6·§5    │  └──────────────┘
                        ▼          │ SC-4·8·9)  │
                  ┌──────────┐     └────────────┘
                  │  MICOM   │  (cooperative_tradeoff
                  │ (정확 pin)│   fluxes=True, pfba=...)
                  └──────────┘
```

> **seam 한정 원칙(Option C)**: 4개 seam만 인터페이스로 분리한다 — `SolverBackend`(SC-1·SC-6), `MICOM engine wrapper`(SC-5), `Store`(SC-4·SC-8·SC-9), `RenderClient`(출판 그림). namespace·sign·tidy·delta·interactions·manifest는 core 내부 직접 구현이다.

### 2.2 Data Flow

```
[SBML/JSON/MAT import]  (io/, file_format ∈ {SBML,JSON,MAT}, [FILE-FORMAT])
        │ MemberModel(+checksum #1) · Medium(+checksum #2)
        ▼
[namespace gate §4.8]  ── unresolved high-confidence? ──► BLOCKED
        │ (NamespaceGateResult.blocked=false)            (MICOM 미호출,
        │  decisions → run_hash #10                       sweep: status=failed
        ▼                                                 +diagnostic)
[MICOM cooperative_tradeoff(fluxes=True, pfba=...)]  (engine wrapper, §4.1)
        │ ① growth = OSQP (QP, member growth L2)
        │    μ_c ≥ f·μ_c*  (tradeoff f #6)
        ▼
[LP pFBA flux 재계산 §4.2]  (SolverBackend: Gurobi/HiGHS LP)
        │ growth/community constraint 고정 → LP pFBA/normalization
        │ LP 부재 시 → flux_report_status='QP-only approximate'
        ▼
[sign 정규화 §4.3·§4.7]  (단일 진입점, raw_flux → (ui_flux≥0, label))
        │ 환경 −10→(10,uptake) / +8→(8,secretion) ...
        ▼
[tidy 계약 §4.6]  (core/tidy/, schema_version 필드)
        │  nodes (member·environment_pool)
        │  edges (cross-feeding: m분비+ ∧ m′흡수−, weight=min(...))
        │  profile (community↔env net exchange + FVA range)
        ▼
[Store writer]  ──► viewer (graph·profile·delta, 단일 reader)
                ──► R export (RenderClient → SVG/TIFF, figure_spec)
                ──► sweep.parquet (commit run만; run_hash·status·diagnostic)
```

### 2.3 Dependencies

| Component | Depends-on | Purpose |
|-----------|-----------|---------|
| `gui/` (PySide6) | EngineService | presentation only — 계산은 facade 경유 job (Plan §7.3) |
| `cli/` | EngineService | headless 산출 진입점(MVP-1a·SC-7) |
| EngineService (facade) | JobRunner, `core/*` | 단일 진입점 — solve/sandbox/sweep 오케스트레이션 |
| JobRunner | (in-process threads/process) | cancel/retry·진행률·non-blocking (Plan §7.2·NFR-Perf) |
| `core/namespace/` | NamespaceDecision, gate 규칙 | solve 직전 hard gate (§4.8·SC-3) |
| `core/engine/` (orchestrator) | **MICOM engine wrapper (seam #2)**, namespace, SolverBackend | solve 흐름 조립 (gate→QP→LP→sign→tidy) |
| MICOM engine wrapper (seam #2) | MICOM (`micom==X.Y.Z`) | public API only 단일 진입점 (§4.1·SC-5) |
| `core/sign/` | (none — pure) | 단일 진입점 sign 정규화 (§4.3·§4.7·SC-2) |
| `core/tidy/` | pyarrow/pandas | tidy 계약 산출 (nodes/edges/profile, §4.6·SC-9) |
| `core/interactions/` | tidy edges, sign | cross-feeding 추출·CMIG-MIP/MRO·typing (§4.5) |
| `core/delta/` | EngineService, tidy | AN-DELTA add-member delta (§10) |
| `core/sandbox/` | EngineService, JobRunner | G1 preview/commit·debounced re-solve (§4.2·A11·SC-8) |
| `core/sweep/` | manifest(run_hash), **Store (seam #3)** | G4 캐시·실패 diagnostic (§5·A14·SC-4) |
| `core/manifest/` | checksum, NamespaceDecision, solver setting | RunManifest·run_hash 11구성요소 (§7·SC-1·4·6) |
| **SolverBackend (seam #1)** | gurobipy / highspy / osqp | LP/QP/MILP·golden 변형 swap (§2·SC-1·SC-6) |
| **Store (seam #3)** | pyarrow, sqlite | tidy parquet / sqlite meta / sweep.parquet (§4.6·§5·SC-4·8·9) |
| **RenderClient (seam #4)** | R subprocess (격리) | 출판 그림 SVG/TIFF·figure_spec (§9·NFR-License) |
| `io/` | cobrapy, pyarrow | SBML/JSON/MAT import·checksum·Parquet/YAML/SQLite (**pickle 금지**) |

### 2.4 Sequence Diagrams

#### (a) Community Solve — gate 차단/통과 + QP-only 분기

```
 GUI        EngineService    namespace      MICOM wrapper   SolverBackend   sign    Store
  │  solve(scenario)│            │               │              │           │       │
  ├────────────────►│            │               │              │           │       │
  │                 │ evaluate_gate(exchanges)    │              │           │       │
  │                 ├───────────►│               │              │           │       │
  │                 │            │ NamespaceGateResult           │           │       │
  │                 │◄───────────┤ (blocked? coverage% unresolved_high)      │       │
  │                 │            │               │              │           │       │
  │   ┌─── ALT [blocked = true  (unresolved high-confidence ≥1, §4.8)] ──────────┐  │
  │   │ ❌ BLOCKED: MICOM 미호출. resolution 요구. audit trail 기록.            │  │
  │   │ (sweep 맥락이면 status=failed + diagnostic; ok run 승격 금지 [Gate-선행])│  │
  │ ◄─┤ gate_blocked(unresolved_high)                                          │  │
  │   └──────────────────────────────────────────────────────────────────────┘  │
  │                 │            │               │              │           │       │
  │   ┌─── ELSE [blocked = false → pass/warn] ───────────────────────────────────┐│
  │   │             │ cooperative_tradeoff(fluxes=True, pfba=...)│            │    ││
  │   │             ├───────────────────────────►│              │            │    ││
  │   │             │            │   ① growth = OSQP (QP, μ_c≥f·μ_c*)         │    ││
  │   │             │            │               ├─────────────►│            │    ││
  │   │             │            │               │◄─ growth ────┤            │    ││
  │   │             │            │               │              │            │    ││
  │   │   ┌── ALT [flux_solver(LP) 존재] ──────────────────────────────────┐ │    ││
  │   │   │ ② LP pFBA flux 재계산 (constraint 고정 → Gurobi/HiGHS LP §4.2) │ │    ││
  │   │   │         │            │               ├─────────────►│ flux(LP)  │ │    ││
  │   │   │         │            │               │◄─────────────┤ status=full│ │    ││
  │   │   ├── ELSE [LP 부재] ───────────────────────────────────────────────┤ │    ││
  │   │   │ flux_report_status = 'QP-only approximate' (§4.2·§4.4)          │ │    ││
  │   │   └─────────────────────────────────────────────────────────────────┘ │    ││
  │   │             │   raw_flux → (ui_flux≥0, label)  단일 진입점 §4.7       │    ││
  │   │             ├──────────────────────────────────────────►│           │    ││
  │   │             │   tidy(nodes/edges/profile) + schema_version            │    ││
  │   │             ├────────────────────────────────────────────────────────►│   ││
  │   │ ◄───────────┤ result(tidy, growth, flux_report_status)                │   ││
  │   └───────────────────────────────────────────────────────────────────────┘    ││
  └──────────────────────────────────────────────────────────────────────────────────┘
```

#### (b) Sandbox preview → commit (G1) — preview 비오염 + 승격

```
 GUI          EngineService    sandbox       JobRunner    MICOM/Solver    Store
  │ bound drag (constraint, source=sandbox)   │             │             │
  ├──────────────►│             │             │             │             │
  │               │ preview_resolve(debounced) │             │             │
  │               ├────────────►│ submit(cancel 이전 pending) │             │
  │               │             ├────────────►│ re-solve (§4.2 tradeoff)   │
  │               │             │             ├────────────►│             │
  │               │             │             │◄── flux ────┤             │
  │               │             │   ┌── ALT [보상 우회 → 변화 미미] ──────┐│
  │               │             │   │ FVA 범위 계산 + 'no significant      ││
  │               │             │   │  change' 진단 (§10·§11)             ││
  │               │             │   └──────────────────────────────────────┘│
  │ ◄─────────────┤ preview result + delta overlay (baseline vs constrained)│
  │   ⚠ STATE=preview → store/cache/sweep 비기록 [PREVIEW-NOWRITE] (NO WRITE)│
  │               │             │             │             │             │
  │ [Apply/Save]  │             │             │             │             │
  ├──────────────►│ commit(scenario)          │             │             │
  │               ├────────────►│ promote: state preview→commit            │
  │               │             │ run_hash 산출 (11구성요소, [RUNHASH-COMMIT])│
  │               │             │  bounds(#5)=sandbox constraint 반영       │
  │               │             ├──────────────────────────────────────────►│
  │               │             │  Scenario/Run artifact 기록 (commit only) │
  │ ◄─────────────┤ committed(run_hash)                                     │
```

#### (c) Sweep run_hash 캐시 (G4) — hit/miss + 실패 diagnostic

```
 GUI       EngineService    sweep        manifest        MICOM/Solver    Store(sweep.parquet)
  │ sweep_run(axes × 값)  │              │                  │               │
  ├──────────────────────►│              │                  │               │
  │              │ for each condition (axis 값 조합):        │               │
  │              │  build condition_id  │                  │               │
  │              │  compute run_hash ───►│ run_hash(11구성요소, float round) │
  │              │              │◄───────┤ (§4.2·A14)        │               │
  │              │  cache lookup(run_hash) ─────────────────────────────────►│
  │              │              │        │                  │   exists?     │
  │              │   ┌── ALT [HIT: 동일 run_hash 존재] ──────────────────────┐│
  │              │   │ 재계산 회피 → 기존 행 재사용 (SC-4). hit 표시.        ││
  │              │   └──────────────────────────────────────────────────────┘│
  │              │   ┌── ELSE [MISS] ───────────────────────────────────────┐│
  │              │   │ gate → MICOM solve → sign → tidy                      ││
  │              │   │   ┌── ALT [solve ok] ──────────────────────────────┐ ││
  │              │   │   │ append(condition_id, metric, value,            │ ││
  │              │   │   │   run_hash, status=ok, diagnostic=null) ───────►│ ││
  │              │   │   ├── ELSE [infeasible/solver err / gate blocked] ──┤ ││
  │              │   │   │ append(... status=failed, value=null,          │ ││
  │              │   │   │   diagnostic≠null)  실패 누락 금지 [STATUS-CLOSED]│ ││
  │              │   │   └─────────────────────────────────────────────────┘ ││
  │              │   └──────────────────────────────────────────────────────┘│
  │              │  RunManifest.sweep.n_runs = Π(축별 n_values) = len(run_hash)│
  │ ◄────────────┤ sweep complete (hit/miss 통계, 실패 condition 목록)        │
```

> **불변식 교차참조**: (a) [GATE-BLOCK]·[SOLVER-SPLIT]·[SIGN-2] (schema §8.6·§8.1) / (b) [STATE-DEFAULT]·[PREVIEW-NOWRITE]·[RUNHASH-COMMIT] (schema §8.5) / (c) [HASH-DETERMINISM]·[CONDITION-CONSISTENCY]·[STATUS-CLOSED] (schema §8.4·§8.3·§8.6) + sweep manifest 정합(schema §6.2).

---

I have everything needed. Writing the Data Model section.

## 3. Data Model

> **권위 자료 참조 (authoritative reference)**: 본 절은 `docs/01-plan/schema.md` 와 `docs/01-plan/glossary.md` 를 **단일 권위(single authoritative source)** 로 참조한다. 필드 표·타입·nullable·단위·전체 불변식은 schema.md 의 §2~§8 에 정식화되어 있으므로 **여기서 재정의(중복)하지 않고**, ① Option C(Pragmatic) 아키텍처가 이 데이터 모델을 어떻게 소비·생산하는지의 **설계 관점(design view)**, ② 엔티티 간 관계(relationship), ③ 설계 수준에서 추가되는 **in-memory 표현(ephemeral)** 을 고정한다. spec 미명시 값은 `(Design에서 확정)` + Open Decision 번호(OD-n)로 표기한다.

### 3.1 엔티티 개요 (Entity Overview)

데이터 모델은 **3개 계층(layer)** 으로 구분된다 — (A) **도메인 입력 엔티티**(사용자가 import·구성), (B) **tidy 단일 출력 계약**(모든 소비자의 유일한 reader 경유 산출), (C) **재현성·집계 레코드**(run_hash 11·manifest·sweep store). Option C 의 layered `core/` 와 단일 `EngineService` facade 는 (A)→solve(MICOM 위임)→(B)+(C) 의 단방향 흐름을 강제하며, 모든 writer 는 thin seam `Store` 인터페이스(tidy parquet / sqlite / sweep.parquet — SC-4·SC-8)를 경유한다.

| # | 엔티티 (entity) | 계층 | 역할 (Option C 소비자/생산자) | 권위 정의 |
|---|----------------|------|------------------------------|-----------|
| E1 | **MemberModel** | A 입력 | 단일 미생물 GEM 멤버. namespace gate·sign 정규화의 대상. community 조립 기본 단위. `id` 멤버셋 내 유일. | schema §3.1 |
| E2 | **Medium** | A 입력 | 배지(외부 exchange 가용성). minimal medium=cardinality MILP(capability gate). solve 전 §4.8 gate 대상. | schema §3.2 |
| E3 | **Scenario** | A 입력 | 재현 가능한 실행 단위 = medium+constraints+member_set+config. **preview/commit** 상태 보유. commit 시 `run_hash` 산출. | schema §3.3 |
| E4 | **CommunityModel** | A 조립 | MICOM `cooperative_tradeoff` solve 입력 객체. `engine` wrapper(SC-5)가 소비하는 유일 입력. `namespace_gate_status` 보유. | schema §3.4 |
| — | **HostModel** | — | **PART II (§12 G2) — 범위 외**. Baseline 엔티티 계약엔 stub 만 포함. | schema §3.5 |
| E5 | **tidy 5계약** | B 출력 | `nodes / edges / profile / matrix / timecourse` (parquet). **단일 reader** 경유(SC-9). `timecourse`=PART II placeholder(비산출). golden 회귀=nodes/edges/profile 3종. | schema §2 |
| E6 | **RunManifest** | C 재현 | 단일 solve/sweep run 의 완전한 재현 메타(inputs·engine·solver·algorithms·sweep·software·figure_specs·platform). 메타=YAML+SQLite. | schema §4.1 |
| E7 | **run_hash (11)** | C 재현 | **정확히 11개 구성요소**의 정규화 hash. solve 동일성 식별자 + AN-SWEEP 캐시 키(SC-4). 세 곳(Scenario/Manifest/Store)에서 비트 단위 일치. | schema §4.2·glossary §3 |
| E8 | **AggregationStore** | C 집계 | `sweep.parquet` long-format. §4.6 tidy 5종이 아닌 **§5 스토어 규약**(carve-out). 성공·실패 run 모두 기록. | schema §6 |
| E9 | **NamespaceDecision** | C 감사 | exchange 매핑 결정 1건의 audit 레코드. gate 입력 + run_hash #10 의 원소. 자동병합 금지. | schema §7.1 |

> **설계 결정 (Option C 소유 경계)**: MICOM 은 E4→solve 만 위임받고(`is_cmig_owned=false`), E5(tidy)·E6~E9(재현/집계/감사)는 모두 **CMIG core 소유**다. `engine` wrapper 는 documented flux only(`cooperative_tradeoff(fluxes=True, pfba=...)`)로 단일 진입하며, OSQP(QP growth)→LP(Gurobi/HiGHS) pFBA flux 재계산(§4.2·SC-6) 결과를 sign 단일 진입점(§4.7)을 거쳐 E5 로 tidy 화한다.

### 3.2 엔티티 관계 (Entity Relationships)

핵심 cardinality 와 데이터 흐름(input → solve → contract/store):

```
            ┌──────────────────────────────────────────────────────────────────┐
   INPUT    │                                                                    │
 (layer A)  │   MemberModel ───N──┐                                              │
            │     · id (unique)   │  (member_set: list<MemberModel.id>)          │
            │     · source.       │                                              │
            │       checksum #1 ──┼──┐                       Medium ──1───┐      │
            │                     │  │                         · checksum #2     │
            │                     ▼  │                              │      │     │
            │                 Scenario ◄── medium_ref ──────────────┘      │     │
            │                   · state {preview|commit}  (default=preview)│     │
            │                   · member_set #3 · abundance_ovr #4         │     │
            │                   · constraints #5 (source:{user_edit,sandbox})    │
            │                   · config{tradeoff_f #6, solver #7, norm #11}     │
            │                   · namespace_mapping_decisions #10 ◄─┐     │      │
            │                        │                              │     │      │
            └────────────────────────┼──────────────────────────────┼─────┼──────┘
                                     │ (assemble: N members 1 medium)│     │
                                     ▼                               │     │
            ┌─────────────────── CommunityModel ──1── micom_version #8│     │
            │   · members[{member_id, abundance(normalized Σ=1.0)}]   │     │
            │   · namespace_gate_status {passed|blocked|warning} ─────┘     │
            │            │                                                  │
            │   [§4.8 GATE]  blocked ⇒ NO MICOM solve ────────────────┐    │
            │            │ passed/warning                              │    │
            │            ▼                                             │    │
            │   MICOM cooperative_tradeoff (engine wrapper, SC-5)      │    │
            │   QP growth(OSQP) → LP pFBA flux(Gurobi/HiGHS, SC-6)     │    │
            └────────────┬────────────────────────────────────────────┼────┘
                         │ (sign single entry §4.7)                    │
         ┌───────────────┼─────────────────────────────┐              │
  OUTPUT │               ▼                              ▼              │
(layer B)│   tidy E5: nodes·edges·profile·matrix   RunManifest (E6)   │
         │   (·timecourse = PART II placeholder)        │             │
         │        │  (SINGLE reader, SC-9)               │ cmig_core   │
         └────────┼──────────────────────────────────────┼ _version #9 │
                  │                                       ▼             │
   COMMIT only    │              run_hash (E7, 11 components) ◄─────────┘
  (preview ✗)     │                   │  (#1..#11 normalized hash)
                  │   ┌───────────────┼──────────────────────────────┐
 (layer C)        ▼   ▼               ▼                              ▼
        AggregationStore (E8)   Scenario.run_hash         RunManifest.run_hash
        sweep.parquet           ───── HASH-SINGLE: 비트 단위 일치 ─────
          · 1 condition_id ──N── rows(metric,value)
          · status{ok|failed}, diagnostic(failed≠null)
          · run_hash (cache key) ──hit/miss──> SC-4
                  ▲
                  │ axes(6): {medium variant·abundance·member set·bounds·tradeoff f·solver}
            AN-SWEEP (Π n_values = n_runs = len(run_hash 목록))
```

**관계 요약 (cardinality)**:

| 관계 | cardinality | 제약/불변식 | 앵커 |
|------|-------------|-------------|------|
| MemberModel — Scenario.member_set | N — 1 | `member_set` ⊆ 존재하는 `MemberModel.id` (REF-INTEGRITY). `id` 유일(ID-UNIQUE). | schema §8.3 |
| Medium — Scenario | 1 — N | `medium_ref` = `Medium.id` 또는 임베드. uptake=음수 lower_bound(MEDIUM-SIGN). | schema §3.2·§8.1 |
| MemberModel + Medium — CommunityModel | N+1 — 1 | abundance 해소(`overrides`>`MemberModel`)·정규화 후 Σ=1.0(ABUND-NORM). | schema §3.4·§8.2 |
| Scenario — run_hash | 1 — 0..1 | **commit 에서만** 산출. preview=null/ephemeral(RUNHASH-COMMIT). | schema §8.5 |
| CommunityModel — MICOM solve | 1 — 1 | `gate_status=blocked` ⇒ solve 미호출(GATE-BLOCK). passed/warning 만 진입. | schema §7.3·§8.6 |
| solve — tidy 5계약 | 1 — 1 | 단일 reader 경유(SC-9). nodes/edges/profile/matrix 산출, timecourse placeholder. | schema §2 |
| run_hash — AggregationStore row | 1 — N | 동일 `condition_id` 행 전체가 동일 run_hash 공유(CONDITION-CONSISTENCY). 캐시 키. | schema §6.2·§8.3 |
| sweep axes — condition_id | 6축 — N | `n_runs = Π(축별 n_values) = len(run_hash)`. 폐쇄 enum 6축. | schema §6.2 |
| NamespaceDecision — run_hash #10 | N — 1 | 결정 집합이 run_hash 구성요소 #10. gate 입력이자 audit trail. | schema §7.1·§4.2 |
| RunManifest ≡ run_hash ≡ Scenario.run_hash | 1 ≡ 1 ≡ 1 | 동일 11구성요소·동일 직렬화·동일 해시 → 비트 단위 일치(HASH-SINGLE). | schema §8.4 |

### 3.3 핵심 불변식 요약 (Core Invariants — design enforcement)

schema §8 의 전체 불변식 목록을 권위로 하되, Option C 아키텍처가 **어디서 강제하는지(enforcement point)** 를 설계 관점으로 고정한다. 충돌 시 schema.md·`CMIG_명세서_v3.0.md` 우선.

| 불변식 | 내용 (요약) | Option C 강제 지점 | 앵커 |
|--------|-------------|---------------------|------|
| **부호 단일 진입** | `+`=분비/`−`=흡수. 모든 `raw_flux→(ui_flux≥0, label)` 변환은 sign 단일 진입점만 경유. canonical −10→(10,uptake). | `core/sign/` 단일 모듈, 우회 금지. SC-2 sign-test CI. | SIGN-1~4·schema §8.1 |
| **cross-feeding** | edge m→m′ ⟺ (m 분비>0)∧(m′ 흡수<0). weight=min(\|분비\|,\|흡수\|)≥0. | `core/interactions/` → tidy `edges` 산출. | CROSS-FEED·schema §8.1 |
| **abundance 정규화** | normalize 시 Σ=1.0. 우선순위 overrides>선언. | `core/engine/` 조립 시 해소→정규화 후 run_hash #4. | ABUND-NORM/PRIORITY·schema §8.2 |
| **run_hash 11 완전성** | 정확히 11구성요소(가감 금지). 1개 변경→miss·재계산. env_lock 미포함. | `core/manifest/` 단일 canonical serializer. SC-4. FR-2.8 Critical. | HASH-11/ENVLOCK·schema §8.4 |
| **run_hash 단일 정의** | Store=Manifest=Scenario run_hash 비트 단위 일치. | 세 writer 가 동일 serializer 호출(`Store` seam). | HASH-SINGLE·schema §8.4 |
| **float rounding** | float 구성요소는 hash 전 rounding/tolerance(예 6 decimal) 적용. | golden 비교·hash 공통 정규화 함수. SC-1·SC-6. | HASH-FLOAT·schema §8.4 |
| **preview 비오염** | preview solve 는 store/cache/sweep 비기록. commit 승격은 오직 Apply/Save. | `core/sandbox/` preview 경로는 `Store` writer 미호출. SC-8. | PREVIEW-NOWRITE·schema §8.5 |
| **state 기본 preview** | `Scenario.state` 기본=preview. run_hash 는 commit 에서만 영구. | EngineService facade 가 state 분기. | STATE-DEFAULT·RUNHASH-COMMIT·schema §8.5 |
| **gate 선행·차단** | unresolved high-confidence 1건 ⇒ blocked ⇒ MICOM 미호출. low=warn(자동병합 금지·audit). 차단 condition 은 sweep 에 `status=failed`+diagnostic 만 기록. | `core/namespace/` gate 가 `engine` wrapper 앞단. SC-3. | GATE-BLOCK·schema §7.3·§8.6 |
| **tidy 단일 reader** | 전 소비자(graph·profile·delta·sweep·R)가 단일 reader 경유. schema_version 필드 보유. | `core/tidy/` 단일 reader/계약 테스트. SC-9. | schema §1.3·§2 |
| **solver split** | growth=QP(OSQP)→flux=LP 재계산. LP 부재 시 'QP-only approximate'. | `SolverBackend` seam(gurobi 기본/highs/osqp). SC-1·SC-6. | SOLVER-SPLIT·schema §8.6 |
| **no-pickle / file-format** | pickle 금지. 직렬화=Parquet/Arrow/JSON/YAML/SQLite. TSV=golden 전용. `file_format∈{SBML,JSON,MAT}`. | `Store` writer 가 허용 포맷만 산출. | NO-PICKLE/FILE-FORMAT·schema §8.6 |
| **status 폐쇄·실패 보존** | `status∈{ok,failed}`. failed→diagnostic≠null·value 결측. 실패 run 누락 금지. | `core/sweep/` 가 실패도 row append. SC-4. | STATUS-CLOSED·schema §8.6 |
| **MICOM exact pin** | `micom==X.Y.Z`. 버전 상향은 solver별 golden 전부 통과 시에만 승격. | `engine` wrapper 버전 고정 + golden 승격 게이트. SC-5. | MICOM-PIN·schema §8.6 |

### 3.4 설계 수준 in-memory 표현 (Design-level In-Memory Representations)

schema 의 영속(persisted) 엔티티 외에, Option C 구현이 요구하는 **비영속(ephemeral) in-memory 표현**을 명시한다. 이들은 `core/` 헤드리스 계층에 존재하며 `Store` writer 를 거치지 않는다(= 영속 계약과 분리).

| 표현 | 성격 | 설계 의미 | 앵커 / OD |
|------|------|-----------|-----------|
| **ephemeral preview Scenario** | in-memory only(또는 temp) | G1 sandbox bound-drag 의 `state=preview` Scenario. `run_hash=null/ephemeral`, store/cache/sweep 미기록. debounced 재solve(§4.2)의 입력. Apply/Save 시에만 commit Scenario 로 승격되어 영속·run_hash 산출. **저장 위치/수명(in-memory only vs temp file)은 OD-9**. | schema §8.5·glossary 1.C / OD-9 |
| **preview vs baseline delta (in-memory)** | 휘발 결과 | sandbox 의 baseline external-profile vs constrained external-profile 차이. tidy `profile` 형식을 재사용하되 **영속 산출 아님**(preview 비오염). 보상 우회 미미 시 FVA 범위·`no significant change` 진단(판정 임계 OD-53). | schema §8.5·glossary AN-SANDBOX / OD-53 |
| **NamespaceGateResult** | solve 직전 평가 객체 | `{blocked, coverage_pct, unresolved_high, warned_low, decisions}`. gate 평가의 in-memory 산출이며, commit 시 `decisions` 만 run_hash #10·audit trail 로 영속. `audit_trail_ref` 매체는 OD-41. coverage% 분모는 OD-40. | schema §7.2 / OD-40·OD-41 |
| **assembled CommunityModel (transient)** | solve 입력 객체 | abundance 해소·정규화·gate 평가를 마친 MICOM solve 직전 객체. 영속 엔티티라기보다 `engine` wrapper 로 넘기는 transient 조립체(영속은 Scenario+Manifest 가 담당). | schema §3.4 |
| **JobRunner job context** | in-process 작업 상태 | sweep N-run / sandbox 재solve 의 cancel/retry 상태·진행률. 영속 산출은 AggregationStore row(성공·실패 모두)이며, job context 자체는 비영속. | plan §7.3·SC-4 |
| **tidy contract DTO (single reader 출력)** | 인메모리 DataFrame | 모든 소비자(graph/profile/delta/R)가 받는 단일 reader 의 in-memory 표현(pyarrow/pandas). 영속 parquet 과 동일 schema_version 계약. RenderClient(R subprocess)에는 격리 전달. | plan §6.3·SC-9 |

> **설계 원칙 (ephemeral 분리)**: preview 경로의 모든 in-memory 표현은 `Store` seam 을 **호출하지 않는 것**으로 SC-8(preview 비오염)을 구조적으로 보장한다 — 즉 "기록 안 함"을 정책이 아니라 **코드 경로 분리**로 강제한다(preview 경로엔 writer 의존성 자체가 없음). commit(Apply/Save)만이 `Store` writer→run_hash→AggregationStore 진입을 트리거한다(schema §8.5·plan §7.3).

---

## 4. Engine Interface API (EngineService + Seam 인터페이스)

> **위치 (positioning)**: 본 절은 **웹 REST API가 아니라** in-process Python 서비스 API다 (Plan §7.2 `in-process sidecar(우선) + job runner`). CLI(`cmig/cli/`)와 GUI(`cmig/gui/`)는 **동일한 `EngineService` facade**를 소비하며(Plan §7.3), 경계는 추후 FastAPI/remote로 전환 가능하도록 형성하되 지금은 in-process다. 모든 계산은 GUI 바깥 job으로 위임된다(FR-0.2 `계산 GUI 밖 job, cancel/retry`).
>
> **불변 전제 (invariants this API enforces)**: ① 모든 `solve_*`는 namespace hard gate 통과 후에만 MICOM을 호출한다(schema [GATE-BLOCK]·[Gate-순서] §7.3·§4.8). ② growth=QP(OSQP) → flux=LP(Gurobi/HiGHS) pFBA 재계산(§4.2·schema [SOLVER-SPLIT]). ③ 모든 산출은 tidy 단일 계약(`nodes/edges/profile/matrix/timecourse` parquet, §4.6·schema §2). ④ `run_hash`는 manifest 모듈이 **정확히 11개 구성요소**로 산출한다(schema §4.2·glossary §3). ⑤ preview는 Store에 기록하지 않는다(schema [PREVIEW-NOWRITE] §8.5·A11·SC-8). ⑥ pickle 금지(schema [NO-PICKLE] §8.6).

### 4.1 EngineService Facade 메서드 표

`EngineService`는 `core/` 레이어드 모듈(engine·namespace·sign·tidy·interactions·delta·sandbox·sweep·manifest)을 단일 진입점으로 묶는 **facade**다(Option C / Plan §7.3). 장기 메서드는 `JobRunner`(§4.4)를 통해 비동기 job handle을 반환하고, 짧은 메서드는 동기 결과를 반환한다.

> **표기**: 입력/출력 타입은 schema §3 도메인 엔티티·§2 tidy 계약을 참조한다. `TidyBundle` = `{nodes, edges, profile, matrix?}` parquet 산출 묶음(§4.6). `(D)` = 동기, `(J)` = JobRunner job handle.

| 메서드 | 입력 | 출력 (tidy 산출) | 주요 예외 | SC 연결 |
|--------|------|------------------|-----------|---------|
| `import_model(path, file_format)` `(D)` | `file_path` (절대경로), `file_format ∈ {SBML, JSON, MAT}` (schema [FILE-FORMAT] §3.1) | `MemberModel` (`source.checksum` 산출 = run_hash #1 §4.2; `stats`·`exchange_compartment`) | `UnsupportedFormatError`(pickle 등 비허용 [NO-PICKLE]), `ModelParseError`, `FileNotFoundError` | — (Foundation, FR-0.3) |
| `check_growth(member_model, medium)` `(D)` | `MemberModel`, `Medium` | growth feasibility(μ, status) — `profile` 요약 | `InfeasibleError`(diagnostic 포함 §4.4), `MediumNamespaceMismatch` | — (FR-0.4·FR-0.5) |
| `solve_single(member_model, medium, mode, config)` `(D\|J)` | `mode ∈ {FBA, pFBA, FVA}`, knockout/bound 편집, `Scenario.config` | `TidyBundle`(`nodes`+`profile`; FVA는 `profile.fva_min/fva_max` schema §2.3) | `InfeasibleError`, `CapabilityUnavailableError`(LP/QP 부재 §5.3) | SC-9(tidy 계약) |
| `solve_community(scenario)` `(J)` | `Scenario`(member_set·medium·config·tradeoff_f) → `CommunityModel` 조립 | `TidyBundle`(`nodes`+`edges` cross-feeding+`profile` external) + `RunManifest`·`run_hash`(commit 시) | `NamespaceGateBlocked`(unresolved high-conf §4.8), `InfeasibleError`, `MicomVersionMismatch` | SC-1·SC-2·SC-3·SC-6·SC-9 |
| `add_member_delta(baseline_scenario, new_member_id)` `(J)` | baseline `Scenario`(복제) + 추가 멤버 id; **동일 조건 고정** (Plan FR-2.1) | `TidyBundle` ×2 (baseline·constrained) + delta `edges`/`matrix`(delta network·heatmap 입력) | `NamespaceGateBlocked`, `RefIntegrityError`(member_id 미존재 [REF-INTEGRITY] §8.3) | SC-9 |
| `run_sandbox_preview(scenario, bound_constraints)` `(J)` | `Scenario` + `constraints[]`(`source=sandbox`, schema §3.3) — **bound 제약 변경(flux 직접편집 아님, A11)** | `TidyBundle`(constrained) + baseline-vs-constrained external-profile delta + FVA/`no significant change` 진단 — **Store 비기록(ephemeral)** | `InfeasibleError`(diagnostic), `CompensationBypass`(FVA 범위 보고) | **SC-8** (preview 비오염) |
| `commit_sandbox(preview_handle)` `(D)` | preview job handle / preview `Scenario` | `Scenario(state=commit)` + `run_hash` 영구 산출 + Store 기록(승격) | `NotPreviewError`, `StoreWriteError` | **SC-8** (Apply/Save 승격만) |
| `run_sweep(sweep_spec)` `(J)` | `axes ⊆ {medium variant·abundance·member set·bounds·tradeoff f·solver}`(폐쇄 6종 schema §6.2) × 값 | `AggregationStore` append (`sweep.parquet` long-format; `condition_id·metric·value·run_hash·status·diagnostic`) | per-condition `status=failed`+diagnostic (**누락 금지**, job은 실패 run에도 계속) | **SC-4** (run_hash 캐시·실패 diagnostic) |
| `export_figure(figure_spec, tidy_source)` `(J)` | `FigureSpec`(seed 포함 §7) + tidy 산출 | SVG(svglite)/TIFF(ragg 600dpi LZW) (Plan FR-2.5) | `RenderTimeoutError`(R subprocess), `RenderClientError` → Python fallback | — (재현: figure_spec §7) |

**facade 계약 노트**:
- `import_model`은 `file_format` 폐쇄 enum만 허용하고 pickle 경로를 거부한다(schema [FILE-FORMAT]·[NO-PICKLE]). `source.checksum`은 commit 시 run_hash #1로 진입한다(§4.2).
- `solve_*` 계열은 모두 §4.3 계약(gate→MICOM, QP→LP, tidy)을 공유하며, `solve_community`/`add_member_delta`/`run_sandbox_preview`/`run_sweep`는 community solve이므로 **namespace gate가 선행조건**이다(glossary §1.B).
- `run_sandbox_preview` ↔ `commit_sandbox`는 preview/commit 이원화(§8.5·glossary §1.C)를 facade 수준에서 강제한다 — preview는 `Store.write_*`를 호출하지 않는다.

### 4.2 Seam 인터페이스 (Python Protocol/ABC 시그니처)

> **원칙 (Option C / Plan §7.3)**: thin seam 인터페이스는 **SC가 요구하는 외부 의존 경계에만** 둔다. **4개 seam(외부 의존 adapter)** = `SolverBackend`(SC-1·SC-6) · `EngineWrapper`(SC-5, MICOM public API only) · `Store`(SC-4·SC-8) · `RenderClient`(출판 그림). 모두 `core/`가 의존하는 외부 구현 추상이며 교체(solver swap·remote 전환)를 허용한다. **`NamespaceGate`는 외부 의존이 아닌 순수 도메인 로직이므로 seam이 아니라 `core/namespace/`의 내부 인터페이스**다(§9.4 Domain 배정). Protocol로 정의하는 이유는 테스트 더블·gate fixture 주입(SC-3) 편의일 뿐, adapter 교체 지점이 아니다.

```python
from __future__ import annotations
from typing import Protocol, Literal, Optional, runtime_checkable
from dataclasses import dataclass

# ── 공용 타입 (schema §2·§3·§4 참조) ──────────────────────────────
ProblemClass = Literal["LP", "QP", "MILP"]          # schema §5.1
SolverName   = Literal["gurobi", "highs", "osqp", "cplex"]   # schema §5.2 (glpk=GPL 미번들)
FluxReportStatus = Literal["full", "qp_only_approximate"]    # 직렬화 canonical 값 (OD-19). UI 표시 라벨 = "QP-only approximate". 'qp_only_approximate'만 spec 의미 명시 §4.2

@dataclass(frozen=True)
class SolveResult:
    objective: float
    fluxes: Optional["pa.Table"]          # pFBA 정규화 flux (LP); QP-only면 None
    status: Literal["optimal", "infeasible", "unbounded"]
    flux_report_status: FluxReportStatus  # LP 부재 시 'qp_only_approximate' (직렬화 값; UI 라벨 "QP-only approximate") (§4.2·§4.4)
    diagnostic: Optional[str] = None       # infeasible/capability 강등 (§4.4)

@dataclass(frozen=True)
class NamespaceGateResult:                 # schema §7.2
    blocked: bool                          # unresolved high-conf ≥1 → True → MICOM 호출 금지
    coverage_pct: float                    # 0–100 (분모 정의 Design 확정 OD-40)
    unresolved_high: list[str]
    warned_low: list[str]
    decisions: list["NamespaceDecision"]   # run_hash #10 원천 (§4.8)
    audit_trail_ref: Optional[str] = None

# ── Seam 1: SolverBackend — capability 보고 + solver selection ──
#    SC-1(golden by solver)·SC-6(OSQP→LP). (Check G-1 동기화: 2026-05-31)
#    실제 community solve·pFBA·OSQP(QP)→LP 재계산은 MICOM(optlang)이 내부 수행한다.
#    CMIG 는 cmig solver 이름을 MICOM optlang solver 로 매핑(SOLVER_MAP)하여 선택만 한다:
#      gurobi→"gurobi" · osqp→"osqp" · osqp_growth_highs_flux→"hybrid"(OSQP-QP+HiGHS-LP).
#    따라서 이 seam 은 solve_lp/solve_qp 를 노출하지 않는다 — solver 교체(golden 변형·
#    OSQP→LP swap)는 optlang solver 이름 선택으로 실현된다.
@runtime_checkable
class SolverBackend(Protocol):
    """solver capability 보고 + selection 추상. gurobi 기본 / highs / osqp.
    golden 변형 osqp_growth_highs_flux = MICOM hybrid(QP=osqp→LP=highs) (schema §5.3)."""
    name: SolverName

    def capability(self) -> SolverCapability:
        """지원 problem_class(LP/QP/MILP)·가용성. 부재 class는 해당 분석만 비활성화
        (disable_analysis_on_missing=true, schema §5.3)."""
        ...

# ── Seam 2: EngineWrapper — SC-5 (MICOM public API only, 단일 진입점) ─
@runtime_checkable
class EngineWrapper(Protocol):
    """MICOM community FBA 위임. public API + documented flux only —
    internal 접근 금지. 단일 진입점(core/engine/) (Plan §7.3·§4.1)."""
    micom_version: str                     # exact pin micom==X.Y.Z → run_hash #8

    def cooperative_tradeoff(
        self, community_model, *, tradeoff_f: float,
        fluxes: bool = True, pfba: bool = True,
    ) -> SolveResult:
        """MICOM cooperative_tradeoff(fluxes=True, pfba=...) 정확 래핑.
        0 < tradeoff_f ≤ 1 (μ_c ≥ f·μ_c*) (§4.2·schema [TRADEOFF-RANGE])."""
        ...

# ── Seam 3: Store — SC-4(run_hash 캐시)·SC-8(preview 비기록) ──────
@runtime_checkable
class Store(Protocol):
    """tidy parquet / sqlite meta / sweep.parquet writer-reader.
    Parquet/Arrow/SQLite/YAML만 — pickle 금지 (schema [NO-PICKLE] §8.6)."""

    def write_tidy(self, bundle, *, run_hash: str) -> None:
        """nodes/edges/profile/matrix parquet 기록 (commit 전용)."""
        ...

    def read_tidy(self, run_hash: str) -> Optional["TidyBundle"]:
        """단일 reader (전 소비자 경유, schema §1.3·§2)."""
        ...

    def write_sweep(self, rows, *, run_hash: str, status: Literal["ok", "failed"]) -> None:
        """sweep.parquet long-format append. status=failed면 diagnostic 필수
        (누락 금지, schema §6.1·[STATUS-CLOSED])."""
        ...

    def cache_lookup_by_run_hash(self, run_hash: str) -> Optional["SweepRows"]:
        """동일 run_hash 존재→hit(재계산 회피); 부재→miss·재solve (schema §6.2·SC-4)."""
        ...

# ── Seam 4: RenderClient — 출판 그림 (R subprocess 격리) ──────────
@runtime_checkable
class RenderClient(Protocol):
    """R Render Service 별도 프로세스 격리 (GPL 격리, Plan §7.2·NFR-License).
    figure_spec(seed) 재현; R 실패 시 Python fallback (FR-2.5)."""

    def render(self, figure_spec) -> bytes:
        """SVG(svglite)/TIFF(ragg 600dpi LZW) 바이트 산출."""
        ...

# ── core 내부 인터페이스 (seam 아님): NamespaceGate — SC-3 (gate 차단) ──
#    외부 의존 adapter가 아니라 core/namespace/ 순수 도메인 로직.
#    Protocol는 테스트 더블·gate fixture 주입용일 뿐 교체 지점 아님 (§9.4 Domain).
@runtime_checkable
class NamespaceGate(Protocol):
    """solve 직전 hard gate (§4.8). unresolved high-conf→차단,
    low→warn 진행(자동병합 금지)·audit (schema §7.3)."""

    def check(self, community_model) -> NamespaceGateResult:
        ...
```

> **seam 노트**: `SolverBackend`는 solver별 golden(SC-1)과 OSQP→LP swap(SC-6)을 가능케 하는 교체 지점이다 — golden 변형 `osqp_growth_highs_flux`는 `capability()`가 QP만 보고하는 osqp 백엔드 + LP=highs 조합으로 실현된다(schema §5.3). `EngineWrapper`는 MICOM-version golden regression(SC-5)의 단일 격리점으로, `micom_version` pin 변경이 이 seam 한 곳에 국한된다(schema [MICOM-PIN] §8.6). `HiGHS-QP(experimental)` 노출 여부는 `(Design에서 확정, OD-24/OD-26)`.
>
> **역할별 solver enum (schema §5.1·§5.2와 1:1, capability 분기)**: `growth_solver ∈ {osqp, gurobi, cplex, highs}`(QP; OSQP 포함, **GLPK 제외**) · `flux_solver ∈ {gurobi, highs, cplex}`(LP; **OSQP·GLPK 제외**) · `milp_solver ∈ {gurobi, highs, cplex}`(minimal medium·cardinality MILP; **GLPK 제외**). 즉 `SolverName` 폐쇄 집합은 동일하되 **role마다 허용 부분집합이 다르다**(OSQP는 QP 전용 → flux_solver 불가, GLPK는 미번들 → 전 role 제외). 이 분기는 `SolverBackend.capability()`가 보고하며 OD-13 직렬화·OD-32 sweep 축 enum과 정합한다.

### 4.3 핵심 계약 (Core Contracts)

facade·seam을 관통하는 4대 불변 계약. 모든 `solve_*` 메서드 구현은 이 순서를 따른다.

1. **gate → MICOM 순서 (schema [Gate-순서]·[Gate-선행] §7.3·§4.8 · SC-3)**:
   모든 community `solve_*`는 `NamespaceGate.check()`를 먼저 호출한다. `result.blocked == True`(unresolved high-confidence ≥1)이면 **어떤 `EngineWrapper.cooperative_tradeoff` 호출도 실행하지 않고** `NamespaceGateBlocked` 예외를 던진다. low-confidence는 차단하지 않고 `warned`로 진행하되 **자동병합(auto-merge) 금지**·audit trail 기록(§4.8). sweep에서 차단된 condition은 정상 run으로 승격되지 않고 `status=failed`+diagnostic으로만 기록된다(schema §7.3 [Gate-선행]).

2. **growth=QP → flux=LP 재계산 (§4.2·schema [SOLVER-SPLIT] §8.6 · SC-6)**:
   **(Check G-1 동기화)** ① MICOM `cooperative_tradeoff(fraction=f, fluxes=True, pfba=True)`가 선택된 optlang solver로 member growth(QP) 확보 후 pFBA flux(LP)를 내부 수행한다. `osqp_growth_highs_flux`(=optlang `hybrid`)는 **OSQP-QP growth → HiGHS-LP flux 재계산**을 MICOM 내부에서 실현(SC-6). CMIG 는 `SolverBackend.capability()`로 가용성을 확인하고 `engine.SOLVER_MAP`으로 solver를 **선택**할 뿐, solve_lp/solve_qp를 직접 호출하지 않는다. LP flux 부재 시 `flux_report_status='qp_only_approximate'`(직렬화값; UI 라벨 "QP-only approximate"). growth_solver(QP)·flux_solver(LP)는 `RunManifest.solver`에 **분리 기록**(§7).

3. **산출 = tidy 단일 계약 (§4.6·schema §2 · SC-9)**:
   모든 `solve_*` 산출은 `core/tidy/`를 경유해 `nodes/edges/profile/matrix` parquet으로만 출력된다. `edges`는 §4.3 sign 규약·cross-feeding `weight=min(|m 분비|, |m′ 흡수|)`를 적용하고, 모든 `raw_flux → (ui_flux, label)` 변환은 `core/sign/` **단일 진입점**만 경유한다(schema [SIGN-2] §8.1). `timecourse`는 PART II placeholder로 baseline 미산출(schema §2.5).

4. **run_hash = manifest 모듈 11구성요소 (schema §4.2·glossary §3)**:
   `run_hash`는 `core/manifest/` 모듈이 **정확히 11개 구성요소**(model checksum·medium checksum·member set·abundance·bounds·tradeoff f·solver setting·micom_version·cmig_core_version·namespace_mapping_decisions·flux_normalization_method)를 canonical 직렬화·float rounding(예: 6 decimal) 후 정규화 hash하여 산출한다(schema [HASH-11]·[HASH-FLOAT] §8.4). `env_lock`은 **미포함**(manifest.inputs에만, [HASH-ENVLOCK]). `Store.cache_lookup_by_run_hash`의 hit/miss는 이 11구성요소 동일성으로 판정된다(SC-4). 동일 run_hash는 `AggregationStore.run_hash = RunManifest.run_hash = Scenario.run_hash`로 비트 단위 일치([HASH-SINGLE]). 해시 함수·canonical 직렬화 순서는 `(Design에서 확정, OD-11)`.

5. **preview 비기록 (schema [PREVIEW-NOWRITE] §8.5·A11 · SC-8)**:
   `run_sandbox_preview`는 `Store.write_tidy`/`write_sweep`를 **호출하지 않는다**(ephemeral). preview에서 `run_hash`는 null/ephemeral([RUNHASH-COMMIT])이며, Store 진입·run_hash 영구 산출은 오직 `commit_sandbox`(Apply/Save)에서만 발생한다.

### 4.4 JobRunner 계약 (비동기 실행)

`JobRunner`는 in-process 비동기 실행자로, 장기 `solve_*`/`run_sweep`/`export_figure`를 GUI 바깥 job으로 돌린다(FR-0.2·Plan §7.2 `in-process sidecar + job runner`). GUI는 job handle만 들고 non-blocking으로 진행률·취소를 수신한다(NFR Performance·Reliability).

```python
class JobStatus(Protocol):
    job_id: str
    # 작업 수명주기 enum — AggregationStore.status(ok/failed, schema §8.6 [STATUS-CLOSED])와 **별개 namespace**.
    state: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    progress: float                    # 0.0–1.0 (sweep: 완료 condition / 전체 n_runs)
    diagnostic: Optional[str]          # infeasible 원인·capability 강등·qp_only_approximate

class JobRunner(Protocol):
    def submit(self, callable, *args, **kwargs) -> str: ...   # → job_id
    def poll(self, job_id: str) -> JobStatus: ...
    def cancel(self, job_id: str) -> None: ...                # 협조적 취소
    def retry(self, job_id: str) -> str: ...                  # 실패 job 재제출
    def result(self, job_id: str): ...                        # 완료 시 산출 회수
```

**JobRunner 계약 항목**:
- **cancel/retry (FR-0.2·NFR Reliability)**: 모든 장기 job은 협조적 cancel·실패 retry를 지원한다. sandbox의 debounced re-solve는 in-flight job을 cancel하고 최신 입력으로 재제출한다(glossary `debounced re-solve`; debounce 지연·취소 정책 `Design에서 확정, OD-54`).
- **진행률 (progress)**: `run_sweep`는 `RunManifest.sweep.n_runs = Π(축별 n_values)` 대비 완료 condition 수로 progress를 산출한다(schema §6.2). 캐시 hit condition은 즉시 완료로 집계된다(SC-4).
- **infeasible/capability 강등 보고 (§4.4·schema §5.3)**: solve가 infeasible면 `state=failed`+`diagnostic`(원인)을 채운다. solver capability 부재는 **앱 전체 강등이 아니라 해당 분석만 비활성화**(`CapabilityUnavailableError` → `disable_analysis_on_missing`)하고, LP 부재 시 `QP-only approximate`로 강등 보고한다.
- **실패 누락 금지 (sweep, schema §6.1·[STATUS-CLOSED] · SC-4)**: `run_sweep`의 개별 condition이 실패해도 job은 중단되지 않고 `Store.write_sweep(status='failed', diagnostic=...)`로 반드시 기록한다(`diagnostic ≠ null` 강제). 실패 run diagnostic 누락은 0이어야 한다(SC-4).
- **두 status enum 구분 (namespace)**: `JobStatus.state`(작업 수명주기: queued/running/succeeded/failed/cancelled)와 `AggregationStore.status`(condition 결과: ok/failed, schema §8.6 [STATUS-CLOSED])는 **별개 namespace**다. 매핑: 한 sweep job 안의 각 condition이 개별 row로 `status=ok|failed`로 기록되며, job 전체 `state=failed`는 인프라/취소 등으로 job 자체가 중단된 경우다(개별 condition 실패는 job을 failed로 만들지 않고 row status=failed로만 남긴다).
- **GUI 생존 (NFR Reliability)**: job 실패가 GUI를 죽이지 않으며, 진단은 GUI runtime_jobs 패널로 표면화된다. 산출 I/O는 Parquet(메타 YAML+SQLite)이며 **pickle 금지**(schema [NO-PICKLE] §8.6).

> **경계 전환성 (Plan §7.2)**: `JobRunner`/`EngineService`는 현재 in-process지만, seam이 모두 Protocol로 추상화되어 있어 추후 FastAPI/remote(127.0.0.1 바인딩·토큰, NFR Security)로 job 실행 경계를 옮길 수 있도록 형성한다.

---

## 5. UI/UX Design (PySide6)

> **설계 근거 (design basis)**: 본 섹션은 Plan §7.2(PySide6+Cytoscape.js+QWebEngine·in-process sidecar 결정)·§7.3(folder structure `gui/`)·NFR(부호 범례 상시·한/영 토글, Plan §3.2 i18n)와 schema §2(tidy 계약)·§7(gate)·§8.5(preview 비오염)을 GUI presentation 계층으로 구체화한다. **GUI는 presentation only** — 모든 계산은 `EngineService` facade → in-process `JobRunner`(cancel/retry, Plan §7.2)를 경유하며, GUI는 tidy 계약(schema §2)·`NamespaceGateResult`(schema §7.2)·`AggregationStore`(schema §6)만 단일 reader로 소비한다(Plan §6.3). spec에 미명시된 위젯·표현은 `(Design에서 확정)`으로 표기한다.

---

### 5.1 Screen Layout (메인 셸)

3-pane 도킹 셸(dockable shell). 좌측 **Project Explorer**, 중앙 **View 영역**(탭/스택), 우측 **Inspector + Runtime&Jobs**. 상단에 메뉴/툴바·**한↔영 토글**·**command palette** 호출, 하단에 **상태바**(gate 상태·solver·job·**부호 범례 상시**). 부호 범례(`+`=분비/`−`=흡수)는 NFR(Plan §3.2·schema §8.1·glossary 2.8 "부호 범례 상시")에 따라 **상시 표시**한다.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ CMIG   File  Edit  Analysis  View  Tools  Help        [⌘K Command Palette]   [한|EN] [◐ Theme]│ ← 메뉴/툴바 + i18n 토글 + 고대비 테마
├──────────────────┬──────────────────────────────────────────────┬───────────────────────────┤
│ PROJECT EXPLORER │  CENTRAL VIEW  (tab stack)                     │  INSPECTOR                │
│ ───────────────  │  ┌───────────────────────────────────────────┐│  ───────────────          │
│ ▾ Project demo   │  │[Models][Medium][Community][Graph][Profile]││  선택 객체 속성/메타       │
│   ▾ Models       │  │[Compare][Sweep]                  ◀ tabs   ││  (node/edge/member/       │
│     • E. coli    │  ├───────────────────────────────────────────┤│   reaction 속성)          │
│     • B. theta   │  │                                           ││  · id / label / taxonomy  │
│     • F. prau    │  │     active View canvas                    ││  · growth μ / abundance   │
│   ▾ Media        │  │     (e.g. Interaction Graph: QWebEngine   ││  · flux(ui_flux,label)    │
│     • M9         │  │      + Cytoscape.js)                      ││  · run_hash(commit 시)    │
│   ▾ Scenarios    │  │                                           ││ ───────────────           │
│     • base(commit)│  │                                          ││  RUNTIME & JOBS           │
│     • s1(preview)│  │                                           ││  ▸ job#42 sweep 63% ⟳ ✕   │ ← 진행률 + cancel/retry
│   ▾ Runs/Sweeps  │  │                                           ││  ▸ job#41 solve ✅        │   (JobRunner, Plan §7.2)
│     • sweep_AxB   │  │                                          ││  ▸ job#40 import ✅       │
│                  │  └───────────────────────────────────────────┘│  solver: Gurobi(default)  │ ← schema §5.2
├──────────────────┴──────────────────────────────────────────────┴───────────────────────────┤
│ STATUS BAR:  Sign: + 분비/secretion  − 흡수/uptake │ Gate: ✅ passed (cov 98%) │ μ_c=0.83 │ ⟳ 1 job │ Gurobi LP+OSQP QP │
│              └──── 부호 범례 상시 (NFR) ─────────┘ └── schema §7.2 ──┘            └ §4.2 split ┘ │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Command Palette (⌘K / Ctrl+K)**: 액션 fuzzy 검색(예: "Run community solve", "Open gate", "Export figure", "Toggle EN"). 분석 모드 6종(glossary 2.2 AN-SINGLE/PAIR/COMMUNITY/DELTA/SANDBOX/SWEEP) 진입점 통합. 키 바인딩·등록 액션 카탈로그는 `(Design에서 확정)`.
- **i18n 토글 (한|EN)**: 모든 UI 문자열 즉시 전환. 단, **부호 label 'uptake/secretion'과 멤버↔pool '분비'**(schema §8.1 [SIGN-4]·glossary 1.A)는 데이터 계약상 enum이므로 표시 라벨만 i18n하고 값은 불변(OD-43 enum 통일 `Design에서 확정`).
- **상태바 상시 표시**: ① 부호 범례, ② 현 Community의 `namespace_gate_status`(schema §3.4·§7.2), ③ community growth μ_c, ④ 활성 job 수, ⑤ growth(QP)/flux(LP) split solver(schema §4.2·§5.2).

---

### 5.2 User Flow (import → export)

핵심 baseline 워크플로. **모든 solve는 §4.8 hard gate 통과 후에만 MICOM 호출**(schema §7.3 [Gate-순서]·glossary 1.B)이며, preview solve는 store/cache/sweep에 **비기록**(schema §8.5 [PREVIEW-NOWRITE]·SC-8)이다.

```
 ┌──────────┐   ┌─────────────────┐   ┌───────────────────┐
 │ 1.IMPORT │──▶│ 2.NAMESPACE     │──▶│ 3.COMMUNITY        │
 │ SBML/JSON│   │   STATUS         │   │   BUILDER           │
 │ /MAT     │   │ coverage% ·      │   │ members+abundance   │
 │ (§5 enum,│   │ unresolved 목록  │   │ +medium+objective   │
 │  NO pickle)  │ (schema §7.2)    │   │ +tradeoff f         │
 └──────────┘   └─────────────────┘   └─────────┬──────────┘
                       │                          │
                       │ unresolved high-conf?    ▼
                       │                ┌───────────────────────┐
                       └───────────────▶│ GATE (solve 직전 hard) │  schema §7.3
                                        │ blocked=true ?         │
                                        └───┬──────────────┬─────┘
                              blocked=true   │              │  passed / warned(low)
                          ┌──────────────────▼──┐           ▼
                          │ ✕ SOLVE 차단         │   ┌───────────────────┐
                          │ unresolved_high 해소 │   │ 4.SOLVE (MICOM     │
                          │ 바로가기 (resolve)   │   │   cooperative_     │
                          │ → 2로 복귀           │   │   tradeoff,        │
                          └──────────────────────┘   │   fluxes=True,pfba)│  glossary D
                                                      │ OSQP→LP 재계산     │  §4.2
                                                      └─────────┬─────────┘
                                                                │ tidy nodes/edges/profile
                          ┌─────────────────────────────────────┼───────────────────────────┐
                          ▼                     ▼                ▼               ▼            ▼
                  ┌──────────────┐   ┌──────────────┐  ┌──────────────┐ ┌──────────┐ ┌──────────┐
                  │5.INTERACTION │   │6.ADD-MEMBER  │  │7.SANDBOX (G1)│ │8.SWEEP   │ │9.EXPORT  │
                  │  GRAPH       │   │  DELTA       │  │ bound 제약+  │ │  (G4)    │ │  FIGURE  │
                  │ cross-feeding│   │ baseline 복제│  │ 재최적화     │ │ 축×값 →  │ │ R Render │
                  │ edges        │   │→멤버 추가→   │  │ preview 기본 │ │ N-run    │ │ SVG/TIFF │
                  │ (External    │   │ 재solve→     │  │ →Apply/Save  │ │ run_hash │ │ figure_  │
                  │  Profile도)  │   │ delta network│  │ commit 승격  │ │ 캐시·실패│ │ spec     │
                  │              │   │ /heatmap     │  │ (SC-8 비오염)│ │ diagnostic│ │ 재현     │
                  └──────────────┘   └──────────────┘  └──────┬───────┘ └────┬─────┘ └──────────┘
                                                       Apply/Save│   commit  │
                                                              ▼            ▼
                                                       ┌────────────────────────┐
                                                       │ AggregationStore /      │  schema §6·§8.5
                                                       │ RunManifest (run_hash   │  [RUNHASH-COMMIT]
                                                       │ 11구성요소, commit only)│
                                                       └────────────────────────┘
```

**Flow 불변식 (invariants)**:
- **gate 선행 (schema §7.3 [Gate-선행])**: 차단된 condition은 정상 run으로 승격되지 않고 sweep.parquet에 `status=failed`·diagnostic으로만 기록(SC-3).
- **preview→commit (schema §8.5)**: 5·6·7의 탐색은 기본 preview. **Apply/Save 사용자 액션**에서만 Scenario/Run artifact 승격 → run_hash 산출(11구성요소, schema §4.2)·AggregationStore 진입(SC-8).
- **단일 reader (Plan §6.3)**: 5/6/7/8/9 모든 View는 tidy 계약(schema §2)·sweep.parquet(schema §6)을 동일 reader로 소비.

---

### 5.3 Component (View) List

> 각 View는 책임(presentation)과 소비/호출하는 core 계층(Plan §7.3 `core/*` + `EngineService` facade)을 분리한다. View는 직접 MICOM/solver를 호출하지 않고 **`EngineService` → `JobRunner`** 만 경유한다.

| View (gui/ 모듈) | 책임 (presentation responsibility) | 소비 tidy/엔티티 | core 연결 (호출 대상) | 앵커 |
|---|---|---|---|---|
| **ProjectExplorer** (`explorer/`) | Models·Media·Scenarios·Runs/Sweeps 트리 탐색·선택·preview/commit 상태 배지 | Scenario.state(schema §3.3) | `Store` reader·`manifest/` | §5·Plan §7.3 |
| **ModelManager** (`models/`) | import(SBML/JSON/MAT)·model summary·reaction/metabolite/gene 테이블(필터·정렬·다중선택)·**namespace 상태(coverage%·unresolved) 상시 노출** | MemberModel(schema §3.1) | `io/`(import)·`namespace/`(gate 평가) | §5·§11·FR-0.3 |
| **MediumEditor** (`medium/`) | 배지 정의(CSV paste·preset·composition 편집)·Check Growth·minimal medium(MILP) 토글·aerobic/anaerobic | Medium(schema §3.2) | `engine/`(Check Growth)·minimal medium(MILP capability, schema §5) | §4.5·§5·FR-0.4 |
| **CommunityBuilder** (`community_builder/`) | member set 조립·abundance(절대/상대·normalize)·objective·tradeoff f·**solve 전 gate 배지**·sandbox bound 진입 | CommunityModel(schema §3.4)·Scenario.config | `engine/`(MICOM wrapper)·`namespace/`(gate)·`sandbox/` | §4.1·§4.2·§4.8 |
| **InteractionGraph** (`graph/`) | **Cytoscape.js in QWebEngineView** — cross-feeding 노드/엣지 시각화·레이아웃·필터·linked highlight·Export Figure 트리거 | nodes/edges.parquet(schema §2.1·§2.2) | `tidy/`(단일 reader)·`RenderClient` | §4.6·FR-1b.1·Plan §7.2 |
| **ExternalProfileViewer** (`profile/`) | net diverging bar·per-member stacked·heatmap·FVA error bar·baseline vs constrained delta 오버레이 | profile.parquet(schema §2.3) | `tidy/`·`sandbox/`(delta 오버레이) | §4.3·§4.6·§10·§11 |
| **ScenarioCompare** (`scenario/`) | A/B/N Scenario 비교·동일조건 고정 토글·condition×metric matrix·delta network/heatmap(AN-DELTA) | matrix.parquet(schema §2.4)·nodes/edges | `delta/`·`tidy/` | §4.6·§10·FR-2.1·FR-2.2 |
| **SweepView** (`sweep_view/`) | 축×값 정의·배치 실행·진행률·condition×metric 매트릭스·**캐시 hit 표시**·집계 export | sweep.parquet(schema §6) | `sweep/`(run_hash 캐시·diagnostic)·`JobRunner` | §5·§10·A14·FR-2.7 |
| **Runtime & Jobs** (`runtime_jobs/`) | in-process job 목록·진행률·**cancel/retry**·solver capability 상태·QP-only 표기 | RunManifest.solver(schema §4.1) | `JobRunner`·`SolverBackend` | Plan §7.2·NFR Perf/Reliability |
| **GateUI** (`models/` or `community_builder/` 통합 패널) | coverage%·unresolved_high 목록·warned_low 목록·**차단 상태**·해소(resolution) 바로가기 | NamespaceGateResult(schema §7.2)·NamespaceDecision(schema §7.1) | `namespace/`(gate)·audit trail | §4.8·§11·FR-1b.3 |

---

### 5.4 Page (View) UI Checklist

> **gap-detector 검증용**. 각 주요 View가 baseline(MVP-0~2) 요구·불변식을 누락 없이 충족하는지 점검하는 **필수 인터랙티브/표시 요소** 체크리스트. spec 미명시 위젯 세부는 `(Design에서 확정)`.

#### 5.4.1 ModelManager + GateUI (schema §3.1·§7.2·§11)
- [ ] **import 버튼** — SBML/JSON/MAT만 허용(file dialog 필터); pickle/기타 거부(schema §8.6 [FILE-FORMAT]·[NO-PICKLE]).
- [ ] **model summary 패널** — stats(n_reactions/metabolites/genes/exchanges), biomass/exchange compartment, namespace_convention 표시.
- [ ] **reaction/metabolite/gene 테이블** — 컬럼 정렬·텍스트 필터·다중선택(FR-0.3).
- [ ] **namespace 상태 배지(상시)** — `coverage_pct`(0–100) 진행바·색상 코딩(schema §7.2).
- [ ] **unresolved_high 목록** — 차단 유발 대사체 list, 항목 클릭 → 해소 바로가기(resolution shortcut).
- [ ] **warned_low 목록** — 경고 진행 대사체 list, **자동병합 없음 명시**(schema §7.3 [Gate-경고]).
- [ ] **차단 상태 표시(blocked)** — `blocked=true` 시 빨강 배너 "SOLVE blocked: N unresolved high-conf"(SC-3).
- [ ] **해소 워크플로 진입점** — confidence/decision 표시·rationale 입력(자동병합 금지). 매핑 wizard 상세 범위는 OD-42(`Design에서 확정`).
- [ ] **audit trail 링크** — gate 결정 기록 위치(schema §7.2 audit_trail_ref).

#### 5.4.2 MediumEditor (schema §3.2·§4.5)
- [ ] **composition 편집기** — metabolite_id·lower_bound·upper_bound 행 편집; **uptake=음수 lower_bound** 시각 단서(schema §8.1 [MEDIUM-SIGN]).
- [ ] **CSV paste / preset 선택** — preset 카탈로그(OD-7 `Design에서 확정`).
- [ ] **aerobic/anaerobic 토글** — oxygen_mode(schema §3.2).
- [ ] **minimal medium 토글(is_minimal)** — **MILP capability 부재 시 비활성화**(schema §5.3·§8.6 [MILP-CAPABILITY]); U={H₂O,H⁺,Pi} 강제 표시.
- [ ] **Check Growth 버튼** — feasibility 결과·diagnostic(infeasible 시).

#### 5.4.3 CommunityBuilder (schema §3.3·§3.4·§4.2·§4.8)
- [ ] **멤버 add/remove (drag)** — Explorer→Builder 드래그·중복 id 거부(schema §8.3 [ID-UNIQUE]).
- [ ] **abundance 입력** — 멤버별 수치 입력 + **절대/상대 토글** + **normalize 버튼**(합=1.0, schema §8.2 [ABUND-NORM]); override 우선순위(schema §8.2 [ABUND-PRIORITY]) 표시. 단위·모드는 OD-4.
- [ ] **objective 선택** — community growth Σa_m·μ_m(host 결합은 PART II 비노출, schema §3.4).
- [ ] **tradeoff f 슬라이더** — 0<f≤1 범위 강제(schema §8.2 [TRADEOFF-RANGE]); 값 표시.
- [ ] **solver 설정** — growth_solver(QP)/flux_solver(LP) 분리 표시·기본 Gurobi(schema §5.2); HiGHS-QP experimental 노출 여부 OD-26.
- [ ] **실행 전 namespace hard gate 배지** — passed/warning/blocked(schema §3.4 namespace_gate_status); **blocked면 Run 버튼 비활성화**(glossary 1.B).
- [ ] **Run (community solve) 버튼** — gate 통과 시에만 활성; OSQP→LP 재계산·LP 부재 시 "QP-only approximate" 표기(schema §4.1 solver 블록·glossary 1.D).
- [ ] **sandbox 진입 + bound 슬라이더 (G1)** — reaction bound 제약 변경(flux 직접 편집 아님, glossary AN-SANDBOX)·**debounced 재solve**(OD-54)·취소/되돌리기.
- [ ] **preview 표시 + Apply/Save 버튼** — 기본 preview(store/cache 비기록, schema §8.5); Apply/Save 시에만 commit 승격·run_hash 산출(SC-8).

#### 5.4.4 InteractionGraph (schema §2.1·§2.2·§4.6)
- [ ] **노드 인코딩** — node_type{member, environment_pool}·label·growth/abundance 시각 매핑(크기/색).
- [ ] **엣지 인코딩** — cross-feeding 방향(source_member→target_member)·weight(=min, ≥0) 두께/투명도; metabolite 라벨.
- [ ] **레이아웃 선택** — force/circular/hierarchical 등(Cytoscape.js 레이아웃 선택기).
- [ ] **필터** — metabolite·weight 임계·member·edge_type{cross_feeding}(schema §2.2).
- [ ] **linked highlight** — 그래프↔Inspector↔테이블 연동 선택(glossary 2.8 linked selection).
- [ ] **부호 범례** — `+`=분비/`−`=흡수 graph 내 범례(NFR 상시, schema §8.1).
- [ ] **Export Figure 버튼** — RenderClient(R subprocess)로 SVG/TIFF·figure_spec 재현(schema §4.1 figure_specs·Plan §7.2).
- [ ] **렌더 실패 fallback** — QWebEngine/Cytoscape 실패 시 텍스트/테이블 fallback(Plan R5).

#### 5.4.5 ExternalProfileViewer (schema §2.3·§4.3·§11)
- [ ] **net diverging bar** — metabolite별 net_flux(+secretion/−uptake) 양/음 발산 막대; label(uptake/secretion) 색 코딩.
- [ ] **per-member stacked** — member_contribution(멤버↔pool 분해) 스택드 바(schema §2.3).
- [ ] **heatmap** — metabolite × member/condition 히트맵.
- [ ] **FVA error bar** — fva_min/fva_max 범위 표시(schema §2.3); 보상 우회 "no significant change" 진단(OD-53).
- [ ] **baseline vs constrained delta 오버레이** — G1 sandbox preview의 baseline↔constrained external-profile delta 오버레이(glossary AN-SANDBOX).
- [ ] **부호 범례** — +분비/−흡수 상시(NFR).

#### 5.4.6 ScenarioCompare (schema §2.4·§4.6·AN-DELTA)
- [ ] **A/B/N 선택기** — 비교 Scenario 다중 선택.
- [ ] **동일조건 고정 토글** — medium/abundance 등 고정 후 멤버 추가만 변주(AN-DELTA, schema §3.3).
- [ ] **delta network** — 추가 멤버 전/후 cross-feeding edge 변화(추가/제거/강화).
- [ ] **delta heatmap** — metric별 Δ 히트맵.
- [ ] **condition×metric matrix** — matrix.parquet(row_key×col_key×value, schema §2.4).

#### 5.4.7 SweepView (schema §6·§10·A14)
- [ ] **축 정의 (6종 폐쇄 enum)** — {medium variant·abundance·member set·bounds·tradeoff f·solver} 중 선택(schema §6.2 폐쇄 enum); 그 외 축 거부.
- [ ] **값 정의** — 축별 값 목록 입력; 그리드 미리보기 `n_runs = Π(축별 n_values)`(schema §6.2).
- [ ] **배치 실행 버튼** — N-run job submit → JobRunner(비차단).
- [ ] **진행률** — job 진행바·취소(NFR Perf·Reliability).
- [ ] **condition×metric 매트릭스** — condition_id × metric × value 표(schema §6.1).
- [ ] **캐시 hit 표시** — run_hash hit(재사용)/miss(재계산) 행별 배지(schema §6.2·SC-4).
- [ ] **실패 run 표시(누락 금지)** — `status=failed` 행 + diagnostic 필수 노출(schema §6.1·§8.6 [STATUS-CLOSED]·SC-4).
- [ ] **집계 export 버튼** — sweep.parquet export(Parquet/Arrow만, pickle 금지).

#### 5.4.8 Runtime & Jobs (Plan §7.2·NFR)
- [ ] **job 목록** — solve/sweep/import/render job 상태(pending/running/done/failed).
- [ ] **진행률·cancel·retry** — 장기 작업 cancel/retry(in-process JobRunner).
- [ ] **solver capability 표시** — LP/QP/MILP별 가용 solver·기본 Gurobi(schema §5.2); 부재 시 해당 분석 비활성화 안내(schema §5.3 disable_analysis_on_missing).
- [ ] **QP-only approximate 경고** — LP flux_solver 부재 시 flux_report_status 경고 배지(schema §4.1·glossary 1.D).

---

## 6. Error Handling

> CMIG의 에러 처리는 두 가지 원칙을 따른다: **(1) Fail-fast & explicit** — silent error 절대 금지(특히 namespace/sign 혼동, R2), **(2) 부분 강등(graceful degradation)** — capability 부재 시 앱 전체가 아니라 **해당 분석만 비활성화**한다(`disable_analysis_on_missing=true`, schema §5.3·NFR Reliability). 모든 진단(diagnostic)은 사용자에게 투명하게 노출되며, sweep 컨텍스트에서는 `status=failed`·`diagnostic≠null`로 **누락 없이 기록**된다(schema §6·[STATUS-CLOSED]·SC-4).

### 6.1 에러·진단 카탈로그 (Error & Diagnostic Catalog)

> 진단 구조(자유 텍스트 vs 구조화 JSON·코드 enum + 메시지)는 `(Design에서 확정 — OD-31)`. 아래 메시지는 표준 문안 권장이며, `diagnostic` 컬럼(schema §6.1)·RunManifest·GUI 모두 동일 문안을 참조한다.

| # | 원인 (cause) | 발생 지점 | 처리 (handling) / 거동 | 사용자 메시지 (표준 문안) | 기록 위치 | 앵커 |
|---|---|---|---|---|---|---|
| **E-1 infeasible** | MICOM solve가 infeasible (배지 부적합·과도한 bound 제약·growth 0 등) | engine wrapper(MICOM 호출) 직후 | solve 결과를 `status=failed`로 마킹, **infeasible diagnostic** 산출(원인 추정: 결핍 exchange·충돌 bound). cross-feeding/profile 추출 **중단**, tidy `nodes/edges/profile`는 status=failed 표현으로 결측. sweep에서는 행을 **append(누락 금지)**. | "Solve infeasible — 커뮤니티가 현재 배지·제약 하에서 성장 불가. 확인: minimal medium 결핍 exchange / 충돌하는 bound 제약 / tradeoff_f 과대." | sweep.parquet(`status=failed`·`diagnostic`)·RunManifest | §4.4·schema §6.1·[STATUS-CLOSED] |
| **E-2 namespace gate 차단** | `unresolved AND confidence=high` exchange mapping 1건 이상 (schema §7.3 [Gate-차단]) | solve **직전** gate (MICOM 호출 전, schema §7.3 [Gate-순서]) | `NamespaceGateResult.blocked=true` → **MICOM solve 미호출**(어떤 solve도 실행 안 됨). **해소(resolution) 요구** — `unresolved_high` 목록을 바로가기로 제시. **자동병합 절대 금지**. sweep condition은 정상 run으로 승격되지 않고 `status=failed`·diagnostic으로만 기록(schema §7.3 [Gate-선행]·SC-3). | "Namespace gate 차단 — 미해소 고신뢰(high-confidence) exchange 매핑 N건. solve 진행 불가. 해소 필요: {unresolved_high 목록}." (gate 차단/경고 동작은 audit trail 필수 기록, [Gate-audit]) | NamespaceGateResult·audit_trail·sweep.parquet(failed) | §4.8·schema §7.2·§7.3·SC-3 |
| **E-3 namespace 경고(low-confidence)** | `confidence=low` mapping (schema §7.3 [Gate-경고]) | solve 직전 gate | **차단하지 않음** — 경고 후 진행, `decision=warned` 표기. **자동병합 금지**(사용자/audit 확인 대상). solve는 정상 수행되나 GUI에 경고·`warned_low` 목록 노출. | "Namespace 경고 — 저신뢰(low-confidence) 매핑 M건을 경고와 함께 진행(자동병합 없음). 결과 해석 주의: {warned_low 목록}." | NamespaceGateResult.warned_low·audit_trail | §4.8·schema §7.3 |
| **E-4 capability 강등 (solver 부재 → 분석 비활성화)** | 요청 분석의 problem_class에 맞는 solver 미설치/미라이선스 (예: LP·QP·MILP 부재) | EngineService capability 점검(solve 전) | **부분 강등** — 해당 분석만 비활성화(`disable_analysis_on_missing=true`), **앱 전체는 생존**. GUI에서 해당 액션 disable + 사유 표시. Gurobi(기본) 부재 시 무라이선스 경로(highs/osqp) fallback 규칙은 `(Design에서 확정 — OD-25)`. | "Solver capability 부재 — {analysis}는 {LP\|QP\|MILP} solver를 요구하나 사용 가능 solver 없음. 이 분석만 비활성화됨(앱 정상). 설치/라이선스 안내: {Gurobi WLS·highspy·osqp}." | RunManifest.solver·GUI 상태 | §2·schema §5.3·SC-1 |
| **E-5 QP-only approximate (LP flux_solver 부재)** | growth=OSQP(QP)로 확보했으나 flux 재계산용 **LP solver(Gurobi/HiGHS/CPLEX) 부재** (schema §5.3 [SOLVER-SPLIT]) | OSQP growth solve 후 LP pFBA 재계산 단계 | LP pFBA 재계산 **불가** → QP 결과만으로 flux 근사. `flux_report_status='QP-only approximate'`로 **명시 표기**(에러 아님, 정확도 한계 투명 고지). growth/flux solver는 manifest에 분리 기록(schema §4.1). tidy 산출은 유효하되 approximate 플래그 동반. | "QP-only approximate — LP flux solver 부재로 pFBA flux 재계산 생략. growth는 정확(OSQP), flux는 QP 근사값. 정확 flux를 원하면 LP solver(Gurobi/HiGHS) 설치." | RunManifest.solver.flux_report_status·diagnostic(비-실패) | §4.2·§4.4·schema §4.1·SC-6 |
| **E-6 MILP 부재 → minimal medium 비활성화** | `Medium.is_minimal=true` 산출 요청이나 **MILP capability(Gurobi/HiGHS/CPLEX) 부재** (schema §5.3 [MILP-CAPABILITY]) | minimal medium(cardinality MILP) 진입 | **minimal medium 분석만 비활성화**(E-4의 특수 케이스). 다른 분석(LP/QP)은 정상. GUI에서 minimal medium 액션 disable. | "Minimal medium 비활성화 — cardinality MILP는 MILP solver(Gurobi/HiGHS/CPLEX)를 요구하나 사용 불가. 이 분석만 비활성화됨." | GUI 상태·RunManifest | §2·§4.5·schema §5.3·[MILP-CAPABILITY] |
| **E-7 sandbox cancel / undo** | 사용자가 G1 sandbox 재solve 취소 또는 되돌리기(undo) (AN-SANDBOX·debounced re-solve) | JobRunner(in-process, cancel/retry) | 진행 중 debounced re-solve job을 **cancel** — GUI 생존, UI 프리즈 0. preview 상태이므로 store/cache/sweep **비오염(미기록)**, undo는 직전 bound 상태로 복원. commit(Apply/Save) 전까지 어떤 artifact도 승격 안 됨(SC-8). debounce 지연·취소 정책 구체값은 `(Design에서 확정 — OD-54)`. | "재solve 취소됨 — preview 결과는 저장되지 않음(store/cache 비기록). 직전 제약으로 복원 가능(undo)." | (없음 — preview 비기록, [PREVIEW-NOWRITE]) | §10 AN-SANDBOX·§4.2·schema §8.5·A11·SC-8 |
| **E-8 MICOM API/버전 drift** | MICOM public API 변경·미노출 기능 의존·exact pin 불일치 (R1) | engine wrapper(단일 진입점) | engine wrapper가 **public API + documented flux only** 경계를 강제 — internal API 접근 시 명시적 에러. 버전 불일치는 golden 승격 게이트(SC-5)에서 차단. | "MICOM 버전/API 불일치 — pin된 micom==X.Y.Z와 환경 불일치 또는 미지원 API. golden 미통과 시 승격 차단." | RunManifest.engine·golden CI | §4.1·schema §5(미생물)·SC-5 |
| **E-9 직렬화 위반 (pickle)** | pickle import/직렬화 시도 (schema §8.6 [NO-PICKLE]) | I/O 계층·lint | **차단** — 허용 직렬화(Parquet/Arrow/JSON/YAML/SQLite) 외 거부. pickle import 금지 lint(§7.4 참조). | "직렬화 위반 — pickle 금지. 허용: Parquet/Arrow/JSON/YAML/SQLite (TSV=golden 전용)." | lint·코드 스캔 | §5·§8·schema §8.6·[NO-PICKLE] |

### 6.2 진단 처리 불변식 (Diagnostic Invariants)

- **[ERR-NO-SILENT]** 모든 에러(특히 E-2/E-3 namespace, sign 혼동)는 명시 표기·audit 기록한다. silent 잘못된 cross-feeding 결론을 절대 산출하지 않는다(R2·§4.8).
- **[ERR-FAILED-RECORD]** sweep 컨텍스트의 실패 run(E-1·E-2)은 `status=failed`·`diagnostic≠null`로 **반드시 기록**한다(누락 금지, schema §6·[STATUS-CLOSED]·SC-4).
- **[ERR-DEGRADE-PARTIAL]** capability 부재(E-4·E-6)는 **해당 분석만** 비활성화한다 — 앱 전체 강등 금지(schema §5.3).
- **[ERR-QP-FLAG]** LP 부재(E-5)는 에러가 아니라 `QP-only approximate` 상태값으로 처리한다(growth는 정확, flux만 근사; §4.2).
- **[ERR-PREVIEW-SAFE]** sandbox cancel/undo(E-7)는 preview 비오염을 보존한다 — store/cache/sweep 미기록(schema §8.5·SC-8).
- **[ERR-GATE-PRECEDE]** gate 차단(E-2)은 MICOM 호출 **이전**에 발생하며, 차단 시 어떤 solve도 실행되지 않는다(schema §7.3 [Gate-순서]·[Gate-선행]).

---

## 7. Security & Licensing

> 네이티브 데스크톱 과학앱(SaaS/web/BaaS 아님)의 보안·라이선스 정책. 핵심: **로컬 바인딩·격리·pickle 금지·GPL 오염 차단**. 측정은 코드 스캔·import 경로 검사·의존성 라이선스 audit으로 수행한다(NFR Security·License).

### 7.1 보안 정책 (Security Policy, §8 NFR)

| # | 항목 | 정책 | 근거 / 위협 | 검증 방법 | 앵커 |
|---|---|---|---|---|---|
| **S-1** | optional 원격/IPC 바인딩 | 원격 모드(optional FastAPI) 활성 시 **127.0.0.1(loopback) 전용 바인딩** — 외부 인터페이스 노출 금지. baseline은 in-process sidecar 우선이라 네트워크 표면 최소. | 로컬 데스크톱 — 외부 네트워크 노출 불필요·공격 표면 축소 | 바인딩 주소 코드 스캔 | §8·Plan §3.2 NFR-Security |
| **S-2** | 인증 토큰 | 원격/IPC 경계 사용 시 **토큰 인증** 필수 (loopback이라도 로컬 멀티유저 보호) | 동일 호스트 타 프로세스의 무단 호출 차단 | 토큰 검증 테스트 | §8 NFR-Security |
| **S-3** | Docker socket | optional Docker 사용 시 **docker socket 미마운트** (`/var/run/docker.sock` 컨테이너 노출 금지) | docker socket 마운트 = 호스트 권한 탈취 경로(privilege escalation) | 컨테이너 구성 검사 | §8 NFR-Security |
| **S-4** | **pickle 금지** | 어떤 엔티티·산출·fixture도 pickle 직렬화 금지. 허용=Parquet/Arrow/JSON/YAML/SQLite(TSV=golden 전용). pickle import 금지 lint. | pickle 역직렬화 = 임의 코드 실행(RCE) 벡터 | import 경로 스캔·lint | §5·§8·schema §8.6 [NO-PICKLE] |
| **S-5** | 모델 import 포맷 | `MemberModel.source.file_format ∈ {SBML, JSON, MAT}`만 허용(폐쇄 enum). pickle/실행형 포맷 거부. | 신뢰 불가 모델 파일의 코드 실행 차단 | file_format enum 검증 | §5·§8·schema §8.6 [FILE-FORMAT] |
| **S-6** | 경로 안전성 | `source.file_path` 등 절대 경로 사용·path traversal 방지. | 외부 경로 탈출 차단 | 경로 검증 | §5·RULES |

### 7.2 라이선스 정책 (Licensing Policy, §2·NFR-License)

| # | 컴포넌트 | 라이선스 | 정책 | 근거 | 앵커 |
|---|---|---|---|---|---|
| **L-1** | **GLPK** | **GPL** | **미번들(unbundled)** — 번들/배포 제외. capability matrix에 존재하되 `is_bundled=false`. capability가 아닌 **라이선스 정책** 사안. | GPL 정적/배포 결합 시 전체 GPL 오염(copyleft) | schema §5.2 GLPK 행·A7 | §2·A6·A7 |
| **L-2** | **R + 렌더 패키지** (svglite/ragg/ggraph/circlize/ComplexHeatmap) | **GPL** | **별도 프로세스 격리(process isolation)** — `render_r/`는 subprocess로 분리, 데이터 I/O(Parquet/SVG/TIFF 파일)만 교환. in-process 링크 금지. RenderClient(R subprocess, 격리)가 단일 경계. Python fallback 보유. | R GPL을 별도 프로세스로 격리하면 CMIG 코어와 GPL 결합 회피 | Plan §7.2·§8.3 | §9·NFR-License·R7 |
| **L-3** | **cobrapy** | **LGPL** | **재검증(re-validate)** — LGPL 사용 경계 확인(동적 링크·수정 배포 조건). | LGPL은 조건부 허용이나 사용 형태 재확인 필요 | Plan §8.3 deps | §2·NFR-License |
| **L-4** | **Gurobi** | commercial-academic | **WLS 학술 라이선스** — CI=Gurobi WLS, **미번들**. 무라이선스 경로(highs/osqp golden)로 진입장벽 완화(R4). | 상용 라이선스 — 번들 불가·학술 WLS로 CI 사용 | schema §5.2·Plan §7.2 | §2·A6 |
| **L-5** | OSQP / HiGHS / pyarrow 등 | Apache / MIT | **번들 가능** — permissive. OSQP=QP 전용 경로, HiGHS=무라이선스 LP/MILP·QP(experimental). | permissive — 오염 없음 | schema §5.2 | §2·A6 |
| **L-6** | MICOM | Apache-2.0 | **번들 가능**(엔진 buy). 정확 pin·public API only. | permissive·Build vs Buy(buy) | Plan §1.2 | §2·§4.1 |
| **L-7** | PySide6 / cobrapy | LGPL | PySide6=LGPL(GUI), L-3과 동일 재검증 원칙. | LGPL 동적 링크 허용 | Plan §7.2 | §2 |

### 7.3 보안·라이선스 불변식 (Invariants)

- **[SEC-NO-PICKLE]** pickle 직렬화는 코드·테스트·fixture 어디에도 존재하지 않는다(S-4·schema §8.6).
- **[SEC-LOOPBACK]** 원격 경계는 127.0.0.1 + 토큰만 허용한다(S-1·S-2).
- **[LIC-GPL-ISOLATE]** GPL 컴포넌트(GLPK·R)는 **번들 제외(GLPK)** 또는 **프로세스 격리(R)** 로 코어와 결합하지 않는다(L-1·L-2·R7).
- **[LIC-AUDIT]** 모든 의존성은 라이선스 audit을 통과해야 한다 — cobrapy LGPL 재검증 포함(L-3·NFR-License).

---

## 8. Test Plan (pytest, L1–L5)

> 본 프로젝트는 과학앱(NOT 웹)이므로 웹 표준 L1/L2/L3(단위/통합/E2E) 대신 **L1–L5 과학앱 매핑**을 사용한다: **L1 core 단위** → **L2 통합** → **L3 golden 매트릭스** → **L4 시나리오** → **L5 회귀(승격 게이트)**. 모든 테스트는 `tests/`(Plan §7.3)에서 pytest로 실행하며, **각 테스트를 SC-1..SC-9에 명시 매핑**한다(Plan §4.2). float 비교는 항상 **rounding/tolerance 후 정규화 hash**(schema §4.3·OD-12)로 수행한다.

### 8.1 L1 — Core 단위 테스트 (Core Unit, headless)

> `core/` 모듈을 GUI/엔진/네트워크 없이 격리 검증. 결정성·계약 형태 단위.

| 테스트 ID | 대상 | 검증 내용 | SC 매핑 | 앵커 |
|---|---|---|---|---|
| **L1-1** sign 변환 단일 진입점 | `core/sign/` | `raw_flux → (ui_flux, label)` 단일 진입점 경유; ui_flux=magnitude≥0; canonical: 환경 −10→(10,uptake)/+8→(8,secretion), 멤버↔pool −5→(5,uptake)/+3→(3,분비) | **SC-2** | §4.7·schema §8.1·[SIGN-2]·[SIGN-4] |
| **L1-2** cross-feeding 규칙 | `core/interactions/` | edge m→m′ 성립 ⟺ (m>0 분비 ∧ m′<0 흡수); weight=min(\|m\|,\|m′\|)≥0 | SC-2·SC-9 | §4.3·schema §8.1 [CROSS-FEED] |
| **L1-3** tidy 스키마 계약 | `core/tidy/` | `nodes/edges/profile`(parquet) 컬럼·타입·nullable·`schema_version` 필드 존재; 단일 reader 경유 | **SC-9** | §4.6·schema §2·§8.6 |
| **L1-4** run_hash 결정성 | `core/manifest/` | 동일 11구성요소 → 동일 hash; **정확히 11개**(가감 금지); float 구성요소는 hash 전 rounding/tolerance 적용; env_lock **미포함** | SC-4 | §7·schema §4.2·§4.3·§8.4 [HASH-11]·[HASH-FLOAT]·[HASH-ENVLOCK] |
| **L1-5** run_hash 단일 정의 | `core/manifest/` | AggregationStore.run_hash = RunManifest.run_hash = Scenario.run_hash 비트 단위 일치 | SC-4 | schema §8.4 [HASH-SINGLE] |
| **L1-6** abundance normalize | `core/engine/` | normalize 시 합=1.0; 우선순위 abundance_overrides > MemberModel.abundance | SC-9 | §5·§11·schema §8.2 [ABUND-NORM]·[ABUND-PRIORITY] |
| **L1-7** tradeoff_f 범위 | `core/engine/` | 0<f≤1 강제(경계 검증) | — | §4.2·schema §8.2 [TRADEOFF-RANGE] |

### 8.2 L2 — 통합 테스트 (Integration)

> 모듈 경계 결합 — gate→engine→tidy, OSQP→LP 재계산, cache hit/miss. MICOM은 단일 wrapper 경유.

| 테스트 ID | 대상 | 검증 내용 | SC 매핑 | 앵커 |
|---|---|---|---|---|
| **L2-1** gate 차단 | `namespace/`→`engine/` | unresolved high-confidence 존재 → `blocked=true` → **MICOM solve 미호출**; 해소 요구; gate는 solve 직전 적용 | **SC-3** | §4.8·schema §7.3 [Gate-차단]·[Gate-순서] |
| **L2-2** gate 경고(low) | `namespace/` | low-confidence → `warned` 진행·**자동병합 없음**·audit 기록 | **SC-3** | §4.8·schema §7.3 [Gate-경고]·[Gate-audit] |
| **L2-3** gate 선행→sweep | `namespace/`→`sweep/` | 차단 condition은 정상 run 미승격 → sweep.parquet에 `status=failed`·diagnostic만 기록 | SC-3·SC-4 | schema §7.3 [Gate-선행]·SC-3 |
| **L2-4** OSQP→LP 재계산 | `engine/` | growth=OSQP(QP) 확보 → community/growth constraint 고정 → LP(Gurobi/HiGHS) pFBA flux 재계산; growth/flux solver 분리 기록 | **SC-6** | §4.2·schema §4.1·§5.3 [SOLVER-SPLIT] |
| **L2-5** QP-only approximate | `engine/` | LP flux_solver 부재 → `flux_report_status='QP-only approximate'` 표기(에러 아님); growth 유효 | SC-6 | §4.2·§4.4·schema §4.1 |
| **L2-6** cache hit/miss | `sweep/`·`manifest/` | 동일 run_hash → **hit**(재계산 회피·기존 행 재사용); 1개 구성요소 변경 → **miss**·재계산 | **SC-4** | §10·schema §6.2·§8.4 [HASH-DETERMINISM] |
| **L2-7** 실패 run 누락 0 | `sweep/` | infeasible(E-1)/gate 차단(E-2) run도 `status=failed`·`diagnostic≠null`로 기록(누락 금지) | SC-4 | schema §6·§8.6 [STATUS-CLOSED] |
| **L2-8** capability 강등 | `engine/`·EngineService | MILP/LP/QP solver 부재 → **해당 분석만 비활성화**(앱 생존); minimal medium MILP 부재 시 비활성화 | SC-1 | §2·schema §5.3 [MILP-CAPABILITY] |

### 8.3 L3 — Golden 매트릭스 (Golden Matrix, solver별)

> `fixtures/community_3_member/`(schema §7.4) 기준, **solver 변형 3종**을 CI 매트릭스로 회귀. float 컬럼은 **rounding/tolerance 후 정규화 hash**(원시 float 직접 hash 금지).

| 테스트 ID | solver 변형 | 비교 대상 | 검증 내용 | SC 매핑 | 앵커 |
|---|---|---|---|---|---|
| **L3-1** | `gurobi`(기본) | expected_nodes/edges/profile.parquet · growth_expected.tsv · sign_expected.tsv | float tolerance(예: 6 decimal·abs/rel tol) 후 정규화 hash 일치 | **SC-1·SC-2·SC-9** | §16·A17·schema §7.4 |
| **L3-2** | `osqp` | 동일 expected/ (osqp/) | 무라이선스 QP 경로 golden 일치 | **SC-1** | §16·schema §5.2 |
| **L3-3** | `osqp_growth_highs_flux` | 동일 expected/ (osqp_growth_highs_flux/) | QP=OSQP→flux=HiGHS LP 재계산 변형이 gurobi golden과 **tolerance 내 일치** | **SC-1·SC-6** | §4.2·§16·A6·A17·schema §5.2·§7.4 |
| **L3-4** sign_expected | 3종 공통 | sign_expected.tsv | §4.7 canonical (ui_flux,label) 기대값 일치(TSV=golden 전용) | **SC-2** | §4.7·schema §8.6 |
| **L3-5** hash 정규화 규칙 | 3종 공통 | — | 컬럼 정렬·NaN 처리·decimal 자릿수 일관(determinism); 원시 float hash 금지 | SC-1 | §16·A17·schema §4.3 |

> golden은 tidy 5종 중 **nodes/edges/profile 3종**만 회귀 비교(glossary §1.E). `osqp_growth_highs_flux`는 golden 세트 명이지 solver 축 값이 아니다(schema OD-32).
>
> ⚠️ **golden 변형 = `gurobi`/`osqp`/`osqp_growth_highs_flux`** (Do 확정, I-3). 설계 초안의 무라이선스 변형은 `highs`였으나 **MICOM community `cooperative_tradeoff`는 QP solver를 요구**하여 pure-HiGHS(LP 전용)로는 community solve가 불가(SolverNotFound)하다. 따라서 무라이선스 QP 경로는 **`osqp`**로, **HiGHS LP는 hybrid(`osqp_growth_highs_flux`) 변형에서 flux 재계산으로 실검증**된다(SC-6). `engine.SOLVER_MAP` 및 `golden_fixture.SOLVER_VARIANTS`가 이 셋을 사용한다.
>
> ⚠️ **tolerance acceptance 미확정 (OD-12·OD-50)**: 위 L3 표의 `6 decimal·abs/rel tol 1e-6`은 **안전 시작값**이며 golden 안정화 후 variant별(특히 osqp_growth_highs_flux)로 보정한다. 따라서 **SC-1·SC-6 green 판정은 OD-12·OD-50 확정에 종속**된다 — 이 risk는 §11.2 MVP-1a DoD에 명시하며, Do 착수 시 golden 캡처와 함께 tolerance를 우선 확정한다.

### 8.4 L4 — 시나리오 테스트 (Scenario / End-to-end headless)

> 실제 분석 워크플로를 CLI/headless로 재현 — 튜토리얼 재현·delta·sandbox 비오염.

| 테스트 ID | 시나리오 | 검증 내용 | SC 매핑 | 앵커 |
|---|---|---|---|---|
| **L4-1** MICOM 튜토리얼 재현 | 스크립트 0줄로 MICOM 튜토리얼을 CLI/GUI 재현 + cross-feeding sanity | community/member growth·cross-feeding 추출이 튜토리얼과 일치 | **SC-7** | §16·Plan §4.1 MVP-1c |
| **L4-2** add-member delta | baseline community 복제→멤버 추가→**동일 조건** 재solve→delta 산출(delta network/heatmap) | 동일 조건 고정 하 delta 정확; tidy 계약 일치 | SC-7·SC-9 | §1·§10 AN-DELTA·Plan FR-2.1 |
| **L4-3** sandbox preview 비오염 | G1 sandbox bound 제약 변경→debounced 재solve(preview) | preview는 store/cache/sweep **비기록**; Apply/Save 시에만 artifact 승격; cancel/undo 후에도 비오염 | **SC-8** | §10 AN-SANDBOX·schema §8.5 [PREVIEW-NOWRITE]·A11 |
| **L4-4** sandbox 보상 우회 | bound 변경 후 보상 우회로 변화 미미 | FVA 범위·`no significant change` 진단 표시(임계는 OD-53) | SC-8 | §10·§11·Plan FR-2.6 |
| **L4-5** commit run_hash | preview→Apply/Save 승격 | commit 상태에서만 run_hash 영구 산출·기록; preview는 null/ephemeral | SC-8·SC-4 | schema §8.5 [RUNHASH-COMMIT]·A11 |

### 8.5 L5 — 회귀 / 승격 게이트 (Regression / Promotion Gate)

> MICOM 버전 상향·core 변경 시 golden 회귀로 **승격을 게이트**. 미통과 시 차단.

| 테스트 ID | 회귀 대상 | 검증 내용 | SC 매핑 | 앵커 |
|---|---|---|---|---|
| **L5-1** MICOM-version golden regression | micom_version 상향(micom==X.Y.Z 변경) | solver별 golden(L3-1~L3-3) **전부 통과 시에만 승격**; 미통과 시 **차단** | **SC-5** | §4.1·§16·§17·schema §7.4·§8.6 [MICOM-PIN] |
| **L5-2** run_hash 구성요소 변경 회귀 | run_hash 11구성요소 정의 변경 | 캐시 무효화·`manifest_schema_version` bump·마이그레이션 정책 적용(OD-22) | SC-4 | schema §4.3·§8.4·Plan §6.2·§6.3 |
| **L5-3** tidy 스키마 변경 회귀 | tidy 컬럼·schema_version 변경 | 모든 소비자(graph/profile/delta/sweep/R) 단일 reader 경유 계약 테스트 통과 | SC-9 | §4.6·Plan §6.2·§6.3 |
| **L5-4** sign 규약 변경 게이트 | sign 변환 규약 변경 | sign_expected.tsv 회귀가 **CI 필수 게이트** — 변경 시 cross-feeding/delta 해석 영향 차단 | SC-2 | §4.7·Plan §6.2 |

### 8.6 Fixtures / Seed (테스트 자산)

> 모든 fixture는 **pickle 금지** — Parquet/Arrow/JSON/YAML/SQLite, **TSV=golden 전용**(schema §8.6 [NO-PICKLE]). seed는 `config.yaml`·RunManifest에 기록하여 tie-break·sweep 결정성을 보장한다(schema §4.1·OD-12).

**`fixtures/community_3_member/` 구조 (schema §7.4):**

```
fixtures/community_3_member/
├── models/                  # 미생물 GEM 3개 (SBML|JSON|MAT, pickle 금지)
│   ├── member_1.xml
│   ├── member_2.xml
│   └── member_3.xml
├── medium.yaml              # 공통 배지 (YAML)
├── config.yaml              # tradeoff_f · seed · micom_version 등 재현 파라미터
└── expected/                # solver별 분리 (CI 매트릭스)
    ├── gurobi/              # expected_nodes/edges/profile.parquet · growth_expected.tsv · sign_expected.tsv
    ├── highs/               # 〃
    └── osqp_growth_highs_flux/   # QP=OSQP→flux=HiGHS LP 재계산 (§4.2)
```

**추가 fixture (L1/L2 전용):**

| fixture | 용도 | 테스트 | 앵커 |
|---|---|---|---|
| **sign fixture** (raw_flux→expected ui_flux/label) | canonical case (−10/+8/−5/+3) 단위 검증 | L1-1·L3-4 | §4.7·schema §8.1 [SIGN-4] |
| **gate fixture** (unresolved high / low-confidence mapping 세트) | gate 차단(blocked) vs 경고(warned) 분기 | L2-1·L2-2 | §4.8·schema §7.1·§7.2 |
| **cache fixture** (동일/1개 변경 run_hash 입력쌍) | hit/miss 결정성 | L2-6·L1-4 | §10·schema §6.2 |
| **infeasible fixture** (배지 결핍·과제약) | E-1 infeasible diagnostic·실패 run 기록 | L2-7 | §4.4·schema §6 |

**SC 커버리지 매트릭스 (요약):**

| SC | 충족 테스트 |
|---|---|
| **SC-1** golden(solver별) | L3-1·L3-2·L3-3·L3-5·L2-8 |
| **SC-2** sign-test CI | L1-1·L1-2·L3-4·L5-4 |
| **SC-3** namespace gate 차단 | L2-1·L2-2·L2-3 |
| **SC-4** run_hash 캐시 | L1-4·L1-5·L2-6·L2-7·L5-2 |
| **SC-5** MICOM-version golden regression | L5-1 |
| **SC-6** OSQP→LP 재계산 | L2-4·L2-5·L3-3 |
| **SC-7** MICOM 튜토리얼 재현 | L4-1·L4-2 |
| **SC-8** sandbox preview 비오염 | L4-3·L4-4·L4-5 |
| **SC-9** tidy 계약 | L1-3·L1-6·L4-2·L5-3 |

> **seed/결정성**: seed는 `Scenario.config.seed`(schema §3.3)·RunManifest.algorithms에 기록되며, golden 비교·sweep tie-break의 재현성 기반이다. float tolerance 파라미터(decimal·abs/rel tol)는 `(Design에서 확정 — OD-12·OD-50)`이며, gurobi golden과 osqp_growth_highs_flux golden의 LP 재계산 허용 오차 일치 기준도 동일하게 확정 대상이다(SC-6).

---

## 9. Clean Architecture

### 9.1 레이어 구조 (Layered Headless `core/` + facade + JobRunner)

채택 아키텍처는 **Option C (Pragmatic)** — layered headless `core/` + 단일 **EngineService facade** + in-process **JobRunner**(cancel/retry). bkit 표준 레벨(Starter/Dynamic/Enterprise)은 웹 스택 전제라 부적합하므로, **Enterprise 급 레이어 분리 + DI**의 구조 모델만 차용하고 웹/BaaS 요소는 전부 제외한다 (Plan §7.1·§7.2).

| Layer | 위치 (folder) | 책임 (responsibility) | 의존 방향 | 앵커 |
|-------|--------------|----------------------|-----------|------|
| **Presentation** | `cmig/gui/` (PySide6/Qt) · `cmig/cli/` | UI/CLI 렌더·이벤트만. 계산 로직 없음(presentation only). QWebEngine(Cytoscape.js) graph 호스팅·gate UI·sandbox 드래그·sweep view. **계산은 GUI 밖 job** | → Application (EngineService) | Plan §7.3·FR-0.1·§11 |
| **Application** | `EngineService` facade + `JobRunner` | core 유스케이스 오케스트레이션의 **단일 진입점**. solve/sweep/sandbox/delta/render 요청을 job으로 래핑(cancel/retry)·진행률·취소·결과 tidy 반환. CLI·GUI 공통 소비 | → Domain (core) · → Infra(seam Protocol) | Plan §7.2(in-process sidecar+job runner)·FR-0.2 |
| **Domain** | `cmig/core/` (headless, engine-agnostic) | CMIG **부가가치 계층**. namespace gate·sign 정규화·tidy 계약·cross-feeding/interaction·delta·sandbox·sweep·manifest/run_hash. **외부 라이브러리(MICOM/Qt/R/solver)에 직접 무의존** — seam Protocol만 의존 | → (seam Protocol 인터페이스만) | Plan §7.3·schema §1.2 |
| **Infrastructure** | seam 구현체 | core가 정의한 Protocol의 구체 구현. `SolverBackend`·MICOM `engine` wrapper·`Store` writer·`RenderClient`(R subprocess). 외부 의존(gurobipy/highspy/osqp·micom·pyarrow/sqlite·R)을 **여기에 격리** | Domain Protocol **구현(역전)** | Plan §7.2·§7.3·§8.3 |

### 9.2 의존성 규칙 (Dependency Rule — core는 외부 무의존, seam은 Protocol로 역전)

```
  Presentation (gui/, cli/)
        │  uses
        ▼
  Application (EngineService facade + JobRunner)
        │  uses
        ▼
  Domain (core/  ── headless, pure CMIG value-add)
        ▲  defines Protocol (interface)
        │  implements (Dependency Inversion)
  Infrastructure (seams: solver / engine[MICOM] / store / render_r)
```

- **[DEP-1] 안쪽 화살표만**: 의존은 항상 Presentation→Application→Domain 방향. **Domain은 바깥 레이어를 import하지 않는다**. `core/`는 Qt·MICOM·gurobipy·R·pyarrow를 **직접 import 금지**.
- **[DEP-2] thin seam은 SC가 필요로 하는 곳에만**: 모든 추상화가 아니라 SC 충족에 필요한 4개 경계에만 Protocol(seam)을 둔다. 과추상화 금지(YAGNI, PRINCIPLES).
  - `SolverBackend` (gurobi 기본 / highs / osqp; golden 변형 `osqp_growth_highs_flux` swap) — **SC-1·SC-6** (§4.2 OSQP→LP 재계산, schema §5.3)
  - MICOM `engine` wrapper (public API + documented flux only: `cooperative_tradeoff(fluxes=True, pfba=...)`, 단일 진입점) — **SC-5·SC-7** (§4.1·§4.2)
  - `Store` writer (tidy parquet / sqlite meta / `sweep.parquet`) — **SC-4·SC-8·SC-9** (schema §2·§6)
  - `RenderClient` (R subprocess, 격리) — 출판 그림 (Plan §9, GPL 격리)
- **[DEP-3] Dependency Inversion**: seam 인터페이스(Protocol)는 **Domain이 소유**하고, 구체 구현은 Infrastructure가 제공한다. core는 추상에만 의존(Dependency Inversion, PRINCIPLES SOLID-D). 따라서 solver/engine/store/render는 **교체 가능**(Gurobi→HiGHS, parquet→sqlite, in-process→FastAPI/remote) — Plan §7.2 "경계는 추후 FastAPI/remote로 전환 가능하게 형성".
- **[DEP-4] 단일 진입점 불변식**:
  - 모든 solve는 **namespace hard gate 통과 후에만** MICOM `engine` wrapper를 호출한다 (schema [GATE-BLOCK]·§7.3 Gate-순서; `blocked=true`면 MICOM 미호출 — **SC-3**).
  - 모든 `raw_flux → (ui_flux, label)` 변환은 `core/sign/`의 **단일 진입점**만 경유 (schema [SIGN-2], glossary §1.A — **SC-2**).
  - 모든 산출은 `core/tidy/`의 **단일 계약**(nodes/edges/profile/matrix/timecourse parquet)으로만 출력, 전 소비자는 **단일 reader** 경유 (schema §1.3·§2 — **SC-9**).

### 9.3 Import 규칙 (정적 검증 가능)

| 규칙 | 내용 | 검증 |
|------|------|------|
| **IMP-1** `core/` import 화이트리스트 | `core/`는 표준 라이브러리 + 순수 데이터(numpy/pandas/pyarrow type 한정) 외 외부 엔진/GUI/solver를 import하지 않는다. `import micom`·`from PySide6`·`import gurobipy`·R 호출은 `core/` 밖(Infra)에서만 | ruff isort-boundary·import-linter(레이어 계약) |
| **IMP-2** seam은 Protocol로 선언 | `core/`는 `SolverBackend`/`engine`/`Store`/`RenderClient`를 `typing.Protocol`로 정의·주입받는다(생성자 DI). 구체 클래스를 직접 참조하지 않는다 | mypy(strict on `core/`) |
| **IMP-3** Presentation은 core 직접 호출 금지 | `gui/`·`cli/`는 `EngineService` facade만 호출하고 `core/` 내부 모듈을 직접 import하지 않는다 | import-linter |
| **IMP-4** pickle import 금지 | 어떤 레이어도 `import pickle`/`cPickle` 직렬화 사용 금지. 허용=Parquet/Arrow/JSON/YAML/SQLite(TSV=golden 전용) | pickle-ban lint (schema [NO-PICKLE]) |

### 9.4 본 기능(cmig-community-core) 레이어 배정

| 기능 요소 | Layer | 모듈 | SC/앵커 |
|-----------|-------|------|---------|
| PySide6 shell·graph viewer(Cytoscape.js+QWebEngine)·gate UI·sandbox 드래그·sweep view | Presentation | `gui/{explorer,models,medium,graph,profile,scenario,sweep_view,runtime_jobs}` | FR-0.1·1b.1·1b.3·§11 |
| headless CLI(MVP-1a 산출 진입점) | Presentation | `cli/` | FR-1a·§16 |
| solve/sweep/sandbox/delta/render 오케스트레이션·cancel/retry job | Application | `EngineService` + `JobRunner` | FR-0.2·NFR Reliability |
| namespace 정합·hard gate | Domain | `core/namespace/` | FR-1a.2·**SC-3**·§4.8 |
| sign 정규화 단일 진입점 | Domain | `core/sign/` | FR-1a.3·**SC-2**·§4.7 |
| tidy 데이터 계약·단일 reader | Domain | `core/tidy/` | FR-1a.4·**SC-9**·§4.6 |
| cross-feeding 추출·interaction typing·CMIG-MIP/MRO | Domain | `core/interactions/` | FR-1a.5·FR-2.4·§4.3·§4.5 |
| add-member delta | Domain | `core/delta/` | FR-2.1·§10 AN-DELTA |
| G1 constraint sandbox(preview/commit) | Domain | `core/sandbox/` | FR-2.6·**SC-8**·A11 |
| G4 sweep(run_hash 캐시·diagnostic) | Domain | `core/sweep/` | FR-2.7·**SC-4**·A14 |
| RunManifest·run_hash(11 구성요소) | Domain | `core/manifest/` | FR-2.8·§7·schema §4 |
| MICOM engine wrapper(public API only) | Infrastructure | `core/engine/`(seam 구현) | FR-1a.1·**SC-5·SC-7**·§4.1 |
| SolverBackend(gurobi/highs/osqp·OSQP→LP) | Infrastructure | solver seam | FR-1a.6·**SC-1·SC-6**·§4.2 |
| Store writer(parquet/sqlite/sweep.parquet) | Infrastructure | `io/` + store seam | **SC-4·SC-8·SC-9**·§8 |
| R Render Service(별도 프로세스) | Infrastructure | `render_r/`(RenderClient seam) | FR-2.5·Plan §9 |

> **주의**: `core/engine/`는 위치상 `core/` 아래에 있으나 **seam(Infra) 역할**이다 — Protocol은 `core/`가 정의하고, MICOM 의존 구현체만 이 wrapper에 격리된다(IMP-1 예외 없음: MICOM import는 이 wrapper 파일에서만).

---

## 10. Coding Convention Reference

> 본 절은 **참조 인덱스**다. 정식 규약은 **Phase 2 Convention**(`docs/01-plan/conventions.md`, 미존재→생성 예정)에서 확정한다 (Plan §8.1·§8.2·§9.3). 용어·부호·계약의 단일 권위는 `glossary.md`, 데이터 계약·불변식의 단일 권위는 `schema.md`다.

### 10.1 권위 참조 (Authoritative References)

| 주제 | 단일 권위 문서 | 비고 |
|------|---------------|------|
| 용어(domain term)·부호 규약·preview/commit·QP-only·tidy 5테이블 | `glossary.md` §1·§2 | 코드/UI/문서가 이 표현을 참조 |
| 데이터 계약(tidy parquet 컬럼)·도메인 엔티티·불변식·run_hash 11구성요소 | `schema.md` §2·§3·§4·§8 | 컬럼 표준명 일부는 OD(Design 확정) |
| gate·sign·golden·solver capability | `schema.md` §5·§7, `glossary.md` §1.A·§1.B | invariant 코드는 schema [TAG] 인용 |

### 10.2 Phase 2 Convention 예정 항목 (Plan §8.2)

| Category | 현재 상태 | To Define | Priority |
|----------|-----------|-----------|:--------:|
| **Naming** | missing | snake_case(함수·모듈)·PascalCase(클래스)·tidy 컬럼 표준명 | High |
| **Folder structure** | missing | §7.3 `core/cli/gui/render_r/io` 분리 | High |
| **Lint/Format** | missing | ruff + black, **mypy strict on `core/`** | High |
| **Sign/Unit 규약** | missing | `+`=분비/`−`=흡수 단일 진입점·flux 단위·정규화 표기 | **Critical** |
| **Reproducibility** | missing | **run_hash 11구성요소 직렬화 규칙**·seed 기록·float tolerance(예: 6 decimal) | **Critical** |
| **Error handling** | missing | infeasible diagnostic·capability 강등·QP-only 표기·gate 차단 메시지 표준 | High |
| **Pickle 금지** | missing | 직렬화는 Parquet/Arrow/JSON/YAML/SQLite만; **pickle import 금지 lint** | High |

### 10.3 네이밍 규칙 (Naming)

- **함수·모듈·변수**: `snake_case` (예: `extract_cross_feeding`, `core/sign/`, `run_hash`).
- **클래스·Protocol·Enum 타입**: `PascalCase` (예: `EngineService`, `JobRunner`, `SolverBackend`, `NamespaceGateResult`, `MemberModel`, `AggregationStore`).
- **tidy 컬럼 표준명**: schema §2의 표준명을 코드 상수로 고정 — `node_id`·`node_type`·`edge_type`·`metabolite`·`source_member`·`target_member`·`weight`·`net_flux`·`label`·`schema_version` 등. 컬럼 미상세분(`edge_type` 전체 집합·matrix `row_key/col_key`)은 **OD-45/OD-46**(Design 확정)까지 잠정.
- **sign label enum**: `uptake`/`secretion` (멤버↔pool '분비' enum 통일은 **OD-43**).
- **상태 enum**: `preview`/`commit`(Scenario.state), `ok`/`failed`(status), `passed`/`blocked`/`warning`(gate), `high`/`low`(confidence) — schema §3·§7·§8 폐쇄 enum 준수.

### 10.4 직렬화·재현성 lint 계약

- **pickle-ban lint**: `import pickle` 발견 시 CI 실패 (schema [NO-PICKLE]·NFR Security). 허용 직렬화만 통과. **TSV는 golden(`growth_expected.tsv`·`sign_expected.tsv`) 전용**.
- **run_hash 직렬화 규칙**: 정확히 11구성요소(가감 금지, schema [HASH-11])·float은 hash 전 rounding/tolerance(예: 6 decimal, schema [HASH-FLOAT]) 적용. 해시 함수·canonical 순서·구분자·인코딩은 **OD-11**(Design 확정).
- **mypy strict on `core/`**: Domain은 타입 완전성으로 seam Protocol 계약(IMP-2)을 정적 보장.

---

## 11. Implementation Guide

### 11.1 File Structure (Plan §7.3)

```
cmig/
  core/                 # CMIG 부가가치 계층 (engine-agnostic, headless) — Domain
    engine/             #   MICOM wrapper (public API only) — seam(Infra) 격리
    namespace/          #   namespace 정합 + hard gate (§4.8)               [SC-3]
    sign/               #   sign 정규화 단일 진입점 (§4.3·§4.7)            [SC-2]
    tidy/               #   tidy 데이터 계약 (nodes/edges/profile…, §4.6)  [SC-9]
    interactions/       #   cross-feeding 추출·interaction typing·MIP/MRO
    delta/              #   AN-DELTA (add-member delta)
    sandbox/            #   G1 constraint sandbox (preview/commit)          [SC-8]
    sweep/              #   G4 sweep (run_hash 캐시·diagnostic)             [SC-4]
    manifest/           #   RunManifest·run_hash (11 구성요소, §7)
  cli/                  # headless CLI (MVP-1a 산출 진입점) — Presentation
  gui/                  # PySide6 (presentation only) — Presentation
    explorer/ models/ medium/ community_builder/
    graph/              #   Cytoscape.js + QWebEngineView
    profile/ scenario/ sweep_view/ runtime_jobs/
  render_r/             # R Render Service (별도 프로세스, 데이터 I/O) — Infra
  io/                   # SBML/JSON/MAT import · Parquet/Arrow · SQLite/YAML meta — Infra
fixtures/
  community_3_member/   # golden: models×3 · medium.yaml · config.yaml
    expected/           #   solver별: gurobi/ · highs/ · osqp_growth_highs_flux/
                        #     expected_nodes/edges/profile.parquet · growth_/sign_expected.tsv
tests/                  # pytest (sign·gate·golden 매트릭스·cache·sandbox preview)
```

> `EngineService` facade + `JobRunner`(Application)는 `core/`와 `gui/cli/` 사이 단일 진입점으로 배치(파일 위치는 Design 확정, 예: `cmig/app/`). golden `expected/` 중복 vs 공유 구조는 **OD-48**.

### 11.2 Implementation Order (MVP-0 → 1a → 1b → 1c → 2)

MVP-1a(headless core + golden)가 **1순위** (Plan §2.1·§9.4). 검증 게이트(1c)는 MICOM-version golden regression이 통과해야 다음으로 승격(**SC-5**).

| 순서 | MVP | 목표 | 완료 정의(DoD) | 앵커 |
|------|-----|------|----------------|------|
| 1 | **MVP-0** Foundation | Qt shell·sidecar+EngineService/JobRunner·SBML import·단일종 AN-SINGLE·RunManifest·solver capability matrix | 단일 모델 FBA/pFBA·bound 편집·capability 강등 동작 | Plan §2.1·§4.1·schema §5 |
| 2 | **MVP-1a** Headless core | MICOM 통합·namespace gate·sign 계약·tidy 계약·cross-feeding·OSQP→LP 재계산·golden(solver별) | **CLI 3+ 미생물·배지 산출 + sign 통과 + gate 동작 + solver별 golden 통과** | Plan §4.1·SC-1/2/3/6/9 |

> ⚠️ **MVP-1a DoD risk (OD-12·OD-50)**: solver별 golden 통과 판정(SC-1·SC-6)의 **tolerance acceptance 값이 미확정**(round 6dec·abs/rel 1e-6는 안전 시작값)이다. Do 착수 첫 단계에서 golden 캡처와 함께 variant별(특히 `osqp_growth_highs_flux`) tolerance를 **우선 확정**해야 CI gate가 의미를 가진다 (§8.3 L3 각주 참조).
| 3 | **MVP-1b** GUI graph | Cytoscape.js graph viewer·필터·linked selection·gate UI | graph 노드/엣지 인코딩·coverage%·unresolved 바로가기 | Plan §2.1·FR-1b·§11 |
| 4 | **MVP-1c** Validation(승격 게이트) | MICOM 튜토리얼 재현(스크립트 0줄)·cross-feeding sanity·MICOM-version golden regression | 재현 로그 + golden 전부 통과 시에만 승격 | Plan §4.1·SC-5·SC-7 |
| 5 | **MVP-2** Delta/Sandbox/Sweep/R | AN-DELTA·G1 sandbox(preview/commit)·G4 sweep(run_hash 캐시·diagnostic)·R export | delta 뷰·preview 비오염·캐시 hit/miss·R SVG/TIFF | Plan §4.1·SC-4·SC-8 |

### 11.3 Session Guide (`/pdca do --scope`)

각 module은 독립 세션 단위. scope key로 `/pdca do --scope <key>` 호출.

#### Module Map

| module (scope key) | 설명 | 핵심 산출/SC | 예상 turns |
|--------------------|------|-------------|:----------:|
| **module-0** `foundation` | Qt shell·EngineService facade+JobRunner(cancel/retry)·SBML/JSON/MAT import·io(parquet/sqlite/yaml)·단일종 AN-SINGLE·RunManifest skeleton·solver capability matrix·**pickle-ban/ruff/black/mypy 설정** | FR-0.*·solver matrix(schema §5) | 8–12 |
| **module-1a** `headless-core` | `core/engine`(MICOM wrapper, public API only)·`core/namespace`(gate)·`core/sign`(단일 진입점)·`core/tidy`(계약+reader)·`core/interactions`(cross-feeding)·OSQP→LP 재계산·`core/manifest`(run_hash 11)·golden fixture+CI 매트릭스 | **SC-1·2·3·6·9** + run_hash | 14–20 |
| **module-1b** `gui-graph` | Cytoscape.js in QWebEngineView·노드/엣지 인코딩·레이아웃·필터·linked selection·Inspector·**gate UI**(coverage%·unresolved·차단 상태) | FR-1b.*·§11 | 8–12 |
| **module-1c** `validation` | MICOM 튜토리얼 재현(GUI/CLI 0-script)·cross-feeding sanity·**MICOM-version golden regression**(승격 게이트) | **SC-5·SC-7** | 5–8 |
| **module-2** `delta-sandbox-sweep-render` | `core/delta`(AN-DELTA)·`core/sandbox`(G1 preview/commit·debounced·FVA/no-change)·`core/sweep`(run_hash 캐시·실패 diagnostic·hit 표시)·Medium comparison/minimal medium(MILP)·`render_r`(R SVG/TIFF·Python fallback) | **SC-4·SC-8** + FR-2.* | 16–24 |

#### Recommended Session Plan

1. **세션 1 — `foundation`** (module-0): 기반·lint·capability matrix 먼저. 이후 모든 모듈의 전제(EngineService/JobRunner·io·pickle-ban).
2. **세션 2~3 — `headless-core`** (module-1a, **최우선·가장 큼**): turns가 많아 2세션 분할 권장 — (2a) engine wrapper+namespace gate+sign, (2b) tidy+interactions+OSQP→LP+manifest+golden. **MVP-1a DoD가 baseline 핵심 게이트**.
3. **세션 4 — `validation`** (module-1c): golden regression이 green이어야 GUI/MVP-2로 승격(SC-5). 가벼우므로 1a 직후 배치 가능.
4. **세션 5 — `gui-graph`** (module-1b): headless 산출(tidy)을 소비. 1c와 순서 교환 가능(둘 다 1a 의존).
5. **세션 6~7 — `delta-sandbox-sweep-render`** (module-2, 큼): (6) delta+sandbox(preview 비오염·SC-8), (7) sweep(캐시·diagnostic·SC-4)+R render. 분할 권장.

> **세션 분할 원칙**: turns≥14 모듈(1a·2)은 2세션으로 나눠 ≥90% 컨텍스트 유지(RULES). 각 세션은 해당 SC의 pytest(sign·gate·golden·cache·preview)가 green일 때만 완료 처리(quality gate).

---

I now have sufficient context. Writing the section.

## 12. Open Decisions — Design Resolutions

> **목적**: schema.md §9 / glossary §5의 **OD-1~OD-54**를 Option C (Pragmatic) 아키텍처 관점에서 분류·해소한다. **Resolved** = Option C의 layered `core/` + EngineService facade + thin seam(`SolverBackend`·MICOM `engine` wrapper·`Store` writer·`RenderClient`) + 직렬화 정책(Parquet/Arrow/JSON/YAML/SQLite, pickle 금지)이 **설계 결정만으로 확정 가능**한 것. **Deferred** = 데이터·실측·라이브러리 핀·실험 튜닝에 의존하여 **Do(구현/실측) 단계에서 확정**해야 하는 것.
>
> **원칙 (불변)**:
> - 모든 Resolved 결정은 spec/schema 불변식을 **위반하지 않는다**(예: run_hash 11개 고정 [HASH-11], env_lock 미포함 [HASH-ENVLOCK], pickle 금지 [NO-PICKLE], 단일 해시 정의 [HASH-SINGLE]).
> - Resolved 직렬화 규칙은 `core/manifest`·`core/sweep`·`io/` 모듈의 **단일 구현(single implementation)** 으로 강제되어 `AggregationStore.run_hash = RunManifest.run_hash = Scenario.run_hash` 비트 단위 일치를 보장한다(schema §4.3 [HASH-SINGLE]).
> - 수치 tolerance·임계값·formula·버전 핀 등 **값(value)** 은 golden fixture/실측으로 보정해야 하므로 Deferred로 둔다(우선 안전값 제시).

### 12.1 재현성·해시 (Reproducibility & Hash) — OD-10~OD-23

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-10** | checksum 해시 알고리즘 | **Resolved** | **SHA-256**. 모델/배지 입력 파일은 `io/` import 계층에서 **파일 바이트 스트림에 직접 SHA-256** 적용(정규화 없이 raw bytes → 입력 무결성 보존). `MemberModel.source.checksum`·`Medium.checksum`은 `sha256:<hex64>` 접두 형식으로 저장. run_hash와 동일 해시 함수 계열 사용으로 의존성 단순화(schema §4.2 #1·#2). |
| **OD-11** | run_hash 해시 함수·canonical 직렬화 | **Resolved** | **canonical = 11개 구성요소를 고정 key 이름으로 담은 dict → key 사전식(lexicographic) 정렬 → UTF-8 JSON(공백 없음 `separators=(",",":")`, `ensure_ascii=false`, NaN/Inf 금지) → SHA-256 → `sha256:<hex64>`.** 구성요소 key 순서는 직렬화 순서에 무관(정렬이 canonical 보장)하나 schema §4.2 #1~#11 번호를 key 이름 규약으로 고정. `core/manifest`의 단일 `compute_run_hash()`가 유일 진입점이며 EngineService·Store·Scenario commit 전부 이를 호출([HASH-SINGLE] 강제). 부동소수는 OD-12 rounding 적용 **후** 직렬화. (§10·§16·Plan §8.2) |
| **OD-12** | float rounding/tolerance 파라미터 | **Deferred** | rounding 메커니즘(**hash 전 round-half-to-even 적용**)은 설계 확정이나, **decimal 자릿수·abs/rel tol 값은 golden fixture 비교에서 alternate optima 잡음 폭을 보고 보정**해야 함. 시작 안전값: hash용 **6 decimal** round, golden 비교 **abs_tol=1e-6 · rel_tol=1e-6 병행**(둘 중 하나 충족 시 일치). Do에서 solver별 golden green이 안정될 때까지 조정. (§16·A17·SC-1) |
| **OD-13** | solver_setting 직렬화 필드 set (#7) | **Resolved** | run_hash #7 = **`{growth_solver, flux_solver, tolerance}`** 정확 3필드만 직렬화 포함. growth/flux solver는 **이름 문자열**(`gurobi`/`highs`/`osqp`/`cplex`), `tolerance`는 OD-12 rounding 적용 후 float. **벤더별 비결정 옵션(스레드 수·time limit·presolve 등)은 #7에서 제외**(재현성에 무관·플랫폼 의존). `flux_solver=null`(QP-only)도 명시적 null로 canonical 직렬화. (§4.2·§7·§10) |
| **OD-14** | RunManifest 직렬화 포맷·레이아웃 | **Resolved** | **메타 = YAML manifest 파일 + SQLite 인덱스**의 이원 구조. `Store` writer(thin seam)가 소유: (a) `manifest/<run_hash>.manifest.yaml` — 사람이 읽는 권위 레코드(전 블록 inputs/engine/solver/algorithms/sweep/software/figure_specs/platform/run_hash/manifest_schema_version), (b) SQLite `runs` 인덱스 테이블(`run_hash` PK, `created_ts`, `scenario_id`, `micom_version`, `status`, `manifest_path`) — 캐시 조회·sweep hit/miss 판정용. pickle 금지([NO-PICKLE]). schema_version 스킴 = `manifest_schema_version` 정수 monotonic. (§3·§8·Plan §7.2·§7.3) |
| **OD-15** | env_lock 직렬화 방식 | **Deferred** | **run_hash 11구성요소 미포함은 확정 불변식**([HASH-ENVLOCK])이며 `RunManifest.inputs.env_lock`에만 기록. 다만 lock **포맷**(conda `environment-lock.yml` vs `uv.lock` vs 해시)은 빌드/패키징 툴체인 채택에 의존 → Do(packaging) 착수 시 확정. 안전 기본: 채택 lock 파일 **전문(text) 임베드 + 그 SHA-256**. (§7·Plan §8.3) |
| **OD-16** | flux_normalization_method enum·필드 위치 | **Resolved (열린 enum)** | 필드 위치 = `Scenario.config.flux_normalization_method` → `RunManifest.algorithms.normalization` (#11). enum 시작 집합 = **`{pfba, pfba_loopless}`** (pFBA + tie-break 기본; loopless는 §4.4 옵션). 추가 method는 후속 확장 가능한 열린 enum. baseline 기본값 = `pfba`. (§4.4·§7·§10) |
| **OD-17** | cmig_core_version 보유 엔티티·주입 시점 | **Resolved** | run_hash #9의 source-of-truth = **`core` 패키지의 `__version__`** (single import). Scenario **commit 시점**에 EngineService가 주입 → `RunManifest.software.cmig_core_version` 및 `Scenario.cmig_core_version`에 동시 기록. preview에서는 미주입(run_hash null). §5 엔티티 필드 미명시는 manifest/commit 주입으로 해소([MANIFEST-CONSISTENCY]). (§7·§8) |
| **OD-18** | metric_mode enum 값셋 | **Deferred** | CMIG-MIP/MRO 산식(OD-52)에 종속. mode 컬럼 위치(`RunManifest.algorithms.metric_mode`)는 확정이나 값셋은 formula 확정 후. 안전 시작: `{cmig_default}` (+ optional `smetana_compatible`). (§4.5·§7) |
| **OD-19** | flux_report_status 대비 상태값 명칭 | **Resolved** | enum = **`{full, qp_only_approximate}`** (2값 폐쇄). `full` = LP flux_solver로 pFBA 재계산 완료, `qp_only_approximate` = LP 부재로 QP 근사(spec 명시값). `RunManifest.solver.flux_report_status`에 기록. (§4.2·§4.4·§7·SC-6) |
| **OD-20** | tolerance(solver)와 golden rounding 정합·값 | **Deferred** | 정합 **규칙**(solver tolerance ≤ golden rounding 정밀도여야 결정적 비교 성립)은 설계 확정이나, 구체 tolerance 값은 OD-12와 함께 golden 안정화에서 실측 보정. 안전 시작: solver `tolerance=1e-7`, golden round 6 decimal. (§4.2·§16) |
| **OD-21** | bounds(flux bound) 단위 | **Resolved** | **mmol/gDW/h** (flux bound 표준 단위)로 고정. `Scenario.constraints`·`Medium.composition`의 lower/upper bound 모두 동일 단위. uptake 허용 = 음수 lower_bound([MEDIUM-SIGN]). (§5·§7·§10·§4.3) |
| **OD-22** | manifest_schema_version 변경 시 캐시 마이그레이션 정책 | **Resolved** | **무효화(invalidate) 기본** — run_hash 구성요소 정의가 바뀌면 기존 `sweep.parquet`/SQLite 캐시 행을 **stale로 표시하고 재계산**(보존하되 재사용 금지). `manifest_schema_version` monotonic bump가 트리거. 재해시(rehash) 자동 변환은 금지(구성요소 의미 변경 시 위험). 마이그레이션 = 새 버전으로 re-solve. (Plan §6.2·§6.3·§9.1·SC-4) |
| **OD-23** | RunManifest.platform 세부 필드 | **Resolved (최소셋)** | run_hash **미포함**(재현성 무관·정보용). 최소셋 = **`{os∈{macos,windows,linux}, arch∈{arm64,x64}, python_version, solver_versions:map}`**. OS 패치 버전·하드웨어 상세는 정보 컬럼으로만(선택). (§7·§11) |

### 12.2 도메인 엔티티 (Domain Entities) — OD-1~OD-9

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-1** | ncbi_taxid 표현 타입 | **Resolved** | **string** 보관(선행 0·비정수 식별자 안전성, schema §3.1 권장). UI 표시/검색만 사용, 연산 없음. |
| **OD-2** | MemberModel.stats 필드 집합 | **Resolved** | **`struct{n_reactions, n_metabolites, n_genes, n_exchanges}`** 4필드 고정(schema §3.1 후보 채택). cobrapy 모델 로드 시 `io/` 계층이 결정적으로 계산. |
| **OD-3** | source.origin 허용값 | **Resolved (열린 enum)** | 시작 집합 = **`{bigg, agora, user, other}`** (열린 enum, 자유 문자열 fallback=`other`). provenance 정보용이며 gate/run_hash 미진입. |
| **OD-4** | abundance 단위·normalize 모드 | **Deferred** | 우선순위(`Scenario.abundance_overrides > MemberModel.abundance`)·normalize 후 합=1.0([ABUND-NORM]·[ABUND-PRIORITY])은 확정. 그러나 **절대(cell/biomass) vs 상대 dimensionless** 표현·절대→상대 변환 규칙은 데이터 입력 형태(사용자 abundance 제공 방식)에 의존 → Do에서 확정. 안전 기본: **상대(dimensionless) 단일 모드**, 입력은 normalize. (§5·§11) |
| **OD-5** | Medium.composition bound 단위 | **Resolved** | OD-21과 통일 = **mmol/gDW/h**. uptake=음수 lower_bound. (§4.3·§4.5·§5) |
| **OD-6** | namespace_convention 허용값 enum | **Resolved (열린 enum)** | 시작 집합 = **`{bigg, kegg, metanetx, seed, custom}`** (`SolverBackend`/gate 무관, namespace 정합 입력). 미지 규약=`custom`. gate(§4.8)는 convention 불일치를 mapping decision으로 처리. (§4.8) |
| **OD-7** | Medium preset 카탈로그·minimal tie-break | **Deferred** | preset 카탈로그(M9·gut-diet 등 구체 composition)는 **도메인 데이터**이며 큐레이션 필요 → Do. minimal medium tie-break는 **결정적 규칙**(예: metabolite id 사전식 최소) 설계는 가능하나 cardinality MILP solver 거동·seed와의 정합 실측 필요 → Do. 불변 U={H₂O,H⁺,Pi}([MIN-MEDIUM-U])는 확정. (§4.5) |
| **OD-8** | constraints.source 태그 표현 | **Resolved** | `Scenario.constraints[].source ∈ {user_edit, sandbox}` enum 그대로 채택. sandbox 출처 bound는 commit 시에만 run_hash #5 진입(preview는 비기록 [PREVIEW-NOWRITE]). `core/sandbox`가 source 태그 부여. (§10·A11) |
| **OD-9** | preview Scenario ephemeral 저장 위치/수명 | **Resolved** | **in-memory only** (JobRunner in-process 세션 메모리). preview solve 결과는 디스크 store/cache/sweep에 미기록([PREVIEW-NOWRITE]·SC-8), Apply/Save commit 시에만 `Store` writer가 artifact 승격. temp file 미사용(누수·오염 위험 회피). (§8·A11) |

### 12.3 Solver Capability — OD-24~OD-26

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-24** | growth_solver HiGHS-QP 허용·기본 정책 | **Resolved** | growth 기본 = **OSQP**(QP), flux LP = Gurobi 기본(default). `config.solver.growth_solver` enum에 `highs` 포함은 하되 **HiGHS-QP는 experimental 플래그**로만 노출(기본 비활성, OD-26). `SolverBackend` seam이 capability 질의로 강제. (§2·A6·SC-1) |
| **OD-25** | default solver 무라이선스 fallback 규칙 | **Deferred** | default=**Gurobi** 확정(Plan §7.2). 그러나 무라이선스 CI/환경에서 **자동 fallback 체인**(→highs/osqp) 발동 조건·사용자 알림 정책은 라이선스 탐지 거동 실측 필요 → Do. `SolverBackend.is_available()` seam은 설계 확정. (§2·Plan §7.2·R4) |
| **OD-26** | HiGHS-QP baseline 노출 여부 | **Resolved** | **baseline 비노출(disabled by default)**. HiGHS-QP=experimental이므로 QP 경로 기본은 OSQP. 활성화는 명시적 experimental 옵션. golden 변형 `osqp_growth_highs_flux`는 HiGHS를 **LP**로만 사용(QP 아님). (§2·A6) |

### 12.4 AggregationStore · Sweep — OD-27~OD-35

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-27** | condition_id 생성 규칙 | **Resolved** | **결정적 슬러그 = 축 값 정렬 dict의 SHA-256 단축(앞 16 hex)**, prefix `cond_`. 순차 인덱스 대신 결정적 슬러그 채택(재실행·캐시 정합 [CONDITION-CONSISTENCY] 보장, run_hash와 별개로 sweep 그리드 좌표 식별). `core/sweep`가 산출. (§5·§10) |
| **OD-28** | AggregationStore 경로·분할 | **Resolved** | **단일 `sweep.parquet`**(sweep run 디렉터리 1개당) long-format append. 파티셔닝은 baseline 미적용(파일 1개, `Store` writer 단일 reader 경유 [CARVE-OUT]). `schema_version` 컬럼 정수. 대규모 sweep 파티셔닝은 후속 최적화. (§5·Plan §6.2·§6.3) |
| **OD-29** | metric 허용 도메인 enum·value 단위 | **Resolved (열린 enum)** | 시작 집합 = **`{community_growth, member_growth, exchange_flux, fva_min, fva_max}`**. growth=1/h 또는 mmol/gDW/h(OD-4 따름), exchange/fva=mmol/gDW/h. value 단위는 metric별 메타로 기록. 확장 가능한 열린 enum. (§5·§10) |
| **OD-30** | 축 값 컬럼 직렬화 표현 | **Resolved** | long-format 단일 컬럼에 **결정적 식별자 문자열**: `axis_member_set`/`axis_bounds`/`axis_abundance` = 해당 구조의 **canonical JSON → SHA-256 단축 슬러그**(원본은 manifest에서 역참조), `axis_medium_variant`=preset/variant id, `axis_solver`=solver 이름, `axis_tradeoff_f`=float(rounding 적용). 스칼라 직접값 대신 슬러그+manifest 역참조로 일관. (§10) |
| **OD-31** | diagnostic 컬럼 구조 | **Resolved** | **구조화 JSON 문자열** = `{code, message, detail?}`. `code` = 폐쇄 enum(`infeasible`/`solver_error`/`capability_missing`/`qp_only_approximate`/`gate_blocked`). status=failed에 필수(≠null [STATUS-CLOSED]). 자유 텍스트는 `message`. (§5·§10·§4.4) |
| **OD-32** | solver 축 enum 전체 목록 | **Resolved** | `axis_solver ∈ {gurobi, highs, osqp, cplex}` (§2 matrix solver 이름). **`osqp_growth_highs_flux`는 golden 세트 명이지 축 값 아님**(schema §6.1 주의 준수). (§2·§10) |
| **OD-33** | condition_id↔run_hash 매핑 표현 | **Resolved** | `RunManifest.sweep`에 **정렬된 list of `{condition_id, run_hash}`** 인라인(별도 테이블 불필요, n_runs 소규모 baseline). `n_runs = Π(축별 n_values) = len(목록)` 정합 검증([CONDITION-CONSISTENCY]). SQLite 인덱스가 빠른 조회 보조. (§7·§10) |
| **OD-34** | axis_tradeoff_f 값 도메인 | **Resolved** | **0 < f ≤ 1**([TRADEOFF-RANGE] 준수). 경계: f=1 허용(=μ_c*), f≤0 거부(validation error). run_hash #6 진입 시 OD-12 rounding. (§10·§4.2) |
| **OD-35** | status=ok 행 diagnostic 정책 | **Resolved** | status=ok에서도 **비-실패 진단 허용**(같은 컬럼) — 예 `code=qp_only_approximate`(ok이나 LP 부재 근사) 또는 `code=capability_missing`(강등). ok에서 정상이면 null. failed에서만 필수. (§5·§10) |

### 12.5 Namespace · Gate · Sign — OD-36~OD-44

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-36** | confidence(high/low) 산출 알고리즘·임계 | **Deferred** | gate 거동(high+unresolved→차단, low→warn [GATE-BLOCK])은 확정. 그러나 confidence **산정 방식**(exact id match / synonym DB / 매핑 거리)·임계값은 namespace 매핑 데이터·MetaNetX 등 참조 자원에 의존 → Do. 안전 기본: exact canonical id match=high, fuzzy/synonym=low. (§4.8) |
| **OD-37** | NamespaceDecision.target_id nullability | **Resolved** | **`unresolved ⇒ target_id=null`** (별도 상태 필드 불필요, `decision` enum이 상태 보유). resolved/warned ⇒ target_id non-null. canonical 직렬화에서 null 명시. (§4.8) |
| **OD-38** | audit_ts timezone·정밀도·포맷 | **Resolved** | **UTC ISO-8601, 밀리초(ms) 정밀도**, 포맷 `YYYY-MM-DDTHH:MM:SS.sssZ`. 모든 audit/manifest timestamp 통일. **단, run_hash #10 namespace_decisions 직렬화에서는 audit_ts 제외**(비결정 시각이 hash를 오염하지 않도록 — decision 의미값만 hash, OD-39). (§4.8) |
| **OD-39** | namespace_mapping_decisions run_hash 직렬화 규칙 | **Resolved** | run_hash #10 = **decision 레코드를 `{metabolite, source_id, target_id, confidence, decision}` 5필드로 투영 → `metabolite` 사전식 정렬 → canonical JSON**. **`rationale`·`audit_ts` 제외**(audit 전용·비결정). 정렬+투영으로 동일 매핑 집합→동일 hash 보장([HASH-SINGLE]). (§4.8·§5·§7) |
| **OD-40** | coverage_pct 분모 정의 | **Deferred** | 산출식(`resolved / 전체 exchange metabolite`)의 **분모 = 멤버별 exchange metabolite 합집합(union)** 을 권장하나, pool 기준 vs union 선택은 실제 모델 exchange 정의 분포 확인 후 확정 → Do. UI 노출(Model Manager coverage%·unresolved 바로가기)은 확정. (§11) |
| **OD-41** | gate audit_trail 저장 매체 | **Resolved** | **SQLite 테이블** `namespace_decisions`(run_hash FK·metabolite·source_id·target_id·confidence·decision·rationale·audit_ts). 메타=YAML+SQLite 정책 일관(§8). ndjson 대신 SQLite(질의·조인 용이). `NamespaceGateResult.audit_trail_ref` = SQLite 핸들/run_hash 키. (§8) |
| **OD-42** | gate 차단 해소 워크플로(mapping wizard) | **Deferred** | baseline gate는 **차단·경고·audit·바로가기 표시까지** 확정. 본격 수동 매핑 wizard UI는 spec §16에서 **MVP-3/host 명시**(범위 경계) → Do(후속). baseline은 unresolved 목록 표시 + 사용자 수동 mapping 입력의 최소 경로. (§4.8·§16) |
| **OD-43** | 멤버↔pool '분비' label enum 통일 | **Resolved** | **`secretion`으로 통일**(단일 enum `{uptake, secretion}`). schema §3.3 profile.label·canonical case [SIGN-4]의 멤버↔pool '분비'를 환경 secretion과 **동일 enum 값**으로 정규화. 한국어 '분비'는 UI 표시 라벨(i18n)일 뿐 내부 enum은 `secretion`. `core/sign` 단일 진입점([SIGN-2])이 강제. (§4.7) |
| **OD-44** | flux 단위 정규화 표기·ui_flux 단위 문자열 | **Resolved** | ui_flux 단위 = **mmol/gDW/h** magnitude(≥0 [SIGN-3]). QP-only 산출도 동일 단위 문자열, 신뢰도는 `flux_report_status`(OD-19)로 구분(단위 문자열 변경 없음). (§4.4) |

### 12.6 Tidy 계약 · Golden — OD-45~OD-54

| OD | 항목 | 상태 | 결정 또는 보류 사유 |
|----|------|------|---------------------|
| **OD-45** | tidy 5종 컬럼 표준명·edge_type 전체 집합 | **Resolved (컬럼명) / Deferred (typing 확장)** | 컬럼 표준명 = schema §2.1~§2.5 권장 스키마 채택(nodes: `schema_version·node_id·node_type·label·growth·abundance` 등). `node_type ∈ {member, environment_pool}`. **edge_type 시작 집합 = `{cross_feeding}`** (baseline 추출 대상). interaction typing·MIP/MRO edge 추가 집합은 OD-52 산식·typing 정의에 의존 → **Deferred**. 모든 산출은 단일 reader 경유(§4.6). (§4.6) |
| **OD-46** | tidy schema_version 경계·엔티티 매핑 | **Resolved** | `schema_version`은 **tidy 계약(5 parquet) 전용 정수**이며 도메인 엔티티(MemberModel/Scenario)·`AggregationStore.schema_version`·`manifest_schema_version`과 **독립적으로 bump**. 계약(컬럼) 변경 시에만 tidy schema_version 증가. 단일 reader/계약 테스트 기준(SC-9). (§4.6·Plan §6.3) |
| **OD-47** | golden normalized_hash 알고리즘·컬럼 정규화 | **Resolved** | golden 비교 hash = **컬럼명 사전식 정렬 → 행 결정적 정렬(key 컬럼 기준) → float 컬럼 OD-12 rounding → canonical Arrow/parquet 직렬화 → SHA-256**. NaN은 null로 정규화. run_hash와 동일 SHA-256 계열·동일 rounding 정책 재사용. (§16·A17·SC-1) |
| **OD-48** | golden solver_variant 디렉터리 레이아웃 | **Resolved** | **입력 공유 + expected solver별 분리**: `models/`·`medium.yaml`·`config.yaml`은 solver 무관 공유, `expected/{gurobi,highs,osqp_growth_highs_flux}/`만 분리(schema §7.4 트리·중복 회피). CI 매트릭스가 variant 순회. (§16·A17·SC-1·SC-6) |
| **OD-49** | golden config.yaml 전체 필드 스키마 | **Resolved** | config.yaml = **run_hash 정합 필드 전부 포함**: `tradeoff_f·seed·micom_version·growth_solver·flux_solver·tolerance·flux_normalization_method`(= run_hash #6·#7·#8·#11 + seed). golden이 run_hash 재현을 직접 검증하도록 정합. checksum(#1·#2)은 fixture 파일에서 산출. (§16·SC-1·SC-5) |
| **OD-50** | osqp_growth_highs_flux LP 재계산 tolerance 허용오차 | **Deferred** | OSQP→HiGHS LP 경로가 gurobi golden과 **float tolerance 내 일치**해야 함(SC-6 [SOLVER-SPLIT])은 확정. 그러나 허용오차 **값**은 OSQP QP 수렴·HiGHS LP 재계산 잔차를 실측해 보정 → Do. 시작 안전값 = OD-12 golden tolerance(abs/rel 1e-6) 재사용, 미통과 시 variant별 완화. (§16·§4.2·A6·SC-6) |
| **OD-51** | MICOM exact pin 버전 | **Deferred** | exact pin([MICOM-PIN])·승격 게이트(solver별 golden 전부 통과 시에만 [MICOM-PIN]·SC-5)는 확정 불변식. 구체 `micom==X.Y.Z`는 **Do 착수 시 최신 stable 버전을 확정·핀**(public API + documented flux only 호환 검증 후). MICOM `engine` wrapper(thin seam)가 단일 진입점으로 버전 고립. (§4.1·§16·SC-5) |
| **OD-52** | CMIG-MIP/MRO 정확 산식·SMETANA 매핑 | **Deferred** | CMIG-defined 지표의 **formula는 도메인 산식 결정**이며 cross-feeding/resource-overlap 정의·optional SMETANA-compatible 매핑 검증 필요 → Do. `core/interactions`가 소유. OD-18 metric_mode·OD-45 edge_type 확장이 이에 종속. (§4.5·A9) |
| **OD-53** | 'no significant change' 진단 임계 | **Deferred** | G1 sandbox 보상 우회 시 FVA 범위 대비 변화량 판정([AN-SANDBOX])은 **실측 임계**(변화량/FVA 범위 비율)가 필요 → Do. 진단 메커니즘(FVA 범위 표시 + diagnostic code)은 설계 확정. 안전 시작: |Δprofile| < OD-12 abs_tol 또는 FVA 범위 폭 대비 <1% → `no_significant_change`. (§10 AN-SANDBOX·§17) |
| **OD-54** | debounced re-solve debounce 지연·취소 정책 | **Deferred** | 메커니즘(debounce + JobRunner cancel/retry [debounced re-solve])은 Option C JobRunner로 설계 확정. **지연(ms)·취소 정책 값**은 인터랙티브 latency·UI 프리즈 0 NFR을 충족하도록 실사용 측정 후 튜닝 → Do. 시작 안전값: **debounce 300ms**, 새 입력 시 진행 중 job **cancel 후 재투입**. (§4.2·§10·§8) |

### 12.7 해소 요약 (Resolution Summary)

| 분류 | Resolved | Deferred |
|------|---------|----------|
| 재현성·해시 (OD-10~23) | OD-10·11·13·14·16·17·19·21·22·23 | OD-12·15·18·20 |
| 도메인 엔티티 (OD-1~9) | OD-1·2·3·5·6·8·9 | OD-4·7 |
| Solver (OD-24~26) | OD-24·26 | OD-25 |
| AggregationStore·Sweep (OD-27~35) | OD-27·28·29·30·31·32·33·34·35 | — |
| Namespace·Gate·Sign (OD-36~44) | OD-37·38·39·41·43·44 | OD-36·40·42 |
| Tidy·Golden (OD-45~54) | OD-45(컬럼)·46·47·48·49 | OD-45(typing)·50·51·52·53·54 |

> **Resolved 36 / Deferred 19** (OD-45 양분 카운트). Option C 아키텍처는 **직렬화·canonical hash·store 레이아웃·enum·gate audit 매체·sign 통일** 등 **계약·구조 결정을 전면 해소**한다. Deferred는 모두 **(a) 수치 tolerance·임계값**(OD-12·20·50·53·54), **(b) 도메인 산식/데이터**(OD-7·18·36·40·52), **(c) 라이브러리 핀·패키징**(OD-15·25·51), **(d) 후속 범위 UI**(OD-42·OD-45 typing)로, 모두 **Do(구현/실측/큐레이션) 단계 또는 후속 MVP**에서 확정한다. 각 Deferred는 위 안전 시작값을 가지므로 baseline 구현은 차단되지 않는다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-31 | Initial Design (Option C Pragmatic) — 7-section workflow + critic | PDCA Design |
