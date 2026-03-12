"""
CMPT 371 A3: BroadSide — TCP Game Client

Purpose:
    Connects to the BroadSide server over TCP, manages the network
    communication on a background thread, and bridges between the
    server protocol and the Tkinter GUI.

Architecture:
    The client runs two threads:

        Main Thread
        │   Runs the Tkinter event loop (gui.run()).
        │   All GUI updates happen here — Tkinter is NOT thread-safe.
        │
        └── Network Thread (daemon=True)
            Runs a recv_message() loop, reading server messages.
            Dispatches each message to the GUI via root.after(),
            which schedules the callback on the main thread's event loop.

    User actions (ship placement clicks, fire clicks) call send_message()
    directly from the main thread. Since send_message() is a single
    sendall() call on a blocking socket, this is safe without additional
    locking.

Threading rule:
    The network thread must NEVER call GUI methods directly.
    Always use:  self.gui.root.after(0, self.gui.handle_server_message, msg)

References:
    - Tkinter threading pattern: https://docs.python.org/3/library/tkinter.html
    - Python socket: https://docs.python.org/3/library/socket.html
    - Claude Code was used to assist with structuring the module layout.
"""

from __future__ import annotations

import logging
import socket

# ---------------------------------------------------------------------------
# Client configuration
# ---------------------------------------------------------------------------

HOST: str = "127.0.0.1"
PORT: int = 5050

logger = logging.getLogger("BroadSide-Client")


# ---------------------------------------------------------------------------
# Game client
# ---------------------------------------------------------------------------


class GameClient:
    """Manages the TCP connection and bridges between network and GUI.

    Attributes:
        host: Server IP address.
        port: Server TCP port.
        sock: The connected TCP socket (set after connect()).
        gui: The BattleshipGUI instance (set after start()).
        player_id: Assigned by the server in the WELCOME message.
        running: Flag to control the network thread's recv loop.
    """

    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.gui = None  # Set in start() to avoid circular import at module level
        self.player_id: int | None = None
        self.running: bool = False

    def connect(self) -> None:
        """Establish a TCP connection and send the CONNECT handshake.

        Raises:
            ConnectionRefusedError: If the server is not running.
            OSError: If the connection fails for any other reason.
        """
        raise NotImplementedError("Phase 3: GameClient.connect")

    def send(self, message: dict) -> None:
        """Send a message to the server. Called by the GUI on user actions.

        Args:
            message: A protocol message dict (e.g., FIRE, PLACE_SHIPS).
        """
        raise NotImplementedError("Phase 3: GameClient.send")

    def _network_loop(self) -> None:
        """Background thread: receive messages and dispatch to the GUI.

        Runs continuously until self.running is set to False or the
        connection drops. Each received message is scheduled on the
        Tkinter main thread via root.after().
        """
        raise NotImplementedError("Phase 3: GameClient._network_loop")

    def start(self) -> None:
        """Connect to server, create the GUI, and run the event loop.

        This is the main entry point. It blocks until the GUI window
        is closed.
        """
        raise NotImplementedError("Phase 3: GameClient.start")

    def shutdown(self) -> None:
        """Cleanly shut down the client.

        Stops the network thread and closes the socket.
        """
        raise NotImplementedError("Phase 3: GameClient.shutdown")


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    client = GameClient()
    client.start()
