# cmig-figure-composer Design (Option C)
> RenderClient 패턴 재사용 + 패널별 R 스크립트.

## Module Map
| render/composer.py | 신규 | FigureComposer·PanelSpec·render_panel/render_panels·PANEL_CSV_COLUMNS |
| render_r/network.R | 신규 | ggraph + igraph (edges) |
| render_r/heatmap.R | 신규 | ComplexHeatmap (matrix, base xtabs wide) |
| render_r/chord.R | 신규 | circlize chordDiagram (edges) |
| tests/test_figure_composer.py | 신규 | 7 (실 R 렌더) |

## 설계
- PanelSpec(kind∈network|heatmap|chord) → kind별 CSV schema → kind.R subprocess(--rlib .Rlib).
- network: graph_from_data_frame + ggraph(fr layout)·geom_edge_link(arrow)·node_text. chord: chordDiagram. heatmap: xtabs long→wide + Heatmap(colorRamp2).
- R/패키지 부재 → RenderError(matplotlib fallback 없음 — 패널은 R 전용, 정직).
- figure_spec sidecar(재현). .Rlib project-local(decision).

## Test Plan
network/chord/heatmap 실 SVG(>1KB)+sidecar·다중 패널·미지원 kind·R 부재 RenderError.
