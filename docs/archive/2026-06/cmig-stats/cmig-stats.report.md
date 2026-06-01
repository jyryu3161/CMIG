# cmig-stats — Completion Report (v1.0)

## Executive Summary
| 관점 | Value Delivered |
|------|-----------------|
| Problem | sweep 통계 비교·차원축소 부재 |
| Solution | core/stats.py(5a: 분포·effect size·검정·BH-FDR·경고) + core/stats_embed.py(5b PCA/KMeans·5c UMAP) |
| Function UX Effect | 그룹 비교 검정·effect size·FDR·PCA/UMAP 임베딩. sweep→groups 실 wiring |
| Core Value | robust 기본·honesty 경고·재현. 242 tests·잔여 결함 0 |

## SC 최종 (8/8 Met)
ST1 분포·ST2 effect size·ST3 2그룹·ST4 다그룹·ST5 BH-FDR·ST6 경고+wiring·ST7 PCA/cluster·ST8 UMAP.

## 산출물
신규: core/stats.py · core/stats_embed.py · tests/test_stats.py(10). 수정: pyproject(stats extra + mypy override). 설치: statsmodels 0.14.6·umap-learn 0.5.12(.venv).

## Key Decisions
- robust(Cliff δ/MWU/Kruskal) 기본·parametric opt-in · BH-FDR statsmodels · pseudo-replication 경고(honesty).

## Quality
242 passed(+10)·ruff clean·mypy strict clean·0 placeholder.

## 결론
Phase 3.7-3.9(§15 G5) 완료. 다음: search(3.4-3.6) 또는 figure/GUI.
