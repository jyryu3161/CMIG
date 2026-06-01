# cmig-search-core Analysis
> Phase 3.4. Match ≈100% (SC-SR1~SR5 Met). 248 tests · ruff/mypy clean.

| SC | 상태 | 증거 |
|----|------|------|
| SR1 target-max | ✅ | test_target_max_solve_optimal(acetate 16.68, growth≥floor) |
| SR2 missing | ✅ | test_target_max_missing_exchange |
| SR3 score | ✅ | test_score_target_result |
| SR4 랭킹 | ✅ | test_rank_consortia_exhaustive(C(3,2)=3, 내림차순) |
| SR5 n_max guard | ✅ | test_rank_consortia_nmax_guard(silent 절단 금지) |

## 정직성
- R-OBJ spike 검증 후 구현(public API optlang Constraint+objective 오버라이드, status=optimal 확인).
- exhaustive 한계 n_max ValueError(silent 절단 금지) · 부재 target=missing diagnostic.
- raw flux 점수(정규화는 carry-over 3.5에서 — 과장 없음).

## Findings
없음(0 C/I/M). 셀프 포착: growth_expr.value→floor.primal(optlang 정확 API).

## Carry-over: 3.5 weighted 정규화/Pareto · 3.6 MIP pre-screen/GA/robustness/GUI.
