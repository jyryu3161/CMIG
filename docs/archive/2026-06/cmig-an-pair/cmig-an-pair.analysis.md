# cmig-an-pair Analysis
> Phase 1.2. Match ≈100% (SC-AP1~AP4 Met). 226 tests · ruff/mypy clean.

| SC | 상태 | 증거 |
|----|------|------|
| SC-AP1 mono-vs-co | ✅ | test_pair_mono_vs_co_growth(10/5→12.5/12.5) |
| SC-AP2 interaction | ✅ | test_pair_interaction_mutualism |
| SC-AP3 MRO/MIP | ✅ | test_pair_mro_mip(0/1) |
| SC-AP4 matrix | ✅ | test_pair_matrix_long_format·test_matrix_parquet_roundtrip |

## 정직성
- 전 지표 단일 진입점 위임(metrics·single_model·sign) — 재구현 0.
- 실 시너지 결과(cross-feeding→mutualism) probe 확인 후 테스트(과장 없음).
- 셀프 포착 결함: 필드명 `mro`→`type.mro` 충돌(dataclass default 오인) → `mro_score` 개명.

## Findings
없음(0 C/I/M). dataclass 충돌은 구현 중 셀프 포착·수정.
