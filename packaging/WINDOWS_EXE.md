# Windows EXE Packaging

Axis Server and Axis Control Panel can run on Windows without Docker after
packaging with PyInstaller.

## Build

Run from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_exe.ps1
```

The package is created at:

```text
dist\ROS2_CIA402
```

## Package Layout

```text
dist\ROS2_CIA402
  motion_server.exe
  config.txt
  config.example.txt
  device\cmmt\config.txt
  device\cmmt\config.example.txt
  device\cpx_ap_i_ec\config.example.txt
  device\virtual_servo_drive\config.txt
  device\virtual_servo_drive\config.example.txt
  Manual\Motion_Server_User_Manual_*.*
  Reference\cmmt_error_catalog.json
  Tools\axis_control_panel\axis_control_panel.exe
  Tools\axis_control_panel\config.txt
  Tools\axis_control_panel\config.example.txt
  Tools\list_ethercat_nics.ps1
  Tools\npcap-1.88.exe
```

Local `.env` files can be copied by the build script as Windows `config.txt`
files for this PC. For a clean redistributable package, create or edit these
files manually:

```text
dist\ROS2_CIA402\config.txt
dist\ROS2_CIA402\device\cmmt\config.txt
dist\ROS2_CIA402\device\cpx_ap_i_ec\config.txt
dist\ROS2_CIA402\device\virtual_servo_drive\config.txt
dist\ROS2_CIA402\Tools\axis_control_panel\config.txt
```

## Run With Mock Axes

```powershell
cd dist\ROS2_CIA402
.\motion_server.exe --backend mock --bus cmmt,cmmt,cmmt --server-mode basic --port 15000
.\Tools\axis_control_panel\axis_control_panel.exe
```

## Run With Real EtherCAT Hardware

Npcap must be installed on the Windows PC. Run the bundled installer if needed:

```powershell
.\Tools\npcap-1.88.exe
```

Enable the WinPcap API-compatible mode option during Npcap installation. The
server loads Npcap DLLs from the standard installation paths at runtime.

To list Windows Npcap adapter names:

```powershell
powershell -ExecutionPolicy Bypass -File .\Tools\list_ethercat_nics.ps1
```

Set the real adapter name and device settings in `config.txt`, then run:

```powershell
cd dist\ROS2_CIA402
.\motion_server.exe
.\Tools\axis_control_panel\axis_control_panel.exe
```

## API Unit Policy

The Motion Server public API uses:

- linear position: `mm`
- rotary position: `deg`

PV mode is allowed only when the CMMT user position unit `0x216E:01` is in the
rotary unit family: rad, degree, or revolution.
