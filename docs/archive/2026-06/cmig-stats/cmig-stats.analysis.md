# cmig-stats Analysis
> Phase 3.7-3.9. Match ≈100% (SC-ST1~ST8 Met). 242 tests · ruff/mypy clean.

| SC | 상태 | 증거 |
|----|------|------|
| ST1 분포 | ✅ | test_distribution_summary |
| ST2 effect size | ✅ | test_effect_sizes(δ=±1, d>2) |
| ST3 2그룹 | ✅ | test_two_group_test_robust_and_parametric |
| ST4 다그룹 | ✅ | test_multi_group_test |
| ST5 BH-FDR | ✅ | test_fdr_correction(단조) |
| ST6 경고+wiring | ✅ | test_stats_warnings_honesty·test_groups_from_sweep_rows_wiring |
| ST7 PCA/cluster | ✅ | test_pca_and_kmeans |
| ST8 UMAP | ✅ | test_umap_embed |

## 정직성
- robust 기본(비정규 flux 적합) · pseudo-replication 경고(과학적 단정 회피) · 재현 random_state.
- sweep→groups 실 wiring(orphan 아님) · scipy/statsmodels/sklearn/umap 위임(재구현 0).

## Findings
없음(0 C/I/M).
