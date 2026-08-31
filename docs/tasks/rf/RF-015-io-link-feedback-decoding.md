# RF-015 IO-Link IODD 기반 Feedback 디코딩

- 등록일: 2026-08-31
- 상태: `complete`
- 우선순위: 보통
- 현재 단계: 2026-08-31 계약 확정 및 구현. 자동 검증 완료; 실장치 대조 검증은 미수행.

## 사용자 가치

Control Panel과 Node-RED가 IODD 및 raw byte를 직접 해석하지 않아도 IO-Link 센서의
측정값, 단위와 상태 bit를 사용할 수 있도록 한다. 해석 전 raw 데이터도 함께 유지하여
장치 검증 및 디코딩 문제 분석에 사용할 수 있게 한다.

## 배경 및 기존 기능

- 현재 `motion_server/api/encoder.py`는 IO-Link module raw payload, 포트별 `port/data`와
  별도의 qualifier 배열을 제공한다. 측정값 및 상태 bit 디코딩은 아직 구현하지 않았다.
- `MOTION_SERVER_IO_<io>_IOL_PORTS`는 `<port>:<iodd_key>[:<process_data_profile>]`을 지원한다.
  명시값은 IODD `Condition value`의 숫자이며, 생략 시 IODD 문서 순서의 첫 profile을 선택한다.
- 포트 binding은 선택한 profile을 보관하지만 현재 IODD metadata는 profile id, condition value,
  input/output 크기까지만 제공한다. Record/DatatypeRef 및 field metadata 해석을 확장해야 한다.
- DEC-011의 ESI/IODD metadata 원칙을 따른다. RF-013의 가상 ISDU parameter 공간과는 별도 기능이다.

## 요청된 구현 범위

- 주기 `system/feedback`의 IO-Link 입력에 포트별 raw, qualifier와 `decoded` 정보를 함께 제공한다.
- 선택된 profile에 따라 측정값, 단위와 이름이 있는 상태 bit를 해석한다.
- 동일 IODD를 사용하는 포트라도 선택한 profile과 데이터가 서로 영향을 주지 않도록 한다.
- 동일한 raw 데이터와 설정에는 real/mock 모두 같은 해석 결과를 제공한다.
- IODD metadata는 설정/모델 구성 시 준비하며 매 Feedback마다 XML을 다시 읽거나 SDO/ISDU를
  조회하지 않는다. 주기 처리에서는 현재 raw process data만 디코딩한다.

## 확정 응답 계약

기존 `inputs.io_link_channels[]`를 확장하고 별도 `inputs.io_link_qualifiers` 배열은 제거한다.
module 전체 `inputs.io_link` raw와 output 응답은 그대로 유지한다. 같은 snapshot을 사용하는
`system/feedback`, `system/io/status`, `system/io/input_read` 및 output-write 응답의 input에도 적용한다.

| 위치 | 필드 | 의미 |
|---|---|---|
| 포트 | `port` | 해당 module 내부 IO-Link port 번호 |
| 포트 | `data` | variant padding을 포함한 해당 포트 전체 raw hexadecimal 데이터 |
| 포트 | `qualifier` | CPX 포트 qualifier 원시 정수; 바이트가 없으면 `null` |
| 포트 | `decode_status` | `ok`, `not_configured`, `unsupported`, `invalid_data` |
| 포트 | `decoded` | 선택된 IODD profile의 해석 결과 또는 `null` |
| decoded | `profile` | 설정과 동일한 숫자 Condition value; 무조건부 profile은 `null` |
| decoded | `profile_name` | 사용자에게 표시할 profile 이름 |
| decoded | `values[]` | `subindex`, `name`, `value`, `unit`을 갖는 숫자값 목록 |
| decoded | `status_bits[]` | `subindex`, `bit_offset`, `name`, `active`를 갖는 Boolean 목록 |

- 식별자는 station id → module slot → port → `subindex` 조합이다. scalar는 subindex `0`,
  RecordItem은 IODD subindex를 사용한다. 이름은 IODD PrimaryLanguage의 표시 텍스트이다.
- `bit_offset`은 IODD process data상의 offset으로 정의하여 byte 내부 bit 번호와 혼동하지 않게 한다.
- 상태 bit는 `active: false`도 포함한다.
- 단위 및 scale은 IODD 근거가 있는 경우만 적용한다. 알 수 없는 단위를 추측하지 않는다.
- 디코딩 불가 시 raw/qualifier는 유지하고 `decoded: null`로 표현한다. 한 포트의 실패는
  다른 포트/Feedback을 중단하지 않는다. 부분 field 결과를 정상 결과로 제공하지 않는다.
- 판정 순서: binding 없음 → `not_configured`; 공통 process-data 무효/qualifier 무효/길이 부족 →
  `invalid_data`; 미지원 metadata → `unsupported`; 비정상 숫자 → `invalid_data`; 나머지 → `ok`.
- CPX qualifier bit7(PQ)와 bit5(DevCom)가 모두 1이어야 디코딩한다. bit6(DevErr)는 원시값으로
  유지하되 이것만으로 input을 무효화하지 않는다. Bus disconnected에서도 stale qualifier를 믿지 않는다.

## 책임 경계

1. IODD catalog: 선택된 profile의 datatype, record field, offset, name, unit 및 변환 metadata 제공.
2. IO-Link process data decoder: 준비된 metadata와 raw bytes로 해석 결과 생성.
3. API encoder: raw/qualifier/decoded를 기존 I/O 응답 구조에 조립.

센서별 해석을 EtherCAT Master, MockSlave, VirtualOdBridge 또는 Virtual Device behavior에
추가하지 않는다. 센서 상태 bit를 서버 Diagnostic Alarm/Fault로 자동 승격하지 않는다.

## 지원 타입과 변환

- 기본 숫자 타입: `IntegerT`, `UIntegerT`(1~64bit), `Float32T`; Boolean은 `BooleanT`.
  signed integer는 2의 보수, Float32는 IEEE754, 다중 byte는 IO-Link big endian으로 해석한다.
- flat `RecordT`와 `DatatypeRef`, inline `Datatype`/`SimpleDatatype`를 지원한다.
  bitOffset은 LSB 기준이며 byte 비정렬 integer/Boolean도 해석한다. profile 유효 길이만 디코딩하며
  variant padding을 숫자값에 섞지 않는다.
- Array, nested Record, String/OctetString, 알 수 없는 datatype과 누락/중복 DatatypeRef는
  `unsupported`로 처리한다. 범위 밖/중첩 field, subindex 중복, 모호한 conversion metadata도 같다.
  전체 IODD 표준/버전의 완전한 schema validator를 구현하는 범위는 아니다.
- `ProcessDataRef`는 선택된 `ProcessDataIn.id`로 연결한다. `ProcessDataInfo` 또는
  `ProcessDataRecordItemInfo`의 고정 gradient/offset으로 `value = raw * gradient + offset`을 적용한다.
  명시되지 않으면 1/0이며 단위 변환이나 표시 반올림을 추가하지 않는다. Enum label/특수값 의미를
  추정하지 않고 숫자를 유지한다.
- 초기 단위 symbol table은 공식 StandardUnitDefinitions의 1001=`°C`, 1062=`mm/s`, 1658=`g`를
  지원한다. 미등록/미지정 unitCode는 `null`; 센서 이름을 기준으로 단위나 scale을 추측하지 않는다.
- 이름과 단위를 매 Feedback에 포함한다. catalog load에서 metadata를 immutable layout으로 준비하고
  주기 경로에는 XML 재파싱, SDO/ISDU 조회와 센서별 분기를 추가하지 않는다.

### 근거

- [IO-Link Interface V1.1.2 §7.2.1](https://io-link.com/fileadmin/user_upload/Downloads/Package_2015/IOL-Interface-Spec_10002_V112_Jul13.pdf): 다중 octet big endian.
- [IODD V1.1.4 specification/schema/standard definitions](https://io-link.com/fileadmin/user_upload/Downloads/Package_2024/IO-Device-Desc-Spec_10012_V114_Jun24_Update202507.zip):
  Datatype/RecordItem, ProcessDataInfo gradient/offset, StandardUnitDefinitions1.1 V1.1.9 단위 표.
- [Festo CPX-AP-I-4IOL-M12 매뉴얼](https://www.festo.com/fox/net/supportportal/defaultwindow.aspx?q=CPX-AP-I-4IOL-M12&s=t&tab=4),
  2025-05e p.11 Port Qualifier Information Bytes: PQ bit7, DevErr bit6, DevCom bit5, 마지막 4 input bytes가 port qualifier.
- bundled Balluff IODD: `D_VibrationVelocity`, `DT_PD_Slot`, `DT_PD_Stat`와
  `PI_Vibration_VelocIn`의 ProcessDataRef로 field offset·타입·단위를 대조했다.

## 구현 및 검증 기록

- `device/io_link/iodd_process_data.py`: immutable layout compiler와 확인된 unit symbol table.
- `device/io_link/process_data.py`: 공통 raw decoder; `iodd_catalog.py`가 profile별 layout을 소유한다.
- `motion_server/api/encoder.py`: 포트 응답 조립. feedback/status/input-read/output-write에서
  공통 process-data 유효성을 전달한다. Master/Bridge/Virtual Device 책임은 변경하지 않았다.
- `tests/test_io_link_decoding.py`: 독립 IEEE754 raw fixture, 단위/bit, scalar/record/참조,
  profile·module·station 격리, 미지원/무효 입력, raw injection과 실장치 codec 경로 parity,
  조회 API 간 동일 schema 및 bus 단절 시 stale 값 차단을 검증한다.
- 로컬 4-port Balluff fixture 측정: snapshot+decode+JSON 약 0.15ms, UTF-8 JSON 14,306 bytes.
  이름·단위 포함 정책의 초기 회귀 기준은 같은 fixture에서 5ms/32KiB 이하이며 실시간 보장은 아니다.
  기본 Feedback period 50ms 대비 충분한 여유가 있지만 station/client 수에 비례하여 payload와 비용은 증가한다.
- 실센서 수치 대조, 대규모 station/client 부하, Windows EXE 재빌드는 미수행이다.
- 자동 검증: 디코딩 전용 16개 포함 전체 unittest 374개와 whitespace 검사 통과.

## 제외 범위

- IO-Link output 디코딩/encoding과 engineering value 쓰기 API.
- 실제 장치 mode/profile을 자동 변경하는 ISDU write 또는 runtime profile 전환.
- RF-013의 가상 AP/ISDU parameter 장치 및 센서 물리 동작 모델.
- Control Panel/Node-RED 전용 신규 화면 구현. 본 항목은 공통 API와 사용 예제까지 다룬다.

## 검증 및 완료 조건

- 확정된 API 구조와 지원/미지원 범위를 문서화하고 그 계약에 맞는 decoder 및 encoder를 구현한다.
- 실제 IODD를 기반으로 독립적으로 확인한 raw fixture를 사용해 숫자값, 단위, bit offset과
  inactive bit를 검증한다. 구현 decoder로 생성한 값만을 정답으로 사용하지 않는다.
- 숫자 profile 선택/생략, 서로 다른 크기의 profile, 다중 station/module/port 격리를 검증한다.
- payload 길이 부족, 미설정/미지원 IODD, 무효 qualifier와 비정상 float 등 경계 입력을 검증한다.
  디코딩 불가를 정상값으로 바꾸거나 해당 포트 때문에 전체 Feedback 전달을 중단하지 않는다.
- 같은 raw 입력에 대한 real/mock 공통 경로 parity와 RF-014 raw input injection 회귀를 확인한다.
- 주기 처리 중 XML 재파싱 및 추가 SDO/ISDU 조회가 없고, 처리 시간/메시지 크기가 확정한 한도
  안에 드는지 검증한다. 최종 결과와 미검증 실장치 항목은 worklog에 기록한다.
