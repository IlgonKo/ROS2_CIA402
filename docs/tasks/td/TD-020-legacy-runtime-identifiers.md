# TD-020 Legacy 실행 식별자 Migration

## 배경 및 현재 구조

실행 환경에 과거 ROS2/CiA402 및 Axis Server 명칭을 포함한 식별자가 남아 있다.

- Docker image/container: `ros2_cia402_*`, `ros_cia402_motion_server`
- systemd unit: `ros-cia402-axis-server.service`
- environment: `ROS2_CIA402_AXIS_NAMES`, `ROS2_CIA402_INTERFACE`
- script cleanup과 log command가 legacy container/service 이름을 직접 사용한다.

## 문제와 위험

- 사용자 노출 명칭과 운영 식별자가 달라 설치 및 장애 대응이 혼란스럽다.
- 즉시 변경하면 실행 중인 container, 설치된 systemd unit, `.env`와 외부 automation이 중단될 수 있다.
- 신규/기존 이름을 무기한 함께 지원하면 fallback과 cleanup code가 기술 부채로 남는다.

## 확정 결정

- Motion Server image는 `motion-server:dev`, container는 `motion-server`를 사용한다.
- Axis/IO Panel 공용 image는 `motion-server-control-panel:dev`를 사용한다.
- Compose project는 `motion-server`, systemd unit은 `motion-server.service`를 사용한다.
- Motion Server environment namespace는 `MOTION_SERVER_*`를 사용한다.
- 아직 외부 배포되지 않았으므로 legacy alias, fallback 및 deprecation 기간 없이 직접 전환한다.
- `ROS2_CIA402_AXIS_NAMES`를 포함한 ROS 전용 image/container/environment는 RF-008에서 처리한다.

## 구현 범위

- Docker Compose, host script와 systemd installer를 신규 식별자로 직접 변경한다.
- 기존 systemd unit의 stop/disable/remove와 container 제거 절차를 문서화한다.
- 운영 코드와 script에서 TD-020 대상 legacy 식별자를 제거한다.
- legacy naming 검사에서 TD-020 allowlist를 제거한다.

## Migration

기존 Linux 설치에서 한 번만 다음 resource를 정리한 뒤 신규 service를 설치한다.

```bash
sudo systemctl disable --now ros-cia402-axis-server.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/ros-cia402-axis-server.service
sudo systemctl daemon-reload
docker rm -f ros_cia402_motion_server ros2_cia402_pysoem_host 2>/dev/null || true
sudo bash scripts/host/service.sh install
```

운영 script는 위 legacy 이름을 자동 탐색하거나 fallback하지 않는다.

## 범위 제외

- repository 및 filesystem 경로는 [TD-019](TD-019-project-path-migration.md)에서 처리한다.
- ROS package, topic, action과 robot identifier는 [RF-008](../rf/RF-008-ros-bridge-migration.md)에서 처리한다.
- 제품명이 확정된 `Axis Control Panel`은 변경하지 않는다.

## 검증 계획

- Compose render 결과와 host script가 신규 식별자만 사용하는지 검사한다.
- 기존 container/service의 일회성 제거 후 신규 service 설치를 검증한다.
- clean Windows/Linux 설치가 신규 식별자만 생성하는지 확인한다.
- 호환성 allowlist 외 legacy identifier를 검사한다.

## 완료 증거

### 자동 검증

- Compose render image가 `motion-server:dev`인지 확인한다.
- legacy naming 검사와 전체 unittest 265개가 통과한다.
- host 운영 script에 TD-020 대상 legacy runtime identifier가 없음을 확인한다.

### 실환경 검증

- 2026-08-26: Linux에서 TD-020 branch를 적용하고 신규 `motion-server.service`와
  `motion-server` container가 정상 기동됨을 확인했다.
- 신규 service/container 이름으로 Motion Server가 실제 구동되므로 Docker Compose와 systemd
  identifier 직접 전환이 완료됐다.
