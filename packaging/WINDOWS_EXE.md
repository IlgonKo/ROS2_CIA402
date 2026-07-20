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
  axis_control_panel.exe
  .env.example
  device\cmmt\.env.example
  device\cpx_ap_i_ec\.env.example
  Reference\cmmt_error_catalog.json
  Tools\list_ethercat_nics.ps1
  Tools\npcap-1.88.exe
```

Local `.env` files are intentionally not copied by the build script. Copy or
create these files manually when running against real hardware:

```text
dist\ROS2_CIA402\.env
dist\ROS2_CIA402\device\cmmt\.env
dist\ROS2_CIA402\device\cpx_ap_i_ec\.env
```

## Run With Mock Axes

```powershell
cd dist\ROS2_CIA402
.\motion_server.exe --backend mock --bus cmmt,cmmt,cmmt --server-mode basic --port 15000
.\axis_control_panel.exe
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

Set the real adapter name and device settings in `.env`, then run:

```powershell
cd dist\ROS2_CIA402
.\motion_server.exe
.\axis_control_panel.exe
```

## API Unit Policy

The Axis Server public API uses:

- linear position: `mm`
- rotary position: `deg`

PV mode is allowed only when the CMMT user position unit `0x216E:01` is in the
rotary unit family: rad, degree, or revolution.
