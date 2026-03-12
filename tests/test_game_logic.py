"""Tests for the Battleship game logic module.

Covers:
    - Ship: construction, hit tracking, sunk detection.
    - Board: placement validation, shot processing, sunk/win detection, views.
    - GameState: full lifecycle (setup -> playing -> finished), turn enforcement,
      error handling, atomic rollback.
"""

from __future__ import annotations

import pytest

from src.game_logic import (
    BOARD_SIZE,
    SHIP_DEFINITIONS,
    TOTAL_SHIP_CELLS,
    Board,
    CellState,
    GamePhase,
    GameState,
    Ship,
)

from .conftest import STANDARD_SHIP_PLACEMENTS

# ═══════════════════════════════════════════════════════════════════════════
# Ship
# ═══════════════════════════════════════════════════════════════════════════


class TestShip:
    """Tests for the Ship dataclass."""

    def test_new_ship_is_not_sunk(self):
        ship = Ship(name="Destroyer", size=2, positions=[(0, 0), (0, 1)])
        assert not ship.is_sunk

    def test_partial_hits_not_sunk(self):
        ship = Ship(name="Cruiser", size=3, positions=[(0, 0), (0, 1), (0, 2)])
        ship.hits.add((0, 0))
        assert not ship.is_sunk

    def test_all_hits_is_sunk(self):
        ship = Ship(name="Destroyer", size=2, positions=[(0, 0), (0, 1)])
        ship.hits.add((0, 0))
        ship.hits.add((0, 1))
        assert ship.is_sunk

    def test_occupies_returns_true_for_valid_position(self):
        ship = Ship(name="Carrier", size=5, positions=[(1, c) for c in range(5)])
        assert ship.occupies(1, 0)
        assert ship.occupies(1, 4)

    def test_occupies_returns_false_for_invalid_position(self):
        ship = Ship(name="Carrier", size=5, positions=[(1, c) for c in range(5)])
        assert not ship.occupies(0, 0)
        assert not ship.occupies(1, 5)


# ═══════════════════════════════════════════════════════════════════════════
# Board — Ship Placement
# ═══════════════════════════════════════════════════════════════════════════


class TestBoardPlacement:
    """Tests for Board.place_ship() validation."""

    def test_valid_horizontal_placement(self, empty_board: Board):
        ok, msg = empty_board.place_ship("Carrier", 0, 0, horizontal=True)
        assert ok is True
        assert msg == "OK"
        assert len(empty_board.ships) == 1

    def test_valid_vertical_placement(self, empty_board: Board):
        ok, _msg = empty_board.place_ship("Destroyer", 3, 0, horizontal=False)
        assert ok is True
        # Destroyer (size 2) occupies (3,0) and (4,0).
        assert empty_board.grid[3][0] == CellState.SHIP
        assert empty_board.grid[4][0] == CellState.SHIP

    def test_reject_unknown_ship_name(self, empty_board: Board):
        ok, msg = empty_board.place_ship("Frigate", 0, 0, horizontal=True)
        assert ok is False
        assert "Unknown" in msg

    def test_reject_duplicate_ship(self, empty_board: Board):
        empty_board.place_ship("Carrier", 0, 0, horizontal=True)
        ok, msg = empty_board.place_ship("Carrier", 5, 0, horizontal=True)
        assert ok is False
        assert "already" in msg.lower()

    def test_reject_horizontal_out_of_bounds(self, empty_board: Board):
        # Carrier (size 5) at col 7 would extend to col 11.
        ok, msg = empty_board.place_ship("Carrier", 0, 7, horizontal=True)
        assert ok is False
        assert "beyond" in msg.lower()

    def test_reject_vertical_out_of_bounds(self, empty_board: Board):
        # Carrier (size 5) at row 7 would extend to row 11.
        ok, msg = empty_board.place_ship("Carrier", 7, 0, horizontal=False)
        assert ok is False
        assert "beyond" in msg.lower()

    def test_reject_overlap(self, empty_board: Board):
        empty_board.place_ship("Carrier", 0, 0, horizontal=True)
        ok, msg = empty_board.place_ship("Destroyer", 0, 3, horizontal=True)
        assert ok is False
        assert "overlaps" in msg.lower()

    def test_all_ships_placed_flag(self, empty_board: Board):
        assert not empty_board.all_ships_placed()
        for ship_data in STANDARD_SHIP_PLACEMENTS:
            empty_board.place_ship(**ship_data)
        assert empty_board.all_ships_placed()

    @pytest.mark.parametrize(
        ("row", "col", "horizontal"),
        [
            (0, 0, True),  # Top-left corner, horizontal
            (0, 5, True),  # Carrier fits exactly: cols 5-9
            (5, 0, False),  # Carrier fits exactly: rows 5-9
            (9, 0, True),  # Bottom row, horizontal Destroyer
        ],
    )
    def test_boundary_placements_succeed(
        self, empty_board: Board, row: int, col: int, horizontal: bool
    ):
        """Ships that fit exactly at grid boundaries should be accepted."""
        # Use Destroyer (size 2) for boundary tests since it's smallest.
        ok, _ = empty_board.place_ship("Destroyer", row, col, horizontal)
        assert ok is True


# ═══════════════════════════════════════════════════════════════════════════
# Board — Shot Processing
# ═══════════════════════════════════════════════════════════════════════════


class TestBoardShots:
    """Tests for Board.receive_shot() and related methods."""

    def test_miss_on_empty_water(self, board_with_all_ships: Board):
        result, sunk = board_with_all_ships.receive_shot(1, 0)
        assert result == "miss"
        assert sunk is None
        assert board_with_all_ships.grid[1][0] == CellState.MISS

    def test_hit_on_ship(self, board_with_all_ships: Board):
        result, sunk = board_with_all_ships.receive_shot(0, 0)
        assert result == "hit"
        assert sunk is None
        assert board_with_all_ships.grid[0][0] == CellState.HIT

    def test_sunk_after_all_cells_hit(self, board_with_all_ships: Board):
        """Hitting every cell of the Destroyer (row 8, cols 0-1) sinks it."""
        board_with_all_ships.receive_shot(8, 0)
        result, sunk = board_with_all_ships.receive_shot(8, 1)
        assert result == "sunk"
        assert sunk == "Destroyer"

    def test_full_carrier_sunk_lifecycle(self, board_with_all_ships: Board):
        """Hit all 5 cells of the Carrier: 4 hits then 1 sunk."""
        for col in range(4):
            result, sunk = board_with_all_ships.receive_shot(0, col)
            assert result == "hit"
            assert sunk is None

        result, sunk = board_with_all_ships.receive_shot(0, 4)
        assert result == "sunk"
        assert sunk == "Carrier"

    def test_duplicate_shot_raises_value_error(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(0, 0)
        with pytest.raises(ValueError, match="already"):
            board_with_all_ships.receive_shot(0, 0)

    def test_out_of_bounds_shot_raises_value_error(self, board_with_all_ships: Board):
        with pytest.raises(ValueError, match="out of bounds"):
            board_with_all_ships.receive_shot(10, 0)

    def test_is_valid_target_untouched_cell(self, board_with_all_ships: Board):
        assert board_with_all_ships.is_valid_target(9, 9) is True

    def test_is_valid_target_after_hit(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(0, 0)
        assert board_with_all_ships.is_valid_target(0, 0) is False

    def test_is_valid_target_after_miss(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(1, 1)
        assert board_with_all_ships.is_valid_target(1, 1) is False

    def test_is_valid_target_out_of_bounds(self, board_with_all_ships: Board):
        assert board_with_all_ships.is_valid_target(-1, 0) is False
        assert board_with_all_ships.is_valid_target(0, 10) is False

    def test_all_sunk_when_fleet_destroyed(self, board_with_all_ships: Board):
        """Sinking every ship on the board makes all_sunk() return True."""
        for ship_data in STANDARD_SHIP_PLACEMENTS:
            ship_size = SHIP_DEFINITIONS[ship_data["name"]]
            row = ship_data["row"]
            for col in range(ship_size):
                board_with_all_ships.receive_shot(row, col)

        assert board_with_all_ships.all_sunk() is True

    def test_all_sunk_false_with_ships_remaining(self, board_with_all_ships: Board):
        """Sinking only some ships leaves all_sunk() as False."""
        # Sink only the Destroyer (row 8, cols 0-1).
        board_with_all_ships.receive_shot(8, 0)
        board_with_all_ships.receive_shot(8, 1)
        assert board_with_all_ships.all_sunk() is False


# ═══════════════════════════════════════════════════════════════════════════
# Board — View Serialization
# ═══════════════════════════════════════════════════════════════════════════


class TestBoardViews:
    """Tests for Board.to_own_view() and Board.to_opponent_view()."""

    def test_own_view_shows_ships(self, board_with_all_ships: Board):
        view = board_with_all_ships.to_own_view()
        # Carrier at row 0, cols 0-4.
        assert view[0][0] == "S"
        assert view[0][4] == "S"

    def test_own_view_shows_hits_and_misses(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(0, 0)  # Hit
        board_with_all_ships.receive_shot(1, 0)  # Miss
        view = board_with_all_ships.to_own_view()
        assert view[0][0] == "X"
        assert view[1][0] == "O"

    def test_opponent_view_hides_unhit_ships(self, board_with_all_ships: Board):
        view = board_with_all_ships.to_opponent_view()
        # Row 0 has the Carrier, but opponent shouldn't see it.
        assert view[0][0] == "~"
        assert view[0][4] == "~"

    def test_opponent_view_reveals_hits(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(0, 0)
        view = board_with_all_ships.to_opponent_view()
        assert view[0][0] == "X"

    def test_opponent_view_reveals_misses(self, board_with_all_ships: Board):
        board_with_all_ships.receive_shot(1, 0)
        view = board_with_all_ships.to_opponent_view()
        assert view[1][0] == "O"


# ═══════════════════════════════════════════════════════════════════════════
# GameState — Setup Phase
# ═══════════════════════════════════════════════════════════════════════════


class TestGameStateSetup:
    """Tests for the SETUP phase of GameState."""

    def test_initial_phase_is_setup(self, game_in_setup: GameState):
        assert game_in_setup.phase == GamePhase.SETUP

    def test_place_ships_success(self, game_in_setup: GameState):
        ok, msg = game_in_setup.place_ships(1, STANDARD_SHIP_PLACEMENTS)
        assert ok is True
        assert msg == "OK"
        assert game_in_setup.ships_ready[1] is True

    def test_reject_wrong_ship_count(self, game_in_setup: GameState):
        ok, msg = game_in_setup.place_ships(1, STANDARD_SHIP_PLACEMENTS[:3])
        assert ok is False
        assert "Expected" in msg

    def test_reject_wrong_ship_names(self, game_in_setup: GameState):
        bad_ships = [
            {"name": "Frigate", "row": 0, "col": 0, "horizontal": True},
            *STANDARD_SHIP_PLACEMENTS[1:],
        ]
        ok, msg = game_in_setup.place_ships(1, bad_ships)
        assert ok is False
        assert "mismatch" in msg.lower()

    def test_reject_duplicate_placement(self, game_in_setup: GameState):
        game_in_setup.place_ships(1, STANDARD_SHIP_PLACEMENTS)
        ok, msg = game_in_setup.place_ships(1, STANDARD_SHIP_PLACEMENTS)
        assert ok is False
        assert "already" in msg.lower()

    def test_atomic_rollback_on_invalid_placement(self, game_in_setup: GameState):
        """If any ship in the batch fails, all placements are rolled back."""
        overlapping = [
            {"name": "Carrier", "row": 0, "col": 0, "horizontal": True},
            {"name": "Battleship", "row": 0, "col": 0, "horizontal": True},
            {"name": "Cruiser", "row": 4, "col": 0, "horizontal": True},
            {"name": "Submarine", "row": 6, "col": 0, "horizontal": True},
            {"name": "Destroyer", "row": 8, "col": 0, "horizontal": True},
        ]
        ok, _msg = game_in_setup.place_ships(1, overlapping)
        assert ok is False
        # Board should have no ships (rollback).
        assert len(game_in_setup.boards[1].ships) == 0

    def test_both_players_ready(self, game_ready_to_play: GameState):
        assert game_ready_to_play.both_players_ready() is True

    def test_start_game_transitions_to_playing(self, game_ready_to_play: GameState):
        game_ready_to_play.start_game()
        assert game_ready_to_play.phase == GamePhase.PLAYING

    def test_start_game_before_ready_raises(self, game_in_setup: GameState):
        with pytest.raises(RuntimeError, match="not all players"):
            game_in_setup.start_game()


# ═══════════════════════════════════════════════════════════════════════════
# GameState — Gameplay Phase
# ═══════════════════════════════════════════════════════════════════════════


class TestGameStateGameplay:
    """Tests for the PLAYING phase of GameState."""

    def test_player_one_moves_first(self, game_in_progress: GameState):
        assert game_in_progress.current_turn == 1

    def test_valid_shot_returns_result(self, game_in_progress: GameState):
        result = game_in_progress.process_shot(1, 0, 0)
        assert result["result"] in ("hit", "miss", "sunk")
        assert result["row"] == 0
        assert result["col"] == 0

    def test_turn_alternates_after_shot(self, game_in_progress: GameState):
        game_in_progress.process_shot(1, 0, 0)
        assert game_in_progress.current_turn == 2

    def test_wrong_turn_raises_value_error(self, game_in_progress: GameState):
        with pytest.raises(ValueError, match="turn"):
            game_in_progress.process_shot(2, 0, 0)

    def test_invalid_coordinates_raise_value_error(self, game_in_progress: GameState):
        with pytest.raises(ValueError, match="not a valid target"):
            game_in_progress.process_shot(1, 10, 0)

    def test_duplicate_shot_raises_value_error(self, game_in_progress: GameState):
        game_in_progress.process_shot(1, 0, 0)
        game_in_progress.process_shot(2, 9, 9)  # P2 takes a turn
        with pytest.raises(ValueError, match="not a valid target"):
            game_in_progress.process_shot(1, 0, 0)

    def test_shot_during_setup_raises_value_error(self, game_in_setup: GameState):
        with pytest.raises(ValueError, match="setup"):
            game_in_setup.process_shot(1, 0, 0)

    def test_game_over_on_all_ships_sunk(self, game_in_progress: GameState):
        """Sinking every ship on P2's board ends the game with P1 as winner."""
        for ship_data in STANDARD_SHIP_PLACEMENTS:
            ship_size = SHIP_DEFINITIONS[ship_data["name"]]
            row = ship_data["row"]
            for col in range(ship_size):
                # Force turn to P1 for clean test.
                game_in_progress.current_turn = 1
                result = game_in_progress.process_shot(1, row, col)

        assert result["game_over"] is True
        assert result["winner"] == 1
        assert game_in_progress.phase == GamePhase.FINISHED

    def test_get_opponent_id(self, game_in_progress: GameState):
        assert game_in_progress.get_opponent_id(1) == 2
        assert game_in_progress.get_opponent_id(2) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Constants sanity checks
# ═══════════════════════════════════════════════════════════════════════════


class TestConstants:
    """Verify module-level constants are correct."""

    def test_board_size(self):
        assert BOARD_SIZE == 10

    def test_total_ship_cells(self):
        assert TOTAL_SHIP_CELLS == 17  # 5 + 4 + 3 + 3 + 2

    def test_ship_definitions_count(self):
        assert len(SHIP_DEFINITIONS) == 5

    def test_ship_definitions_values(self):
        assert SHIP_DEFINITIONS == {
            "Carrier": 5,
            "Battleship": 4,
            "Cruiser": 3,
            "Submarine": 3,
            "Destroyer": 2,
        }
