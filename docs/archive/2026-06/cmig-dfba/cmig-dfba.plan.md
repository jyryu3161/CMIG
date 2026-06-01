# cmig-dfba Planning Document
> Roadmap Phase 3.3 (§13) — well-mixed 동적 FBA.

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | 시간에 따른 대사·성장 동역학(dFBA) 부재 |
| Solution | `core/dfba.py` — Static Optimization Approach(매 step MM 흡수 한계→cobra FBA→explicit Euler), non-negativity 강제(dt 적응), timecourse.parquet |
| Function UX Effect | biomass·농도·성장률 timecourse. 고갈→maintenance 미충족 infeasible(생물학적 사멸) 정직 표기 |
| Core Value | cobra 위임·scipy 불요(explicit Euler)·수치 acceptance. PART II §13 |

## Success Criteria
- SC-DF1 biomass 성장(monotonic) · SC-DF2 짧은 horizon completed · SC-DF3 고갈+non-negativity
- SC-DF4 고갈 후 infeasible+diagnostic(silent 위장 금지) · SC-DF5 timecourse schema · SC-DF6 LP gate
