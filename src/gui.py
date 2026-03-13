"""
CMPT 371 A3: BroadSide - Tkinter GUI Module

Purpose:
    Renders the Battleship game interface using Tkinter Canvas widgets.
    Provides two 10x10 grids (own board and attack board), a ship
    placement system with hover preview, a firing interface with
    visual feedback, a ship roster panel, and a scrollable game log.

Architecture:
    The GUI is a passive view layer - it renders state and emits user
    actions via a callback, but does not own any game logic. The
    send_callback function (provided by GameClient) transmits actions
    to the server, and handle_server_message() processes incoming
    server messages to update the display.

Threading safety:
    All methods in this class MUST be called from the Tkinter main thread.
    The network thread dispatches messages here via root.after().

References:
    - Tkinter Canvas: https://docs.python.org/3/library/tkinter.html
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

# Color palette for all UI elements.
COLORS: dict[str, str] = {
    # -- Cell state backgrounds -------------------------------------------
    "empty": "#0d2137",           # Deep navy — untouched water
    "ship": "#4a6272",            # Steel blue-gray — own ship segment
    "hit": "#7f0000",             # Dark crimson — hit cell background
    "miss": "#1c2b38",            # Very dark slate — missed cell background
    "sunk": "#3d0000",            # Near-black red — sunk ship cell
    "hover_valid": "#1a4d8a",     # Deep blue — valid placement/target hover
    "hover_invalid": "#7f0000",   # Deep red — invalid placement hover
    # -- Grid -------------------------------------------------------------
    "grid_line": "#091523",       # Very dark — cell borders
    # -- Window -----------------------------------------------------------
    "background": "#060e1a",      # Deep space navy — window background
    "panel_bg": "#0a1628",        # Slightly lighter — panel areas
    # -- Typography -------------------------------------------------------
    "text": "#9db8c8",            # Cool off-white — general labels
    "text_bright": "#dde9f0",     # Bright white — important text
    "text_dim": "#3d5566",        # Dimmed — secondary labels
    "title": "#ffd54f",           # Amber gold — main title
    "title_own": "#4dd0e1",       # Cyan — YOUR FLEET heading
    "title_attack": "#ef5350",    # Coral red — ATTACK BOARD heading
    # -- Game log ---------------------------------------------------------
    "log_bg": "#040b14",          # Very dark — log background
    # -- Status bar backgrounds -------------------------------------------
    "status_turn_bg": "#0d2e0d",  # Dark green — your turn
    "status_wait_bg": "#0a1628",  # Dark navy — waiting
    "status_over_bg": "#2e0d0d",  # Dark red — game over
    # -- Cell markers (drawn on top of cell rectangles) -------------------
    "hit_marker": "#ff5252",      # Bright red — hit X lines
    "sunk_marker": "#ff6d00",     # Bright orange-red — sunk X lines
    "miss_marker": "#4a7a99",     # Steel blue — miss circle outline
    # -- Ship placement roster --------------------------------------------
    "roster_placed_bg": "#1b3d1b",    # Dark green — ship placed
    "roster_placed_fg": "#81c784",    # Light green text
    "roster_current_bg": "#0d2e52",   # Dark blue — current ship to place
    "roster_current_fg": "#90caf9",   # Light blue text
    "roster_pending_bg": "#0d1f2d",   # Dark — pending ship
    "roster_pending_fg": "#3d5566",   # Dim text
    # -- Buttons ----------------------------------------------------------
    "btn_bg": "#0d2137",
    "btn_fg": "#9db8c8",
    "btn_active_bg": "#163352",
    # -- Separator line ---------------------------------------------------
    "separator": "#1e3a5f",
}

logger = logging.getLogger("BroadSide-GUI")


# ---------------------------------------------------------------------------
# GUI class
# ---------------------------------------------------------------------------


class BattleshipGUI:
    """Tkinter-based GUI for BroadSide.

    Manages the complete visual interface:
        - Two 10x10 Canvas grids (own fleet + attack board).
        - Ship placement with hover preview, rotation, and a roster panel.
        - Firing interface with click-to-fire, X/O markers, and visual results.
        - Dynamic status bar that changes color based on game state.
        - Scrollable game log showing all events.

    Attributes:
        root: The Tkinter root window.
        send_callback: Function to call when the user performs an action.
        player_id: Assigned by the server (1 or 2).
        phase: Current GUI phase ("connecting", "placement", "playing", "gameover").
        my_turn: Whether it is currently this player's turn to fire.
    """

    def __init__(self, send_callback: Callable[[dict], None]) -> None:
        """Initialize the GUI window and all widgets.

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
        self.placed_ships: list[dict] = []
        self.own_ship_cells: set[tuple[int, int]] = set()

        # -- Attack board tracking ----------------------------------------
        self.fired_cells: set[tuple[int, int]] = set()
        self.attack_sunk_cells: set[tuple[int, int]] = set()
        self.attack_hit_cells: set[tuple[int, int]] = set()
        self.attack_miss_cells: set[tuple[int, int]] = set()

        # -- Own board hit/miss/sunk tracking (opponent's shots) ----------
        self.own_hit_cells: set[tuple[int, int]] = set()
        self.own_miss_cells: set[tuple[int, int]] = set()
        self.own_sunk_cells: set[tuple[int, int]] = set()

        # -- Ship roster widget references (built in _build_roster) -------
        self.roster_frames: list[tk.Frame] = []
        self.roster_labels: list[tk.Label] = []

        # -- Build the UI -------------------------------------------------
        self._build_ui()

    # =====================================================================
    # UI Construction
    # =====================================================================

    def _build_ui(self) -> None:
        """Construct the complete Tkinter widget hierarchy.

        Layout (top to bottom):
            1. Title bar with subtitle and separator
            2. Board area (two Canvas grids side by side)
            3. Fleet deployment roster (ship placement checklist)
            4. Control panel (ship name label + rotate button)
            5. Status bar (color changes with game state)
            6. Game log (scrollable text area)
        """
        self.root = tk.Tk()
        self.root.title("BroadSide — Battleship")
        self.root.configure(bg=COLORS["background"])
        self.root.resizable(False, False)

        # -- Title area ---------------------------------------------------
        title_frame = tk.Frame(self.root, bg=COLORS["background"])
        title_frame.pack(pady=(12, 0))

        tk.Label(
            title_frame,
            text="BroadSide",
            font=("Helvetica", 28, "bold"),
            fg=COLORS["title"],
            bg=COLORS["background"],
        ).pack()

        tk.Label(
            title_frame,
            text="N A V A L   W A R F A R E",
            font=("Helvetica", 8),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
        ).pack(pady=(1, 4))

        # Thin separator line under the title.
        tk.Frame(self.root, bg=COLORS["separator"], height=1).pack(
            fill=tk.X, padx=30, pady=(0, 8)
        )

        # -- Board area (two grids side by side) --------------------------
        board_frame = tk.Frame(self.root, bg=COLORS["background"])
        board_frame.pack(padx=20, pady=0)

        # Calculate canvas dimensions (grid cells + label padding).
        canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD

        # Left: Own board ("YOUR FLEET") in cyan.
        own_frame = tk.Frame(board_frame, bg=COLORS["background"])
        own_frame.pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(
            own_frame,
            text="YOUR FLEET",
            font=("Helvetica", 11, "bold"),
            fg=COLORS["title_own"],
            bg=COLORS["background"],
        ).pack(pady=(0, 4))

        self.own_canvas = tk.Canvas(
            own_frame,
            width=canvas_w,
            height=canvas_h,
            bg=COLORS["background"],
            highlightthickness=0,
        )
        self.own_canvas.pack()

        # Right: Attack board ("ATTACK BOARD") in coral red.
        attack_frame = tk.Frame(board_frame, bg=COLORS["background"])
        attack_frame.pack(side=tk.LEFT)

        tk.Label(
            attack_frame,
            text="ATTACK BOARD",
            font=("Helvetica", 11, "bold"),
            fg=COLORS["title_attack"],
            bg=COLORS["background"],
        ).pack(pady=(0, 4))

        self.attack_canvas = tk.Canvas(
            attack_frame,
            width=canvas_w,
            height=canvas_h,
            bg=COLORS["background"],
            highlightthickness=0,
        )
        self.attack_canvas.pack()

        # -- Fleet deployment roster --------------------------------------
        self._build_roster()

        # -- Control panel ------------------------------------------------
        ctrl_frame = tk.Frame(self.root, bg=COLORS["background"])
        ctrl_frame.pack(pady=(8, 4))

        # Current ship label (shown during placement).
        self.ship_label = tk.Label(
            ctrl_frame,
            text="",
            font=("Helvetica", 11),
            fg=COLORS["text"],
            bg=COLORS["background"],
        )
        self.ship_label.pack(side=tk.LEFT, padx=(0, 12))

        # Themed rotate button (shown during placement).
        self.rotate_btn = tk.Button(
            ctrl_frame,
            text="  Rotate: Horizontal  ",
            font=("Helvetica", 10),
            command=self._toggle_rotation,
            state=tk.DISABLED,
            bg=COLORS["btn_bg"],
            fg=COLORS["btn_fg"],
            activebackground=COLORS["btn_active_bg"],
            activeforeground=COLORS["text_bright"],
            disabledforeground=COLORS["text_dim"],
            relief=tk.FLAT,
            padx=10,
            pady=4,
            cursor="hand2",
        )
        self.rotate_btn.pack(side=tk.LEFT)

        # -- Status bar (colored frame changes with game state) -----------
        self.status_frame = tk.Frame(
            self.root, bg=COLORS["status_wait_bg"], pady=6
        )
        self.status_frame.pack(fill=tk.X, padx=20, pady=(4, 4))

        self.status_var = tk.StringVar(value="Connecting to server...")
        self.status_label = tk.Label(
            self.status_frame,
            textvariable=self.status_var,
            font=("Helvetica", 12, "bold"),
            fg=COLORS["text_bright"],
            bg=COLORS["status_wait_bg"],
        )
        self.status_label.pack()

        # -- Game log (scrollable text) -----------------------------------
        log_frame = tk.Frame(self.root, bg=COLORS["background"])
        log_frame.pack(padx=20, pady=(0, 12), fill=tk.X)

        tk.Label(
            log_frame,
            text="GAME LOG",
            font=("Helvetica", 8, "bold"),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 2))

        text_frame = tk.Frame(log_frame, bg=COLORS["background"])
        text_frame.pack(fill=tk.X)

        self.log_text = tk.Text(
            text_frame,
            height=5,
            width=70,
            font=("Courier", 9),
            fg=COLORS["text"],
            bg=COLORS["log_bg"],
            state=tk.DISABLED,
            wrap=tk.WORD,
            borderwidth=0,
            relief=tk.FLAT,
            padx=6,
            pady=4,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        log_scrollbar = tk.Scrollbar(text_frame, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        # -- Draw initial grids -------------------------------------------
        self._draw_grid(self.own_canvas)
        self._draw_grid(self.attack_canvas)

        # -- Bind events --------------------------------------------------
        self.own_canvas.bind("<Button-1>", self._on_own_board_click)
        self.own_canvas.bind("<Motion>", self._on_own_board_hover)
        self.own_canvas.bind("<Leave>", self._on_own_board_leave)
        self.own_canvas.bind("<Button-3>", lambda _e: self._toggle_rotation())

        self.attack_canvas.bind("<Button-1>", self._on_attack_board_click)
        self.attack_canvas.bind("<Motion>", self._on_attack_board_hover)
        self.attack_canvas.bind("<Leave>", self._on_attack_board_leave)

        self.root.bind("<r>", lambda _e: self._toggle_rotation())
        self.root.bind("<R>", lambda _e: self._toggle_rotation())

    def _build_roster(self) -> None:
        """Build the fleet deployment roster panel.

        Displays a row of 5 ship boxes, one per ship in SHIP_DEFINITIONS.
        Each box shows the ship name, a visual size indicator, and cell count.
        Colors update as ships are placed: dark (pending) → blue (current) → green (placed).
        """
        self.roster_outer = tk.Frame(self.root, bg=COLORS["background"])
        self.roster_outer.pack(pady=(6, 0))

        tk.Label(
            self.roster_outer,
            text="FLEET DEPLOYMENT",
            font=("Helvetica", 8),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
        ).pack(pady=(0, 4))

        ships_row = tk.Frame(self.roster_outer, bg=COLORS["background"])
        ships_row.pack()

        self.roster_frames = []
        self.roster_labels = []

        for name, size in SHIP_DEFINITIONS.items():
            # Each ship gets a padded box with name, block indicator, and size.
            box = tk.Frame(
                ships_row,
                bg=COLORS["roster_pending_bg"],
                padx=10,
                pady=5,
            )
            box.pack(side=tk.LEFT, padx=3)

            lbl = tk.Label(
                box,
                text=f"{name}\n{'■ ' * size}\n{size} cells",
                font=("Courier", 8),
                fg=COLORS["roster_pending_fg"],
                bg=COLORS["roster_pending_bg"],
                justify=tk.CENTER,
            )
            lbl.pack()

            self.roster_frames.append(box)
            self.roster_labels.append(lbl)

    def _update_ship_roster(self) -> None:
        """Refresh the roster panel to reflect current placement progress.

        Colors:
            - Pending (not yet placed): dark background, dim text.
            - Current (being placed now): blue background, bright text with arrow.
            - Placed (already placed): green background, checkmark in name.
        """
        for i, (name, size) in enumerate(SHIP_DEFINITIONS.items()):
            blocks = "■ " * size
            if i < self.current_ship_index:
                bg = COLORS["roster_placed_bg"]
                fg = COLORS["roster_placed_fg"]
                text = f"✓ {name}\n{blocks}\n{size} cells"
            elif i == self.current_ship_index and self.phase == "placement":
                bg = COLORS["roster_current_bg"]
                fg = COLORS["roster_current_fg"]
                text = f"▶ {name}\n{blocks}\n{size} cells"
            else:
                bg = COLORS["roster_pending_bg"]
                fg = COLORS["roster_pending_fg"]
                text = f"{name}\n{blocks}\n{size} cells"

            self.roster_frames[i].configure(bg=bg)
            self.roster_labels[i].configure(bg=bg, fg=fg, text=text)

    def _set_status_style(self, style: str) -> None:
        """Update the status bar background color to reflect game state.

        Args:
            style: One of "turn" (your turn, green), "wait" (waiting, navy),
                or "over" (game finished, dark red).
        """
        bg_map = {
            "turn": COLORS["status_turn_bg"],
            "wait": COLORS["status_wait_bg"],
            "over": COLORS["status_over_bg"],
        }
        bg = bg_map.get(style, COLORS["status_wait_bg"])
        self.status_frame.configure(bg=bg)
        self.status_label.configure(bg=bg)

    # =====================================================================
    # Grid Drawing
    # =====================================================================

    def _draw_grid(self, canvas: tk.Canvas) -> None:
        """Draw a 10x10 grid of empty water cells with row/column labels.

        Each cell is tagged with ``cell_R_C`` for later color changes via
        itemconfigure. Labels use A-J for columns and 1-10 for rows.

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
                text=chr(65 + c),
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

        # Draw cells as filled rectangles tagged for later updates.
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
        """Change the fill color of a specific grid cell rectangle.

        Uses itemconfigure on the cell's tag — does not affect any marker
        items drawn on top of the cell.

        Args:
            canvas: The Canvas containing the cell.
            row: Row index (0-9).
            col: Column index (0-9).
            color: Hex color string to fill with.
        """
        canvas.itemconfigure(f"cell_{row}_{col}", fill=color)

    def _cell_from_pixel(self, x: int, y: int) -> tuple[int, int] | None:
        """Convert pixel coordinates to grid (row, col), or None if out of bounds.

        Args:
            x: Pixel x-coordinate from a Canvas event.
            y: Pixel y-coordinate from a Canvas event.

        Returns:
            A (row, col) tuple if inside the grid, else None.
        """
        col = (x - LABEL_PAD) // CELL_SIZE
        row = (y - LABEL_PAD) // CELL_SIZE
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            return row, col
        return None

    def _draw_marker(
        self, canvas: tk.Canvas, row: int, col: int, marker_type: str
    ) -> None:
        """Draw a visual hit/miss marker on top of a grid cell.

        Markers are separate Canvas items drawn over the cell rectangle.
        They persist independently of cell color changes (itemconfigure only
        affects the rectangle, not these overlay items). Each cell holds at
        most one marker at a time — calling this replaces any prior marker.

        Marker styles:
            "hit":  Bold red X (two crossing lines).
            "sunk": Bold orange-red X (brighter than hit, emphasises sinking).
            "miss": Steel-blue circle (O shape).

        Args:
            canvas: The Canvas to draw on.
            row: Cell row (0-9).
            col: Cell column (0-9).
            marker_type: "hit", "sunk", or "miss".
        """
        tag = f"mrk_{row}_{col}"
        canvas.delete(tag)  # Remove any existing marker first.

        pad = 9
        x1 = LABEL_PAD + col * CELL_SIZE + pad
        y1 = LABEL_PAD + row * CELL_SIZE + pad
        x2 = LABEL_PAD + col * CELL_SIZE + CELL_SIZE - pad
        y2 = LABEL_PAD + row * CELL_SIZE + CELL_SIZE - pad

        if marker_type in ("hit", "sunk"):
            color = (
                COLORS["hit_marker"] if marker_type == "hit" else COLORS["sunk_marker"]
            )
            # Draw an X using two diagonal lines.
            canvas.create_line(
                x1, y1, x2, y2, fill=color, width=3, capstyle=tk.ROUND, tags=(tag,)
            )
            canvas.create_line(
                x2, y1, x1, y2, fill=color, width=3, capstyle=tk.ROUND, tags=(tag,)
            )
        elif marker_type == "miss":
            # Draw an O (circle) centered in the cell.
            cx = LABEL_PAD + col * CELL_SIZE + CELL_SIZE // 2
            cy = LABEL_PAD + row * CELL_SIZE + CELL_SIZE // 2
            r = (CELL_SIZE - 2 * pad) // 2
            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=COLORS["miss_marker"],
                width=2,
                fill="",
                tags=(tag,),
            )

    # =====================================================================
    # Ship Placement
    # =====================================================================

    def _enter_placement_phase(self) -> None:
        """Transition the GUI into ship placement mode.

        Resets placement state, enables the rotate button, updates the
        ship roster to highlight the first ship, and prompts the player.
        """
        self.phase = "placement"
        self.current_ship_index = 0
        self.is_horizontal = True
        self.placed_ships = []
        self.own_ship_cells = set()
        self.rotate_btn.configure(state=tk.NORMAL)
        self._update_placement_labels()
        self._update_ship_roster()
        self._set_status_style("wait")

    def _update_placement_labels(self) -> None:
        """Update the ship label and status bar for the current ship."""
        if self.current_ship_index < len(self.ships_to_place):
            name = self.ships_to_place[self.current_ship_index]
            size = SHIP_DEFINITIONS[name]
            self.ship_label.configure(text=f"Placing: {name} ({size} cells)")
            self.status_var.set(f"Place your {name} ({size} cells)  |  R = rotate")
        else:
            self.ship_label.configure(text="")
            self.status_var.set("Waiting for opponent to place ships...")

    def _toggle_rotation(self) -> None:
        """Toggle ship orientation between horizontal and vertical."""
        if self.phase != "placement":
            return
        self.is_horizontal = not self.is_horizontal
        direction = "Horizontal" if self.is_horizontal else "Vertical"
        self.rotate_btn.configure(text=f"  Rotate: {direction}  ")

    def _get_ship_cells(
        self, row: int, col: int, size: int, horizontal: bool
    ) -> list[tuple[int, int]] | None:
        """Compute cells a ship would occupy, or None if any cell is out of bounds.

        Args:
            row: Starting row.
            col: Starting column.
            size: Ship length.
            horizontal: True for rightward placement, False for downward.

        Returns:
            List of (row, col) tuples, or None if any cell is out of bounds.
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
        """Check whether all given cells are free (no overlap with placed ships).

        Args:
            cells: The (row, col) positions to check.

        Returns:
            True if none of the cells overlap with existing ship cells.
        """
        return not any(cell in self.own_ship_cells for cell in cells)

    def _on_own_board_hover(self, event: tk.Event) -> None:
        """Show a placement preview of the current ship on the own board.

        Highlights the cells the ship would occupy in blue (valid) or
        red (invalid/out of bounds).

        Args:
            event: The Tkinter Motion event with pixel coordinates.
        """
        if self.phase != "placement":
            return
        if self.current_ship_index >= len(self.ships_to_place):
            return

        self._redraw_own_board()

        cell = self._cell_from_pixel(event.x, event.y)
        if cell is None:
            return

        row, col = cell
        name = self.ships_to_place[self.current_ship_index]
        size = SHIP_DEFINITIONS[name]
        cells = self._get_ship_cells(row, col, size, self.is_horizontal)

        if cells is None:
            self._set_cell_color(self.own_canvas, row, col, COLORS["hover_invalid"])
            return

        color = (
            COLORS["hover_valid"] if self._is_valid_placement(cells) else COLORS["hover_invalid"]
        )
        for r, c in cells:
            self._set_cell_color(self.own_canvas, r, c, color)

    def _on_own_board_leave(self, _event: tk.Event) -> None:
        """Clear the hover preview when the mouse leaves the own board."""
        if self.phase == "placement":
            self._redraw_own_board()

    def _on_own_board_click(self, event: tk.Event) -> None:
        """Handle a left-click on the own board to place the current ship.

        Validates placement locally, commits cells, advances to the next
        ship, and sends PLACE_SHIPS to the server when all 5 are placed.

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
        self._update_ship_roster()

        # If all ships are placed, send to server.
        if self.current_ship_index >= len(self.ships_to_place):
            self.rotate_btn.configure(state=tk.DISABLED)
            self.send_callback({"type": "PLACE_SHIPS", "ships": self.placed_ships})
            self.log("All ships placed! Sending to server...")

    def _redraw_own_board(self) -> None:
        """Redraw the own board cell colors from the current tracking sets.

        Priority order: sunk > hit > miss > ship > empty.
        Marker items (X/O symbols) are separate Canvas items and persist
        independently — this method only updates cell rectangle fills.
        """
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if (r, c) in self.own_sunk_cells:
                    color = COLORS["sunk"]
                elif (r, c) in self.own_hit_cells:
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

        Disables placement controls, marks all roster ships as placed,
        and enables the attack board for firing.

        Args:
            first_turn: The player_id who fires first (1 or 2).
        """
        self.phase = "playing"
        self.rotate_btn.configure(state=tk.DISABLED)
        self.ship_label.configure(text="")
        self.fired_cells = set()
        self.my_turn = first_turn == self.player_id

        # Mark all ships as placed in the roster.
        self.current_ship_index = len(self.ships_to_place)
        self._update_ship_roster()

        self._update_turn_status()

    def _update_turn_status(self) -> None:
        """Update the status bar text and background color for the current turn."""
        if self.my_turn:
            self.status_var.set("Your turn — click the ATTACK BOARD to fire.")
            self._set_status_style("turn")
        else:
            self.status_var.set("Opponent's turn... waiting.")
            self._set_status_style("wait")

    def _on_attack_board_click(self, event: tk.Event) -> None:
        """Handle a left-click on the attack board to fire a shot.

        Validates that it is the player's turn and the cell has not been
        fired at before, then sends the FIRE message to the server.

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

        if (row, col) in self.fired_cells:
            self.status_var.set("Already targeted! Choose another cell.")
            return

        # Record the fire and disable further clicks until RESULT arrives.
        self.fired_cells.add((row, col))
        self.my_turn = False
        self.status_var.set(f"Fired at {chr(65 + col)}{row + 1}... waiting for result.")
        self._set_status_style("wait")

        self.send_callback({"type": "FIRE", "row": row, "col": col})

    def _on_attack_board_hover(self, event: tk.Event) -> None:
        """Highlight the hovered cell on the attack board during the player's turn.

        Shows a blue highlight on untargeted cells; no change on already-fired cells.

        Args:
            event: The Tkinter Motion event.
        """
        if self.phase != "playing" or not self.my_turn:
            return

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
        """Redraw the attack board cell colors from current tracking sets.

        Priority order: sunk > hit > miss > empty.
        Marker items (X/O symbols) persist independently of this redraw.
        """
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

        Always called on the Tkinter main thread (via root.after()).

        Supported message types:
            WAIT, WELCOME, GAME_START, SHIPS_CONFIRMED, SHIPS_REJECTED,
            ALL_READY, YOUR_TURN, OPPONENT_TURN, RESULT, GAME_OVER,
            OPPONENT_DISCONNECTED, ERROR.

        Args:
            message: A deserialized protocol message dict from the server.
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
        self.root.title(f"BroadSide — Player {self.player_id}")
        self.log(f"Connected! You are Player {self.player_id}.")
        self.status_var.set(f"Player {self.player_id} — Waiting for match...")

    def _handle_game_start(self, _message: dict) -> None:
        """Handle GAME_START: opponent found, begin placement."""
        self.log("Opponent found! Place your ships.")
        self._enter_placement_phase()

    def _handle_ships_confirmed(self, _message: dict) -> None:
        """Handle SHIPS_CONFIRMED: server accepted our placement."""
        self.log("Ships confirmed by server!")
        self.status_var.set("Ships placed — Waiting for opponent...")

    def _handle_ships_rejected(self, message: dict) -> None:
        """Handle SHIPS_REJECTED: server rejected placement.

        Resets placement state so the player can try again.
        """
        reason = message.get("message", "Unknown reason")
        self.log(f"Ships rejected: {reason}")
        self.status_var.set("Placement rejected! Try again.")

        self.current_ship_index = 0
        self.placed_ships = []
        self.own_ship_cells = set()
        self.rotate_btn.configure(state=tk.NORMAL)
        self._redraw_own_board()
        self._update_placement_labels()
        self._update_ship_roster()

    def _handle_all_ready(self, message: dict) -> None:
        """Handle ALL_READY: both players placed ships, game begins."""
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

        Determines whether this was our shot (update attack board) or the
        opponent's shot (update own board).

        Args:
            message: RESULT dict with row, col, result, sunk_ship, player fields.
        """
        row = message["row"]
        col = message["col"]
        result = message["result"]
        sunk_ship = message.get("sunk_ship")
        shooter = message.get("player")

        if shooter == self.player_id:
            self._apply_attack_result(row, col, result, sunk_ship)
        else:
            self._apply_own_board_result(row, col, result, sunk_ship)

    def _apply_attack_result(
        self, row: int, col: int, result: str, sunk_ship: str | None
    ) -> None:
        """Render a shot result on the attack board (our shot at opponent).

        Sets the cell background color, draws an X or O marker on the cell,
        and appends a line to the game log.

        Args:
            row: Target row (0-9).
            col: Target column (0-9).
            result: "hit", "miss", or "sunk".
            sunk_ship: Name of the sunk ship, or None.
        """
        coord = f"{chr(65 + col)}{row + 1}"
        if result == "miss":
            self.attack_miss_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["miss"])
            self._draw_marker(self.attack_canvas, row, col, "miss")
            self.log(f"  {coord}  Miss.")
        elif result == "hit":
            self.attack_hit_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["hit"])
            self._draw_marker(self.attack_canvas, row, col, "hit")
            self.log(f"  {coord}  Hit!")
        elif result == "sunk":
            # Use attack_sunk_cells (not hit_cells) so _redraw_attack_board
            # renders the darker sunk color correctly on hover redraws.
            self.attack_sunk_cells.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["sunk"])
            self._draw_marker(self.attack_canvas, row, col, "sunk")
            self.log(f"  {coord}  Sunk {sunk_ship}!")

    def _apply_own_board_result(
        self, row: int, col: int, result: str, sunk_ship: str | None
    ) -> None:
        """Render an opponent's shot on our own board.

        Args:
            row: Target row on our board (0-9).
            col: Target column on our board (0-9).
            result: "hit", "miss", or "sunk".
            sunk_ship: Name of the sunk ship, or None.
        """
        coord = f"{chr(65 + col)}{row + 1}"
        if result == "miss":
            self.own_miss_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["miss"])
            self._draw_marker(self.own_canvas, row, col, "miss")
            self.log(f"  {coord}  Opponent missed.")
        elif result == "hit":
            self.own_hit_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["hit"])
            self._draw_marker(self.own_canvas, row, col, "hit")
            self.log(f"  {coord}  Opponent hit your ship!")
        elif result == "sunk":
            # Use own_sunk_cells so _redraw_own_board renders sunk color
            # correctly when the board is redrawn (e.g. after placement reset).
            self.own_sunk_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["sunk"])
            self._draw_marker(self.own_canvas, row, col, "sunk")
            self.log(f"  {coord}  Opponent sunk your {sunk_ship}!")

    def _handle_game_over(self, message: dict) -> None:
        """Handle GAME_OVER: display a dramatic victory or defeat overlay.

        Draws a stippled semi-transparent overlay on both canvases with
        large result text and a reason subtitle.

        Args:
            message: GAME_OVER dict with winner and reason fields.
        """
        self.phase = "gameover"
        self.my_turn = False
        winner = message.get("winner")
        reason = message.get("reason", "")

        if winner == self.player_id:
            headline = "VICTORY!"
            subtitle = "All enemy ships sunk."
            overlay_color = "#0a2e0a"   # Dark green
            text_color = "#a5d6a7"      # Light green
            self.log(f"You win! {reason}")
        else:
            headline = "DEFEAT"
            subtitle = "Your fleet was destroyed."
            overlay_color = "#2e0a0a"   # Dark red
            text_color = "#ef9a9a"      # Light red
            self.log(f"You lose. {reason}")

        self.status_var.set(headline)
        self._set_status_style("over")

        canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        cx = canvas_w // 2
        cy = canvas_h // 2

        for canvas in (self.own_canvas, self.attack_canvas):
            # Full-canvas dimming overlay.
            canvas.create_rectangle(
                0, 0, canvas_w, canvas_h,
                fill=overlay_color,
                stipple="gray50",
                tags=("overlay",),
            )
            # Solid backing box for the text so it's legible.
            box_w, box_h = 220, 80
            canvas.create_rectangle(
                cx - box_w // 2, cy - box_h // 2,
                cx + box_w // 2, cy + box_h // 2,
                fill=overlay_color,
                outline=text_color,
                width=2,
                tags=("overlay",),
            )
            # Main headline.
            canvas.create_text(
                cx, cy - 12,
                text=headline,
                fill=text_color,
                font=("Helvetica", 26, "bold"),
                tags=("overlay",),
            )
            # Subtitle reason.
            canvas.create_text(
                cx, cy + 22,
                text=subtitle,
                fill=text_color,
                font=("Helvetica", 10),
                tags=("overlay",),
            )

    def _handle_opponent_disconnected(self, message: dict) -> None:
        """Handle OPPONENT_DISCONNECTED: show a notification."""
        msg = message.get("message", "Your opponent has disconnected.")
        self.phase = "gameover"
        self.my_turn = False
        self.status_var.set("Opponent disconnected.")
        self._set_status_style("over")
        self.log(msg)

    def _handle_error(self, message: dict) -> None:
        """Handle ERROR: show the server error and re-enable turn if in gameplay."""
        error_msg = message.get("message", "Unknown error from server.")
        self.log(f"Server error: {error_msg}")
        if self.phase == "playing":
            self.my_turn = True
            self._update_turn_status()

    # =====================================================================
    # Game Log
    # =====================================================================

    def log(self, text: str) -> None:
        """Append a line to the scrollable game log panel.

        Temporarily enables the read-only Text widget, inserts the new
        line, auto-scrolls to the bottom, then re-disables editing.

        Args:
            text: The message to display.
        """
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"> {text}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # =====================================================================
    # Main Loop
    # =====================================================================

    def run(self) -> None:
        """Start the Tkinter main event loop (blocks until window is closed)."""
        self.root.mainloop()
