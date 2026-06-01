# cmig-an-single — Completion Report (v1.0)

## Executive Summary
| 관점 | Value Delivered |
|------|-----------------|
| **Problem** | facade.solve_single 0.1 stub(capability_missing) · 단일 GEM 분석 부재 |
| **Solution** | `core/single_model.py` — cobra 위임 FBA/pFBA(growth 일관)·FVA(reuse core.fva)·반응/유전자 knockout(복원)·exchange 요약(sign 단일 진입점)·feasibility. facade.solve_single 실연결 |
| **Function UX Effect** | 단일 모델 growth·flux·FVA 범위·knockout 영향·exchange 방향 산출(e_coli_core 실검증 obj≈0.8739) |
| **Core Value** | AN-SINGLE baseline 분석 원자. cobra 위임·정직 capability gate. **carried-over(solve_single 실로직) 해소**. 220 tests·잔여 결함 0 |

## SC 최종 (6/6 Met)
SC-AS1 FBA/pFBA growth · SC-AS2 FVA 위임 · SC-AS3 knockout 복원 · SC-AS4 exchange 방향 · SC-AS5 feasibility · SC-AS6 capability·무회귀.

## 산출물
**신규**: `core/single_model.py` · `tests/test_single_model.py`(8)
**수정**: `service/engine_service.py`(solve_single 실연결, 0.1 stub 대체) · `tests/test_service_facade.py`(실 FBA 테스트)

## Key Decisions & Outcomes
- objective=**growth 일관**(pFBA biomass flux via linear_reaction_coefficients) — pFBA objective_value(총 flux) 오용 방지. ✅
- core.fva 위임(FVA 재구현 0) · sign.classify 단일 진입점 · cobra 위임. ✅
- knockout `with model:` 자동 복원. ✅

## Quality
220 passed(+8) · ruff clean · mypy strict clean · 0 placeholder.

## 결론
Phase 1.1 완료, solve_single carried-over 해소. 다음: Phase 1.2 AN-PAIR(mono-vs-co + matrix).

| v1.0 | 2026-06-01 | SC-AS 6/6, 220 tests, 잔여 결함 0. |
