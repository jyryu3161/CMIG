# R Figure Deps Lock (2026-06-01)

Figure Composer(§9) 패키지를 **project-local `.Rlib`** 에 설치(전역 R 라이브러리 비오염).

| 패키지 | 출처 | 용도 |
|--------|------|------|
| ggraph + graphlayouts + igraph | CRAN | network panel(network.R) |
| ComplexHeatmap | Bioconductor | heatmap panel(heatmap.R) |
| circlize | CRAN | chord panel(chord.R) + heatmap colorRamp2 |
| svglite | CRAN | SVG device |

설치: `Rscript -e '.libPaths(".Rlib"); install.packages(c("ggraph","graphlayouts","circlize")); BiocManager::install("ComplexHeatmap")'`.
R 스크립트는 `--rlib` 인자로 `.Rlib` 를 .libPaths 에 prepend. GPL 격리: R subprocess 전용(§2).
R 부재 시 패널 미생성 + 명시적 RenderError(matplotlib fallback 없음 — 정직).
