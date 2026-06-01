# cmig-search-advanced Planning Document
> Roadmap Phase 3.5/3.6 (§14) — search-core carry-over 해소(정규화·Pareto·전략·robustness·explain).

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | search-core 위 weighted 정규화·Pareto·전략 dispatch·robustness·설명 부재 |
| Solution | core/search_advanced.py — normalize_score(literature_max/observed)·weighted_multi_target·pareto_frontier·select_strategy·mro_mip_prescreen·robustness_fva·explain_consortium |
| Function UX Effect | 다표적 정규화 점수·Pareto frontier·전략 자동선택·robustness FVA·자연어 설명 |
| Core Value | normalizer 강제(honesty)·non-exhaustive 경고·GA 미구현 명시·FVA robustness |

## Success Criteria
SA1 정규화 · SA2 weighted · SA3 Pareto · SA4 전략 · SA5 MRO/MIP pre-screen · SA6 robustness FVA · SA7 explain.
