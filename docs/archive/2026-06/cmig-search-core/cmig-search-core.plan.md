# cmig-search-core Planning Document
> Roadmap Phase 3.4 (§14 G3) — consortium search core(target-max + 랭킹). 3.5 Pareto·3.6 strategy/GUI = carry-over.

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | 표적 대사체(SCFA 등) 생산 최대 consortium 탐색 부재 |
| Solution | core/search.py — R-OBJ target-max(growth-floor 제약+objective 오버라이드, spike 검증 optimal) + TargetSpec encode + exhaustive 멤버셋 랭킹 |
| Function UX Effect | target-max flux·점수·멤버셋 랭킹(growth≥f·μc* 보장) |
| Core Value | R-OBJ public API 검증·gurobi 전제·exhaustive honesty(n_max guard) |

## Success Criteria
SC-SR1 target-max optimal · SR2 부재 target missing · SR3 score · SR4 exhaustive 랭킹 · SR5 n_max guard.

## Carry-over (후속): 3.5 weighted 정규화·Pareto≤2 · 3.6 MRO/MIP pre-screen·GA·robustness·GUI.
