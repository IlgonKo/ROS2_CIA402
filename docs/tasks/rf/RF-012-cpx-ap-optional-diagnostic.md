# RF-012 CPX-AP 선택형 상세 Diagnostic

## 구분

Optional Item이다. 기본 Motion Server 및 CPX-AP I/O 운전에 필수인 기능으로 간주하지 않는다.

## 목표

명시적으로 선택한 CPX-AP 구성에서 Diagnosis TxPDO를 활성화하고, I/O station의 Alarm/Fault와 장치가
제공하는 상세 진단 정보를 안정적으로 제공한다.

## 배경

CPX-AP ESI는 `0x6102 Diagnosis`와 이를 process data로 전달하는 `0x1AF1 Diag PDO`를 정의한다.
그러나 `0x1AF1`은 기본 Sync Manager assignment에 포함되지 않는 특수 PDO다. 따라서 현재처럼 설정된
AP module input process image만 사용하는 구성에서는 해당 진단 정보를 주기적으로 받을 수 없다.

## 구현 범위

- 설정에서 선택형 Diagnosis TxPDO 사용 여부를 명시한다.
- `0x1AF1` TxPDO assignment와 실제 mapping readback을 검증한다.
- 추가되는 12-byte diagnosis 영역과 AP module input 영역의 offset 계약을 확정한다.
- `0x6102`의 Category Status, active diagnosis count, latest module과 latest diagnosis code를 decode한다.
- `IO:<configured index>` station 단위 Alarm/Fault 변환 기준을 정의한다.
- module 번호와 diagnosis code는 source identity가 아니라 Diagnostic 상세정보로 제공한다.
- virtual CPX-AP와 실장치의 동일한 공개 동작을 검증한다.

## 범위 제외

- module 또는 channel을 독립적인 Diagnostic source로 만들지 않는다.
- Bus WKC 불일치로 특정 I/O station 또는 module 장애를 추정하지 않는다.
- AP parameter나 IO-Link ISDU 요청의 단발 실패를 I/O Diagnostic으로 승격하지 않는다.
- `0x6102` SDO polling은 PDO를 사용할 수 없는 환경의 요구와 bus 부하 정책이 별도로 확정되기 전에는
  구현하지 않는다.

## 선행 결정

- Category Status bit와 장치 diagnosis category를 Motion Server의 `ALARM`/`FAULT`로 변환하는 기준
- latching 여부와 resolve 조건
- 선택형 PDO 활성화가 기존 module process-image offset과 설정 호환성에 미치는 영향
- latest diagnosis만 제공되는 경우 활성 진단 전체 목록의 표현 범위

## 검증 계획

- `0x1AF1` 비활성 구성에서 기존 process image와 I/O 동작이 변하지 않는지 검증한다.
- 활성 구성에서 PDO assignment/mapping readback, image 크기와 모든 offset을 검증한다.
- Category Status 없음, Alarm, Fault, 복수 활성 진단과 조건 해제를 virtual fixture로 시험한다.
- 대표 CPX-AP 실장치에서 동일한 payload와 Diagnostic lifecycle을 확인한다.

## 완료 증거

설정 계약, ESI/PDO mapping 표, Alarm/Fault 변환표, real/mock parity 자동 테스트와 실장치 readback 기록을
남긴다.
