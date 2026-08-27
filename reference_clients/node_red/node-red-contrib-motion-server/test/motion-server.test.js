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

    it("ships shared foundation flows, safe scenario flows and a 500-point axis dashboard", function() {
        const flowDirectory = path.join(__dirname, "..", "examples", "flows");
        const expected = [
            "01_connection_and_status.json",
            "02_command_authority.json",
            "03_axis_control.json",
            "04_io_control.json",
            "05_parameter_access.json",
            "06_virtual_io_simulation.json",
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
            path.join(flowDirectory, "01_connection_and_status.json"),
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
                `${name} must reuse the connection owned by 01_connection_and_status.json`,
            );
        }

        const axisFlow = JSON.parse(fs.readFileSync(
            path.join(flowDirectory, "03_axis_control.json"),
            "utf8",
        ));
        const charts = axisFlow.filter((node) => node.type === "ui-chart");
        assert.equal(charts.length, 2);
        assert.ok(charts.every((node) => node.removeOlderPoints === "500"));
        assert.ok(axisFlow.some((node) => node.type === "motion-server-feedback"));
        assert.ok(axisFlow.some((node) => node.name === "Clear on Disconnect"));
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
