"""
CMPT 371 A3: BroadSide — Tkinter GUI Module

Purpose:
    Renders the Battleship game interface using Tkinter Canvas widgets.
    Provides two 10x10 grids (own board and attack board), a ship
    placement system with hover preview, a firing interface with
    visual feedback, and a scrollable game log.

Architecture:
    The GUI is a passive view layer — it renders state and emits user
    actions via a callback, but does not own any game logic. The
    send_callback function (provided by GameClient) transmits actions
    to the server, and handle_server_message() processes incoming
    server messages to update the display.

    ┌─────────────────────────────────────────────────────────┐
    │                    BroadSide                            │
    │                                                         │
    │  YOUR FLEET              ATTACK BOARD                   │
    │  ┌──────────────────┐    ┌──────────────────┐           │
    │  │  10x10 Canvas    │    │  10x10 Canvas    │           │
    │  │  (own board)     │    │  (attack board)  │           │
    │  └──────────────────┘    └──────────────────┘           │
    │                                                         │
    │  [Current Ship: Carrier]  [Rotate: Horizontal]          │
    │  Status: Place your Carrier (5 cells)                   │
    │                                                         │
    │  ┌─────────────────────────────────────────┐            │
    │  │ Game Log (scrollable)                   │            │
    │  │ > Connected to server.                  │            │
    │  │ > Match found! You are Player 1.        │            │
    │  └─────────────────────────────────────────┘            │
    └─────────────────────────────────────────────────────────┘

Threading safety:
    All methods in this class MUST be called from the Tkinter main thread.
    The network thread dispatches messages here via root.after().

References:
    - Tkinter Canvas: https://docs.python.org/3/library/tkinter.html#the-canvas-widget
    - Pillow ImageTk: https://pillow.readthedocs.io/en/stable/reference/ImageTk.html
    - Claude Code was used to assist with structuring the GUI layout and
      generating the Canvas rendering logic.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

from src.game_logic import SHIP_DEFINITIONS

# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

# Each grid cell is a square of this many pixels.
CELL_SIZE: int = 40

# Color palette for cell states.
COLORS: dict[str, str] = {
    "empty": "#1a3a5c",  # Dark navy — untouched water
    "ship": "#708090",  # Steel gray — own ship segment
    "hit": "#e74c3c",  # Red — confirmed hit on a ship
    "miss": "#ecf0f1",  # Off-white — shot missed
    "sunk": "#c0392b",  # Dark red — sunk ship cell
    "hover_valid": "#3498db",  # Light blue — valid placement/target hover
    "hover_invalid": "#e74c3c",  # Red — invalid placement hover
    "grid_line": "#2c3e50",  # Dark slate — grid border lines
    "background": "#0d1b2a",  # Deep navy — window background
    "text": "#ecf0f1",  # Off-white — label text
}


# ---------------------------------------------------------------------------
# GUI class
# ---------------------------------------------------------------------------


class BattleshipGUI:
    """Tkinter-based GUI for BroadSide.

    Attributes:
        root: The Tkinter root window.
        send_callback: Function to call when the user performs an action
            (e.g., placing ships, firing a shot). Accepts a dict message.
        player_id: Assigned by the server (1 or 2). Set via handle_server_message.
        phase: Current GUI phase ("connecting", "placement", "playing", "gameover").
    """

    def __init__(self, send_callback: Callable[[dict], None]) -> None:
        """Initialize the GUI window and widgets.

        Args:
            send_callback: A function that accepts a dict and sends it to
                the server (provided by GameClient).
        """
        self.send_callback = send_callback
        self.player_id: int | None = None
        self.phase: str = "connecting"

        # Placement state
        self.current_ship_index: int = 0
        self.is_horizontal: bool = True
        self.ships_to_place: list[str] = list(SHIP_DEFINITIONS.keys())

        # Will be initialized in _build_ui() during Phase 3 implementation.
        self.root: tk.Tk | None = None

        raise NotImplementedError("Phase 3: BattleshipGUI.__init__")

    def handle_server_message(self, message: dict) -> None:
        """Process an incoming message from the server and update the GUI.

        This method is the single entry point for all server → GUI
        communication. It is always called on the Tkinter main thread
        (via root.after()).

        Args:
            message: A deserialized protocol message from the server.
        """
        raise NotImplementedError("Phase 3/4: BattleshipGUI.handle_server_message")

    def log(self, text: str) -> None:
        """Append a line to the scrollable game log panel.

        Args:
            text: The message to display (e.g., "Player 1 hit B5!").
        """
        raise NotImplementedError("Phase 3: BattleshipGUI.log")

    def run(self) -> None:
        """Start the Tkinter main event loop. Blocks until the window is closed."""
        raise NotImplementedError("Phase 3: BattleshipGUI.run")
