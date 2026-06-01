# cmig-figure-composer Planning Document
> Roadmap Phase 1.3 (§9) — 다중 패널 출판 그림(ggraph network·ComplexHeatmap·circlize chord).

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | RenderClient(profile 단일 그림) 외 network/heatmap/chord 다중 패널 부재 |
| Solution | render/composer.py(FigureComposer dispatch) + render_r/{network,heatmap,chord}.R(.Rlib 패키지). PanelSpec 확장 |
| Function UX Effect | edges→network/chord, matrix→heatmap 실 SVG/TIFF 산출 + figure_spec sidecar 재현 |
| Core Value | GPL 격리(R subprocess)·R 부재 시 명시 RenderError(정직)·실 렌더 검증 |

## Success Criteria
SC-FC1 network · FC2 chord · FC3 heatmap · FC4 미지원 kind 거부 · FC5 R 부재 RenderError(silent 위장 금지).
