# cmig-dfba Design Document (Option C)
> Plan: cmig-dfba.plan.md. SOA dFBA + timecourse 신규 tidy.

## Module Map
| core/dfba.py | 신규 | DfbaConfig·DfbaResult·simulate_dfba·TIMECOURSE_SCHEMA·build/write_timecourse |
| tests/test_dfba.py | 신규 | 6 (e_coli_core glucose-batch) |

## 설계
- simulate_dfba: 매 step (1) MM 흡수 vmax·S/(km+S) → exchange lower_bound, (2) cobra FBA(LP gate), (3) explicit Euler biomass=biomass+μ·X·dt, dS=v·X·dt(부호: v<0 흡수→농도↓).
- **non-negativity**: 농도<0 이면 dt halving(min_dt), 그래도 음수면 0 clamp(고갈).
- 종료: t_end(completed) · μ≤floor(stalled) · FBA infeasible(infeasible+diagnostic).
- μ=growth(linear_reaction_coefficients, single_model 일관). scipy 불요.
- TIMECOURSE_SCHEMA long-format(t·series·value).

## Test Plan
성장 monotonic·short completed·고갈+non-negativity·고갈후 infeasible explicit·schema·LP gate.
