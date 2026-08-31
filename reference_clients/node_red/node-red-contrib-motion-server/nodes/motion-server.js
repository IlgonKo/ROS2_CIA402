"use strict";

const crypto = require("crypto");
const net = require("net");

const RECONNECT_PERIOD_MS = 1000;

module.exports = function registerMotionServerNodes(RED) {
    function MotionServerConnectionNode(config) {
        RED.nodes.createNode(this, config);
        const node = this;
        node.host = String(config.host || "127.0.0.1").trim();
        node.port = Number(config.port || 15000);
        node.requestTimeout = positiveMilliseconds(
            config.requestTimeout,
            5000,
        );
        node.desiredConnected = config.autoConnect !== false;
        node.connected = false;
        node.lastError = "";
        node.socket = null;
        node.buffer = Buffer.alloc(0);
        node.pending = new Map();
        node.feedbackListeners = new Set();
        node.statusListeners = new Set();
        node.sessionPrefix = `node-red-${crypto.randomBytes(3).toString("hex")}`;
        node.requestSequence = 0;
        node.reconnectTimer = null;
        node.stopped = false;

        node.endpointSnapshot = () => ({
            host: node.host,
            port: node.port,
            desired_connected: node.desiredConnected,
        });

        node.connectionSnapshot = () => ({
            connected: node.connected,
            last_error: node.lastError,
        });

        node.subscribeFeedback = (listener) => {
            node.feedbackListeners.add(listener);
            return () => node.feedbackListeners.delete(listener);
        };

        node.subscribeStatus = (listener) => {
            node.statusListeners.add(listener);
            listener(node.connectionSnapshot());
            return () => node.statusListeners.delete(listener);
        };

        node.request = (message, timeout, callback) => {
            const requestId = `${node.sessionPrefix}-${++node.requestSequence}`;
            const command = isPlainObject(message) ? message.cmd : "";
            const validationError = validateRequest(message);
            if (validationError) {
                callback(clientError(
                    "invalid_client_request",
                    validationError,
                    requestId,
                    command,
                ));
                return;
            }
            if (!node.connected || node.socket === null) {
                callback(clientError(
                    "not_connected",
                    "Motion Server is not connected",
                    requestId,
                    command,
                ));
                return;
            }

            const request = { ...message, request_id: requestId };
            let payload;
            try {
                payload = Buffer.from(`${JSON.stringify(request)}\n`, "utf8");
            } catch (error) {
                callback(clientError(
                    "invalid_client_request",
                    `request is not JSON serializable: ${error.message}`,
                    requestId,
                    command,
                ));
                return;
            }
            const timeoutMs = positiveMilliseconds(timeout, node.requestTimeout);
            const timer = setTimeout(() => {
                if (!node.pending.delete(requestId)) {
                    return;
                }
                callback(clientError(
                    "request_timeout",
                    `Motion Server request timed out after ${timeoutMs / 1000}s`,
                    requestId,
                    command,
                ));
            }, timeoutMs);
            node.pending.set(requestId, { callback, command, timer });

            try {
                node.socket.write(payload, (error) => {
                    if (!error) {
                        return;
                    }
                    node.disconnect(`Motion Server connection lost: ${error.message}`);
                });
            } catch (error) {
                node.disconnect(`Motion Server connection lost: ${error.message}`);
            }
        };

        node.setConnectionState = (connected, lastError) => {
            const changed = node.connected !== connected;
            node.connected = connected;
            node.lastError = lastError || "";
            if (!changed) {
                return;
            }
            const snapshot = node.connectionSnapshot();
            for (const listener of node.statusListeners) {
                listener(snapshot);
            }
        };

        node.failPending = (code, message) => {
            const pending = Array.from(node.pending.entries());
            node.pending.clear();
            for (const [requestId, item] of pending) {
                clearTimeout(item.timer);
                item.callback(clientError(
                    code,
                    message,
                    requestId,
                    item.command,
                ));
            }
        };

        node.disconnect = (message) => {
            const socket = node.socket;
            node.socket = null;
            node.buffer = Buffer.alloc(0);
            node.setConnectionState(false, message);
            node.failPending("connection_lost", message);
            if (socket !== null && !socket.destroyed) {
                socket.destroy();
            }
        };

        node.cancelReconnect = () => {
            if (node.reconnectTimer !== null) {
                clearTimeout(node.reconnectTimer);
                node.reconnectTimer = null;
            }
        };

        node.controlConnection = (message) => {
            if (!isPlainObject(message)) {
                throw new Error("msg.payload must be an object");
            }
            const action = message.action;
            if (action === "disconnect") {
                node.desiredConnected = false;
                node.cancelReconnect();
                node.disconnect("Disconnected by user");
                return node.endpointSnapshot();
            }
            if (action !== "connect") {
                throw new Error("msg.payload.action must be connect or disconnect");
            }

            const host = String(message.host || "").trim();
            const port = Number(message.port);
            if (!host) {
                throw new Error("msg.payload.host must not be empty");
            }
            if (!Number.isInteger(port) || port < 1 || port > 65535) {
                throw new Error("msg.payload.port must be an integer in 1..65535");
            }

            const endpointChanged = node.host !== host || node.port !== port;
            node.host = host;
            node.port = port;
            node.desiredConnected = true;
            node.cancelReconnect();
            if (node.socket !== null && !endpointChanged) {
                return node.endpointSnapshot();
            }
            if (node.socket !== null) {
                node.disconnect("Motion Server endpoint changed");
            }
            node.connect();
            return node.endpointSnapshot();
        };

        node.routeMessage = (message) => {
            if (message.type === "system/feedback" && !("request_id" in message)) {
                for (const listener of node.feedbackListeners) {
                    listener(message);
                }
                return;
            }
            if (!("request_id" in message)) {
                return;
            }
            const requestId = String(message.request_id);
            const pending = node.pending.get(requestId);
            if (!pending) {
                return;
            }
            node.pending.delete(requestId);
            clearTimeout(pending.timer);
            pending.callback(null, message);
        };

        node.consumeData = (chunk) => {
            node.buffer = Buffer.concat([node.buffer, chunk]);
            while (true) {
                const newline = node.buffer.indexOf(0x0a);
                if (newline < 0) {
                    return;
                }
                const line = node.buffer.subarray(0, newline);
                node.buffer = node.buffer.subarray(newline + 1);
                if (line.toString("utf8").trim() === "") {
                    continue;
                }
                let message;
                try {
                    message = JSON.parse(line.toString("utf8"));
                } catch (error) {
                    node.disconnect(`Motion Server protocol error: ${error.message}`);
                    return;
                }
                if (!isPlainObject(message)) {
                    node.disconnect("Motion Server protocol error: message must be an object");
                    return;
                }
                node.routeMessage(message);
            }
        };

        node.scheduleReconnect = () => {
            if (
                node.stopped
                || !node.desiredConnected
                || node.connected
                || node.reconnectTimer !== null
            ) {
                return;
            }
            node.reconnectTimer = setTimeout(() => {
                node.reconnectTimer = null;
                node.connect();
            }, RECONNECT_PERIOD_MS);
        };

        node.connect = () => {
            if (node.stopped || !node.desiredConnected || node.socket !== null) {
                return;
            }
            let socket;
            try {
                socket = net.createConnection({ host: node.host, port: node.port });
            } catch (error) {
                node.lastError = error.message;
                node.scheduleReconnect();
                return;
            }
            node.socket = socket;
            socket.setNoDelay(true);
            socket.on("connect", () => {
                if (node.socket !== socket || node.stopped) {
                    socket.destroy();
                    return;
                }
                node.buffer = Buffer.alloc(0);
                node.cancelReconnect();
                node.setConnectionState(true, "");
            });
            socket.on("data", (chunk) => {
                if (node.socket === socket) {
                    node.consumeData(chunk);
                }
            });
            socket.on("error", (error) => {
                if (node.socket === socket) {
                    node.lastError = error.message;
                }
            });
            socket.on("close", () => {
                if (node.socket === socket) {
                    const message = node.lastError || "Motion Server connection closed";
                    node.disconnect(message);
                }
                node.scheduleReconnect();
            });
        };

        node.on("close", (removed, done) => {
            node.stopped = true;
            node.cancelReconnect();
            node.disconnect("Motion Server connection stopped");
            node.feedbackListeners.clear();
            node.statusListeners.clear();
            done();
        });

        if (node.desiredConnected) {
            node.connect();
        }
    }

    function MotionServerConnectionControlNode(config) {
        RED.nodes.createNode(this, config);
        const node = this;
        node.connection = RED.nodes.getNode(config.connection);
        if (!node.connection) {
            node.status({ fill: "red", shape: "ring", text: "missing connection" });
            return;
        }
        const sendEndpoint = (endpoint) => node.send({
            topic: "motion-server/endpoint",
            payload: endpoint,
        });
        const unsubscribe = node.connection.subscribeStatus((status) => {
            setNodeConnectionStatus(node, status);
        });
        setImmediate(() => sendEndpoint(node.connection.endpointSnapshot()));
        node.on("input", (msg, send, done) => {
            try {
                const endpoint = node.connection.controlConnection(msg.payload);
                sendEndpoint(endpoint);
                done();
            } catch (error) {
                done(error);
            }
        });
        node.on("close", unsubscribe);
    }

    function MotionServerRequestNode(config) {
        RED.nodes.createNode(this, config);
        const node = this;
        node.connection = RED.nodes.getNode(config.connection);
        node.timeout = config.timeout === undefined || config.timeout === null
            || config.timeout === ""
            ? null
            : Number(config.timeout);
        if (!node.connection) {
            node.status({ fill: "red", shape: "ring", text: "missing connection" });
            return;
        }
        const unsubscribe = node.connection.subscribeStatus((status) => {
            setNodeConnectionStatus(node, status);
        });
        node.on("input", (msg, send, done) => {
            const output = { ...msg };
            node.connection.request(msg.payload, node.timeout, (error, response) => {
                if (error) {
                    output.payload = error;
                    send([null, output]);
                } else {
                    output.payload = response;
                    send([output, null]);
                }
                done();
            });
        });
        node.on("close", unsubscribe);
    }

    function MotionServerFeedbackNode(config) {
        RED.nodes.createNode(this, config);
        const node = this;
        node.connection = RED.nodes.getNode(config.connection);
        if (!node.connection) {
            node.status({ fill: "red", shape: "ring", text: "missing connection" });
            return;
        }
        const unsubscribeFeedback = node.connection.subscribeFeedback((feedback) => {
            node.send({ topic: "system/feedback", payload: feedback });
        });
        const unsubscribeStatus = node.connection.subscribeStatus((status) => {
            setNodeConnectionStatus(node, status);
        });
        node.on("close", () => {
            unsubscribeFeedback();
            unsubscribeStatus();
        });
    }

    function MotionServerConnectionStatusNode(config) {
        RED.nodes.createNode(this, config);
        const node = this;
        node.connection = RED.nodes.getNode(config.connection);
        if (!node.connection) {
            node.status({ fill: "red", shape: "ring", text: "missing connection" });
            return;
        }
        const unsubscribe = node.connection.subscribeStatus((status) => {
            setNodeConnectionStatus(node, status);
            node.send({
                topic: "motion-server/connection",
                payload: status,
            });
        });
        node.on("close", unsubscribe);
    }

    RED.nodes.registerType("motion-server-connection", MotionServerConnectionNode);
    RED.nodes.registerType(
        "motion-server-connection-control",
        MotionServerConnectionControlNode,
    );
    RED.nodes.registerType("motion-server-request", MotionServerRequestNode);
    RED.nodes.registerType("motion-server-feedback", MotionServerFeedbackNode);
    RED.nodes.registerType(
        "motion-server-connection-status",
        MotionServerConnectionStatusNode,
    );
};

function positiveMilliseconds(value, fallback) {
    if (value === undefined || value === null || value === "") {
        return fallback;
    }
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds <= 0) {
        return fallback;
    }
    return Math.round(seconds * 1000);
}

function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validateRequest(message) {
    if (!isPlainObject(message)) {
        return "msg.payload must be an object";
    }
    if (typeof message.cmd !== "string" || message.cmd.trim() === "") {
        return "msg.payload.cmd must be a non-empty string";
    }
    if (Object.prototype.hasOwnProperty.call(message, "request_id")) {
        return "request_id is managed by the Motion Server Connection";
    }
    return "";
}

function clientError(code, message, requestId, command) {
    return {
        type: "motion-server/client-error",
        code,
        message,
        request_id: requestId,
        command: typeof command === "string" ? command : "",
    };
}

function setNodeConnectionStatus(node, status) {
    if (status.connected) {
        node.status({ fill: "green", shape: "dot", text: "connected" });
    } else {
        node.status({
            fill: "red",
            shape: "ring",
            text: status.last_error || "disconnected",
        });
    }
}
