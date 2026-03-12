"""Tests for the length-prefixed JSON protocol module.

Covers:
    - Basic send/recv roundtrip across a real TCP socket pair.
    - Rapid sequential sends (verifies framing under TCP coalescing).
    - Large message handling.
    - Clean EOF detection (peer closes connection gracefully).
    - Dirty EOF detection (connection drops mid-message).
    - Oversized payload rejection (MAX_PAYLOAD_SIZE guard).
    - Empty/invalid JSON handling.
"""

from __future__ import annotations

import json
import socket
import struct

import pytest

from src.protocol import (
    HEADER_FORMAT,
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    recv_message,
    send_message,
)

# ---------------------------------------------------------------------------
# Basic roundtrip
# ---------------------------------------------------------------------------


class TestSendRecvRoundtrip:
    """Verify that send_message and recv_message form a correct pair."""

    def test_simple_dict(self, socket_pair: tuple[socket.socket, socket.socket]):
        """A simple dict survives a send/recv cycle intact."""
        client, server = socket_pair
        original = {"type": "CONNECT"}

        send_message(client, original)
        received = recv_message(server)

        assert received == original

    def test_nested_payload(self, socket_pair: tuple[socket.socket, socket.socket]):
        """A message with nested structures roundtrips correctly."""
        client, server = socket_pair
        original = {
            "type": "PLACE_SHIPS",
            "ships": [
                {"name": "Carrier", "row": 0, "col": 0, "horizontal": True},
                {"name": "Destroyer", "row": 8, "col": 0, "horizontal": False},
            ],
        }

        send_message(client, original)
        received = recv_message(server)

        assert received == original

    def test_numeric_values(self, socket_pair: tuple[socket.socket, socket.socket]):
        """Integer and float values are preserved through JSON serialization."""
        client, server = socket_pair
        original = {"row": 3, "col": 5, "confidence": 0.95, "flag": True}

        send_message(client, original)
        received = recv_message(server)

        assert received == original

    def test_bidirectional(self, socket_pair: tuple[socket.socket, socket.socket]):
        """Both sides can send and receive on the same socket pair."""
        client, server = socket_pair

        send_message(client, {"from": "client"})
        assert recv_message(server) == {"from": "client"}

        send_message(server, {"from": "server"})
        assert recv_message(client) == {"from": "server"}


# ---------------------------------------------------------------------------
# Rapid sequential sends (TCP coalescing stress test)
# ---------------------------------------------------------------------------


class TestRapidSend:
    """Verify framing integrity when multiple messages arrive in one recv()."""

    def test_ten_sequential_messages(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """10 messages sent back-to-back are all received intact and in order."""
        client, server = socket_pair

        for i in range(10):
            send_message(client, {"type": "RESULT", "index": i})

        for i in range(10):
            msg = recv_message(server)
            assert msg is not None
            assert msg["index"] == i

    def test_fifty_sequential_messages(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """50 rapid messages all arrive intact (stress test for framing)."""
        client, server = socket_pair
        count = 50

        for i in range(count):
            send_message(client, {"seq": i, "data": f"message-{i}"})

        for i in range(count):
            msg = recv_message(server)
            assert msg is not None
            assert msg["seq"] == i
            assert msg["data"] == f"message-{i}"


# ---------------------------------------------------------------------------
# Large message handling
# ---------------------------------------------------------------------------


class TestLargeMessages:
    """Verify that messages approaching MAX_PAYLOAD_SIZE work correctly."""

    def test_large_payload(self, socket_pair: tuple[socket.socket, socket.socket]):
        """A message with a large string value roundtrips correctly."""
        client, server = socket_pair
        # Create a payload close to 100 KB.
        original = {"type": "DATA", "blob": "x" * 100_000}

        send_message(client, original)
        received = recv_message(server)

        assert received == original
        assert len(received["blob"]) == 100_000


# ---------------------------------------------------------------------------
# EOF handling
# ---------------------------------------------------------------------------


class TestEOFHandling:
    """Verify correct behavior when the peer closes the connection."""

    def test_clean_eof_returns_none(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """recv_message returns None when the peer closes cleanly."""
        client, server = socket_pair

        # Close the sender side.
        client.close()

        result = recv_message(server)
        assert result is None

    def test_message_then_eof(self, socket_pair: tuple[socket.socket, socket.socket]):
        """A message followed by EOF: message is received, then None."""
        client, server = socket_pair

        send_message(client, {"type": "GOODBYE"})
        client.close()

        msg = recv_message(server)
        assert msg == {"type": "GOODBYE"}

        eof = recv_message(server)
        assert eof is None

    def test_dirty_eof_raises_connection_error(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """A partial header (connection drops mid-header) raises ConnectionError."""
        client, server = socket_pair

        # Manually send only 2 of the 4 header bytes, then close.
        client.sendall(b"\x00\x00")
        client.close()

        with pytest.raises(ConnectionError):
            recv_message(server)


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    """Verify the protocol rejects malformed or oversized payloads."""

    def test_oversized_payload_rejected(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """A length header exceeding MAX_PAYLOAD_SIZE raises ValueError."""
        client, server = socket_pair

        # Craft a header claiming a payload larger than the limit.
        fake_header = struct.pack(HEADER_FORMAT, MAX_PAYLOAD_SIZE + 1)
        client.sendall(fake_header)

        with pytest.raises(ValueError, match="exceeds maximum"):
            recv_message(server)

    def test_zero_length_payload_rejected(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """A zero-length payload header raises ValueError."""
        client, server = socket_pair

        fake_header = struct.pack(HEADER_FORMAT, 0)
        client.sendall(fake_header)

        with pytest.raises(ValueError, match="zero-length"):
            recv_message(server)

    def test_invalid_json_raises_decode_error(
        self, socket_pair: tuple[socket.socket, socket.socket]
    ):
        """A valid header followed by non-JSON bytes raises JSONDecodeError."""
        client, server = socket_pair

        garbage = b"this is not json"
        header = struct.pack(HEADER_FORMAT, len(garbage))
        client.sendall(header + garbage)

        with pytest.raises(json.JSONDecodeError):
            recv_message(server)


# ---------------------------------------------------------------------------
# Header constant sanity checks
# ---------------------------------------------------------------------------


class TestProtocolConstants:
    """Verify the module-level constants are correct."""

    def test_header_size_is_four_bytes(self):
        assert HEADER_SIZE == 4

    def test_header_format_is_big_endian_uint32(self):
        assert HEADER_FORMAT == "!I"

    def test_max_payload_is_one_megabyte(self):
        assert MAX_PAYLOAD_SIZE == 1_048_576
