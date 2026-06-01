# cmig-search-advanced Design (Option C)
> search-core 위 부가가치. 대부분 순수 함수(테스트 결정적).

## Module Map
| core/search_advanced.py | 신규 | Normalizer·normalize_score·weighted_multi_target·pareto_frontier·Strategy·select_strategy·mro_mip_prescreen·robustness_fva·explain_consortium |
| tests/test_search_advanced.py | 신규 | 11 |

## 설계
- normalize_score: literature_max 우선·observed_range 폴백(경고)·미지정 ValueError(강제).
- pareto_frontier: 비지배 인덱스(둘 다 최대화).
- select_strategy: ≤20 exhaustive / ≤100 MRO-MIP greedy / >100 GA(미구현).
- mro_mip_prescreen: metrics MRO/MIP 위임, MIP 내림·MRO 오름 + 근사 경고.
- robustness_fva: core.fva.community_fva(target exchange 범위) 위임.
- explain_consortium: 자연어.

## Test Plan
정규화(clamp/폴백/강제)·weighted·Pareto(지배/trade-off)·전략·pre-screen·robustness(fixture)·explain.
