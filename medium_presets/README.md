# medium_presets

Diet/medium preset seed (C6). 형식: csv `exchange_id,uptake_limit`(uptake_limit ≥ 0).
`MediumSpec`(cmig.core.medium_spec)으로 로드하여 `apply_medium(community, spec)`로 적용한다.

| preset | 의미 | 비고 |
|--------|------|------|
| `western_diet.csv` | 고당(glucose uptake↑) | 정성 비교용 seed — 정량 식이 모델 아님 |
| `high_fiber.csv` | 저단순당(glucose uptake↓) | fiber diet 의 단순 proxy |

> seed 수준의 **정성 비교용** preset이다. 실제 diet 정량 모델(AGORA/VMH 호환·세분 영양)은 후속.
> exchange_id 는 community medium 키(`EX_*_m`)에 맞춘다 — 미지 키는 apply 시 무시된다.
