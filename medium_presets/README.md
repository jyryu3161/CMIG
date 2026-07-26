# medium_presets

형식: csv `exchange_id,uptake_limit` (`uptake_limit ≥ 0`, 단위 **mmol gDW⁻¹ h⁻¹**).
`MediumSpec`(cmig.core.medium_spec)으로 로드해 `apply_medium(community, spec)` 로 적용한다.
CMIG 는 medium 을 **대사체 기준**으로 매칭하므로 `EX_glc__D_m` 이 member model 의 `EX_glc__D_e` 에도
적용된다 — 한 파일에 두 namespace 를 같이 넣으면 **exit 2 로 거부**된다.

## ⚠️ `--medium` 은 medium 을 **덮어쓰지 않고 얹는다(overlay)**

CMIG 는 `apply_medium_translated(..., exact=False)` 로 **merge** 한다. 즉 **파일에 적지 않은 대사체는
MICOM 기본값을 그대로 유지한다.** 실측(`iML1515 + iYO844` community, glucose 한 줄짜리 spec 적용):

```
spec 에 없는데도 열려 있는 uptake 23 개 — EX_o2_m = 999999.0, EX_co2_m = 999999.0, EX_nh4_m = 1000.0 …
```

**대장은 사실상 무산소인데 O₂ 가 무한정 열려 있다.** 실측 (iML1515+iYO844+iHN637, tradeoff f=0.5,
gurobi):

| medium | 적용 후 `EX_o2_m` | community growth (h⁻¹) |
|---|---|---|
| `western_diet.csv` (glucose 20 한 줄) | **999999.0** | **1.2677557** |
| 여기에 `EX_o2_m,0.001` 만 추가 | 0.001 | **0.6990206751** |

한 줄 누락으로 growth 를 **81 % 과대추정**한다. 그래서 아래 overlay 들은 전부
(1) `EX_o2_m = 0.001` 을 명시하고, (2) **background closure block**(pool 의 default medium 이 열어두는
대사체를 `uptake_limit = 0` 으로 명시)을 포함한다. `0` 행은 merge 의미론에서 CSV 가 "환경이 이걸
공급하지 않는다"를 표현하는 **유일한** 방법이다. 적용 후 "overlay 가 적지 않았는데 열려 있는 uptake"
집합이 7개 overlay 모두 **빈 집합**임을 실측했다. 근본 해결(코드 쪽 `--exact-medium`)은
[`PROVENANCE_gut_media.md`](PROVENANCE_gut_media.md) §9 에 남겼다.

## Literature-grounded gut overlays (권장)

**출처·단위·변환 산술·모델별 coverage·섬유 coverage 는
[`PROVENANCE_gut_media.md`](PROVENANCE_gut_media.md) 에 전부 기록되어 있다.** 행 단위 provenance 는
[`provenance_rows.csv`](provenance_rows.csv).

| overlay | rows | 근거 |
|--------|------|------|
| `gut_overlay_agora_western.csv` | 133 | **AGORA Supp Table 12 Western** × MICOM 소장흡수 dilution. 표 제목에 단위가 `mmol gDW⁻¹ h⁻¹` 로 인쇄돼 있어 **변환 불필요**. 기준 medium. |
| `gut_overlay_agora_high_fiber.csv` | 133 | 같은 표의 **high fiber** 열. 위와 짝을 이루는 대조군. |
| `gut_overlay_vmh_high_fat_low_carb.csv` (+`_x100`) | 80 | VMH "High fat, low carb" (mmol person⁻¹ day⁻¹) → 변환 |
| `gut_overlay_vmh_high_fiber.csv` (+`_x100`) | 80 | VMH "High fiber" → 변환 |
| `gut_overlay_micom_western.csv` | 131 | MICOM 이 발표한 western-diet gut medium(BiGG/CarveMe) **그대로** |

`_x100` 은 문헌값이 아니라 **공학적 rescale**(식이 행에만 ×100; O₂·closure 행은 그대로)이며
파일명에 드러나 있다. 이유는 PROVENANCE §5.

반드시 알고 써야 할 것:

1. **이 model pool 에는 섬유 분해자가 사실상 없다.** AGORA 의 섬유 24종 중 **1종(raffinose)** 만
   bundled model 에 exchange 가 있다 (iSFV_1184, iYO844 각각 1/24, 나머지 3개는 0/24). 즉
   "high fiber" 대조는 **섬유 발효 대조가 아니다.** 남는 차이는 단당/이당 3.8배, 지방 2배,
   raffinose 22배다. 그림이 섬유 발효를 시사하게 만들지 말 것.
2. **AGORA 식이의 탄소 86.5 % 는 두 식이에 동일한 flat "other" block** 에서 온다. 그래서 AGORA
   쌍의 community growth 차이는 1.0 % 뿐이다(0.1407 vs 0.1393). 민감한 대조가 필요하면 VMH 쌍을
   쓸 것 — 18 % 차이(0.0719 vs 0.0847 at `_x100`).
3. **VMH 문헌 스케일(`_x100` 없는 파일)은 이 5개 모델의 유지에너지(ATPM) 하한보다 낮다.** 단일
   모델 exact medium 으로 주면 5개 전부 infeasible 이다(MICOM 자신의 medium 도 마찬가지). community
   경로에서는 member bound 가 abundance 로 스케일되므로 동작한다.

재생성 (`sources/` 에 원본이 전부 미러링되어 있어 네트워크 불필요):

```bash
python -m scripts.build_gut_media            # 재생성
python -m scripts.build_gut_media --check    # 파일이 소스와 어긋나면 exit 1
python -m scripts.build_gut_media --report   # 모델별 coverage + 섬유 coverage
```

## Legacy seed presets — **식이로 인용하지 말 것**

| preset | 내용 | 상태 |
|--------|------|------|
| `western_diet.csv` | `EX_glc__D_m,20.0` (1행) | ❌ 출처 없음. AGORA 공표값의 **134.24배** |
| `high_fiber.csv` | `EX_glc__D_m,3.0` (1행) | ❌ 출처 없음. **섬유가 없다.** AGORA 공표값의 **76.00배** |

포도당 한 종만 든 파일이고 20/3 에 출처가 없다. AGORA Supp Table 12 는 D-glucose 를
Western **0.14898579**, high fibre **0.03947368** mmol gDW⁻¹ h⁻¹ 로 공표한다 — 내부 비율도
20/3 = 6.667 vs AGORA 3.774 로 다르다. 또 `EX_glc__D_m` 은 `iAF987` 에 없어 그 모델에서는 아무 일도
하지 않으며, O₂ 를 닫지 않아 위의 81 % 과대추정을 유발한다. "medium 을 바꾸면 답이 바뀐다" smoke
test(`tests/test_medium_spec.py`) 용도로만 유지한다. 감사 내역은 PROVENANCE §1.

## 적용 의미(공통)

- exchange_id 는 community medium 키(`EX_*_m`)에 맞춘다. 대상 모델이 `EX_*_e` 를 쓰더라도
  대사체 기준으로 번역되어 적용되며, **현재 닫혀 있는 exchange 도 열린다**.
- 대응 exchange 반응이 아예 없는 대사체는 기본적으로 **오류**이고,
  `--allow-unknown-medium` 을 준 경우에만 무시되며 그 사실이 diagnostic/warnings 에 기록된다.
- overlay 는 **이 5개 모델 pool 에 맞춰진 것**이다. 다른 pool 에서는 closure block 이 불완전할 수
  있다 (PROVENANCE §9).
