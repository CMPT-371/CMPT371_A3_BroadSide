"""
CMPT 371 A3: BroadSide — TCP Game Server

Purpose:
    Implements the authoritative game server for BroadSide. The server
    listens for incoming TCP connections, matches pairs of players through
    a matchmaking queue, and spawns an isolated game session thread for
    each pair.

Architecture:
    The server uses a multithreaded design:

        Main Thread (start_server)
        │
        ├── accept() loop
        │   ├── Client connects → recv CONNECT → add to matchmaking queue
        │   └── Queue has 2 players → pop both → spawn game_session thread
        │
        └── game_session Thread (one per matched pair, daemon=True)
            ├── Send WELCOME (assign player_id 1 and 2)
            ├── Wait for PLACE_SHIPS from both players
            ├── Send ALL_READY → transition to gameplay
            ├── Turn loop: recv FIRE → validate → broadcast RESULT
            └── GAME_OVER or disconnect → close both sockets

    The server is the single source of truth for all game state. Clients
    are thin renderers that send actions and display results — they cannot
    modify the board or skip turns.

Thread safety:
    The matchmaking queue is the only shared mutable state between threads.
    It is protected by a threading.Lock. Each game_session thread owns its
    own GameState instance with no sharing.

References:
    - Python threading: https://docs.python.org/3/library/threading.html
    - Python socket: https://docs.python.org/3/library/socket.html
    - CMPT 371 course tutorial: "TCP Echo Server" (socket boilerplate).
    - Claude Code was used to assist with structuring the module layout.
"""

from __future__ import annotations

import logging
import socket
import threading

from src.game_logic import GameState
from src.protocol import recv_message, send_message

# ---------------------------------------------------------------------------
# Server configuration
# ---------------------------------------------------------------------------

HOST: str = "127.0.0.1"
PORT: int = 5050

# Configure structured logging for server events.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BroadSide-Server")

# ---------------------------------------------------------------------------
# Matchmaking state (shared between main thread and session threads)
# ---------------------------------------------------------------------------

# Holds connected clients waiting to be paired into a game.
matchmaking_queue: list[socket.socket] = []
queue_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Game session (runs on a dedicated daemon thread per matched pair)
# ---------------------------------------------------------------------------

def game_session(conn_p1: socket.socket, conn_p2: socket.socket) -> None:
    """Run an isolated game loop for two matched players.

    This function executes on a daemon thread and manages the full
    game lifecycle: handshake → setup → gameplay → termination.

    Args:
        conn_p1: TCP socket for Player 1.
        conn_p2: TCP socket for Player 2.
    """
    raise NotImplementedError("Phase 2: server game_session")


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

def start_server(host: str = HOST, port: int = PORT) -> None:
    """Start the BroadSide TCP server.

    Binds to the given host and port, listens for incoming connections,
    and matches players into game sessions.

    Args:
        host: The IP address to bind to (default: 127.0.0.1).
        port: The TCP port to listen on (default: 5050).
    """
    raise NotImplementedError("Phase 2: start_server")


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_server()
