"""
BroadSide — A real-time two-player Battleship game over TCP sockets.

This package contains all source modules for the BroadSide application:

    protocol    — Length-prefixed JSON message framing over TCP.
    game_logic  — Board, Ship, and GameState models (pure logic, no I/O).
    server      — Multithreaded TCP server with matchmaking and session management.
    client      — TCP client with background networking thread.
    gui         — Tkinter-based GUI for ship placement, firing, and game display.
"""
