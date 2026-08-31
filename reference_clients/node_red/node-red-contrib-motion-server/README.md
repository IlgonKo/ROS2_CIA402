# Node-RED Motion Server Nodes

This package provides five reusable nodes for the Motion Server TCP JSON-lines API:

- Motion Server Connection (configuration node)
- Motion Server Connection Control
- Motion Server Request
- Motion Server Feedback
- Motion Server Connection Status

## Local installation

From the Node-RED user directory:

```powershell
npm install C:\path\to\motion-server\reference_clients\node_red\node-red-contrib-motion-server
```

Restart Node-RED and import `01_connection_and_authority.json` first. It owns the shared Connection Config,
Dashboard Base/Theme, server endpoint controls and command-authority controls. Then import any required
functional flows from `02` through `05`. All of these flows reference the same Connection Config and
Dashboard, and therefore share one TCP connection, correlation state and command authority.

When a flow from `02` through `05` is imported without `01`, first import `01` or reselect an existing
Connection and Dashboard configuration in each dependent node.

The common Dashboard is available at `/dashboard/server`. Its compact server control bar provides Host/Port,
Connect/Disconnect, connection and authority state, Request/Release Authority, Bus Reconnect, Server Fault
Reset, Server Restart and a feedback-driven Motion Server Status summary. Disconnect stops automatic reconnect
until Connect is requested again. Authority and recovery actions are always explicit user actions.

Request input uses `msg.payload.cmd`. The first output carries raw server Success/Fail envelopes; the second
output carries client transport failures. Caller `msg.topic` and custom properties are preserved.

The Axis dashboard example uses `@flowfuse/node-red-dashboard`, which is installed as a package dependency.
It is available at `/dashboard/axis` and mirrors the main single-axis controls: axis selection, Statusword
lamps, position and velocity values, Enable/Disable/Run/Stop/Homing/Fault Reset/Refresh, press-and-hold Jog,
selected-axis Profile parameters, Motion Limits, Software Position Limits, parameter catalog/read/write/save
and selected-axis position/velocity charts. Settings are populated from `system/axis/status`, require command
authority to apply, and refresh from device readback after a successful write. Changing the selected axis
clears the previous chart history.
Jog stops on pointer release, leave or cancellation.

The I/O dashboard at `/dashboard/io` mirrors the operational I/O Control Panel without Virtual Input
Simulation. It provides device/module status, optional raw process images, Digital Output control and
EC/AP/IO-Link catalog and parameter access. Virtual input changes remain exclusive to flow `04`.
The Virtual I/O dashboard at `/dashboard/virtual-io` reads the configured Mock CPX stations and modules,
injects Digital, Analog and IO-Link input process data, and resets a selected module or station. It requires
the Mock backend and `MOTION_SERVER_SIMULATION_API_ENABLED=1`, but does not require command authority.
The sample sequence at `/dashboard/sequence` demonstrates application composition without adding a dedicated
sequence node. It connects the existing Request and Feedback nodes with small, visible standard Node-RED
Function nodes for each command and completion condition. The supplied four-axis motion and I/O values are
examples intended to be edited in the corresponding stage nodes before use.
Deploying an example never sends a motion or output-changing command automatically.
