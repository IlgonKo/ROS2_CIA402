# Exception 발생 및 Catch 지점 전수 조사

## 문서 역할

이 문서는 TD-005 설계를 위한 현재 코드 inventory다. 각 지점이 API Fail, Alarm, Fault 또는
내부 처리 중 어디에 해당하는지는 아직 확정하지 않았으며 목표 계약을 현재 동작처럼 기록하지 않는다.
상세 계약이 확정되면 API 결과는 `docs/api/`, 운전 상태는 `docs/diagnostic/`의 별도 설계 문서로
옮기고, 이 문서는 migration 추적 자료로 유지한다.

## 조사 기준

- 조사일: 2026-08-21
- 범위: 저장소의 Python source
- 제외: `Reference/`, vendor ESI/IODD 원본
- catch: 줄 시작의 `except`
- broad catch: 줄 시작의 `except Exception`
- 발생 지점: 줄 시작의 `raise`
- generic runtime 발생: 줄 시작의 `raise RuntimeError`
- 자동 재조사 명령은 완료 단계에서 별도 검사 script로 고정한다.

## 전체 집계

| 항목 | 개수 |
| --- | ---: |
| 예외 관련 파일 | 74 |
| catch 지점 | 144 |
| `except Exception` | 85 |
| 명시적 raise | 233 |
| `raise RuntimeError` | 42 |
| bare `except:` | 0 |
| bare re-raise | 1 (`ethercat/pysoem_master.py:125`) |

## 계층별 우선 조사 대상

| 계층 | 주요 파일 | 현재 위험 | TD-005에서 결정할 사항 |
| --- | --- | --- | --- |
| EtherCAT transport | `pysoem_master.py`, `sdo_access.py` | library 오류가 `RuntimeError` 문자열로 평탄화됨 | timeout, disconnect, mailbox, short payload 구분 |
| Startup/runtime | `server.py`, `app/startup.py` | readback 실패 후 fallback 또는 계속 실행 정책이 항목별로 다름 | initialization failure와 degraded 상태 경계 |
| EtherCAT parameter | `handlers/parameter_access/ethercat.py` | validation과 SDO transport 실패가 handler에서 같은 문자열 응답으로 변환됨 | object access/API code와 연결 유지 정책 |
| AP parameter | `handlers/parameter_access/ap.py` | AP handshake, timeout, invalid request가 혼재 | AP protocol error와 transport error 구분 |
| IO-Link parameter | `handlers/parameter_access/iol.py` | ISDU status, timeout, encoding 오류가 혼재 | IOL protocol code와 retry/recovery 정책 |
| Command handler | `handlers/command/*` | handler별 broad catch 및 응답 형식 중복 | 공통 client boundary와 programming error 처리 |
| Status handler | `handlers/status/*` | 조회 실패가 빈 상태/문자열 오류로 변환될 수 있음 | partial status 허용 여부와 code |
| Device profile | `device/cmmt/profile.py`, `device/cpx_ap_i_ec/*` | catalog, identity, mapping, readback 오류가 일반 예외 | configuration/device/protocol 경계 |
| Client/Panel | `control_panel/*/client.py`, panel modules | transport, timeout, server reject 표시 방식 불일치 | structured error 호환 및 사용자 표시 |
| ROS | `ros/bridge.py`, `ros/control_panel.py` | socket/JSON/UI 오류가 broad catch에서 합쳐짐 | reconnect, log severity와 사용자 알림 |
| Diagnostics | `diagnostics/*` | 도구 최상위 catch와 제품 코드 정책 혼동 가능 | 제품 allowlist 검사에서 분리 |

## 파일별 전수 집계

`Catch`는 모든 catch, `Broad`는 `except Exception`, `Raise`는 모든 명시적 raise,
`Runtime`은 `raise RuntimeError` 개수다.

| 파일 | Catch | Broad | Raise | Runtime |
| --- | ---: | ---: | ---: | ---: |
| `control_panel/axis_control_panel/client.py` | 4 | 1 | 2 | 0 |
| `control_panel/axis_control_panel/connection.py` | 2 | 1 | 0 | 0 |
| `control_panel/axis_control_panel/control_panel.py` | 1 | 0 | 0 | 0 |
| `control_panel/axis_control_panel/diagnosis.py` | 4 | 1 | 0 | 0 |
| `control_panel/axis_control_panel/motion.py` | 4 | 0 | 1 | 0 |
| `control_panel/axis_control_panel/motion_settings.py` | 4 | 0 | 0 | 0 |
| `control_panel/axis_control_panel/units.py` | 2 | 0 | 0 | 0 |
| `control_panel/io_control_panel/client.py` | 3 | 1 | 3 | 0 |
| `control_panel/io_control_panel/control_panel.py` | 11 | 11 | 4 | 4 |
| `device/__init__.py` | 1 | 0 | 1 | 0 |
| `device/capabilities.py` | 0 | 0 | 1 | 0 |
| `device/cmmt/error_catalog.py` | 3 | 0 | 0 | 0 |
| `device/cmmt/esi_catalog.py` | 0 | 0 | 3 | 0 |
| `device/cmmt/pdo_codec.py` | 0 | 0 | 2 | 0 |
| `device/cmmt/pdo_configuration.py` | 1 | 0 | 4 | 0 |
| `device/cmmt/profile.py` | 5 | 4 | 5 | 5 |
| `device/cmmt/rxpdo.py` | 0 | 0 | 1 | 0 |
| `device/cmmt/txpdo.py` | 0 | 0 | 1 | 0 |
| `device/cpx_ap_i_ec/ap_module_idents.py` | 0 | 0 | 3 | 2 |
| `device/cpx_ap_i_ec/ap_parameter_access.py` | 0 | 0 | 1 | 1 |
| `device/cpx_ap_i_ec/esi_module_catalog.py` | 2 | 0 | 3 | 0 |
| `device/cpx_ap_i_ec/file_matching.py` | 0 | 0 | 3 | 0 |
| `device/cpx_ap_i_ec/io_config.py` | 2 | 0 | 15 | 0 |
| `device/cpx_ap_i_ec/module_layout.py` | 1 | 0 | 17 | 0 |
| `device/cpx_ap_i_ec/module_resolver.py` | 3 | 0 | 9 | 0 |
| `device/cpx_ap_i_ec/pdo_configuration.py` | 1 | 0 | 3 | 3 |
| `device/io_link/file_matching.py` | 0 | 0 | 2 | 0 |
| `device/io_link/iodd_catalog.py` | 0 | 0 | 1 | 0 |
| `device/pdo_metadata/base.py` | 0 | 0 | 3 | 0 |
| `device/virtual_servo_drive/od_bridge.py` | 0 | 0 | 1 | 0 |
| `device/virtual_servo_drive/od_model.py` | 0 | 0 | 1 | 0 |
| `device/virtual_servo_drive/servo_model.py` | 1 | 1 | 1 | 0 |
| `diagnostics/check_legacy_names.py` | 1 | 0 | 1 | 0 |
| `diagnostics/cmmt_sync_probe.py` | 1 | 1 | 2 | 2 |
| `diagnostics/dump_pdo_mapping.py` | 2 | 2 | 0 | 0 |
| `diagnostics/pysoem_single_axis_smoke_test.py` | 1 | 1 | 0 | 0 |
| `ethercat/backend_contract.py` | 0 | 0 | 1 | 0 |
| `ethercat/mock_master.py` | 0 | 0 | 3 | 2 |
| `ethercat/pysoem_master.py` | 7 | 5 | 11 | 8 |
| `ethercat/sdo_access.py` | 4 | 4 | 5 | 5 |
| `motion_server/api/decoder.py` | 0 | 0 | 3 | 0 |
| `motion_server/api/validator.py` | 0 | 0 | 2 | 0 |
| `motion_server/app/client_transport.py` | 1 | 0 | 0 | 0 |
| `motion_server/app/runtime.py` | 0 | 0 | 2 | 0 |
| `motion_server/app/startup.py` | 7 | 7 | 5 | 0 |
| `motion_server/config.py` | 0 | 0 | 6 | 1 |
| `motion_server/control/csp_trajectory_generator.py` | 0 | 0 | 2 | 0 |
| `motion_server/control/motion_controller.py` | 0 | 0 | 1 | 0 |
| `motion_server/control/setpoint_output.py` | 0 | 0 | 1 | 1 |
| `motion_server/control/trajectory_verifier.py` | 0 | 0 | 4 | 0 |
| `motion_server/device_manager/axis_device_group.py` | 0 | 0 | 3 | 0 |
| `motion_server/device_manager/axis_diagnostics.py` | 1 | 1 | 0 | 0 |
| `motion_server/device_manager/axis_unit_conversion.py` | 0 | 0 | 1 | 0 |
| `motion_server/device_manager/io_device_group.py` | 0 | 0 | 4 | 0 |
| `motion_server/handlers/authority/registry.py` | 0 | 0 | 1 | 1 |
| `motion_server/handlers/command/axis_settings.py` | 7 | 6 | 1 | 0 |
| `motion_server/handlers/command/axis_state.py` | 8 | 6 | 1 | 1 |
| `motion_server/handlers/command/homing.py` | 1 | 0 | 0 | 0 |
| `motion_server/handlers/command/io_output_write.py` | 1 | 1 | 3 | 0 |
| `motion_server/handlers/command/jog.py` | 4 | 4 | 2 | 0 |
| `motion_server/handlers/command/motion.py` | 4 | 4 | 7 | 0 |
| `motion_server/handlers/command/registry.py` | 0 | 0 | 1 | 1 |
| `motion_server/handlers/command/trajectory.py` | 2 | 1 | 0 | 0 |
| `motion_server/handlers/parameter_access/ap.py` | 5 | 5 | 18 | 2 |
| `motion_server/handlers/parameter_access/ethercat.py` | 7 | 5 | 11 | 0 |
| `motion_server/handlers/parameter_access/iol.py` | 4 | 4 | 26 | 2 |
| `motion_server/handlers/status/axis_parameter_catalog.py` | 1 | 1 | 2 | 0 |
| `motion_server/handlers/status/io_ethercat_parameter_catalog.py` | 1 | 1 | 1 | 0 |
| `motion_server/handlers/status/io_input_read.py` | 1 | 1 | 0 | 0 |
| `motion_server/handlers/status/io_iol_parameter_catalog.py` | 1 | 1 | 5 | 0 |
| `motion_server/handlers/status/registry.py` | 1 | 1 | 1 | 1 |
| `motion_server/server.py` | 6 | 1 | 4 | 0 |
| `ros/bridge.py` | 4 | 1 | 1 | 0 |
| `ros/control_panel.py` | 6 | 1 | 0 | 0 |

## `except Exception` 위치

아래 85곳은 TD-005에서 각각 `허용`, `구체화`, `상위 경계로 이동` 중 하나로 판정해야 한다.

| 파일 | 줄 |
| --- | --- |
| `control_panel/axis_control_panel/client.py` | 121 |
| `control_panel/axis_control_panel/connection.py` | 50 |
| `control_panel/axis_control_panel/diagnosis.py` | 399 |
| `control_panel/io_control_panel/client.py` | 58 |
| `control_panel/io_control_panel/control_panel.py` | 526, 705, 715, 728, 772, 846, 859, 896, 909, 965, 1176 |
| `device/cmmt/profile.py` | 437, 446, 459, 486 |
| `device/virtual_servo_drive/servo_model.py` | 425 |
| `diagnostics/cmmt_sync_probe.py` | 95 |
| `diagnostics/dump_pdo_mapping.py` | 44, 68 |
| `diagnostics/pysoem_single_axis_smoke_test.py` | 118 |
| `ethercat/pysoem_master.py` | 120, 123, 161, 289, 423 |
| `ethercat/sdo_access.py` | 45, 82, 94, 109 |
| `motion_server/app/startup.py` | 245, 268, 302, 318, 334, 418, 452 |
| `motion_server/device_manager/axis_diagnostics.py` | 42 |
| `motion_server/handlers/command/axis_settings.py` | 116, 255, 371, 385, 449, 467 |
| `motion_server/handlers/command/axis_state.py` | 83, 170, 202, 242, 274, 292 |
| `motion_server/handlers/command/io_output_write.py` | 15 |
| `motion_server/handlers/command/jog.py` | 31, 45, 74, 91 |
| `motion_server/handlers/command/motion.py` | 93, 202, 225, 242 |
| `motion_server/handlers/command/trajectory.py` | 232 |
| `motion_server/handlers/parameter_access/ap.py` | 70, 125, 275, 429, 433 |
| `motion_server/handlers/parameter_access/ethercat.py` | 104, 152, 210, 256, 370 |
| `motion_server/handlers/parameter_access/iol.py` | 68, 120, 371, 522 |
| `motion_server/handlers/status/axis_parameter_catalog.py` | 27 |
| `motion_server/handlers/status/io_ethercat_parameter_catalog.py` | 17 |
| `motion_server/handlers/status/io_input_read.py` | 14 |
| `motion_server/handlers/status/io_iol_parameter_catalog.py` | 20 |
| `motion_server/handlers/status/registry.py` | 72 |
| `motion_server/server.py` | 346 |
| `ros/bridge.py` | 795 |
| `ros/control_panel.py` | 363 |

## `raise RuntimeError` 위치

아래 42곳은 typed error로 교체할지, programming invariant로 유지할지 판정해야 한다.

| 파일 | 줄 |
| --- | --- |
| `control_panel/io_control_panel/control_panel.py` | 704, 764, 952, 1182 |
| `device/cmmt/profile.py` | 195, 202, 260, 267, 306 |
| `device/cpx_ap_i_ec/ap_module_idents.py` | 54, 86 |
| `device/cpx_ap_i_ec/ap_parameter_access.py` | 36 |
| `device/cpx_ap_i_ec/pdo_configuration.py` | 73, 85, 114 |
| `diagnostics/cmmt_sync_probe.py` | 124, 135 |
| `ethercat/mock_master.py` | 43, 64 |
| `ethercat/pysoem_master.py` | 85, 116, 260, 320, 339, 512, 521, 544 |
| `ethercat/sdo_access.py` | 46, 83, 95, 110, 116 |
| `motion_server/config.py` | 615 |
| `motion_server/control/setpoint_output.py` | 127 |
| `motion_server/handlers/authority/registry.py` | 87 |
| `motion_server/handlers/command/axis_state.py` | 230 |
| `motion_server/handlers/command/registry.py` | 150 |
| `motion_server/handlers/parameter_access/ap.py` | 203, 276 |
| `motion_server/handlers/parameter_access/iol.py` | 199, 372 |
| `motion_server/handlers/status/registry.py` | 145 |

## 구체적 catch와 typed 발생 지점

아래 항목도 migration 대상이지만 broad catch와 동일하게 제거 대상으로 보지는 않는다. 현재 의미가
목표 error taxonomy와 일치하는지 확인한다.

| 종류 | 위치 |
| --- | --- |
| `except OSError` | Axis client 119, IO client 40/46, server 226, client transport 50, ROS bridge 793 |
| `except ValueError` | Axis connection 14, diagnosis 210/222/240, motion 263/301/324/352, motion settings 54/67/77/87, CPX config/layout 290/543, ROS bridge 240, ROS panel 957/1071/1143 |
| `except KeyError` | device factory 26, CMMT PDO/profile 187/259, CPX ESI/resolver/PDO 83/91/150/175/225/72 |
| 복합 catch | JSON/socket client boundary, parser conversion과 catalog loader에 18곳 |
| `raise ValueError` | configuration/parser/command validation 중심 165곳 |
| `raise KeyError` | OD/PDO/catalog lookup 8곳 |
| `raise PermissionError` | Virtual OD read-only write 1곳 |
| `raise ConnectionError` | Panel client disconnected 3곳 |
| `raise TimeoutError` | IO Panel response wait 1곳 |
| `raise OSError` | Axis/ROS socket closed 2곳 |

## Broad catch 1차 분류 규칙

| 판정 | 의미 | 예시 |
| --- | --- | --- |
| 허용 후보 | process, client, thread, callback 또는 cleanup의 최상위 안전 경계 | server client loop, PySOEM close cleanup |
| 구체화 대상 | 해당 계층이 예상 가능한 외부 실패를 알고 있음 | SDO transport, AP/IOL handshake, socket receive |
| 상위 이동 대상 | 중간 계층이 programming error까지 문자열 응답으로 숨김 | command/status handler의 반복 broad catch |
| 별도 정책 | 여러 축/장치 중 일부 실패를 수집하는 진단 경로 | startup readback, axis diagnostics |

최상위 경계의 broad catch도 무조건 유지하지 않는다. 허용할 경우 목적, log level, connection/runtime 상태와
programming error 처리 정책을 allowlist에 기록한다.

## 문서 관리 제안

1. 이 inventory는 TD-005 하위 조사 문서로 유지하고 migration 상태와 line inventory를 관리한다.
2. 설계 합의 후 `docs/api/`와 `docs/diagnostic/` 아래에 책임별 설계 문서를 생성하여 다음의 장기 계약만 기록한다.
   - error taxonomy와 계층별 변환 경계;
   - 안정적인 API failure code와 Fail response schema;
   - recoverable, connection 유지, runtime/degraded 정책;
   - logging 및 민감정보 비노출 정책;
   - broad catch allowlist 원칙.
3. `docs/motion_server_api_basic.md`에는 client가 의존하는 response schema와 code만 기록한다.
4. `docs/test_procedure.md`에는 오류 주입과 복구 판정 절차만 기록한다.
5. 코드 migration 진행률은 이 문서의 파일별 표 또는 별도 자동 검사 결과로 갱신한다.

## 다음 설계 단계

- 85개 broad catch를 각 행 단위로 `허용/구체화/상위 이동/별도 정책` 판정한다.
- 42개 generic RuntimeError를 target taxonomy에 매핑한다.
- 사용자 입력 `ValueError`와 programming invariant를 구분한다.
- 대표 수직 경로로 EtherCAT SDO read/write의 발생, 변환, API response, Panel 표시와 연결 유지를 설계한다.
- TD-018이 사용할 initialization/degraded 오류 계약을 분리한다.
