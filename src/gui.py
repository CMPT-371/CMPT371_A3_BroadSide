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
    - Tkinter documentation and Python standard library references were used.
"""

from __future__ import annotations

import logging
import math
import tkinter as tk
from collections.abc import Callable

from src.game_logic import BOARD_SIZE, SHIP_DEFINITIONS

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

# Each grid cell is a square of this many pixels.
CELL_SIZE: int = 44

# Padding between the grid edge and the cell area (for row/col labels).
LABEL_PAD: int = 28

# Color palette for all UI elements.
COLORS: dict[str, str] = {
    # -- Cell state backgrounds -------------------------------------------
    "empty": "#0c1e30",  # Deep navy — untouched water
    "ship": "#3d5a6e",  # Steel blue-gray — own ship segment
    "hit": "#8b0000",  # Dark crimson — hit cell background
    "miss": "#101e2d",  # Very dark slate — missed cell background
    "sunk": "#4a0000",  # Near-black red — sunk ship cell
    "hover_valid": "#1a5c9e",  # Deep blue — valid placement/target hover
    "hover_invalid": "#7f0000",  # Deep red — invalid placement hover
    # -- Grid -------------------------------------------------------------
    "grid_line": "#091523",  # Very dark — cell borders
    # -- Water decoration -------------------------------------------------
    "wave_bright": "#1e4565",  # Visible ripple highlight (much more contrast)
    "wave_dim": "#162d4a",  # Secondary ripple
    # -- Window -----------------------------------------------------------
    "background": "#050c14",  # Deep space navy — window background
    "panel_bg": "#080f1a",  # Slightly lighter — panel areas
    # -- Typography -------------------------------------------------------
    "text": "#8dafc0",  # Cool off-white — general labels
    "text_bright": "#d4e8f4",  # Bright white — important text
    "text_dim": "#3a5268",  # Dimmed — secondary labels
    "title": "#ffca28",  # Amber gold — main title
    "title_own": "#4fc3f7",  # Cyan — YOUR FLEET heading
    "title_attack": "#ef5350",  # Coral red — ATTACK BOARD heading
    # -- Game log ---------------------------------------------------------
    "log_bg": "#030a11",  # Very dark — log background
    "log_hit": "#ff6b6b",  # Bright red — hit event text
    "log_miss": "#5b9dc0",  # Steel blue — miss event text
    "log_sunk": "#ff9e40",  # Orange — sunk event text
    "log_system": "#6abf6a",  # Green — system/status messages
    # -- Status bar backgrounds -------------------------------------------
    "status_turn_bg": "#0a280a",  # Dark green — your turn
    "status_wait_bg": "#080f1a",  # Dark navy — waiting
    "status_over_bg": "#280a0a",  # Dark red — game over
    # -- Cell markers (drawn on top of cell rectangles) -------------------
    "hit_marker": "#ff4444",  # Bright red — hit explosion fill
    "hit_glow": "#ff8c00",  # Orange — hit glow outer
    "sunk_marker": "#ff6600",  # Orange — sunk explosion fill
    "sunk_glow": "#ffcc00",  # Yellow — sunk outer glow
    "miss_marker": "#3d84a8",  # Steel blue — miss ring outline
    "miss_ring": "#5ba8d0",  # Lighter blue — outer splash ring
    "miss_dot": "#6ab0d0",  # Light blue — center dot
    # -- Ship silhouette --------------------------------------------------
    "ship_highlight": "#6a8fa0",  # Light stripe on top of ship cells
    "ship_deck": "#2d4555",  # Darker deck stripe
    "ship_outline": "#5a8098",  # Ship cell border
    # -- Ship placement roster --------------------------------------------
    "roster_placed_bg": "#112211",  # Dark green — ship placed
    "roster_placed_fg": "#6abf6a",  # Light green text
    "roster_current_bg": "#0a1e38",  # Dark blue — current ship to place
    "roster_current_fg": "#7ecef0",  # Light blue text
    "roster_pending_bg": "#080e18",  # Dark — pending ship
    "roster_pending_fg": "#3a5268",  # Dim text
    # -- Buttons ----------------------------------------------------------
    "btn_bg": "#0a1828",
    "btn_fg": "#8dafc0",
    "btn_active_bg": "#122040",
    # -- Separator line ---------------------------------------------------
    "separator": "#1a3852",
    # -- Canvas glow border -----------------------------------------------
    "canvas_glow": "#1e4a6e",
    # -- Sonar sweep ------------------------------------------------------
    "sonar_ring": "#1e6080",
    "sonar_center": "#0d3040",
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
        - Firing interface with click-to-fire, explosion/splash markers.
        - Dynamic status bar that changes color based on game state.
        - Sonar sweep animation on the attack board while waiting.
        - Ship silhouette overlays on the own board.
        - Scrollable, color-coded game log.

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

        # -- Sonar animation state ----------------------------------------
        # _sonar_active: whether the sweep animation is running.
        # _sonar_r:      current radius of the expanding sonar ring.
        self._sonar_active: bool = False
        self._sonar_r: int = 0

        # -- Wave animation state -----------------------------------------
        # _wave_phase: current phase offset for animating water ripples.
        self._wave_phase: float = 0.0

        # -- Attack hit tracking for sunk-ship resolution -----------------
        # Keeps hit cells that have not yet been assigned to a confirmed sunk
        # ship.  When a "sunk" result arrives we search this set to find all
        # cells belonging to that ship so every cell turns dark-red together.
        self._unassigned_attack_hits: set[tuple[int, int]] = set()

        # -- Sunk flash animation state -----------------------------------
        # Brief orange flash when a ship is sunk.
        self._sunk_flash_step: int = 0
        self._sunk_flash_cells: list[tuple[int, int]] = []
        self._sunk_flash_canvas: tk.Canvas | None = None

        # -- Build the UI -------------------------------------------------
        self._build_ui()

    # =====================================================================
    # UI Construction
    # =====================================================================

    def _build_ui(self) -> None:
        """Construct the complete Tkinter widget hierarchy.

        Layout (top to bottom):
            1. Title bar with anchor icons, subtitle, and separator
            2. Board area (two Canvas grids side by side, with glow borders)
            3. Fleet deployment roster (ship placement checklist)
            4. Control panel (ship name label + rotate button)
            5. Status bar (color changes with game state)
            6. Game log (scrollable, color-coded text area)
        """
        self.root = tk.Tk()
        self.root.title("BroadSide — Battleship")
        self.root.configure(bg=COLORS["background"])
        # Allow resizing so the OS maximize/zoom button works normally.
        # A minsize prevents the window from being shrunk below playable dimensions.
        self.root.resizable(True, True)
        self.root.minsize(940, 680)

        # -- Title area ---------------------------------------------------
        title_frame = tk.Frame(self.root, bg=COLORS["background"])
        title_frame.pack(pady=(14, 0))

        # Main title with anchor emojis for a nautical feel.
        tk.Label(
            title_frame,
            text="⚓  BroadSide  ⚓",
            font=("Helvetica", 30, "bold"),
            fg=COLORS["title"],
            bg=COLORS["background"],
        ).pack()

        tk.Label(
            title_frame,
            text="〜〜〜  N A V A L   W A R F A R E  〜〜〜",
            font=("Helvetica", 8),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
        ).pack(pady=(2, 6))

        # Thin separator line under the title.
        tk.Frame(self.root, bg=COLORS["separator"], height=1).pack(
            fill=tk.X, padx=30, pady=(0, 10)
        )

        # -- Board area (two grids side by side) --------------------------
        board_frame = tk.Frame(self.root, bg=COLORS["background"])
        board_frame.pack(padx=20, pady=0)

        # Canvas dimensions (grid cells + label padding).
        canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD

        # Left: Own board ("YOUR FLEET") in cyan.
        own_frame = tk.Frame(board_frame, bg=COLORS["background"])
        own_frame.pack(side=tk.LEFT, padx=(0, 22))

        tk.Label(
            own_frame,
            text="⛵  YOUR FLEET",
            font=("Helvetica", 11, "bold"),
            fg=COLORS["title_own"],
            bg=COLORS["background"],
        ).pack(pady=(0, 5))

        # Wrap canvas in a Frame for a glowing border effect.
        own_canvas_border = tk.Frame(
            own_frame, bg=COLORS["canvas_glow"], padx=2, pady=2
        )
        own_canvas_border.pack()

        self.own_canvas = tk.Canvas(
            own_canvas_border,
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
            text="🎯  ATTACK BOARD",
            font=("Helvetica", 11, "bold"),
            fg=COLORS["title_attack"],
            bg=COLORS["background"],
        ).pack(pady=(0, 5))

        # Wrap canvas in a Frame for a glowing border effect.
        attack_canvas_border = tk.Frame(
            attack_frame, bg=COLORS["canvas_glow"], padx=2, pady=2
        )
        attack_canvas_border.pack()

        self.attack_canvas = tk.Canvas(
            attack_canvas_border,
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
            text="  ↻  Rotate: Horizontal  ",
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
        self.status_frame = tk.Frame(self.root, bg=COLORS["status_wait_bg"], pady=8)
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

        # -- Game log (scrollable, color-coded text) ----------------------
        log_frame = tk.Frame(self.root, bg=COLORS["background"])
        log_frame.pack(padx=20, pady=(0, 14), fill=tk.X)

        tk.Label(
            log_frame,
            text="📋  COMBAT LOG",
            font=("Helvetica", 8, "bold"),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 3))

        text_frame = tk.Frame(log_frame, bg=COLORS["background"])
        text_frame.pack(fill=tk.X)

        self.log_text = tk.Text(
            text_frame,
            height=5,
            width=74,
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

        # Configure color tags for different log message types.
        self.log_text.tag_configure("hit", foreground=COLORS["log_hit"])
        self.log_text.tag_configure("miss", foreground=COLORS["log_miss"])
        self.log_text.tag_configure("sunk", foreground=COLORS["log_sunk"])
        self.log_text.tag_configure("system", foreground=COLORS["log_system"])
        self.log_text.tag_configure("default", foreground=COLORS["text"])

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
        Each box shows the ship name, a visual size indicator with ship icons,
        and cell count. Colors update as ships are placed.
        """
        self.roster_outer = tk.Frame(self.root, bg=COLORS["background"])
        self.roster_outer.pack(pady=(8, 0))

        tk.Label(
            self.roster_outer,
            text="⚓  FLEET DEPLOYMENT",
            font=("Helvetica", 8, "bold"),
            fg=COLORS["text_dim"],
            bg=COLORS["background"],
        ).pack(pady=(0, 5))

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
                pady=6,
            )
            box.pack(side=tk.LEFT, padx=4)

            # Use a ship-segment visual: solid blocks scaled to ship size.
            blocks = "▬ " * size
            lbl = tk.Label(
                box,
                text=f"{name}\n{blocks}\n{size} cells",
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
            blocks = "▬ " * size
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

        Each cell is tagged with ``cell_R_C`` for later color changes.
        Water ripple lines are drawn over each empty cell for a nautical look.
        Labels use A-J for columns and 1-10 for rows.

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

        # Draw water ripple overlays on every empty cell at initial phase 0.
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                self._draw_cell_wave(canvas, r, c, 0.0)

    def _draw_cell_wave(
        self, canvas: tk.Canvas, row: int, col: int, phase: float = 0.0
    ) -> None:
        """Draw two sine-wave ripple lines on an empty cell.

        Uses 12 evenly-spaced points to trace a proper sinusoid across each
        cell. A per-cell phase offset means neighbouring cells are shifted so
        the overall grid looks like a rolling ocean rather than a flat grid
        of identical lines.

        Args:
            canvas: The Canvas to draw on.
            row: Cell row (0-9).
            col: Cell column (0-9).
            phase: Animation phase in radians (incremented each frame).
        """
        tag = f"wv_{row}_{col}"
        canvas.delete(tag)

        x1 = LABEL_PAD + col * CELL_SIZE
        y1 = LABEL_PAD + row * CELL_SIZE

        # Each cell has its own spatial phase shift so waves appear to travel
        # diagonally across the board rather than all cresting at the same time.
        cell_offset = row * 1.1 + col * 0.7

        n = 12  # Number of sample points per wave line
        amp = 2.2  # Sine amplitude in pixels

        for i, (frac, color) in enumerate(
            ((0.30, COLORS["wave_bright"]), (0.65, COLORS["wave_dim"]))
        ):
            wy = y1 + int(CELL_SIZE * frac)
            # Second line is phase-shifted by π so the two waves don't overlap.
            line_phase = phase + cell_offset + i * math.pi

            pts: list[float] = []
            for j in range(n + 1):
                px = x1 + 1 + (CELL_SIZE - 2) * j / n
                py = wy + amp * math.sin(2 * math.pi * j / n + line_phase)
                pts.extend([px, py])

            canvas.create_line(
                *pts, fill=color, width=1, smooth=False, tags=(tag, "wave")
            )

    def _set_cell_color(
        self, canvas: tk.Canvas, row: int, col: int, color: str
    ) -> None:
        """Change the fill color of a specific grid cell rectangle.

        Also manages overlays:
            - Deletes wave overlay when a cell transitions away from empty.
            - Deletes ship overlay when a cell is hit, missed, or sunk,
              so the damage color shows through beneath the hit marker.

        Args:
            canvas: The Canvas containing the cell.
            row: Row index (0-9).
            col: Column index (0-9).
            color: Hex color string to fill with.
        """
        canvas.itemconfigure(f"cell_{row}_{col}", fill=color)

        # Remove water ripple once the cell is no longer empty.
        if color != COLORS["empty"]:
            canvas.delete(f"wv_{row}_{col}")

        # Remove ship overlay when the cell is damaged (hit/sunk/miss),
        # so the background damage color is fully visible.
        if color in (COLORS["hit"], COLORS["sunk"], COLORS["miss"]):
            canvas.delete(f"shp_{row}_{col}")

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

        Markers are separate Canvas items drawn above the cell rectangle and
        any ship overlay. Calling this replaces any prior marker on the cell.

        Marker styles:
            "hit":  8-point explosion starburst in orange/red with white center.
            "sunk": Larger 8-point explosion in yellow/orange with bright center.
            "miss": Concentric splash circles in steel blue with a dot center.

        Args:
            canvas: The Canvas to draw on.
            row: Cell row (0-9).
            col: Cell column (0-9).
            marker_type: "hit", "sunk", or "miss".
        """
        tag = f"mrk_{row}_{col}"
        canvas.delete(tag)  # Remove any existing marker first.

        cx = LABEL_PAD + col * CELL_SIZE + CELL_SIZE // 2
        cy = LABEL_PAD + row * CELL_SIZE + CELL_SIZE // 2

        if marker_type in ("hit", "sunk"):
            # --- Explosion starburst ---
            # Outer glow color and inner fill color differ by severity.
            glow_color = (
                COLORS["hit_glow"] if marker_type == "hit" else COLORS["sunk_glow"]
            )
            fill_color = (
                COLORS["hit_marker"] if marker_type == "hit" else COLORS["sunk_marker"]
            )

            # Outer starburst: 8 points alternating between outer and inner radii.
            outer_r = CELL_SIZE // 2 - 5
            inner_r = outer_r // 2

            glow_pts: list[float] = []
            fill_pts: list[float] = []
            for i in range(8):
                angle = math.pi * i / 4 - math.pi / 8  # Rotate 22.5° for visual balance
                r_outer = outer_r if i % 2 == 0 else inner_r
                r_inner = int(outer_r * 0.6) if i % 2 == 0 else int(inner_r * 0.6)
                glow_pts.extend(
                    [cx + r_outer * math.cos(angle), cy + r_outer * math.sin(angle)]
                )
                fill_pts.extend(
                    [cx + r_inner * math.cos(angle), cy + r_inner * math.sin(angle)]
                )

            # Draw outer glow polygon first (behind inner).
            canvas.create_polygon(glow_pts, fill=glow_color, outline="", tags=(tag,))
            # Draw inner brighter polygon on top.
            canvas.create_polygon(fill_pts, fill=fill_color, outline="", tags=(tag,))
            # Bright center dot.
            center_r = 4 if marker_type == "hit" else 5
            canvas.create_oval(
                cx - center_r,
                cy - center_r,
                cx + center_r,
                cy + center_r,
                fill="#ffffff",
                outline="",
                tags=(tag,),
            )

        elif marker_type == "miss":
            # --- Splash circles ---
            r = CELL_SIZE // 2 - 6

            # Outermost faint ring (splash boundary).
            canvas.create_oval(
                cx - r - 5,
                cy - r - 5,
                cx + r + 5,
                cy + r + 5,
                outline=COLORS["miss_ring"],
                width=1,
                fill="",
                tags=(tag,),
            )
            # Main ring.
            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=COLORS["miss_marker"],
                width=2,
                fill="#0a1824",
                tags=(tag,),
            )
            # Small inner ring.
            canvas.create_oval(
                cx - r + 5,
                cy - r + 5,
                cx + r - 5,
                cy + r - 5,
                outline=COLORS["miss_dot"],
                width=1,
                fill="",
                tags=(tag,),
            )
            # Center droplet dot.
            canvas.create_oval(
                cx - 3,
                cy - 3,
                cx + 3,
                cy + 3,
                fill=COLORS["miss_dot"],
                outline="",
                tags=(tag,),
            )

    def _draw_ship_overlay(self, ship_dict: dict) -> None:
        """Draw a ship silhouette on the own board for a placed ship.

        Each cell of the ship receives its own overlay item (tagged shp_{r}_{c})
        so individual cells can be removed when they are damaged. Adjacent
        cells share seamless edges to form a continuous hull.

        The overlay sits between the cell rectangle and hit markers in z-order,
        and is automatically removed per-cell when _set_cell_color marks a cell
        as hit, sunk, or missed.

        Args:
            ship_dict: A placement dict with keys name, row, col, horizontal.
        """
        name = ship_dict["name"]
        row = ship_dict["row"]
        col = ship_dict["col"]
        horizontal = ship_dict["horizontal"]
        size = SHIP_DEFINITIONS[name]

        for i in range(size):
            r = row if horizontal else row + i
            c = col + i if horizontal else col

            is_bow = i == 0
            is_stern = i == size - 1

            x1 = LABEL_PAD + c * CELL_SIZE
            y1 = LABEL_PAD + r * CELL_SIZE
            x2 = x1 + CELL_SIZE
            y2 = y1 + CELL_SIZE

            # --- Padding: blunt at connections, pointed at bow/stern ---
            if horizontal:
                # Bow (leftmost cell): narrow left edge for a "prow" look.
                # Stern (rightmost cell): narrow right edge.
                pl = 4 if is_bow else 0
                pr = 4 if is_stern else 0
                pt = 5
                pb = 5
            else:
                pt = 4 if is_bow else 0
                pb = 4 if is_stern else 0
                pl = 5
                pr = 5

            tag = f"shp_{r}_{c}"
            self.own_canvas.delete(tag)

            # Draw main hull body rectangle.
            self.own_canvas.create_rectangle(
                x1 + pl,
                y1 + pt,
                x2 - pr,
                y2 - pb,
                fill=COLORS["ship"],
                outline=COLORS["ship_outline"],
                width=1,
                tags=(tag, "shp_ovl"),
            )

            # Draw a bright highlight stripe along the top/left edge of each cell
            # to simulate a metallic sheen on the hull.
            if horizontal:
                self.own_canvas.create_rectangle(
                    x1 + pl + 1,
                    y1 + pt + 1,
                    x2 - pr - 1,
                    y1 + pt + 4,
                    fill=COLORS["ship_highlight"],
                    outline="",
                    tags=(tag, "shp_ovl"),
                )
            else:
                self.own_canvas.create_rectangle(
                    x1 + pl + 1,
                    y1 + pt + 1,
                    x1 + pl + 4,
                    y2 - pb - 1,
                    fill=COLORS["ship_highlight"],
                    outline="",
                    tags=(tag, "shp_ovl"),
                )

            # Draw a dark deck stripe near the bottom/right edge.
            if horizontal:
                self.own_canvas.create_rectangle(
                    x1 + pl + 1,
                    y2 - pb - 4,
                    x2 - pr - 1,
                    y2 - pb - 1,
                    fill=COLORS["ship_deck"],
                    outline="",
                    tags=(tag, "shp_ovl"),
                )
            else:
                self.own_canvas.create_rectangle(
                    x2 - pr - 4,
                    y1 + pt + 1,
                    x2 - pr - 1,
                    y2 - pb - 1,
                    fill=COLORS["ship_deck"],
                    outline="",
                    tags=(tag, "shp_ovl"),
                )

    # =====================================================================
    # Wave Animation
    # =====================================================================

    def _tick_waves(self) -> None:
        """Animate ocean waves by incrementing the phase and redrawing ripples.

        Runs at ~10 fps (every 100 ms). Only redraws cells that are currently
        showing empty water on each board, so it gracefully handles mid-game
        state where many cells are occupied.
        """
        if self.phase == "gameover":
            return  # Stop animating after game ends.

        self._wave_phase += 0.14  # Phase step per frame — controls wave speed.

        # Redraw water cells on the own board.
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self._is_water_own(r, c):
                    self._draw_cell_wave(self.own_canvas, r, c, self._wave_phase)

        # Redraw water cells on the attack board.
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if self._is_water_attack(r, c):
                    self._draw_cell_wave(self.attack_canvas, r, c, self._wave_phase)

        self.root.after(100, self._tick_waves)

    def _is_water_own(self, row: int, col: int) -> bool:
        """Return True if the own-board cell is currently empty ocean."""
        return (
            (row, col) not in self.own_ship_cells
            and (row, col) not in self.own_hit_cells
            and (row, col) not in self.own_miss_cells
            and (row, col) not in self.own_sunk_cells
        )

    def _is_water_attack(self, row: int, col: int) -> bool:
        """Return True if the attack-board cell is currently empty ocean."""
        return (
            (row, col) not in self.attack_hit_cells
            and (row, col) not in self.attack_miss_cells
            and (row, col) not in self.attack_sunk_cells
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
        self.rotate_btn.configure(text=f"  ↻  Rotate: {direction}  ")

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
            COLORS["hover_valid"]
            if self._is_valid_placement(cells)
            else COLORS["hover_invalid"]
        )
        for r, c in cells:
            self._set_cell_color(self.own_canvas, r, c, color)

    def _on_own_board_leave(self, _event: tk.Event) -> None:
        """Clear the hover preview when the mouse leaves the own board."""
        if self.phase == "placement":
            self._redraw_own_board()

    def _on_own_board_click(self, event: tk.Event) -> None:
        """Handle a left-click on the own board to place the current ship.

        Validates placement locally, commits cells, draws the ship silhouette,
        advances to the next ship, and sends PLACE_SHIPS when all 5 are placed.

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

        ship_dict = {
            "name": name,
            "row": row,
            "col": col,
            "horizontal": self.is_horizontal,
        }
        self.placed_ships.append(ship_dict)

        self.log(
            f"Placed {name} at {chr(65 + col)}{row + 1} "
            f"({'H' if self.is_horizontal else 'V'}).",
            "system",
        )

        # Advance to the next ship.
        self.current_ship_index += 1
        self._redraw_own_board()

        # Draw the ship silhouette overlay for the just-placed ship.
        self._draw_ship_overlay(ship_dict)

        self._update_placement_labels()
        self._update_ship_roster()

        # If all ships are placed, send to server.
        if self.current_ship_index >= len(self.ships_to_place):
            self.rotate_btn.configure(state=tk.DISABLED)
            self.send_callback({"type": "PLACE_SHIPS", "ships": self.placed_ships})
            self.log("All ships placed! Sending to server...", "system")

    def _redraw_own_board(self) -> None:
        """Redraw the own board cell colors from the current tracking sets.

        Priority order: sunk > hit > miss > ship > empty.
        Marker items (X/O symbols) and ship overlay items are separate Canvas
        items and persist independently — this method only updates cell fills.
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
        self._unassigned_attack_hits = set()
        self.my_turn = first_turn == self.player_id

        # Mark all ships as placed in the roster.
        self.current_ship_index = len(self.ships_to_place)
        self._update_ship_roster()

        self._update_turn_status()

    def _update_turn_status(self) -> None:
        """Update the status bar text and background color for the current turn."""
        if self.my_turn:
            self.status_var.set("🎯  Your turn — click the ATTACK BOARD to fire.")
            self._set_status_style("turn")
        else:
            self.status_var.set("⏳  Opponent's turn... waiting.")
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
            self.status_var.set("⛔  Not your turn!")
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
        self.status_var.set(
            f"💣  Fired at {chr(65 + col)}{row + 1}... awaiting result."
        )
        self._set_status_style("wait")

        self.send_callback({"type": "FIRE", "row": row, "col": col})
        # Single sonar sweep radiates outward after each shot is fired.
        self._start_sonar()

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
    # Sonar Sweep Animation
    # =====================================================================

    def _start_sonar(self) -> None:
        """Start the sonar sweep animation on the attack board.

        An expanding ring pulses outward from the board centre, simulating
        an active sonar system scanning for the opponent's fleet. Runs
        continuously until _stop_sonar() is called.
        """
        self._sonar_active = True
        self._sonar_r = 0
        self._tick_sonar()

    def _stop_sonar(self) -> None:
        """Stop the sonar animation and clear any ring artifacts."""
        self._sonar_active = False
        self.attack_canvas.delete("sonar")

    def _tick_sonar(self) -> None:
        """Advance the sonar ring by one frame.

        Deletes the previous ring, draws a new one at the current radius,
        and schedules the next frame. When the ring reaches max radius it
        pauses briefly before restarting from the centre.
        """
        if not self._sonar_active:
            return

        self.attack_canvas.delete("sonar")

        # Centre of the 10x10 grid in pixel coordinates.
        cx = LABEL_PAD + BOARD_SIZE * CELL_SIZE // 2
        cy = LABEL_PAD + BOARD_SIZE * CELL_SIZE // 2
        max_r = int(BOARD_SIZE * CELL_SIZE * 0.68)

        r = self._sonar_r
        if r < max_r:
            # Line width tapers as the ring expands (thicker near centre).
            width = max(1, 3 - int(3 * r / max_r))
            self.attack_canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=COLORS["sonar_ring"],
                width=width,
                tags=("sonar",),
            )
            # Small origin dot while the ring is still close to the centre.
            if r < 20:
                self.attack_canvas.create_oval(
                    cx - 3,
                    cy - 3,
                    cx + 3,
                    cy + 3,
                    fill=COLORS["sonar_center"],
                    outline=COLORS["sonar_ring"],
                    width=1,
                    tags=("sonar",),
                )
            self._sonar_r += 14
            self.root.after(35, self._tick_sonar)
        else:
            # Single sweep complete — clean up and stop (no loop restart).
            self._sonar_active = False
            self.attack_canvas.delete("sonar")

    # =====================================================================
    # Sunk Flash Animation
    # =====================================================================

    def _flash_sunk_cells(
        self, canvas: tk.Canvas, cells: list[tuple[int, int]]
    ) -> None:
        """Briefly flash sunk ship cells with an orange highlight.

        Gives a visual "explosion" impression when a ship is completely
        destroyed. Runs for 4 alternating frames (orange / sunk-color).

        Args:
            canvas: The canvas containing the cells to flash.
            cells:  List of (row, col) positions that belong to the sunk ship.
        """
        self._sunk_flash_canvas = canvas
        self._sunk_flash_cells = cells
        self._sunk_flash_step = 0
        self._tick_sunk_flash()

    def _tick_sunk_flash(self) -> None:
        """Advance the sunk flash by one step."""
        step = self._sunk_flash_step
        if step >= 6 or not self._sunk_flash_cells:
            # Ensure cells end on the sunk color.
            for r, c in self._sunk_flash_cells:
                self._sunk_flash_canvas.itemconfigure(  # type: ignore[union-attr]
                    f"cell_{r}_{c}", fill=COLORS["sunk"]
                )
            return

        # Alternate between a vivid orange flash and the regular sunk color.
        flash_color = "#ff6a00" if step % 2 == 0 else COLORS["sunk"]
        for r, c in self._sunk_flash_cells:
            self._sunk_flash_canvas.itemconfigure(  # type: ignore[union-attr]
                f"cell_{r}_{c}", fill=flash_color
            )

        self._sunk_flash_step += 1
        self.root.after(90, self._tick_sunk_flash)

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
        self.status_var.set("⏳  Waiting for an opponent to connect...")
        self.log(message.get("message", "Waiting for opponent..."), "system")

    def _handle_welcome(self, message: dict) -> None:
        """Handle WELCOME: server assigned our player_id."""
        self.player_id = message.get("player_id")
        self.root.title(f"BroadSide — Player {self.player_id}")
        self.log(f"Connected! You are Player {self.player_id}.", "system")
        self.status_var.set(f"Player {self.player_id} — Waiting for match...")

    def _handle_game_start(self, _message: dict) -> None:
        """Handle GAME_START: opponent found, begin placement."""
        self.log("Opponent found! Place your ships.", "system")
        self._enter_placement_phase()

    def _handle_ships_confirmed(self, _message: dict) -> None:
        """Handle SHIPS_CONFIRMED: server accepted our placement."""
        self.log("Ships confirmed by server!", "system")
        self.status_var.set("⚓  Ships placed — Waiting for opponent...")

    def _handle_ships_rejected(self, message: dict) -> None:
        """Handle SHIPS_REJECTED: server rejected placement.

        Resets placement state and redraws the board so the player can retry.
        """
        reason = message.get("message", "Unknown reason")
        self.log(f"Ships rejected: {reason}", "system")
        self.status_var.set("Placement rejected! Try again.")

        # Full board reset: clear cells, wave overlays, and ship overlays.
        self.current_ship_index = 0
        self.placed_ships = []
        self.own_ship_cells = set()
        self.rotate_btn.configure(state=tk.NORMAL)
        self._draw_grid(self.own_canvas)  # Deletes all, redraws waves.
        self._update_placement_labels()
        self._update_ship_roster()

    def _handle_all_ready(self, message: dict) -> None:
        """Handle ALL_READY: both players placed ships, game begins."""
        first_turn = message.get("turn", 1)
        self.log("All ships placed! Game starting!", "system")
        self._enter_playing_phase(first_turn)

    def _handle_your_turn(self) -> None:
        """Handle YOUR_TURN: it is now our turn to fire."""
        self.my_turn = True
        self._stop_sonar()  # Stop sonar sweep — player is now active.
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

    # =====================================================================
    # Sunk-ship cell resolution helpers
    # =====================================================================

    def _ship_cells_from_dict(self, ship_dict: dict) -> list[tuple[int, int]]:
        """Return all (row, col) positions occupied by a ship placement dict."""
        row = ship_dict["row"]
        col = ship_dict["col"]
        size = SHIP_DEFINITIONS[ship_dict["name"]]
        horizontal = ship_dict["horizontal"]
        return [(row, col + i) if horizontal else (row + i, col) for i in range(size)]

    def _connected_segment(
        self, sorted_cells: list[tuple[int, int]], target: int, axis: int
    ) -> list[tuple[int, int]]:
        """Return the contiguous run of cells (sorted by `axis`) that contains `target`.

        Args:
            sorted_cells: Cells sorted by their `axis` coordinate.
            target:       The axis-coordinate value that must be in the run.
            axis:         0 = row axis, 1 = col axis.
        """
        indices = [c[axis] for c in sorted_cells]
        if target not in indices:
            return []
        pos = indices.index(target)
        start = pos
        end = pos
        while start > 0 and indices[start - 1] == indices[start] - 1:
            start -= 1
        while end < len(indices) - 1 and indices[end + 1] == indices[end] + 1:
            end += 1
        return sorted_cells[start : end + 1]

    def _find_attack_sunk_cells(
        self, row: int, col: int, ship_name: str
    ) -> list[tuple[int, int]]:
        """Identify all attack-board cells that belong to the just-sunk ship.

        We know the ship size from SHIP_DEFINITIONS and that the sinking shot
        landed on (row, col).  The remaining cells are in _unassigned_attack_hits.
        We look for a straight horizontal or vertical connected run (including
        the current cell) whose length matches the ship size.

        Args:
            row:       Row of the sinking shot.
            col:       Column of the sinking shot.
            ship_name: Name of the sunk ship (used to look up its size).

        Returns:
            List of (row, col) cells for the entire sunk ship, or just
            [(row, col)] if the group cannot be determined.
        """
        size = SHIP_DEFINITIONS.get(ship_name, 1)
        # Pool = all previous unassigned hits + the current sinking cell.
        pool = self._unassigned_attack_hits | {(row, col)}

        # --- Check horizontal run (same row, varying col) ----------------
        h_cells = sorted([(r, c) for r, c in pool if r == row], key=lambda x: x[1])
        h_run = self._connected_segment(h_cells, col, axis=1)
        if len(h_run) == size:
            return h_run

        # --- Check vertical run (same col, varying row) ------------------
        v_cells = sorted([(r, c) for r, c in pool if c == col], key=lambda x: x[0])
        v_run = self._connected_segment(v_cells, row, axis=0)
        if len(v_run) == size:
            return v_run

        # Fallback: size-1 ship or ambiguous layout — just colour this cell.
        return [(row, col)]

    def _apply_attack_result(
        self, row: int, col: int, result: str, sunk_ship: str | None
    ) -> None:
        """Render a shot result on the attack board (our shot at opponent).

        Sets the cell background, draws an explosion or splash marker, and
        appends a color-coded line to the combat log.

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
            self.log(f"  {coord}  Miss.", "miss")
        elif result == "hit":
            self.attack_hit_cells.add((row, col))
            self._unassigned_attack_hits.add((row, col))
            self._set_cell_color(self.attack_canvas, row, col, COLORS["hit"])
            self._draw_marker(self.attack_canvas, row, col, "hit")
            self.log(f"  {coord}  Hit!", "hit")
        elif result == "sunk":
            # Find ALL cells belonging to this ship (previous hits + this cell).
            sunk_cells = self._find_attack_sunk_cells(row, col, sunk_ship or "")

            for r, c in sunk_cells:
                # Reclassify any previously-hit cells as sunk.
                self.attack_hit_cells.discard((r, c))
                self._unassigned_attack_hits.discard((r, c))
                self.attack_sunk_cells.add((r, c))
                self._set_cell_color(self.attack_canvas, r, c, COLORS["sunk"])
                self._draw_marker(self.attack_canvas, r, c, "sunk")

            self._flash_sunk_cells(self.attack_canvas, sunk_cells)
            self.log(f"  {coord}  Sunk {sunk_ship}! ☠", "sunk")

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
            self.log(f"  {coord}  Opponent missed.", "miss")
        elif result == "hit":
            self.own_hit_cells.add((row, col))
            self._set_cell_color(self.own_canvas, row, col, COLORS["hit"])
            self._draw_marker(self.own_canvas, row, col, "hit")
            self.log(f"  {coord}  Opponent hit your ship!", "hit")
        elif result == "sunk":
            # We know our own ship positions exactly — look up by name.
            sunk_cells: list[tuple[int, int]] = [(row, col)]
            for ship_dict in self.placed_ships:
                if ship_dict["name"] == sunk_ship:
                    sunk_cells = self._ship_cells_from_dict(ship_dict)
                    break

            for r, c in sunk_cells:
                self.own_hit_cells.discard((r, c))
                self.own_sunk_cells.add((r, c))
                self._set_cell_color(self.own_canvas, r, c, COLORS["sunk"])
                self._draw_marker(self.own_canvas, r, c, "sunk")

            self._flash_sunk_cells(self.own_canvas, sunk_cells)
            self.log(f"  {coord}  Opponent sunk your {sunk_ship}! 💥", "sunk")

    def _handle_game_over(self, message: dict) -> None:
        """Handle GAME_OVER: display a dramatic victory or defeat overlay.

        Draws a stippled semi-transparent overlay on both canvases with
        a large result headline and subtitle. Victory shows green; defeat red.

        Args:
            message: GAME_OVER dict with winner and reason fields.
        """
        self.phase = "gameover"
        self.my_turn = False
        self._stop_sonar()

        winner = message.get("winner")
        reason = message.get("reason", "")

        if winner == self.player_id:
            headline = "VICTORY!"
            subtitle = "All enemy ships sunk."
            overlay_color = "#062406"
            text_color = "#a5d6a7"
            border_color = "#66bb6a"
            self.log(f"You win! {reason}", "system")
        else:
            headline = "DEFEAT"
            subtitle = "Your fleet was destroyed."
            overlay_color = "#240606"
            text_color = "#ef9a9a"
            border_color = "#ef5350"
            self.log(f"You lose. {reason}", "system")

        self.status_var.set(headline)
        self._set_status_style("over")

        canvas_w = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        canvas_h = BOARD_SIZE * CELL_SIZE + LABEL_PAD
        cx = canvas_w // 2
        cy = canvas_h // 2

        for canvas in (self.own_canvas, self.attack_canvas):
            # Stippled semi-transparent full-canvas overlay.
            canvas.create_rectangle(
                0,
                0,
                canvas_w,
                canvas_h,
                fill=overlay_color,
                stipple="gray50",
                tags=("overlay",),
            )
            # Outer decorative border box.
            box_w, box_h = 240, 100
            canvas.create_rectangle(
                cx - box_w // 2 - 3,
                cy - box_h // 2 - 3,
                cx + box_w // 2 + 3,
                cy + box_h // 2 + 3,
                fill="",
                outline=border_color,
                width=1,
                tags=("overlay",),
            )
            # Solid backing box for the text.
            canvas.create_rectangle(
                cx - box_w // 2,
                cy - box_h // 2,
                cx + box_w // 2,
                cy + box_h // 2,
                fill=overlay_color,
                outline=border_color,
                width=2,
                tags=("overlay",),
            )
            # Main headline.
            canvas.create_text(
                cx,
                cy - 18,
                text=headline,
                fill=text_color,
                font=("Helvetica", 28, "bold"),
                tags=("overlay",),
            )
            # Decorative divider line.
            canvas.create_line(
                cx - 80,
                cy + 6,
                cx + 80,
                cy + 6,
                fill=border_color,
                width=1,
                tags=("overlay",),
            )
            # Subtitle.
            canvas.create_text(
                cx,
                cy + 26,
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
        self._stop_sonar()
        self.status_var.set("Opponent disconnected.")
        self._set_status_style("over")
        self.log(msg, "system")

    def _handle_error(self, message: dict) -> None:
        """Handle ERROR: show the server error and re-enable turn if in gameplay."""
        error_msg = message.get("message", "Unknown error from server.")
        self.log(f"Server error: {error_msg}", "system")
        if self.phase == "playing":
            self.my_turn = True
            self._update_turn_status()

    # =====================================================================
    # Game Log
    # =====================================================================

    def log(self, text: str, category: str = "default") -> None:
        """Append a color-coded line to the scrollable combat log panel.

        Temporarily enables the read-only Text widget, inserts the new
        line with the appropriate color tag, auto-scrolls to the bottom,
        then re-disables editing.

        Args:
            text:     The message to display.
            category: One of "hit", "miss", "sunk", "system", or "default".
        """
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"> {text}\n", (category,))
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # =====================================================================
    # Main Loop
    # =====================================================================

    def run(self) -> None:
        """Start the Tkinter main event loop (blocks until window is closed)."""
        # Kick off the wave ripple animation once the event loop is running.
        self.root.after(200, self._tick_waves)
        self.root.mainloop()
