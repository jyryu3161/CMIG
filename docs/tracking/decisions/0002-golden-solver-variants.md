# 0002. golden과 솔버 역할: Gurobi는 full-flux 기준, OSQP는 QP-only 근사, HiGHS는 선택 불가

- 상태: 수락 (2026-06-01 결정, 같은 날 개정, 2026-06-02 개정, 2026-09-25 HiGHS 선택 제거 반영)
- 대체한 명세 문구: 명세 §2·§4.2·§16의 `highs` golden, `osqp_growth_highs_flux` hybrid, "OSQP 기본 성장 솔버"

## 맥락

명세는 solver별 golden으로 `gurobi` / `highs` / `osqp_growth_highs_flux`를 요구했다. 그러나 MICOM community solve는 cooperative tradeoff에 QP가 필요하고 HiGHS의 QP는 실험 단계라 순수 HiGHS community golden을 만들 수 없었다. hybrid 변형은 실제 HiGHS LP 재계산을 하지 않아 OSQP와 같은 계산이었는데 이름만 full-flux처럼 보였다. 또한 `highspy` 설치만으로 HiGHS가 "사용 가능"으로 보였지만 COBRA 어댑터가 없어 실제 solve는 실패했다.

## 결정

- golden 변형은 `gurobi`(full-flux, 기준 경로)와 `osqp`(`growth_solver=osqp`, `flux_solver=null`, `flux_report_status=qp_only_approximate`) 두 가지다.
- hybrid 이름은 폐기한다. HiGHS는 어떤 명령의 `--solver`로도 고를 수 없다.
- OSQP를 받는 명령은 `solve`, `solve-fixture`, `single`, `dfba`, `dfba-sensitivity`, `sandbox-fixture`뿐이다. 멤버 flux 전체나 MILP가 필요한 나머지 경로(조합 탐색, pair, minimal-medium, medium-gap, 숙주 결합, community FVA, community dFBA, model-quality, publication-benchmark 등)는 Gurobi만 받는다.
- 솔버 가용성 보고는 패키지 설치와 COBRA/optlang 어댑터를 따로 확인한다.

## 대안

- 명세대로 `highs` golden 유지: 만들 수 없으므로 제외.
- hybrid 유지: 계산이 OSQP와 같은데 이름이 full-flux를 암시해 오해를 부르므로 제외.
- OSQP-성장 → Gurobi-LP 재계산 변형: 필요하면 별도 실험 변형으로 추가할 수 있으나 현재 구현하지 않음.

## 결과

- 라이선스 없는 사용자는 OSQP 근사 community solve만 할 수 있고 탐색·숙주·동역학 커뮤니티 경로는 쓸 수 없다.
- 원격 CI에서 golden·전체 테스트를 돌리려면 Gurobi WLS 비밀값이 필수다.
- OSQP 결과를 full-flux로 표기하는 모든 코드·문서는 결함이다.
- 명세서의 해당 문구는 개정되지 않은 상태로 남아 있다.
