# cmig-analysis-completion — Check (Gap Analysis)

> foundation carried-over 5개 완성(gurobi-only) cycle의 Check. F1~F5 + 외부 리뷰 5건 반영분 평가.

## Context Anchor
| 축 | 내용 |
|----|------|
| WHY | foundation의 정직한 미완 항목을 gurobi로 실제 완성 — 동작으로. |
| SUCCESS | SC-C1~C6 — diagnostic 구조화·CLI targets·hybrid 폐기·community FVA 실채움·schema v1.1. |

## 1. Success Criteria (SC-C1~C6)
| SC | 기준 | P | 상태 | 근거 |
|----|------|:-:|:----:|------|
| SC-C1 | diagnostic 전면 구조화 | P0 | ✅ Met | engine/delta/sandbox→Diagnostic JSON, test_diagnostic_unified(4) |
| SC-C2 | CLI --targets → target_summary.json | P0 | ✅ Met | test_cli_targets(4), 실 profile acetate |
| SC-C3 | hybrid 폐기, functional 참조 0 | P1 | ✅ Met | 9파일+fixture 정리, grep=deprecation 마커만, argparse 거부 |
| SC-C4 | community FVA fva_lo/hi 실채움 | P1 | ✅ Met | **CLI --fva 실 산출 8/8 채움**(리뷰 후 wiring), fraction=tradeoff_f bracketing |
| SC-C5 | schema v1.1 + v1.0 하위호환 | P2 | ✅ Met | read_legacy_or_upgrade(컬럼-존재·빈 테이블·default microbe), golden v1.1 재캡처 |
| SC-C6 | 무회귀 + gurobi-only 강제 | all | ✅ Met | 191 pytest, ruff/mypy clean, engine 라이브러리 레벨 solver 거부 |

**SC-C 6/6 Met (100%).**

## 2. 외부 리뷰 반영 (2차 — 구현 갭 5건)
| # | 등급 | 갭 | 해소 |
|---|:---:|----|------|
| 1 | High | F2 helper만, 실 산출 미연결(profile fva 0/8) | solve_with_community + attach_community_fva_to_bundle + CLI --fva → 8/8 채움 |
| 2 | High | engine 임의 solver 허용·any-non-osqp=full | ALLOWED_CMIG_SOLVERS 강제, full=gurobi 명시. highs 거부 |
| 3 | Med | F5 빈 v1.0 테이블 미승격 | read_legacy_or_upgrade 컬럼-존재 기준 재작성 |
| 4 | Med | default microbe 계약 불일치 | legacy nodes member→microbe·pool→None |
| 5 | Low | 문서 게이트 미달 | README·schema.md·glossary.md 갱신(hybrid 폐기) |

> 핵심 교훈(재확인): **테스트 green ≠ 기능 연결.** F2는 helper 단위 테스트만으로 통과했으나 실 산출 경로 미연결이었다. 리뷰가 `solve("gurobi")` 실행으로 0/8 포착 → CLI --fva로 실 경로 wiring + 산출-경로 검증 테스트 추가.

## 3. Layer 점수
| Layer | Score | 근거 |
|-------|:-----:|------|
| Structural | 100% | 계획 산출물 전부(신규 community_fva·--targets·--fva·schema v1.1·diagnostic 통일·hybrid 제거) |
| Functional | 99% | 5 capability end-to-end 동작·실 산출 경로 연결(리뷰 후). 잔여 후속(AGORA import 등 out-of-scope) |
| Contract | 99% | gurobi-only 라이브러리 강제·diagnostic 단일계약·schema v1.1 하위호환·grep 게이트 |
| Runtime | 100% | 191 pytest green(실 MICOM·cobra FVA·CLI·schema migration), ruff/mypy clean |

**Match Rate = 100×0.15 + 99×0.25 + 99×0.25 + 100×0.35 = 99.5%** (runtime 실행 공식).

## 4. 정직한 방법론 노트
- 신규/수정 모듈(community_fva·targets CLI·diagnostics 통일·hybrid 폐기·schema migration)은 per-slice Check + 표적 테스트 + **2차 외부 리뷰(구현 갭 5건)**를 받았다. cycle #3 패턴(자체 적대 리뷰)은 Checkpoint 5 옵션으로 잔존 — 외부 리뷰가 이미 실 산출 갭을 포착했으므로 선택적.
- 과학적 디테일(community FVA fraction=tradeoff_f bracketing)은 가정 없이 실측 검증.

## 5. 잔여 (out-of-scope / 후속, gap 아님)
- 실 AGORA/VMH import(별도 대형 feature) · host-microbe solve 로직(MVP-3) · `osqp_growth_gurobi_flux` experimental(필요 시) · member EX_*_e community FVA · `--fva` 항상-on(현재 opt-in, 비용).

## 6. 결론 (Check)
- **SC-C 6/6 Met · Match 99.5% · Critical·Important 0.**
- foundation carried-over 5개를 gurobi-only로 실제 완성: diagnostic 전면 구조화·CLI targets·hybrid 폐기·community FVA 실채움(실 산출)·schema v1.1.
- 2차 외부 리뷰 5건(실 산출 wiring·solver 강제·legacy 견고·default microbe·문서) 반영.
- **Checkpoint 5: Critical·Important 0 → report 권장**(또는 신규 모듈 적대 리뷰 확장 선택).

## Version History
| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-06-01 | Check: SC-C 6/6 Met, Match 99.5%, Critical·Important 0. 외부 리뷰 5건 반영 매트릭스 + 방법론 노트. |
