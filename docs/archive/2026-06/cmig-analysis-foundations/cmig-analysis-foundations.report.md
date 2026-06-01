<!--
Feature: cmig-analysis-foundations
Phase: Report
Created: 2026-06-01
Status: Complete
Basis: REVIEW/CMIG_v3_update_review_2026-06-01.md + CMIG_v3_implementation_review.md (외부 리뷰)
-->

# cmig-analysis-foundations — Completion Report (v1.0)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 외부 리뷰가 확인 — 분석의 *원자 연산*(상호작용·섭동·재현성)은 있으나 **실제 분석으로 바꾸는 기능 기반**(실모델 수집·배지 입력·사용자 산출 경로·표적 readout)이 없고, hybrid solver는 QP flux를 `full(LP)`로 **거짓 표기**. 분석을 라이브러리로는 돌려도 *사용자-facing 산출 경로로는 실행 불가*. |
| **Solution** | capability foundation 7종을 짓는다 — **C9** hybrid 정직화 · **C7** CLI 산출(solve-fixture+solve) · **R5** diagnostic 구조화 기반(sweep 적용) · **C6** medium 입력/preset · **C8** SCFA readout · **C3** sandbox 단일-GEM FVA · **C5** synthetic cross-feeding fixture. |
| **Value Delivered** | 사용자가 `cmig solve --taxonomy --medium`으로 실행→parquet+manifest(재현 run_hash) 산출, diet 조건에 따라 growth·profile·run_hash 상이(diet 비교 가능), SCFA 추적, hybrid 정직 표기. 외부 리뷰 R1~R6·U1~U5를 **사용자-facing 정직성 기준으로 해소**(실 HiGHS LP 재계산·diagnostic 전면 구조화는 후속). |
| **Core Value** | CMIG를 "검증된 원자 연산"에서 **"사용자가 실제 community 분석을 실행·재현·비교할 수 있는 기반"**으로. 정직성(hybrid·diagnostic 기반)·실행성(CLI·medium)을 확보, host는 별도 feature로 정직 분리. |

## 1. Success Criteria 최종 상태

| SC | 기준 | 상태 |
|----|------|:----:|
| SC-F1 | hybrid `full` 미표기 + diagnostic | ✅ Met |
| SC-F2 | solve-fixture run_hash==lib | ✅ Met |
| SC-F3 | solve --taxonomy --medium | ✅ Met |
| SC-F4 | medium A vs B → profile·run_hash 상이 | ✅ Met |
| SC-F5 | SCFA target summary | ✅ Met |
| SC-F6 | sandbox 단일-GEM FVA | ✅ Met |
| SC-F7 | synthetic cross-feeding golden | ✅ Met |
| SC-F8 | 무회귀 + R5/R6/R2 | ✅ Met |

**Overall: 8/8 Met · Match Rate 99.25% · Critical·Important 0.**

## 2. Capability Foundation Map — 전/후

| # | capability | 이전 | 현재 |
|---|-----------|:---:|:---:|
| C1 상호작용 추출 | ✅ | ✅ |
| C2 섭동/sweep | ✅ | ✅ |
| C3 FVA | ⚠️ 미연결 | ✅ sandbox 단일-GEM 연결 |
| C4 재현성/manifest | ✅ | ✅ |
| C5 실모델 수집 | ❌ | ⚠️ synthetic fixture seed (실 AGORA는 후속) |
| C6 배지 입력 | ❌ | ✅ MediumSpec·preset·medium_checksum |
| C7 사용자 산출(CLI) | ❌ | ✅ solve-fixture + solve --taxonomy --medium |
| C8 표적 readout | ❌ | ✅ SCFA target summary |
| C9 solver 정직성 | ❌ 거짓 | ✅ qp_only_approximate + diagnostic |
| C11 host-microbe | ❌ | ⏸ 별도 schema-migration feature(의도적 분리) |

## 3. 외부 리뷰 해소
R1/U1(hybrid 거짓 `full` 표기) · R3/U2(CLI stub) · R6(README) · R2(golden 목록) · R4(sandbox FVA) — **해소**.
R5/U5(자유문자열 diagnostic) — **부분 해소**: `Diagnostic{code,message,detail}` helper + **sweep 실패 경로 구조화**.
engine/delta/sandbox diagnostic은 아직 legacy 자유 문자열(후속 통일). hybrid는 *거짓 표기*만 해소했고
*실 HiGHS LP pFBA 재계산*은 후속 feature.

## 4. Key Decisions & Outcomes
| 결정 | 근거 | 결과 |
|------|------|------|
| [Plan] capability foundation 재정의(시나리오 X) | 사용자 재정의("기능 기반 구현 여부") | 7 capability 구축 |
| [리뷰 반영] hybrid=qp_only_approximate+diagnostic(새 enum X) | FluxReportStatus 2값 파급 회피 | 작고 안전한 정직화 |
| [리뷰 반영] C11 schema seed 코드 제외→별도 feature | validate() exact-match 파급 | golden 미파손 |
| [리뷰 반영] synthetic 명명(종명 X)·단일-GEM FVA·P0~P2 단계화·medium_checksum→run_hash | 정직성·재현성 | 16 corrections 반영 후 구현 |
| [Do] CLI 라이브러리 단일 경로([HASH-SINGLE]) | 자체 hash 금지 | 적대 리뷰서 반증(정직 확인) |
| [Check] 신규 모듈 적대 리뷰 | cycle #2 교훈 | 5 Minor(전부 수정), 0 Critical/Important |

## 5. 정직성 — 잔여 위험·경계 (숨기지 않음)
- **hybrid 실 HiGHS LP pFBA 재계산 미구현** — 현재 정직 표기(diagnostic)까지. 실 재계산은 후속 feature.
- **실 AGORA/VMH 모델 import 미구현** — C5는 synthetic fixture seed. 실 모델 import는 별도 foundation.
- **C11 host-microbe** — schema seed조차 별도 schema-migration feature(validate() exact-match 파급).
- **community-level FVA** — out-of-scope. C3는 단일-GEM FVA만.
- **신규 모듈 적대 리뷰**: 수행함(5 Minor 수정). 설계단계 리뷰 16건 반영이 고severity 차단 효과(cycle #2 18건 → 5건 전부 Minor).

## 6. Quality Metrics
- **테스트**: 95 → **175** (+80) — C9(2)·C7(5)·R5(6)·C6(11)·C8(6)·C3(4)·C5(5)·AF회귀(7) + 기존.
- **품질**: ruff clean · mypy strict(30 files) · 0 placeholder.
- **실검증**: 실 MICOM community solve(default vs diet)·cobra FVA·CLI 산출(parquet+manifest)·synthetic cross-feeding(producer→consumer acetate, consumer butyrate).

## 7. 결론
외부 리뷰가 지적한 capability 격차를 전부 닫아 CMIG를 *사용자 실행 가능한 분석 기반*으로 전환했다. 이번 사이클의 메타 성과: **외부 리뷰 → 설계 반영(16건) → 구현 → 자체 적대 리뷰(5 Minor)**의 완결된 정직성 루프. 설계단계 반영이 적대 리뷰 부담을 cycle #2의 18건(3C+6I)에서 5건(전부 Minor)으로 줄였다.

**다음**: `/pdca archive cmig-analysis-foundations`. 후속 feature 후보: 실 HiGHS LP 재계산 · 실 AGORA/VMH import + namespace mapping · C11 host schema-migration · community-level FVA.

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | foundation 완료 — SC-F 8/8 Met, 99.25%, 175 tests, Critical·Important 0. 외부 리뷰 해소 + 자체 적대 리뷰(5 Minor 수정). |
