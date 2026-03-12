"""Shared pytest fixtures for the BroadSide test suite.

Provides reusable socket pairs, pre-built boards, and game state
factories so individual test modules stay focused on assertions.
"""

from __future__ import annotations

import socket

import pytest

from src.game_logic import Board, GameState

# ---------------------------------------------------------------------------
# Standard ship placement used across multiple test modules.
# Places all 5 ships in non-overlapping horizontal rows.
# ---------------------------------------------------------------------------

STANDARD_SHIP_PLACEMENTS: list[dict] = [
    {"name": "Carrier", "row": 0, "col": 0, "horizontal": True},
    {"name": "Battleship", "row": 2, "col": 0, "horizontal": True},
    {"name": "Cruiser", "row": 4, "col": 0, "horizontal": True},
    {"name": "Submarine", "row": 6, "col": 0, "horizontal": True},
    {"name": "Destroyer", "row": 8, "col": 0, "horizontal": True},
]


# ---------------------------------------------------------------------------
# Socket fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def socket_pair():
    """Create a connected TCP socket pair for protocol testing.

    Yields a (client_sock, server_conn) tuple. Both sockets are
    automatically closed after the test finishes.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    port = server_sock.getsockname()[1]

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect(("127.0.0.1", port))

    server_conn, _ = server_sock.accept()

    yield client_sock, server_conn

    # Cleanup: close all sockets regardless of test outcome.
    client_sock.close()
    server_conn.close()
    server_sock.close()


# ---------------------------------------------------------------------------
# Game logic fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def empty_board() -> Board:
    """Return a fresh 10x10 board with no ships placed."""
    return Board()


@pytest.fixture()
def board_with_all_ships() -> Board:
    """Return a board with all 5 ships placed in standard positions."""
    board = Board()
    for ship_data in STANDARD_SHIP_PLACEMENTS:
        ok, msg = board.place_ship(
            name=ship_data["name"],
            row=ship_data["row"],
            col=ship_data["col"],
            horizontal=ship_data["horizontal"],
        )
        assert ok, f"Fixture setup failed: {msg}"
    return board


@pytest.fixture()
def game_in_setup() -> GameState:
    """Return a GameState in the SETUP phase (no ships placed yet)."""
    return GameState()


@pytest.fixture()
def game_ready_to_play() -> GameState:
    """Return a GameState where both players have placed ships.

    Call game.start_game() to transition to the PLAYING phase.
    """
    game = GameState()
    game.place_ships(1, STANDARD_SHIP_PLACEMENTS)
    game.place_ships(2, STANDARD_SHIP_PLACEMENTS)
    return game


@pytest.fixture()
def game_in_progress() -> GameState:
    """Return a GameState in the PLAYING phase (Player 1's turn)."""
    game = GameState()
    game.place_ships(1, STANDARD_SHIP_PLACEMENTS)
    game.place_ships(2, STANDARD_SHIP_PLACEMENTS)
    game.start_game()
    return game
