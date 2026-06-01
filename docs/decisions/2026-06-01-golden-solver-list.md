# Decision: golden solver 목록 — 명세 `highs` vs 구현 `osqp`

- 일자: 2026-06-01
- 상태: **Accepted**
- 범위: `cmig/golden_fixture.py` `SOLVER_VARIANTS`, `fixtures/community_3_member/expected/`
- 관련: 외부 리뷰 R2 (`REVIEW/CMIG_v3_implementation_review.md` §R2), 명세 `CMIG_명세서_v3.0.md` §16

## 맥락
명세 §16은 solver별 golden을 **`gurobi` / `highs` / `osqp_growth_highs_flux`** 3종으로 요구한다.
그러나 구현은 **`gurobi` / `osqp` / `osqp_growth_highs_flux`** 3종이다 (`pure-highs` 제외, `osqp` 추가).

## 근거
- **MICOM community solve는 pure-HiGHS(QP) 단독 변형을 지원하지 않는다** (SolverNotFound). MICOM의
  community problem은 cooperative_tradeoff에서 QP를 요구하며, HiGHS의 QP는 experimental(§2·A6)이다.
- 따라서 결정적 community golden을 만들 수 있는 무라이선스 QP solver는 **OSQP**다. pure-`highs`
  golden은 생성 불가하여 `osqp`로 대체했다 (Do/2b, OD-12·OD-50 결정).

## 결정
1. **baseline golden 변형 = `gurobi` / `osqp` / `osqp_growth_highs_flux`** (구현 현행 유지, 공식화).
2. 명세 §16의 `highs`는 **community golden 대상에서 제외**한다(community pure-HiGHS QP 미지원).
   HiGHS는 LP/MILP capability(§2 matrix)로만 존재한다.
3. `osqp_growth_highs_flux`는 **현재 실 HiGHS LP 재계산 미수행**(C9 참조) — golden은 OSQP-QP flux를
   저장하며 `flux_report_status='qp_only_approximate'` + diagnostic `metadata_only_hybrid`로 표기.
   실 LP 재계산 구현 시 본 결정과 golden을 재검토한다.

## 영향
- 명세 §16과 구현/CI 기준의 불일치를 본 로그로 해소(거버넌스). 명세 차기 개정 시 §16 golden 목록을
  본 결정으로 정정 권고.
- `cmig golden verify`(SC-5)는 golden 변형 기준으로 동작.

## 개정 (2026-06-01, cmig-analysis-completion F1) — Superseded

- 사용자 제약 "HiGHS 제거 · gurobi-only"에 따라 **`osqp_growth_highs_flux`(hybrid)를 폐기**한다.
- **golden 변형 = `gurobi` / `osqp` 2종**(hybrid 제거). full-flux 는 gurobi 전용(canonical),
  osqp 는 qp_only_approximate(무라이선스 정직 경로).
- 근거: hybrid 는 실 HiGHS LP 재계산을 하지 않아 osqp 와 동일 계산이었고(C9), HiGHS 의존 제거로
  solver 표면을 단순화. 실 LP full-flux 가 필요하면 gurobi 사용.
- `osqp_growth_gurobi_flux`(OSQP-growth→gurobi-LP recalc) experimental 변형은 필요 시 별도 후속.
