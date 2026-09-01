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

그러나 2026-09-01 추가 확인 결과 `0x2001`은 CPX-AP-I-4IOL-M12의 ISDU Access object가
아니라 실제 module parameter object로 판단한다. 특히 `0x2001:00 = 57`이며, Port Mode,
Port Status, Actual VendorID/DeviceID, Input/OutputDataLength가 이 object에서 정상적으로
읽혔다. 같은 구성에서 `0x2002`, `0x2011`, `0x2012`, `0x2021`, `0x2022`는 SDO object로
확인되지 않았다.

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
- 같은 구성에서 ISDU Access 후보 object는 실장치 SDO dictionary에서 확인되지 않았다.
  - `0x2002`, `0x2011`, `0x2012`, `0x2021`, `0x2022`는 object-not-found로 확인했다.
- 따라서 현재 실패는 IOL port 비활성 문제가 아니라 CPX-AP-I-4IOL-M12의 ISDU Access OD가
  확인된 실장치 SDO dictionary에서 일반 object로 노출되지 않는 문제로 본다.
- 공개 `system/io/iol/param_read`와 `system/io/iol/param_write`는 실장치 접근 경로가 확정될 때까지
  `UNSUPPORTED_OPERATION`으로 명확히 보류한다.
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

1. CPX-AP-I-4IOL-M12의 ISDU Access 경로는 ESI의 `DependOnSlot` object 표기만으로
   Motion Server에서 바로 SDO 접근할 수 있는 형태가 아닐 수 있다.
2. process data와 module parameter는 정상이어도 acyclic ISDU service는 별도 mailbox,
   tool 전용 service, 또는 다른 object 경로를 사용할 수 있다.
3. `0x2001`은 현재 실장치 기준으로 ISDU gateway가 아니라 module parameter object로 본다.
4. CPX-AP-I-EC 전용 manual 또는 FAS/TwinCAT 동작 대조가 필요하다.

## 구현 계획

1. 공개 `system/io/iol/param_read/write`는 실장치 ISDU Access 경로가 확정될 때까지
   `UNSUPPORTED_OPERATION`으로 응답한다.
2. CPX-AP-I-EC ESI와 가능한 공식/제조사 문서에서 ISDU access object의 subindex,
   access 속성, module offset과 실행 trigger 의미를 정리한다.
3. 현재 handler의 내부 SDO write/read sequence는 삭제하지 않고 실험용 코드로 보존하되,
   공개 handler에서는 호출하지 않는다.
4. 실장치에서 최소 read sequence를 단계별로 검증한다.
   - 후보 object 존재 여부
   - object별 subindex 0 count
   - port/channel write 가능 여부
   - index/subindex write 가능 여부
   - direction trigger 가능 여부
   - status/error read 가능 여부
   - length/data read 가능 여부
5. 단계별 raw SDO 확인은 RF-016 Hidden Expert Mode를 사용하며, 공개 API guard를 영구 제거하지 않는다.
6. 필요한 경우 CPX gateway sequence를 수정하되 `port=1`을 임의로 `port=0`으로 변환하지 않는다.
7. 실장치 ISDU Access 경로가 확정되기 전까지 Virtual CPX gateway를 공개 API 성공 계약으로
   확장하지 않는다.
8. API 문서와 test procedure에 process data 확인과 ISDU 접근 보류를 분리해 기록한다.

## 제외 범위

- IO-Link process data decoding 계약 변경은 RF-015에서 관리한다.
- Virtual AP/IO-Link parameter runtime device 구현은 RF-013에서 관리한다.
- Bus 단절 중 요청 격리와 서버 생존성은 TD-031에서 관리한다.
- 임의 port 번호 변환 fallback은 추가하지 않는다.

## 완료 조건

- 현재 단계 완료 조건:
  - `system/io/iol/param_read`와 `system/io/iol/param_write`가 실장치 ISDU Access 경로 미확정 상태를
    `UNSUPPORTED_OPERATION`으로 명확히 반환한다.
  - IO-Link process data decoding과 CPX module parameter read/write는 계속 사용할 수 있다.
  - 실장치에서 확인한 IOL module parameter object와 ISDU Access 후보 object 부재가 문서화된다.
- 후속 재개 조건:
  - Festo Automation Suite, TwinCAT 또는 제조사 문서에서 CPX-AP-I-4IOL-M12 ISDU Access 경로가
    확인된다.
  - 확인된 경로로 `system/io/iol/param_read`가 실장치 port 1의 대표 ISDU parameter를 읽는다.
  - `system/io/iol/param_write`가 쓰기 가능한 대표 ISDU parameter에서 성공하거나,
    쓰기 불가 parameter에 대해 정확한 device reject를 반환한다.
  - 실패 응답에는 `isdu_step`, `sdo_index`, `sdo_subindex`, `sdo_value`, device code/status가 포함된다.
- process data valid와 acyclic ISDU access 가능 여부를 분리한 문서와 회귀 테스트가 있다.
- 전체 unit test와 관련 실장치 smoke test가 통과한다.
