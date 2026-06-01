# cmig-search-core Design (Option C)
> R-OBJ target-max + exhaustive 랭킹. micom Community=cobra subclass.

## Module Map
| core/search.py | 신규 | Direction·TargetSpec·target_max_solve·score_target_result·rank_consortia |
| tests/test_search.py | 신규 | 6 (3-member fixture) |

## 설계
- target_max_solve(R-OBJ): cooperative_tradeoff→μc* → with community: growth_expr 하한 제약(f·μc*, optlang Constraint) → objective=EX_target_m, max/min → optimize. growth=floor.primal.
- 부재 exchange → status=missing+capability_missing diagnostic.
- rank_consortia: 멤버셋 부분집합(itertools.combinations) exhaustive(≤n_max, 초과 ValueError) → target_max → score 내림차순.
- score: MAX_SECRETION=+flux, MAX_UPTAKE=−flux, weight 가중(정규화 전 raw).

## Test Plan
target-max optimal(growth≥floor)·missing·score·exhaustive 랭킹·n_max guard.
