"""CMIG headless value-added core (engine-agnostic, GUI/CLI 독립).

Design Ref: §2.1 / §9 — core/ 는 외부 의존 없는 순수 도메인 로직.
MICOM 호출은 engine wrapper 단일 진입점만 경유, 산출은 tidy 단일 계약.
"""
