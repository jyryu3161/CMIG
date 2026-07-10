# R Figure Deps Lock (2026-06-01)

Figure Composer(§9) 패키지를 **project-local `.Rlib`** 에 설치(전역 R 라이브러리 비오염).

| 패키지 | 출처 | 용도 |
|--------|------|------|
| ggraph + graphlayouts + igraph | CRAN | network panel(network.R) |
| ComplexHeatmap | Bioconductor | heatmap panel(heatmap.R) |
| circlize | CRAN | chord panel(chord.R) + heatmap colorRamp2 |
| svglite | CRAN | SVG device |

정확 버전과 전이 의존성은 `cmig/render_r/renv.lock`에 고정한다. 복원:

```bash
Rscript -e 'if (!requireNamespace("renv", quietly=TRUE)) install.packages("renv", repos="https://cloud.r-project.org"); renv::restore(lockfile="cmig/render_r/renv.lock", library=".Rlib", prompt=FALSE)'
```

R 스크립트는 `--rlib` 인자로 `.Rlib` 를 .libPaths 에 prepend. GPL 격리: R subprocess 전용(§2).
R 부재 시 패널 미생성 + 명시적 RenderError(matplotlib fallback 없음 — 정직).
성공한 모든 렌더는 실제 R/패키지 버전과 입력·스크립트·lock·출력 체크섬을
`<figure>.render_provenance.json`에 기록한다.
