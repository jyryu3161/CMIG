# 시스템 구성

CMIG는 한 개의 Python 패키지(`cmig`)로 배포되는 데스크톱 GUI + CLI 도구다. 서버, 데이터베이스 서버, 원격 실행 경로는 없다. 모든 계산은 사용자의 기계에서 같은 프로세스(또는 그 프로세스가 띄운 spawn 워커) 안에서 돈다. 커뮤니티 FBA 자체는 MICOM(`micom==0.39.0`)이 풀고, CMIG는 그 앞뒤의 부가가치 계층 — 입력 검증·namespace 차단·부호 정규화·tidy 산출·탐색·숙주 결합·동역학·재현성 기록 — 을 소유한다.

## 구성요소와 의존 방향

```
cmig.gui ──(in-process 호출)──▶ cmig.cli.main.main(argv) ──▶ cmig.core ──▶ MICOM / cobra / optlang ──▶ Gurobi | OSQP
   │                                  │        │                 ▲
   │                                  │        └──▶ cmig.io ─────┘ (원자적 게시·모델 로딩·manifest 보조)
   └──▶ cmig.service (JobRunner, SearchService, EngineService)
                                      └──▶ cmig.render ──(subprocess)──▶ Rscript + cmig/render_r/*.R   (없으면 matplotlib)
```

| 구성요소 | 역할 | 의존 방향 |
|---|---|---|
| `cmig/core` | 과학 알고리즘과 엔진·솔버 어댑터. MICOM 호출의 단일 진입점(`engine.py`), 부호 변환 단일 진입점(`sign.py`), 경계 격리(`boundary.py`), 탐색·숙주·dFBA·통계·manifest/hash | `io`(원자적 쓰기·모델 로딩), `service.search_service`(탐색 워커, 함수 내부 지연 import), `render.figure_style`(상호작용 그림 스타일)을 참조한다. `gui`·`cli`는 참조하지 않는다 |
| `cmig/service` | 실행 조정. `JobRunner`(스레드 기반 비차단 실행·협조적 취소), `SearchService`(CLI·GUI 공통 탐색 요청·preflight·spawn 프로세스 워커), `EngineService`(solve facade), `FileSystemStore`(영속 run 저장소 — 현재 어떤 경로에도 연결되지 않음) | `core`, `io` |
| `cmig/io` | 입력·출력 경계. 모델 import(SBML/JSON/MAT), 정규화 모델 캐시, AGORA2 fetcher(유일한 네트워크 경로), 원자적 파일 게시, 디렉터리 트랜잭션, solve 산출 | `core` |
| `cmig/cli` | `cmig` 명령 전체(`main.py` 단일 파일, 약 1.1만 줄). 인자 해석 → core 호출 → 산출·manifest 게시 → 종료 코드 결정. GUI 워크플로 지도(`GUI_CLI_WORKFLOWS`)와 `inspect-run` 판독기도 여기 있다 | `core`, `io`, `service`, `render` |
| `cmig/gui` | PySide6 데스크톱 앱. 분석 버튼은 CLI argv를 조립해 `JobRunner` 스레드에서 `cmig.cli.main.main(argv)`를 **같은 프로세스 안에서** 실행하고, 결과는 CLI가 쓴 run 디렉터리를 다시 읽어 보여준다. 그래프 뷰는 QtWebEngine + Cytoscape.js | `service`, `cli`, `core`, `io` |
| `cmig/render`, `cmig/render_r` | 출판 그림. R은 별도 프로세스로만 실행(GPL 격리), 버전은 `renv.lock`, 라이브러리는 프로젝트 로컬 `.Rlib`. 단일 profile 그림은 R 부재 시 matplotlib로 대체되지만 다중 패널(network/heatmap/chord)은 R 전용이며 R이 없으면 명시적 오류 | `io`, `core` |
| `scripts/` | 배포 감사, 버전 정합 검사, 인간 GEM 다운로드·검증, 장내 배지 preset 빌드, 탐색 벤치마크, 단계 실행기(`execute.py`)와 검사 카탈로그(`harness_checks.py`) | 패키지 외부. 실행기·검사·hook은 sdist에서 제외된다 |

## 대표 흐름: `cmig search` (모델 풀 조합 탐색)

1. **입력** — CLI가 `--model-dir` 또는 taxonomy CSV, `--target`, 크기 범위, 전략, 배지, 성장 하한을 받아 `SearchRequest`로 만든다. GUI Search 탭도 같은 요청 타입을 만든다.
2. **preflight** — `SearchService`가 모델 파일을 정규화 캐시(`io.model_cache`, 원본 불변)로 준비하고, 솔버가 실제 사용 가능한지 확인한다. taxonomy id 중복·빈 값, 유한 양수가 아닌 abundance는 solve 전에 거부된다.
3. **후보 생성** — `auto`는 후보 수 ≤ `exhaustive_max`(기본 100)이면 exhaustive, 넘으면 GA로 바뀐다. random·GA는 seed로 결정적이다.
4. **평가** — 각 후보를 spawn 프로세스 워커에서 MICOM community로 조립한다. 요청한 멤버와 MICOM이 실제 유지한 멤버가 다르면 거부된다. 먼저 커뮤니티 최대 성장 μ\*를 구하고, μ\* ≤ 1e-6이면 `non_viable`로 격리한다. 그렇지 않으면 `μ_community ≥ max(f·μ*, 절대 하한)`과 선택적 멤버 성장 하한 아래에서 target exchange(`EX_<target>_m`)를 LP로 최적화한다(Gurobi 전용).
5. **기록** — 평가마다 strict-JSON checkpoint와 평가 ledger를 남긴다. 취소는 후보/배치 경계에서만 적용되고, 재개는 요청 identity가 같을 때만 허용된다.
6. **게시** — 결과 CSV/JSON, 그림, workflow manifest(`run_hash`, `result_digest`)를 staging 디렉터리에 만든 뒤 잠금·rollback이 있는 디렉터리 트랜잭션으로 `--out`에 게시한다.
7. **종료 코드** — 과학적 성공 0, 입력 오류 2, 산출은 썼지만 과학적 실패 3. GUI는 같은 run 디렉터리를 읽어 과학적 결과와 산출물 무결성을 따로 표시한다.

## 대표 흐름: `cmig solve` (단일 커뮤니티 solve)

taxonomy + 배지 → namespace gate(미해결 high-confidence 매핑이 있으면 MICOM 호출 전에 차단) → `engine.py`가 `cooperative_tradeoff(fraction=f, fluxes=True, pfba=True)` 호출 → `interactions.py`가 flux를 `sign.py` 단일 진입점으로 (크기, uptake/secretion)으로 바꿔 tidy `nodes/edges/profile` Parquet 작성 → 11구성요소 `run_hash`를 담은 legacy solve manifest 게시. 이 경로의 manifest에는 `result_digest`가 없다.

## 숙주-미생물 결합 (구성 B)

MICOM 0.39의 `Community`에는 host 인자가 없으므로 CMIG가 2단계로 푼다: 미생물 community solve → 환경 분비량을 lumen에서 쓸 수 있는 양으로 변환 → cobra 숙주 모델을 lumen uptake 한계와 viability 제약(유지 ATP 등 하한) 아래에서 별도로 solve → 흡수·전달량 분해. 숙주는 community 성장 목적함수에 들어가지 않는다. lumen(미생물 공유)과 blood(숙주 전용) 두 경계면이 있고, 숙주-미생물 대사체 대응은 검토된 interface map(`cmig host-map`이 초안 생성)을 통해서만 연결된다.

## 경계를 넘는 것과 넘지 않는 것

- **네트워크**: `agora2-list`/`agora2-fetch`만 외부로 나간다(VMH 게시 서버의 허용 경로). 다른 모든 명령은 오프라인이다. `scripts/download_human_gems.py`는 사용자가 직접 실행할 때만 BiGG에서 Recon3D/RECON1을 받는다.
- **파일**: 결과는 사용자가 지정한 `--out` 아래에 게시된다. 예외: `agora2-list`/`agora2-fetch`에 `--catalogue`도 `--out`도 없으면 카탈로그 캐시를 패키지 상위의 `data/agora2/`(소스 checkout에서는 저장소 안이며 gitignore됨)에 쓴다. 사용자 원본 GEM은 절대 수정하지 않고, 형식 변환은 폐기 가능한 캐시 사본에서 한다.
- **프로세스**: R은 subprocess, 탐색 평가는 spawn 워커 프로세스, GUI 분석은 같은 프로세스의 스레드다.
- **Qt**: `core`·`service`·`io`는 PySide6를 import하지 않는다. 선택 의존성(엔진·GUI·통계·렌더)은 모두 사용 시점에 지연 import되어 `pyarrow`만 있는 설치에서도 패키지가 import된다.

## 외부 의존

| 의존 | 위치 | 비고 |
|---|---|---|
| MICOM 0.39.0 (정확 고정) | `core/engine.py` 및 community 경로 | 커뮤니티 조립·cooperative tradeoff. pool/member 식별자 해석은 버전 확인이 붙은 비공개 결합 |
| cobra / optlang | 단일 모델·숙주·dFBA·import | 솔버 어댑터는 optlang 인터페이스 |
| Gurobi 12 (라이선스 필요) | full-flux 기준 경로, 탐색·숙주·community FVA·community dFBA 전용 | CI에서는 WLS 비밀값 |
| OSQP | community solve의 무라이선스 경로 | QP-only 근사로만 표기 |
| R 4.3.2 + renv.lock | 출판 그림 | 선택 |
| PySide6 + QtWebEngine | GUI | 선택 |
| scipy / statsmodels / scikit-learn / umap-learn | 통계 | 선택 |
| VMH 파일 서버 | AGORA2 fetch | 유일한 런타임 네트워크 의존 |
