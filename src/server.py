"""
CMPT 371 A3: BroadSide - TCP Game Server

Purpose:
    Implements the authoritative game server for BroadSide. The server
    listens for incoming TCP connections, matches pairs of players through
    a matchmaking queue, and spawns an isolated game session thread for
    each pair.

Architecture:
    The server uses a multithreaded design:

        Main Thread (start_server)
        |
        +-- accept() loop
        |   +-- Client connects -> recv CONNECT -> add to matchmaking queue
        |   +-- Queue has 2 players -> pop both -> spawn game_session thread
        |
        +-- game_session Thread (one per matched pair, daemon=True)
            +-- Send WELCOME (assign player_id 1 and 2)
            +-- Wait for PLACE_SHIPS from both players
            +-- Send ALL_READY -> transition to gameplay
            +-- Turn loop: recv FIRE -> validate -> broadcast RESULT
            +-- GAME_OVER or disconnect -> close both sockets

    The server is the single source of truth for all game state. Clients
    are thin renderers that send actions and display results - they cannot
    modify the board or skip turns.

Thread safety:
    The matchmaking queue is the only shared mutable state between threads.
    It is protected by a threading.Lock. Each game_session thread owns its
    own GameState instance with no sharing.

References:
    - Python threading: https://docs.python.org/3/library/threading.html
    - Python socket: https://docs.python.org/3/library/socket.html
    - CMPT 371 course tutorial: "TCP Echo Server" (socket boilerplate).
    - Python threading and socket documentation.
"""

from __future__ import annotations

import contextlib
import logging
import select
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
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_send(conn: socket.socket, message: dict, label: str = "") -> bool:
    """Send a message to a client, returning False if the connection is dead.

    Wraps ``send_message`` in a try/except so callers never crash from a
    broken pipe or reset connection.  This is used throughout the game
    session to protect every outbound send.

    Args:
        conn: The client TCP socket to send on.
        message: The protocol message dict to serialize and send.
        label: A human-readable label for logging (e.g., "P1").

    Returns:
        True if the message was sent successfully, False on any error.
    """
    try:
        send_message(conn, message)
        return True
    except (ConnectionError, BrokenPipeError, ConnectionResetError, OSError) as exc:
        logger.warning("Send failed for %s: %s", label, exc)
        return False


def _safe_recv(conn: socket.socket, label: str = "") -> dict | None:
    """Receive a message from a client, returning None on any error or EOF.

    Wraps ``recv_message`` in a try/except so callers can simply check
    for None instead of handling multiple exception types.

    Args:
        conn: The client TCP socket to read from.
        label: A human-readable label for logging (e.g., "P1").

    Returns:
        The received message dict, or None if the connection is
        closed, broken, or encountered any error.
    """
    try:
        return recv_message(conn)
    except (
        ConnectionError,
        BrokenPipeError,
        ConnectionResetError,
        OSError,
        ValueError,
    ) as exc:
        logger.warning("Recv failed for %s: %s", label, exc)
        return None


def _close_socket(conn: socket.socket, label: str = "") -> None:
    """Close a socket silently, ignoring errors if already closed.

    Args:
        conn: The socket to close.
        label: A human-readable label for logging.
    """
    with contextlib.suppress(OSError):
        conn.close()
    logger.debug("Closed socket for %s.", label)


def _notify_and_close(
    survivor: socket.socket,
    disconnected: socket.socket,
    survivor_label: str,
    disconnected_label: str,
) -> None:
    """Notify one player that their opponent disconnected, then close both.

    Args:
        survivor: The socket of the player still connected.
        disconnected: The socket of the player who dropped.
        survivor_label: Logging label for the survivor (e.g., "P1").
        disconnected_label: Logging label for the disconnected player.
    """
    logger.info("%s disconnected. Notifying %s.", disconnected_label, survivor_label)
    _safe_send(
        survivor,
        {
            "type": "OPPONENT_DISCONNECTED",
            "message": "Your opponent has disconnected. You win!",
        },
        survivor_label,
    )
    _close_socket(survivor, survivor_label)
    _close_socket(disconnected, disconnected_label)


# ---------------------------------------------------------------------------
# Game session (runs on a dedicated daemon thread per matched pair)
# ---------------------------------------------------------------------------


def game_session(conn_p1: socket.socket, conn_p2: socket.socket) -> None:
    """Run an isolated game loop for two matched players.

    This function executes on a daemon thread and manages the full
    game lifecycle: handshake -> setup -> gameplay -> termination.

    The session owns a ``GameState`` instance that serves as the single
    source of truth.  Every client action is validated through it before
    any state change or broadcast occurs.

    Lifecycle:
        1. Send WELCOME to both players (assign player_id 1 and 2).
        2. Wait for PLACE_SHIPS from both players (interleaved).
        3. Send ALL_READY + initial YOUR_TURN / OPPONENT_TURN.
        4. Turn loop: recv FIRE -> validate -> broadcast RESULT.
        5. On game over or disconnect -> close both sockets.

    Args:
        conn_p1: TCP socket for Player 1.
        conn_p2: TCP socket for Player 2.
    """
    # Map player_id to their socket for easy lookup.
    connections: dict[int, socket.socket] = {1: conn_p1, 2: conn_p2}
    labels: dict[int, str] = {1: "P1", 2: "P2"}

    logger.info("Game session started between P1 and P2.")

    # -- Phase 1: Handshake (WELCOME) ------------------------------------
    # Assign each player their ID and inform them the connection succeeded.

    for pid in (1, 2):
        ok = _safe_send(
            connections[pid],
            {
                "type": "WELCOME",
                "player_id": pid,
                "message": f"Welcome, Player {pid}! Waiting for setup...",
            },
            labels[pid],
        )
        if not ok:
            # Cannot reach this player - notify the other and bail.
            other = 2 if pid == 1 else 1
            _notify_and_close(
                connections[other],
                connections[pid],
                labels[other],
                labels[pid],
            )
            return

    logger.info("WELCOME sent to both players.")

    # Send GAME_START to both players to signal the match is ready
    # and they should begin placing ships.
    for pid in (1, 2):
        ok = _safe_send(
            connections[pid],
            {
                "type": "GAME_START",
                "message": "Both players connected! Place your ships.",
            },
            labels[pid],
        )
        if not ok:
            other = 2 if pid == 1 else 1
            _notify_and_close(
                connections[other],
                connections[pid],
                labels[other],
                labels[pid],
            )
            return

    logger.info("GAME_START sent to both players.")

    # -- Phase 2: Ship Placement (SETUP) ---------------------------------
    # Both players submit their ship placements independently.
    # We create a fresh GameState to validate and store placements.

    game = GameState()

    # Track which players have successfully placed ships.
    # We use select() to multiplex reads from both sockets so that
    # players can place ships in any order (or retry after rejection)
    # without blocking the other player's socket.

    # Build a reverse lookup: socket -> player_id, used by select().
    sock_to_pid: dict[socket.socket, int] = {
        conn_p1: 1,
        conn_p2: 2,
    }

    while not game.both_players_ready():
        # Collect sockets of players who haven't placed yet.
        pending_socks = [
            connections[pid] for pid in (1, 2) if not game.ships_ready[pid]
        ]

        # Use select() to wait for data on any pending socket.
        # Timeout of 1 second avoids indefinite blocking — the loop
        # re-evaluates the ready state on each iteration.
        try:
            readable, _, _ = select.select(pending_socks, [], [], 1.0)
        except (OSError, ValueError):
            # One of the sockets was closed externally.
            logger.warning("select() error during setup - ending session.")
            _close_socket(conn_p1, "P1")
            _close_socket(conn_p2, "P2")
            return

        for sock in readable:
            pid = sock_to_pid[sock]

            msg = _safe_recv(connections[pid], labels[pid])
            if msg is None:
                # Player disconnected during setup.
                other = game.get_opponent_id(pid)
                _notify_and_close(
                    connections[other],
                    connections[pid],
                    labels[other],
                    labels[pid],
                )
                return

            msg_type = msg.get("type", "")

            if msg_type == "PLACE_SHIPS":
                ships_data = msg.get("ships", [])
                success, reason = game.place_ships(pid, ships_data)

                if success:
                    logger.info("%s placed ships successfully.", labels[pid])
                    _safe_send(
                        connections[pid],
                        {
                            "type": "SHIPS_CONFIRMED",
                            "message": "Ships placed successfully!",
                        },
                        labels[pid],
                    )
                else:
                    logger.warning(
                        "%s ship placement rejected: %s",
                        labels[pid],
                        reason,
                    )
                    ok = _safe_send(
                        connections[pid],
                        {
                            "type": "SHIPS_REJECTED",
                            "message": f"Invalid placement: {reason}",
                        },
                        labels[pid],
                    )
                    if not ok:
                        other = game.get_opponent_id(pid)
                        _notify_and_close(
                            connections[other],
                            connections[pid],
                            labels[other],
                            labels[pid],
                        )
                        return
            else:
                # Wrong message type during setup - send an error.
                logger.warning(
                    "%s sent unexpected '%s' during setup.",
                    labels[pid],
                    msg_type,
                )
                ok = _safe_send(
                    connections[pid],
                    {
                        "type": "ERROR",
                        "message": (
                            f"Expected PLACE_SHIPS during setup, got '{msg_type}'."
                        ),
                    },
                    labels[pid],
                )
                if not ok:
                    other = game.get_opponent_id(pid)
                    _notify_and_close(
                        connections[other],
                        connections[pid],
                        labels[other],
                        labels[pid],
                    )
                    return

    # -- Phase 3: Transition to Gameplay ----------------------------------
    # Both players have placed ships.  Start the game and announce turns.

    game.start_game()
    logger.info("Both players ready. Game starting!")

    # Broadcast ALL_READY to both players.
    for pid in (1, 2):
        ok = _safe_send(
            connections[pid],
            {"type": "ALL_READY", "turn": game.current_turn},
            labels[pid],
        )
        if not ok:
            other = game.get_opponent_id(pid)
            _notify_and_close(
                connections[other],
                connections[pid],
                labels[other],
                labels[pid],
            )
            return

    # Send initial turn notifications.
    _send_turn_notifications(connections, labels, game.current_turn)

    # -- Phase 4: Gameplay Loop -------------------------------------------
    # Alternate turns until someone wins or a player disconnects.

    while game.phase.value == "playing":
        active_pid = game.current_turn
        active_conn = connections[active_pid]

        # Wait for the active player to send a FIRE message.
        msg = _safe_recv(active_conn, labels[active_pid])
        if msg is None:
            # Active player disconnected during gameplay.
            other = game.get_opponent_id(active_pid)
            _notify_and_close(
                connections[other],
                connections[active_pid],
                labels[other],
                labels[active_pid],
            )
            return

        msg_type = msg.get("type", "")

        if msg_type != "FIRE":
            # Wrong message type during gameplay - send error, don't
            # advance the turn.  The player should resend correctly.
            logger.warning(
                "%s sent unexpected '%s' during gameplay.",
                labels[active_pid],
                msg_type,
            )
            ok = _safe_send(
                active_conn,
                {
                    "type": "ERROR",
                    "message": f"Expected FIRE during your turn, got '{msg_type}'.",
                },
                labels[active_pid],
            )
            if not ok:
                other = game.get_opponent_id(active_pid)
                _notify_and_close(
                    connections[other],
                    connections[active_pid],
                    labels[other],
                    labels[active_pid],
                )
                return
            continue

        # Extract coordinates and validate via GameState.
        row = msg.get("row")
        col = msg.get("col")

        # Check that row and col are present and numeric.
        if row is None or col is None:
            _safe_send(
                active_conn,
                {
                    "type": "ERROR",
                    "message": "FIRE message must include 'row' and 'col'.",
                },
                labels[active_pid],
            )
            continue

        try:
            row = int(row)
            col = int(col)
        except (TypeError, ValueError):
            _safe_send(
                active_conn,
                {
                    "type": "ERROR",
                    "message": (
                        f"Invalid coordinates: row={row!r}, col={col!r}. "
                        f"Must be integers 0-9."
                    ),
                },
                labels[active_pid],
            )
            continue

        # Process the shot through the game logic.
        try:
            result = game.process_shot(active_pid, row, col)
        except ValueError as exc:
            # Invalid shot (duplicate target, out of bounds, etc.).
            logger.warning("%s invalid FIRE: %s", labels[active_pid], exc)
            _safe_send(
                active_conn,
                {"type": "ERROR", "message": str(exc)},
                labels[active_pid],
            )
            continue

        # Build the RESULT broadcast message.
        result_msg = {
            "type": "RESULT",
            "player": active_pid,
            "row": result["row"],
            "col": result["col"],
            "result": result["result"],
            "sunk_ship": result["sunk_ship"],
            "game_over": result["game_over"],
            "winner": result["winner"],
            "next_turn": result["next_turn"],
        }

        logger.info(
            "%s fired at (%d, %d) -> %s%s",
            labels[active_pid],
            row,
            col,
            result["result"],
            f" (sunk {result['sunk_ship']})" if result["sunk_ship"] else "",
        )

        # Broadcast RESULT to both players.
        for pid in (1, 2):
            ok = _safe_send(connections[pid], result_msg, labels[pid])
            if not ok:
                other = game.get_opponent_id(pid)
                _notify_and_close(
                    connections[other],
                    connections[pid],
                    labels[other],
                    labels[pid],
                )
                return

        # Check for game over.
        if result["game_over"]:
            winner = result["winner"]
            logger.info("Game over! %s wins!", labels[winner] if winner else "Nobody")

            game_over_msg = {
                "type": "GAME_OVER",
                "winner": winner,
                "reason": "All ships sunk",
            }
            for pid in (1, 2):
                _safe_send(connections[pid], game_over_msg, labels[pid])
            break

        # Send turn notifications for the next round.
        _send_turn_notifications(connections, labels, result["next_turn"])

    # -- Phase 5: Cleanup -------------------------------------------------
    logger.info("Game session ended. Closing connections.")
    _close_socket(conn_p1, "P1")
    _close_socket(conn_p2, "P2")


def _send_turn_notifications(
    connections: dict[int, socket.socket],
    labels: dict[int, str],
    active_player: int,
) -> None:
    """Send YOUR_TURN and OPPONENT_TURN messages to the appropriate players.

    Args:
        connections: Map of player_id -> socket.
        labels: Map of player_id -> logging label.
        active_player: The player_id whose turn it is.
    """
    waiting_player = 2 if active_player == 1 else 1

    _safe_send(
        connections[active_player],
        {"type": "YOUR_TURN", "turn": active_player},
        labels[active_player],
    )
    _safe_send(
        connections[waiting_player],
        {"type": "OPPONENT_TURN", "turn": active_player},
        labels[waiting_player],
    )


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------


def start_server(host: str = HOST, port: int = PORT) -> None:
    """Start the BroadSide TCP server.

    Binds to the given host and port, listens for incoming TCP connections,
    and matches players into game sessions. The main thread runs the
    accept loop while each game session runs on its own daemon thread.

    The accept loop performs the following for each new connection:
        1. Receive a CONNECT message from the client.
        2. Add the client socket to the matchmaking queue.
        3. If the first player is waiting, send a WAIT message.
        4. Once two players are queued, pop both and spawn a game_session
           thread.

    The server runs indefinitely until interrupted by Ctrl+C.

    Args:
        host: The IP address to bind to (default: 127.0.0.1).
        port: The TCP port to listen on (default: 5050).
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Allow the port to be reused immediately after the server shuts down.
    # Without this, the OS keeps the port in TIME_WAIT for ~60 seconds.
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server_sock.bind((host, port))
    server_sock.listen(5)

    logger.info("BroadSide server listening on %s:%d", host, port)
    logger.info("Waiting for players to connect...")

    try:
        while True:
            # Block until a new client connects.
            conn, addr = server_sock.accept()
            logger.info("New connection from %s:%d", addr[0], addr[1])

            # Receive the CONNECT handshake from the client.
            msg = _safe_recv(conn, f"new@{addr[0]}:{addr[1]}")
            if msg is None:
                logger.warning(
                    "Client %s:%d disconnected before handshake.",
                    addr[0],
                    addr[1],
                )
                _close_socket(conn, f"new@{addr[0]}:{addr[1]}")
                continue

            msg_type = msg.get("type", "")
            if msg_type != "CONNECT":
                logger.warning(
                    "Expected CONNECT from %s:%d, got '%s'. Dropping.",
                    addr[0],
                    addr[1],
                    msg_type,
                )
                _safe_send(
                    conn,
                    {
                        "type": "ERROR",
                        "message": f"Expected CONNECT handshake, got '{msg_type}'.",
                    },
                    f"new@{addr[0]}:{addr[1]}",
                )
                _close_socket(conn, f"new@{addr[0]}:{addr[1]}")
                continue

            # Add the validated client to the matchmaking queue.
            with queue_lock:
                matchmaking_queue.append(conn)
                queue_size = len(matchmaking_queue)

            logger.info(
                "Client %s:%d added to matchmaking queue (%d waiting).",
                addr[0],
                addr[1],
                queue_size,
            )

            if queue_size == 1:
                # First player in queue - tell them to wait.
                _safe_send(
                    conn,
                    {
                        "type": "WAIT",
                        "message": "Waiting for an opponent to connect...",
                    },
                    f"queued@{addr[0]}:{addr[1]}",
                )

            # Check if we have a pair ready to play.
            with queue_lock:
                if len(matchmaking_queue) >= 2:
                    player1_conn = matchmaking_queue.pop(0)
                    player2_conn = matchmaking_queue.pop(0)
                else:
                    continue

            # Spawn an isolated game session thread for the matched pair.
            logger.info("Match found! Spawning game session.")
            session_thread = threading.Thread(
                target=game_session,
                args=(player1_conn, player2_conn),
                daemon=True,
            )
            session_thread.start()

    except KeyboardInterrupt:
        logger.info("Server shutting down (KeyboardInterrupt).")
    finally:
        # Close any clients still waiting in the matchmaking queue.
        with queue_lock:
            for conn in matchmaking_queue:
                _safe_send(
                    conn,
                    {
                        "type": "ERROR",
                        "message": "Server is shutting down.",
                    },
                    "queued-client",
                )
                _close_socket(conn, "queued-client")
            matchmaking_queue.clear()

        server_sock.close()
        logger.info("Server socket closed. Goodbye!")


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_server()
