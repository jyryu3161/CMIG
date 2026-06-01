<!--
Feature: cmig-analysis-completion
Phase: Report
Created: 2026-06-01
Status: Complete
Predecessor: cmig-analysis-foundations (archived 2026-06)
Constraint: HiGHS 제거, gurobi-only
-->

# cmig-analysis-completion — Completion Report (v1.0)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | foundation cycle이 capability 일부를 정직하게 미완으로 남김 — hybrid flux 정직 표기만(실 LP 재계산 X)·FVA 단일-GEM만·SCFA readout CLI 미노출·diagnostic sweep만 구조화·host schema seed 코드 미반영. |
| **Solution** | 사용자 제약(HiGHS 제거·gurobi-only)으로 5개 완성 — **F1** hybrid 폐기(gurobi=full canonical) · **F2** community-level FVA(gurobi) · **F3** CLI `--targets` · **F4** diagnostic 전면 구조화 · **F5** schema v1.1 host-microbe 확장. |
| **Value Delivered** | `cmig solve --fva`로 community FVA를 profile fva_lo/hi에 실채움 · `--targets scfa`로 SCFA summary 산출 · 모든 diagnostic이 {code,message,detail} JSON · solver 표면 2개(gurobi/osqp)로 단순화(라이브러리 강제) · schema v1.1 하위호환(v1.0 parquet 자동 승격). |
| **Core Value** | "정직하게 미완으로 남긴 것"을 gurobi로 실제 완성. HiGHS 의존·거짓 표기 가능성 제거. 무라이선스(osqp)는 qp_only_approximate 정직 경로 유지. |

## 1. Success Criteria 최종 상태
| SC | 기준 | 상태 |
|----|------|:----:|
| SC-C1 | diagnostic 전면 구조화 | ✅ Met |
| SC-C2 | CLI --targets → target_summary.json | ✅ Met |
| SC-C3 | hybrid 폐기 (functional 참조 0) | ✅ Met |
| SC-C4 | community FVA fva_lo/hi 실채움 | ✅ Met |
| SC-C5 | schema v1.1 + v1.0 하위호환 | ✅ Met |
| SC-C6 | 무회귀 + gurobi-only 강제 | ✅ Met |

**Overall: 6/6 Met · Match Rate 99.5% · Critical·Important 0.**

## 2. 항목별 산출 (staged)
| F | P | 산출 |
|---|:-:|------|
| F4 diagnostic 전면 구조화 | P0 | `diagnostic_from_parts`(다중 code→primary+detail), engine/delta/sandbox JSON 통일 |
| F3 CLI --targets | P0 | `cmig solve [--targets scfa]` → target_summary.json + manifest artifacts |
| F1 hybrid 폐기 | P1 | osqp_growth_highs_flux 9파일+fixture 정리, gurobi=full canonical, **library 레벨 solver 강제** |
| F2 community FVA | P1 | `community_fva`(cobra FVA on micom community, processes=1, gurobi) + `--fva` 실 산출 wiring + EX_*_m→metabolite 매핑 |
| F5 schema v1.1 | P2 | host-microbe 확장 컬럼 + `read_legacy_or_upgrade`(v1.0 하위호환) + golden v1.1 재캡처 |

## 3. Key Decisions & Outcomes
| 결정 | 근거 | 결과 |
|------|------|------|
| [Plan] HiGHS 제거·gurobi-only | research 불확실성 제거(gurobi=QP+LP+MILP+FVA) | community FVA·LP recalc 확실 구현 |
| [Plan gate] F1=hybrid 폐기 확정(design 미루지 않음) | 9파일+fixture 흩어짐(리뷰) | design 작업량 안정 |
| [Do-F2] community FVA fraction=tradeoff_f 필요 | 실측: fraction=1.0이면 tradeoff 解가 envelope 밖 | bracketing 정확성 확보 |
| [리뷰] F2 helper→실 산출 --fva wiring | 테스트 green≠연결(profile 0/8) | 실 경로 8/8 채움 |
| [리뷰] engine 라이브러리 레벨 solver 강제 | CLI choices만으론 우회 가능 | full=gurobi 불변 보장 |
| [F5] read_legacy_or_upgrade 컬럼-존재 기준 | 빈 v1.0 테이블 견고성 | row 0 승격 |

## 4. 정직성 — 잔여 위험·경계
- **실 AGORA/VMH import 미구현** — 별도 대형 데이터 foundation(분리 결정).
- **host-microbe solve 로직 미구현** — F5는 schema 확장 자리만, organism_type 항상 microbe(MVP-3).
- **community FVA opt-in** — `--fva` 시에만 산출(비용↑). 항상-on 아님.
- **`osqp_growth_gurobi_flux`(실 OSQP-growth→gurobi-LP recalc)** — 본 cycle 밖(필요 시 후속).
- **community FVA bracketing은 fraction=solve의 tradeoff_f일 때만** — 테스트·docstring 명시.

## 5. Quality Metrics
- **테스트**: 175 → **191** (+16) — F4(4)·F3(4)·F1(테스트 대체)·F2(6+CLI)·F5(6)·리뷰 회귀.
- **품질**: ruff clean · mypy strict(30) · 0 placeholder.
- **실검증**: 실 MICOM solve(gurobi/osqp)·cobra community FVA·CLI 산출(parquet+manifest+target+fva)·schema v1.0→v1.1 migration.

## 6. 결론
foundation carried-over 5개를 gurobi-only로 실제 완성했다. 메타 성과: **외부리뷰→plan(범위 재조정)→design→구현→2차 외부리뷰(실 산출 갭 5건)**의 검증 루프. 특히 *"테스트 green이 곧 기능 연결은 아니다"*(F2 helper만 통과)를 외부 리뷰가 실행으로 포착·수정한 것이 핵심.

**다음**: `/pdca archive cmig-analysis-completion`. 후속 feature: 실 AGORA/VMH import · host-microbe solve(MVP-3) · osqp_growth_gurobi_flux experimental.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | completion 완료 — SC-C 6/6 Met, 99.5%, 191 tests, Critical·Important 0. gurobi-only 5개 완성 + 2차 외부 리뷰 5건 반영. |
