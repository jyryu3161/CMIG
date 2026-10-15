# 엔지니어링 노트

## 함정

**다른 프로젝트 환경으로 실행됨**
- 증상: git worktree나 형제 checkout에서 `uv run cmig workflows`는 되는데 분석 명령은 모두 "엔진 stack 필요"로 실패한다.
- 원인: `uv run`은 가장 가까운 `pyproject.toml`의 프로젝트를 쓴다. worktree마다 새 최소 `.venv`(engine extra 없음)가 만들어지고, 오류 메시지가 알려 주는 해결책은 엉뚱한 프로젝트를 동기화한다.
- 대응: 동기화한 checkout에서 실행하거나, worktree에서도 `uv sync --extra engine --extra gui --extra render --extra stats`를 먼저 한다. hook·실행기는 저장소의 `.venv` Python을 요구하며 없으면 검사를 blocked로 처리한다.

**pytest 요약 줄이 안 보임**
- 증상: `uv run pytest -q` 출력에 통과/실패 요약이 없다.
- 원인: `pyproject.toml`의 `addopts = "-q"`에 `-q`를 더하면 `-qq`가 된다.
- 대응: 추가 `-q`를 빼거나 `-ra`/`--junitxml`로 결과를 확인한다. 테스트 순서는 `pytest-randomly`로 매번 섞이므로 순서 의존 실패는 출력 첫 줄의 seed를 `-p randomly --randomly-seed=<seed>`로 다시 주어 재현한다.

**가짜 Rscript가 플랫폼 캐시를 가로챔**
- 증상: 렌더 테스트를 특정 순서로 돌리면 무관한 테스트가 플랫폼 정보를 잘못 읽는다.
- 원인: 테스트용 가짜 `Rscript` subprocess 대역이 `uname -p` 호출까지 가로챘다.
- 대응: 가짜 대역은 `--out`이 없는 명령을 실제 `subprocess.run`에 넘긴다. 새 대역도 같은 방식을 따른다.

**AGORA2 원본 파일은 UTF-8이 아님**
- 증상: libsbml "Badly formed XML", cobra "No SBML model detected in file".
- 원인: UTF-8 선언인데 species 이름에 Latin-1 바이트(`ß`, `è`, NBSP)가 몇 개 섞여 있다(20개 중 약 3개).
- 대응: 해당 바이트만 표적 변환한다. 파일 전체를 latin-1로 읽으면 다른 문자가 깨진다.

**AGORA2 id 변환을 절반만 하면 조용히 실패**
- 증상: namespace gate 0%로 차단되거나, 통과해도 정의 배지에서 성장 0.
- 원인: 구획 표기(`EX_but(e)` → `EX_but_e`)와 이성질체 구분자(`glc_D` → `glc__D`) 두 가지가 모두 BiGG와 다르다. 구획만 바꾸면 D-glucose와 모든 아미노산이 배지와 맞지 않는다(144개 중 93→122개 일치).
- 대응: fetcher의 두 변환을 모두 적용한다.

**AGORA 모델이 어떤 식단에서도 성장 0**
- 원인: 복제·번역 비용을 `--> dnarep_c` 같은 경계 반응(formula `X`)으로 표현한다. 이것을 질량 공급으로 보고 exact 배지에서 닫으면 모든 AGORA 모델이 비생존이 된다.
- 대응: 경계 격리 정책이 비-exchange formula-`X` 공급자를 열어 두고 `pseudo_supply_open`에 기록한다. formula가 비어 있는 경우까지 이 예외로 넓히면 안 된다(테스트용 장난감 모델 대부분이 formula가 없다).

**탐색 속도는 모델 파일 형식이 좌우**
- 증상: 조합 탐색이 매우 느리다.
- 원인: MICOM은 `Community`를 만들 때마다 멤버 모델을 다시 읽는다. 같은 모델이 SBML 14.0 MB/1.72 s, cobra JSON 1.16 MB/0.26 s. 또한 후보마다 community를 2~3번 새로 만든다.
- 대응: 모델 풀은 `agora2-fetch --format json`으로 받는다.

**`auto` 전략이 GA로 바뀜**
- 증상: 20개 중 3개 조합 탐색 결과에 근사 경고가 붙는다.
- 원인: C(20,3)=1140 > `--exhaustive-max` 100이라 `auto`가 GA가 된다.
- 대응: 전역 최적이 필요하면 `--strategy exhaustive`를 명시한다. 단일 균주 사전선별은 `--min-size 1 --max-size 1`로 하되, 혼자서는 타깃을 0으로 내는 cross-feeder(예: lactate/acetate 공급자)가 빠진다.

**merge 배지는 제약이 아닐 수 있음**
- 증상: 배지를 줬는데 성장이 비현실적으로 크다.
- 원인: merge는 파일에 없는 대사체를 모델 기본값으로 둔다. MICOM 기본 `EX_o2_m = 999999`처럼 무제한 산소가 남는다(3멤버 예: 1.2678 vs 산소 지정 시 0.6990 h⁻¹, 81% 과대).
- 대응: 보고용 결과는 `--exact-medium`. 성장 0이면 `cmig medium-gap`을 먼저 돌린다.

**hash가 같은데 숫자가 다름**
- 원인: 결과 의미를 바꾼 정책 수정(배지 적용 v2, 경계 격리 v2, 숙주 격리 등)은 입력을 바꾸지 않아 `run_hash`가 그대로다.
- 대응: `cmig inspect-run --format json`의 `provenance`에서 정책 표식을 비교한다. `medium_policy`가 없거나 `open_uptakes_exact_key_v1`인 run은 재실행한다. `exchange_reactions_by_metabolite_v2` → `_pool_scoped_v3`는 v2가 배지 행 일부를 받을 수 없다는 이유로 거부하던 후보·선택·단일 모델에 답이 생긴 변화이며(pool workflow와, 2026-10-15부터 전체 커뮤니티·단일 모델 workflow), v2가 낸 수치는 바뀌지 않았다.

**GUI 취소가 즉시 멈추지 않음**
- 원인: 취소는 `threading.Event`를 세우는 협조적 취소다. MICOM solve는 GIL을 잡은 C 호출이라 진행 중인 1건은 끝까지 돈다.
- 대응: 새 장기 작업도 후보/조건 경계에서 `ctx.cancelled`를 확인해야 한다. GUI 분석은 같은 프로세스에서 CLI `main`을 부르므로 `SystemExit`도 job 결과로 잡힌다.

**배지 preset 사본 불일치**
- 증상: `tests/test_distribution_audit.py::test_packaged_presets_match_the_canonical_source` 실패, 또는 설치본 GUI에 이전 preset이 보인다.
- 원인: `scripts/build_gut_media.py`는 `medium_presets/`만 다시 쓴다. 설치본은 `cmig/resources/medium_presets/`를 `importlib.resources`로 읽는다.
- 대응: 빌드 후 두 디렉터리를 바이트 단위로 맞춘다.

**한국어 모드에서만 GUI가 죽음**
- 증상: `cmig gui --lang ko`에서 특정 동작 시 `KeyError`.
- 원인: 문구 조회(`CmigMainWindow._message`)가 활성 언어 카탈로그만 보고 영어로 대체하지 않는다. 새 키를 `"en"`에만 넣으면 한국어 모드에서 키가 없다.
- 대응: 새 키는 `"ko"`에도 같은 영어 문구로 넣는다(한국어화는 더 진행하지 않음). 검증: `--lang ko`로 새 화면 경로를 offscreen 테스트.

**Windows에서 실행기 프로세스 정리**
- POSIX는 시간 초과 시 프로세스 그룹 전체를 종료한다. Windows는 `taskkill /T`와 하위 프로세스 스냅샷으로 정리한다. Windows에서 실제로 돌려 보기 전에는 그 플랫폼 동작을 검증됐다고 말하지 않는다.

## 비직관적 메커니즘

- **숙주 목적 368.01 → 0.0**: 숙주 격리를 `model.exchanges`에서 모든 경계 흡수로 넓히자, 신고되지 않은 sink/demand로 들어오던 공급이 끊기면서 Recon3D 숙주 목적값이 0.0이 되었다. 이전 값은 결함에서 나온 것이므로 회귀 기준이 아니다.
- **edges.weight 기준**: tidy 1.3부터 커뮤니티 기준이다. 1.2 이하 번들은 읽을 때 의미 변환되고, 노드 문맥 없는 단독 legacy 엣지 표는 null과 `LegacyEdgeBasisWarning`을 낸다.
- **float hash 규칙**: 6자리 반올림이 무손실이면 기존과 같은 문자열을, 아니면 `f64:` 정확 표기를 쓴다. 그래서 고정 golden hash는 유지되면서 1e-7과 4e-7 같은 입력이 충돌하지 않는다. 문자열 값이 `f64:`로 시작하면 `str:` 접두로 이스케이프한다.
- **`inspect-run`의 판정**: run을 다시 판단하지 않고 설명한다. 종료 코드가 0이 아닌 경우는 산출물 무결성 불일치뿐이다. 분석 성공 여부는 분석 명령의 종료 코드로 본다.

## 반복 작업 체크리스트

**CMIG core 버전을 올릴 때** (core 버전은 solve hash 구성요소)
1. 버전 표면 6곳을 함께 바꾸고 `uv lock`.
2. `uv run --no-sync python -m cmig.golden_fixture`로 gurobi·osqp golden 재캡처(Gurobi 필요).
3. 새 hash를 `tests/test_round5_domain_accuracy.py`, `tests/test_workflow_manifest.py`, `tests/test_round5_p3_io_exception.py`와 `cmig/core/manifest.py` 주석에 반영. (0.3.0 기준 gurobi `31d5647d…`, osqp `b8ca28e3…`)
4. 검증: `cmig golden verify`, `cmig golden verify-envelope`(envelope는 합성 상수에 고정돼 움직이지 않아야 함), `scripts/check_release_versions.py`.
5. CHANGELOG에 이전 버전 hash와 비교 불가임을 적는다.

**workflow hash 구성요소를 바꿀 때**
1. `WORKFLOW_HASH_COMPONENTS`와 `_EXPECTED_ARITY`를 함께 수정(새 이름은 `WORKFLOW_COMPONENT_VOCABULARY`에 추가).
2. `uv run --no-sync python -m cmig.core.workflow_envelope_golden`으로 재승인.
3. 검증: `cmig golden verify-envelope` 통과, 관련 manifest 테스트 통과, CHANGELOG에 이동한 kind 기록.

**AGORA2 카탈로그·네트워크 경로를 고칠 때**
1. 모든 테스트는 offline transport로 한다(실제 VMH 서버 가용성에 기대지 않는다).
2. 검증: `../`, 절대 경로, Windows 구분자, symlink, 리다이렉트 각 단계가 전송 전에 거부되고 출력 폴더 밖 바이트가 그대로인지 `tests/test_agora2.py`로 확인.

**배포 전**
1. `uv build` → `scripts/audit_distribution.py dist/*`.
2. 소스 checkout 밖에 wheel을 새로 설치해 `cmig version`, `cmig solvers`, GUI preset 열기를 확인한다(허용 목록 통과만으로 설치 UX가 검증되지 않는다).
