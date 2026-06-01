"""CMIG — Community Metabolic Interaction GUI (headless core).

community FBA는 MICOM(정확 pin·public API only)에 위임하고, CMIG가 namespace 정합·
sign 정규화·tidy 계약·delta·sandbox·sweep·R 그림의 부가가치 계층을 소유한다.

Authoritative ground truth: CMIG_명세서_v3.0.md (§1–§11, §16).
Design: docs/02-design/features/cmig-community-core.design.md (Option C).
"""

__version__ = "0.1.0"
# Design Ref: §4.3 — cmig_core_version 은 run_hash 11구성요소 #9 (schema §4.2).
CMIG_CORE_VERSION = __version__
