<!--
Feature: cmig-baseline-hardening
Phase: Report
Created: 2026-06-01
Status: Complete
Predecessor: cmig-community-core (archived 2026-05-31)
-->

# cmig-baseline-hardening — Completion Report (v1.0)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | baseline 98.25%는 *계약·단위* 지표일 뿐 *제품 동작* 지표가 아니었다 — CMIG의 "G"(GUI)는 import조차 안 됐고(G-7), 전 파이프라인 통합이 미증명이며, 적대적 정밀도를 받은 모듈만 그 정밀도로 검증됐다. |
| **Solution** | 4트랙 하드닝 — **A** GUI를 offscreen으로 실제 실행·산출 검증, **B** model→solve→tidy→graph→R→GUI end-to-end 6-hop 통합, **C** 미검토 6모듈 적대 리뷰(29 agents), **D** TC-10 min-medium invariants + AN-SINGLE FVA + 과학 Minor + robustness. |
| **Solution (1.3 Value Delivered)** | "never executed GUI"→실행+산출 검증(G-7 해소) · 결합부 미지수→통합 1-pass · **18 confirmed 결함 발굴, Important 9 수정**(fail-explicit 클러스터) · FVA 실구현(fva_lo/hi 채움) · sign eps 과학적 정정. 부수 제품수정: cytoscape CDN→로컬 번들(offline). |
| **Core Value** | baseline을 "통과하는 문서"에서 **"실행으로 증명된 제품"**으로. 잔여 위험(human 시각 QA·OSQP 근사 재현)을 숨기지 않고 명시적 경계로 전환. |

## 1. Success Criteria 최종 상태

| SC | 기준 | 상태 | 근거 |
|----|------|:----:|------|
| SC-H1 | GUI offscreen 실행+산출(G-7) | ✅ Met | test_gui_render.py 5 (DOM count·gate·grab·GateBadge) |
| SC-H2 | E2E 1-pass, hop 계약 보존 | ✅ Met | test_e2e_pipeline.py 6 (실 solve→R→GUI, 부호 100%) |
| SC-H3 | 미검토 모듈 0 Critical·Important 잔존 | ✅ Met | 적대리뷰 18 confirmed(Critical 0), Important 9 수정+9 회귀 |
| SC-H4 | 과학 Minor + FVA + robustness | ✅ Met | TC-10(3)·FVA(6)·robustness(5)·sign eps 정정·metrics 단일진입 |
| SC-H5 | 무회귀 | ✅ Met | 129 pytest, ruff clean, mypy strict(24), 0 placeholder |
| SC-H6 | 정직성 산출물 | ✅ Met | offscreen≠시각QA·H4 데이터계약·golden·OSQP 취약 문서화 |

**Overall: 6/6 Met · Match Rate 98.75% · Critical·Important 0.**

## 2. Track별 산출

| Track | 산출 | 검증 |
|-------|------|------|
| **A** GUI exec | offscreen 위젯 실행 검증(G-7 해소) + cytoscape 로컬 번들 | 5 tests |
| **B** E2E | 6-hop 계약 매트릭스(model→engine→tidy→graph→R→GUI) | 6 tests |
| **C** 적대리뷰 | 29 agents·2.06M tokens, 23 raised→18 confirmed, Important 9 수정 | 9 회귀 tests |
| **D** 보강 | TC-10 [MIN-MEDIUM-U] + `core/fva.py`(AN-SINGLE FVA) + 과학 Minor + robustness | 14 tests |

## 3. Key Decisions & Outcomes

| 결정 | 근거 | 결과 |
|------|------|------|
| [Plan] 4-track A·B·C·D 전체 범위 | 정직성 격차 3종 전부 닫기 | 6/6 SC-H Met |
| [Design] Option C — 검증+국소수정(신규 아키텍처 없음) | 하드닝=검증, 과설계 회피 | 코드변경 국소 + fva.py 1개 신규 |
| [Do-A] offscreen QPA + DOM count 1차 게이트 | QWebEngine 비동기 픽셀 회피, 결정성 | QtWebEngine 실동작 확인 |
| [Do-A] cytoscape CDN→로컬 번들 | offline 데스크톱 앱 + network-free 테스트 | 제품 결함 동반 해소 |
| [Do-C] 적대 리뷰 refute-first verify | 오탐 억제 | 23→18(오탐 5 제거) |
| [Do-C/Checkpoint5] Important 9 수정, TC-10→D, Minor 8 defer | 과학적 위험 우선 | fail-explicit 클러스터 해소 |
| [Do-D] FVA cobra 위임(자체 LP 미구현) | MICOM/cobra 위임 철학 일관 | fva_lo≤net≤fva_hi 불변 |
| [Do-D] 2nd community=불변식 검증(captured-golden 아님) | OD-47: OSQP cross-process 취약 | 강건한 robustness |

## 4. 정직성 — 잔여 위험·경계 (숨기지 않음)

- **G-7b (human 시각 디자인 QA)**: offscreen은 *실행+산출* 증거이며 *시각 디자인 검증이 아니다*. 미수행 — 별도 세션 필요.
- **재현성 비대칭**: bit-exact는 Gurobi 전용. OSQP/HiGHS(무료 경로)는 tolerance 근사 — 변동 없음(baseline 계승).
- **Track-C Minor 8 (TC-11~18)**: defer(사용자 결정). commit-no-store·cache_hit 컬럼·fallback net_flux→0·sidecar allow_nan·solver bare-except·metrics enum casing 등 — known issue.
- **golden 정직성**: sign eps 정정(0.0→1e-6)이 기존 3-member golden을 깨지 않음(near-zero flux 부재). 정정은 적용·재캡처 불요.
- **FVA 범위**: AN-SINGLE(단일 GEM, MVP-0) 구현·검증. community profile fva_lo/hi 실채움 helper 제공.

## 5. Quality Metrics
- **테스트**: 129 pytest (95→129, **+34**) — GUI 5 · E2E 6 · 적대리뷰 회귀 9 · FVA 6 · robustness 5 · TC-10 3.
- **품질**: ruff clean · mypy strict(24 files) · 0 placeholder.
- **실검증**: MICOM community solve · ggplot2 SVG · cobra cardinality MILP · cobra FVA · PySide6 offscreen 렌더.

## 6. 결론
4-track 하드닝으로 baseline의 3대 정직성 격차를 전부 닫았다. **적대 리뷰가 per-slice Check가 놓친 18건(Important 9 수정)을 발굴**한 것이 핵심 — "complete" 표기 모듈에도 fail-explicit 위반이 잠재함을 입증. 잔여는 Minor 8(defer)·G-7b(human QA)로 명시.

**다음**: `/pdca archive cmig-baseline-hardening`.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | 하드닝 완료 보고서 — SC-H 6/6 Met, 98.75%, 129 tests, Critical·Important 0. |
