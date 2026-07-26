# medium_presets

Diet/medium preset seed (C6). 형식: csv `exchange_id,uptake_limit`(uptake_limit ≥ 0).
`MediumSpec`(cmig.core.medium_spec)으로 로드하여 `apply_medium(community, spec)`로 적용한다.

| preset | 의미 | 비고 |
|--------|------|------|
| `western_diet.csv` | 고당(glucose uptake↑) | 정성 비교용 seed — 정량 식이 모델 아님 |
| `high_fiber.csv` | 저단순당(glucose uptake↓) | fiber diet 의 단순 proxy |

> seed 수준의 **정성 비교용** preset이다. 실제 diet 정량 모델(AGORA/VMH 호환·세분 영양)은 후속.
> exchange_id 는 community medium 키(`EX_*_m`)에 맞춘다. 대상 모델이 `EX_*_e` 를 쓰더라도
> 대사체 기준으로 번역되어 적용되며, **현재 닫혀 있는 exchange 도 열린다**.
> 대응 exchange 반응이 아예 없는 대사체는 기본적으로 **오류**이고,
> `--allow-unknown-medium` 을 준 경우에만 무시되며 그 사실이 diagnostic/warnings 에 기록된다.
