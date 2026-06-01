# cmig-host-microbe Design (Option C, config B)
| synthetic_host.py | 신규 | colonocyte toy(lumen SCFA=유일 탄소·blood O2·ATPM viability) |
| core/host.py | 신규 | HostInterface·InterfaceFlux·classify_host_exchanges·solve_host·run_host_microbe |
| core/host_impact.py | 신규 | HostImpact·host_impact(microbe→host 분해) |
| tests/test_host.py | 신규 | 8 |
## 설계(config B): micom Community host 파라미터 없음(probe) → CMIG 2-compartment. solve_host: lumen interface 기본 폐쇄(phantom 흡수 방지)→가용 대사체만 개방, ATPM lower=maintenance(viability, bound 역전 가드), host 자체 biomass 목적(군집 미포함). 2-interface=exchange 접미사(_lumen/_blood)+sign.convert. run_host_microbe=community external_exchange(분비) → solve_host → host_impact(실 wiring). toy=정성(Human-GEM 불요, 정량은 후속).
