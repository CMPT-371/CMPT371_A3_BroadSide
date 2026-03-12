"""
CMPT 371 A3: BroadSide — Network Protocol Module

Purpose:
    Provides reliable, length-prefixed JSON message framing over TCP sockets.
    Every message sent through this module is structured as:

        [4-byte big-endian uint32 length][UTF-8 JSON payload]

    This framing guarantees that each JSON message is received atomically,
    regardless of how the underlying TCP stack segments or coalesces bytes.

Why length-prefixed instead of newline-delimited?
    TCP is a byte-stream protocol with no built-in concept of message boundaries.
    A newline delimiter ('\\n') breaks if the JSON payload contains embedded
    newlines, and naive splitting can silently drop partial messages.
    Length-prefixed framing is the industry standard (used by HTTP/2, gRPC,
    Kafka, and most binary protocols) because it is unambiguous and robust.

Architecture:
    This module is a pure utility layer with no game logic or state.
    Both server.py and client.py import send_message() and recv_message()
    to communicate through the same framing contract.

References:
    - Python struct module: https://docs.python.org/3/library/struct.html
    - Python socket HOWTO: https://docs.python.org/3/howto/sockets.html
    - Claude Code was used to assist with structuring the module layout.
"""

from __future__ import annotations

import json
import logging
import socket
import struct

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# The framing header is a single 4-byte big-endian unsigned integer.
# This supports messages up to ~4 GB, far exceeding anything Battleship needs.
# Format string "!I" means: network byte order (big-endian), unsigned int.
HEADER_FORMAT: str = "!I"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 4 bytes

# Maximum allowed payload size (1 MB). Prevents a malformed or malicious
# length header from causing the receiver to allocate unbounded memory.
MAX_PAYLOAD_SIZE: int = 1_048_576

# Module logger — inherits from the root logger's configuration.
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_message(sock: socket.socket, message: dict) -> None:
    """Serialize a dictionary to JSON and send it as a length-prefixed frame.

    The frame layout on the wire is:

        ┌──────────────────┬────────────────────────────┐
        │ 4-byte uint32 BE │ UTF-8 JSON payload bytes   │
        │ (payload length) │ (exactly N bytes)           │
        └──────────────────┴────────────────────────────┘

    Uses ``sendall()`` to guarantee the entire frame is transmitted, even
    if the OS-level TCP send buffer is smaller than the frame.

    Args:
        sock: A connected TCP socket (``AF_INET``, ``SOCK_STREAM``).
        message: A JSON-serializable dictionary (e.g., ``{"type": "FIRE", "row": 3, "col": 5}``).

    Raises:
        TypeError: If *message* is not JSON-serializable.
        OSError: If the socket is closed or broken mid-send.
    """
    # Serialize the dict to a compact JSON byte string (no extra whitespace).
    payload: bytes = json.dumps(message, separators=(",", ":")).encode("utf-8")

    # Pack the payload length into a 4-byte big-endian header.
    header: bytes = struct.pack(HEADER_FORMAT, len(payload))

    # Send header + payload as a single atomic write.
    # sendall() blocks until every byte is delivered to the OS send buffer.
    sock.sendall(header + payload)

    logger.debug("Sent %d-byte message: %s", len(payload), message.get("type", "?"))


def recv_message(sock: socket.socket) -> dict | None:
    """Read a single length-prefixed JSON message from the TCP socket.

    Protocol:
        1. Read exactly 4 bytes → the big-endian uint32 payload length.
        2. Read exactly *length* bytes → the UTF-8 JSON payload.
        3. Deserialize and return as a ``dict``.

    Returns:
        The deserialized message dictionary, or ``None`` if the peer
        closed the connection gracefully (``recv`` returned ``b""``).

    Raises:
        ConnectionError: If the connection drops mid-message (partial header
            or partial payload received before EOF).
        ValueError: If the payload length exceeds ``MAX_PAYLOAD_SIZE``
            (protects against malformed or malicious headers).
        json.JSONDecodeError: If the payload is not valid JSON.
    """
    # ── Step 1: Read the 4-byte length header ──
    header_bytes: bytes | None = _recv_exactly(sock, HEADER_SIZE)

    if header_bytes is None:
        # Peer closed the connection cleanly — no more data coming.
        logger.debug("Connection closed by peer (clean EOF on header read).")
        return None

    # Unpack the big-endian unsigned 32-bit integer.
    # struct.unpack returns a tuple; we extract the single value.
    (payload_length,) = struct.unpack(HEADER_FORMAT, header_bytes)

    # ── Step 2: Validate payload length ──
    if payload_length > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload length {payload_length:,} bytes exceeds maximum "
            f"allowed size of {MAX_PAYLOAD_SIZE:,} bytes."
        )

    if payload_length == 0:
        raise ValueError("Received a zero-length payload (empty message).")

    # ── Step 3: Read exactly payload_length bytes ──
    payload_bytes: bytes | None = _recv_exactly(sock, payload_length)

    if payload_bytes is None:
        # Connection dropped mid-message — we got the header but not the payload.
        raise ConnectionError(
            f"Connection lost while reading {payload_length}-byte payload "
            f"(received header but peer closed before payload was complete)."
        )

    # ── Step 4: Decode and deserialize ──
    message: dict = json.loads(payload_bytes.decode("utf-8"))

    logger.debug(
        "Received %d-byte message: %s", payload_length, message.get("type", "?")
    )

    return message


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _recv_exactly(sock: socket.socket, num_bytes: int) -> bytes | None:
    """Read exactly *num_bytes* from the socket, handling TCP fragmentation.

    TCP's ``recv()`` may return fewer bytes than requested because the OS
    delivers data as it arrives from the network. This helper loops until
    the full requested amount has been accumulated.

    Args:
        sock: A connected TCP socket.
        num_bytes: The exact number of bytes to read.

    Returns:
        A ``bytes`` object of exactly *num_bytes* length, or ``None`` if
        the peer closed the connection before any data was sent (clean EOF).

    Raises:
        ConnectionError: If the connection closes *after* some but not all
            bytes have been received (partial read indicates a broken stream).
    """
    # Pre-allocate a bytearray to accumulate chunks without repeated concatenation.
    buffer = bytearray(num_bytes)
    bytes_received: int = 0

    while bytes_received < num_bytes:
        # Request only the remaining bytes to avoid over-reading.
        chunk: bytes = sock.recv(num_bytes - bytes_received)

        if not chunk:
            # recv() returned b"" — the peer closed the connection.
            if bytes_received == 0:
                # Clean EOF: nothing was read yet, so no data was lost.
                return None

            # Dirty EOF: we have a partial read, meaning the stream is corrupt.
            raise ConnectionError(
                f"Connection closed after receiving {bytes_received} of "
                f"{num_bytes} expected bytes (incomplete message)."
            )

        # Copy the chunk into the pre-allocated buffer at the correct offset.
        buffer[bytes_received : bytes_received + len(chunk)] = chunk
        bytes_received += len(chunk)

    return bytes(buffer)
