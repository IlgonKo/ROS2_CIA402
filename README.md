# ROS2 CiA402 EtherCAT Sandbox

This project has two execution paths.

## Mock path

The mock path uses the same Axis Server TCP API as the real drive path, but
selects the virtual CiA402 servo backend.

```text
ROS Control Panel
  -> ros/bridge.py
  -> TCP JSON
  -> Axis Server backend=mock
  -> MockMaster / MockSlave
  -> VirtualCiA402Servo
```

## Real Festo CMMT path

The real-drive path keeps ROS2 in Docker and runs PySOEM on the PC that is
physically connected to the EtherCAT device.

```text
Docker ROS2 GUI / command nodes
  -> ros/bridge.py
  -> TCP JSON
  -> Axis Server on the EtherCAT host PC
  -> Festo CMMT-AS
```

Use the scripts under `scripts/host`, `scripts/ros`, and `scripts/windows`
for the current recommended entry points.

## Recommended real-drive startup

Dockerized Ubuntu EtherCAT host PC:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker "$USER"
# Log out and back in after adding the docker group.

bash scripts/host/adapters.sh
bash scripts/host/start.sh
```

Runtime settings are stored in `.env`:

```text
PYSOEM_INTERFACE=enp1s0
AXIS_SERVER_BACKEND=pysoem
PYSOEM_AXIS_COUNT=1
PYSOEM_AXIS_SERVER_PORT=15000
PYSOEM_CYCLE_TIME=0.01
PYSOEM_CSP_COUNTS_PER_UNIT=1.0
PYSOEM_DERIVED_VELOCITY_ALPHA=0.2
PYSOEM_MOTION_MODE=pp
PYSOEM_START_CONTROL_PANEL=1
```

For a mock backend, use:

```text
AXIS_SERVER_BACKEND=mock
PYSOEM_AXIS_COUNT=3
```

For multiple same-profile CiA402 slaves, edit `.env` once:

```bash
nano .env
bash scripts/host/start.sh
```

Or use the start helper:

```bash
bash scripts/host/start.sh
docker logs -f ros_cia402_axis_server
```

The Dockerized PySOEM server uses host networking and privileged raw Ethernet
access so the container can send EtherCAT frames through the Ubuntu PC NIC.
Its Docker assets live under `docker/axis_server/`.

Linux local Axis Server control and visualization:

```bash
bash scripts/host/panel.sh
```

By default, `PYSOEM_START_CONTROL_PANEL=1` starts the Axis Server Control Panel
automatically when the container starts. The manual script above can be used to
open another panel later. The panel runs inside the `ros_cia402_axis_server`
container, connects directly to the local Axis Server TCP port from `.env`, and
does not require ROS2. It can send target positions, apply profile
velocity/accel/decel limits, send alarm ack, run two-point repeat motion, and
show position/velocity traces. It also provides manual CiA402 controlword
commands after the server's automatic startup sequence has enabled the drive.

Motion modes:

```text
pp   Profile Position, default and recommended for Windows/Linux non-RT hosts
csp  Cyclic Synchronous Position, available for smoother target streaming
csv  Cyclic Synchronous Velocity, TCP protocol only for now
```

The local Control Panel allows PP/CSP selection. CSV is implemented in the Axis
Server protocol but disabled in the Control Panel until a velocity command UI is
added.

PP profile velocity objects can be interpreted by the drive in configured user
units such as mm/s, while CSP target positions are streamed in position counts.
Use `PYSOEM_CSP_COUNTS_PER_UNIT` to align CSP speed with PP speed. Example:

```text
PYSOEM_CSP_COUNTS_PER_UNIT=1000.0
```

With that setting, a panel Max Velocity of `1000` becomes `1,000,000 count/s`
inside the CSP trajectory generator.

For CSP testing, reduce the process-data cycle time in `.env` if the generated
target stream is too coarse:

```text
PYSOEM_CYCLE_TIME=0.002
```

The Axis Server log prints `CSP_CV=...` and `CSP_CP=...` for each axis so the
generated CSP command velocity/position can be compared with the drive's actual
velocity/position. Some drives do not expose CiA402 object `0x60C2`
interpolation time period; the Axis Server treats that as a supported fallback
and continues without writing it.

The drive's `0x606C` actual velocity can use vendor-specific scaling. The Axis
Server also logs and publishes `DV=...`, a derived velocity calculated from
actual position delta over time in position-counts per second. The local panel
shows and traces the drive's actual velocity feedback.

`PYSOEM_DERIVED_VELOCITY_ALPHA` filters the derived velocity display. Smaller
values are smoother; `1.0` disables filtering.

The automatic panel needs an active Linux desktop/X11 session. If the boot
service starts before a user logs in, the Axis Server still starts, but the GUI
window may not appear until started manually.

To start the Dockerized PySOEM server automatically when the Ubuntu PC boots:

```bash
sudo bash scripts/host/service.sh install
systemctl status ros-cia402-axis-server.service
docker logs -f ros_cia402_axis_server
```

After this installation, Ubuntu boot starts Docker, systemd runs
`ros-cia402-axis-server.service`, and the service starts the
`ros_cia402_axis_server` container. The container command starts
`axis_server/server.py` automatically.

To change the EtherCAT NIC or axis count later, edit `.env` and restart:

```bash
sudo systemctl restart ros-cia402-axis-server.service
```

For a multi-axis boot service:

```bash
nano .env
sudo systemctl restart ros-cia402-axis-server.service
```

To remove the boot service:

```bash
sudo bash scripts/host/service.sh uninstall
```

If the boot service fails, check the systemd and container logs:

```bash
systemctl status ros-cia402-axis-server.service --no-pager
journalctl -xeu ros-cia402-axis-server.service --no-pager
docker ps -a
docker logs ros_cia402_axis_server
```

If an old container name is blocking startup:

```bash
docker rm -f ros_cia402_axis_server
sudo systemctl restart ros-cia402-axis-server.service
```

If Docker cannot resolve Docker Hub, configure Docker DNS and restart Docker:

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "dns": ["8.8.8.8", "1.1.1.1"]
}
EOF
sudo systemctl restart docker
docker pull ubuntu:24.04
```

Windows PowerShell, only when the EtherCAT device is connected to Windows:

```powershell
.\scripts\windows\axis_server.ps1
```

ROS Docker bash:

```bash
docker compose -f docker/ros/compose.yaml up -d --build ros2_dev
docker exec -it ros2_cia402_dev bash
bash scripts/ros/bridge.sh
bash scripts/ros/panel.sh
```

## Sync to Ubuntu EtherCAT host

From Windows PowerShell, push this project to the Ubuntu PC:

```powershell
.\scripts\windows\sync_virtual_ethercat_to_ubuntu.ps1 -User ubuntu
```

To keep syncing while editing:

```powershell
.\scripts\windows\sync_virtual_ethercat_to_ubuntu.ps1 -User ubuntu -Watch
```

Replace `ubuntu` with the Ubuntu login user. The default target is
`ubuntu@192.168.0.12:/home/festo/Documents/ROS_CIA402/virtual_ethercat`.

If sync fails because Docker created root-owned `__pycache__` files on Ubuntu,
fix ownership once:

```bash
sudo systemctl stop ros-cia402-axis-server.service
sudo chown -R festo:festo /home/festo/Documents/ROS_CIA402/virtual_ethercat
```

The PySOEM Docker image runs Python with bytecode generation disabled so new
`__pycache__` files are not created in the bind-mounted project folder.

## Folder guide

```text
axis_server/         Axis Server TCP API, backend selection, local panel, and host entrypoint
diagnostics/         Adapter listing, PDO dump, and smoke-test utilities
docker/axis_server/  Axis Server Dockerfile and compose file
docker/ros/          ROS Dockerfile and compose file
scripts/host/        Ubuntu EtherCAT host commands: start, stop, panel, service, adapters
scripts/ros/         ROS container launch helpers
scripts/windows/     Windows sync helper and optional direct Axis Server launcher
ros/                 ROS bridge/control panel and trace display
ethercat/            Mock/PySOEM EtherCAT transport, PDO, and process-data code
cia402/              Virtual CiA402 drive model
```
