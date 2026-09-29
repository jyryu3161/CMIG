# 도메인 규칙

명세서(`CMIG_명세서_v3.0.md`)와 다른 항목 — 솔버 역할, golden 변형, 숙주 구성 — 은 수락된 결정에 따른 현재 규칙이며, 명세서의 해당 문구는 개정 전 문구다.

## 용어

| 용어 | 뜻 | 혼동 주의 |
|---|---|---|
| 환경 exchange (`EX_<met>_m`) | 커뮤니티 전체 ↔ 외부 배지 경계의 순(net) flux | 멤버 exchange(멤버 ↔ 공유 pool)와 다른 기준(basis)이다 |
| 멤버 기여 | 멤버 ↔ 공유 pool flux | 멤버 1 gDW 기준(per-taxon)인지 커뮤니티 기준인지 항상 구분한다 |
| 커뮤니티 기준 weight | 멤버 flux × 멤버 상대 abundance (mmol gDW_community⁻¹ h⁻¹) | tidy 1.3 이후 `edges.weight`는 이미 커뮤니티 기준이다. abundance를 다시 곱하면 이중 계산이다 |
| 요청 멤버 / 실효 멤버 | 사용자가 요청한 멤버 집합 / MICOM이 실제로 조립한 멤버 집합 | MICOM은 아주 작은 상대 abundance를 조용히 버릴 수 있다 |
| merge 배지 | 배지 파일을 모델 기본 경계 위에 덮어씀 | 이름 없는 대사체는 모델 기본값(흔히 무제한 산소 포함)이 그대로 남는다 |
| exact 배지 | 모델 경계 전체를 닫은 뒤 파일에 있는 것만 연다(`exact_boundary_isolation`) | 보고용 결과의 권장 모드 |
| 과학적 성공 / 산출물 성공 | solve가 해석 가능한 답을 냄 / 파일이 온전히 게시됨 | 산출물이 있어도 과학적 실패일 수 있다(종료 코드 3) |
| full-flux / QP-only 근사 | Gurobi로 QP 성장 + LP pFBA flux까지 계산 / OSQP로 QP만 풀어 멤버 flux 전체가 없음 | OSQP 결과를 full-flux로 표기하면 안 된다 |

## 부호 규약

- `+` = 환경(또는 pool)으로 **분비**, `−` = 환경(또는 pool)에서 **흡수**. 환경 exchange와 멤버↔pool 모두 같은 규약이며 둘 다 `secretion`/`uptake` 라벨을 쓴다.
- 화면·tidy의 `ui_flux`는 항상 ≥ 0인 크기이고 방향은 라벨이 담는다. 기준 사례: 환경 raw −10 → (10, uptake), +8 → (8, secretion); 멤버↔pool raw −5 → (5, uptake), +3 → (3, secretion).
- 물리량 변환: 경계 대사체 계수가 c인 exchange의 반응 flux v에 대해 대사체 이동량은 q = −c·v 이다. 역방향 exchange(`--> glc__D_e`)와 비단위 계수 exchange에서도 농도 변화·숙주 흡수량·전달량은 이 식을 따른다. 반응 방향을 뒤집어도 물리적 소비·전달량은 같아야 한다.
- 배지 한계는 COBRA 반응 flux 경계로 남는다. 배지 파일의 `uptake_limit`(≥ 0, mmol gDW⁻¹ h⁻¹)은 검증된 exchange 방향에서 `lower_bound = −uptake_limit`로 적용된다.

## 배지

- 모든 배지 인자 명령은 merge(기본)와 exact(`--exact-medium`)를 명시적으로 구분하고, manifest에 기록한다. workflow manifest에서는 이 모드가 배지 checksum과 함께 hash에 들어간다. 반례: legacy 커뮤니티 solve(`cmig solve`)의 11구성요소 hash는 배지 checksum만 담고 모드는 hash 밖 기록이라, 같은 배지 파일의 merge run과 exact run이 같은 `run_hash`에 다른 결과를 가진다. 이 경우 두 run은 기록된 모드로 구분한다.
- exact 모드는 exchange뿐 아니라 sink·demand를 포함한 **모든 경계 흡수**를 닫은 뒤 파일 항목만 연다. 닫힘은 가정하지 않고 측정해 기록한다.
- 예외: 조성 없음 표시(formula `X`) 대사체를 공급하는 **exchange가 아닌** 경계 반응(AGORA의 `--> dnarep_c` 등)은 원자를 더하지 않으므로 열어 두고, 열어 둔 반응을 run 기록에 남긴다. formula가 **없는** 대사체는 질량으로 취급해 닫는다(모름 ≠ 0). exchange는 formula가 `X`여도 절대 이 예외로 열지 않는다(`EX_biomass_e`를 열면 모델이 자기 산물을 먹는다).
- 배지 id가 커뮤니티에 대응 exchange가 없으면 입력 오류(종료 2)다. `--allow-unknown-medium`을 주면 해당 id를 빼고 진행하되 run 상태는 `degraded`, `medium_unapplied` 진단에 빠진 id를 적고, `medium_checksum`은 요청한 전체 배지로 계산한다. 이 모드의 결과는 보고용 결과가 아니다.
- 같은 대사체를 두 namespace로 적으면(`EX_glc__D_m`과 `EX_glc__D_e`) 입력 오류다. 이름이 바뀐 단위 계수 exchange는 대사체 topology로 찾고, 대응이 둘 이상이면 오류다.
- MICOM 0.39는 비단위 계수 입력 exchange를 커뮤니티에서 보존하지 못하므로, 그런 모델은 커뮤니티 solve 전에 거부한다. 단일 모델 dFBA와 숙주 결합에서는 허용된다.
- `medium-gap`: 배지를 exact로 적용하고, `--min-growth`에 도달하는 **추가** 경계 반응의 최소 개수 집합을 cardinality MILP로 찾고, 다시 solve해 검증한 뒤 leave-one-out으로 필수 항목을 가린다. 기본 산소 모드는 혐기다(혐기성 균을 호흡시켜 "고치는" 답 금지). 목적함수 자신의 산물은 후보에서 뺀다. 보충 배지 파일의 추가 행은 `row_role: gap_supplement`로 표시되며, 발표된 식단의 일부로 보고하면 안 된다. 모델 내부 sink/demand가 필요한 보충은 배지 파일로 공급할 수 없으므로 따로 보고한다.
- 출처 없는 단일 행 glucose 파일(`western_diet.csv`, `high_fiber.csv`)은 smoke 용도이며 식단으로 인용하면 안 된다. `row_role: pool_closure` 행은 번들 5모델 pool의 배경 닫기 블록이다. 이를 지운 뒤 merge하면 무제한 산소 기본값이 되살아난다.

## Namespace gate

- exchange 대사체 매핑 결정마다 confidence(high/low)와 결정(resolved/unresolved/warned)을 남긴다.
- **unresolved + high confidence가 한 건이라도 있으면** MICOM 호출 전에 solve를 막고 해소를 요구한다. low confidence는 경고 후 진행하되 자동 병합은 하지 않는다. 모든 차단·경고는 audit에 남는다.
- 매핑 결정 목록은 solve `run_hash`의 구성요소다. 차단된 조건은 정상 run이 될 수 없고, sweep에서는 `status=failed`와 진단으로만 기록된다.
- BiGG namespace를 사용자가 명시적으로 주장할 수 있다(`--assume-bigg-namespace`). 이 주장도 hash에 들어간다.

## 멤버십·abundance·성장

- taxonomy id는 비어 있지 않고 유일해야 한다. abundance는 유한한 양수여야 한다(0, 음수, NaN, inf는 거부).
- 요청 멤버와 실효 멤버가 다르면 그 후보는 거부된다. 정확히 k개를 골랐다는 사실은 k개 모두가 양의 성장을 하거나 안정적으로 공존한다는 증거가 아니다.
- 커뮤니티 최대 성장 μ\* ≤ 1e-6이면 그 후보는 `non_viable`이다. 순위에 넣지 않고 평가 불가 목록으로 격리하며, run 경고에 원인이 타깃이 아니라 배지라고 적는다.
- 타깃 최적화 시 커뮤니티 성장 하한은 `max(f·μ*, 절대 하한)`이고, 멤버 성장 하한은 선택이다. 멤버 하한을 쓰려면 멤버 목적함수가 있는 MICOM community여야 한다.
- 탐색은 선택된 집합 안에서 입력 abundance를 재정규화한다. abundance를 동시에 최적화하지 않는다.

## 조합 탐색

- 방향 4종: `max_secretion`, `min_secretion`(분비 억제이며 흡수에 의한 해독과 다르다), `max_uptake`, `min_uptake`. 분비 방향은 v ≥ 0, 흡수 방향은 v ≤ 0 영역에서 최적화한다. 가능한 최솟값이 0이면 0은 정상 해다.
- 전략: `exhaustive`, `random`, `ga`, `auto`. `auto`는 후보 수 ≤ `--exhaustive-max`(기본 100)일 때만 exhaustive이고 그 위에서는 GA로 바뀐다. 전역 최적을 보증해야 하면 `exhaustive`를 명시한다. GA·random 결과는 근사라는 경고를 달고, 전역 최적을 주장하지 않는다.
- GA genome은 멤버 집합이다. 부모 선택·생존의 동점은 seed로 결정적으로 깬다. seed, 평가 예산, 정책 이름(`consortium_search_v2` / `set_ga_v2`)이 탐색 provenance에 기록되며, 의미가 바뀌면 이 이름을 올려 이전 결과와 구분한다.
- 다중 타깃 metric: `normalized_weighted`, `carbon_equivalent`, `raw_sum`, `pareto`. 보고 점수는 LP 목적식과 같은 affine 척도(`Σ w_t·(u_t − b_t)/s_t`)이며, 잘라내지(clip) 않는다. GA·random의 `normalized_weighted`는 고정 reference scale(`--target-scales`)을 요구한다. exhaustive의 관측 범위 정규화는 비교한 pool에 따라 달라진다.
- Pareto: 공동으로 feasible한 벡터의 극점과 epsilon slice를 모은 **표본** 전선이다. 각 타깃의 독립 최댓값을 한 해처럼 보여 주면 안 된다. 모든 LP 시도(기준선 2회, 타깃별 capability, slice, 최소화 보조)를 시도 ledger에 기록하고, 해결(optimal·infeasible)과 실패(timeout·error)를 따로 센다. 나중 시도가 timeout/error여도 이전 feasible 점은 보존하고, 후보를 partial로, run을 degraded로 표시한다. 전선의 rank는 보고 순서일 뿐이다.
- 사후 검증(leave-one-out, monoculture, 배지·abundance 섭동)은 별도 예산이며 GA fitness 예산에 포함되지 않는다. 이는 민감도이지 synergy나 인과의 증거가 아니다.
- 순위에는 과학적으로 유효한 후보만 들어간다. `missing`(타깃 exchange 없음), `non_viable`, `timeout`, `error`, 취소된 평가는 각각 구분해 unevaluated 목록과 ledger에 남기고, 어떤 경우에도 "최고"로 순위화하지 않는다.

## 상호작용 추출

- cross-feeding m→m′은 m이 분비(+)하고 m′이 흡수(−)할 때만 성립한다. 공유 pool flux만으로는 실제 donor→recipient 전달을 식별할 수 없으므로, 대사체별 총 전달량 `min(총 분비, 총 흡수)`를 donor 공급·consumer 수요에 비례 배분한다. 이 배분은 측정값이 아니다.
- `profile.net_flux`와 대조할 때는 `edge_type ∈ {secretion, uptake}` 행만 부호를 붙여 합한다(`cross_feeding` 행 제외). 멤버 abundance가 없으면 커뮤니티 기준 weight를 만들 수 없으므로 산출 생성이 실패한다(척도를 지어내지 않는다).

## 숙주-미생물 결합

- 숙주는 커뮤니티 성장 목적함수에 포함되지 않는다. viability/maintenance 하한 제약으로만 들어간다.
- 경계면: lumen(미생물 공유) `+` = 숙주→lumen 분비, `−` = 숙주가 lumen에서 흡수; blood(숙주 전용) `+` = 숙주→blood 분비, `−` = blood에서 흡수.
- 숙주 격리는 `model.exchanges`만이 아니라 모든 경계 흡수에 적용한다. (이 정책 때문에 Recon3D 숙주 목적값이 368.01에서 0.0으로 바뀌었다. 0.0이 올바른 값이다. 368.01을 회귀 기준으로 쓰면 안 된다.)
- 결합 flux를 해석하려면 양쪽의 gDW 기준(biomass basis)이 필수다. `--microbial-biomass-gdw`, `--host-biomass-gdw`, 기준 종류와 출처가 없으면 실행하지 않는다.
- 검토되지 않은 interface map은 명시적 허용 플래그 없이는 쓰지 않는다. 출판용 결과는 생성된 map을 사람이 검토해야 한다.
- 숙주 목적이 최적이어도 타깃 전달량이 식별되지 않으면(FVA 구간이 한 점이 아니면) 전달 점값은 JSON `null`, CSV 빈칸이며 구간과 이유를 함께 보존한다. 측정된 0은 0으로 남는다. KO 효과·탐색 점수에서 미식별 값을 0으로 채우면 안 된다. 숙주 목적의 변화는 전달량이 미식별이어도 따로 보고될 수 있다.

## 동역학(dFBA)

- well-mixed만 지원한다. 단일 모델과 커뮤니티(`dfba-community`, Gurobi 전용, 한 번 조립한 MICOM의 abundance와 멤버 uptake 한계를 매 step 다시 묶음). 사멸·washout은 모델링하지 않는다. `spatial-preview`는 확산·source/sink 배지 설계 미리보기이며 격자별 FBA가 아니다.
- 매 step: Michaelis–Menten 흡수 한계 → FBA → explicit Euler. 농도는 음수가 될 수 없다(소비 ≤ 가용, 필요하면 dt 반감).
- 추적하지 않는 기질의 흡수가 열려 있으면 결과는 해석 불가다. `--close-untracked-uptake`로 닫거나 해당 기질을 추적해야 한다. 멤버 sink/demand를 통한 숨은 공급도 같은 경계 정책을 적용한다. 각 run은 `acceptance.interpretable`을 스스로 기록하며, false이면 manifest의 더 좋은 상태를 뒤집는다.
- dt/Km 민감도 감사(`dfba-sensitivity`)는 동역학 결과를 보고하기 위한 별도 감사다.

## 통계

- 결정적 sweep 조건은 독립 반복이 아니다. replicate id 열이 있고 사용자가 독립성을 명시적으로 확인했을 때만 p-value를 계산하며, 같은 replicate의 여러 조건은 먼저 하나의 관측치로 합친다.
- 기본은 robust 방법(Cliff's δ, Mann-Whitney/Kruskal)이고 정규성 가정 검정은 선택이다. 다중검정은 BH(또는 BY) FDR.
- 그룹 내 분산이 0인데 평균이 다르면 효과 크기는 0이 아니라 "정의 불가"(null + 진단)다.

## 결과 상태

- 과학적 실패(`failed`)는 산출물이 있어도 결과가 아니다. 실패를 성공으로 바꾸는 사용자 선택(실패 run 허용)은 판정만 바꿀 뿐 그 run을 결과로 만들지 않는다.
- `degraded`는 실패가 아니지만 경고가 붙은 결과다(예: 배지 일부를 버리고 진행, Pareto 부분 timeout). 보고할 때는 경고를 함께 적는다.
- run 상태 어휘는 닫혀 있지 않다(`ok`, `degraded`, `failed`, `unknown`, 그리고 그대로 전달되는 `infeasible`, `stalled` 등). 모르는 값은 모두 not-ok로 취급한다. `unknown`은 통과가 아니다. `acceptance.interpretable: false`는 상태를 더 나쁘게만 바꿀 수 있다.

## 재현성 지문

- **solve `run_hash`**: 정확히 11개 구성요소 — model checksum, medium checksum, member set, abundance, bounds, tradeoff f, solver setting, MICOM 버전, CMIG core 버전, namespace 매핑 결정, flux 정규화 방법. env lock은 포함하지 않는다. 구성요소 추가·삭제는 금지다. float는 6자리 반올림이 무손실일 때만 반올림하고, 아니면 정확한 값을 `f64:` 토큰으로 쓴다.
- **workflow `run_hash`**: 18개 workflow kind마다 고정된 구성요소 튜플(맨 앞은 항상 `workflow_kind`)을 canonical JSON → SHA-256. manifest schema 1.2.
- `run_hash`는 **입력**을 인증할 뿐 답을 인증하지 않는다. 결과를 바꾸는 정책 변경(배지 적용, 경계 격리, 숙주 격리, 물리량 변환, 숙주 전달, 통계, Pareto 표본)은 hash 밖의 provenance 표식(`medium_policy`, `boundary_isolation_policy` 등)에 정책 버전으로 남긴다. 결과가 바뀌었는데 hash가 같을 수 있으므로, 이전 run의 유효성은 이 표식으로 판정한다(예: `medium_policy`가 없거나 `open_uptakes_exact_key_v1`이면 재실행 대상).
- **`result_digest`**: workflow manifest가 선언한 산출물 바이트의 지문. 일치는 바이트 일치일 뿐 과학적 해석을 검증하지 않는다. 산출물이 결정적인 kind(`delta`, `host_map`, `minimal_medium`, `pair`, `single`)만 run 간 비교가 가능하고, 나머지 kind는 같은 입력으로도 digest가 달라진다. legacy `solve` manifest에는 없다(`not recorded`가 정상).
- CMIG core 버전은 solve hash 구성요소이므로 버전을 올리면 solve golden hash가 반드시 바뀐다. 서로 다른 core 버전의 `run_hash`는 비교할 수 없다.

## Sandbox와 sweep

- Sandbox는 reaction flux를 직접 바꾸지 않는다. 멤버 반응 경계를 바꾸고 커뮤니티를 재최적화한다. 우회 보상으로 변화가 작으면 "유의한 변화 없음"과 FVA 범위를 보여 준다.
- Sandbox 결과는 기본적으로 preview(임시)이며 store·cache·sweep에 기록하지 않는다. 사용자가 Apply/Save할 때만 run artifact로 승격되고 그때 `run_hash`가 생긴다.
- Sweep 축은 {배지 변형, abundance, 멤버 집합, bounds, tradeoff f, solver} 6종이다. 같은 `run_hash`면 캐시를 재사용한다. 실패한 조건도 `condition_id`별로 `status=failed`와 비어 있지 않은 진단으로 저장하며 누락하지 않는다.

## 솔버 표기

- `gurobi`: full-flux 기준 경로. OSQP를 받는 분석은 단일 커뮤니티 solve, 단일 모델 분석(FBA/pFBA/FVA), 단일 모델 dFBA와 그 민감도 감사, sandbox 예시뿐이다. 멤버 flux 전체나 MILP가 필요한 나머지(조합 탐색, pair, minimal medium, medium-gap, 균주 성장·abundance·KO 영향, 숙주 결합, community FVA, community dFBA, 모델 품질, 출판 벤치마크)는 Gurobi만 받는다.
- `osqp`: 지원되는 community solve에서 `flux_report_status = qp_only_approximate`, `flux_solver = null`로 기록한다. 멤버 flux 전체가 필요한 경로에는 쓸 수 없다.
- HiGHS는 어떤 명령의 `--solver`로도 고를 수 없다. `highspy` 설치는 COBRA 어댑터 가용성을 뜻하지 않는다. 솔버 가용성 목록은 선택 가능성이나 Gurobi 라이선스 유효성을 증명하지 않는다(실제 작은 solve로 확인).

## 해석 한계 (결과를 보고할 때 반드시 함께 적는 것)

- FVA 범위는 feasible 범위이지 통계적 신뢰구간이 아니다. 탄소 등가 flux는 수율·titer·생물학적 효능이 아니다. 큰 타깃 flux는 강한 단독 생산자만으로도 나올 수 있다(별도의 synergy/null-model 목적은 현재 없음).
- 번들 `models/` pool(iML1515, iYO844, iAF987, iSFV_1184, iHN637)은 장내 커뮤니티가 아니다. 이 pool 위의 결과는 방법 시연이며 장내 생물학으로 제시하면 안 된다.
- 단위 테스트 통과는 출판 타당성을 증명하지 않는다. 출판 결과는 실제 입력·라이선스 솔버·검토된 interface map·dFBA 민감도 감사를 거친 출판 검증 절차를 따른다.
