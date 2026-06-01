# cmig-search-ga Plan
> Phase 3.6 (§14) — GA 전략(>100 후보), search-advanced GA carry-over 해소.
## Executive Summary
| Problem | exhaustive/greedy 불가 대규모 후보 탐색 부재 |
| Solution | core/search_ga.py GA(genome=멤버셋·tournament·union crossover·mutation·elitism·fitness 캐시·결정적 seed) |
| Effect | 대규모 근사 best 멤버셋 + top_k |
| Value | 결정적·캐시(solve 재호출 회피)·근사 경고(honesty) |
## SC: GA1 수렴·GA2 size bounds·GA3 결정적·GA4 캐시·GA5 경고.
