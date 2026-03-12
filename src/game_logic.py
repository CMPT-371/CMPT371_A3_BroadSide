"""
CMPT 371 A3: BroadSide — Game Logic Module

Purpose:
    Implements the complete Battleship game rules as a pure-logic layer with
    no networking, GUI, or I/O dependencies. This module is the single source
    of truth for all game state — the server creates a GameState instance and
    delegates every move to it, ensuring clients cannot cheat by modifying
    their local state.

Architecture:
    Three core classes form a hierarchy:

        Ship      - Represents a single ship (name, size, positions, hits).
        Board     - A player's 10x10 grid (ships, shots, validation).
        GameState - Orchestrates a full game (turns, phases, win detection).

    All methods are deterministic and side-effect-free
    (except mutating their own state).
    This makes the logic easy to test in isolation without sockets or threads.

References:
    - Classic Battleship rules (Hasbro): 5 ships on a 10x10 grid.
    - Python dataclasses: https://docs.python.org/3/library/dataclasses.html
    - Claude Code was used to assist with structuring the module layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard Battleship grid dimensions.
BOARD_SIZE: int = 10

# The five ships in a standard Battleship game, mapped to their lengths.
# Ordered from largest to smallest — this is the order players place them.
SHIP_DEFINITIONS: dict[str, int] = {
    "Carrier": 5,
    "Battleship": 4,
    "Cruiser": 3,
    "Submarine": 3,
    "Destroyer": 2,
}

# Total number of ship cells across all five ships (5+4+3+3+2 = 17).
# A player wins when they have landed 17 hits on the opponent's fleet.
TOTAL_SHIP_CELLS: int = sum(SHIP_DEFINITIONS.values())


class CellState(StrEnum):
    """Visual state of a single cell on the board.

    Using StrEnum allows direct comparison with string literals while
    providing a clean namespace for the possible values.
    """

    EMPTY = "~"  # Untouched water
    SHIP = "S"  # Contains a ship segment (visible only on own board)
    HIT = "X"  # Shot landed on a ship
    MISS = "O"  # Shot landed on empty water


class GamePhase(StrEnum):
    """High-level phase of the game lifecycle.

    The game progresses strictly in order: SETUP -> PLAYING -> FINISHED.
    No phase can be revisited once it transitions forward.
    """

    SETUP = "setup"  # Players are placing ships
    PLAYING = "playing"  # Players are taking turns firing
    FINISHED = "finished"  # A winner has been determined


# ---------------------------------------------------------------------------
# Ship
# ---------------------------------------------------------------------------


@dataclass
class Ship:
    """A single ship on the Battleship grid.

    Each ship occupies a contiguous line of cells (horizontal or vertical)
    and tracks which of its cells have been hit. A ship is sunk when every
    cell has been hit.

    Attributes:
        name: The ship type (e.g., "Carrier", "Destroyer").
        size: Number of grid cells the ship occupies.
        positions: Ordered list of (row, col) tuples the ship occupies.
        hits: Set of (row, col) tuples that have been hit by opponent shots.
    """

    name: str
    size: int
    positions: list[tuple[int, int]] = field(default_factory=list)
    hits: set[tuple[int, int]] = field(default_factory=set)

    @property
    def is_sunk(self) -> bool:
        """A ship is sunk when every position has been hit."""
        return len(self.hits) == self.size

    def occupies(self, row: int, col: int) -> bool:
        """Check whether this ship occupies the given cell."""
        return (row, col) in self.positions


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------


class Board:
    """A single player's 10x10 Battleship grid.

    The board tracks ship positions and the history of incoming shots.
    It is the authoritative state for one player's fleet — the server
    creates two Board instances (one per player) and delegates shot
    processing to them.

    Attributes:
        grid: 10x10 nested list of CellState values.
        ships: List of Ship instances successfully placed on this board.
    """

    def __init__(self) -> None:
        """Initialize a blank 10x10 board filled with empty water."""
        self.grid: list[list[CellState]] = [
            [CellState.EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
        ]
        self.ships: list[Ship] = []

    # -- Ship placement -----------------------------------------------------

    def place_ship(
        self,
        name: str,
        row: int,
        col: int,
        horizontal: bool,
    ) -> tuple[bool, str]:
        """Attempt to place a ship on the board.

        Validates that:
            1. The ship name is a recognized type in SHIP_DEFINITIONS.
            2. The ship has not already been placed on this board.
            3. Every cell the ship would occupy is within the 10x10 grid.
            4. No cell overlaps with an already-placed ship.

        Args:
            name: Ship type (must be a key in SHIP_DEFINITIONS).
            row: Starting row index (0-9, top to bottom).
            col: Starting column index (0-9, left to right).
            horizontal: If True, ship extends rightward from (row, col).
                        If False, ship extends downward.

        Returns:
            A tuple of (success, message). On success: (True, "OK").
            On failure: (False, "human-readable reason").
        """
        # --- Validate ship name ---
        if name not in SHIP_DEFINITIONS:
            return False, f"Unknown ship type: '{name}'"

        ship_size: int = SHIP_DEFINITIONS[name]

        # --- Check for duplicate placement ---
        if any(ship.name == name for ship in self.ships):
            return False, f"'{name}' has already been placed on this board"

        # --- Compute the cells the ship would occupy ---
        positions: list[tuple[int, int]] = []
        for i in range(ship_size):
            r = row if horizontal else row + i
            c = col + i if horizontal else col

            # Bounds check: every cell must be within the 10x10 grid.
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
                direction = "rightward" if horizontal else "downward"
                return False, (
                    f"'{name}' (size {ship_size}) placed at ({row}, {col}) "
                    f"extends {direction} beyond the board boundary"
                )

            positions.append((r, c))

        # --- Check for overlap with existing ships ---
        occupied: set[tuple[int, int]] = {
            pos for ship in self.ships for pos in ship.positions
        }
        for r, c in positions:
            if (r, c) in occupied:
                return False, (
                    f"'{name}' at ({row}, {col}) overlaps with an existing "
                    f"ship at cell ({r}, {c})"
                )

        # --- Placement is valid — commit to the board ---
        ship = Ship(name=name, size=ship_size, positions=positions)
        self.ships.append(ship)

        for r, c in positions:
            self.grid[r][c] = CellState.SHIP

        return True, "OK"

    def all_ships_placed(self) -> bool:
        """Check whether all five ships have been placed."""
        return len(self.ships) == len(SHIP_DEFINITIONS)

    # -- Shot processing ----------------------------------------------------

    def receive_shot(self, row: int, col: int) -> tuple[str, str | None]:
        """Process an incoming shot at the given coordinates.

        Determines whether the shot is a hit, miss, or sinks a ship,
        and updates the grid state accordingly.

        Args:
            row: Target row (0-9).
            col: Target column (0-9).

        Returns:
            A tuple of (result, ship_name_or_none):
                - ("miss", None)       — shot landed on empty water.
                - ("hit", None)        — shot hit a ship but did not sink it.
                - ("sunk", "Carrier")  — shot sank the named ship.

        Raises:
            ValueError: If (row, col) is out of bounds or has already been
                shot at (the server should validate before calling this).
        """
        # --- Bounds validation ---
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise ValueError(
                f"Shot coordinates ({row}, {col}) are out of bounds "
                f"(valid range: 0-{BOARD_SIZE - 1})"
            )

        # --- Duplicate shot check ---
        cell = self.grid[row][col]
        if cell in (CellState.HIT, CellState.MISS):
            raise ValueError(
                f"Cell ({row}, {col}) has already been targeted "
                f"(current state: {cell.value})"
            )

        # --- Miss: shot landed on empty water ---
        if cell == CellState.EMPTY:
            self.grid[row][col] = CellState.MISS
            return "miss", None

        # --- Hit: shot landed on a ship segment ---
        self.grid[row][col] = CellState.HIT

        # Find the ship that occupies this cell and record the hit.
        for ship in self.ships:
            if ship.occupies(row, col):
                ship.hits.add((row, col))

                if ship.is_sunk:
                    return "sunk", ship.name

                return "hit", None

        # This should never happen if the grid and ships are consistent.
        raise RuntimeError(  # pragma: no cover
            f"Grid shows SHIP at ({row}, {col}) but no Ship object claims it"
        )

    def is_valid_target(self, row: int, col: int) -> bool:
        """Check whether a cell is a valid target for a new shot.

        A cell is valid if it is within bounds and has not been previously
        targeted (not HIT and not MISS).

        Args:
            row: Target row (0-9).
            col: Target column (0-9).

        Returns:
            True if the cell can be fired upon, False otherwise.
        """
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            return False

        return self.grid[row][col] not in (CellState.HIT, CellState.MISS)

    def all_sunk(self) -> bool:
        """Check whether every ship on this board has been sunk."""
        return all(ship.is_sunk for ship in self.ships)

    # -- Serialization (for network transmission) ---------------------------

    def to_own_view(self) -> list[list[str]]:
        """Return the grid as the owning player sees it (ships visible).

        This view is sent to the player who owns this board so they can
        see where their ships are and where the opponent has fired.

        Returns:
            A 10x10 nested list of single-character strings.
        """
        return [[cell.value for cell in row] for row in self.grid]

    def to_opponent_view(self) -> list[list[str]]:
        """Return the grid as the opponent sees it (ships hidden).

        Ship cells that have NOT been hit appear as empty water. Only
        hits and misses are visible — this is the "fog of war" view.

        Returns:
            A 10x10 nested list of single-character strings.
        """
        result: list[list[str]] = []
        for row in self.grid:
            result_row: list[str] = []
            for cell in row:
                if cell == CellState.SHIP:
                    # Hide unhit ship segments — they look like empty water.
                    result_row.append(CellState.EMPTY.value)
                else:
                    result_row.append(cell.value)
            result.append(result_row)
        return result


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------


class GameState:
    """Orchestrates a complete two-player Battleship game.

    This class manages the full lifecycle:
        1. SETUP phase — both players place their ships.
        2. PLAYING phase — players alternate firing shots.
        3. FINISHED phase — a winner is determined.

    The server creates one GameState per game session and routes all
    player actions through it. The GameState validates every action and
    produces the response message payloads.

    Attributes:
        boards: A dict mapping player_id (1 or 2) to their Board.
        current_turn: The player_id whose turn it is (1 or 2).
        phase: The current GamePhase.
        winner: The winning player_id, or None if the game is ongoing.
        ships_ready: A dict tracking which players have placed their ships.
    """

    def __init__(self) -> None:
        """Initialize a new game with two empty boards."""
        self.boards: dict[int, Board] = {1: Board(), 2: Board()}
        self.current_turn: int = 1  # Player 1 always fires first.
        self.phase: GamePhase = GamePhase.SETUP
        self.winner: int | None = None
        self.ships_ready: dict[int, bool] = {1: False, 2: False}

    # -- Setup phase --------------------------------------------------------

    def place_ships(
        self,
        player_id: int,
        ships_data: list[dict],
    ) -> tuple[bool, str]:
        """Validate and place all ships for a player.

        Each entry in *ships_data* must contain:
            - "name": str  (a key in SHIP_DEFINITIONS)
            - "row": int   (starting row, 0-9)
            - "col": int   (starting column, 0-9)
            - "horizontal": bool

        The method places ships one at a time, rolling back all placements
        if any single ship fails validation. This ensures atomicity — either
        all ships are placed or none are.

        Args:
            player_id: The player placing ships (1 or 2).
            ships_data: A list of ship placement dictionaries.

        Returns:
            (True, "OK") on success, or (False, "error description") on failure.
        """
        if self.phase != GamePhase.SETUP:
            return False, "Ships can only be placed during the setup phase"

        if self.ships_ready[player_id]:
            return False, "You have already placed your ships"

        # --- Validate that exactly 5 ships are provided ---
        if len(ships_data) != len(SHIP_DEFINITIONS):
            return False, (
                f"Expected {len(SHIP_DEFINITIONS)} ships, " f"got {len(ships_data)}"
            )

        # --- Validate that all required ship types are present ---
        provided_names = {ship["name"] for ship in ships_data}
        required_names = set(SHIP_DEFINITIONS.keys())
        if provided_names != required_names:
            missing = required_names - provided_names
            extra = provided_names - required_names
            parts: list[str] = []
            if missing:
                parts.append(f"missing: {', '.join(sorted(missing))}")
            if extra:
                parts.append(f"unexpected: {', '.join(sorted(extra))}")
            return False, f"Ship set mismatch — {'; '.join(parts)}"

        # --- Place each ship on a fresh board (atomic: all or nothing) ---
        # We work on the existing board since it starts empty. If any
        # placement fails, we reset the board to a clean state.
        board = self.boards[player_id]
        original_grid = [row[:] for row in board.grid]  # Shallow copy rows
        original_ships = board.ships[:]

        for ship_data in ships_data:
            success, msg = board.place_ship(
                name=ship_data["name"],
                row=ship_data["row"],
                col=ship_data["col"],
                horizontal=ship_data["horizontal"],
            )
            if not success:
                # Roll back: restore the board to its pre-placement state.
                board.grid = original_grid
                board.ships = original_ships
                return False, msg

        # --- All ships placed successfully ---
        self.ships_ready[player_id] = True
        return True, "OK"

    def both_players_ready(self) -> bool:
        """Check whether both players have placed all their ships."""
        return self.ships_ready[1] and self.ships_ready[2]

    def start_game(self) -> None:
        """Transition from SETUP to PLAYING phase.

        Should only be called after both_players_ready() returns True.

        Raises:
            RuntimeError: If called before both players are ready.
        """
        if not self.both_players_ready():
            raise RuntimeError(
                "Cannot start game: not all players have placed their ships"
            )
        self.phase = GamePhase.PLAYING

    # -- Gameplay phase -----------------------------------------------------

    def process_shot(self, player_id: int, row: int, col: int) -> dict:
        """Process a FIRE action from the given player.

        Validates the action, applies the shot to the opponent's board,
        checks for a win condition, and returns the result payload for
        broadcast to both clients.

        Args:
            player_id: The player firing the shot (1 or 2).
            row: Target row on the opponent's board (0-9).
            col: Target column on the opponent's board (0-9).

        Returns:
            A dict suitable for sending as a protocol message payload::

                {
                    "row": 3,
                    "col": 5,
                    "result": "hit" | "miss" | "sunk",
                    "sunk_ship": "Destroyer" | null,
                    "game_over": false,
                    "winner": null,
                    "next_turn": 2
                }

        Raises:
            ValueError: If the game is not in PLAYING phase, it is not this
                player's turn, or the target cell is invalid.
        """
        # --- Phase check ---
        if self.phase != GamePhase.PLAYING:
            raise ValueError(f"Cannot fire during the '{self.phase.value}' phase")

        # --- Turn check ---
        if player_id != self.current_turn:
            raise ValueError(
                f"It is Player {self.current_turn}'s turn, " f"not Player {player_id}'s"
            )

        # --- Determine the target board (opponent's) ---
        opponent_id: int = 2 if player_id == 1 else 1
        target_board: Board = self.boards[opponent_id]

        # --- Validate the target cell ---
        if not target_board.is_valid_target(row, col):
            raise ValueError(
                f"Cell ({row}, {col}) is not a valid target "
                f"(out of bounds or already targeted)"
            )

        # --- Apply the shot ---
        result, sunk_ship = target_board.receive_shot(row, col)

        # --- Check for game over ---
        game_over: bool = target_board.all_sunk()
        if game_over:
            self.phase = GamePhase.FINISHED
            self.winner = player_id

        # --- Advance the turn (only if the game is still going) ---
        next_turn: int = self.current_turn
        if not game_over:
            self.current_turn = opponent_id
            next_turn = opponent_id

        return {
            "row": row,
            "col": col,
            "result": result,
            "sunk_ship": sunk_ship,
            "game_over": game_over,
            "winner": self.winner,
            "next_turn": next_turn,
        }

    # -- Convenience --------------------------------------------------------

    def get_opponent_id(self, player_id: int) -> int:
        """Return the opponent's player_id."""
        return 2 if player_id == 1 else 1
