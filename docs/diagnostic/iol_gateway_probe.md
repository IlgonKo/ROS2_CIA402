# IO-Link gateway 일회성 읽기 진단

- 2026-08-31 사용자 승인: `io0`의 `0x2001:02`, `0x2021:02` 존재/읽기 가능 여부 확인.
- 공개 API 변경 없음. 기존 EC parameter API의 ISDU gateway 차단을 유지한다.
- 서버의 기존 Master `read_sdo(..., size=1)`만 사용한다. 별도 Master, OD write,
  ISDU header/direction 실행 또는 주소 자동 fallback은 추가하지 않는다.
- 임시 startup hook은 `.runtime/iol-gateway-probe.request`가 있을 때만 한 번 실행한다.
  실행 전 marker를 소비하고 `.runtime/iol-gateway-probe-result.json`과 console에 결과를 남긴다.
  실패는 기존 예외의 `__cause__`에서 원래 SDO Abort code를 보존해 보고한다.
- startup/restart의 기존 device initialization은 별개로 유지된다. probe 자체만 읽기 전용이다.
- 실장비 재시작 전 축 Disable 및 제어권 해제를 확인한다. 현재 client의 authority를 강제로 빼앗지 않는다.
- 진단 완료 후 startup hook과 임시 실행 요청을 제거한다. 읽기 성공은 ISDU 쓰기/전체 sequence
  동작 성공을 의미하지 않으므로 별도 승인 전에는 추정하여 주소를 변경하지 않는다.
- 자동 테스트: 고정 주소 두 번 읽기, write 경로 없음, Abort code 보존, marker 단발 실행,
  응답 길이 오류를 검증한다.

## 실제 실행 결과

- 실행일시: 2026-08-31 20:38:06 KST. 사용자가 현재 축 상태에서 재시작 진행을 승인했다.
- 재시작 전 actual velocity=0, authority owner=null을 확인한 뒤 정상 authority/request 및
  server/restart API를 사용했다. 다른 client의 authority를 강제로 해제하지 않았다.
- 기존 PID 14184 → PID 6172로 재시작. 기존 Master의 `io0`, EtherCAT slave index 1에서 읽었다.

| 주소 | 결과 | 값 / 원래 SDO Abort |
|---|---|---|
| `0x2001:02` | success | uint8 `0`, raw `00` |
| `0x2021:02` | fail | `SdoObjectNotFoundException`, `0x06020000` (Object does not exist) |

- 증거 파일: `.runtime/iol-gateway-probe-result.json` (local runtime artifact).
- 일회성 request marker는 실행 전에 소비되었고, 결과 확인 후 server.py의 임시 startup hook도 제거했다.
  probe helper와 자동 테스트는 조사 근거로 보관한다. 다음 재시작에 자동 실행되지 않는다.
- `0x2001:02` 읽기 가능 여부만 확인했다. gateway write 및 sensor index 81의 전체 ISDU read sequence는
  실행하지 않았다.
- 후속 사용자 승인에 따라 Motion Server의 IO-Link ISDU access object 계산은 module 1이
  `0x2001`, module 2가 `0x2011`을 사용하도록 변경했다.
- 최초 사전 조건의 Disable 요청은 사용자의 후속 '축은 지금 상태로 진행해도 됨' 승인으로 대체되었다.
