# 미해결 문제

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
- 지금 못 푸는 이유: 실제 데스크톱에서 사람이 확인해야 한다.
- 방향: 릴리스 전 1280×800·1500×950 창에서 Search/Host/Dynamics/Pareto를 수동 확인.

## legacy `solve` hash가 배지 적용 모드를 구분하지 못함

- 증상: `cmig solve --medium X`와 `cmig solve --medium X --exact-medium`은 결과가 다른데 같은 11구성요소 `run_hash`를 받는다. solve 경로의 배지 checksum은 uptake 값만 담고, 모드는 hash 밖 provenance(`medium_application_mode`)에만 기록된다. workflow manifest 경로는 모드를 hash에 넣는다.
- 영향: `run_hash`를 캐시 키나 동일성 판단으로 쓰는 소비자(sweep 캐시 포함)가 merge run과 exact run을 같은 run으로 취급할 수 있다.
- 지금 못 푸는 이유: solve hash는 고정 11구성요소 계약이고 golden hash가 발표돼 있다. 모드를 넣으려면 구성요소 정의를 바꾸는 계약 변경이 필요하다.
- 방향: 배지 checksum 입력에 모드를 포함하되 merge 기본값은 기존 직렬화를 유지하는 방식(고정 golden 보존)을 설계해 한 번의 계약 변경으로 처리. 그 전까지는 solve run을 비교할 때 기록된 모드를 반드시 함께 확인.
