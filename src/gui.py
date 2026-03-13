"""
CMPT 371 A3: BroadSide - Tkinter GUI Module

Purpose:
    Renders the Battleship game interface using Tkinter Canvas widgets.
    Provides two 10x10 grids (own board and attack board), a ship
    placement system with hover preview, a firing interface with
    visual feedback, and a scrollable game log.

Architecture:
    The GUI is a passive view layer - it renders state and emits user
    actions via a callback, but does not own any game logic. The
    send_callback function (provided by GameClient) transmits actions
    to the server, and handle_server_message() processes incoming
    server messages to update the display.

    +-------------------------------------------------------------+
    |                    BroadSide                                 |
    |                                                              |
    |  YOUR FLEET              ATTACK BOARD                        |
    |  +------------------+    +------------------+                |
    |  |  10x10 Canvas    |    |  10x10 Canvas    |                |
    |  |  (own board)     |    |  (attack board)  |                |
    |  +------------------+    +------------------+                |
    |                                                              |
    |  [Current Ship: Carrier]  [Rotate: Horizontal]               |
    |  Status: Place your Carrier (5 cells)                        |
    |                                                              |
    |  +---------------------------------------------+             |
    |  | Game Log (scrollable)                        |             |
    |  | > Connected to server.                       |             |
    |  | > Match found! You are Player 1.             |             |
    |  +---------------------------------------------+             |
    +-------------------------------------------------------------+

Threading safety:
    All methods in this class MUST be called from the Tkinter main thread.
    The network thread dispatches messages here via root.after().

References:
    - Tkinter Canvas: https://docs.python.org/3/library/tkinter.html
    - Pillow ImageTk: https://pillow.readthedocs.io/en/stable/reference/ImageTk.html
    - Claude Code was used to assist with structuring the GUI layout and
      generating the Canvas rendering logic.
"""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Callable

from src.game_logic import BOARD_SIZE, SHIP_DEFINITIONS

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

# Each grid cell is a square of this many pixels.
CELL_SIZE: int = 40

# Padding between the grid edge and the cell area (for row/col labels).
LABEL_PAD: int = 25

# Color palette for cell states.
COLORS: dict[str, str] = {
    "empty": "#1a3a5c",  # Dark navy - untouched water
    "ship": "#708090",  # Steel gray - own ship segment
    "hit": "#e74c3c",  # Red - confirmed hit on a ship
    "miss": "#ecf0f1",  # Off-white - shot missed
    "sunk": "#c0392b",  # Dark red - sunk ship cell
    "hover_valid": "#3498db",  # Light blue - valid placement/target hover
    "hover_invalid": "#e74c3c",  # Red - invalid placement hover
    "grid_line": "#2c3e50",  # Dark slate - grid border lines
    "background": "#0d1b2a",  # Deep navy - window background
    "text": "#ecf0f1",  # Off-white - label text
    "title": "#e8c547",  # Gold - title text
    "log_bg": "#0a1628",  # Darker navy - log background
}

logger = logging.getLogger("BroadSide-GUI")


# ---------------------------------------------------------------------------
# GUI class
# ---------------------------------------------------------------------------


class BattleshipGUI:
    """Tkinter-based GUI for BroadSide.

    This class manages the entire visual interface:
        - Two 10x10 Canvas grids (own fleet + attack board).
        - Ship placement with hover preview and rotation.
        - Firing interface with click-to-fire and visual results.
        - Status bar showing game phase and turn information.
        - Scrollable game log showing all events.

    Attributes:
        root: The Tkinter root window.
        send_callback: Function to call when the user performs an action
            (e.g., placing ships, firing a shot). Accepts a dict message.
        player_id: Assigned by the server (1 or 2).
        phase: Current GUI phase ("connecting", "placement", "playing",
            "gameover").
        my_turn: Whether it is currently this player's turn to fire.
    """

    def __init__(self, send_callback: Callable[[dict], None]) -> None:
        """Initialize the GUI window and all widgets.

        Creates the Tkinter root window, builds the layout (grids,
        labels, buttons, log), and binds event handlers for mouse
        clicks and keyboard input.

        Args:
            send_callback: A function that accepts a dict and sends it
                to the server (provided by GameClient).
        """
        self.send_callback = send_callback
        self.player_id: int | None = None
        self.phase: str = "connecting"
        self.my_turn: bool = False

        # -- Ship placement state -----------------------------------------
        self.current_ship_index: int = 0
        self.is_horizontal: bool = True
        self.ships_to_place: list[str] = list(SHIP_DEFINITIONS.keys())
        # Stores placed ship data for the PLACE_SHIPS message.
        self.placed_ships: list[dict] = []
        # Tracks which cells on own board have ships (for rendering).
        self.own_ship_cells: set[tuple[int, int]] = set()

        # -- Attack board tracking ----------------------------------------
        # Tracks cells already fired at (prevents double-fire client-side).
        self.fired_cells: set[tuple[int, int]] = set()
        # Tracks sunk ship cells for dark-red rendering on attack board.
        self.attack_sunk_cells: set[tuple[int, int]] = set()
        # Tracks hit cells on attack board for RESULT rendering.
        self.attack_hit_cells: set[tuple[int, int]] = set()
        # Tracks miss cells on attack board.
        self.attack_miss_cells: set[tuple[int, int]] = set()

        # -- Own board hit/miss tracking (for opponent's shots) -----------
        self.own_hit_cells: set[tuple[int, int]] = set()
        self.own_miss_cells: set[tuple[int, int]] = set()

        # -- Build the UI ------------------------------------------------
        self._build_ui()

    # =====================================================================
    # UI Construction
    # =====================================================================

    def _build_ui(self) -> None:
        """Construct the complete Tkinter widget hierarchy.

        Layout (top to bottom):
            1. Title bar
            2. Board area (two Canvas grids side by side)
            3. Control panel (ship name, rotate button, status)
            4. Game log (scrollable text area)
        """
        self.root = tk.Tk()
        self.root.title("BroadSide - Battleship")
        self.root.configure(bg=COLORS["background"])
        self.root.resizable(False, False)

        # -- Title --------------------------------------------------------
        title_label = tk.Label(
            self.root,
            text="BroadSide",
            font=("Helvetica", 24, "bold"),
            fg=COLORS["title"],
            bg=COLORS["background"],
        )
        title_label.pack(pady=(10, 5))

        # -- Board area (two grids side by side) --------------------------
        board_frame = tk.Frame(self.root, bg=COLORS["background"])
        board_frame.pack(padx=20, pady=5)

        # Calculate canvas dimensions (grid + label padding).
        canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD

        # Left: Own board ("YOUR FLEET")
        own_frame = tk.Frame(board_frame, bg=COLORS["background"])
        own_frame.pack(side=tk.LEFT, padx=(0, 20))

        own_title = tk.Label(
            own_frame,
            text="YOUR FLEET",
            font=("Helvetica", 12, "bold"),
            fg=COLORS["text"],
            bg=COLORS["background"],
        )
        own_title.pack()

        self.own_canvas = tk.Canvas(
            own_frame,
            width=canvas_w,
            height=canvas_h,
            bg=COLORS["background"],
            highlightthickness=0,
        )
        self.own_canvas.pack()

        # Right: Attack board ("ATTACK BOARD")
        attack_frame = tk.Frame(board_frame, bg=COLORS["background"])
        attack_frame.pack(side=tk.LEFT)

        attack_title = tk.Label(
            attack_frame,
            text="ATTACK BOARD",
            font=("Helvetica", 12, "bold"),
            fg=COLORS["text"],
            bg=COLORS["background"],
        )
        attack_title.pack()

        self.attack_canvas = tk.Canvas(
            attack_frame,
            width=canvas_w,
            height=canvas_h,
            bg=COLORS["background"],
            highlightthickness=0,
        )
        self.attack_canvas.pack()

        # -- Control panel ------------------------------------------------
        ctrl_frame = tk.Frame(self.root, bg=COLORS["background"])
        ctrl_frame.pack(pady=5)

        # Current ship label (shown during placement).
        self.ship_label = tk.Label(
            ctrl_frame,
            text="",
            font=("Helvetica", 11),
            fg=COLORS["text"],
            bg=COLORS["background"],
        )
        self.ship_label.pack(side=tk.LEFT, padx=(0, 10))

        # Rotate button (shown during placement).
        self.rotate_btn = tk.Button(
            ctrl_frame,
            text="Rotate: Horizontal",
            font=("Helvetica", 10),
            command=self._toggle_rotation,
            state=tk.DISABLED,
        )
        self.rotate_btn.pack(side=tk.LEFT)

        # -- Status bar ---------------------------------------------------
        self.status_var = tk.StringVar(value="Connecting to server...")
        status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Helvetica", 12, "bold"),
            fg=COLORS["title"],
            bg=COLORS["background"],
        )
        status_label.pack(pady=5)

        # -- Game log (scrollable text) -----------------------------------
        log_frame = tk.Frame(self.root, bg=COLORS["background"])
        log_frame.pack(padx=20, pady=(0, 10), fill=tk.X)

        log_title = tk.Label(
            log_frame,
            text="Game Log",
            font=("Helvetica", 10, "bold"),
            fg=COLORS["text"],
            bg=COLORS["background"],
            anchor=tk.W,
        )
        log_title.pack(fill=tk.X)

        self.log_text = tk.Text(
            log_frame,
            height=6,
            width=70,
            font=("Courier", 10),
            fg=COLORS["text"],
            bg=COLORS["log_bg"],
            state=tk.DISABLED,
            wrap=tk.WORD,
            borderwidth=1,
            relief=tk.SUNKEN,
        )
        self.log_text.pack(fill=tk.X)

        log_scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        # -- Draw initial grids -------------------------------------------
        self._draw_grid(self.own_canvas)
        self._draw_grid(self.attack_canvas)

        # -- Bind events --------------------------------------------------
        # Own board: placement clicks and hover.
        self.own_canvas.bind("<Button-1>", self._on_own_board_click)
        self.own_canvas.bind("<Motion>", self._on_own_board_hover)
        self.own_canvas.bind("<Leave>", self._on_own_board_leave)
        # Right-click to rotate during placement.
        self.own_canvas.bind("<Button-3>", lambda _e: self._toggle_rotation())

        # Attack board: fire clicks and hover.
        self.attack_canvas.bind("<Button-1>", self._on_attack_board_click)
        self.attack_canvas.bind("<Motion>", self._on_attack_board_hover)
        self.attack_canvas.bind("<Leave>", self._on_attack_board_leave)

        # Keyboard: R to rotate during placement.
        self.root.bind("<r>", lambda _e: self._toggle_rotation())
        self.root.bind("<R>", lambda _e: self._toggle_rotation())

    # =====================================================================
    # Grid Drawing
    # =====================================================================

    def _draw_grid(self, canvas: tk.Canvas) -> None:
        """Draw a 10x10 grid of empty water cells with row/column labels.

        Each cell is tagged with ``cell_R_C`` for later lookup and
        color changes.

        Args:
            canvas: The Canvas widget to draw on.
        """
        canvas.delete("all")

        # Draw column labels (A-J).
        for c in range(BOARD_SIZE):
            x = LABEL_PAD + c * CELL_SIZE + CELL_SIZE // 2
            canvas.create_text(
                x,
                LABEL_PAD // 2,
                text=chr(65 + c),  # A, B, C, ...
                fill=COLORS["text"],
                font=("Helvetica", 9, "bold"),
            )

        # Draw row labels (1-10).
        for r in range(BOARD_SIZE):
            y = LABEL_PAD + r * CELL_SIZE + CELL_SIZE // 2
            canvas.create_text(
                LABEL_PAD // 2,
                y,
                text=str(r + 1),
                fill=COLORS["text"],
                font=("Helvetica", 9, "bold"),
            )

        # Draw cells.
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                x1 = LABEL_PAD + c * CELL_SIZE
                y1 = LABEL_PAD + r * CELL_SIZE
                x2 = x1 + CELL_SIZE
                y2 = y1 + CELL_SIZE

                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=COLORS["empty"],
                    outline=COLORS["grid_line"],
                    width=1,
                    tags=(f"cell_{r}_{c}",),
                )

    def _set_cell_color(
        self, canvas: tk.Canvas, row: int, col: int, color: str
    ) -> None:
        """Change the fill color of a specific grid cell.

        Args:
            canvas: The Canvas containing the cell.
            row: Row index (0-9).
            col: Column index (0-9).
            color: The hex color string to fill with.
        """
        tag = f"cell_{row}_{col}"
        canvas.itemconfigure(tag, fill=color)

    def _cell_from_pixel(self, x: int, y: int) -> tuple[int, int] | None:
        """Convert pixel coordinates to grid (row, col), or None if out of bounds.

        Args:
            x: Pixel x-coordinate from the Canvas event.
            y: Pixel y-coordinate from the Canvas event.

        Returns:
            A (row, col) tuple if the pixel is inside the grid, else None.
        """
        col = (x - LABEL_PAD) // CELL_SIZE
        row = (y - LABEL_PAD) // CELL_SIZE

        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            return row, col
        return None

    # =====================================================================
    # Ship Placement
    # =====================================================================

    def _enter_placement_phase(self) -> None:
        """Transition the GUI into ship placement mode.

        Resets placement state, enables the rotate button, and updates
        the status bar to prompt the player to place their first ship.
        """
        self.phase = "placement"
        self.current_ship_index = 0
        self.is_horizontal = True
        self.placed_ships = []
        self.own_ship_cells = set()
        self.rotate_btn.configure(state=tk.NORMAL)
        self._update_placement_labels()

    def _update_placement_labels(self) -> None:
        """Update the ship label and status bar for the current ship."""
        if self.current_ship_index < len(self.ships_to_place):
            name = self.ships_to_place[self.current_ship_index]
            size = SHIP_DEFINITIONS[name]
            self.ship_label.configure(text=f"Ship: {name} ({size} cells)")
            self.status_var.set(f"Place your {name} ({size} cells)")
        else:
            self.ship_label.configure(text="")
            self.status_var.set("Waiting for opponent to place ships...")

    def _toggle_rotation(self) -> None:
        """Toggle ship orientation between horizontal and vertical."""
        if self.phase != "placement":
            return
        self.is_horizontal = not self.is_horizontal
        direction = "Horizontal" if self.is_horizontal else "Vertical"
        self.rotate_btn.configure(text=f"Rotate: {direction}")

    def _get_ship_cells(
        self, row: int, col: int, size: int, horizontal: bool
    ) -> list[tuple[int, int]] | None:
        """Compute the cells a ship would occupy, or None if out of bounds.

        Args:
            row: Starting row.
            col: Starting column.
            size: Ship length.
            horizontal: True for rightward, False for downward.

        Returns:
            A list of (row, col) tuples, or None if any cell is out of bounds.
        """
        cells = []
        for i in range(size):
            r = row if horizontal else row + i
            c = col + i if horizontal else col
            if not (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE):
                return None
            cells.append((r, c))
        return cells

    def _is_valid_placement(self, cells: list[tuple[int, int]]) -> bool:
        """Check whether the given cells are free (no overlap with placed ships).

        Args:
            cells: The list of (row, col) positions to check.

        Returns:
            True if none of the cells overlap with existing ships.
        """
        return not any(cell in self.own_ship_cells for cell in cells)

    def _on_own_board_hover(self, event: tk.Event) -> None:
        """Show a hover preview of the current ship on the own board.

        Highlights cells in blue (valid) or red (invalid/out of bounds).

        Args:
            event: The Tkinter Motion event with pixel coordinates.
        """
        if self.phase != "placement":
            return
        if self.current_ship_index >= len(self.ships_to_place):
            return

        # Clear any previous hover preview.
        self._redraw_own_board()

        cell = self._cell_from_pixel(event.x, event.y)
        if cell is None:
            return

        row, col = cell
        name = self.ships_to_place[self.current_ship_index]
        size = SHIP_DEFINITIONS[name]

        cells = self._get_ship_cells(row, col, size, self.is_horizontal)

        if cells is None:
            # Ship extends beyond the board - show red on the starting cell.
            self._set_cell_color(self.own_canvas, row, col, COLORS["hover_invalid"])
            return

        valid = self._is_valid_placement(cells)
        color = COLORS["hover_valid"] if valid else COLORS["hover_invalid"]

        for r, c in cells:
            self._set_cell_color(self.own_canvas, r, c, color)

    def _on_own_board_leave(self, _event: tk.Event) -> None:
        """Clear the hover preview when the mouse leaves the own board."""
        if self.phase == "placement":
            self._redraw_own_board()

    def _on_own_board_click(self, event: tk.Event) -> None:
        """Handle a left-click on the own board to place a ship.

        Validates the placement locally, adds the ship cells to the
        internal tracking set, and advances to the next ship. When all
        5 ships are placed, sends the PLACE_SHIPS message to the server.

        Args:
            event: The Tkinter Button-1 event with pixel coordinates.
        """
        if self.phase != "placement":
            return
        if self.current_ship_index >= len(self.ships_to_place):
            return

        cell = self._cell_from_pixel(event.x, event.y)
        if cell is None:
            return

        row, col = cell
        name = self.ships_to_place[self.current_ship_index]
        size = SHIP_DEFINITIONS[name]

        cells = self._get_ship_cells(row, col, size, self.is_horizontal)
        if cells is None or not self._is_valid_placement(cells):
            # Invalid placement - flash and ignore.
            self.status_var.set(f"Invalid placement for {name}! Try again.")
            return

        # Commit the placement locally.
        for r, c in cells:
            self.own_ship_cells.add((r, c))

        self.placed_ships.append(
            {
                "name": name,
                "row": row,
                "col": col,
                "horizontal": self.is_horizontal,
            }
        )

        self.log(
            f"Placed {name} at ({row}, {col}) "
            f"{'horizontal' if self.is_horizontal else 'vertical'}."
        )

        # Advance to the next ship.
        self.current_ship_index += 1
        self._redraw_own_board()
        self._update_placement_labels()

        # If all ships are placed, send to server.
        if self.current_ship_index >= len(self.ships_to_place):
            self.rotate_btn.configure(state=tk.DISABLED)
            self.send_callback({"type": "PLACE_SHIPS", "ships": self.placed_ships})
            self.log("All ships placed! Sending to server...")

    def _redraw_own_board(self) -> None:
        """Redraw the own board, showing placed ships, hits, and misses."""
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if (r, c) in self.own_hit_cells:
                    color = COLORS["hit"]
                elif (r, c) in self.own_miss_cells:
                    color = COLORS["miss"]
                elif (r, c) in self.own_ship_cells:
                    color = COLORS["ship"]
                else:
                    color = COLORS["empty"]
                self._set_cell_color(self.own_canvas, r, c, color)

    # =====================================================================
    # Firing (Gameplay)
    # =====================================================================

    def _enter_playing_phase(self, first_turn: int) -> None:
        """Transition the GUI into the gameplay phase.

        Disables the placement controls and enables the attack board
        for firing.

        Args:
            first_turn: The player_id who goes first (1 or 2).
        """
        self.phase = "playing"
        self.rotate_btn.configure(state=tk.DISABLED)
        self.ship_label.configure(text="")
        self.fired_cells = set()
        self.my_turn = first_turn == self.player_id
        self._update_turn_status()

    def _update_turn_status(self) -> None:
        """Update the status bar to reflect whose turn it is."""
        if self.my_turn:
            self.status_var.set("Your turn! Click the attack board to fire.")
        else:
            self.status_var.set("Opponent's turn... waiting.")

    def _on_attack_board_click(self, event: tk.Event) -> None:
        """Handle a left-click on the attack board to fire a shot.

        Validates client-side that it is the player's turn and the cell
        has not been fired at before, then sends the FIRE message.

        Args:
            event: The Tkinter Button-1 event with pixel coordinates.
        """
        if self.phase != "playing":
            return
        if not self.my_turn:
            self.status_var.set("Not your turn!")
            return

        cell = self._cell_from_pixel(event.x, event.y)
        if cell is None:
            return

        row, col = cell

        # Client-side duplicate check (prevents wasted server round-trips).
        if (row, col) in self.fired_cells:
            self.status_var.set("Already targeted! Choose another cell.")
            return

        # Record the fire and disable further clicks until RESULT arrives.
        self.fired_cells.add((row, col))
        self.my_turn = False
        self.status_var.set(f"Fired at ({row}, {col})... waiting for result.")

        self.send_callback({"type": "FIRE", "row": row, "col": col})

    def _on_attack_board_hover(self, event: tk.Event) -> None:
        """Highlight the hovered cell on the attack board during gameplay.

        Shows a blue highlight on valid targets, no change on already-fired.

        Args:
            event: The Tkinter Motion event.
        """
        if self.phase != "playing" or not self.my_turn:
            return

        # Reset all un-fired cells to their base color.
        self._redraw_attack_board()

        cell = self._cell_from_pixel(event.x, event.y)
        if cell is None:
            return

        row, col = cell
        if (row, col) not in self.fired_cells:
            self._set_cell_color(self.attack_canvas, row, col, COLORS["hover_valid"])

    def _on_attack_board_leave(self, _event: tk.Event) -> None:
        """Clear hover when the mouse leaves the attack board."""
        if self.phase == "playing":
            self._redraw_attack_board()

    def _redraw_attack_board(self) -> None:
        """Redraw the attack board with current hit/miss/sunk state."""
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if (r, c) in self.attack_sunk_cells:
                    color = COLORS["sunk"]
                elif (r, c) in self.attack_hit_cells:
                    color = COLORS["hit"]
                elif (r, c) in self.attack_miss_cells:
                    color = COLORS["miss"]
                else:
                    color = COLORS["empty"]
                self._set_cell_color(self.attack_canvas, r, c, color)

    # =====================================================================
    # Server Message Handler
    # =====================================================================

    def handle_server_message(self, message: dict) -> None:
        """Process an incoming message from the server and update the GUI.

        This is the single entry point for all server-to-GUI communication.
        It is always called on the Tkinter main thread (via root.after()).

        Supported message types:
            - WAIT: Server tells us to wait for an opponent.
            - WELCOME: Assigns our player_id.
            - GAME_START: Opponent found, begin ship placement.
            - SHIPS_CONFIRMED: Our placement was accepted.
            - SHIPS_REJECTED: Our placement was invalid.
            - ALL_READY: Both players placed, game begins.
            - YOUR_TURN / OPPONENT_TURN: Turn notifications.
            - RESULT: Shot result broadcast.
            - GAME_OVER: Game ended.
            - OPPONENT_DISCONNECTED: Other player left.
            - ERROR: Server-side validation error.

        Args:
            message: A deserialized protocol message from the server.
        """
        msg_type = message.get("type", "")

        if msg_type == "WAIT":
            self._handle_wait(message)
        elif msg_type == "WELCOME":
            self._handle_welcome(message)
        elif msg_type == "GAME_START":
            self._handle_game_start(message)
        elif msg_type == "SHIPS_CONFIRMED":
            self._handle_ships_confirmed(message)
        elif msg_type == "SHIPS_REJECTED":
            self._handle_ships_rejected(message)
        elif msg_type == "ALL_READY":
            self._handle_all_ready(message)
        elif msg_type == "YOUR_TURN":
            self._handle_your_turn()
        elif msg_type == "OPPONENT_TURN":
            self._handle_opponent_turn()
        elif msg_type == "RESULT":
            self._handle_result(message)
        elif msg_type == "GAME_OVER":
            self._handle_game_over(message)
        elif msg_type == "OPPONENT_DISCONNECTED":
            self._handle_opponent_disconnected(message)
        elif msg_type == "ERROR":
            self._handle_error(message)
        else:
            logger.warning("Unknown message type: %s", msg_type)

    # -- Individual message handlers --------------------------------------

    def _handle_wait(self, message: dict) -> None:
        """Handle WAIT: waiting for an opponent to connect."""
        self.status_var.set("Waiting for an opponent to connect...")
        self.log(message.get("message", "Waiting for opponent..."))

    def _handle_welcome(self, message: dict) -> None:
        """Handle WELCOME: server assigned our player_id."""
        self.player_id = message.get("player_id")
        self.root.title(f"BroadSide - Player {self.player_id}")
        self.log(f"Connected! You are Player {self.player_id}.")
        self.status_var.set(f"Player {self.player_id} - Waiting for match...")

    def _handle_game_start(self, message: dict) -> None:
        """Handle GAME_START: opponent found, begin placement."""
        self.log("Opponent found! Place your ships.")
        self._enter_placement_phase()

    def _handle_ships_confirmed(self, message: dict) -> None:
        """Handle SHIPS_CONFIRMED: server accepted our placement."""
        self.log("Ships confirmed by server!")
        self.status_var.set("Ships placed! Waiting for opponent...")

    def _handle_ships_rejected(self, message: dict) -> None:
        """Handle SHIPS_REJECTED: server rejected our placement.

        Resets the placement state so the player can try again.
        """
        reason = message.get("message", "Unknown reason")
        self.log(f"Ships rejected: {reason}")
        self.status_var.set("Placement rejected! Try again.")

        # Reset placement state for a retry.
        self.current_ship_index = 0
        self.placed_ships = []
        self.own_ship_cells = set()
        self.rotate_btn.configure(state=tk.NORMAL)
        self._redraw_own_board()
        self._update_placement_labels()

    def _handle_all_ready(self, message: dict) -> None:
        """Handle ALL_READY: both players placed, game begins."""
        first_turn = message.get("turn", 1)
        self.log("All ships placed! Game starting!")
        self._enter_playing_phase(first_turn)

    def _handle_your_turn(self) -> None:
        """Handle YOUR_TURN: it is now our turn to fire."""
        self.my_turn = True
        self._update_turn_status()

    def _handle_opponent_turn(self) -> None:
        """Handle OPPONENT_TURN: it is now the opponent's turn."""
        self.my_turn = False
        self._update_turn_status()

    def _handle_result(self, message: dict) -> None:
        """Handle RESULT: a shot result broadcast from the server.

        Determines whether this was our shot (update attack board) or
        the opponent's shot (update own board), then renders the result.

        The ``player`` field in the RESULT identifies who fired the shot.
        If ``player == self.player_id``, we fired it (update attack board).
        Otherwise, the opponent fired at us (update own board).

        Args:
            message: The RESULT message with row, col, result, sunk_ship,
                game_over, winner, next_turn, and player fields.
        """
        row = message["row"]
        col = message["col"]
        result = message["result"]
        sunk_ship = message.get("sunk_ship")
        shooter = message.get("player")

        if shooter == self.player_id:
            # We fired this shot - update the attack board.
            self._apply_attack_result(row, col, result, sunk_ship)
        else:
            # Opponent fired at us - update our own board.
            self._apply_own_board_result(row, col, result, sunk_ship)

    def _apply_attack_result(
        self, row: int, col: int, result: str, sunk_ship: str | None
    ) -> None:
        """Render a shot result on the attack board (our shot at opponent).

        Args:
            row: Target row.
            col: Target column.
            result: "hit", "miss", or "sunk".
            sunk_ship: Name of the sunk ship, or None.
        """
        if result == "miss":
            self.attack_miss_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["miss"])
            self.log(f"Shot at ({row}, {col}): Miss.")
        elif result == "hit":
            self.attack_hit_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["hit"])
            self.log(f"Shot at ({row}, {col}): Hit!")
        elif result == "sunk":
            self.attack_hit_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["sunk"])
            self.log(f"Shot at ({row}, {col}): Sunk {sunk_ship}!")

    def _apply_own_board_result(
        self, row: int, col: int, result: str, sunk_ship: str | None
    ) -> None:
        """Render an opponent's shot on our own board.

        Args:
            row: Target row on our board.
            col: Target column on our board.
            result: "hit", "miss", or "sunk".
            sunk_ship: Name of the sunk ship, or None.
        """
        if result == "miss":
            self.own_miss_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["miss"])
            self.log(f"Opponent fired at ({row}, {col}): Miss.")
        elif result == "hit":
            self.own_hit_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["hit"])
            self.log(f"Opponent fired at ({row}, {col}): Hit!")
        elif result == "sunk":
            self.own_hit_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["sunk"])
            self.log(f"Opponent fired at ({row}, {col}): Sunk your {sunk_ship}!")

    def _handle_game_over(self, message: dict) -> None:
        """Handle GAME_OVER: display victory or defeat overlay.

        Args:
            message: The GAME_OVER message with winner and reason fields.
        """
        self.phase = "gameover"
        self.my_turn = False
        winner = message.get("winner")
        reason = message.get("reason", "")

        if winner == self.player_id:
            result_text = "VICTORY!"
            self.log(f"You win! {reason}")
            overlay_color = "#27ae60"  # Green
        else:
            result_text = "DEFEAT"
            self.log(f"You lose. {reason}")
            overlay_color = "#c0392b"  # Red

        self.status_var.set(result_text)

        # Draw a semi-transparent overlay on both canvases.
        for canvas in (self.own_canvas, self.attack_canvas):
            canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
            canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD

            # Overlay rectangle.
            canvas.create_rectangle(
                0,
                0,
                canvas_w,
                canvas_h,
                fill=overlay_color,
                stipple="gray50",
                tags=("overlay",),
            )

            # Result text centered on the canvas.
            canvas.create_text(
                canvas_w // 2,
                canvas_h // 2,
                text=result_text,
                fill="white",
                font=("Helvetica", 28, "bold"),
                tags=("overlay",),
            )

    def _handle_opponent_disconnected(self, message: dict) -> None:
        """Handle OPPONENT_DISCONNECTED: show a notification."""
        msg = message.get("message", "Your opponent has disconnected.")
        self.phase = "gameover"
        self.my_turn = False
        self.status_var.set("Opponent disconnected!")
        self.log(msg)

    def _handle_error(self, message: dict) -> None:
        """Handle ERROR: show the server's error message."""
        error_msg = message.get("message", "Unknown error from server.")
        self.log(f"Server error: {error_msg}")
        # If it was a turn-related error, re-enable our turn.
        if self.phase == "playing":
            self.my_turn = True
            self._update_turn_status()

    # =====================================================================
    # Game Log
    # =====================================================================

    def log(self, text: str) -> None:
        """Append a line to the scrollable game log panel.

        The log is a read-only Text widget. We temporarily enable it,
        insert the new line, then re-disable it to prevent user editing.

        Args:
            text: The message to display (e.g., "Player 1 hit B5!").
        """
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"> {text}\n")
        self.log_text.see(tk.END)  # Auto-scroll to the latest entry.
        self.log_text.configure(state=tk.DISABLED)

    # =====================================================================
    # Main Loop
    # =====================================================================

    def run(self) -> None:
        """Start the Tkinter main event loop.

        This method blocks until the user closes the window or the
        application calls ``root.destroy()``.
        """
        self.root.mainloop()
