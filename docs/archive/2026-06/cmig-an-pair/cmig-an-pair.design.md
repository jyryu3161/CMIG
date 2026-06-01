# cmig-an-pair Design Document (Option C)
> Plan: cmig-an-pair.plan.md. mono-vs-co 위임 + 신규 MATRIX_SCHEMA.

## Module Map
| 모듈 | 신규 | 역할 |
|------|------|------|
| core/pair.py | 신규 | PairResult·analyze_pair·pair_matrix_rows |
| core/matrix.py | 신규 | MATRIX_SCHEMA·build/write/read_matrix |
| tests/test_pair.py | 신규 | 6 (synthetic pair) |

## 설계
- analyze_pair: co=micom cooperative_tradeoff member_growth, mono=각 GEM 단독 FBA(single_model), interaction=metrics.interaction_type, MRO=mro_pair(uptake_sets), MIP=mip_pair(secretion∩uptake 양방향).
- **NB**: PairResult 필드명 `mro_score`(‘mro’ 는 type.mro 와 충돌 → dataclass default 오인).
- MATRIX_SCHEMA: long-format(schema_version·medium_id·member_id·metric·value·label). interaction 은 label(categorical), 나머지 numeric value. TidyBundle.matrix(현 None) 실 스키마.

## Test Plan
mono/co growth·interaction(mutualism)·MRO/MIP·matrix 9행·parquet 라운드트립·2-멤버 강제.
