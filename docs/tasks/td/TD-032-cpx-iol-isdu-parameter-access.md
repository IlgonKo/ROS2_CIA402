# TD-032 CPX IO-Link ISDU Parameter Read/Write 실패

## 상태

- 상태: `open`
- 우선순위: 높음
- 등록일: 2026-08-31
- 관련 항목: TD-031, RF-001, RF-013, RF-015

## 배경

실장치 CPX-AP-I-4IOL-M12에서 IO-Link process value는 확인되지만,
`system/io/iol/param_read`와 `system/io/iol/param_write`가 성공하지 않는다.

2026-08-31 실장치 확인 중에는 module 1의 ISDU access object를 `0x2001`로 가정하고
Motion Server의 module별 ISDU access object 계산을 module 1 `0x2001`,
module 2 `0x2011` 기준으로 수정했다.

그러나 2026-09-01 추가 확인 결과 당시 펌웨어에서는 `0x2001`이
CPX-AP-I-4IOL-M12의 ISDU Access object가 아니라 module parameter object로 판단되었다.
특히 `0x2001:00 = 57`이며, Port Mode, Port Status, Actual VendorID/DeviceID,
Input/OutputDataLength가 이 object에서 정상적으로 읽혔다. 같은 구성에서 `0x2002`,
`0x2011`, `0x2012`, `0x2021`, `0x2022`는 SDO object로 확인되지 않았다.

2026-09-04 CPX-AP-I-EC 펌웨어 업데이트 이후 사용자가 IO-Link parameter 접근 가능을
확인했다. 새 펌웨어에서는 CPX module PDO index와 같은 stride 개념을 적용하여 ISDU Access
object가 계산된다. 현재 확인된 규칙은 다음과 같다.

```text
ISDU Access object = 0x2001 + module_slot * module_index_stride
```

예를 들어 `MOTION_SERVER_IO_io0_MODULE_PDO_INDEX_STRIDE=0x0010`이고 IOL module이 첫 번째
AP module slot이면 ISDU Access object는 `0x2011`이다.

아래는 `0x2001`을 ISDU access object로 가정했을 때 관측했던 실패 요청이다.

```json
{
  "cmd": "system/io/iol/param_read",
  "io": "io0",
  "module": 1,
  "port": 1,
  "index": 81,
  "subindex": 0,
  "data_type": "uint8",
  "length": 1
}
```

관측된 Fail detail:

```json
{
  "operation": "sdo_write",
  "device_code": 101253168,
  "isdu_step": "write port",
  "sdo_index": "0x2001",
  "sdo_subindex": 2,
  "sdo_value": 1
}
```

`101253168`은 `0x06090030`이다. 이 실패는 센서 ISDU index 81 접근 전의
`0x2001:02 = 1` SDO write에서 발생했지만, 이후 확인 결과 해당 object는 ISDU gateway가
아니므로 이 실패를 정상 ISDU sequence 실패로 해석하지 않는다.

## 현재까지 확정한 점

- `port=1`은 유지한다.
  - 센서는 두 번째 물리 포트에 연결되어 있고, CPX/ESI 표기는 `Port 0`, `Port 1`의
    0-base 개념을 사용한다.
  - process value가 확인되므로 포트 자체가 비활성화되었다고 단정하지 않는다.
- AI module을 제거하고 CPX-AP-I-EC 바로 아래에 CPX-AP-I-4IOL-M12를 연결한 구성에서,
  IOL module parameter object는 `0x2001`로 확인했다.
  - `0x2001:00 = 57`
  - port 1 `Port Mode = IOL_MANUAL`, `Port Status = OPERATE`, `Actual VendorID/DeviceID`,
    Input/OutputDataLength가 정상으로 읽힌다.
- 펌웨어 업데이트 후 `module_pdo_index_stride=0x0010` 구성에서 첫 번째 IOL module의 ISDU Access
  object는 `0x2011`로 접근 가능하다.
- 공개 `system/io/iol/param_read`와 `system/io/iol/param_write`는 더 이상 보류하지 않고,
  configured module stride를 반영한 ISDU Access object를 통해 실행한다.
- `Direction`은 idle/neutral 값이 아니라 `Read`/`Write` 실행 trigger 성격으로 본다.
  - ESI의 Direction enum은 `0 = Read`, `1 = Write`로 확인된다.
- `Channel -> Index -> Subindex -> Direction` 계열의 request 조립 순서를 우선 기준으로 본다.
  - 순서 변경은 문서와 실장치 증거 없이 임의로 적용하지 않는다.

## 외부 문서 조사 기록

- Festo CPX-FB36의 ISDU Access Object는 `Channel`, `CBUS module`, `Index`, `Sub-index`,
  `Data`를 request에 포함하며, response status에 `Port unknown`, `Port on master not support`,
  `Port in invalid state`를 별도로 둔다.
- ifm EtherCAT IO-Link master의 acyclic command 예시는 port별 object에서 command buffer에
  command, IO-Link index, subindex, length/data를 구성하고 status/response buffer로 결과를 확인한다.
- Beckhoff 문서는 IO-Link acyclic data가 device-specific index/subindex range를 사용하며
  구체 접근 방식은 vendor documentation에 의존한다고 설명한다.

위 문서들은 CPX-AP-I-EC의 `0x2001` SDO write 순서를 직접 확정하지는 않지만,
ISDU 접근이 단순 process data 활성 여부와 별도인 acyclic service 계약이라는 점을 뒷받침한다.

## 가설

1. ISDU Access object는 고정 module ordinal 기준이 아니라 AP module slot과 firmware별
   module index stride를 함께 사용한다.
2. process data와 module parameter가 정상이어도 acyclic ISDU access object 노출 여부는
   펌웨어에 따라 달라질 수 있다.
3. `0x2001`은 현재 새 펌웨어/stride 구성에서 slot 0이 아니라면 실제 IOL module의 ISDU Access
   object로 사용하지 않는다.

## 구현 계획

1. 공개 `system/io/iol/param_read/write`를 실제 handler로 다시 연결한다.
2. ISDU Access object index는 `0x2001 + module_slot * module_pdo_index_stride`로 계산한다.
3. `system/io/iol/param_catalog`의 `object_index`도 같은 계산을 사용한다.
4. Virtual CPX OD와 gateway dispatch도 같은 stride 규칙을 사용한다.
5. 실장치에서 최소 read/write sequence를 단계별로 검증한다.
   - 후보 object 존재 여부
   - object별 subindex 0 count
   - port/channel write 가능 여부
   - index/subindex write 가능 여부
   - direction trigger 가능 여부
   - status/error read 가능 여부
   - length/data read 가능 여부
6. 필요한 경우 CPX gateway sequence를 수정하되 `port=1`을 임의로 `port=0`으로 변환하지 않는다.
7. API 문서와 test procedure에 펌웨어/stride 의존성을 기록한다.

## 제외 범위

- IO-Link process data decoding 계약 변경은 RF-015에서 관리한다.
- Virtual AP/IO-Link parameter runtime device 구현은 RF-013에서 관리한다.
- Bus 단절 중 요청 격리와 서버 생존성은 TD-031에서 관리한다.
- 임의 port 번호 변환 fallback은 추가하지 않는다.

## 완료 조건

- `system/io/iol/param_read`와 `system/io/iol/param_write`가 configured module stride를 반영한
  ISDU Access object를 사용한다.
- `system/io/iol/param_catalog`가 같은 object index를 표시한다.
- 확인된 경로로 `system/io/iol/param_read`가 실장치 port 1의 대표 ISDU parameter를 읽는다.
- `system/io/iol/param_write`가 쓰기 가능한 대표 ISDU parameter에서 성공하거나,
  쓰기 불가 parameter에 대해 정확한 device reject를 반환한다.
- 실패 응답에는 `isdu_step`, `sdo_index`, `sdo_subindex`, `sdo_value`, device code/status가 포함된다.
- process data valid와 acyclic ISDU access 가능 여부를 분리한 문서와 회귀 테스트가 있다.
- 전체 unit test와 관련 실장치 smoke test가 통과한다.
