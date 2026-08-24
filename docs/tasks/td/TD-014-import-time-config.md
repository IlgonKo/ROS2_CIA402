# TD-014 Import 시점 전역 설정 로딩

## 배경과 문제

TD-006에서 공통 file parser, loader와 Bus model을 도입했지만
`motion_server/config.py`는 import 시점에 configuration을 생성하고
`os.environ`을 변경한다. 여러 module이 이 파일의 전역 상수와 전역 CMMT profile을
직접 import하고, 일부 장치 코드는 환경 변수를 다시 검색한다.

이 구조에서는 import 자체가 실행 환경을 변경하고, 한 process 안에서 서로 다른
configuration을 격리하기 어렵다. `argparse.Namespace`, configuration, runtime과
변경 가능한 server state의 책임도 혼재한다.

## 목표

- 공통 loader 결과를 immutable typed `MotionServerConfig`로 변환한다.
- 설정 생성은 application 진입점에서 명시적으로 한 번 수행한다.
- `MotionServerApplication`을 composition root로 사용한다.
- 하위 component에는 Application 전체나 최상위 config가 아니라 실제 필요한 typed
  projection과 runtime dependency만 전달한다.
- module import는 filesystem과 process environment를 읽거나 변경하지 않는다.
- configuration, runtime과 변경 가능한 state를 분리한다.

## 설정 생성 및 우선순위

```text
장치 기본 설정
    < 프로젝트 공통 설정
    < 프로세스 환경 변수
    < CLI option
        ↓
ConfigurationModel
        ↓ typed 변환 및 validation
MotionServerConfig
```

`argparse.Namespace`는 입력 경계에서만 사용한다. CLI에서 지정하지 않은 항목은
`None`인 `CliOverrides`로 표현하며 최종 runtime 계약으로 전달하지 않는다.

```python
@dataclass(frozen=True)
class ConfigurationSource:
    project_root: Path
    project_filename: str
    device_filename: str

def build_motion_server_config(
    source: ConfigurationModel,
    cli: CliOverrides | None = None,
) -> MotionServerConfig:
    ...
```

## 최상위 데이터 모델

```python
@dataclass(frozen=True)
class MotionServerConfig:
    project_root: Path
    server: ServerConfig
    ethercat: EtherCATConfig
    motion: MotionConfig
    logging: LoggingConfig
    devices: tuple[BusDeviceConfig, ...]
```

모든 configuration model은 `frozen=True`로 정의한다.

### ServerConfig

```python
class ServerMode(str, Enum):
    BASIC = "basic"
    ADVANCED = "advanced"

@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    mode: ServerMode
    feedback_period: float
    axis_restart_disable_settle_time: float
```

`FeedbackConfig`는 단일 필드 class로 만들지 않는다. port는 `1..65535`, feedback
period는 양수, restart settle time은 0 이상이어야 한다.

### EtherCATConfig

```python
class BackendType(str, Enum):
    PYSOEM = "pysoem"
    MOCK = "mock"

@dataclass(frozen=True)
class CycleConfig:
    period: float
    spin_wait_time: float

@dataclass(frozen=True)
class DistributedClockConfig:
    enabled: bool
    sync0_shift_time_ns: int
    phase_lock: bool
    absolute_shift: bool
    phase_offset_ns: int
    phase_kp: float
    phase_ki: float
    phase_max_correction: float

@dataclass(frozen=True)
class EtherCATConfig:
    backend: BackendType
    interface: str
    sync_mode: int | None
    cycle: CycleConfig
    dc: DistributedClockConfig
```

`spin_wait_time`은 DC 전용 값이 아니라 일반 periodic/DC cycle의 deadline 대기
설정이므로 `CycleConfig`에 둔다. period는 양수이고
`0 <= spin_wait_time < period`여야 한다. DC 비활성 시 DC 세부값은 runtime에
적용하거나 startup log에 출력하지 않는다.

### MotionConfig

```python
class CspProfile(str, Enum):
    TRAPEZOID = "trapezoid"
    QUINTIC = "quintic"

@dataclass(frozen=True)
class MotionLimitConfig:
    max_velocity: float
    acceleration: float
    deceleration: float
    jerk: float
    pp_jerk: int

@dataclass(frozen=True)
class MotionConfig:
    default_limits: MotionLimitConfig
    initial_motion_mode: str
    csp_profile: CspProfile
```

default limit은 서버 측 safety/trajectory 초기 제한이며 장치 startup OD 기본값과
구분한다. velocity, acceleration, deceleration과 jerk는 양수여야 한다.

## LoggingConfig와 pre-logging

```python
@dataclass(frozen=True)
class LoggingConfig:
    command: CommandLogConfig
    status: StatusLogConfig
    cycle_stats: CycleStatsLogConfig
    trajectory: TrajectoryLogConfig
    velocity_anomaly: VelocityAnomalyLogConfig
    position_feedback_lag: PositionFeedbackLagLogConfig
    csp_command_step: CspCommandStepLogConfig
    pre_logging: PreLoggingConfig
```

각 하위 config는 기존 enabled, period 및 threshold를 책임별로 보유한다.

```python
@dataclass(frozen=True)
class CspCommandStepLogConfig:
    enabled: bool
    step_threshold: float
    error_threshold: float

@dataclass(frozen=True)
class PreLoggingConfig:
    enabled: bool
    length: int
```

CSP command step threshold는 motion 동작이 아니라 로그 발생만 결정하므로
`LoggingConfig`에 둔다.

기존 `tx_history`는 공통 pre-logging으로 대체한다.

- `MOTION_SERVER_TX_HISTORY_LENGTH`는 제거한다.
- `MOTION_SERVER_PRE_LOGGING_ENABLED`, `MOTION_SERVER_PRE_LOGGING_LENGTH`를 사용한다.
- pre-logging이 꺼져 있으면 history buffer를 생성하거나 cycle snapshot을 기록하지
  않는다.
- 켜져 있으면 최근 상태를 length만큼 저장하고 command log 이외의 log event에
  직전 상태를 함께 제공한다.
- command log는 외부 요청 기록이므로 pre-logging 대상에서 제외한다.
- enabled일 때 length는 1 이상이어야 한다.

`PreLogSnapshot`과 buffer는 공개 configuration이 아니라 logging runtime 내부
모델이다. snapshot은 cycle sequence/time, target/actual/command position과 velocity,
mode, statusword, WKC와 DC/tx timing 등 공통 분석 항목을 보관한다. cycle 성능을 위해
내부 저장은 가벼운 tuple 구조를 사용할 수 있다.

전역 `status_log()`는 제거하고 각 module의 표준 logger를 application 시작 시
`LoggingConfig`로 구성한다. 공통 `RuntimeLogger`가 event와 pre-history 결합을
책임진다.

## Bus 및 장치 instance 설정

```python
@dataclass(frozen=True)
class BusDeviceConfig:
    slave_index: int
    role: DeviceRole
    profile_name: str
    logical_id: str | None
    device: DeviceConfig
```

설정의 숫자 label은 설명용이므로 최종 model의 `configured_index`는 제거한다.
runtime 식별에는 Bus entry 순서로 계산한 `slave_index`만 사용한다.

가상/실제 장치용 config를 분리하지 않는다. 동일한 `BusDeviceConfig`를
PySOEMMaster와 MockMaster가 소비한다.

```text
BusDeviceConfig
    ├─ PySOEMMaster → 실제 EtherCAT slave
    └─ MockMaster   → DeviceProfile → OD Model → MockSlave
```

`VirtualServoConfig`, `MockConfig`, `MockBackendConfig`와 simulation option은 만들지
않는다. `MOCK_AXIS_TYPES`, `MOCK_AXIS_USER_UNITS`는 제거하고 가상축 OD/unit도 동일한
device profile 및 instance config로 결정한다.

### CMMT

```python
class CspInterpolationMode(IntEnum):
    CSP = 1
    CSP_V = 4
    CSP_T = 5
    CSP_VT = 6

@dataclass(frozen=True)
class CmmtDeviceConfig:
    profile_name: str
    axis_index: int
    pdo_configuration: str
    csp_interpolation_mode: CspInterpolationMode
    csp_velocity_offset: bool
    startup_parameters: tuple[OdStartupParameter, ...]
```

CSP interpolation mode와 velocity offset은 서버 trajectory 알고리즘이 아니라 CMMT
장치 동작이므로 `MotionConfig`에 두지 않는다. PDO override 우선순위도 typed config
생성 시 해결하여 장치 코드가 환경 변수 이름을 알지 않게 한다. startup parameter는
현재 사용 범위만 projection하고 정책 자체는 TD-023에서 변경한다.

### CPX-AP-I

```python
@dataclass(frozen=True)
class CpxApIEcDeviceConfig:
    profile_name: str
    logical_id: str
    modules: tuple[IoModuleConfig, ...]
    io_link_ports: tuple[IoLinkPortConfig, ...]
```

`MOTION_SERVER_IO_<logical_id>_MODULES`와 IOL port 설정은 typed config 생성 시 한 번
해석한다. CPX 장치 코드는 `os.environ.items()`를 검색하지 않는다.

DeviceProfile은 mode, mask, capability, PDO/OD schema 같은 장치 종류의 고정 계약이고,
DeviceConfig는 해당 Bus instance의 PDO 선택, startup 값과 module 배치다. 전역
`DEVICE_PROFILE = get_device_profile("cmmt")`는 제거하고 instance의 profile name으로
구체 profile을 생성한다.

## Derived velocity 제거

모든 축에서 `actual_velocity`가 필수 TxPDO이므로 위치 차분 기반 derived velocity는
제거한다.

- `MOTION_SERVER_DERIVED_VELOCITY_ALPHA`, CLI option 제거
- derived velocity 계산 함수와 state 필드 제거
- Axis/Axes status의 `derived_velocity`, `derived_velocities` 제거
- Axis Panel mapping 및 startup/status log의 관련 값 제거
- actual/command velocity는 유지

미배포 프로젝트이므로 제거된 환경 변수와 API 필드의 backward compatibility는
제공하지 않는다.

## Application 및 dependency 전달 경계

```python
class MotionServerApplication:
    def __init__(self, config: MotionServerConfig):
        self._config = config

    def run(self):
        ...
```

Application은 logging, socket, device profile/instance, master, DeviceManager,
MotionController와 AxisRuntime을 조립하고 reset/reconnect 시 재생성하는 composition
root다.

하위 component에는 Application 또는 `MotionServerConfig` 전체를 전달하지 않는다.
실제 필요한 typed projection과 runtime dependency만 전달한다.

```text
TCP server                 ← ServerConfig
PySOEMMaster / MockMaster  ← EtherCATConfig + BusDeviceConfig[]
MotionController           ← MotionConfig + cycle period
CMMT instance              ← CmmtDeviceConfig
CPX instance               ← CpxApIEcDeviceConfig
RuntimeLogger              ← LoggingConfig
```

Application 전체를 전달하거나 전역 current application을 두는 service-locator 방식은
금지한다. 요청 경계에서 공통 dependency가 필요하면 책임이 제한된 RequestContext나
객체형 router를 사용하되 Application 전체를 넣지 않는다.

## Configuration, runtime과 state

- Configuration: port, cycle, Bus/device와 logging처럼 실행 중 불변인 입력
- Runtime: master, DeviceManager, MotionController, AxisRuntime, RuntimeLogger
- State: 위치, motion/trajectory/homing, authority, initialization과 현재 limit

`state["config"]`처럼 최상위 config를 변경 가능한 state에 넣지 않는다. pre-log
history buffer는 configuration이 아니라 RuntimeLogger가 소유하는 runtime data다.

## 실행 entrypoint

TD-006의 전역 `active_configuration()`은 제거한다. 일반 실행과 Windows package는
파일 위치만 다른 `ConfigurationSource`를 `main()`에 전달하고 같은 경로에서 typed
config를 한 번 생성한다.

```text
source:  .env / device .env
Windows: config.txt / device config.txt
```

platform DLL path 준비는 configuration loading과 별도의 명시적인 bootstrap 책임으로
유지한다.

## 포함 범위

- immutable typed model, validation과 CLI override
- `MotionServerApplication` composition root와 명시적 dependency injection
- import-time file/environment side effect 및 전역 설정 상수 제거
- 전역 CMMT profile과 장치 코드의 환경 변수 직접 접근 제거
- CSP interpolation mode Enum과 instance device config
- 표준 logging, 공통 pre-logging 및 disabled 시 history 미기록
- derived velocity와 configured index 제거
- Windows active configuration 제거
- import isolation 및 동일 process 복수 configuration 격리 테스트

## 단계별 구현 계획

한 번에 전체 경로를 전환하지 않고 각 단계가 독립적으로 검증 가능한 순서로 진행한다.

### S01 Typed model과 builder

- immutable configuration dataclass와 Enum을 정의한다.
- TD-006 `ConfigurationModel` 및 CLI override를 typed model로 변환한다.
- 범위, Enum, cycle/DC 조합과 device instance validation을 추가한다.
- 기존 runtime은 아직 기존 config/args 경로를 사용한다.

완료 기록:

- 상태: `complete`
- 변경: `configuration/models.py`, `configuration/builder.py`,
  `configuration/loader.py`, `configuration/__init__.py`
- 검증: immutable model, CMMT/CPX Bus instance projection, CSP interpolation Enum,
  cycle 범위, PySOEM interface와 pre-logging validation 테스트 5개를 추가했다.
- 결과: 전체 unittest 160개와 source compile 검사가 통과했다.
- 기존 runtime 연결은 변경하지 않았으며 다음 단계는 S02다.

### S02 Application composition root

- 명시적인 `ConfigurationSource`와 `MotionServerApplication`을 도입한다.
- 일반/Windows entrypoint가 source를 전달하고 typed config를 한 번 생성하게 한다.
- reset/reconnect lifecycle을 Application 경계로 이동한다.

완료 기록:

- 상태: `complete`
- 변경: `motion_server/application.py`, `motion_server/__main__.py`,
  `motion_server/server.py`, Windows packaging entrypoint와 runtime bootstrap
- 일반/Windows entrypoint가 명시적인 `ConfigurationSource`를 사용하고
  `MotionServerApplication`이 raw/typed configuration을 한 번 생성한다.
- 기존 runtime은 S03 전까지 내부 Namespace adapter로 유지하며 Application 전체를
  하위 runner에 전달하지 않는다.
- 서로 다른 source 두 개의 application/config 격리와 runner 전달 경계 테스트 2개를
  추가했다.
- 결과: 전체 unittest 162개와 source compile 검사가 통과했다.
- 다음 단계는 Namespace adapter를 typed projection으로 대체하는 S03이다.

### S03 Server·EtherCAT·Motion projection 주입

- server loop, master와 MotionController가 필요한 typed projection을 받게 한다.
- `argparse.Namespace`의 runtime 전달과 관련 전역 상수 import를 제거한다.

완료 기록:

- 상태: `complete`
- 변경: `configuration/builder.py`, `motion_server/application.py`,
  `motion_server/server.py`, `motion_server/app/startup.py`,
  `motion_server/app/state.py`, `motion_server/app/client_transport.py`
- CLI `Namespace`는 `CliOverrides` 변환 경계 안으로 제한하고 server runtime에는
  immutable `MotionServerConfig`만 전달한다.
- TCP loop에는 `ServerConfig`, runtime factory에는 `EtherCATConfig`, `MotionConfig`,
  `LoggingConfig`, `BusDeviceConfig[]`, state factory에는 server/EtherCAT/motion
  projection만 전달하여 하위 component의 최상위 config 의존을 제거했다.
- feedback period, socket, cycle/DC, motion limit/CSP 설정은 typed projection에서
  소비한다. logging 전역 설정은 S05 전환 범위로 유지했다.
- startup log에서 장치 상태를 제거하고 DC 비활성 시 DC 세부 설정을 출력하지 않게
  했다.
- 결과: 전체 unittest 162개, source compile과 diff 검사가 통과했다.
- 다음 단계는 장치별 instance config를 실제/mock backend에 주입하는 S04다.

### S04 Device instance config 주입

- Bus entry를 CMMT/CPX instance별 typed config와 결합한다.
- CMMT PDO/CSP mode와 CPX module/IOL 설정의 환경 변수 직접 접근을 제거한다.
- mock과 PySOEM이 동일한 device instance config를 소비하게 한다.

완료 기록:

- 상태: `complete`
- 변경: `device/__init__.py`, CMMT profile/PDO configuration, CPX profile/I/O
  configuration, `motion_server/app/startup.py`
- 공통 profile factory가 `BusDeviceConfig.device`를 profile constructor에 전달하며,
  CMMT profile은 `CmmtDeviceConfig.pdo_configuration`, CPX profile은
  `CpxApIEcDeviceConfig.modules/io_link_ports`만 소비한다.
- CMMT PDO와 CPX module/IOL을 장치 코드가 `os.environ`에서 다시 읽는 경로를
  제거했다. CMMT profile 기본 생성은 고정 profile default만 사용하고 CPX profile은
  typed instance config를 필수로 요구한다.
- mock virtual servo와 PySOEM master는 동일 factory에서 생성된 CMMT profile을
  사용하므로 backend에 관계없이 같은 PDO/OD instance 설정을 소비한다.
- typed CMMT 두 축의 서로 다른 PDO 선택과 CPX module projection을 검증하는 profile
  테스트를 추가했다.
- 결과: 전체 unittest 163개, source compile, 장치 환경 변수 정적 참조와 diff 검사가
  통과했다.
- 다음 단계는 logging 전역과 tx history를 `RuntimeLogger`/pre-logging으로 전환하는
  S05다.

### S05 Logging과 pre-logging

- 표준 logger 및 `RuntimeLogger`로 전환하고 전역 `status_log()`를 제거한다.
- optional pre-history buffer와 command 제외 계약을 구현한다.
- pre-logging 비활성 시 buffer 생성과 cycle snapshot 기록을 하지 않는다.

완료 기록:

- 상태: `complete`
- 변경: `motion_server/runtime_logging.py`, runtime/startup/server/client transport,
  cycle/trajectory logging, API router와 status 변경 handler
- `RuntimeLogger`가 `LoggingConfig`와 optional bounded history를 소유하고
  `AxisRuntime`에 주입된다. 변경 가능한 server state의 `tx_history`와 전역
  `status_log()` 및 runtime logging 전역 상수를 제거했다.
- pre-logging 비활성 시 deque를 만들지 않고 cycle snapshot 기록을 즉시 건너뛴다.
  활성 시 target/actual/command position과 velocity, mode, statusword, WKC 및 tx/DC
  timing을 설정 length만큼 보관한다.
- status, cycle stats, trajectory, velocity/position/CSP anomaly event에는 pre-history를
  첨부하고 외부 요청인 command log에는 첨부하지 않는다.
- `.env.example`에 `MOTION_SERVER_PRE_LOGGING_ENABLED/LENGTH`를 추가하고 기존
  `MOTION_SERVER_TX_HISTORY_LENGTH` 경로는 제거했다.
- pre-logging on/off, bounded length와 command 제외 테스트 3개를 추가했다.
- 결과: 전체 unittest 166개, source compile, legacy logging 참조와 diff 검사가
  통과했다.
- 다음 단계는 derived velocity와 legacy mock/configured index 설정을 제거하는 S06다.

### S06 중복·legacy 설정 제거

- derived velocity 계산, state, API, UI와 설정을 제거한다.
- `configured_index`, `MOCK_AXIS_TYPES`, `MOCK_AXIS_USER_UNITS`를 제거한다.
- 제거 항목의 정적 참조 검사를 추가한다.

완료 기록:

- 상태: `complete`
- derived velocity 계산 module, cycle update, state와 Axis/Axes status field 및 Control
  Panel merge mapping을 제거했다. actual velocity는 필수 TxPDO `0x606C`만 사용한다.
- `MOTION_SERVER_DERIVED_VELOCITY_ALPHA` 환경 변수/CLI/shell/문서 설정을 제거했다.
- `BusDevice.configured_index`를 제거하고 numeric label은 parsing에만 사용하며 최종
  model에는 실제 순서의 `slave_index`만 보존한다.
- mock axis type/user-unit parser, CLI와 virtual-servo 전용 환경 파일을 제거했다.
  가상축 OD/unit은 실제축과 동일하게 CMMT device profile에서 결정한다.
- 제거된 runtime/configuration/API/UI identifier가 다시 추가되지 않도록 정적 검사와
  `BusDevice` field 계약 테스트 2개를 추가했다.
- 결과: 전체 unittest 168개, source compile, CLI help, Linux shell 문법과 diff 검사가
  통과했다.
- 다음 단계는 import-time loader/environment mutation, active configuration과 전역
  profile을 제거하는 S07이다.

### S07 Import isolation 마무리

- import-time loader, environment mutation, active configuration과 전역 profile을 제거한다.
- 동일 process의 복수 config 격리, Windows/Linux smoke test와 전체 회귀를 수행한다.

완료 기록:

- 상태: `complete`
- import 시 loader 실행, `os.environ` overlay와 전역 profile/PDO 계약을 혼합하던
  `motion_server/config.py`를 제거했다.
- CLI는 명시한 값만 `CliOverrides`로 만드는 `configuration/cli.py`, PDO field 검증은
  `motion_server/control/pdo_contract.py`로 분리했다.
- `active_configuration/set_active_configuration`과 Windows configuration 환경 변수
  backfill을 제거했다. 일반 `.env`와 Windows `config.txt`는 각각
  `ConfigurationSource`만 다르고 동일 Application 경계에서 한 번 생성된다.
- 모든 Axis 제어·startup·parameter access는 전역 CMMT profile이 아니라 runtime
  slave의 instance device profile을 사용한다.
- Linux/Docker 시작 명령을 직접 `server.py` 실행에서 `python -m motion_server`로
  통일했다.
- module reload가 configuration file을 읽거나 process environment를 변경하지 않는
  검사, legacy global symbol 정적 검사와 명시적 CLI override 테스트 3개를 추가했다.
- 결과: 전체 unittest 171개, source compile, Linux CLI/shell과 Windows source smoke,
  import isolation 및 diff 검사가 통과했다.

각 단계 완료 시 변경 파일, 테스트 결과와 다음 단계를 이 문서에 기록한다.

## 제외 범위

- ROS configuration 연동: RF-008
- Control Panel 대형 구조 개선: TD-007
- DeviceManager 책임 재설계: TD-008
- simulation engine option
- legacy identifier 일반 변경: TD-020
- startup OD 정책 변경: TD-023
- platform DLL bootstrap

## 검증 계획

- project module import 전후 filesystem 접근과 process environment 불변을 검사한다.
- 서로 다른 configuration 두 개를 같은 process에서 생성해 값과 runtime 격리를
  검증한다.
- invalid enum, 범위, cycle/DC 조합과 장치 instance 설정을 검증한다.
- mock과 PySOEM factory가 동일한 BusDeviceConfig projection을 받는지 검증한다.
- pre-logging on/off, length와 command 제외 계약을 검증한다.
- derived velocity 및 제거된 전역 config/API 참조가 남지 않았는지 정적으로 검사한다.
- Windows package와 Linux startup entrypoint를 smoke test한다.

## 완료 증거

- 최종 model: immutable `MotionServerConfig`와 server, EtherCAT/cycle/DC, motion,
  logging 및 Bus device instance projection
- dependency: Application → typed projection → Runtime/DeviceProfile이며 하위 component는
  Application과 최상위 config를 받지 않는다.
- 제거: import-time `motion_server/config.py`, active configuration, environment backfill,
  전역 CMMT profile, state `tx_history`, derived velocity, configured index와 mock 전용
  axis type/unit 설정
- 검증: unittest 171개, import reload/file-access/environment 불변, 복수 config 격리,
  Windows `config.txt`, Linux `python -m motion_server --help`, shell/source compile 통과
