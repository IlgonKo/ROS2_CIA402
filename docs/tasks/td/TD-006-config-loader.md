# TD-006 설정 로더와 Bus Parser 중복

## 배경 및 현재 구조

기존에는 공통 `config_file.py` 외에 ROS runtime과 packaging이 자체 설정 및 Bus
해석을 수행했다. 장치 설정을 선택하는 로직도 실행 경로별로 중복되어 있었다.

## 문제와 위험

continuation, indexed entry, explicit `axis:`/`io:` 형식이 실행 경로에 따라 다르게 해석될 수 있다.

## 관련 위치

- `configuration/file_parser.py`
- `configuration/bus.py`
- `configuration/loader.py`
- `motion_server/config.py`
- `ros/axis_runtime_config.py`
- `packaging/windows_runtime.py`
- Control Panel별 `config.py`

## 목표 구조 및 구현 범위

- file parsing, environment overlay, validation과 typed bus model의 책임을 분리한다.
- Motion Server와 packaging 실행 경로가 공통 parser와 bus model을 사용한다.
- client별 설정은 공통 model 위의 명시적인 projection으로 제한한다.

## 확정 구조

```text
프로젝트 공통 설정
        ↓
공통 file parser
        ↓
공통 Bus parser → BusConfig / BusDevice
        ↓
Bus에 포함된 profile의 장치 설정만 공통 parser로 추가 로드
        ↓
장치 기본값 < 프로젝트 공통 설정 < 프로세스 환경 변수
        ↓
ConfigurationModel
        ├─ Motion Server
        ├─ Windows packaging runtime
        └─ client별 projection
```

- 장치별 설정 파일은 유지하지만 장치별 parser는 만들지 않는다.
- numeric index는 `configured_index`, 실제 Bus 순서는 `slave_index`로 구분한다.
- `axis`/`drive`와 `io`/`device`/`slave` 별칭은 parser 경계에서 각각
  `DeviceRole.AXIS`, `DeviceRole.IO`로 정규화한다.

### ROS 처리 경계

- ROS가 프로젝트 `.env`와 `MOTION_SERVER_BUS`를 독자적으로 읽고 해석하는
  로직은 먼저 제거한다.
- 공통 데이터 모델 연동 전까지 ROS bridge의 기존 import contract를 유지하기
  위한 임시 기본 축 이름만 둔다. 이 값은 Motion Server 구성을 나타내는 설정
  모델이 아니다.
- ROS가 공통 데이터 모델을 사용하는 작업과 ROS 전용 설정 파일 도입은 후속
  작업으로 분리한다.

## 검증 계획

- 동일 fixture를 Motion Server와 packaging entrypoint에 적용해 결과가 같은지
  검증한다.
- continuation, indexed entry, axis/I/O 혼합 bus와 잘못된 설정을 테스트한다.

## 완료 증거

- 제거한 parser: ROS `load_env_file()`/`axis_count_from_bus()`, Windows runtime의
  Bus/profile parser와 `strip_index_label()`, `motion_server.config.parse_bus_config()`,
  CMMT sync probe의 독자적인 축 count parser, Linux/PowerShell 실행 스크립트의
  `.env` 및 Bus parser.
- 기존 `config_file.py`는 제거하고 모든 소비자가 `configuration.file_parser`를
  사용하도록 전환했다.
- Motion Server와 Windows runtime은 공통 `ConfigurationModel` 및 `BusConfig`를
  사용한다. Windows bootstrap이 만든 active model을 Motion Server import 경계로
  전달하여 같은 프로세스에서 공통 설정을 다시 파싱하지 않는다.
- Linux Compose와 Windows PowerShell entrypoint는 `python -m configuration`의
  env/JSON projection을 소비하며 설정 문법을 다시 구현하지 않는다.
- fixture 테스트에서 continuation, indexed entry, axis/I/O 혼합 Bus, 잘못된
  role/profile, 설정 우선순위, 사용하지 않는 장치 설정 미로딩과 Windows 경로
  parity를 검증한다.
- 설정 model 전용 테스트 6개와 전체 unittest 155개 및 source compile 검사가
  통과했다.
