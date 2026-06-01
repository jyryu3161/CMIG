---
template: report
version: 1.1
feature: cmig-community-core
project: CMIG (Community Metabolic Interaction GUI)
author: PDCA Report
date: 2026-05-31
milestone: headless-core (module-1a + 1c)
---

# cmig-community-core Completion Report — Headless Core Milestone

> **Status**: **Baseline Complete (MVP-0~2)** — 전 baseline FR 구현·실검증. **SC 9/9 Met · Critical·Important 0.** 적대적 코드 리뷰(24-agent) 통과(Act #2로 3 Critical + 6 Important 해소).
> 잔여(non-blocking): Minor 6(defer) · G-7(GUI Qt 렌더 = 디스플레이 환경 필요) · G-3(AN-SINGLE FVA = MVP-0 세부).
>
> **Project**: CMIG (Community Metabolic Interaction GUI) — native desktop scientific app
> **Author**: PDCA Report · **Completion Date**: 2026-05-31 · **PDCA Cycle**: #1 (headless baseline milestone)
> **Upstream**: [PRD](../../00-pm/cmig-community-core.prd.md) · [Plan](../../01-plan/features/cmig-community-core.plan.md) · [Design](../../02-design/features/cmig-community-core.design.md) · [Analysis](../../03-analysis/cmig-community-core.analysis.md)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | cmig-community-core (PART I Baseline, MVP-0~2) |
| Milestone | **Headless baseline** — module-1a(2a+2b) + module-1c(validation) + module-2(delta·sandbox·sweep slice) |
| Stack | PySide6 desktop(예정) · Python sidecar · cobrapy + **MICOM 0.39.0** · pyarrow · uv |
| Architecture | Option C — layered headless `core/` + EngineService facade + 4 SC-driven seams |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Baseline Match Rate: 98.25% (MVP-0~2 완성)   │
├─────────────────────────────────────────────┤
│  ✅ Met SC:        9 / 9 (baseline 전체)      │
│  ✅ 실검증: MICOM solve · R 그림 · cardinality MILP │
│  ✅ 적대적 리뷰 통과 (Act #2: 3C+6I 해소)      │
│  Tests: 95 passed · ruff/mypy clean (23)     │
│  Critical: 0 · Important: 0 · Minor: 6(defer) │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | community 대사 상호작용 분석이 MICOM/SMETANA 스크립트 전용에 갇혀 인터랙티브·재현·출판 단절 |
| **Solution** | community FBA를 **MICOM(정확 pin·public API only)에 위임**하고, CMIG가 namespace gate·sign·tidy·delta-기반·run_hash 재현성의 **부가가치 헤드리스 코어**를 소유 |
| **Function/UX Effect** | **스크립트 0줄**로 community solve → tidy + add-member delta·sandbox(비오염)·sweep(캐시) + **Cytoscape graph 데이터** + **R 출판 그림(SVG/TIFF)** + **cardinality MILP 최소 배지·MRO/MIP/상호작용 유형**. SC 9/9·solver golden·gate·run_hash 모두 **자동 검증**(95 tests, 적대적 리뷰 통과) |
| **Core Value** | community-FBA 재현성·무결성을 **일급 보장**하는 검증된 baseline 전체(MVP-0~2). 실제 MICOM·R·MILP로 동작 검증되고 적대적 코드 리뷰로 계약 위반까지 제거됨 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | solver별 golden 통과 | ✅ Met | `test_engine_golden::test_golden_regression_per_solver[gurobi/osqp/osqp_growth_highs_flux]` · `fixtures/community_3_member/expected/*` |
| SC-2 | sign-test CI | ✅ Met | `test_sign.py`(canonical −10→uptake10 등) · `test_sign_labels_real_data` |
| SC-3 | namespace gate 차단 | ✅ Met | `test_namespace_gate.py`(high-unresolved→block, low→warn·자동병합 없음, coverage%) |
| SC-4 | run_hash 캐시 정확성 | ✅ Met | `test_run_hash.py`(11구성요소·결정성·env_lock 제외·float 잡음 흡수) |
| SC-5 | MICOM-version golden regression | ✅ Met | `verify_golden_versions` + `cmig golden verify` + `test_version_mismatch_blocks_promotion`(차단) |
| SC-6 | OSQP→LP 재계산 | ✅ Met | `test_osqp_to_lp_matches_gurobi_profile`(hybrid=OSQP-QP+HiGHS-LP ≡ gurobi tolerance 내) |
| SC-7 | MICOM 튜토리얼 재현 | ✅ Met | `test_engine_reproduces_direct_micom`(비트 동일) · `test_tutorial_sanity_*` |
| SC-9 | tidy 계약 준수 | ✅ Met | `test_tidy.py`(스키마·node/edge_type·roundtrip) + 실데이터 build_tidy |
| SC-8 | sandbox preview 비오염 | ✅ Met | `test_sandbox.py`(PREVIEW store write 0·COMMITTED run_hash 승격·multiple preview 비오염) |

**Success Rate**: **9/9 baseline SC Met (100%)** — module-1a+1c+2(headless slice).

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [PRD] | beachhead = MICOM 숙련 microbiome lab; 스크립트 대체 가치 | ✅ | 스크립트 0줄 community solve·재현 입증 |
| [Plan] | MICOM 위임·public API only · Gurobi 기본 · solver별 golden | ✅ | `cooperative_tradeoff` 단일 wrapper; gurobi/osqp/hybrid golden |
| [Plan] | 패키징=소스/uv 실행 우선 | ✅ | uv venv + optional engine extra |
| [Design] | Option C — 4 SC-driven seam | ✅ | (Act G-1) SolverBackend=capability+selection seam로 정합화·design 동기화 |
| [Design] | tidy 단일 계약·pickle 금지·run_hash 11 | ✅ | TidyBundle 단일 reader · ruff pickle-ban · manifest 불변식 |
| [Do/OD] | OD-51 micom pin · OD-12/50 tolerance | ✅ | `micom==0.39.0`; per-variant tolerance(gurobi hash-exact, OSQP atol=1e-4) |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| PM | [prd.md](../../00-pm/cmig-community-core.prd.md) | ✅ |
| Plan | [plan.md](../../01-plan/features/cmig-community-core.plan.md) | ✅ |
| Phase-1 | [schema.md](../../01-plan/schema.md) · [glossary.md](../../01-plan/glossary.md) | ✅ |
| Design | [design.md](../../02-design/features/cmig-community-core.design.md) | ✅ (Option C) |
| Check | [analysis.md](../../03-analysis/cmig-community-core.analysis.md) | ✅ (99%) |
| Report | Current document | 🔄 |

---

## 3. Completed Items

### 3.1 Functional Requirements (module-1a + 1c)

| ID | Requirement | Status |
|----|-------------|--------|
| FR-1a.1 | MICOM 통합 (정확 pin·public API+documented flux) | ✅ |
| FR-1a.2 | Namespace hard gate (차단/경고) | ✅ |
| FR-1a.3 | Sign 테스트 계약 (canonical CI) | ✅ |
| FR-1a.4 | Tidy 데이터 계약 (nodes/edges/profile parquet) | ✅ |
| FR-1a.5 | community/member growth · exchange decomposition · cross-feeding | ✅ |
| FR-1a.6 | OSQP growth → LP pFBA 재계산 (MICOM hybrid) | ✅ |
| FR-1a.7 | Golden fixture (solver별·float tolerance) | ✅ |
| FR-1c.1 | MICOM 튜토리얼 재현 (스크립트 0줄) | ✅ |
| FR-1c.2 | cross-feeding sanity + sign 테스트 | ✅ |
| FR-1c.3 | MICOM-version golden regression (승격 게이트) | ✅ |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 직렬화 보안 | pickle 금지 | ruff pickle-ban 룰 + Parquet/Arrow/JSON/YAML/SQLite | ✅ |
| 재현성 | run_hash 11 + golden 승격 게이트 | 결정성 테스트 + `cmig golden verify` | ✅ |
| 타입 안정성 | mypy strict | no issues (13 files) | ✅ |
| Lint | ruff clean | All checks passed | ✅ |
| 라이선스 | GLPK 미번들·Gurobi 학술 | GLPK registry 제외; gurobipy==12(env license match) | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Headless core | `cmig/core/{engine,namespace,sign,tidy,interactions,manifest,solver,golden}.py` | ✅ |
| module-2 core | `cmig/core/{delta,sandbox,sweep}.py` (AN-DELTA·G1 sandbox·G4 sweep) | ✅ |
| GUI 데이터 브릿지 | `cmig/gui/graph_data.py` (tidy→Cytoscape·필터·gate UI·legend) + `assets/graph.html` | ✅ tested |
| GUI 위젯 | `cmig/gui/graph_view.py` (PySide6 InteractionGraphView·GateBadge) | ⚠️ headless 미검증 (G-7) |
| R Render | `cmig/render/client.py`(subprocess·GPL격리) + `cmig/render_r/figure.R`(ggplot2) | ✅ 실제 SVG/TIFF |
| MILP/지표 | `cmig/core/medium.py`(cardinality MILP) + `cmig/core/metrics.py`(MRO/MIP/typing) | ✅ 실제 MILP |
| CLI | `cmig/cli/main.py` (`version`·`solvers`·`solve`·`golden verify`) | ✅ |
| Golden fixtures | `fixtures/community_3_member/expected/{gurobi,osqp,osqp_growth_highs_flux}` | ✅ |
| Tests | `tests/` (**65**: sign·gate·tidy·run_hash·solver·golden·validation·delta·sandbox·sweep) | ✅ |
| Project | `pyproject.toml`(uv·ruff·mypy·pytest) · README | ✅ |
| Phase-1 docs | `docs/01-plan/{schema,glossary}.md` | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over (후속 Do 사이클)

| Item | Module | Priority | Note |
|------|--------|----------|------|
| **GUI 위젯 렌더링 검증 (G-7)** | module-1b | High | 디스플레이+PySide6 환경 필요 (코드 작성 완료) |
| ~~R Render (G-4)~~ · ~~MILP(G-5)~~ · ~~MIP/MRO(G-6)~~ | ~~module-2~~ | ✅ Done | 실검증 완료 |
| Minor 6 (sign eps·coverage WARNED·manifest flux_report·edge_type·metrics sign·status) | known issues | Low | Act #2 defer |
| AN-SINGLE FVA·loopless·infeasible (G-3) | MVP-0 보강 | Low | 범위 외 |
| R Render (SVG/TIFF) | module-2 | Medium | 출판 그림 |
| AN-SINGLE FVA·loopless·infeasible diagnostic (G-3) | MVP-0 보강 | Low | 범위 외 잔여 |

### 4.2 Cancelled/On Hold
없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | 비고 |
|--------|--------|-------|------|
| Design Match Rate | ≥90% | **98.25%** | #1~5 → #6 94.75(적대적 리뷰 15 confirmed) → Act#2 **98.25** |
| Tests | green | **95 passed** | MICOM solve + delta/sandbox/sweep + GUI 브릿지 + 실제 R 렌더 + 실제 MILP + 7 회귀 |
| Lint (ruff) | 0 | 0 | pickle-ban 포함 |
| Types (mypy strict) | 0 | 0 (13 files) | — |
| Placeholders | 0 | 0 | NotImplementedError 제거 |
| Critical/Important gaps | 0 | 0 | — |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| Gurobi license v12 ≠ gurobipy 13 | `gurobipy>=12,<13` pin | ✅ |
| OSQP cross-process jitter(~6.3e-6) | tolerance 비교(`tables_close`, atol=1e-4) not rounding-hash (OD-47) | ✅ |
| G-1 SolverBackend.solve_* 미사용 stub | seam을 capability+selection으로 정리 + design §4.2 동기화 | ✅ |
| G-2 cross-feeding 경로 미검증 | 합성 secretor/consumer sanity 테스트(weight=min) | ✅ |
| 워크플로 author 파일 직접 write / preamble 오염 | 트랜스크립트 복구 + 정리 패치(docs) | ✅ |
| R base `svg()` X11(libSM) 의존 → SVG 미생성 | CRAN에서 **svglite/ragg 설치**(X11 불요) + figure.R가 svglite 우선 | ✅ |
| **[적대적 리뷰] C-1/C-2** OSQP가 flux_solver='osqp'·'full' 오기록 → run_hash 오염 | branch별 flux_report: osqp→None/qp_only_approximate | ✅ |
| **C-3** sweep.parquet schema_version 누락 | SWEEP_SCHEMA 첫 컬럼 추가 | ✅ |
| **I-5** golden run_hash 독자 재구현([HASH-SINGLE] 위반) | manifest.compute_run_hash 단일 경유 | ✅ |
| **I-2** sweep 실패 run 미캐시 | RunHashCache가 (value,status,diag) 저장·replay | ✅ |
| I-1/I-3/I-4/I-6 | member silent-drop·golden highs→osqp·tradeoff guard·non-finite float | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 Keep
- **명세 우선 + 적대적 검증 워크플로**: schema/design을 fan-out + critic으로 생성 → 모순(seam 수·flux enum 등)을 조기 발견·패치.
- **실제 solver로 조기 검증**: MICOM/Gurobi 실행이 라이선스 버전·OSQP 비결정성 같은 현실 문제를 Do 초기에 노출.
- **Design risk가 실현됨**: OD-12/50(tolerance)을 risk로 미리 표기 → Do에서 정확히 그 지점이 터졌고 즉시 해소.

### 6.2 Problem
- 워크플로 author 에이전트가 결과를 파일 직접 write/요약 반환 → 본문 복구 필요. (구조화 출력 계약을 더 엄격히)
- rounding-then-hash가 iterative solver에 부적합 → tolerance 비교로 전환(설계 가정 수정).

### 6.3 Try
- 다음 워크플로는 author가 **마크다운 문자열만 반환**하도록 스키마 강제 + main-loop write 일원화.
- module-2 sandbox는 preview 비오염(SC-8)을 **로그 기반 QA**로 추가 검증.

---

## 7. Process Improvement Suggestions

| Phase | Improvement |
|-------|-------------|
| Design | golden tolerance 같은 수치 acceptance는 Design에서 "측정 후 확정" task로 명시(이미 적용·효과 확인) |
| Do | iterative solver 결과는 hash-exact가 아닌 tolerance 비교를 기본 패턴으로 |
| Check | 과학 라이브러리는 web L1/L2/L3 대신 pytest를 runtime layer로 매핑(적용함) |

---

## 8. Next Steps

### 8.1 Immediate
- [ ] `/pdca do --scope module-1b` (Cytoscape.js GUI graph) **또는** `--scope module-2` (delta·sandbox·sweep·R)
- [ ] (선택) MVP-0 보강: AN-SINGLE FVA/loopless/infeasible diagnostic (G-3)

### 8.2 Roadmap (PART II, 범위 외)
| Item | Note |
|------|------|
| G2 Host-Microbe (+spike) | MVP-3 |
| dFBA | MVP-3 |
| G3 Consortium Search | MVP-4 |
| G5 통계 | MVP-5 |

---

## 9. Changelog

### v0.1.0 (2026-05-31) — Headless Baseline
**Added:**
- Headless community core: MICOM wrapper · namespace gate · sign · tidy · interactions(cross-feeding) · run_hash manifest · SolverBackend seam · golden harness.
- **module-2 slice**: `core/delta`(AN-DELTA) · `core/sandbox`(G1 preview/commit, SC-8 비오염) · `core/sweep`(G4 run_hash 캐시·AggregationStore parquet).
- CLI: `cmig version|solvers|solve|golden verify`.
- Golden fixtures (gurobi/osqp/osqp_growth_highs_flux) + MICOM-version regression gate.
- **module-1b GUI**: `gui/graph_data` + `assets/graph.html` + `gui/graph_view`(PySide6, headless 미검증).
- **R Render(G-4)**: `render/client`(subprocess·GPL격리) + `render_r/figure.R`(ggplot2) → SVG(svglite)/TIFF(ragg).
- **MILP/지표(G-5/G-6)**: `core/medium`(cardinality MILP, cobra+Gurobi) + `core/metrics`(MRO/MIP/interaction typing).
- **적대적 코드 리뷰 + Act #2**: 3 Critical + 6 Important 해소(OSQP flux 메타·sweep schema_version·HASH-SINGLE 등) + 7 회귀.
- **95-test suite** — 실제 MICOM solve·R 렌더·cardinality MILP 포함.

**Carry-over(non-blocking):** Minor 6(defer) · GUI Qt 렌더 검증(G-7, 디스플레이) · AN-SINGLE FVA(G-3, MVP-0).

**Decisions resolved:** OD-11/12/13/19/47/50/51 (run_hash 직렬화·tolerance·flux_report_status·micom pin).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-05-31 | Headless-core(module-1a+1c) milestone report | PDCA Report |
| 1.1 | 2026-05-31 | Headless baseline 갱신 — module-2 slice 포함, SC 9/9 Met | PDCA Report |
| 1.2 | 2026-05-31 | Baseline 갱신 — module-1b GUI 데이터 브릿지 포함(72 tests); G-7(Qt 렌더 미검증) 명시 | PDCA Report |
| 1.3 | 2026-05-31 | Baseline + R Render(G-4) 갱신 — 실제 ggplot2 SVG 검증(78 tests); G-4 closed | PDCA Report |
| 1.4 | 2026-05-31 | **Baseline Complete** — MILP(G-5/6) + 적대적 리뷰 Act#2(3C+6I 해소). 95 tests, 98.25%, Critical·Important 0 | PDCA Report |
