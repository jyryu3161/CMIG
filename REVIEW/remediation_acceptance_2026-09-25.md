# CMIG 결함 보정 최종 독립 인수 검토 — 2026-09-25

검토자: GPT-6 Astra. Task `task_91ab73823bed`, Dispatch `ctx_7b90f8159222`. 기준 HEAD는 `0167529fa9ba81649b138c476c524dc4495d4954`, 브랜치는 `main`이다. 아래 판단은 이 HEAD 위의 보정 작업 트리를 대상으로 하며, 검토자는 생산 코드·테스트·Git·환경·자격 증명을 변경하지 않았다. 작성 범위는 이 보고서와 `.run/remediation-20260925/final-review/`뿐이다.

**최종 판단: 검토 범위 승인. SC01–SC08/F1–F12의 20개 결함과 별도 기존 CI 원인 세 건의 코드 보정을 인수한다. 미해결 범위 내 material blocker는 없다. 코디네이터는 사용자 승인 범위대로 이 검토 트리를 커밋하고 `main`에 일반 push해도 된다. Push 후 원격 CI 결과는 별도로 확인·보고해야 하며, 현재 원격 solver CI 통과나 WLS 제공을 승인/확인한 것은 아니다.**

## 근거와 검토 범위

`AGENTS.md`, `CLAUDE.md`, 원명세의 MICOM·부호·namespace·search 계약, [보정 설계](remediation_design_2026-09-25.md) 및 모든 `remediation_*_2026-09-25.md` 구현·독립 검토·재검토·통합 triage 보고서를 읽었다. 초기 구현 보고서의 “Fixed”는 당시 재검토가 발견한 R1–R5, RR1/RR2, GR-1–GR-5, GR-2a/b, FR-1보다 우선하지 않는다. 아래 표는 수정 후의 최종 판단이며 역사적 실패 기록을 지우지 않는다.

코디네이터의 최종 범위 지시에 따라 이미 완료된 독립 GUI/SVG 및 IO 검증은 관련 소스 동일성을 확인하여 재사용했다. 이번에 새로 수행한 범위는 RR1/RR2의 실제 LP와 저장·GUI 경계, 공유 판독 helper, 후속 fixture와 문서 검토, 최종 통합 로그 대조다. 전체 pytest나 광범위 GUI 행렬을 중복 실행하지 않았다.

주요 선행 증거:

- [과학 재검토](remediation_scientific_rereview_2026-09-25.md): 212 과학 테스트와 4 GUI 경계 테스트 통과, 실제 MICOM/LP/FVA·worker/resume 검증. 남았던 RR1/RR2는 아래 새 증거로 닫는다.
- [GUI/SVG 독립 인수](remediation_gui_figures_acceptance_2026-09-25.md): 187 통과, 48 loader 변형, 20 malformed 경계, 추가 schema 행렬, 실제 rc=2/3, 12 EN/KO 화면, 네 SVG/TIFF 쌍 및 실제 SVG export. RR2 외의 Search 게시/검증 함수와 figure/export helper 해시가 동일하다.
- [IO 검토](remediation_io_review_2026-09-25.md)와 [과학·IO 후속 검토](remediation_scientific_review_2026-09-25.md): F11/F12·세 CI 원인 승인, F1의 `os.fchmod` 미제공 보정은 후속 84개 IO 테스트 및 실제 공개 fetch API 재현으로 승인됐다. 해당 atomic helper는 동일하다.
- [그림 최초 검토](remediation_figures_review_2026-09-25.md): F2 열 가지 부호/순서/단위 사례와 22개 잘못된 입력 거부가 통과했지만 Qt SVG overflow FR-1을 발견했다. 후속 GUI/SVG 인수에서 실제 최종 파일로 이를 해소했다.

서로 겹치는 부분 시험 수를 합산하여 전체 시험 수로 제시하지 않는다. 해시 대조와 새 실행 결과는 [final-review 증거](../.run/remediation-20260925/final-review/)의 `prior-lane-source-comparison.json`, `gui-function-comparison.json`, `figure-source-reuse.json`, `source-start.json`, `source-end.json`, `residual-results.json`에 보존했다.

## 20개 감사 ID의 최종 처분

여기서 “수정·승인”은 명시한 소프트웨어 계약과 검증 범위의 인수다. 생물학적 효능, 전체 명세 구현 완료 또는 모든 플랫폼 인증을 뜻하지 않는다.

| ID | 처분 | 실제 수정된 동작과 확인 근거 |
| --- | --- | --- |
| SC01 (SC-01) | 수정·승인 | 숙주 목적값과 전달 식별성을 분리한다. `[0,5]`는 null/빈 값과 구간을 보존하고 전달/가중 순위에서 제외하며, 목적값 순위는 사용 가능하되 degraded다. 실제 `[0,0]→[5,5]`의 ±5 KO 연산이 보존되고, RR2 후 `[0,0]`은 CSV `0`/`identifiable=True`와 GUI `0`으로 이어진다. 불확정 구간 차이는 보수적인 marginal bounds이며 공동 달성/신뢰구간이 아니다. [test_remediation_host_cli.py](../tests/test_remediation_host_cli.py), [test_host_ko_impact.py](../tests/test_host_ko_impact.py), 새 실제 writer/readback probe. |
| SC02 (SC-02) | 수정·승인 | community dFBA에서 환경 exchange와 member sink/demand를 포함한 미선언 공급을 닫고 강제 공급은 거부한다. closure 해제 시 동일 적분 해에서 실제 공급량과 `member_biomass`/`community_biomass` 기준을 기록하여 해석 불가를 표시한다. 명시적 formula X 예외와 missing-formula 대조를 유지한다. 과학 재검토 실제 MICOM 한 번의 해·숨은 공급 및 isolation 회귀. |
| SC03 (SC-03) | 수정·승인 | standalone dFBA/host가 `q=-c*v`와 실제 공급 방향으로 비단위·역방향 exchange를 환산한다. community 역방향 member의 Vmax=0 우회를 차단하고 standalone 출력에 `model_biomass` 기준을 제공한다. 실제 ±0.5/±3 단위 환산·FVA·고갈·bounds 복구 및 역방향 zero-cap 대조 통과. [test_remediation_scientific.py](../tests/test_remediation_scientific.py), [test_dfba.py](../tests/test_dfba.py). |
| SC04 (SC-04) | 수정·승인 | 반응 이름 대신 metabolite/pool/member topology로 identity를 정하고 abundance를 한 번만 적용한다. 중복 member 채널의 gross uptake 합에 단일 nutrient budget을 적용하여 중복 채널로 허용량을 늘릴 수 없다. 모호한 medium alias와 MICOM 0.39가 보존하지 못하는 비단위 community 입력은 명시적으로 거부한다. 실제 renamed/unequal-abundance·중복/역방향/blocked-channel·두 timestep 회귀. |
| SC05 (SC-05) | 수정·승인 | baseline, 독립 capability, 보조 최소화, weighted/extreme/epsilon LP별 ledger와 후보/점 상태를 분리한다. 실제 정상 2-target 예는 20 LP/20행이며 capability 벡터를 동시 달성점으로 내보내지 않는다. 1점 뒤 15개 주입 timeout은 점을 유지하고 partial/degraded, 유효점 없음은 failed다. RR1의 baseline 예외도 단계·정책·실행 불확실성을 보존한다. 양 실행 경로, 취소/worker/resume, digest 및 `attempt_ledger_v3` 호환성 검증. |
| SC06 (SC-06) | 수정·승인 | legacy `rank_consortia`도 유한 양수 abundance·중복 ID와 requested/effective membership를 검증한다. `[1,1e-8]`로 한 멤버가 탈락한 해를 두 멤버 결과로 순위화하지 않는다. 유효 입력 대조와 zero/negative/NaN/inf 거부 및 두 membership 진단 확인. |
| SC07 (SC-07) | 수정·승인 | 작은 표본·pooled SD=0 등의 정의 불가 통계량/효과량을 0으로 만들지 않고 null과 이유를 기록한다. 유한 분산 대조는 수치를 유지하고 strict JSON·FDR·volcano 경계가 미확정값을 거부한다. [test_remediation_stats_solver.py](../tests/test_remediation_stats_solver.py) 및 독립 통계 대조. |
| SC08 (SC-08) | 수정·승인 | 패키지 설치와 COBRA/optlang adapter 가용성을 분리한다. `highspy`만으로 native HiGHS를 사용 가능하다고 하지 않으며 `_require_lp`에서 거부한다. 실제 Gurobi/OSQP LP·QP와 Gurobi MILP 성공, OSQP의 MILP 미광고 확인. 라이선스 증거는 capability 목록과 별개다. |
| F1 | 수정·승인 | catalog/direct ID·파일명, 출력 containment·symlink를 검증하고 예측 불가 staging 및 atomic 교체로 기존/외부 파일을 보존한다. Unix 전용 `os.fchmod` 부재에서도 direct SBML 및 세 atomic writer가 작동한다. offline 악성 입력·실제 SBML/JSON 변환·실패 보존 검증. Windows API 부재 모사이며 native Windows 실행은 아니다. |
| F2 | 수정·승인 | 양수/음수를 별도 누적 기점에 쌓고 저장된 signed total을 diamond로 표시한다. 실제 `−10/+13.358851988170386`은 두 방향 bar와 `3.358851988170386` 합계로 보존된다. 음수/양수/0/혼합·정규화 weight 한 번 적용·Pareto report order·22개 malformed/nonfinite 거부 증거와 최종 함수 동일성 확인. |
| F3 | 수정·승인 | Gene KO/Growth/Ratio가 클릭 당시 medium/exact 정책과 해당 workflow 설정을 고정하여 실행한다. 전용 cooperative fraction과 Search 방향/성장 제약을 구분한다. 적용되는 변경은 결과를 무효화하고 무관한 변경은 유지한다. 큐에서 변경한 세 workflow argv, 12 applicability 대조, 실제 parser 및 defined-medium 대조 증거. |
| F4 | 수정·승인, offscreen 범위 | 숨은 탭을 포함한 전체 창과 긴 경고가 1280×800/1500×950을 강제로 확장하지 않는다. EN/KO empty/Pareto/Host 12개 화면의 실제 크기·수평 overflow 없음·scroll과 필수 control 접근을 확인했다. Native window manager/HiDPI 전체 인증은 아니다. |
| F5 | 수정·승인 | rc=3의 실패 Search가 실패 job/summary를 유지하면서 출력 경로·후보 이유·Explorer readback을 제공한다. rc=2의 실제 missing-medium/empty-pool 원인도 남는다. 과학 실패·취소·artifact 성공을 혼동하지 않으며 유효 순위나 없는 그림 export를 만들지 않는다. |
| F6 | 수정·승인 | 공통 `_inspect_run_dir` digest 판정을 GUI가 사용하고 verified/mismatch/not_recorded와 readback invalid를 구별한다. verified A 뒤 manifest 없는 rc=2 B가 A의 검증 상태를 물려받지 않는다. schema 오류는 digest가 맞아도 올바른 과학 화면으로 게시하지 않는다. GR-2a/b 및 대용량 해시 event-loop 검증. |
| F7 | 수정·승인 | 현재 run에 실제 존재하는 지원 그림만 선택한다. 삭제/읽기 실패 선택은 이전 preview를 지우고 export를 비활성화한다. preview와 export artifact가 일치하고 multi-target Scatter를 만들어내지 않는다. |
| F8 | 수정·승인 | 모든 경고·단위/normalizer·실행 조건·semantics·weights/ranges·GA metadata·후보/attempt/sampling 상태와 원문 summary를 선택 가능한 details에 보존한다. 미기록 legacy 정보는 꾸미지 않으며 host range-only 결과도 보인다. 다섯 adapter 경로와 실제 실패 readback 검증. |
| F9 | 수정·승인, 검증 consumer 범위 | GUI는 실제 wide/tall SVG 비율을 유지한다. 저장 SVG는 단일 설치 font로 wrapping/export metrics를 맞춰 Qt clipping FR-1을 해소했다. 실제 SVG/TIFF의 캡션·단위·legend·member label bounds와 raster를 확인했다. Editable text와 RGB 600 dpi LZW를 유지한다. |
| F10 | 수정·승인 | manifest/소비하는 summary nested shape를 게시 전에 검증한다. malformed/null/list/object numeric 입력은 예외 유출·mixed provenance 없이 거부한다. Host는 완전한 이전 상태 유지, Search/dFBA/spatial은 일관된 clear 정책을 사용한다. 실패 job completion도 동일하게 검증한다. |
| F11 | 수정·승인, offline transport 범위 | 정확한 HTTPS origin/허용 route와 redirect의 각 다음 요청을 전송 전에 검증한다. 위험 filename은 custom fetcher 전에도 거부한다. 실제 urllib opener를 쓴 offline transport 22사례에서 금지 요청이 전송되지 않았고 원요청/실효 URL provenance를 보존했다. Live publisher 가용성 증거는 아니다. |
| F12 | 수정·승인 | `importlib.resources`로 wheel의 preset/row/source provenance를 읽고 명시적 `preset_dir=`도 유지한다. Source와 package bytes가 같고 preview는 자원을 수정하지 않는다. README tutorial의 누락 local 링크를 source URL로 수정했다. 최종 direct 및 sdist 경유 wheel의 실제 외부 설치·9 preset/717 provenance row·archive audit 증거는 아래 참조. |

## 별도 기존 CI blocker 세 건

| 기존 원인 | 최종 처분 | 증거와 아직 수행하지 않은 것 |
| --- | --- | --- |
| Python 3.10에 `tomllib` 없음 | 코드 보정 승인 | 3.11+ `tomllib`/3.10 `tomli` 분기와 조건부 dev dependency. 실제 격리 Python 3.10.18에서 정답 tag 성공/오답 tag 실패. Python 최소 버전 및 MICOM pin을 바꾸지 않았고 root package metadata 외 dependency resolution을 바꾸지 않았다. |
| Windows locale/console | 코드 보정 승인, 모사 검증 | guard의 7개 text read는 UTF-8, tag 출력은 ASCII `->`. non-ASCII fixture와 cp1252 기본 decoding/strict console 대조 통과. Native Windows remote matrix 결과는 push 후 별도 보고해야 한다. |
| PySide 미설치에 따른 strict mypy 실패 | provisioning 보정 승인 | quality sync에 `--extra gui`, 뒤 실행은 `--no-sync`. strict `mypy cmig` 91파일 통과, 전역 ignore/GUI 제외 없음. 이것만으로 remote matrix나 native GUI를 통과했다고 할 수 없다. |

## 이번에 새로 닫은 잔여 경계

실행 명령:

```sh
QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' PYTHONPATH=. uv run --no-sync python .run/remediation-20260925/final-review/probe_residuals.py
```

Exit 0. direct/controlled 두 경로 각각 baseline 반환 예외·정상 ledger·취소·실제 infeasible baseline, 세 실제 Host LP/FVA→writer→GUI 사례와 각 saved/JSON-only 경로, helper 8사례를 확인했다. 실행 중 기록한 소스는 변경되지 않았다. 실제 solver 결과에 예외/취소/FVA 실패를 결정적으로 주입한 경우를 자연 발생 timeout이나 mid-solve interruption으로 주장하지 않는다.

**RR1:** 네 번째 실제 optimization이 optimal로 끝난 뒤 반환 예외를 주입했다. 네 ledger 행이 유지되며 마지막은 `phase=baseline`, `solve_started=true`, `solve_executed=null`, `raw_status=solver_error`, `outcome=error`, 실제 growth policy floors와 진단을 가진다. observer가 받지 못한 값을 측정값으로 날조하지 않는다. 정상 대조는 각 경로 20 LP/20행, 실제 infeasible은 baseline/infeasible, `SearchCancelled`는 전파된다. Observer 이후 readout 예외의 raw optimal 보존은 생산 소스와 parametrized 회귀를 대조했다. 후보 실패는 순위에 들어가지 않는다.

**RR2:** acetate 수송을 막고 butyrate로 objective 5를 유지한 실제 LP에서 acetate FVA `[0,0]`, sparse point map에는 acetate 없음이 확인됐다. HostArm은 identified/0, CSV는 `ac,0,0,0,True`, live/saved/JSON-only GUI는 `0`이며 zero cross-feeding edge를 만들지 않았다. 실제 `[0,5]`는 빈 CSV/`False`/`unknown [0.0, 5.0]`, FVA 주입 실패는 objective 5를 남기고 전달점·구간을 만들지 않는다. Failed/status-free range-only는 0으로 승격하지 않는다. Shared helper는 broad/reversed/nonfinite interval이 incidental point보다 우선하며 legacy finite assertion과 namespace spelling을 보존한다.

Probe 첫 실행은 테스트용 coupling 조립체의 빈 outer warnings를 실제 orchestrator처럼 host warnings에 연결하지 않은 채 warning을 검사하여 실패했다. 원래 log는 `probe-residuals-fixture-error.log`로 보존했고, probe fixture만 고친 최종 실행이 통과했다. 이 fixture 오류를 생산 결함이나 통과 테스트로 계산하지 않는다.

## 그림, 공개 문서, 통합 경계

F2/F9를 다시 승인한 근거는 [최종 GUI/SVG 독립 인수](remediation_gui_figures_acceptance_2026-09-25.md)의 **실제 저장 파일**과 함수 동일성이다. `_write_multi_target_figure`의 `inspect.getsource` SHA-256은 `b5203c28d98a549f53b3da7423805575afd6dbb4bcc39158df6eb2c573ba220a`로 동일하며 load/polish 및 두 exporter도 동일하다. 전체 CLI 파일은 RR2 때문에 달라졌으므로 파일 전체가 동일하다고 주장하지 않는다. 기존 `artifact-sha256.json`에 기록된 57개 SVG/TIFF/PNG artifact는 이번 byte 해시 대조에서 모두 동일했다(`reused-figure-artifacts.json`).

| 최종 파일 | Qt text 최소 canvas 여백 | 확인한 수치 |
| --- | ---: | --- |
| historical mixed | 10.211531 pt | `−10/+13.358851988170386`, 총합 `3.358851988170386` 두 행 |
| historical Pareto | 10.211531 pt | 저장 display score `13.358851988170386`, report order 및 best-point 부정 캡션 |
| normalized weighted | 10.211531 pt | 저장 `−2/+4`에 weight `3/2` 한 번 적용, `−6/+8`, 합계 2 |
| 다섯 행 긴 label | 12.947531 pt | member/plot 7.104687 pt, member row 5.684646 pt, legend/plot 37.118880 pt, legend row 2.683906 pt |

기존 actual TIFF에서 만든 mixed/Pareto/long-label PNG와 Qt SVG PNG, normalized SVG PNG를 이번에도 직접 열어 보았다. 음수 bar·합계·단위·전체 caveat·행/범례 순서에 새 clipping이나 침범을 보지 못했다. 각 TIFF는 RGB/600×600 dpi/LZW이며 SVG는 native editable text다. 이 단계에서는 새 열 가지 figure 행렬을 생성하지 않았다. Historical Pareto의 old missing-target/명시적 0은 시각 호환성 fixture이고 현재 capability의 생물학적 증거가 아니다.

Cross-lane 소스와 선행 실제 publication 증거는 다음을 유지한다. Partial Pareto는 optimal point와 partial candidate를 함께 내보내고 summary/manifest는 degraded다. Capability 실패는 failed/0 ranked이며 ledger를 digest에 포함하고 존재하지 않는 plot은 artifacts에 선언하지 않는다. 명시적 `--allow-failed-run`의 exit 0은 실패 artifact 게시 허용이지 과학 성공이 아니다. GUI의 정확한 summary validator, Search 직접 loader 및 completion 함수는 이전 인수 해시와 같으며 byte integrity와 schema/과학 상태를 분리한다. Nullable Host 인터페이스의 바뀐 부분은 이번 새 LP probe로 확인했다.

문서 최종 대조: **승인**. 두 guide는 default resolution의 보통 2-target 사례에서 전체 20시도/16 sampling slice를 구별하고 optimal·infeasible과 timeout·error 카운터 및 그 밖의 outcome을 설명한다. `attempt_ledger_v2`도 ledger가 있다는 이유로 호환된다고 보지 않고 `attempt_ledger_v3`에 새 checkpoint 경로가 필요하다고 명시한다. `README.md`, `docs/USAGE.md`, `docs/USER_GUIDE.md`, `CHANGELOG.md`의 signed score/units, host null/zero/interval, 시도 ledger/checkpoint v3, GUI workflow별 적용 설정·실제 그림 종류·integrity, 설치 preset, solver prerequisites, reaction-flux/physical amount, community 비단위 거부와 MICOM 내부 adapter 고지를 확인한다. Fixed-abundance search/post-hoc sensitivity를 abundance 최적화로 부르지 않고, 없는 per-target threshold UI/Pareto scatter/Bayesian/host-coupled main fitness/cost·synergy 연구 기능을 구현됐다고 쓰지 않는다.

## fixture 보정과 최종 실행 증거

다섯 legacy test 파일의 최종 `git diff HEAD -- <5 files>`를 [독립 triage](remediation_integration_triage_2026-09-25.md)의 **10개 실패 전부**에 대조하여 승인했다. 원래 assertion을 삭제/완화하지 않았으며 생산 제약이나 golden tolerance 변경도 없다.

| 기존 실패 | 최종 fixture 처리 |
| --- | --- |
| #1–3 medium helper·경고 전파 | `_m` metabolite를 실제 m compartment로 구성한다. 성공 `−7` bound·미적용 warning·실제 search entry-point 검증을 유지했다. |
| #4 private pFBA readout | 빈 해에는 명시적 빈 community와 test-only pinned version을 제공하고 provenance label assertion을 유지했다. |
| #5–6 pFBA success/fallback | 실제 모양의 environment/member topology와 0.5 pool coefficient를 제공했다. 환경값 `3→1.5`는 `0.5×8+0.5×(−5)`에 맞춘 fixture 보정이며 golden 변경이 아니다. 호출 순서·objective 0.6·warning·diagnostic은 유지하고 수치 balance assertion을 추가했다. |
| #7 all-ok host status | 성공에만 explicit `[0,0]`/identified, 실패에는 unavailable을 제공한다. 새 objective-only ambiguous/unavailable 두 대조는 숫자 목적값의 순위를 유지하면서 degraded/null을 검증한다. |
| #8 stereochemical join | 실제 lactate spelling join을 유지하면서 butyrate unused=1에 `[0,0]` 근거를 부여했다. 그 근거를 지우면 transfer/range/unused 숫자가 없어지는 음성 대조를 추가했다. |
| #9–10 host LP·그림 success | typed `HostImpact`와 coherent availability/match/`[1.2,1.2]`를 optimal fixture에만 제공한다. objective zero의 합법적 optimal·exit 0/ok·불필요한 not-evaluable 문구 없음과 실패 경계는 그대로다. |

Sol의 전체 다섯 파일 실행은 **133 passed / 0 failed / 0 skipped**, exit 0이다. 최초 132개 실행에 unavailable 대조 1개가 추가된 최종 133개를 채택한다. 증거: `integration-fixture-correction/five-files-final.xml`, `verification.md`; 이 검토자가 중복 실행하지는 않았다.

```sh
uv run --no-sync pytest -o addopts='' -q -rs --junitxml=.run/remediation-20260925/integration-fixture-correction/five-files-final.xml tests/test_round5_domain_accuracy.py tests/test_engine_solver_guard.py tests/test_run_status_reporting.py tests/test_round10_review_fixes.py tests/test_round5_final_fixes.py
```

**최종 통합 결과: 통과.** 코디네이터가 실행한 `.run/remediation-20260925/integration-final/quality-results.json`의 7 gate는 통과했다. Ruff, harness 56/0/0, lock, version 6면 0.3.0, mypy 91파일, envelope 18 workflow 및 float normalization, license-free CI 287/0/0이다. 같은 디렉터리 `golden.log`는 MICOM 0.39.0의 Gurobi/OSQP published run hash가 일치함을 보여준다. 코디네이터의 `integration-final-r2/prior-quality-source-delta.json`는 이 quality/golden snapshot과 비교하여 위 다섯 non-CI test 파일만 달라졌음을 확인하며, 최종 tree의 Ruff도 통과했다. 이들은 해당 7 gate의 test selection 또는 생산 코드를 바꾸지 않았으므로 나머지 gate를 정당하게 재사용한다. 최종 전체 pytest 결과까지 아래와 같이 확인했다.

중간 전체 결과 `.run/remediation-20260925/integration/full-summary.json`는 **1,764 collected / 1,736 passed / 10 failed / 18 skipped**다. 첫 `integration-final/full.xml`은 fixture가 미반영된 것이 확인되어 중단한 실행이며 최종 인수가 아니다. 최초 product baseline **1,537/1/18**, 후속 harness baseline **1,565/1/18**의 기존 AGORA 실패를 새 결과와 혼합하지 않는다. 최종 전체 suite는 [integration-final-r2/full.xml](../.run/remediation-20260925/integration-final-r2/full.xml)과 `full-tests.log`, `full-summary.json`로 판정한다.

```sh
QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --no-sandbox' uv run --no-sync pytest -q -ra --junitxml=.run/remediation-20260925/integration-final-r2/full.xml
```

**Exit 0, 1,770 collected / 1,752 passed / 0 failed / 0 errors / 18 skipped, 322.590초.** JUnit 시작은 `2026-09-25T15:55:00+09:00`이다. 코디네이터는 실제 process exit 0을 확인했고, 이 검토자는 XML의 모든 testcase를 별도로 집계했다. `test_publication_benchmark.py`의 세 시험도 모두 이 전체 실행 안에서 통과했으며 별도 실행 수로 더하지 않았다. 이는 integrated smoke의 소프트웨어 증거이고 특정 GEM의 publication-validity 인증은 아니다.

최종 skip 18개의 node set은 보존된 `.run/audit-20260925/harness-full/full-tests.xml`과 정확히 같아 추가/제거가 없다. **RECON1 미제공 5개, Recon3D 미제공 13개**이며 각 node/reason은 최종 `full-summary.json`에 있다. `baseline-skips.json`과 `final-evidence-check.json`에 독립 비교를 저장했다.

| 최종 또는 정당하게 재사용한 gate | 명령/실제 selection | 결과 |
| --- | --- | --- |
| Ruff | `uv run --no-sync ruff check .`에 해당하는 final Ruff, quality JSON의 `.venv/bin/python -m ruff check .` | 통과 |
| Harness | `.venv/bin/python -m pytest -q tests/test_harness_execute.py tests/test_harness_hooks.py tests/test_harness_checks.py --junitxml=…/integration-final/harness-tests.xml` | 56 passed / 0 skipped |
| Lock | `uv lock --check` | 통과, dependency pin 불변 |
| Release | `.venv/bin/python scripts/check_release_versions.py` | 6개 surface 모두 0.3.0 |
| Strict types | `.venv/bin/python -m mypy cmig` | 91파일 통과 |
| Workflow envelope | `.venv/bin/python -c 'from cmig.cli.main import main; raise SystemExit(main())' golden verify-envelope` | 18 workflow 및 float normalization 통과 |
| CI deterministic selection | quality JSON의 `.venv/bin/python -m pytest -q` 뒤 16개 명시 파일 | 287 passed / 0 skipped |
| MICOM/version golden | `uv run --no-sync python -c 'from cmig.cli.main import main; raise SystemExit(main())' golden verify` | Gurobi/OSQP, MICOM 0.39.0 및 두 published run hash 일치 |
| 최종 전체 suite | 위 offscreen 전체 명령 | 1,752 passed / 18 기존 skips |

Quality의 정확한 argv·exit·시간·selection 전체는 [quality-results.json](../.run/remediation-20260925/integration-final/quality-results.json)에 있으며, 56 harness는 287 CI selection 및 full suite와 중복된다. 표의 수를 합산하지 않는다. Golden tolerance나 기대 과학 수치를 바꾸어 맞추지 않았다.

코디네이터 `source-start.json`/`source-end.json`의 **233개 production/test/config 파일 해시는 동일**하고 이번 최종 대조에서도 현재 파일과 다르지 않았다. 코디네이터 source-manifest SHA-256은 `8428c27bfd36d45a9fbbbe040fb1cebcee8634e66ed0aa16eb4d7ce8688226bf`다. 시작 HEAD는 그대로이며 이 보고서는 아직 작성 전인 새 commit hash를 추정하지 않는다. 이후 해당 소스가 바뀌면 영향받는 인수 경계를 다시 확인해야 한다.

최종 direct wheel과 fresh sdist→wheel을 서로 다른 checkout 외부 경로에 **실제 설치**했다. 두 경우 source 91 Python file bytes 일치·9개 preset·717개 provenance row·resource 불변을 확인했고, sdist 안의 두 guide도 최종 bytes와 일치한다. 두 wheel의 SHA-256은 모두 `43620c046112c17eee15eb547aa0aaf571b2654bdb80b1c40488c68cbe2ebe5a`다. `integration-final-r2/{installed-direct,installed-sdist-wheel}.json`의 import 경로는 각각 별도 `.../cmig-final-installed-.../site/cmig/__init__.py`, `.../cmig-final-sdist-.../site/cmig/__init__.py`이며 checkout rescue가 아니다. `build.log`는 sdist에서 wheel을 만들었음을 명시하고 `package-audit.log`는 sdist·그 wheel·direct wheel **3/3** 통과를 기록한다.

```sh
uv build --wheel --out-dir .run/remediation-20260925/integration-final-r2/dist-direct
uv build --out-dir .run/remediation-20260925/integration-final-r2/dist
uv run --no-sync python scripts/audit_distribution.py .run/remediation-20260925/integration-final-r2/dist/* .run/remediation-20260925/integration-final-r2/dist-direct/*
```

Staged whitespace 검사는 원본 MICOM source CSV의 canonical CRLF와 구현 보고서 3·4행의 Markdown hard-break 공백을 보고한다. 원본 provenance bytes와 의도된 Markdown을 보존한 예외이며 이를 제외한 staged whitespace는 통과했다. 따라서 일반 `git diff --cached --check`가 무조건 통과했다고 주장하지 않는다. 근거는 `integration-final-r2/staged-whitespace.json`이다.

실제 설치는 각 wheel에 `uv pip install --target <별도 임시 site> --no-deps <wheel>` 후 외부 작업 경로에서 수행했다. 정확한 임시 경로·실행 출력과 설치 결과는 `direct-install.log`, `sdist-wheel-install.log`, 두 `*-installed-probe.log` 및 위 JSON에 있다. 검토자가 환경이나 credentials를 설치/수정한 것이 아니라 코디네이터 실행 로그를 대조했다.

## 허용 범위와 남은 작업

로컬 실제 Gurobi license 및 tiny LP/MICOM 계산은 성공했다. **Repository Gurobi WLS secrets는 없으며 이 검토에서 공급·복사하지 않았다.** 원격 `solver-tests`는 필요한 WLS secret 미제공 시 실패하는 정책을 유지한다. 로컬 성공을 remote solver CI green으로 바꾸어 말할 수 없다. Commit/push 전 코드 인수와 push 후 remote CI 확인은 별도 작업이다.

18 baseline skip은 위에서 확인한 외부 RECON1/Recon3D 부재 경계이며 통과로 세지 않는다. Native Windows/Linux/macOS 창 관리자·HiDPI·전체 접근성, 실제 live AGORA 가용성, full human GEM/대규모 community 생물학, 장기 dt convergence, 자연 발생 solver timeout, R 전용 렌더링, publication-validity는 인증하지 않는다. Qt 검증은 macOS arm64 offscreen/PySide6 6.11.1, Matplotlib 3.10.9 및 실제 설치 Arial에서의 파일/GUI 증거다.

원명세 §4.1의 public-API-only 요구와 MICOM 0.39.0의 `global_id`/`community_id`/pool coefficient adapter 의존성 사이의 불일치는 설계·과학 검토가 승인한 제한으로 남는다. 버전/shape 검증과 golden을 유지하며 private assembly 재작성이나 source GEM 수정으로 회피하지 않았다. 비단위 community 입력은 지원됐다고 주장하지 않는다.

연속 abundance 공동 최적화, cost/size penalty, synergy/null-model objective, host-coupled main-search fitness, 새 per-target threshold UI, Bayesian strategy, interactive Pareto explorer는 **별도 미래 연구/제품 범위**다. 이번 20결함 인수의 누락 기능을 은폐하기 위해 완료 처리한 것이 아니다. Exact membership가 참여·공존·최적성을 보장하지 않고 sampled front가 연속 frontier의 완전성을 증명하지 않으며 통계 독립성 제한도 유지된다.


최종 검토 보고서는 코디네이터가 실제 commit에 포함해야 한다. 검토자는 commit/push 또는 원격 메시지를 수행하지 않았으며, 다음 남은 작업은 코디네이터의 커밋·일반 push와 이후 remote quality/package/solver CI 상태를 구분한 보고다.
