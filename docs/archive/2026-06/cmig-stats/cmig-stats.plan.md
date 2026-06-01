# cmig-stats Planning Document
> Roadmap Phase 3.7-3.9 (§15 G5) — 통계 5a(검정/FDR)+5b(PCA/cluster)+5c(UMAP).

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | sweep 집계의 통계 비교(effect size·검정·다중비교·차원축소) 부재 |
| Solution | core/stats.py(분포·Cliff δ/Cohen d·MWU/Welch/Kruskal/ANOVA·BH-FDR·오용경고) + core/stats_embed.py(PCA/KMeans·UMAP). sweep→groups 실 wiring |
| Function UX Effect | 그룹 비교 검정·effect size·FDR·PCA/UMAP 임베딩 |
| Core Value | robust 기본(비정규 flux)·honesty 경고(pseudo-replication)·재현(random_state). scipy/statsmodels/sklearn/umap 위임 |

## Success Criteria
SC-ST1 분포요약 · ST2 effect size · ST3 2그룹검정 · ST4 다그룹 · ST5 BH-FDR · ST6 경고+sweep wiring · ST7 PCA/cluster · ST8 UMAP.
