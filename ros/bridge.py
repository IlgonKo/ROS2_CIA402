from pathlib import Path
import json
import os
import socket
import sys
import threading
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
from std_msgs.msg import Int32MultiArray
from std_msgs.msg import Empty

from ros.axis_runtime_config import get_axis_count


DEFAULT_HOST = "192.168.0.12"
DEFAULT_PORT = 15000
RECONNECT_PERIOD = 1.0


class Cia402CommandBridgeNode(Node):
    def __init__(self):
        super().__init__("ros_command_bridge")

        self.axis_count = get_axis_count()
        self.host = os.environ.get("CIA402_PYSOEM_HOST", DEFAULT_HOST)
        self.port = int(os.environ.get("CIA402_PYSOEM_PORT", DEFAULT_PORT))
        self.sock = None
        self.sock_file = None
        self.sock_lock = threading.Lock()
        self.stop_event = threading.Event()

        self.target_sub = self.create_subscription(
            Float64MultiArray,
            "/target_positions",
            self.target_position_callback,
            10,
        )

        self.motion_limit_sub = self.create_subscription(
            Float64MultiArray,
            "/motion_limits",
            self.motion_limit_callback,
            10,
        )
        self.alarm_ack_sub = self.create_subscription(
            Empty,
            "/alarm_ack",
            self.alarm_ack_callback,
            10,
        )

        self.target_position_pub = self.create_publisher(
            Float64MultiArray,
            "/target_position_feedback",
            10,
        )
        self.actual_position_pub = self.create_publisher(
            Float64MultiArray,
            "/actual_positions",
            10,
        )
        self.actual_velocity_pub = self.create_publisher(
            Float64MultiArray,
            "/actual_velocities",
            10,
        )
        self.statusword_pub = self.create_publisher(
            Int32MultiArray,
            "/statuswords",
            10,
        )
        self.diagnostics_pub = self.create_publisher(
            Int32MultiArray,
            "/drive_diagnostics",
            10,
        )
        self.motion_limit_pub = self.create_publisher(
            Float64MultiArray,
            "/motion_limits_feedback",
            10,
        )

        self.reader_thread = threading.Thread(
            target=self.connection_loop,
            daemon=True,
        )
        self.reader_thread.start()

        self.get_logger().info(
            f"CIA402 bridge started. axes={self.axis_count} "
            f"target={self.host}:{self.port}"
        )

    def target_position_callback(self, msg):
        if len(msg.data) < self.axis_count:
            self.get_logger().warn(
                f"Invalid /target_positions. Expected {self.axis_count} values."
            )
            return

        self.send_json(
            {
                "type": "target_positions",
                "positions": [
                    float(msg.data[index])
                    for index in range(self.axis_count)
                ],
            }
        )
        self.get_logger().info(
            "Forwarded target positions to PySOEM server: "
            f"{list(msg.data[:self.axis_count])}"
        )

    def motion_limit_callback(self, msg):
        expected_values = self.axis_count * 4
        if len(msg.data) < expected_values:
            self.get_logger().warn(
                f"Invalid /motion_limits. Expected {expected_values} values."
            )
            return

        limits = []
        for index in range(self.axis_count):
            offset = index * 4
            limits.append(
                [
                    float(msg.data[offset]),
                    float(msg.data[offset + 1]),
                    float(msg.data[offset + 2]),
                    float(msg.data[offset + 3]),
                ]
            )

        self.send_json(
            {
                "type": "motion_limits",
                "limits": limits,
            }
        )
        self.get_logger().info(
            f"Forwarded motion limits to PySOEM server: {limits}"
        )

    def alarm_ack_callback(self, _msg):
        self.send_json(
            {
                "type": "alarm_ack",
            }
        )
        self.get_logger().info("Forwarded alarm ack to PySOEM server")

    def connection_loop(self):
        while not self.stop_event.is_set():
            try:
                self.connect()
                self.read_loop()
            except OSError as exc:
                self.get_logger().warn(f"Bridge disconnected: {exc}")
            except Exception as exc:
                self.get_logger().error(f"Bridge error: {exc}")
            finally:
                self.close_socket()

            time.sleep(RECONNECT_PERIOD)

    def connect(self):
        self.get_logger().info(f"Connecting to PySOEM server {self.host}:{self.port}")
        sock = socket.create_connection((self.host, self.port), timeout=5.0)
        sock.settimeout(None)
        sock_file = sock.makefile("r", encoding="utf-8", newline="\n")

        with self.sock_lock:
            self.sock = sock
            self.sock_file = sock_file

        self.get_logger().info("Connected to PySOEM server")

    def read_loop(self):
        while not self.stop_event.is_set():
            line = self.sock_file.readline()
            if not line:
                raise OSError("server closed connection")

            message = json.loads(line)
            if message.get("type") == "feedback":
                self.publish_feedback(message)
            elif message.get("type") == "log":
                self.get_logger().info(message.get("text", ""))

    def publish_feedback(self, message):
        self.publish_float_array(
            self.target_position_pub,
            message.get("target_positions", []),
        )
        self.publish_float_array(
            self.actual_position_pub,
            message.get("actual_positions", []),
        )
        self.publish_float_array(
            self.actual_velocity_pub,
            message.get("actual_velocities", []),
        )
        self.publish_statuswords(message.get("statuswords", []))
        self.publish_diagnostics(message.get("diagnostics", []))
        self.publish_float_array(
            self.motion_limit_pub,
            message.get("motion_limits", []),
        )

    def send_json(self, message):
        payload = (json.dumps(message) + "\n").encode("utf-8")

        with self.sock_lock:
            if self.sock is None:
                self.get_logger().warn("PySOEM server is not connected yet")
                return

            self.sock.sendall(payload)

    def close_socket(self):
        with self.sock_lock:
            if self.sock_file is not None:
                self.sock_file.close()
                self.sock_file = None

            if self.sock is not None:
                self.sock.close()
                self.sock = None

    def publish_float_array(self, publisher, values):
        msg = Float64MultiArray()
        msg.data = [float(value) for value in values]
        publisher.publish(msg)

    def publish_statuswords(self, values):
        msg = Int32MultiArray()
        msg.data = [int(value) for value in values]
        self.statusword_pub.publish(msg)

    def publish_diagnostics(self, diagnostics):
        values = []
        for item in diagnostics:
            values.extend(
                [
                    int(item.get("error_code", 0))
                    if isinstance(item.get("error_code", 0), int)
                    else -1,
                    int(item.get("error_register", 0))
                    if isinstance(item.get("error_register", 0), int)
                    else -1,
                    int(item.get("mode_display", 0))
                    if isinstance(item.get("mode_display", 0), int)
                    else -1,
                ]
            )

        msg = Int32MultiArray()
        msg.data = values
        self.diagnostics_pub.publish(msg)

    def close(self):
        self.stop_event.set()
        self.close_socket()


def main(args=None):
    rclpy.init(args=args)
    node = Cia402CommandBridgeNode()

    try:
        rclpy.spin(node)
    finally:
        node.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
