# cmig-an-single Design Document (Option C)

> Plan: cmig-an-single.plan.md. cobra 위임 단일 GEM 분석 + facade 연결.

## Module Map
| 모듈 | 신규/수정 | 역할 |
|------|----------|------|
| `cmig/core/single_model.py` | 신규 | SingleModelResult + FBA/pFBA/FVA/knockout/exchange/feasibility |
| `cmig/service/engine_service.py` | 수정 | solve_single(model) → single_model 위임(0.1 stub 대체) |
| `tests/test_single_model.py` | 신규 | 8 ops (e_coli_core) |
| `tests/test_service_facade.py` | 수정 | solve_single 실 FBA 테스트(stub 테스트 대체) |

## 설계
- `SingleModelResult(objective=growth, status, method, solver, fluxes, diagnostic)` — **objective 는 항상 growth**(원 objective 식, `linear_reaction_coefficients`). pFBA 의 sol.objective_value(총 flux)와 구분.
- `solve_single_model(model, method∈{FBA,pFBA}, solver)`: LP capability gate(`_require_lp`, fva.py 일관) → FBA=optimize·pFBA=cobra.flux_analysis.pfba.
- `single_reaction_knockout`/`single_gene_knockout`: `with model:` 컨텍스트 → knock_out() → 재solve → 자동 복원.
- `single_model_fva`: **core.fva.flux_variability 위임**(재구현 금지).
- `exchange_summary`: FBA 1회 → exchange flux + `sign.classify` 방향(단일 진입점). label=None→inactive.
- `growth_feasible`: status optimal ∧ objective>threshold.
- LP 부재 → `capability_missing_result`(구조화 diagnostic, 강제 success 금지).
- facade.solve_single(model, method, solver): solve_single_model 위임, SingleModelUnavailableError→capability_missing_result.

## Test Plan
FBA/pFBA(obj=growth)·FVA(bracket)·반응/유전자 KO(복원)·exchange 방향(glucose uptake)·feasibility·invalid method·facade 실 FBA.

## Risks/Decisions
- objective=growth 일관(pFBA biomass flux) — 적대 검증 핵심.
- sign 단일 진입점·cobra 위임·capability gate(fva.py 일관).

## Next: do → analyze → report → archive → Phase 1.2.
