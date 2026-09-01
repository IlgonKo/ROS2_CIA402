# TD-032 CPX IO-Link ISDU Parameter Read/Write 실패

## 상태

- 상태: `open`
- 우선순위: 높음
- 등록일: 2026-08-31
- 관련 항목: TD-031, RF-001, RF-013, RF-015

## 배경

실장치 CPX-AP-I-4IOL-M12에서 IO-Link process value는 확인되지만,
`system/io/iol/param_read`와 `system/io/iol/param_write`가 성공하지 않는다.

2026-08-31 실장치 확인에서 module 1의 ISDU access object는 `0x2001`로 판단했다.
`0x2001:02` 직접 read는 성공했고 `0x2021:02`는 object-not-found로 실패했다.
이에 따라 Motion Server의 module별 ISDU access object 계산은 module 1 `0x2001`,
module 2 `0x2011` 기준으로 수정했다.

주소 수정 후에도 다음 요청은 port 선택 단계에서 장치가 거부했다.

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

`101253168`은 `0x06090030`이며, 현재 거부 지점은 센서 ISDU index 81 접근 전의
`0x2001:02 = 1` SDO write다.

## 현재까지 확정한 점

- `port=1`은 유지한다.
  - 센서는 두 번째 물리 포트에 연결되어 있고, CPX/ESI 표기는 `Port 0`, `Port 1`의
    0-base 개념을 사용한다.
  - process value가 확인되므로 포트 자체가 비활성화되었다고 단정하지 않는다.
- `0x2001:02`는 ISDU access object의 `Port` subindex로 해석한다.
- 현재 실패는 공개 API validation이나 IODD catalog 문제가 아니라 실장치 SDO write 거부다.
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

1. CPX-AP-I-4IOL-M12의 `0x2001` gateway가 현재 Motion Server의 SDO write sequence를
   기대 순서로 처리하지 않을 수 있다.
2. process data는 정상이어도 acyclic ISDU service는 port/device 상태에 따라 별도로
   `Port in invalid state` 또는 CoE abort로 거부될 수 있다.
3. `0x2001:02 = 1` write가 거부되는 이유는 port 번호 변환 문제가 아니라
   gateway request 조립 상태, access timing, 또는 port의 acyclic service 상태일 수 있다.
4. CPX-AP-I-EC 전용 manual 또는 FAS/TwinCAT 동작 대조가 필요할 수 있다.

## 구현 계획

1. CPX-AP-I-EC ESI와 가능한 공식/제조사 문서에서 ISDU access object의 subindex,
   access 속성, module offset과 실행 trigger 의미를 정리한다.
2. 현재 handler의 SDO write/read sequence를 명시적인 단계 함수와 테스트 fixture로 분리한다.
3. 실장치에서 최소 read sequence를 단계별로 검증한다.
   - `0x2001:02` direct read
   - port write
   - index/subindex write
   - direction trigger
   - status/error read
   - length/data read
4. 단계별 raw SDO 확인은 RF-016 Hidden Expert Mode를 사용하며, 공개 API guard를 영구 제거하지 않는다.
5. 필요한 경우 CPX gateway sequence를 수정하되 `port=1`을 임의로 `port=0`으로 변환하지 않는다.
6. `param_write`도 같은 sequence 계약으로 정리하고, 실패 단계 detail을 유지한다.
7. Virtual CPX gateway와 unit test를 실장치 sequence와 같은 계약으로 갱신한다.
8. API 문서와 test procedure에 process data 확인과 ISDU 접근 성공을 별도 확인 항목으로 분리한다.

## 제외 범위

- IO-Link process data decoding 계약 변경은 RF-015에서 관리한다.
- Virtual AP/IO-Link parameter runtime device 구현은 RF-013에서 관리한다.
- Bus 단절 중 요청 격리와 서버 생존성은 TD-031에서 관리한다.
- 임의 port 번호 변환 fallback은 추가하지 않는다.

## 완료 조건

- `system/io/iol/param_read`가 실장치 port 1의 대표 ISDU parameter를 읽는다.
- `system/io/iol/param_write`가 쓰기 가능한 대표 ISDU parameter에서 성공하거나,
  쓰기 불가 parameter에 대해 정확한 device reject를 반환한다.
- 실패 응답에는 `isdu_step`, `sdo_index`, `sdo_subindex`, `sdo_value`, device code/status가 포함된다.
- process data valid와 acyclic ISDU access 가능 여부를 분리한 문서와 회귀 테스트가 있다.
- 전체 unit test와 관련 실장치 smoke test가 통과한다.
