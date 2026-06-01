# cmig-an-single Analysis

> Phase 1.1. Match ≈100% (SC-AS1~AS6 Met). 220 tests green · ruff/mypy clean.

## Success Criteria
| SC | 상태 | 증거 |
|----|------|------|
| SC-AS1 FBA/pFBA growth 일관 | ✅ Met | `test_fba_optimal`·`test_pfba_matches_objective`(objective=growth via linear_reaction_coefficients) |
| SC-AS2 FVA 위임 | ✅ Met | `test_single_model_fva_brackets_growth`(core.fva 위임, biomass lo≈hi≈opt) |
| SC-AS3 knockout 복원 | ✅ Met | `test_reaction_knockout_lowers_growth`(복원 검증)·`test_gene_knockout` |
| SC-AS4 exchange 방향 | ✅ Met | `test_exchange_summary_directions`(sign.classify, glucose uptake flux<0) |
| SC-AS5 feasibility | ✅ Met | `test_growth_feasible` |
| SC-AS6 capability·무회귀 | ✅ Met | capability_missing_result(LP 부재)·220 passed·ruff/mypy clean |

## 정직성
- **pFBA growth 정정**(핵심): pFBA sol.objective_value=총 flux(518)≠growth → linear_reaction_coefficients 로 biomass flux(0.8739) 재계산 → objective 의미 FBA/pFBA 일관. 적대 검증 셀프 포착·수정.
- cobra 위임(자체 LP 미구현) · sign.classify 단일 진입점 · core.fva 위임(재구현 0) · LP capability gate fail-fast.
- facade.solve_single **실연결**(0.1 stub 대체) — carried-over 해소, orphan 아님.

## Findings
없음(0 Critical/Important/Minor). pFBA growth 의미는 구현 중 셀프 포착·수정(테스트가 518≠0.87 로 노출 → linear_reaction_coefficients 도입).

## Version History
| v1.0 | 2026-06-01 | Match ≈100%, SC-AS 6/6, 220 tests. |
