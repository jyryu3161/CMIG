# 운영

## 사전 요구

- Python 3.10, 3.11, 3.12 중 하나와 `uv`.
- 전체 workflow: Gurobi 12.x와 유효한 라이선스. 라이선스 없이 OSQP로 돌릴 수 있는 명령은 `solve`, `solve-fixture`, `single`, `dfba`, `dfba-sensitivity`, `sandbox-fixture`뿐이며(커뮤니티 결과는 QP-only 근사), 솔버를 쓰는 나머지 명령(탐색, pair, minimal-medium, medium-gap, strain-growth, abundance-impact, gene-ko-search, 숙주, community dFBA, model-quality, publication-benchmark)은 Gurobi가 필요하다.
- GUI: Qt가 동작하는 환경(헤드리스 서버는 `QT_QPA_PLATFORM=offscreen`).
- 출판 그림(선택): R 4.3.2. 없으면 단일 그림은 matplotlib로 대체되고 다중 패널 그림은 오류로 끝난다.

## 초기 설정

```bash
git clone https://github.com/jyryu3161/CMIG.git
cd CMIG
uv sync --extra engine --extra gui --extra render --extra stats --group dev   # 1
uv run --no-sync cmig version                                                  # 2
uv run --no-sync cmig solvers                                                  # 3
```

1. 전체 개발 환경. 헤드리스 분석 서버는 `--extra engine --extra render`만으로 충분하다. `engine` 없이 동기화하면 `import cmig`와 순수 로직만 되고 분석 명령은 모두 실패한다.
2. 이 checkout의 환경이 잡혔는지 확인한다. worktree나 다른 디렉터리에서 `uv run`하면 다른 프로젝트 환경이 잡히므로 반드시 이 저장소 루트에서 실행한다.
3. 솔버별 사용 가능 여부(패키지와 COBRA 어댑터가 모두 있을 때만 available)를 보여 준다. Gurobi 라이선스는 여기서 확인되지 않는다. `uv run --no-sync cmig solve-fixture --solver gurobi --out .run/license-check` 같은 작은 solve로 확인한다.

R 그림 환경(선택, 3 이후):

```bash
Rscript -e 'if (!requireNamespace("renv", quietly=TRUE)) install.packages("renv", repos="https://cloud.r-project.org"); renv::restore(lockfile="cmig/render_r/renv.lock", library=".Rlib", prompt=FALSE)'
```

글꼴·PNG·TIFF·컴파일용 OS 라이브러리는 별도로 설치해야 한다. `.Rlib`는 gitignore된 프로젝트 로컬 라이브러리다.

숙주 모델(선택, 숙주 workflow와 `tests/test_recon3d_host.py`에 필요):

```bash
uv run --no-sync python scripts/download_human_gems.py                    # 받은 뒤 checksum 검증
uv run --no-sync python scripts/download_human_gems.py --verify --counts   # 바이트와 반응 수 재검증
```

## 실행

```bash
uv run --no-sync cmig gui                      # GUI (cmig-gui와 같음)
uv run --no-sync cmig workflows --format text  # 34개 분석 목록
uv run --no-sync cmig <command> --help         # 플래그의 권위 있는 목록
uv run --no-sync cmig inspect-run --run-dir <run> --format json
```

결과 디렉터리는 `--out`으로 지정하며, 로컬 실험 결과는 gitignore된 `runs/` 또는 `.run/` 아래에 둔다.

## 검증

```bash
uv run --no-sync python scripts/harness_checks.py --tier smoke     # 75초: Ruff + 실행기 회귀
uv run --no-sync python scripts/harness_checks.py --tier quality   # 900초: + lock, 버전, mypy, envelope, CI 무라이선스 테스트
uv run --no-sync python scripts/harness_checks.py --tier solver    # 1800초: golden + engine/탐색/service 테스트. Gurobi와 추적 GEM 필요
uv run --no-sync python scripts/harness_checks.py --tier gui       # 1800초: offscreen Qt 회귀. 시각 사용성 승인이 아님
uv run --no-sync python scripts/harness_checks.py --tier full      # 2700초: 전체 pytest + 출판 smoke. 모든 extra·fixture·라이선스
```

- `cmig golden verify`는 고정 solve hash를 확인하고, `cmig golden verify-envelope`는 workflow manifest 직렬화 drift를 확인한다. 환경(MICOM·솔버 버전)이 바뀌면 둘 다 돌린다.
- 인간 GEM이 없으면 관련 테스트 18개가 skip된다. 이것은 부분 커버리지로 보고한다.

## CI

`.github/workflows/ci.yml`, `main` push·PR·수동 실행:

1. `quality` — Ubuntu py3.10/3.12, macOS py3.12, Windows py3.12. lock 확인 → 전체 extra 동기화 → 버전 정합 → Ruff → strict mypy → envelope → 무라이선스 결정적 테스트 목록.
2. `package` — `uv build` → 배포물 허용 목록 감사.
3. `solver-tests` — 원 저장소의 push 또는 같은 저장소 PR에서만. WLS 비밀값으로 라이선스 파일 생성(없으면 실패) → `cmig golden verify` → offscreen 전체 pytest → 출판 벤치마크 smoke.

## 단계 실행기

```bash
uv sync --extra engine --extra render --extra stats          # 한 번
mkdir -p phases/<name>
cp phases/templates/phase-index.json phases/<name>/index.json # step0.md, step1.md… 는 step.md 템플릿으로
uv run --no-sync python scripts/execute.py <name> --dry-run   # 역할·모델·검사·범위·제한 시간 확인. 아무것도 바꾸지 않음
uv run --no-sync python scripts/execute.py <name>             # 실행
uv run --no-sync python scripts/execute.py <name> --resume    # 호환 상태에서 남은 step만
```

- 상태와 로그는 `.run/harness/<phase>/`(gitignore). 원시 모델 출력이 들어 있을 수 있으니 로컬에만 둔다.
- 중단 후에는 `state.json`과 lock의 소유 프로세스를 먼저 진단한다. lock 삭제나 상태 파일 수동 편집으로 복구하지 않는다. `running`·`error`·`blocked`·`cancelled` 상태는 완료가 아니다.
- `--resume`은 상태 스키마, 단계 정의, 검사 코드, HEAD, 브랜치, index, 보호된 초기 파일, 입력, 완료된 출력이 모두 같을 때만 허용된다.
- 기본은 현재 브랜치·index·무관한 편집을 그대로 두고 커밋·푸시하지 않는다. `--branch <new>`는 깨끗한 checkout과 새 이름이 필요하고, `--commit`은 최종 review 통과 후 검증된 소유 경로만 stage한다. 푸시 옵션은 없다.
- 실행기 안에서 실행기를 다시 띄울 수 없다(`CMIG_HARNESS_DEPTH`).

## 환경 변수

| 변수 | 역할 | 범위 |
|---|---|---|
| `CMIG_RECON3D_PATH`, `CMIG_RECON1_PATH` | 인간 GEM 파일의 명시 경로. 탐색 순서 1순위 | 숙주 workflow·테스트 |
| `CMIG_GEM_DIR` | 공유 읽기 전용 GEM 디렉터리(`<id>.xml`). 2순위 | 같음. 그다음 `data/gems/`, `fixtures/`, `./` 순 |
| `QT_QPA_PLATFORM=offscreen` | 화면 없이 Qt 실행 | GUI 테스트·CI |
| `GRB_LICENSE_FILE` | Gurobi 라이선스 파일 위치 | CI solver 작업에서 WLS 비밀값으로 만든 파일을 가리킴 |
| `GITHUB_REF_NAME` | 태그 이름. `vX.Y.Z`면 버전 검사가 릴리스 조건까지 요구 | `check_release_versions.py` |
| `CMIG_STOP_HOOK_ACTIVE`, `CMIG_HARNESS_DEPTH` | hook 재진입·중첩 실행기 방지 | 내부용. 직접 설정하지 않음 |

## 배지 preset 재생성

```bash
python -m scripts.build_gut_media            # medium_presets/gut_overlay_*.csv 다시 쓰기 (오프라인)
python -m scripts.build_gut_media --check    # 배포된 preset이 오래됐으면 실패
```

다시 쓴 뒤 `medium_presets/`를 `cmig/resources/medium_presets/`에 바이트 그대로 복사한다.

## 릴리스

1. CHANGELOG 릴리스 절 확정, 버전 표면 6곳 정렬, `uv lock`.
2. `uv lock --check` → `uv sync --all-extras --group dev`.
3. 무라이선스 게이트(Ruff, mypy, envelope, 결정적 테스트).
4. `uv build` → `scripts/audit_distribution.py dist/*`.
5. 라이선스 환경에서 `cmig golden verify` → offscreen 전체 pytest → `tests/test_publication_benchmark.py`.
6. `docs/PUBLICATION_VALIDATION.md`의 모든 재실행 항목을 수행하고 명령 로그·종료 코드·검토한 interface map·벤치마크 디렉터리·dFBA 감사·manifest·`run_hash`·`result_digest`를 보관한다.
7. 깨끗한 환경에 wheel을 설치해 CLI smoke를 반복하고, 배포물에 외부 GEM·`.run`·자격증명·`.Rlib`·리뷰 노트가 없는지 확인한다.
8. 서명된 annotated 태그 `vX.Y.Z`, GitHub 릴리스 노트.
9. wheel·sdist 업로드, Zenodo 보관. DOI는 발급된 뒤에만 `CITATION.cff`에 넣는다.
