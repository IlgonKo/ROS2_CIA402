# RF-007 CMMT ESI/PDO 실장치 검증 확대

## 목표

CMMT-AS/ST catalog, required OD와 축별 PDO configuration이 지원 실장치 및 ESI revision에서 일관되게 동작함을 검증한다.

## 구현 범위

- AS/ST model과 ESI revision별 root/subindex parsing을 확인한다.
- required OD readback과 type/access/role validation을 확인한다.
- remap 후 Rx/TxPDO assignment와 mapping entry readback을 기대 configuration과 비교한다.
- 단일축, 6축과 AS/ST 혼합 bus를 시험한다.

## 기술 제약

지원하지 않는 firmware/ESI 조합은 성공으로 간주하지 않고 정확한 compatibility 정보와 실패 원인을 남긴다.

## 검증 계획

- catalog/PDO fixture 자동 테스트와 실제 readback capture를 함께 보존한다.
- 각 구성에서 startup, CiA402 enable, mode 설정과 제한된 motion smoke test를 수행한다.

## 완료 증거

완료 시 device/firmware/ESI matrix, PDO 비교 결과와 motion 시험 기록을 추가한다.
