# cmig-an-single Planning Document

> Roadmap Phase 1.1 — 단일 GEM 분석(AN-SINGLE). facade.solve_single 의 0.1 stub 을 실로직으로 대체(carried-over 해소).

## Executive Summary
| 관점 | 내용 |
|------|------|
| **Problem** | facade.solve_single 은 0.1 에서 capability_missing stub. 단일 GEM FBA/pFBA/FVA/knockout/exchange 분석 부재. |
| **Solution** | `cmig/core/single_model.py` — cobra 위임 FBA/pFBA(LP)·FVA(reuse core.fva)·반응/유전자 knockout·exchange 요약(sign 단일 진입점)·growth feasibility. facade.solve_single 실연결. |
| **Function UX Effect** | 단일 모델 분석 산출(growth·flux·FVA 범위·knockout 영향·exchange 방향). |
| **Core Value** | AN-SINGLE = baseline 분석 원자. cobra 위임(자체 LP 미구현)·정직 capability gate. |

## Scope
**In**: single_model.py(SingleModelResult·solve_single_model·single_reaction/gene_knockout·single_model_fva·exchange_summary·growth_feasible·capability_missing_result) · facade.solve_single 재연결 · tests.
**Out**: 다중 모델·AN-PAIR(1.2)·GUI(2.x).

## Success Criteria
- **SC-AS1**: FBA/pFBA — e_coli_core obj≈0.8739, status optimal, objective=growth 일관(pFBA 도 biomass flux).
- **SC-AS2**: FVA — core.fva 위임, lo≤hi, fraction=1 이면 biomass lo≈hi≈opt.
- **SC-AS3**: 반응/유전자 knockout — bound 자동 복원(with model:), 필수반응 KO→growth 감소.
- **SC-AS4**: exchange 요약 — sign.classify 단일 진입점, glucose=uptake(flux<0).
- **SC-AS5**: growth feasibility.
- **SC-AS6**: LP 부재 → 정직 capability_missing(강제 success 금지) · 220+ green · ruff/mypy clean.

## Risks
| 위험 | 완화 |
|------|------|
| pFBA objective_value=총flux≠growth | linear_reaction_coefficients 로 growth 재계산(FBA/pFBA 일관) |
| knockout bound 영구 변경 | `with model:` 컨텍스트 자동 복원 + 복원 검증 테스트 |
| sign inline 재구현 | sign.classify 단일 진입점 reuse |

## Next Steps
design → do → analyze → report → archive → Phase 1.2 AN-PAIR.
