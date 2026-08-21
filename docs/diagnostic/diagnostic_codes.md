# Diagnostic Code Catalog

이 문서는 Motion Server가 생성하는 안정적인 Diagnostic code와 발생·해제 조건을 관리한다.
API 요청 실패 code는 [API Failure Code](../api/failure_codes.md)에서 별도로 관리한다.

## Server

### SERVER_INITIALIZATION_FAILED

| 항목 | 값 |
| --- | --- |
| Level | `FAULT` |
| Source | `SERVER:0` |
| Latching | `true` |
| 발생 조건 | 필수 drive startup initialization 실패로 degraded server mode에 진입함 |
| Resolve 조건 | 같은 프로세스의 runtime 재초기화가 성공함 |
| Clear 조건 | resolve와 사용자 acknowledge가 모두 완료됨 |

Exception 문자열은 Diagnostic `detail/context`에 저장하지 않는다. 기존 `initialization_error` 상태
field는 현재 client 호환을 위해 유지하며 S08D의 Diagnostic 직렬화 계약과 S09 client migration에서
표시 책임을 다시 검토한다.

서버 reset과 bus reconnect는 같은 프로세스의 `DiagnosticManager`를 새 runtime에 전달한다. 따라서
재초기화 성공은 이 Fault를 resolve하지만 acknowledge 없이 제거하지 않는다. 전체 프로세스 재시작을
넘는 영속 저장은 현재 범위에 포함하지 않는다.

## Bus

### BUS_PROCESS_DATA_INCOMPLETE

| 항목 | 값 |
| --- | --- |
| Level | `FAULT` |
| Source | `BUS:0` |
| Latching | `true` |
| 발생 조건 | EtherCAT WKC가 expected WKC와 3 cycle 연속 불일치함 |
| Resolve 조건 | WKC가 expected WKC와 다시 일치함 |
| Clear 조건 | resolve와 사용자 acknowledge가 모두 완료됨 |

한 cycle의 WKC 불일치는 단발성 process-data 이상으로 보고 Diagnostic을 생성하지 않는다. 정상 cycle이
한 번 관측되면 발생 전 연속 불일치 count를 초기화한다. 이미 발생한 Fault는 정상 cycle에서 resolve되지만
latching이므로 acknowledge 전에는 clear되지 않는다.

## Axis

### AXIS_DRIVE_FAULT

| 항목 | 값 |
| --- | --- |
| Level | `FAULT` |
| Source | `AXIS:<configured index>` |
| Latching | `true` |
| 발생 조건 | CiA 402 statusword fault bit 3이 set됨 |
| Resolve 조건 | statusword fault bit 3이 clear됨 |
| Clear 조건 | resolve와 사용자 acknowledge가 모두 완료됨 |

### AXIS_DRIVE_WARNING

| 항목 | 값 |
| --- | --- |
| Level | `ALARM` |
| Source | `AXIS:<configured index>` |
| Latching | `false` |
| 발생 조건 | CiA 402 statusword warning bit 7이 set됨 |
| Resolve/Clear 조건 | statusword warning bit 7이 clear됨 |

## IO

CPX-AP ESI는 `0x6102 Diagnosis`와 선택형 `0x1AF1 Diag PDO`를 제공하지만, `0x1AF1`은 기본 Sync
Manager assignment에 포함되지 않는다. 현재 runtime PDO model은 설정된 AP module process data만
사용하므로 모든 PDO configuration에서 보장되는 I/O health source가 없다.

따라서 현재는 `IO:<configured index>` station 또는 그 아래 module/channel Diagnostic을 생성하지 않는다.
Bus WKC 불일치로 특정 I/O를 추정하지 않고, 단발 AP/ISDU 요청 실패도 I/O Alarm/Fault로 승격하지 않는다.
선택형 상세 진단은 [RF-012](../tasks/rf/RF-012-cpx-ap-optional-diagnostic.md)에서 추적한다.
