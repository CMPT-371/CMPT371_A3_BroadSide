"""
CMPT 371 A3: BroadSide - TCP Game Client

Purpose:
    Connects to the BroadSide server over TCP, manages the network
    communication on a background thread, and bridges between the
    server protocol and the Tkinter GUI.

Architecture:
    The client runs two threads:

        Main Thread
        |   Runs the Tkinter event loop (gui.run()).
        |   All GUI updates happen here - Tkinter is NOT thread-safe.
        |
        +-- Network Thread (daemon=True)
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

import contextlib
import logging
import socket
import sys
import threading

from src.protocol import recv_message, send_message

# ---------------------------------------------------------------------------
# Client configuration
# ---------------------------------------------------------------------------

HOST: str = "127.0.0.1"
PORT: int = 5050

# Configure logging so the client emits structured messages.
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
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
        # Defer GUI import to avoid circular import at module level.
        self.gui = None  # type: ignore[assignment]
        self.player_id: int | None = None
        self.running: bool = False

    def connect(self) -> None:
        """Establish a TCP connection and send the CONNECT handshake.

        Creates a TCP socket, connects to the server, and sends the
        initial ``CONNECT`` message that registers this client for
        matchmaking.

        Raises:
            ConnectionRefusedError: If the server is not running.
            OSError: If the connection fails for any other reason.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        logger.info("Connected to server at %s:%d", self.host, self.port)

        # Send the protocol handshake to enter the matchmaking queue.
        send_message(self.sock, {"type": "CONNECT"})
        logger.info("CONNECT handshake sent.")

    def send(self, message: dict) -> None:
        """Send a message to the server. Called by the GUI on user actions.

        This is called from the Tkinter main thread when the user clicks
        to place ships or fire. Since ``send_message`` uses ``sendall()``,
        which is a single atomic operation, no additional locking is needed.

        Args:
            message: A protocol message dict (e.g., FIRE, PLACE_SHIPS).
        """
        if self.sock is None:
            logger.warning("Cannot send - not connected.")
            return

        try:
            send_message(self.sock, message)
            logger.debug("Sent: %s", message.get("type", "?"))
        except (ConnectionError, BrokenPipeError, OSError) as exc:
            logger.error("Send failed: %s", exc)
            # Notify the GUI about the lost connection.
            if self.gui is not None:
                self.gui.root.after(
                    0,
                    self.gui.handle_server_message,
                    {
                        "type": "OPPONENT_DISCONNECTED",
                        "message": "Connection lost to the server.",
                    },
                )

    def _network_loop(self) -> None:
        """Background thread: receive messages and dispatch to the GUI.

        Runs continuously until ``self.running`` is set to False or the
        connection drops. Each received message is scheduled on the
        Tkinter main thread via ``root.after()`` to maintain thread safety.

        On clean EOF (server closed connection) or error, a synthetic
        OPPONENT_DISCONNECTED message is dispatched to the GUI so the
        user sees a notification rather than a silent freeze.
        """
        while self.running:
            try:
                msg = recv_message(self.sock)
            except (
                ConnectionError,
                BrokenPipeError,
                ConnectionResetError,
                OSError,
                ValueError,
            ) as exc:
                if self.running:
                    logger.error("Network error: %s", exc)
                    self.gui.root.after(
                        0,
                        self.gui.handle_server_message,
                        {
                            "type": "OPPONENT_DISCONNECTED",
                            "message": "Connection lost to the server.",
                        },
                    )
                break

            if msg is None:
                # Server closed the connection (clean EOF).
                if self.running:
                    logger.info("Server closed the connection.")
                    self.gui.root.after(
                        0,
                        self.gui.handle_server_message,
                        {
                            "type": "OPPONENT_DISCONNECTED",
                            "message": "Server closed the connection.",
                        },
                    )
                break

            logger.info("Received: %s", msg.get("type", "?"))

            # Dispatch the message to the GUI on the main thread.
            # root.after(0, ...) queues the callback on the Tkinter event
            # loop, guaranteeing it runs on the main thread.
            self.gui.root.after(0, self.gui.handle_server_message, msg)

        logger.info("Network loop exited.")

    def start(self) -> None:
        """Connect to server, create the GUI, and run the event loop.

        This is the main entry point for the client. It performs:
            1. TCP connection and CONNECT handshake.
            2. GUI creation (deferred import to avoid circular dependency).
            3. Network thread launch (daemon, so it dies with the process).
            4. Tkinter mainloop (blocks until the window is closed).
            5. Cleanup on exit.

        If the connection fails, a Tkinter error dialog is shown and the
        client exits gracefully.
        """
        # Import GUI here to avoid circular imports at module level.
        # client.py imports gui.py, and gui.py imports game_logic.py.
        from src.gui import BattleshipGUI

        try:
            self.connect()
        except (ConnectionRefusedError, OSError) as exc:
            # Show a Tkinter error dialog even if the connection fails,
            # so the user gets visual feedback rather than a silent crash.
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()  # Hide the root window.
            messagebox.showerror(
                "Connection Failed",
                f"Cannot connect to server at {self.host}:{self.port}.\n\n"
                f"Is the server running?\n\nError: {exc}",
            )
            root.destroy()
            logger.error("Connection failed: %s", exc)
            sys.exit(1)

        # Create the GUI, passing our send method as the callback.
        self.gui = BattleshipGUI(send_callback=self.send)
        self.running = True

        # Register a cleanup handler for when the user closes the window.
        self.gui.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # Start the background network thread.
        net_thread = threading.Thread(
            target=self._network_loop,
            daemon=True,
            name="BroadSide-NetworkThread",
        )
        net_thread.start()
        logger.info("Network thread started.")

        # Log connection status in the GUI.
        self.gui.log("Connecting to server...")

        # Block on the Tkinter event loop until the window closes.
        self.gui.run()

        # After the GUI exits, clean up.
        self.shutdown()

    def _on_window_close(self) -> None:
        """Handle the user closing the Tkinter window via the X button.

        Stops the network loop, destroys the GUI, and lets ``start()``
        proceed to ``shutdown()`` for socket cleanup.
        """
        logger.info("Window closed by user.")
        self.running = False
        if self.gui and self.gui.root:
            self.gui.root.destroy()

    def shutdown(self) -> None:
        """Cleanly shut down the client.

        Stops the network thread by clearing the ``running`` flag, then
        closes the TCP socket. Safe to call multiple times.
        """
        self.running = False
        if self.sock is not None:
            with contextlib.suppress(OSError):
                self.sock.close()
            self.sock = None
            logger.info("Socket closed.")


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    client = GameClient()
    client.start()
