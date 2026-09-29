# 외부 인터페이스 계약

CMIG의 소비자는 (1) `cmig` 명령을 부르는 사람·스크립트·LLM 에이전트, (2) run 디렉터리를 읽는 후속 분석·그림 도구, (3) GUI 사용자다. 네트워크 API와 인증은 없다. 로컬 OS 권한으로 명령을 실행하면 된다.

## 공통 규약

- **호출**: `uv run cmig <command> [options] --out <dir>`. 플래그의 권위 있는 목록은 `cmig <command> --help`다. `cmig workflows --format json`은 GUI 기능 → 명령 대응, 필수 인자, 흔한 옵션, 예상 산출물, 복사용 예시 명령을 주는 경로 안내일 뿐 모든 플래그 목록이 아니다.
- **종료 코드가 판정이다**: 산출 파일의 존재가 아니라 `$?`로 판단한다.

| 코드 | 뜻 |
|---|---|
| `0` | 분석이 돌았고 run 상태가 `failed`가 아님(`ok` 또는 `degraded`), 또는 `--allow-failed-run` |
| `1` | 예상하지 못한 실행 실패: `solve`/`solve-fixture`의 facade 실패, `dfba`/`dfba-community`의 엔진 예외·산출 쓰기 실패, `agora2-fetch`에서 일부 모델만 실패 |
| `2` | 입력 오류(잘못된 배지, 두 namespace로 적은 대사체, 대응 exchange 없는 배지 id, 없는 파일, 모르는 플래그, namespace gate 차단). 분석을 시도하지 않음. 예외: `solve`는 산출 쓰기의 `OSError`도 2로 끝낸다 |
| `3` | 산출물은 썼지만 과학적 solve 실패(`failed`). `agora2-fetch`에서는 요청한 모델을 하나도 받지 못함. `inspect-run`에서는 산출물 무결성 불일치 |

- `degraded`는 종료 0이다. 종료 0만 보고 결과를 채택하지 말고 `status`와 경고를 함께 읽는다.
- `--allow-failed-run`: `solve`, `pair`, `delta`, `single`, `minimal-medium`, `strain-growth`, `abundance-impact`, `gene-ko-search`, `search`, `sweep`, `dfba-community`, `dfba-sensitivity`, `host-microbe-bigg`, `host-search-bigg`, `host-ko-impact`에만 있다. 상태 `failed`의 종료 코드만 0으로 바꾸며 run을 결과로 만들지 않는다. 다른 명령(`dfba`, `model-quality`, `publication-benchmark`, `spatial-preview`, `model-review` 등)에 주면 argparse 오류(2)다.
- **run 디렉터리**: 실패해도 진단용 산출물을 쓴다. 대부분의 workflow는 `manifest.json`(workflow manifest, schema `1.2`)을 쓰고, `solve`/`solve-fixture`는 legacy solve manifest(11구성요소 `run_hash`, `result_digest` 없음)를 쓴다.
- **상태 어휘는 열려 있다**: `ok`, `degraded`, `failed`, `unknown` 외 값(`infeasible`, `stalled` 등)이 그대로 올 수 있다. 소비자는 모르는 값을 not-ok로 취급해야 한다. `unknown`은 통과가 아니다.

## 입력 형식

| 입력 | 형식 | 오류 |
|---|---|---|
| GEM | `.xml`/`.sbml`/`.xml.gz`(SBML), `.json`(cobra), `.mat` | 모르는 확장자·파싱 실패 → 종료 2 |
| 모델 폴더 | `--model-dir <dir>` | 모델 없음 → 2 |
| taxonomy CSV | 열 `id`(유일·비어 있지 않음), `file`(모델 경로), 선택 `abundance`(유한 양수) | 중복 id, 잘못된 abundance → 2 |
| 배지 | CSV `exchange_id,uptake_limit` 또는 JSON. `uptake_limit ≥ 0`, 단위 mmol gDW⁻¹ h⁻¹. 여분 열(`row_role` 등)은 무시 | 음수, 두 namespace 중복, 대응 없는 id(`--allow-unknown-medium` 없을 때) → 2 |
| 배지 모드 | `--medium`(숙주 명령은 `--microbe-medium`/`--host-medium`, 배지 행렬은 `--mediums`) = merge 기본, `--exact-medium` = 파일이 전체 환경 | manifest `medium_application_mode`에 기록. workflow manifest에서는 hash 구성요소, legacy `solve` manifest에서는 hash 밖 기록 |
| 숙주 interface map | `cmig host-map`이 만든 JSON을 사람이 검토한 것 | 미검토 map은 명시적 허용 플래그 없이 거부 |
| 숙주 biomass 기준 | `--microbial-biomass-gdw`, `--host-biomass-gdw`, `--biomass-basis-kind`, `--biomass-basis-source` | 누락 → 실행 거부 |

## 명령 목록 (`cmig workflows`에 34개 GUI 대응 workflow)

| 분류 | 명령 |
|---|---|
| 환경·판독 | `version`, `solvers`, `workflows`, `inspect-run`, `golden verify`, `golden verify-envelope` |
| 모델 준비 | `agora2-list`, `agora2-fetch`(유일한 네트워크 명령), `model-quality`, `model-review`, `namespace-suggest`, `medium-gap`, `minimal-medium` |
| 커뮤니티 | `solve`, `solve-fixture`, `pair`, `delta`, `single`, `strain-growth`, `abundance-impact`, `sweep`, `sweep-fixture`, `sandbox-fixture` |
| 탐색 | `search`, `search-fixture`, `search-advanced-fixture`, `gene-ko-search` |
| 숙주 | `host-fixture`, `host-generic`, `host-benchmark`, `host-map`, `host-microbe-bigg`, `host-search-bigg`, `host-ko-impact` |
| 동역학 | `dfba`, `dfba-fixture`, `dfba-community`, `dfba-sensitivity`, `spatial-preview` |
| 통계·출판 | `stats-demo`, `stats-sweep`, `publication-benchmark`, `render-figure` |
| 앱 | `gui` (`cmig-gui`와 같음, `--lang en|ko`) |

솔버 선택(`--solver`):

| 선택지 | 명령 |
|---|---|
| `{gurobi, osqp}` | `solve`, `solve-fixture`, `single`, `dfba`, `dfba-sensitivity`, `sandbox-fixture` |
| `{gurobi}`만 | `pair`, `minimal-medium`, `medium-gap`, `strain-growth`, `abundance-impact`, `gene-ko-search`, `search`, `search-fixture`, `search-advanced-fixture`, `dfba-community`, `dfba-fixture`, `host-fixture`, `host-generic`, `host-benchmark`, `host-microbe-bigg`, `host-search-bigg`, `host-ko-impact`, `model-quality`, `publication-benchmark` |
| 솔버 인자 없음 | 나머지(판독·모델 준비·통계·그림·`delta`·`sweep`·`host-map`·`spatial-preview` 등) |

HiGHS·CPLEX는 어떤 명령에서도 고를 수 없다.

## `cmig inspect-run --format json` (payload schema `1.2`)

- 입력: `--run-dir <dir>`. 출력 키: `schema_version`, `run_dir`, `kind`, `status`, `status_source`, `summary_file`, `run_hash`, `artifact_integrity`(`verified` / `mismatch` / `not_recorded`), `result_digest`, `result_digest_absent_reason`, `artifacts`, `manifest`(요약), `summary_keys`, `edge_weight_basis`.
- `status_source`: `manifest`, `summary`, `derived`, `acceptance.interpretable`, `host_map_counts`, `solve.status`, `namespace.blocked`, `inference.status`, `no_status_signal`, `unknown`, `result_digest_mismatch` 중 하나.
- 무결성 불일치면 `status: failed`, 종료 3. 그 밖에는 분석 실패여도 종료 0(분석 명령의 종료 코드가 판정).
- 상태 판정은 더 나빠지는 방향으로만 덮어쓴다(`acceptance.interpretable: false`가 manifest의 좋은 상태를 뒤집음).

## 재현성 지문

- `run_hash`: 입력 인증. 같은 입력 → 같은 hash. solve는 11구성요소, workflow는 kind별 구성요소(18 kind). 서로 다른 CMIG core 버전·manifest schema의 hash는 비교할 수 없다.
- `result_digest`: 모든 workflow manifest가 선언한 산출물 바이트의 지문이다. 같은 run 안에서의 무결성 확인용이며, **서로 다른 run 사이의 비교**는 payload의 `cross_run_comparable`이 참인 kind(`delta`, `host_map`, `minimal_medium`, `pair`, `single`)에서만 의미가 있다. 다른 kind는 타임스탬프·그림 래스터·parquet 쓰기 id 때문에 같은 입력으로 두 번 돌려도 digest가 다르다. 바이트 일치는 과학적 해석이나 선언되지 않은 파일을 검증하지 않는다.
- hash 밖 provenance 표식(`medium_policy`, `exchange_readout_policy`, `host_transfer_policy`, `statistics_policy`, `pareto_sampling_policy`, `boundary_isolation_policy`, `host_isolation_policy`)은 결과 의미를 바꾼 정책 버전이다. 같은 hash의 두 run이 이 표식에서 다르면 결과를 비교하면 안 된다.

## tidy 산출 (Parquet, schema `1.3`)

모든 표에 `schema_version` 열이 있다.

| 표 | 열 |
|---|---|
| `nodes.parquet` | `node_id`, `node_type`, `label`, `growth`, `abundance`, `organism_type`, `interface`, `compartment` |
| `edges.parquet` | `source_id`, `target_id`, `metabolite`, `edge_type`(`secretion`/`uptake`/`cross_feeding`), `weight`(≥ 0, 커뮤니티 기준 mmol gDW_community⁻¹ h⁻¹), `label`, `allocation_method`, `identifiable`, `weight_lo`, `weight_hi`(예약, 현재 채워지지 않음) |
| `profile.parquet` | `metabolite`, `net_flux`(+ 분비 / − 흡수), `ui_flux`(≥ 0), `label`, `fva_lo`, `fva_hi`, `organism_type`, `interface`, `compartment` |

- `edges.weight`에 abundance를 다시 곱하지 않는다. `net_flux`와 맞추려면 `secretion`/`uptake` 행만 부호를 붙여 합한다(`cross_feeding`은 비례 배분이지 측정이 아님).
- 1.2 이하 번들은 읽을 때 의미 변환된다.
- sweep 집계는 `sweep.parquet`(long format: `condition_id`, 축 값, `metric`, `value`, `run_hash`, `status ∈ {ok, failed}`, `diagnostic`; failed면 진단 필수, 값 null).

## 탐색 산출

- 순위 CSV/JSON(`search_summary.json`)에는 과학적으로 유효한 후보만 들어간다. `missing`, `non_viable`, `timeout`, `error` 등 평가되지 못한 후보는 `search_unevaluated.csv`에 상태와 함께 들어간다.
- 다중 타깃: 보고 점수 = LP 목적식과 같은 affine 척도(자르지 않음). 그림은 음·양 기여를 0 양쪽에 그리고 저장된 총점을 표시한다.
- Pareto: 표본 전선, 시도 ledger(해결·실패 개수), 전선 rank는 보고 순서.
- 다중 타깃(타깃 2개 이상) Pareto 그림 `search_pareto.svg`/`.tiff`: 타깃 쌍마다 패널 하나(k(k−1)/2개). 점은 top-k가 아니라 `search_evaluations.json`의 평가 행 전체 중 `status == optimal`, `flux_basis == joint_weighted_lp`, 두 축 값이 유한한 행뿐이다(capability 기준·실패·non-viable·missing·timeout·평가 불가는 찍지 않고 0으로 채우지 않는다). 축은 기록된 flux와 부호(+ 분비 / − 흡수, mmol gDW⁻¹ h⁻¹)를 그대로 쓰고 라벨에 방향과 좋은 쪽 화살표를 적는다. 비지배 강조는 기록된 `pareto` 표식이다(다시 계산하지 않음). 결손 타깃 축에서는 기록된 0에 속이 빈 표식("target exchange absent")으로 찍는다. pareto metric은 표본 근사 경고, 비-exhaustive 전략은 "approximate search"를 싣는다. 찍을 점이 없으면 파일을 쓰지 않는다(오류 아님). 그림 작성 실패 시 파일을 지우고 summary `warnings`에 "Pareto figure not written: <원인>"을 남기며 결과·다른 산출물·종료 코드는 그대로다. 파일이 있을 때만 summary/manifest `artifacts`에 들어간다.
- 숙주 전달 점값이 식별되지 않으면 JSON `null`, CSV 빈칸 + 구간·이유 열. 0은 측정값이다.
- `medium_gap_supplemented.csv`의 보충 행은 `row_role: gap_supplement`.

## Python 라이브러리

`cmig`는 import 가능하지만 공개 Python API 안정성은 약속하지 않는다. 안정 계약은 CLI, run 디렉터리 산출물, manifest다.

## 에이전트 skill

`.claude/skills/cmig-metabolic-analysis/`와 `.claude-plugin/marketplace.json`은 사용자용 Claude Code skill/plugin이다. 요청 → 명령 대응과 과학적 타당성 안전장치(숙주 biomass 기준, 검토된 interface map, 솔버 provenance, dFBA 민감도 감사)를 담는다. CLI 플래그가 바뀌면 skill의 명령별 참조를 `--help`와 다시 맞춘다. 개발 규칙의 출처가 아니다.
