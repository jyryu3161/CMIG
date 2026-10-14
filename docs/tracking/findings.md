# 미해결 문제

## 모델 자체의 강제 흡수 경계와 배지 상한이 충돌하면 cobra 오류 문구로 실패

- 증상: 번들 `iAF987`(Geobacter)의 SBML은 `EX_fe3_e`(−67.37, −49.21), `EX_ac_e`(−8.88, −6.84)처럼 흡수를 **강제**한다. 이 대사체 행을 작은 상한으로 담은 배지(예: `gut_overlay_agora_high_fiber`의 `EX_fe3_m` 0.1)를 적용하면 `boundary.set_supply_limit`가 lower bound −0.1을 upper bound −49.21 위에 쓰려 해 cobra의 "The lower bound must be less than or equal to the upper bound (-0.1 <= -49.21)."로 그 후보가 실패한다(exact·merge 모두). 2026-10-14 측정, `iAF987`이 들어간 모든 조합 탐색 후보.
- 영향: 후보를 거부하는 것 자체는 맞다(모델이 요구하는 공급을 배지가 주지 않는다). 그러나 이유가 모델의 강제 경계와 배지 상한의 모순이라는 사실이 문구에 없고, GUI 상태 줄에도 이 cobra 문구가 "가장 흔한 원인"으로 그대로 보인다.
- 지금 못 푸는 이유: 이번 변경(pool 단위 배지 규칙·GUI 실패 사유)의 범위 밖이다. `boundary.py`의 강제 공급 처리(`forced_supply`, strict 거부)와 문구를 함께 정해야 하는 별도 과학 규칙 변경이다.
- 방향: 상한이 모델의 강제 흡수량보다 작으면 "<model>의 SBML이 <exchange> 흡수 ≥ X를 강제하지만 배지는 Y까지만 준다"로 명시적으로 거부하고 테스트로 고정.

## 원격 solver CI가 매번 실패

- 증상: quality가 통과한 `3621868` push에서 CI `solver-tests`가 "Gurobi WLS secrets are required for solver-tests."로 라이선스 설정 단계에서 실패했다(2026-09-25). 그 전 run들은 quality 실패로 이 단계에 도달하지 못했다. golden gate, 전체 pytest, 출판 smoke가 원격에서 한 번도 돌지 않았다.
- 영향: 원격 CI 녹색 표시가 과학 경로(솔버·GUI·출판)를 전혀 보증하지 않는다. 이 경로의 회귀는 로컬 라이선스 실행에서만 잡힌다.
- 지금 못 푸는 이유: 저장소 비밀값(`GRB_WLSACCESSID`, `GRB_WLSSECRET`, `GRB_LICENSEID`) 등록은 라이선스 소유자가 GitHub 설정에서 해야 한다.
- 방향: 비밀값 등록 후 재실행. 비밀값 없이 건너뛰어 통과로 만드는 방식은 금지(정책상 실패 유지).

## 출판 검증 절차가 현재 코드로 재실행되지 않음

- 증상: `docs/PUBLICATION_VALIDATION.md`의 "TO RE-RUN AT RELEASE" 항목이 경계 격리·숙주 격리·물리량 변환 수정 이후 Recon3D로 실행된 기록이 없다. `v0.3.0`은 서명 없는 annotated 태그이고 Zenodo DOI도 없다.
- 영향: 현재 버전의 숙주 결합·dFBA 결과를 출판 근거로 쓸 수 없다. `RELEASE_CHECKLIST.md`의 서명 태그 요건을 충족하지 못한다.
- 지금 못 푸는 이유: Recon3D 재다운로드, 라이선스 솔버 장시간 실행, 연구별 biomass 기준·interface map 검토, 서명 키가 필요하다.
- 방향: 다음 릴리스 절차에서 수행하고 산출물을 보관.

## MICOM pool/member 식별자 해석이 비공개 구조에 의존

- 증상: 커뮤니티 dFBA와 exchange 물리량 변환이 MICOM 0.39의 pool/member 반응 식별자와 abundance 가중 계수 구조를 직접 해석한다. 버전 확인은 있으나 문서화된 공개 API가 아니다.
- 영향: MICOM 버전을 올리면 멤버 flux 매핑·물리량이 조용히 틀릴 수 있다(과거에 member pool flux를 추측 키로 찾다 0.0이 된 결함이 있었다).
- 지금 못 푸는 이유: MICOM이 이 정보를 공개 API로 제공하지 않는다. upstream 기능 추가가 필요하다.
- 방향: MICOM 버전 변경 시 이 경로를 최우선으로 golden·dFBA 회귀와 함께 검토. 가능하면 upstream PR.

## gene-ko 탐색 hash 인자 불일치

- 증상: `gene-ko-search`의 hash 인자에서 `explicit_ids`가 `split(",")` 후 공백을 제거하지 않아 `"g1, g2"`와 `"g1,g2"`가 다른 hash가 된다. `n_evaluated`는 실제 평가 수가 아니라 시도한 행 수다.
- 영향: 같은 KO 목록의 run이 다른 `run_hash`를 받아 캐시·비교가 어긋나고, 평가 수 보고가 과대할 수 있다.
- 지금 못 푸는 이유: 수정하면 `gene_ko_search` workflow hash가 이동하는 계약 변경이라 envelope 재승인과 CHANGELOG 기록을 묶은 별도 변경이 필요하다.
- 방향: 공백 제거·중복 제거 후 정렬, `n_evaluated`를 실제 평가 수로. 한 번의 계약 변경으로 묶는다.

## 로컬에 등록되지 않은 Human-GEM 파일

- 증상: `fixtures/Human-GEM-v1.19.0.xml`(약 43 MB, gitignore)이 이 checkout에 있다. checksum·출처 기록이 없고 어떤 코드 경로도 이 이름을 쓰지 않는다.
- 영향: 재현할 수 없는 바이트에 무심코 의존하는 run이 생길 수 있다.
- 지금 못 푸는 이유: 개인 run이나 원고가 이 경로를 쓰는지 사용자가 확인한 뒤 지워야 한다.
- 방향: 확인 후 삭제. Human-GEM이 정식 숙주가 되면 Recon3D처럼 `data/gems/GEM_SOURCES.json`·다운로드 스크립트·resolver·테스트로 등록.

## 명세서 문구가 수락된 결정과 다름

- 증상: `CMIG_명세서_v3.0.md` §2·§4.2·§16은 OSQP 기본 성장 솔버, `highs` golden, hybrid 변형을, §3·§11은 원격 백엔드·Docker·Escher·한/영 토글을 여전히 적고 있다.
- 영향: 명세서만 읽은 작업자가 폐기된 경로(HiGHS golden, hybrid, 원격 실행, 한국어화)를 다시 구현할 수 있다.
- 지금 못 푸는 이유: 명세서 개정은 저자의 결정 사항이다.
- 방향: 차기 명세 개정 때 수락된 결정(솔버 역할, golden 2종, 숙주 구성 B, 범위 조정)으로 해당 절을 고친다.

## 네이티브 GUI 미검증

- 증상: GUI 검증은 offscreen Qt 렌더와 기능 테스트뿐이다. 2026-09-25 감사에서 기본 창 최소 폭이 2045px(Pareto 경고 후 2771px)로 강제 확대된 것이 관찰됐고, 이후 수정은 offscreen에서만 확인됐다. QtWebEngine 그래프의 GPU·초기 viewport 동작도 네이티브에서 재현되지 않았다.
- 영향: macOS/Windows 실제 화면, HiDPI, 다중 모니터, 키보드 접근성 문제가 배포 후에야 드러날 수 있다.
- 2026-10-14(GUI 2단계): REA로 macOS 실제 창을 어두운 모드에서 1500×950·1280×800으로 캡처해 Combination Search, Community Solve, Host–Microbe, 모델 브라우저, 검색 결과 목록, 다시 연 실행 결과를 확인했다. 이때 offscreen에서 보이지 않던 문제(상태 표시줄의 빈 단추 상자)를 하나 찾아 고쳤다. 밝은 모드 실제 창, Windows, HiDPI·다중 모니터, 사람이 마우스·키보드로 하는 조작은 아직 확인하지 않았다.
- 지금 못 푸는 이유: 실제 데스크톱에서 사람이 확인해야 한다.
- 방향: 릴리스 전 1280×800·1500×950 창에서 Search/Host/Dynamics/Pareto를 수동 확인.

## legacy `solve` hash가 배지 적용 모드를 구분하지 못함

- 증상: `cmig solve --medium X`와 `cmig solve --medium X --exact-medium`은 결과가 다른데 같은 11구성요소 `run_hash`를 받는다. solve 경로의 배지 checksum은 uptake 값만 담고, 모드는 hash 밖 provenance(`medium_application_mode`)에만 기록된다. workflow manifest 경로는 모드를 hash에 넣는다.
- 영향: `run_hash`를 캐시 키나 동일성 판단으로 쓰는 소비자(sweep 캐시 포함)가 merge run과 exact run을 같은 run으로 취급할 수 있다.
- 지금 못 푸는 이유: solve hash는 고정 11구성요소 계약이고 golden hash가 발표돼 있다. 모드를 넣으려면 구성요소 정의를 바꾸는 계약 변경이 필요하다.
- 방향: 배지 checksum 입력에 모드를 포함하되 merge 기본값은 기존 직렬화를 유지하는 방식(고정 golden 보존)을 설계해 한 번의 계약 변경으로 처리. 그 전까지는 solve run을 비교할 때 기록된 모드를 반드시 함께 확인.

## macOS 로컬 전체 pytest가 모두 통과한 뒤 rc=139로 끝남

- 증상: `QT_QPA_PLATFORM=offscreen uv run --no-sync pytest`를 전체로 돌리면 모든 테스트가 통과하고 요약 줄까지 출력된 뒤, 인터프리터 종료 중 "Release of profile requested but WebEnginePage still not deleted"를 남기고 segfault(rc=139)로 끝난다. `9a407bb`에서도 같다(2026-09-29, 1762 passed, rc=139).
- 영향: 종료 코드만 보는 스크립트나 hook은 통과한 실행을 실패로 본다. 반대로 rc=139를 "원래 그렇다"고 넘기면 진짜 crash를 놓칠 수 있다.
- 지금 못 푸는 이유: QtWebEngine 그래프 화면(`graph_view.py`) 객체가 Python 종료 시점까지 남아 있는 문제로 보이며, 원인 객체를 특정하려면 macOS에서 테스트 파일 단위 이분 탐색이 필요하다. 새 GUI 테스트 파일에 autouse `_deterministic_qt_teardown` fixture를 두면 그 파일 단독 실행에서는 사라진다.
- 방향: 판정은 요약 줄과 `--junitxml`의 failures/errors로 한다. 전체 실행에서 WebEngine 객체를 명시적으로 정리하는 공용 fixture(`conftest.py`)를 검토한다.

## `agora2-fetch`를 같은 `--out`에 반복하면 이전 출처 기록이 사라짐

- 증상: `cmig agora2-fetch`는 호출마다 `--out`의 `agora2_manifest.json`을 그 호출이 고른 균주만으로 다시 쓴다. 이미 받은 균주는 같은 호출에서 다시 고른 경우에만 기록에 남고(`already fetched, skipping`), 이전 호출에서 받은 다른 균주의 파일은 폴더에 남아 있어도 manifest 항목(원 URL, 인코딩 수리 횟수, 시각)이 빠진다.
- 영향: 한 폴더에 여러 번 나눠 받으면 일부 모델 파일이 출처 기록 없이 남는다. 그 폴더를 `--model-dir`로 쓰는 분석의 재현성·인용 기록이 불완전해진다.
- 지금 못 푸는 이유: manifest를 합치도록 바꾸면 CLI 산출물 계약(`agora2_manifest.json`의 내용과 `n_models`)이 달라지고, GUI 작업 공간 1단계의 범위(CLI 옵션·산출물 불변)를 벗어난다.
- 방향: GUI는 다운로드마다 `models/agora2/<YYYYMMDD-HHMMSS>/` 새 폴더를 써서 각 호출의 manifest를 보존한다. CLI는 기존 manifest를 읽어 `models`를 균주 id 기준으로 합쳐 쓰는 방식을 별도 변경으로 검토하고, 그 전까지 같은 `--out`에 나눠 받지 않는 것을 사용 설명서에 안내한다.

## 접근성 '누름'(AXPress)으로 사이드바 항목이 선택되지 않음

- 증상: AXPress(접근성 '누름')로 사이드바 QTreeWidget 항목이 선택되지 않음 — REA 자동 조작에서 확인(2026-10-13). 마우스·키보드는 정상. Qt 항목 뷰의 접근성 동작이라 이번 범위에서 고치지 않음. 표의 행(QTableWidget)도 AXPress로 선택되지 않는다.
- 영향: VoiceOver 같은 보조 기술이나 접근성 API로 화면을 옮기는 자동화가 사이드바를 쓸 수 없다. REA 화면 확인은 실행 스크립트가 읽는 명령 파일로 `sidebar.select(group, key)`를 불러 화면을 옮겼다.
- 지금 못 푸는 이유: Qt 항목 뷰가 macOS 접근성에 내보내는 동작(QAccessible) 문제라, 고치려면 사이드바를 접근성 동작을 직접 구현한 위젯으로 바꾸거나 Qt 쪽 수정이 필요하다. GUI 2단계 범위 밖이다.
- 방향: 접근성 점검을 따로 계획할 때 사이드바·표의 QAccessible 동작을 확인하고, 필요하면 항목에 press 동작을 붙인다.

## REA 실제 창 캡처의 제약

- 증상(2026-10-14): REA(`rea-agents@6.4.0`)는 `.app` 묶음(Info.plist + python을 `exec`하는 셸 스크립트)을 `open`으로 띄운 Python/Qt 창만 캡처할 수 있다(실행 시각이 있어야 함). 캡처는 그 순간의 시스템 모양(이번에는 어두운 모드)으로만 되며, 조작은 AXPress·스크롤·값 입력·기다림뿐이다. `open`으로 띄운 창은 앞으로 나와 키보드 포커스를 가져가므로, 그동안 다른 창에 친 글자가 사이드바의 입력 찾기로 들어갈 수 있다(캡처 한 장이 의도하지 않은 화면으로 바뀐 것을 보고 다시 찍었다).
- 영향: 밝은 모드와 어두운 모드를 한 번에 짝지어 실제 창으로 보려면 시스템 모양을 바꿔야 한다. 이번에는 밝은 모드를 offscreen에서 밝은 팔레트를 강제해 확인했다.
- 지금 못 푸는 이유: 시스템 모양 변경은 사용자 설정이라 사용자 동의 없이 바꾸지 않는다. REA는 창 밖 입력을 막지 못한다.
- 방향: 사용자가 밝은 모드로 바꾼 상태에서 같은 스크립트로 다시 캡처한다. 캡처하는 동안 다른 창에 입력하지 않는다.

## 어두운 모드의 계산값 강조색 대비가 낮음

- 증상: macOS 어두운 모드에서 Qt가 주는 강조색(`QPalette.Accent`, 이번 기기에서 `#0A60FF`)으로 칠한 계산값은 표 배경(약 `#1E1E1E`) 위에서 대비가 약 3.3:1이다. 읽을 수는 있으나 작은 글자에 권하는 4.5:1보다 낮다. 밝은 모드(흰 배경)는 약 5:1이다.
- 영향: 어두운 모드에서 계산값이 일반 글자보다 흐리게 보인다.
- 지금 못 푸는 이유: 설계는 "시스템 강조색을 따른다"이고, 색을 밝게 바꾸는 것은 설계 결정이다. 시스템 모양을 바꾼 뒤 이미 칠한 칸은 다시 칠하지 않는다(다시 열면 새 색).
- 방향: 3단계 결과 화면 통일 때 어두운 모드에서 강조색을 밝게 하거나 굵기로 구분할지 정한다.
