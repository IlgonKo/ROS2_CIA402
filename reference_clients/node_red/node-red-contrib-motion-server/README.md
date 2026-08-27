# Node-RED Motion Server Nodes

This package provides four reusable nodes for the Motion Server TCP JSON-lines API:

- Motion Server Connection (configuration node)
- Motion Server Request
- Motion Server Feedback
- Motion Server Connection Status

## Local installation

From the Node-RED user directory:

```powershell
npm install C:\path\to\motion-server\reference_clients\node_red\node-red-contrib-motion-server
```

Restart Node-RED and import `01_connection_and_status.json` first. It owns the shared
`Shared Motion Server` Connection Config. Import `02_command_authority.json` as the common authority flow,
then import any required functional flows from `03` through `06`. All of these flows reference the same
Connection Config and therefore share one TCP connection, correlation state and command authority.

When a flow from `02` through `06` is imported without `01`, first create a Motion Server Connection with
the id expected by the examples or reselect an existing Connection in each Motion Server node.

Request input uses `msg.payload.cmd`. The first output carries raw server Success/Fail envelopes; the second
output carries client transport failures. Caller `msg.topic` and custom properties are preserved.

The Axis dashboard example uses `@flowfuse/node-red-dashboard`, which is installed as a package dependency.
Deploying an example never sends a motion or output-changing command automatically.
