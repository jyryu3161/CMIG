# cmig-an-pair Planning Document
> Roadmap Phase 1.2 — AN-PAIR(mono-vs-co) + 배지별 matrix.

## Executive Summary
| 관점 | 내용 |
|------|------|
| Problem | 2-member 상호작용 분석(monoculture vs co-culture, interaction typing, MRO/MIP, matrix) 부재 |
| Solution | `core/pair.py`(analyze_pair: mono=single_model FBA·co=micom community·interaction=metrics.interaction_type·MRO/MIP) + `core/matrix.py`(MATRIX_SCHEMA long-format) |
| Function UX Effect | 상호작용 유형(mutualism 등)·성장 변화·MRO/MIP·배지별 matrix 산출 |
| Core Value | AN-PAIR baseline 분석. metrics·single_model·sign 단일 진입점 위임(재구현 0) |

## Success Criteria
- SC-AP1 mono-vs-co growth(synthetic: mono 10/5 → co 12.5/12.5)
- SC-AP2 interaction typing(cross-feeding→mutualism)
- SC-AP3 MRO/MIP(mro=0 disjoint, mip=1 acetate 기증)
- SC-AP4 matrix.parquet(MATRIX_SCHEMA long-format, write/read 라운드트립)
