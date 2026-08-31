"use strict";

const assert = require("assert");
const fs = require("fs");
const net = require("net");
const path = require("path");
const helper = require("node-red-node-test-helper");
const motionServerNodes = require("../nodes/motion-server.js");

helper.init(require.resolve("node-red"));

describe("node-red-contrib-motion-server", function() {
    this.timeout(8000);
    let servers = [];

    before(() => helper.startServer());
    after(() => helper.stopServer());
    afterEach(async () => {
        await helper.unload();
        await Promise.all(servers.map(closeServer));
        servers = [];
    });

    it("shares one socket and routes raw success, fail, feedback and status", async function() {
        let connectionCount = 0;
        const server = await createJsonServer((socket, request) => {
            const result = request.cmd === "fail" ? "fail" : "success";
            writeJson(socket, {
                type: request.cmd,
                request_id: request.request_id,
                result,
                [result === "fail" ? "failure" : "data"]: result === "fail"
                    ? { code: "TEST_FAILURE", message: "failed" }
                    : { value: request.value },
            });
        }, (socket) => {
            connectionCount += 1;
            const feedback = Buffer.from(`${JSON.stringify({
                type: "system/feedback",
                label: "축",
                actual_positions: [1, 2],
            })}\n`, "utf8");
            const split = feedback.indexOf(Buffer.from("축", "utf8")) + 1;
            setTimeout(() => {
                socket.write(feedback.subarray(0, split));
                socket.write(feedback.subarray(split));
            }, 30);
        });
        servers.push(server);

        const flow = baseFlow(server.address().port, [
            requestNode("req1", "out1", "err1"),
            requestNode("req2", "out2", "err2"),
            { id: "feedback", type: "motion-server-feedback", connection: "cfg", wires: [["feedbackOut"]] },
            { id: "status", type: "motion-server-connection-status", connection: "cfg", wires: [["statusOut"]] },
            helperNode("out1"), helperNode("err1"), helperNode("out2"), helperNode("err2"),
            helperNode("feedbackOut"), helperNode("statusOut"),
        ]);
        await loadFlow(flow);
        await waitConnected(helper.getNode("cfg"));

        const first = messageFrom(helper.getNode("out1"));
        helper.getNode("req1").receive({ topic: "caller-topic", custom: 7, payload: { cmd: "echo", value: 3 } });
        const firstMessage = await first;
        assert.equal(firstMessage.topic, "caller-topic");
        assert.equal(firstMessage.custom, 7);
        assert.equal(firstMessage.payload.result, "success");
        assert.equal(firstMessage.payload.data.value, 3);

        const second = messageFrom(helper.getNode("out2"));
        helper.getNode("req2").receive({ payload: { cmd: "fail" } });
        assert.equal((await second).payload.result, "fail");

        const feedbackMessage = await messageFrom(helper.getNode("feedbackOut"));
        assert.equal(feedbackMessage.topic, "system/feedback");
        assert.deepEqual(feedbackMessage.payload.actual_positions, [1, 2]);
        assert.equal(connectionCount, 1);
        assert.match(firstMessage.payload.request_id, /^node-red-[0-9a-f]{6}-1$/);
    });

    it("routes invalid requests and timeouts only to the client-error output", async function() {
        const server = await createJsonServer((socket, request) => {
            const delay = request.cmd === "slow" ? 100 : 0;
            setTimeout(() => writeJson(socket, {
                type: request.cmd,
                request_id: request.request_id,
                result: "success",
                data: {},
            }), delay);
        });
        servers.push(server);
        const flow = baseFlow(server.address().port, [
            requestNode("request", "response", "error", "0.03"),
            helperNode("response"), helperNode("error"),
        ]);
        await loadFlow(flow);
        await waitConnected(helper.getNode("cfg"));

        let errorMessage = messageFrom(helper.getNode("error"));
        helper.getNode("request").receive({ topic: "invalid", payload: { axis: 0 } });
        let error = await errorMessage;
        assert.equal(error.topic, "invalid");
        assert.equal(error.payload.code, "invalid_client_request");
        assert.equal(error.payload.command, "");

        const circular = { cmd: "invalid-json" };
        circular.value = circular;
        errorMessage = messageFrom(helper.getNode("error"));
        helper.getNode("request").receive({ topic: "invalid-json", payload: circular });
        error = await errorMessage;
        assert.equal(error.topic, "invalid-json");
        assert.equal(error.payload.code, "invalid_client_request");
        assert.equal(error.payload.command, "invalid-json");

        errorMessage = messageFrom(helper.getNode("error"));
        helper.getNode("request").receive({ payload: { cmd: "slow" } });
        error = await errorMessage;
        assert.equal(error.payload.code, "request_timeout");
        assert.equal(error.payload.command, "slow");

        await delay(120);
        const responseMessage = messageFrom(helper.getNode("response"));
        helper.getNode("request").receive({ payload: { cmd: "next" } });
        assert.equal((await responseMessage).payload.type, "next");
    });

    it("fails a pending request, reconnects, and never retransmits it", async function() {
        let connectionCount = 0;
        const commands = [];
        const server = await createJsonServer((socket, request) => {
            commands.push(request.cmd);
            if (request.cmd === "disconnect") {
                socket.destroy();
                return;
            }
            writeJson(socket, {
                type: request.cmd,
                request_id: request.request_id,
                result: "success",
                data: {},
            });
        }, () => { connectionCount += 1; });
        servers.push(server);
        const flow = baseFlow(server.address().port, [
            requestNode("request", "response", "error"),
            helperNode("response"), helperNode("error"),
        ]);
        await loadFlow(flow);
        const config = helper.getNode("cfg");
        await waitConnected(config);

        const errorMessage = messageFrom(helper.getNode("error"));
        helper.getNode("request").receive({ payload: { cmd: "disconnect" } });
        assert.equal((await errorMessage).payload.code, "connection_lost");

        await waitFor(() => connectionCount >= 2 && config.connected, 2500);
        const responseMessage = messageFrom(helper.getNode("response"));
        helper.getNode("request").receive({ payload: { cmd: "after-reconnect" } });
        assert.equal((await responseMessage).payload.type, "after-reconnect");
        assert.deepEqual(commands, ["disconnect", "after-reconnect"]);
    });

    it("emits connection status only for the initial snapshot and boolean transitions", async function() {
        const server = await createJsonServer(() => {});
        servers.push(server);
        const flow = baseFlow(server.address().port, [
            { id: "status", type: "motion-server-connection-status", connection: "cfg", wires: [["statusOut"]] },
            helperNode("statusOut"),
        ]);
        await loadFlow(flow);
        const config = helper.getNode("cfg");
        await waitConnected(config);
        const messages = [];
        helper.getNode("statusOut").on("input", (msg) => messages.push(msg));

        config.setConnectionState(false, "lost");
        config.setConnectionState(false, "retry failed");
        config.setConnectionState(true, "");
        await delay(20);

        assert.equal(messages.length, 2);
        assert.deepEqual(messages[0].payload, { connected: false, last_error: "lost" });
        assert.deepEqual(messages[1].payload, { connected: true, last_error: "" });
        assert.ok(messages.every((msg) => msg.topic === "motion-server/connection"));
    });

    it("retries an initially absent server without replaying disconnected requests", async function() {
        const port = await reservePort();
        const flow = baseFlow(port, [
            requestNode("request", "response", "error"),
            helperNode("response"), helperNode("error"),
        ]);
        await loadFlow(flow);
        const config = helper.getNode("cfg");

        const disconnected = messageFrom(helper.getNode("error"));
        helper.getNode("request").receive({ payload: { cmd: "not-retried" } });
        assert.equal((await disconnected).payload.code, "not_connected");

        const commands = [];
        const server = await createJsonServer((socket, request) => {
            commands.push(request.cmd);
            writeJson(socket, {
                type: request.cmd,
                request_id: request.request_id,
                result: "success",
                data: {},
            });
        }, () => {}, port);
        servers.push(server);
        await waitFor(() => config.connected, 2500);

        const response = messageFrom(helper.getNode("response"));
        helper.getNode("request").receive({ payload: { cmd: "after-connect" } });
        assert.equal((await response).payload.type, "after-connect");
        assert.deepEqual(commands, ["after-connect"]);
    });

    it("connects to a dashboard endpoint and stops reconnecting after manual disconnect", async function() {
        let connectionCount = 0;
        const server = await createJsonServer(() => {}, () => { connectionCount += 1; });
        servers.push(server);
        const flow = [
            {
                id: "cfg",
                type: "motion-server-connection",
                host: "127.0.0.1",
                port: 15000,
                autoConnect: false,
                requestTimeout: 1,
            },
            {
                id: "control",
                type: "motion-server-connection-control",
                connection: "cfg",
                wires: [["endpoint"]],
            },
            helperNode("endpoint"),
        ];
        await loadFlow(flow);
        const config = helper.getNode("cfg");
        assert.equal(config.connected, false);

        helper.getNode("control").receive({
            payload: {
                action: "connect",
                host: "127.0.0.1",
                port: server.address().port,
            },
        });
        await waitConnected(config);
        assert.equal(config.host, "127.0.0.1");
        assert.equal(config.port, server.address().port);
        assert.equal(connectionCount, 1);

        helper.getNode("control").receive({ payload: { action: "disconnect" } });
        await waitFor(() => !config.connected, 500);
        await delay(1200);
        assert.equal(config.desiredConnected, false);
        assert.equal(connectionCount, 1);
    });

    it("ships one shared control dashboard, safe scenario flows and a 500-point axis dashboard", function() {
        const flowDirectory = path.join(__dirname, "..", "examples", "flows");
        const expected = [
            "01_connection_and_authority.json",
            "02_axis_control.json",
            "03_io_control.json",
            "04_virtual_io_simulation.json",
            "05_sample_motion_sequence.json",
        ];
        assert.deepEqual(fs.readdirSync(flowDirectory).sort(), expected);

        for (const name of expected) {
            const flow = JSON.parse(fs.readFileSync(path.join(flowDirectory, name), "utf8"));
            assert.equal(flow.filter((node) => node.type === "tab").length, 1);
            assert.ok(flow.some((node) => node.type === "motion-server-request") || name === expected[0]);
            for (const node of flow.filter((candidate) => candidate.connection)) {
                assert.equal(node.connection, "cfg-status", `${name}:${node.name} must use the shared connection`);
            }
            for (const inject of flow.filter((node) => node.type === "inject")) {
                assert.equal(inject.once, false, `${name}:${inject.name} must be manual`);
            }
        }

        const connectionFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "01_connection_and_authority.json"),
            "utf8",
        ));
        assert.deepEqual(
            connectionFlow.filter((node) => node.type === "motion-server-connection").map((node) => node.id),
            ["cfg-status"],
        );
        for (const name of expected.slice(1)) {
            const flow = JSON.parse(fs.readFileSync(path.join(flowDirectory, name), "utf8"));
            assert.equal(
                flow.filter((node) => node.type === "motion-server-connection").length,
                0,
                `${name} must reuse the connection owned by 01_connection_and_authority.json`,
            );
        }

        const dashboard = connectionFlow.find((node) => node.type === "ui-base");
        const theme = connectionFlow.find((node) => node.type === "ui-theme");
        const serverPage = connectionFlow.find((node) => node.id === "server-page");
        const controlGroup = connectionFlow.find((node) => node.id === "server-control-group");
        const controlPanel = connectionFlow.find((node) => node.id === "server-control-panel");
        assert.ok(dashboard && theme && serverPage && controlGroup && controlPanel);
        assert.equal(serverPage.ui, dashboard.id);
        assert.equal(serverPage.theme, theme.id);
        assert.equal(controlGroup.page, serverPage.id);
        assert.equal(controlPanel.group, controlGroup.id);
        assert.ok(connectionFlow.some((node) => node.type === "motion-server-connection-control"));
        for (const label of [
            "Request Authority", "Release Authority", "Bus Reconnect",
            "Server Fault Reset", "Server Restart", "Motion Server Status",
            "Host", "Port", "Connect", "Disconnect",
        ]) {
            assert.ok(controlPanel.format.includes(label), label);
        }
        const actionRouter = connectionFlow.find((node) => node.id === "route-control-action");
        for (const command of [
            "system/authority/request", "system/authority/release",
            "system/bus/reconnect", "system/server/fault_reset",
            "system/server/restart",
        ]) {
            assert.ok(actionRouter.func.includes(command), command);
        }
        for (const functionNode of connectionFlow.filter((node) => node.type === "function")) {
            assert.doesNotThrow(
                () => new Function("msg", "flow", "node", functionNode.func),
                functionNode.name,
            );
        }
        const authorityContext = createFlowContext({ authorityOwned: false });
        assert.deepEqual(
            new Function("msg", "flow", "node", actionRouter.func)(
                { payload: { action: "authority_toggle" } },
                authorityContext.flow,
                authorityContext.node,
            ),
            [null, { payload: { cmd: "system/authority/request" } }],
        );
        const feedbackFormatter = connectionFlow.find((node) => node.id === "format-feedback-status");
        const dashboardFeedbackContext = createFlowContext();
        const formattedFeedback = new Function("msg", "flow", "node", feedbackFormatter.func)(
            { payload: { command_authority: { available: true }, process_data_valid: true } },
            dashboardFeedbackContext.flow,
            dashboardFeedbackContext.node,
        );
        assert.equal(formattedFeedback[0].length, 2);
        assert.equal(formattedFeedback[0][0].topic, "dashboard/feedback");
        assert.deepEqual(formattedFeedback[0][1], {
            topic: "dashboard/connection",
            payload: { connected: true, last_error: "" },
        });

        const ioFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "03_io_control.json"),
            "utf8",
        ));
        const ioPage = ioFlow.find((node) => node.id === "io-page");
        const ioPanel = ioFlow.find((node) => node.id === "io-control-panel");
        assert.ok(ioPage && ioPanel);
        assert.equal(ioPage.ui, dashboard.id);
        assert.equal(ioPage.theme, theme.id);
        assert.equal(ioPanel.group, "io-control-group");
        for (const label of [
            "Digital Output", "I/O Status", "EC Parameter",
            "AP Parameter", "IOL Parameter", "Raw Image", "Refresh",
            "<th>Channel</th>", "statusRows(device)",
        ]) {
            assert.ok(ioPanel.format.includes(label), label);
        }
        for (const command of [
            "system/io/status", "system/io/output_write",
            "system/io/param_",
            "system/io/ethercat/param_catalog",
            "system/io/ap/param_",
            "system/io/iol/param_catalog",
            "system/io/iol/param_",
        ]) {
            assert.ok(ioPanel.format.includes(command), command);
        }
        assert.equal(JSON.stringify(ioFlow).includes("system/simulation/io/"), false);
        for (const functionNode of ioFlow.filter((node) => node.type === "function")) {
            assert.doesNotThrow(
                () => new Function("msg", "flow", "node", functionNode.func),
                functionNode.name,
            );
        }
        const ioFeedbackFormatter = ioFlow.find((node) => node.id === "format-io-feedback");
        const ioFeedbackContext = createFlowContext();
        const formattedIoFeedback = new Function("msg", "flow", "node", ioFeedbackFormatter.func)(
            { payload: { io: { devices: [] }, process_data_valid: true } },
            ioFeedbackContext.flow,
            ioFeedbackContext.node,
        );
        assert.equal(formattedIoFeedback[0].length, 2);
        assert.equal(formattedIoFeedback[0][0].topic, "io/feedback");
        assert.deepEqual(formattedIoFeedback[0][1], {
            topic: "io/connection",
            payload: { connected: true, last_error: "" },
        });
        const simulationFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "04_virtual_io_simulation.json"),
            "utf8",
        ));
        const simulationPage = simulationFlow.find((node) => node.id === "simulation-page");
        const simulationPanel = simulationFlow.find((node) => node.id === "simulation-control-panel");
        assert.ok(simulationPage && simulationPanel);
        assert.equal(simulationPage.ui, dashboard.id);
        assert.equal(simulationPage.theme, theme.id);
        assert.equal(simulationPanel.group, "simulation-control-group");
        assert.equal(simulationFlow.filter((node) => node.type === "inject").length, 0);
        for (const label of [
            "Virtual I/O Simulation", "Digital Input", "Analog Input",
            "IO-Link Input Process Data", "Reset Module", "Reset Station", "Refresh",
        ]) {
            assert.ok(simulationPanel.format.includes(label), label);
        }
        const simulationRequestBuilder = simulationFlow.find(
            (node) => node.id === "build-simulation-request",
        );
        for (const command of [
            "system/simulation/io/input_read",
            "system/simulation/io/input_write",
            "system/simulation/io/input_reset",
        ]) {
            assert.ok(simulationRequestBuilder.func.includes(command), command);
        }
        assert.deepEqual(
            new Function("msg", "flow", "node", simulationRequestBuilder.func)(
                { payload: {
                    action: "write_digital",
                    io: "io0",
                    slot: 2,
                    digital_channel: 1,
                    digital_value: true,
                } },
                createFlowContext().flow,
                createFlowContext().node,
            ),
            { payload: {
                cmd: "system/simulation/io/input_write",
                io: "io0",
                slot: 2,
                kind: "digital",
                channel: 1,
                value: true,
            } },
        );
        for (const functionNode of simulationFlow.filter((node) => node.type === "function")) {
            assert.doesNotThrow(
                () => new Function("msg", "flow", "node", functionNode.func),
                functionNode.name,
            );
        }
        const sequenceFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "05_sample_motion_sequence.json"),
            "utf8",
        ));
        const sequencePage = sequenceFlow.find((node) => node.id === "sequence-page");
        assert.ok(sequencePage);
        assert.equal(sequencePage.ui, dashboard.id);
        assert.equal(sequencePage.theme, theme.id);
        assert.equal(sequenceFlow.filter((node) => node.type === "motion-server-connection").length, 0);
        assert.equal(sequenceFlow.filter((node) => node.type === "motion-server-request").length, 1);
        assert.equal(sequenceFlow.filter((node) => node.type === "motion-server-feedback").length, 1);
        assert.equal(sequenceFlow.some((node) => node.id === "sequence-state-machine"), false);
        for (const id of [
            "sequence-build-stage1",
            "sequence-stage1-complete",
            "sequence-stage2-complete",
            "sequence-input-condition",
            "sequence-stage3-complete",
            "sequence-stage4-complete",
        ]) {
            assert.ok(sequenceFlow.some((node) => node.id === id), id);
        }
        const sequenceSource = sequenceFlow
            .filter((node) => node.type === "function")
            .map((node) => node.func)
            .join("\n");
        for (const command of [
            "system/axes/move_abs",
            "system/axis/move_abs",
            "system/axes/stop",
            "system/io/output_write",
        ]) {
            assert.ok(sequenceSource.includes(command), command);
        }
        for (const functionNode of sequenceFlow.filter((node) => node.type === "function")) {
            assert.doesNotThrow(
                () => new Function("msg", "flow", "node", functionNode.func),
                functionNode.name,
            );
        }
        for (const template of [...connectionFlow, ...ioFlow, ...simulationFlow].filter(
            (node) => node.type === "ui-template" && node.format.includes("<script>"),
        )) {
            const script = template.format.match(/<script>([\s\S]*?)<\/script>/)[1]
                .replace("export default", "return");
            assert.doesNotThrow(() => new Function(script), template.name);
        }

        const axisFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "02_axis_control.json"),
            "utf8",
        ));
        const charts = axisFlow.filter((node) => node.type === "ui-chart");
        const page = axisFlow.find((node) => node.type === "ui-page");
        const chartGroup = axisFlow.find((node) => node.id === "axis-chart-group");
        assert.ok(page);
        assert.ok(chartGroup);
        assert.equal(page.ui, dashboard.id);
        assert.equal(page.theme, theme.id);
        assert.ok(axisFlow.filter((node) => node.type === "ui-group").every(
            (node) => node.page === page.id,
        ));
        assert.equal(charts.length, 2);
        assert.ok(charts.every((node) => node.group === chartGroup.id));
        assert.ok(charts.every((node) => node.removeOlderPoints === "500"));
        assert.equal(chartGroup.name, "Selected Axis Feedback");
        assert.ok(charts.every((node) => node.name.startsWith("Selected Axis")));
        assert.ok(axisFlow.some((node) => node.type === "motion-server-feedback"));
        assert.ok(axisFlow.some((node) => node.name === "Clear on Disconnect"));
        assert.ok(axisFlow.some((node) => node.type === "ui-dropdown" && node.name === "Axis Selector"));
        assert.ok(axisFlow.some((node) => node.type === "ui-template" && node.name === "Statusword Lamps"));
        assert.ok(axisFlow.some((node) => node.type === "ui-text-input" && node.name === "Target Position Input"));
        assert.ok(axisFlow.some((node) => node.type === "ui-text-input" && node.name === "Profile Velocity Input"));
        for (const name of ["Enable", "Disable", "Run", "Stop", "Homing", "Fault Reset", "Refresh"]) {
            assert.ok(axisFlow.some((node) => node.type === "ui-button" && node.name === name), name);
        }
        const jogControls = axisFlow.find((node) => node.type === "ui-template" && node.name === "Jog Controls");
        assert.ok(jogControls);
        assert.match(jogControls.format, /jog_negative/);
        assert.match(jogControls.format, /jog_positive/);
        assert.match(jogControls.format, /@pointerup=\"stopJog\"/);
        assert.match(jogControls.format, /@pointerleave=\"stopJog\"/);
        assert.match(jogControls.format, /@pointercancel=\"stopJog\"/);
        assert.match(jogControls.format, /payload: 'jog_stop'/);
        const commandBuilder = axisFlow.find((node) => node.id === "build-axis-command");
        for (const command of [
            "system/axis/enable", "system/axis/disable", "system/axis/move_abs",
            "system/axis/stop", "system/axis/home", "system/axis/fault_reset",
            "system/axis/status", "system/axis/jog_start", "system/axis/jog_stop",
        ]) {
            assert.ok(commandBuilder.func.includes(command), command);
        }
        const axisParameterPanel = axisFlow.find((node) => node.id === "axis-parameter-panel");
        assert.ok(axisParameterPanel);
        for (const command of [
            "system/axis/param_catalog", "system/axis/param_read",
            "system/axis/param_write", "system/axis/param_save",
        ]) {
            assert.ok(axisParameterPanel.format.includes(command), command);
        }
        const axisSettingsPanel = axisFlow.find((node) => node.id === "axis-settings-panel");
        assert.ok(axisSettingsPanel);
        assert.equal(axisSettingsPanel.group, "axis-settings-group");
        for (const label of [
            "Profile Parameters", "Motion Limits", "Software Position Limits",
            "Apply Profile", "Apply Motion Limits", "Apply SW Limits",
        ]) {
            assert.ok(axisSettingsPanel.format.includes(label), label);
        }
        for (const command of [
            "system/axis/profile", "system/axis/motion_limits",
            "system/axis/software_position_limits",
        ]) {
            assert.ok(axisSettingsPanel.format.includes(command), command);
        }
        const settingsResponseFormatter = axisFlow.find(
            (node) => node.id === "format-axis-settings-response",
        );
        assert.deepEqual(
            new Function("msg", "flow", "node", settingsResponseFormatter.func)(
                { axis: 2, payload: { type: "system/axis/profile", result: "success" } },
                createFlowContext().flow,
                createFlowContext().node,
            ),
            [
                {
                    topic: "axis/settings-response",
                    payload: { type: "system/axis/profile", result: "success" },
                },
                { payload: { cmd: "system/axis/status", axis: 2 } },
            ],
        );
        assert.ok(axisFlow.find((node) => node.id === "axis-request")
            .wires[0].includes("axis-settings-status"));
        const settingsStatusFormatter = axisFlow.find(
            (node) => node.id === "axis-settings-status",
        );
        const roundedSettings = new Function("msg", "flow", "node", settingsStatusFormatter.func)(
            { payload: {
                type: "system/axis/status",
                result: "success",
                data: {
                    profile_settings: [1.235, 2.344, 3.456, 4.567],
                    motion_limits: [10.129, -10.129, 20.555, 30.444],
                    software_position_limits: [-100.125, 100.125],
                },
            } },
            createFlowContext().flow,
            createFlowContext().node,
        );
        assert.deepEqual(roundedSettings.payload.profile_settings, [1.24, 2.34, 3.46, 4.57]);
        assert.deepEqual(roundedSettings.payload.motion_limits, [10.13, -10.13, 20.56, 30.44]);
        assert.deepEqual(roundedSettings.payload.software_position_limits, [-100.13, 100.13]);
        for (const displayName of [
            "Actual Position Display", "Actual Velocity Display", "Active Target Display",
        ]) {
            assert.equal(
                axisFlow.find((node) => node.name === displayName).format,
                "{{Number(msg.payload).toFixed(2)}}",
            );
        }
        for (const functionNode of axisFlow.filter((node) => node.type === "function")) {
            assert.doesNotThrow(
                () => new Function("msg", "flow", "node", functionNode.func),
                functionNode.name,
            );
        }
        for (const template of axisFlow.filter(
            (node) => node.type === "ui-template" && node.format.includes("<script>"),
        )) {
            const script = template.format.match(/<script>([\s\S]*?)<\/script>/)[1]
                .replace("export default", "return");
            assert.doesNotThrow(() => new Function(script), template.name);
        }

        const context = createFlowContext({
            selectedAxis: 1,
            axisCount: 2,
            axisTargetPosition: 12.5,
            axisProfileVelocity: 30,
        });
        const built = new Function("msg", "flow", "node", commandBuilder.func)(
            { payload: "run" },
            context.flow,
            context.node,
        );
        assert.deepEqual(built.payload, {
            cmd: "system/axis/move_abs",
            axis: 1,
            position: 12.5,
            profile_velocity: 30,
        });

        const feedbackView = axisFlow.find((node) => node.id === "axis-feedback-view");
        const feedbackContext = createFlowContext();
        const feedbackOutputs = new Function("msg", "flow", "node", feedbackView.func)(
            { payload: {
                actual_positions: [1, 2],
                actual_velocities: [3, 4],
                target_positions: [5, 6],
                statuswords: [0x0027, 0x0008],
            } },
            feedbackContext.flow,
            feedbackContext.node,
        );
        assert.equal(feedbackContext.values.axisCount, 2);
        assert.equal(feedbackContext.values.selectedAxis, 0);
        assert.equal(feedbackOutputs[0].payload.bits.length, 16);
        assert.equal(feedbackOutputs[0].payload.state, "Op Enabled");
        assert.deepEqual(feedbackOutputs[4].ui_update.options, [
            { value: 0, label: "Axis 0" },
            { value: 1, label: "Axis 1" },
        ]);
        assert.equal(feedbackOutputs.length, 7);
        assert.deepEqual(feedbackOutputs[5].payload, {
            cmd: "system/axis/status",
            axis: 0,
        });
        assert.deepEqual(feedbackOutputs[6].payload, {
            axis: 0,
            authority_owned: false,
        });
        assert.equal(feedbackContext.values.axisTargetPosition, undefined);
        assert.equal(feedbackContext.values.axisProfileVelocity, undefined);

        const selectedSeriesContext = createFlowContext({ selectedAxis: 1, axisCount: 2 });
        const positionSeries = axisFlow.find((node) => node.id === "axis-position-series");
        const velocitySeries = axisFlow.find((node) => node.id === "axis-velocity-series");
        assert.deepEqual(
            new Function("msg", "flow", "node", positionSeries.func)(
                { payload: { actual_positions: [10, 20] } },
                selectedSeriesContext.flow,
                selectedSeriesContext.node,
            ),
            { topic: "Axis 1", payload: 20 },
        );
        assert.deepEqual(
            new Function("msg", "flow", "node", velocitySeries.func)(
                { payload: { actual_velocities: [30, 40] } },
                selectedSeriesContext.flow,
                selectedSeriesContext.node,
            ),
            { topic: "Axis 1", payload: 40 },
        );
    });
});

function baseFlow(port, nodes) {
    return [{
        id: "cfg",
        type: "motion-server-connection",
        host: "127.0.0.1",
        port,
        requestTimeout: 1,
    }, ...nodes];
}

function requestNode(id, success, failure, timeout = "") {
    return {
        id,
        type: "motion-server-request",
        connection: "cfg",
        timeout,
        wires: [[success], [failure]],
    };
}

function helperNode(id) {
    return { id, type: "helper" };
}

function createFlowContext(initial = {}) {
    const values = { ...initial };
    return {
        values,
        flow: {
            get: (key) => values[key],
            set: (key, value) => { values[key] = value; },
        },
        node: { warn: () => {} },
    };
}

function loadFlow(flow) {
    return new Promise((resolve, reject) => {
        helper.load(motionServerNodes, flow, (error) => error ? reject(error) : resolve());
    });
}

function messageFrom(node) {
    return new Promise((resolve) => node.once("input", resolve));
}

function waitConnected(config) {
    return waitFor(() => config.connected, 2000);
}

async function waitFor(predicate, timeout) {
    const started = Date.now();
    while (!predicate()) {
        if (Date.now() - started > timeout) {
            throw new Error("condition timed out");
        }
        await delay(10);
    }
}

function delay(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function createJsonServer(handler, onConnection = () => {}, port = 0) {
    return new Promise((resolve, reject) => {
        const server = net.createServer((socket) => {
            onConnection(socket);
            let buffer = Buffer.alloc(0);
            socket.on("data", (chunk) => {
                buffer = Buffer.concat([buffer, chunk]);
                while (true) {
                    const newline = buffer.indexOf(0x0a);
                    if (newline < 0) {
                        break;
                    }
                    const line = buffer.subarray(0, newline);
                    buffer = buffer.subarray(newline + 1);
                    if (line.length > 0) {
                        handler(socket, JSON.parse(line.toString("utf8")));
                    }
                }
            });
        });
        server.once("error", reject);
        server.listen(port, "127.0.0.1", () => resolve(server));
    });
}

function reservePort() {
    return new Promise((resolve, reject) => {
        const server = net.createServer();
        server.once("error", reject);
        server.listen(0, "127.0.0.1", () => {
            const port = server.address().port;
            server.close((error) => error ? reject(error) : resolve(port));
        });
    });
}

function writeJson(socket, message) {
    if (!socket.destroyed) {
        socket.write(`${JSON.stringify(message)}\n`);
    }
}

function closeServer(server) {
    return new Promise((resolve) => server.close(resolve));
}
