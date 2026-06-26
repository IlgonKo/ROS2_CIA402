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

`scripts/host/start.sh` starts the existing Axis Server image. Rebuild the
server image only after changing the Axis Server Dockerfile or dependencies:

```bash
bash scripts/host/start.sh --build
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
```

On Linux, `.env` is a hidden file. In the Files app, press `Ctrl+H` to show it,
or check it from a terminal:

```bash
ls -la
cat .env
```

The host scripts pass this file explicitly to Docker Compose with
`--env-file .env`. When `scripts/host/start.sh` runs, it prints the backend,
axis count, and interface values it read from `.env`.

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

The Dockerized Axis Server uses host networking and privileged raw Ethernet
access so the container can send EtherCAT frames through the Ubuntu PC NIC.
The Axis Server image is intentionally separate from the GUI image. The server
image contains PySOEM and EtherCAT access only; the panel image contains Tk GUI
dependencies and connects to the server through TCP.

Linux local Axis Server control and visualization:

```bash
bash scripts/host/panel.sh
```

The panel runs in a separate `axis_panel` container, connects directly to the
local Axis Server TCP port from `.env`, and does not require ROS2. It can send
target positions, apply profile velocity/accel/decel limits, send alarm ack,
run two-point repeat motion, and show position/velocity traces. It also
provides manual CiA402 controlword commands after the server's automatic
startup sequence has enabled the drive.

The panel container is intentionally short-lived: closing the GUI exits and
removes the container. The image is not rebuilt every time. Rebuild it only
after changing the panel Dockerfile or dependencies:

```bash
bash scripts/host/panel.sh --build
```

The Axis Server accepts multiple TCP clients. Command messages require command
authority: a client must request authority from the panel before sending motion
commands, manual controlwords, limit changes, mode changes, jogs, or alarm ack.
If another client already holds authority, the server rejects the request and
reports the current owner. Feedback remains broadcast to all connected clients.

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

The panel needs an active Linux desktop/X11 session. The boot service starts
only the Axis Server container; open the panel manually with
`bash scripts/host/panel.sh` after logging into the desktop.

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
bash scripts/ros/start.sh --build
bash scripts/ros/control_panel.sh --build
```

After the image exists, normal startup does not rebuild it:

```bash
bash scripts/ros/start.sh
bash scripts/ros/control_panel.sh
```

`ros_bridge` runs in the background as an Axis Server TCP client.
`ros_control_panel` runs only while the GUI is open. They use separate Docker
images: the Bridge image has only ROS messaging/runtime dependencies, while the
ROS Control Panel image also contains Tk/X11 GUI dependencies. The compose
services are separated so the bridge can keep running when the panel is closed.

MoveIt is prepared as a third ROS image so planning dependencies do not bloat
the Bridge or Control Panel images:

```bash
bash scripts/ros/moveit.sh --build
bash scripts/ros/moveit.sh --check
```

Build the local MoveIt test description package before opening the Setup
Assistant. This installs `ros2_cia402_cartesian_description` into
`install/moveit`, so the Setup Assistant can resolve the package through the
ament index:

```bash
bash scripts/ros/moveit.sh --build-workspace
```

For the first 3-axis Cartesian test, load this xacro in the Setup Assistant:

```text
/workspace/ros_moveit/ros2_cia402_cartesian_description/urdf/cartesian_3axis.urdf.xacro
```

Then open the MoveIt Setup Assistant:

```bash
bash scripts/ros/moveit.sh --setup-assistant
```

The model uses prismatic joints named `X`, `Y`, and `Z`, matching the default
Bridge joint names. To display the description package before using the Setup
Assistant:

```bash
bash scripts/ros/moveit.sh --display-cartesian
```

If the Setup Assistant crashes while loading RViz preview in Windows Docker/X11,
use the hand-written MoveIt config package instead:

```bash
bash scripts/ros/moveit.sh --build-workspace
bash scripts/ros/moveit.sh --move-group
```

The MoveIt container uses the same compose project and `ROS_DOMAIN_ID` as the
Bridge and ROS Control Panel. The ROS Bridge provides a MoveIt-compatible
`FollowJointTrajectory` action server:

```text
/cia402_joint_trajectory_controller/follow_joint_trajectory
```

Action completion is controlled by `.env`:

```text
CIA402_ACTION_GOAL_TOLERANCE=0.01
CIA402_ACTION_RESULT_TIMEOUT=0.0
```

`CIA402_ACTION_RESULT_TIMEOUT=0.0` means the Bridge waits until all axes are
inside tolerance or the goal is canceled. Increase
`CIA402_ACTION_GOAL_TOLERANCE` if the drive feedback unit is coarse or if small
settling errors should still count as reached.

Rebuild the Bridge image after action-server changes:

```bash
bash scripts/ros/start.sh --build
```

Then start `move_group` with the hand-written config:

```bash
bash scripts/ros/moveit.sh --build-workspace
bash scripts/ros/moveit.sh --move-group
```

The ROS Bridge Axis Server endpoint is configured in `.env`:

```text
CIA402_AXIS_SERVER_HOST=192.168.0.12
CIA402_AXIS_SERVER_PORT=15000
CIA402_AUTO_REQUEST_AUTHORITY=1
```

Use `192.168.0.12` when the Axis Server runs on the Ubuntu EtherCAT host from a
Windows ROS container. Use `127.0.0.1` when ROS and Axis Server containers run
on the same Linux host with host networking.

By default, the ROS Bridge requests Axis Server command authority automatically
after connecting. Set `CIA402_AUTO_REQUEST_AUTHORITY=0` if command authority
should be managed by another client such as the local Axis Panel.

Standard ROS motion command:

```text
/joint_trajectory            trajectory_msgs/JointTrajectory, standard position command
```

Project-specific management topics:

```text
/motion_mode                  std_msgs/String, "pp" or JSON {"axis":0,"mode":"csp"}
/controlword                  std_msgs/Int32MultiArray, [cw] or [axis, cw]
/jog_position                 std_msgs/Float64MultiArray, [axis, distance]
/alarm_ack                    std_msgs/Empty
/command_authority/request    std_msgs/Empty
/command_authority/release    std_msgs/Empty
```

The ROS Control Panel Command tab can select the command transport:

```text
Action Controller  -> /cia402_joint_trajectory_controller/follow_joint_trajectory
Topic Debug        -> /joint_trajectory
```

`Action Controller` is the recommended default because it exercises the same
`FollowJointTrajectory` interface that MoveIt uses. `Topic Debug` remains as a
simple fire-and-forget compatibility path. Repeat motion follows the selected
transport and supports 2 to 8 points. For example, with 3 points configured the
panel repeats `A -> B -> C -> A`. The authority request/release buttons remain
in the ROS Control Panel as project-specific control ownership management, not
as motion commands.

Axis limit/configuration values are exposed as ROS parameters on
`/ros_command_bridge`, because max velocity, acceleration, deceleration, and
Kp are configuration data rather than normal motion command data:

```text
axis_0.max_velocity
axis_0.acceleration
axis_0.deceleration
axis_0.kp
```

The same parameter pattern is repeated for each axis. The legacy
`/target_positions`, `/motion_limits`, and `/repeat_motion_command` topics are
still accepted by the Bridge for compatibility with earlier test tools, but new
integrations and the ROS Control Panel should prefer parameters and standard
trajectory commands.

Core ROS feedback topics:

```text
/joint_states
/target_position_feedback
/actual_positions
/actual_velocities
/statuswords
/drive_diagnostics
/motion_limits_feedback
/motion_modes_feedback
/command_authority/status
/command_rejected
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
docker/axis_panel/   Axis Server Control Panel Dockerfile
docker/ros/          ROS Compose file
docker/ros_bridge/   ROS Bridge Dockerfile
docker/ros_control_panel/ ROS Control Panel Dockerfile
docker/ros_moveit/   ROS MoveIt Dockerfile
scripts/host/        Ubuntu EtherCAT host commands: start, stop, panel, service, adapters
scripts/ros/         ROS container launch helpers
scripts/windows/     Windows sync helper and optional direct Axis Server launcher
ros/                 ROS bridge/control panel and trace display
ethercat/            Mock/PySOEM EtherCAT transport, PDO, and process-data code
cia402/              Virtual CiA402 drive model
```
