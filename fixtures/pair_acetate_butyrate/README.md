# fixtures/pair_acetate_butyrate (C5/S3)

문헌의 대표 **acetate → butyrate cross-feeding** 관계(primary fermenter 가 acetate 분비,
butyrate producer 가 acetate 흡수→butyrate 분비)를 **정성 검증**하기 위한 **synthetic** fixture.

> ⚠️ **종명을 부여하지 않은 synthetic toy GEM 이다.** 실제 AGORA/VMH 모델이 아니며,
> 정량 해석(실제 균주 flux 예측)에 사용하면 안 된다. CMIG 의 cross-feeding 추출·sign 규약을
> 대표 시나리오로 검증하는 용도다. 모델은 `cmig/synthetic_pair.py` 가 코드 생성한다.

- `synthetic_acetate_producer`: glucose 흡수 → acetate 분비
- `synthetic_butyrate_consumer`: acetate 흡수 → butyrate 분비
- 검증(정성): `producer→consumer ac [cross_feeding]` edge · `consumer` butyrate secretion · sign 규약.
- `expected/`: gurobi(결정적) golden — nodes/edges/profile.parquet + config.json(tidy_hashes).
