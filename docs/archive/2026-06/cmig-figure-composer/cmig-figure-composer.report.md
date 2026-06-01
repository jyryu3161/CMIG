# cmig-figure-composer — Completion Report (v1.0)

## Executive Summary
| 관점 | Value Delivered |
|------|-----------------|
| Problem | 다중 패널 출판 그림(network/heatmap/chord) 부재 |
| Solution | render/composer.py + render_r/{network,heatmap,chord}.R(.Rlib: ggraph·ComplexHeatmap·circlize) |
| Function UX Effect | edges→network(10.8KB)/chord(58.6KB), matrix→heatmap(17KB) 실 SVG 산출 |
| Core Value | 실 R 렌더 검증·GPL 격리·R 부재 명시 에러(정직). 266 tests·잔여 결함 0 |

## SC 최종 (5/5 Met)
FC1 network·FC2 chord·FC3 heatmap·FC4 kind 거부·FC5 R 부재 RenderError.

## 산출물
신규: render/composer.py · render_r/network.R · render_r/heatmap.R · render_r/chord.R · tests/test_figure_composer.py(7). decision: r-figure-deps-lock. 설치: ggraph·graphlayouts·circlize(CRAN)·ComplexHeatmap(Bioc) → .Rlib.

## Key Decisions
- .Rlib project-local(전역 R 비오염) · R 전용 패널(fallback 없음, 정직 RenderError) · GPL subprocess 격리.

## Quality
266 passed(+7, 실 R 렌더 4)·ruff clean·mypy strict clean·0 placeholder.

## 결론
Phase 1.3 완료 → §9 Figure Composer 핵심 3패널 완결. journal preset 세부는 후속.
