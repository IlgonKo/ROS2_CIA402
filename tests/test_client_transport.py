import unittest
from unittest.mock import patch

from motion_server.api.encoder import (
    MAX_CLIENT_OUTPUT_BUFFER_BYTES,
    send_client_message,
)
from motion_server.app.client_transport import flush_client_output, service_client


class _ReceiveWouldBlockSocket:
    def recv(self, _size):
        raise BlockingIOError(10035, "operation would block")


class _BufferedSendSocket:
    def __init__(self):
        self.calls = 0
        self.sent = bytearray()

    def send(self, payload):
        self.calls += 1
        if self.calls == 1:
            raise BlockingIOError(10035, "operation would block")
        count = min(3, len(payload))
        self.sent.extend(payload[:count])
        return count


class ClientTransportTests(unittest.TestCase):
    @patch("motion_server.app.client_transport.select.select")
    def test_receive_would_block_keeps_client_connected(self, select_mock):
        connection = _ReceiveWouldBlockSocket()
        select_mock.return_value = ([connection], [], [])
        client = {"conn": connection, "buffer": ""}

        self.assertTrue(service_client(client, None, {}, lambda *_: None))

    def test_output_is_retained_across_would_block_and_partial_send(self):
        connection = _BufferedSendSocket()
        client = {"conn": connection, "output_buffer": bytearray()}
        send_client_message(client, {"result": "success"})
        expected = bytes(client["output_buffer"])

        flush_client_output(client)
        self.assertEqual(bytes(client["output_buffer"]), expected)

        while client["output_buffer"]:
            flush_client_output(client)

        self.assertEqual(bytes(connection.sent), expected)

    def test_output_buffer_accepts_catalog_sized_message(self):
        client = {"conn": _BufferedSendSocket(), "output_buffer": bytearray()}

        send_client_message(client, {"objects": "x" * (2 * 1024 * 1024)})

        self.assertGreater(len(client["output_buffer"]), 2 * 1024 * 1024)
        self.assertLessEqual(
            len(client["output_buffer"]),
            MAX_CLIENT_OUTPUT_BUFFER_BYTES,
        )

    def test_output_buffer_rejects_accumulation_above_limit(self):
        client = {
            "conn": _BufferedSendSocket(),
            "output_buffer": bytearray(MAX_CLIENT_OUTPUT_BUFFER_BYTES),
        }

        with self.assertRaisesRegex(ConnectionError, "output buffer limit"):
            send_client_message(client, {"result": "success"})


if __name__ == "__main__":
    unittest.main()
