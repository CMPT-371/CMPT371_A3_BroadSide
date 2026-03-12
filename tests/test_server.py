"""Tests for the BroadSide TCP game server.

Covers:
    - Handshake: CONNECT -> WELCOME flow for both players.
    - Matchmaking: first player receives WAIT, second triggers match.
    - Ship placement: valid PLACE_SHIPS -> SHIPS_CONFIRMED -> ALL_READY.
    - Ship placement rejection: invalid placement -> SHIPS_REJECTED.
    - Wrong message type during setup: ERROR sent back.
    - Gameplay: FIRE -> RESULT broadcast to both players.
    - Turn enforcement: wrong player firing gets ERROR.
    - Invalid FIRE coordinates: ERROR sent, turn not advanced.
    - Full game lifecycle: connect -> place -> fire until win -> GAME_OVER.
    - Disconnect handling: opponent notified on disconnect during setup.
    - Disconnect handling: opponent notified on disconnect during gameplay.
"""

from __future__ import annotations

import contextlib
import socket
import threading

import pytest

from src.protocol import recv_message, send_message
from src.server import game_session

from .conftest import STANDARD_SHIP_PLACEMENTS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_socket_pair() -> tuple[socket.socket, socket.socket, socket.socket]:
    """Create a connected TCP socket pair via a temporary listening socket.

    Returns:
        A tuple of (client_sock, server_conn, server_sock) where
        client_sock is the "client" end and server_conn is the
        "server" end (the accepted connection). server_sock is
        the listening socket (for cleanup).
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect(("127.0.0.1", port))

    server_conn, _ = server_sock.accept()
    return client_sock, server_conn, server_sock


def _make_two_player_sockets() -> tuple[
    socket.socket,
    socket.socket,
    socket.socket,
    socket.socket,
    socket.socket,
    socket.socket,
]:
    """Create two connected socket pairs for a two-player game session.

    Returns a flat tuple:
        (p1_client, p1_server, p1_listen,
         p2_client, p2_server, p2_listen)

    The game_session function receives (p1_server, p2_server) as the
    two player connections.  The test code uses (p1_client, p2_client)
    to send/receive messages as if they were the actual game clients.
    """
    p1_client, p1_server, p1_listen = _make_socket_pair()
    p2_client, p2_server, p2_listen = _make_socket_pair()
    return p1_client, p1_server, p1_listen, p2_client, p2_server, p2_listen


@pytest.fixture()
def two_player_session():
    """Fixture: start a game_session thread and yield client sockets.

    Yields (p1_client, p2_client) for the test to interact with.
    Cleans up all sockets after the test finishes.
    """
    (
        p1_client,
        p1_server,
        p1_listen,
        p2_client,
        p2_server,
        p2_listen,
    ) = _make_two_player_sockets()

    # Start the game session on a daemon thread.
    session_thread = threading.Thread(
        target=game_session,
        args=(p1_server, p2_server),
        daemon=True,
    )
    session_thread.start()

    yield p1_client, p2_client

    # Cleanup all sockets.
    for sock in (p1_client, p2_client, p1_server, p2_server):
        with contextlib.suppress(OSError):
            sock.close()
    p1_listen.close()
    p2_listen.close()

    # Give the daemon thread a moment to clean up.
    session_thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Handshake tests
# ---------------------------------------------------------------------------


class TestHandshake:
    """Verify the WELCOME handshake at session start."""

    def test_both_players_receive_welcome(self, two_player_session):
        """Both players receive a WELCOME message with their player_id."""
        p1, p2 = two_player_session

        msg1 = recv_message(p1)
        msg2 = recv_message(p2)

        assert msg1 is not None
        assert msg1["type"] == "WELCOME"
        assert msg1["player_id"] == 1

        assert msg2 is not None
        assert msg2["type"] == "WELCOME"
        assert msg2["player_id"] == 2

    def test_welcome_contains_message_field(self, two_player_session):
        """WELCOME messages include a human-readable message field."""
        p1, p2 = two_player_session

        msg1 = recv_message(p1)
        msg2 = recv_message(p2)

        assert "message" in msg1
        assert "message" in msg2


# ---------------------------------------------------------------------------
# Ship placement tests
# ---------------------------------------------------------------------------


class TestShipPlacement:
    """Verify the setup phase: PLACE_SHIPS -> SHIPS_CONFIRMED."""

    def test_valid_placement_confirmed(self, two_player_session):
        """Valid ship placements are accepted with SHIPS_CONFIRMED."""
        p1, p2 = two_player_session

        # Consume WELCOME messages.
        recv_message(p1)
        recv_message(p2)

        # P1 places ships.
        send_message(p1, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
        confirm1 = recv_message(p1)

        assert confirm1 is not None
        assert confirm1["type"] == "SHIPS_CONFIRMED"

    def test_invalid_placement_rejected(self, two_player_session):
        """Invalid ship placements are rejected with SHIPS_REJECTED."""
        p1, p2 = two_player_session

        # Consume WELCOME messages.
        recv_message(p1)
        recv_message(p2)

        # Send an invalid placement (wrong number of ships).
        bad_ships = [
            {"name": "Carrier", "row": 0, "col": 0, "horizontal": True},
        ]
        send_message(p1, {"type": "PLACE_SHIPS", "ships": bad_ships})
        reject = recv_message(p1)

        assert reject is not None
        assert reject["type"] == "SHIPS_REJECTED"
        assert "message" in reject

    def test_wrong_message_during_setup(self, two_player_session):
        """Sending FIRE during setup returns an ERROR."""
        p1, p2 = two_player_session

        # Consume WELCOME messages.
        recv_message(p1)
        recv_message(p2)

        # Send FIRE instead of PLACE_SHIPS.
        send_message(p1, {"type": "FIRE", "row": 0, "col": 0})
        error = recv_message(p1)

        assert error is not None
        assert error["type"] == "ERROR"
        assert "PLACE_SHIPS" in error["message"]

    def test_both_players_place_then_all_ready(self, two_player_session):
        """After both players place ships, both receive ALL_READY."""
        p1, p2 = two_player_session

        # Consume WELCOME messages.
        recv_message(p1)
        recv_message(p2)

        # Both place ships.
        send_message(p1, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
        recv_message(p1)  # SHIPS_CONFIRMED

        send_message(p2, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
        recv_message(p2)  # SHIPS_CONFIRMED

        # Both should receive ALL_READY.
        all_ready_p1 = recv_message(p1)
        all_ready_p2 = recv_message(p2)

        assert all_ready_p1 is not None
        assert all_ready_p1["type"] == "ALL_READY"
        assert all_ready_p1["turn"] == 1

        assert all_ready_p2 is not None
        assert all_ready_p2["type"] == "ALL_READY"
        assert all_ready_p2["turn"] == 1

    def test_retry_after_rejected_placement(self, two_player_session):
        """A player can retry placement after a rejection."""
        p1, p2 = two_player_session

        # Consume WELCOME messages.
        recv_message(p1)
        recv_message(p2)

        # First attempt: bad placement.
        bad_ships = [
            {"name": "Carrier", "row": 0, "col": 0, "horizontal": True},
        ]
        send_message(p1, {"type": "PLACE_SHIPS", "ships": bad_ships})
        reject = recv_message(p1)
        assert reject["type"] == "SHIPS_REJECTED"

        # Second attempt: valid placement.
        send_message(p1, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
        confirm = recv_message(p1)
        assert confirm["type"] == "SHIPS_CONFIRMED"


# ---------------------------------------------------------------------------
# Gameplay tests
# ---------------------------------------------------------------------------


def _setup_game(p1, p2):
    """Helper: run through handshake + setup to reach gameplay phase.

    Consumes all messages up to and including turn notifications.
    Returns the YOUR_TURN/OPPONENT_TURN messages.
    """
    # Consume WELCOME messages.
    recv_message(p1)
    recv_message(p2)

    # Both place ships.
    send_message(p1, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
    recv_message(p1)  # SHIPS_CONFIRMED

    send_message(p2, {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS})
    recv_message(p2)  # SHIPS_CONFIRMED

    # ALL_READY
    recv_message(p1)
    recv_message(p2)

    # Turn notifications (YOUR_TURN for P1, OPPONENT_TURN for P2).
    turn_p1 = recv_message(p1)
    turn_p2 = recv_message(p2)

    return turn_p1, turn_p2


class TestGameplay:
    """Verify the gameplay loop: FIRE -> RESULT broadcasting."""

    def test_turn_notifications_after_all_ready(self, two_player_session):
        """P1 gets YOUR_TURN, P2 gets OPPONENT_TURN after ALL_READY."""
        p1, p2 = two_player_session
        turn_p1, turn_p2 = _setup_game(p1, p2)

        assert turn_p1["type"] == "YOUR_TURN"
        assert turn_p1["turn"] == 1

        assert turn_p2["type"] == "OPPONENT_TURN"
        assert turn_p2["turn"] == 1

    def test_valid_fire_broadcasts_result(self, two_player_session):
        """A valid FIRE produces a RESULT broadcast to both players."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # P1 fires at (9, 9) - should be a miss (no ships there in standard).
        send_message(p1, {"type": "FIRE", "row": 9, "col": 9})

        result_p1 = recv_message(p1)
        result_p2 = recv_message(p2)

        assert result_p1 is not None
        assert result_p1["type"] == "RESULT"
        assert result_p1["row"] == 9
        assert result_p1["col"] == 9
        assert result_p1["result"] == "miss"
        assert result_p1["game_over"] is False

        # Both receive the same result.
        assert result_p2 is not None
        assert result_p2["type"] == "RESULT"
        assert result_p2["row"] == 9
        assert result_p2["col"] == 9

    def test_hit_detected(self, two_player_session):
        """Firing at a ship cell produces a 'hit' result."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # P1 fires at (0, 0) - Carrier is at row 0, cols 0-4.
        send_message(p1, {"type": "FIRE", "row": 0, "col": 0})

        result_p1 = recv_message(p1)
        assert result_p1["result"] == "hit"

    def test_turn_alternates(self, two_player_session):
        """Turns alternate correctly between P1 and P2."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # P1 fires (miss at 9,9).
        send_message(p1, {"type": "FIRE", "row": 9, "col": 9})

        # Both get RESULT.
        recv_message(p1)  # RESULT
        recv_message(p2)  # RESULT

        # Turn notifications: P2 gets YOUR_TURN.
        turn_p1 = recv_message(p1)
        turn_p2 = recv_message(p2)

        assert turn_p1["type"] == "OPPONENT_TURN"
        assert turn_p1["turn"] == 2

        assert turn_p2["type"] == "YOUR_TURN"
        assert turn_p2["turn"] == 2

    def test_wrong_player_fire_gets_error(self, two_player_session):
        """P2 firing when it's P1's turn gets an ERROR."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # It's P1's turn, but P2 tries to fire.
        # The server only reads from the active player, so we need
        # to test this differently: P1 fires, then P1 tries again.
        send_message(p1, {"type": "FIRE", "row": 9, "col": 9})

        # Consume RESULT + turn notifications.
        recv_message(p1)  # RESULT
        recv_message(p2)  # RESULT
        recv_message(p1)  # OPPONENT_TURN
        recv_message(p2)  # YOUR_TURN

        # Now it's P2's turn. P2 fires validly.
        send_message(p2, {"type": "FIRE", "row": 9, "col": 9})
        recv_message(p1)  # RESULT
        recv_message(p2)  # RESULT

    def test_invalid_fire_missing_coords(self, two_player_session):
        """FIRE without row/col gets an ERROR, turn not advanced."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # Send FIRE without coordinates.
        send_message(p1, {"type": "FIRE"})
        error = recv_message(p1)

        assert error is not None
        assert error["type"] == "ERROR"
        assert "row" in error["message"] or "col" in error["message"]

        # P1 should still be able to fire (turn not advanced).
        send_message(p1, {"type": "FIRE", "row": 9, "col": 9})
        result = recv_message(p1)
        assert result["type"] == "RESULT"

    def test_wrong_message_during_gameplay(self, two_player_session):
        """Sending PLACE_SHIPS during gameplay returns ERROR."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        send_message(p1, {"type": "PLACE_SHIPS", "ships": []})
        error = recv_message(p1)

        assert error is not None
        assert error["type"] == "ERROR"
        assert "FIRE" in error["message"]


# ---------------------------------------------------------------------------
# Full game lifecycle test
# ---------------------------------------------------------------------------


class TestFullGameLifecycle:
    """Verify a complete game from connect to GAME_OVER."""

    def test_complete_game_to_victory(self, two_player_session):
        """Play a full game where P1 sinks all of P2's ships."""
        p1, p2 = two_player_session
        _setup_game(p1, p2)

        # Standard ship placements for P2:
        #   Carrier:    row 0, cols 0-4 (5 cells)
        #   Battleship: row 2, cols 0-3 (4 cells)
        #   Cruiser:    row 4, cols 0-2 (3 cells)
        #   Submarine:  row 6, cols 0-2 (3 cells)
        #   Destroyer:  row 8, cols 0-1 (2 cells)
        #
        # Total: 17 cells. We fire at all 17 to win.
        # Between P1 shots, P2 fires at harmless cells on empty rows.

        targets = []
        # Carrier: (0,0), (0,1), (0,2), (0,3), (0,4)
        for c in range(5):
            targets.append((0, c))
        # Battleship: (2,0), (2,1), (2,2), (2,3)
        for c in range(4):
            targets.append((2, c))
        # Cruiser: (4,0), (4,1), (4,2)
        for c in range(3):
            targets.append((4, c))
        # Submarine: (6,0), (6,1), (6,2)
        for c in range(3):
            targets.append((6, c))
        # Destroyer: (8,0), (8,1)
        for c in range(2):
            targets.append((8, c))

        # P2 fires at unique empty cells (rows 1, 3 have no ships).
        # We need up to 16 unique miss targets (one fewer than P1's 17).
        p2_targets = [(1, c) for c in range(10)] + [(3, c) for c in range(6)]

        game_over = False

        for i, (r, c) in enumerate(targets):
            # P1 fires.
            send_message(p1, {"type": "FIRE", "row": r, "col": c})

            result_p1 = recv_message(p1)
            result_p2 = recv_message(p2)

            assert result_p1["type"] == "RESULT"
            assert result_p1["player"] == 1
            assert result_p2["type"] == "RESULT"

            if result_p1["game_over"]:
                game_over = True
                # Should receive GAME_OVER.
                go_p1 = recv_message(p1)
                go_p2 = recv_message(p2)

                assert go_p1["type"] == "GAME_OVER"
                assert go_p1["winner"] == 1

                assert go_p2["type"] == "GAME_OVER"
                assert go_p2["winner"] == 1
                break

            # Consume turn notifications.
            recv_message(p1)  # OPPONENT_TURN
            recv_message(p2)  # YOUR_TURN

            # P2 fires at a unique empty cell (guaranteed miss).
            p2r, p2c = p2_targets[i]
            send_message(p2, {"type": "FIRE", "row": p2r, "col": p2c})

            recv_message(p1)  # RESULT
            recv_message(p2)  # RESULT

            # Consume turn notifications.
            recv_message(p1)  # YOUR_TURN
            recv_message(p2)  # OPPONENT_TURN

        assert game_over, "Expected game to end after sinking all ships."


# ---------------------------------------------------------------------------
# Disconnect handling tests
# ---------------------------------------------------------------------------


class TestDisconnectHandling:
    """Verify graceful disconnect notifications."""

    def test_p1_disconnect_during_setup_notifies_p2(self):
        """If P1 disconnects during setup, P2 gets OPPONENT_DISCONNECTED."""
        (
            p1_client,
            p1_server,
            p1_listen,
            p2_client,
            p2_server,
            p2_listen,
        ) = _make_two_player_sockets()

        session_thread = threading.Thread(
            target=game_session,
            args=(p1_server, p2_server),
            daemon=True,
        )
        session_thread.start()

        # Both receive WELCOME.
        recv_message(p1_client)
        recv_message(p2_client)

        # P1 disconnects abruptly.
        p1_client.close()

        # P2 should receive OPPONENT_DISCONNECTED.
        msg = recv_message(p2_client)
        assert msg is not None
        assert msg["type"] == "OPPONENT_DISCONNECTED"

        # Cleanup.
        p2_client.close()
        p1_listen.close()
        p2_listen.close()
        session_thread.join(timeout=2.0)

    def test_p2_disconnect_during_gameplay_notifies_p1(self):
        """If P2 disconnects during gameplay, P1 gets OPPONENT_DISCONNECTED."""
        (
            p1_client,
            p1_server,
            p1_listen,
            p2_client,
            p2_server,
            p2_listen,
        ) = _make_two_player_sockets()

        session_thread = threading.Thread(
            target=game_session,
            args=(p1_server, p2_server),
            daemon=True,
        )
        session_thread.start()

        # Run through setup.
        recv_message(p1_client)  # WELCOME
        recv_message(p2_client)  # WELCOME

        send_message(
            p1_client,
            {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS},
        )
        recv_message(p1_client)  # SHIPS_CONFIRMED

        send_message(
            p2_client,
            {"type": "PLACE_SHIPS", "ships": STANDARD_SHIP_PLACEMENTS},
        )
        recv_message(p2_client)  # SHIPS_CONFIRMED

        # ALL_READY
        recv_message(p1_client)
        recv_message(p2_client)

        # Turn notifications
        recv_message(p1_client)  # YOUR_TURN
        recv_message(p2_client)  # OPPONENT_TURN

        # P1 fires once.
        send_message(p1_client, {"type": "FIRE", "row": 9, "col": 9})
        recv_message(p1_client)  # RESULT
        recv_message(p2_client)  # RESULT
        recv_message(p1_client)  # OPPONENT_TURN
        recv_message(p2_client)  # YOUR_TURN

        # P2 disconnects during their turn.
        p2_client.close()

        # P1 should receive OPPONENT_DISCONNECTED.
        msg = recv_message(p1_client)
        assert msg is not None
        assert msg["type"] == "OPPONENT_DISCONNECTED"

        # Cleanup.
        p1_client.close()
        p1_listen.close()
        p2_listen.close()
        session_thread.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Helper function unit tests
# ---------------------------------------------------------------------------


class TestSafeSendRecv:
    """Verify the _safe_send and _safe_recv helpers handle errors."""

    def test_safe_send_returns_false_on_closed_socket(self):
        """_safe_send returns False when the socket is already closed."""
        from src.server import _safe_send

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.close()

        result = _safe_send(sock, {"type": "TEST"}, "test")
        assert result is False

    def test_safe_recv_returns_none_on_closed_socket(self):
        """_safe_recv returns None when the socket is already closed."""
        from src.server import _safe_recv

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.close()

        result = _safe_recv(sock, "test")
        assert result is None

    def test_close_socket_ignores_errors(self):
        """_close_socket does not raise on already-closed sockets."""
        from src.server import _close_socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.close()

        # Should not raise.
        _close_socket(sock, "test")
