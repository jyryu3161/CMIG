# cmig-stats Design Document (Option C)
> Plan: cmig-stats.plan.md. scipy/statsmodels/sklearn/umap 위임.

## Module Map
| core/stats.py | 신규 | distribution_summary·cliffs_delta·cohens_d·two/multi_group_test·fdr_correct·normality·stats_warnings·groups_from_sweep_rows |
| core/stats_embed.py | 신규 | pca_embed·kmeans_cluster·umap_embed |
| tests/test_stats.py | 신규 | 10 (순수 수치) |

## 설계
- robust 기본: Cliff's δ + Mann-Whitney/Kruskal. parametric opt-in: Cohen's d + Welch/ANOVA.
- BH/BY FDR = statsmodels multipletests.
- **honesty**: stats_warnings(소표본·pseudo-replication·비정규 Shapiro) — 차단 아닌 노출.
- sweep replicate 의미론: 그룹=축 값/표본=다른 축(결정적 sweep 반복 없음 → 경고).
- 5b PCA(explained_variance)/KMeans, 5c UMAP. random_state=0 재현.

## Test Plan
분포·effect size(δ=±1)·MWU/Welch·Kruskal/ANOVA·BH-FDR(단조)·경고·sweep wiring·PCA/KMeans·UMAP.
