---
template: plan
version: 1.3
feature: cmig-community-core
project: CMIG (Community Metabolic Interaction GUI)
version_project: 0.1.0 (pre-MVP)
author: PDCA Plan (Daniel + Claude)
date: 2026-05-31
status: Draft
---

# cmig-community-core Planning Document

> **Summary**: 커뮤니티 FBA를 **MICOM(정확 pin·public API only)** 에 위임하고, CMIG가 namespace 정합·sign 정규화·tidy 계약·cross-feeding/delta 추출·G1 constraint sandbox·G4 sweep·R 출판 그림의 **부가가치 계층**을 소유하는 PySide6 네이티브 데스크톱 도구의 **PART I Implementation Baseline (MVP-0~2)** 계획.
>
> **Project**: CMIG (Community Metabolic Interaction GUI) — native desktop scientific app (NOT SaaS/web)
> **Platform**: macOS Apple Silicon (Must) · Windows 10/11 x64 (Must) · macOS Intel/Linux (Should)
> **Stack**: PySide6/Qt GUI + Python sidecar (cobrapy + MICOM + CMIG core) · R Render(별도 프로세스) · optional Docker/Remote
> **Author**: PDCA Plan
> **Date**: 2026-05-31
> **Status**: Draft
> **Authoritative ground truth**: `CMIG_명세서_v3.0.md` (§1–§11, §16). 본 Plan은 명세와 모순되지 않으며, PRD(`docs/00-pm/cmig-community-core.prd.md`)를 상위 참조한다.

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 미생물 community 대사 상호작용 분석(cross-feeding·external profile·멤버 추가 영향)이 MICOM/SMETANA 같은 **스크립트 전용**에 갇혀, 인터랙티브 가설형성·재현성·출판품질이 단절됨. |
| **Solution** | community FBA는 **MICOM에 위임**(정확 pin·public API+documented flux only)하고, CMIG가 **namespace hard gate·sign 정규화·tidy 계약·cross-feeding/delta·G1 sandbox·G4 sweep·R 그림**을 소유하는 PySide6 네이티브 GUI + Python sidecar. 모든 산출은 **run_hash 재현성**과 **solver별 golden fixture**로 검증. |
| **Function/UX Effect** | (1) Headless 커뮤니티 코어(CLI/GUI 공통), (2) Cytoscape.js interaction graph(QWebEngine), (3) **add-member delta** + **constraint sandbox**(bound 제약 변경+재최적화, preview→Apply 승격), (4) sweep 배치(run_hash 캐시·실패 diagnostic), (5) SVG/TIFF 출판 그림. |
| **Core Value** | community-FBA를 **스크립트 전문가 워크플로 → 인터랙티브·재현 가능·출판 준비 데스크톱 도구**로 전환. **run_hash 재현성 + namespace 무결성**을 일급으로. |

---

## Context Anchor

> Executive Summary·Requirements·Risk에서 추출. Design/Do 문서로 전파되어 세션 간 컨텍스트 연속성 보장.

| Key | Value |
|-----|-------|
| **WHY** | community 대사 상호작용 분석이 스크립트 전용에 갇혀 인터랙티브 가설형성·재현성·출판품질이 단절됨 |
| **WHO** | 전산/시스템 생물학자, microbiome·gut-microbiota 연구자, 미생물 community 대사공학자 (2차: bioinformatics core facility, constraint-based modeling 대학원생) |
| **RISK** | (R1) MICOM API/버전 drift → golden 승격 게이트, (R2) namespace mismatch/sign 혼동 silent error → hard gate + sign 테스트 CI, (R3) OSQP LP 정확도/alternate-optima 잡음 → growth QP→flux LP 재계산 + float tolerance hash |
| **SUCCESS** | solver별 golden fixture 통과(Gurobi 기본·highs·osqp_growth_highs_flux) · sign-test CI green · namespace gate 차단 동작 · run_hash 캐시 정확성 · MICOM-version golden regression(승격 게이트) |
| **SCOPE** | MVP-0 Foundation → MVP-1a Headless core(1순위) → MVP-1b GUI graph → MVP-1c validation → MVP-2 delta/medium/R export/G1 sandbox/G4 sweep. **PART II(host-microbe/G2·dFBA·다중타깃/G3·통계/G5·Escher)는 범위 외.** |

---

## 1. Overview

### 1.1 Purpose
미생물 community의 대사 상호작용을 **스크립트 없이 인터랙티브하게 분석·재현·출판**할 수 있는 네이티브 데스크톱 도구의 baseline(MVP-0~2)을 구현한다. community FBA solve는 MICOM에 위임하고, CMIG는 그 위에서 정확성(namespace gate·sign)·해석(cross-feeding·delta)·탐색(sandbox·sweep)·재현(run_hash·golden)·출판(R 그림)을 책임진다.

### 1.2 Background
- 명세 §1: 차별점 = ① 멤버 추가 시 상호작용 변화(delta) ② external 프로파일 ③ 미생물–미생물 interaction ④ 특정 물질 생산 조합.
- 경쟁 공백(PRD §3.2): MICOM=라이브러리(GUI 없음), SMETANA=CLI, CNApy=단일종 GUI. **community FBA를 MICOM에 위임하면서 interaction/delta/sandbox/sweep + 출판급 R 그림을 소유하는 유일한 네이티브 GUI**가 CMIG의 wedge.
- Build vs Buy(§2): 엔진은 buy(MICOM Apache-2.0), 부가가치 계층은 own.

### 1.3 Related Documents
- PRD: `docs/00-pm/cmig-community-core.prd.md`
- Ground truth 명세: `CMIG_명세서_v3.0.md` (§1–§11, §16, 부록 A)
- 다음: Design `docs/02-design/features/cmig-community-core.design.md` (예정)

---

## 2. Scope

### 2.1 In Scope (MVP-0 ~ MVP-2)

**MVP-0 Foundation**
- [ ] PySide6 Qt shell — Project Explorer / Model Manager / Medium Editor 골격
- [ ] Python sidecar + **Engine Interface**(계산은 GUI 밖 job; in-process 우선, 장기 작업 cancel/retry)
- [ ] SBML import(+JSON/MAT) · model summary · reaction/metabolite/gene 테이블(필터·정렬·다중선택)
- [ ] 기본 Medium Editor(CSV paste·preset·Check Growth)
- [ ] 단일종 AN-SINGLE: FBA/pFBA · knockout · exchange 요약 · growth feasibility · bound 편집
- [ ] **RunManifest** 기록 + **solver capability matrix**(LP/QP/MILP; **GLPK 비번들=GPL**; capability 부재 시 해당 분석 비활성화)

**MVP-1a Headless 커뮤니티 코어 (1순위)**
- [ ] **MICOM 통합** — 정확 pin(`micom==X.Y.Z`), **public API + documented flux only**(`cooperative_tradeoff(fluxes=True, pfba=...)`), internal 금지
- [ ] **Namespace hard gate(§4.8)** — unresolved high-confidence exchange mapping → solve 차단·해소 요구; low-confidence 경고 후 진행·자동병합 금지·audit trail
- [ ] **Sign 테스트 계약(§4.7)** — MICOM flux→(ui_flux,label) 단위테스트 + canonical case CI
- [ ] **Tidy 데이터 계약**(nodes/edges/profile parquet)
- [ ] Community/member growth · exchange decomposition · cross-feeding 추출(분비+ ∧ 흡수−, weight=min) · external profile
- [ ] **OSQP growth → LP pFBA flux 재계산(§4.2)** — growth 확보 후 community constraint 고정→LP(**Gurobi 기본**/HiGHS/CPLEX) pFBA/정규화 재수행; LP 부재 시 "QP-only approximate" 표기; growth/flux solver 분리 기록
- [ ] **Golden fixture**(`fixtures/community_3_member/`) — float rounding/tolerance 후 hash; **solver별 분리**(`gurobi`·`highs`·`osqp_growth_highs_flux`) CI 매트릭스

**MVP-1b GUI Graph**
- [ ] **Interaction Graph Viewer** — Cytoscape.js in QWebEngineView; 노드/엣지 인코딩·레이아웃
- [ ] 필터 · linked selection/highlight · Inspector
- [ ] **Gate UI** — namespace coverage%·unresolved 바로가기·차단 상태

**MVP-1c 검증 (승격 게이트)**
- [ ] MICOM 튜토리얼 재현(GUI/CLI, 스크립트 0줄)
- [ ] cross-feeding sanity + sign 테스트 통과
- [ ] **MICOM-version golden regression**(버전 업그레이드는 golden 통과 후에만 승격)

**MVP-2 Delta · Medium · R export · G1 sandbox · G4 sweep**
- [ ] AN-DELTA(add-member delta) — baseline 복제→멤버 추가→동일 조건 재solve→delta 뷰/network/heatmap
- [ ] Scenario Compare(A/B 또는 N)·동일 조건 고정 토글
- [ ] Medium comparison · minimal medium(cardinality MILP) · limiting nutrient · sensitivity
- [ ] CMIG-MIP/MRO + interaction typing
- [ ] **R Render Service**(별도 프로세스) — SVG(svglite)/TIFF(ragg 600dpi LZW)·Figure Composer·figure_spec 재현·Python fallback
- [ ] **G1 Constraint Sandbox** — bound constraint 변경+재최적화(flux 직접 편집 아님)·debounced 재solve·external-profile delta 오버레이·보상 우회 시 FVA/no-change·**preview 기본(store/cache 비기록)→Apply/Save 시 artifact 승격**
- [ ] **G4 Sweep** — 축×값→N-run 배치 job→long-format `sweep.parquet`·**run_hash 캐시**·**실패 run diagnostic 저장(누락 금지)**·캐시 hit 표시

### 2.2 Out of Scope (PART II — 향후 로드맵)
- **G2 Host-Microbe**(MVP-3, 선행 spike 필수) — Human-GEM·viability constraint·2-interface (§12)
- **dFBA**(MVP-3) — well-mixed dynamic FBA (§13)
- **G3 Consortium Search 단일·다중 타깃**(MVP-4) — targets[]·Pareto≤2 (§14)
- **G5 통계**(MVP-5) — 5a→5b→5c (§15)
- **Escher Metabolic Map** — optional post-MVP (§11)
- **서명 인스톨러(.app/.exe) 배포 패키징** — 본 baseline은 소스/개발 실행(conda/uv) 우선; 인스톨러는 Pipeline 배포 단계로 분리

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-0.1 | PySide6 Qt shell (Explorer/Model Manager/Medium Editor 골격) | High | Pending |
| FR-0.2 | Python sidecar + Engine Interface (계산 GUI 밖 job, cancel/retry) | High | Pending |
| FR-0.3 | SBML/JSON/MAT import · summary · reaction/metabolite/gene 테이블 | High | Pending |
| FR-0.4 | 기본 Medium Editor (CSV paste·preset·Check Growth) | Medium | Pending |
| FR-0.5 | 단일종 FBA/pFBA·knockout·exchange 요약·bound 편집·feasibility | High | Pending |
| FR-0.6 | RunManifest + solver capability matrix (GLPK 비번들) | High | Pending |
| FR-1a.1 | MICOM 통합 (정확 pin·public API+documented flux only) | **Critical** | Pending |
| FR-1a.2 | Namespace hard gate (§4.8) — unresolved high-confidence → solve 차단 | **Critical** | Pending |
| FR-1a.3 | Sign 테스트 계약 (§4.7) — 단위테스트 + canonical CI | **Critical** | Pending |
| FR-1a.4 | Tidy 데이터 계약 출력 (nodes/edges/profile parquet) | High | Pending |
| FR-1a.5 | Community/member growth·exchange decomposition·cross-feeding 추출·external profile | **Critical** | Pending |
| FR-1a.6 | OSQP growth → LP pFBA flux 재계산 (§4.2)·QP-only 표기·solver 분리 기록 | **Critical** | Pending |
| FR-1a.7 | Golden fixture (solver별 분리·float tolerance hash) | **Critical** | Pending |
| FR-1b.1 | Interaction Graph Viewer (Cytoscape.js + QWebEngineView) | High | Pending |
| FR-1b.2 | 필터·linked selection·Inspector | Medium | Pending |
| FR-1b.3 | Gate UI (coverage%·unresolved 바로가기·차단 상태) | High | Pending |
| FR-1c.1 | MICOM 튜토리얼 재현 (스크립트 0줄) | High | Pending |
| FR-1c.2 | cross-feeding sanity + sign 테스트 통과 | High | Pending |
| FR-1c.3 | MICOM-version golden regression (승격 게이트) | High | Pending |
| FR-2.1 | AN-DELTA (add-member delta·delta network·delta heatmap) | High | Pending |
| FR-2.2 | Scenario Compare (A/B/N·동일조건 고정) | Medium | Pending |
| FR-2.3 | Medium comparison·minimal medium(MILP)·limiting·sensitivity | Medium | Pending |
| FR-2.4 | CMIG-MIP/MRO + interaction typing | Medium | Pending |
| FR-2.5 | R Render Service (SVG/TIFF·Figure Composer·figure_spec·fallback) | Medium | Pending |
| FR-2.6 | G1 Constraint Sandbox (bound 제약+재최적화·preview→Apply 승격·FVA/no-change) | High | Pending |
| FR-2.7 | G4 Sweep (run_hash 캐시·실패 diagnostic·캐시 hit 표시) | High | Pending |
| FR-2.8 | run_hash 정의 준수 (11개 구성요소) | **Critical** | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|--------------------|
| Performance | 계산은 GUI 밖(job)·Parquet I/O·lazy graph·non-blocking(진행률·취소). sandbox 재solve는 debounce 내 인터랙티브 | sandbox latency spike·UI 프리즈 0 |
| Security | 127.0.0.1 바인딩·토큰·docker socket 미마운트·**pickle 금지** | 코드 스캔·import 경로 검사 |
| Reliability | GUI 생존·cancel/retry·infeasible diagnostic·capability 강등·QP-only 표기·gate 차단·sandbox preview 비기록 | 장애 주입 테스트 |
| License | cobrapy LGPL(재검증)·**GLPK 미번들(GPL)**·Gurobi WLS 학술·**R 프로세스 격리** | 의존성 라이선스 audit |
| Reproducibility | figure_spec·MICOM golden 승격·sweep/seed 기록·**run_hash에 micom/cmig 버전·namespace 결정·normalization 포함** | run_hash 결정성 테스트·golden CI |
| i18n/Accessibility | 한/영 토글·고대비 테마·**부호 범례 상시** | UI 검증 |
| Platform | macOS Apple Silicon(Must)·Windows x64(Must)·macOS Intel/Linux(Should) | CI 매트릭스(가능 범위) |

---

## 4. Success Criteria

### 4.1 Definition of Done (baseline)
- [ ] MVP-1a 완료 정의: **CLI 3개+ 미생물·배지에서 산출 + sign 테스트 통과 + namespace gate 동작 + solver별 golden fixture 통과**
- [ ] MVP-1c 승격 게이트: MICOM 튜토리얼 재현 + cross-feeding sanity + MICOM-version golden regression 통과
- [ ] MVP-2: add-member delta·G1 sandbox(preview/commit 분리)·G4 sweep(run_hash 캐시·실패 diagnostic)·R export 동작
- [ ] tidy 계약(nodes/edges/profile parquet) 스키마 일치
- [ ] RunManifest/run_hash 11개 구성요소 기록

### 4.2 Quality Criteria (측정 가능 — 명세 acceptance gate 앵커)

| # | Success Criteria | 측정/Evidence | 앵커 |
|---|---|---|---|
| SC-1 | **Golden fixture 통과(solver별)** — gurobi(기본)·highs·osqp_growth_highs_flux 각각 expected_nodes/edges/profile.parquet과 float tolerance 후 hash 일치 | CI 매트릭스 green | §10·§16·A17 |
| SC-2 | **Sign-test CI green** — 환경 −10→uptake10/+8→secretion8; 멤버↔pool −5→uptake5/+3→분비3 | sign_expected.tsv 일치 | §4.7·A10 |
| SC-3 | **Namespace gate 차단 동작** — unresolved high-confidence fixture → solve 차단+해소 요구; low-confidence → 경고·진행·자동병합 없음·audit | gate blocking test | §4.8·A10 |
| SC-4 | **run_hash 캐시 정확성** — 동일 11구성요소 hit; 1개 변경 miss·재계산; 실패 run diagnostic 누락 0 | 캐시 hit/miss 테스트 | §5·§10·A14 |
| SC-5 | **MICOM-version golden regression** — 버전 상향은 golden 통과 시에만 승격, 미통과 시 차단 | regression CI | §4.1·§16·§17 |
| SC-6 | **OSQP→LP 재계산 정확성** — osqp golden이 gurobi golden과 tolerance 내 일치; LP 부재 시 "QP-only approximate" | solver별 golden 비교 | §4.2·A6 |
| SC-7 | **MICOM 튜토리얼 재현** — 스크립트 0줄 GUI/CLI 재현 + cross-feeding sanity | MVP-1c 재현 로그 | §16 |
| SC-8 | **Sandbox preview 비오염** — preview는 store/cache 비기록; Apply/Save 시에만 승격; 보상 우회 시 FVA/no-change | preview/commit 분리 테스트 | §4.2·§8·A11 |
| SC-9 | **tidy 계약 준수** — 모든 산출이 nodes/edges/profile parquet 스키마 일치 | schema 검증 | §4.6 |

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| R1 MICOM API/버전 drift로 산출 변화·깨짐 | High | Medium | 정확 pin + public API only + **golden 승격 게이트(SC-5)**; 미노출 기능은 upstream PR (§4.1·§17) |
| R2 namespace mismatch/sign 혼동의 silent 잘못된 cross-feeding 결론 | High | Medium | **hard gate 차단(SC-3)** + **sign 테스트 CI(SC-2)** + 단일 진입점 변환 (§4.7·§4.8) |
| R3 OSQP LP 정확도/alternate-optima 잡음으로 golden 불안정 | High | Medium | **OSQP growth→LP pFBA 재계산** + **float rounding/tolerance 후 hash** + solver별 golden 분리(SC-1·SC-6) (§4.2·§16) |
| R4 Gurobi 라이선스 의존(기본 solver) — CI/사용자 진입장벽 | Medium | Medium | CI에 Gurobi WLS; golden은 highs·osqp 변형도 유지하여 무라이선스 경로 보존; capability 부재 시 강등 (§2·§A6) |
| R5 QWebEngine(Cytoscape.js) 의존·플랫폼별 빌드 차이 | Medium | Medium | Engine Interface로 graph 데이터(tidy)와 렌더 분리; 렌더 실패 시 텍스트/테이블 fallback |
| R6 과범위(scope creep)로 baseline 일정·검증 초점 흐림 | Medium | Medium | Baseline/Extension **엄격 분리**(§16·A16); PART II는 본 Plan Out of Scope |
| R7 GLPK(GPL)/R(GPL) 라이선스 오염 | High | Low | **GLPK 미번들**·R **프로세스 격리**·cobrapy LGPL 재검증 (NFR-License) |

---

## 6. Impact Analysis

> Greenfield baseline — 기존 소비자 없음. 신규로 생성되는 핵심 리소스(계약/스키마)와 향후 변경 시 깨질 수 있는 내부 계약을 인벤토리한다.

### 6.1 Changed/New Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| Tidy 데이터 계약 (`nodes/edges/profile/matrix/timecourse`) | Schema (parquet) | 신규 — 전 분석 산출의 단일 출력 계약 (§4.6) |
| Engine Interface | API (Python sidecar 경계) | 신규 — GUI↔sidecar 계산 호출 추상화 |
| Sign 변환 계층 (MICOM flux → ui_flux,label) | 내부 계약 | 신규 — 부호 규약 단일 진입점 (§4.3·§4.7) |
| RunManifest / run_hash (11 구성요소) | Schema/Config | 신규 — 재현성·sweep 캐시 키 (§5·§7) |
| Namespace mapping decisions | Config/Audit | 신규 — gate 입력·run_hash 구성요소 (§4.8) |
| Golden fixture (solver별) | Test asset | 신규 — `fixtures/community_3_member/` + `expected/` (§16) |
| AggregationStore `sweep.parquet` | Schema (parquet) | 신규 — long-format 집계·run_hash·status·diagnostic (§5) |

### 6.2 Current Consumers
해당 없음(greenfield). 단, **내부 계약 변경 시 깨질 잠재 소비자**를 사전 식별:
- Tidy 스키마 변경 → graph viewer·profile viewer·delta·sweep·R export 전부 영향 → **스키마 버전 필드 + 계약 테스트 필수**.
- run_hash 구성요소 변경 → sweep 캐시 무효화 → **버전 bump + 캐시 마이그레이션 정책 필요**.
- sign 변환 규약 변경 → 모든 cross-feeding/delta 해석 영향 → **sign_expected.tsv 회귀 테스트가 gate**.

### 6.3 Verification
- [ ] Tidy 계약은 스키마 버전 필드를 가지며 모든 소비자가 단일 reader 경유
- [ ] run_hash 구성요소 변경 시 캐시 무효화·버전 bump 규칙 문서화
- [ ] sign/golden 회귀 테스트가 CI 필수 게이트로 등록
- [ ] namespace gate 차단/경고 동작이 audit trail에 기록

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

> ⚠️ bkit 표준 레벨(Starter/Dynamic/Enterprise)은 **웹 스택 기준**이라 본 프로젝트(Python/Qt 데스크톱 과학 도구)에 정확히 맞지 않는다. 구조적 복잡도(레이어 분리·엔진 위임·재현성 계약) 측면에서 **Enterprise에 준하는 모듈 분리**를 채택하되, 웹/BaaS 요소는 전부 제외한다.

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| Starter | 단순 구조 | ☐ |
| Dynamic | feature 모듈 + BaaS(bkend.ai) | ☐ (웹 전용 — 부적합) |
| Enterprise | 엄격한 레이어 분리·DI | ☑ (구조 모델만 차용, 웹 요소 제외) |
| **Native Desktop (CMIG 실제)** | **PySide6 GUI / Python sidecar(엔진 위임) / R 격리 프로세스** | ☑ **채택** |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| GUI Framework | PySide6 / PyQt / Electron / Tauri | **PySide6 (Qt)** | 명세 확정. 네이티브·과학 GUI 생태계·LGPL |
| Community FBA Engine | MICOM / 자체 구현 / SMETANA | **MICOM (정확 pin·public API only)** | §2 Build vs Buy — 엔진 buy, 부가가치 own |
| GUI↔Engine 경계 | in-process / subprocess+IPC / local FastAPI | **in-process sidecar(우선) + job runner** | 단순·낮은 지연; 원격은 optional FastAPI(§3). 장기작업은 cancel/retry job |
| 기본/CI Solver | Gurobi / HiGHS / 둘 다 동등 | **Gurobi 기본** (golden 3종 유지) | 사용자 결정. CI=Gurobi WLS; highs·osqp_growth_highs_flux golden으로 무라이선스 경로 보존 |
| Growth/Flux Solver 분리 | 단일 / QP→LP 분리 | **OSQP(QP growth) → LP(Gurobi/HiGHS) pFBA 재계산** | §4.2. LP 부재 시 "QP-only approximate" |
| Interaction Graph 렌더 | Cytoscape.js+QWebEngine / 네이티브 QGraphicsView | **Cytoscape.js + QWebEngineView** | 사용자 결정. 풍부한 레이아웃/인터랙션; 데이터는 tidy edges로 분리 |
| 데이터 직렬화 | pickle / Parquet+Arrow / JSON | **Parquet/Arrow (메타 YAML+SQLite)** | §3·§8. **pickle 금지(보안)** |
| 출판 그림 | matplotlib만 / R 별도 프로세스 | **R Render(별도 프로세스) + Python fallback** | §9. GPL 격리, 저널 프리셋 |
| Python 패키징/환경 | pip / poetry / uv / conda | **conda 우선(+lock) / uv 병행** | cobrapy·MICOM·solver(gurobipy/highspy/osqp) 바이너리 의존 — conda 친화. **소스/개발 실행 우선**(인스톨러는 배포 단계) |
| 테스트 | pytest | **pytest (+ golden CI 매트릭스)** | float tolerance hash·solver별 golden |
| 패키징(배포) | PyInstaller/briefcase | **Out of scope (배포 단계로 분리)** | baseline=소스 실행 우선 |

### 7.3 Architecture Approach (folder structure preview)

```
CMIG 실제 구조 (Native Desktop, web 요소 없음):

cmig/
  core/                 # CMIG 부가가치 계층 (engine-agnostic, headless)
    engine/             #   Engine Interface + MICOM wrapper (public API only)
    namespace/          #   namespace 정합 + hard gate (§4.8)
    sign/               #   sign 정규화 단일 진입점 (§4.3·§4.7)
    tidy/               #   tidy 데이터 계약 (nodes/edges/profile parquet, §4.6)
    interactions/       #   cross-feeding 추출·interaction typing·CMIG-MIP/MRO
    delta/              #   AN-DELTA (add-member delta)
    sandbox/            #   G1 constraint sandbox (preview/commit)
    sweep/              #   G4 sweep (run_hash 캐시·diagnostic)
    manifest/           #   RunManifest·run_hash (11 구성요소)
  cli/                  # headless CLI (MVP-1a 산출 진입점)
  gui/                  # PySide6 (presentation only)
    explorer/  models/  medium/  community_builder/
    graph/              #   Cytoscape.js + QWebEngineView
    profile/  scenario/  sweep_view/  runtime_jobs/
  render_r/             # R Render Service (별도 프로세스, 데이터 I/O)
  io/                   # SBML/JSON/MAT import · Parquet/Arrow · SQLite/YAML meta
fixtures/
  community_3_member/   # golden: models×3·medium.yaml·config.yaml
    expected/           #   expected_nodes/edges/profile.parquet·growth/sign_expected.tsv
                        #   solver별: gurobi/ · highs/ · osqp_growth_highs_flux/
tests/                  # pytest (sign·gate·golden 매트릭스·cache·sandbox preview)
```

> **핵심 원칙:** `core/`는 GUI/CLI/엔진과 독립(headless·테스트 가능). MICOM 호출은 `core/engine/`의 단일 wrapper만 경유(public API + documented flux only). 모든 산출은 `core/tidy/`의 단일 계약으로.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions
- [ ] `CLAUDE.md` 코딩 컨벤션 섹션 — **미존재 (생성 필요)**
- [ ] `docs/01-plan/conventions.md` (Phase 2 산출) — **미존재**
- [x] Python 프로젝트 — 신규
- [ ] ruff/black 설정 — 미존재 (정의 필요)
- [ ] mypy 설정 — 미존재 (정의 필요)
- [ ] pyproject.toml — 미존재 (생성 필요)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Naming** | missing | snake_case(함수/모듈)·PascalCase(클래스)·tidy 컬럼 표준명(node_id/edge type/flux/label) | High |
| **Folder structure** | missing | §7.3 core/cli/gui/render_r/io 분리 | High |
| **Lint/Format** | missing | ruff + black, mypy(strict on core/) | High |
| **Sign/Unit 규약** | missing | `+`=분비/`−`=흡수 단일 진입점; flux 단위·정규화 표기 규칙 | **Critical** |
| **Reproducibility** | missing | run_hash 11구성요소 직렬화 규칙·seed 기록·float tolerance(예: 6 decimal) | **Critical** |
| **Error handling** | missing | infeasible diagnostic·capability 강등·QP-only 표기·gate 차단 메시지 표준 | High |
| **Pickle 금지** | missing | 직렬화는 Parquet/Arrow/JSON만; pickle import 금지 린트 | High |

### 8.3 Environment / Dependencies Needed

| Dependency | Purpose | Scope | Note |
|----------|---------|-------|:-----:|
| `micom==X.Y.Z` | 커뮤니티 엔진(정확 pin) | core/engine | Design에서 버전 확정 |
| `cobra` (cobrapy) | GEM I/O·FBA/pFBA·optlang | core | **LGPL 재검증** |
| `gurobipy` | 기본 LP/QP/MILP solver | solver | 학술 WLS·미번들 |
| `highspy` (HiGHS) | LP/MILP·무라이선스 경로 | solver | MIT |
| `osqp` | QP growth | solver | Apache; QP 전용 |
| `pyside6` | GUI | gui | LGPL |
| `PySide6-QtWebEngine` | Cytoscape.js 렌더 | gui/graph | 플랫폼 빌드 검증 |
| `pyarrow` / `pandas` | tidy/parquet | io/core | — |
| `networkx` | graph/layout·minimal medium 보조 | core | — |
| R + svglite/ragg/ggraph/circlize/ComplexHeatmap | 출판 그림 | render_r | **별도 프로세스·GPL 격리** |
| ~~GLPK~~ | — | — | **미번들(GPL)** |

### 8.4 Pipeline Integration
| Phase | Status | Document | Note |
|-------|:------:|----------|------|
| Phase 1 (Schema) | ☐ | `docs/01-plan/schema.md` | tidy 계약·데이터 모델(§5) 정식화 권장 |
| Phase 2 (Convention) | ☐ | `docs/01-plan/conventions.md` | §8.2 규약 확정 |

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design cmig-community-core`) — 3-옵션 아키텍처 비교(특히 Engine Interface·sandbox 재solve·sweep 캐시 구조), tidy 스키마 정식화, MICOM 버전 pin 확정
2. [ ] (권장) Phase 1 Schema — tidy 데이터 계약·MemberModel/Scenario/AggregationStore 정식화
3. [ ] (권장) Phase 2 Convention — sign/run_hash/pickle-금지/lint 규약 확정
4. [ ] MVP-1a 우선 착수 (headless core + golden fixture)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-31 | Initial Plan — PRD 참조, baseline MVP-0~2, 아키텍처 결정 4건 확정(Gurobi 기본·Cytoscape.js+QWebEngine·in-process sidecar·소스실행 우선) | PDCA Plan |
