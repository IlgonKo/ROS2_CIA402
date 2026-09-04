# Windows EXE Packaging

Motion Server and Axis Control Panel can run on Windows without Docker after
packaging with PyInstaller.

## Build

Run from the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_exe.ps1
```

The package is created at:

```text
dist\Motion Server
```

PyInstaller intermediate files are created in a temporary folder and removed
after packaging. The project `dist` folder should contain only the final
`Motion Server` package.

## Package Layout

```text
dist\Motion Server
  motion_server.exe
  config.txt
  config.example.txt
  device\cmmt\config.txt
  device\cmmt\config.example.txt
  device\cpx_ap_i_ec\config.example.txt
  device\io_link\iodd\
  Manual\Motion_Server_Installation_Manual_*.*
  Manual\Motion_Server_User_Manual_*.*
  Reference\cmmt_error_catalog.json
  Reference Clients\node_red\node-red-contrib-motion-server\package.json
  Reference Clients\node_red\node-red-contrib-motion-server\examples\flows\*.json
  Tools\axis_control_panel\axis_control_panel.exe
  Tools\axis_control_panel\config.txt
  Tools\axis_control_panel\config.example.txt
  Tools\io_control_panel\io_control_panel.exe
  Tools\io_control_panel\config.txt
  Tools\io_control_panel\config.example.txt
  Tools\list_ethercat_nics.ps1
  Tools\npcap-1.88.exe
```

Local `.env` files can be copied by the build script as Windows `config.txt`
files for this PC. For a clean redistributable package, create or edit these
files manually:

```text
dist\Motion Server\config.txt
dist\Motion Server\device\cmmt\config.txt
dist\Motion Server\device\cpx_ap_i_ec\config.txt
dist\Motion Server\Tools\axis_control_panel\config.txt
dist\Motion Server\Tools\io_control_panel\config.txt
```

Mock and real devices use the same profile configuration files. Virtual CMMT
axes use `device/cmmt/config.txt`; there is no separate virtual servo config.
ESI, IODD and the CMMT error catalog are bundled under `_internal` for runtime
loading, including when the package is launched outside the source checkout.
User-provided IODD files can be copied to `device\io_link\iodd`. In frozen
Windows packages, this external folder is searched before the bundled `_internal`
IODD files. The Node-RED reference client package and sample flows are copied
under `Reference Clients\node_red`; install dependencies with npm on the target
PC before importing the flows.

## Run With Mock Axes

```powershell
cd "dist\Motion Server"
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
cd "dist\Motion Server"
.\motion_server.exe
.\Tools\axis_control_panel\axis_control_panel.exe
```

## API Unit Policy

The Motion Server public API uses:

- linear position: `mm`
- rotary position: `deg`

PV mode is allowed only when the CMMT user position unit `0x216E:01` is in the
rotary unit family: rad, degree, or revolution.
