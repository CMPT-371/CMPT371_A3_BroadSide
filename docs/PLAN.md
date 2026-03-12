# BroadSide — Definitive Implementation Plan

**The single execution document for a 2-person team. Every decision is made. Every edge case is addressed.**

This plan is structured as six sequential phases, each with explicit tasks, owners, acceptance criteria, and hard timeboxes. The rubric drives every decision — no wasted effort, no gold-plating before the fundamentals are locked in.

---

## Strategic Foundation

### Score-Driven Prioritization

The marking guide dictates every architectural and time-allocation decision:

| Criterion | Weight | What Wins | What Loses |
|-----------|--------|-----------|------------|
| Code Functionality | 40% | Runs without errors on a fresh machine. Establishes connections, exchanges data, terminates cleanly. Handles edge cases (disconnect, invalid input, concurrent sessions). | Crashes on startup. Hardcoded paths. Missing `requirements.txt`. Untested on a fresh venv. |
| Code Readability | 20% | Modular files, meaningful variable names, extensive docstrings & inline comments on every socket/threading operation. A stranger can read it top-to-bottom and understand the architecture. | Monolithic 500-line file. Single-letter variables. No comments. God function that does everything. |
| README Guide | 20% | Grader can copy-paste commands on a fresh machine (Mac or Windows) and be playing within 2 minutes. Limitations clearly defined. Architecture explained. | Assumes pre-installed libraries. Missing venv steps. No mention of limitations. |
| Video Demo | 20% | Under 120 seconds. Shows server start, both clients connect, ship placement, gameplay (hits/misses/sinks), win screen, graceful termination. Voiceover or music. | Over 2 minutes (penalized). Only shows one side. Doesn't show connection establishment or termination. |
| Bonus (UI) | 10% | Polished Tkinter GUI with color-coded grids, ship placement via click, animated hit/miss feedback, turn indicator, status bar. | CLI-only. No visual feedback. Raw text grid. |

### The North Star: What the Grader Does

The grader will do exactly this, in this order:

1. Clone the repo.
2. Follow the README step-by-step on a **fresh machine**.
3. If the code doesn't run → **lose 40% immediately** (they will not contact you).
4. If it runs → play a game, check for bugs, check for edge case handling.
5. Read the code for structure, naming, and comments.
6. Watch the video (penalized if over 2 minutes).

**Every decision we make optimizes for this exact workflow.**

### The Three Load-Bearing Technical Insights

**Insight 1: The protocol is the foundation.** Before you can build the game, the server, or the GUI, you need a reliable way to send and receive structured messages over TCP. Get framing wrong and everything built on top is unreliable. The length-prefixed JSON protocol is built first, tested in isolation, and never touched again.

**Insight 2: Server-authoritative state prevents bugs.** The server owns the board, validates every move, and determines all outcomes. Clients are thin renderers. This eliminates an entire class of synchronization bugs and makes the code easier to reason about.

**Insight 3: The GUI is half your grade.** Code functionality (40%) requires the game to *work*. The bonus (10%) rewards a polished UI. Together that is 50% of the score riding on the visual, interactive experience. A beautiful GUI with a solid server beats a perfect server with a CLI every time.

---

## Team Role Assignments (2 People)

| Role | ID | Primary Ownership | Secondary |
|------|----|-------------------|-----------|
| **Backend Lead** | P1 | `server.py`, `game_logic.py`, `protocol.py`, threading, matchmaking, move validation, edge case handling | Help with client networking in `client.py` |
| **Frontend Lead** | P2 | `gui.py`, `client.py`, Tkinter board rendering, ship placement UI, firing UI, game state display, video demo | Help with protocol integration, README finalization |

Both team members should understand every file. Ownership means "you write it first and are accountable for its quality," not "the other person can't touch it."

---

## The Interface Contract (Define Before Any Code)

Every component codes to these types and function signatures. No raw dicts cross module boundaries — only typed structures and well-defined function calls.

```python
# ── Canonical Message Protocol (protocol.py) ──

# Framing: [4-byte big-endian uint32 length][UTF-8 JSON payload]
# Every send() call wraps the JSON in this frame.
# Every recv() call reads the 4-byte header first, then reads exactly N bytes.

def send_message(sock: socket.socket, message: dict) -> None:
    """Serialize a dict to JSON, prepend 4-byte length header, send over TCP."""
    ...

def recv_message(sock: socket.socket) -> dict | None:
    """Read 4-byte length header, then read exactly that many bytes, deserialize JSON."""
    ...


# ── Game Logic Types (game_logic.py) ──

BOARD_SIZE = 10  # 10x10 grid

SHIP_DEFINITIONS: dict[str, int] = {
    "Carrier": 5,
    "Battleship": 4,
    "Cruiser": 3,
    "Submarine": 3,
    "Destroyer": 2,
}

class Ship:
    name: str           # e.g. "Carrier"
    size: int           # e.g. 5
    positions: list[tuple[int, int]]   # grid cells occupied
    hits: set[tuple[int, int]]         # cells that have been hit

class Board:
    grid: list[list[str]]              # 10x10, values: EMPTY/SHIP/HIT/MISS
    ships: list[Ship]

    def place_ship(self, name, row, col, horizontal) -> bool: ...
    def receive_shot(self, row, col) -> tuple[str, str | None]: ...
        # Returns ("hit"/"miss"/"sunk", ship_name_or_None)
    def all_sunk(self) -> bool: ...


# ── Server Session State (server.py) ──

def game_session(conn_p1: socket, conn_p2: socket) -> None:
    """Isolated game loop for two matched players on a daemon thread."""
    ...

def start_server(host: str, port: int) -> None:
    """Main server loop: accept connections, matchmake, spawn sessions."""
    ...


# ── Client State (client.py) ──

def start_client(host: str, port: int) -> None:
    """Connect to server, run GUI event loop, handle send/recv on background thread."""
    ...


# ── GUI (gui.py) ──

class BattleshipGUI:
    """Tkinter-based GUI. Two grids (own board + attack board), status bar, ship placement mode."""

    def __init__(self, send_callback: Callable[[dict], None]): ...
    def handle_server_message(self, message: dict) -> None: ...
    def run(self) -> None: ...
```

### Message Protocol Specification (Locked)

| Phase | Direction | Type | Payload | Purpose |
|-------|-----------|------|---------|---------|
| Handshake | C -> S | `CONNECT` | `{}` | Client requests to join matchmaking queue |
| Handshake | S -> C | `WELCOME` | `{"player_id": 1, "message": "..."}` | Server assigns player number (1 or 2) |
| Waiting | S -> C | `WAIT` | `{"message": "Waiting for opponent..."}` | Server tells P1 to wait for P2 |
| Setup | S -> Both | `GAME_START` | `{"message": "..."}` | Both players connected, begin ship placement |
| Setup | C -> S | `PLACE_SHIPS` | `{"ships": [{"name": "Carrier", "row": 0, "col": 0, "horizontal": true}, ...]}` | Client submits all 5 ship placements |
| Setup | S -> C | `SHIPS_CONFIRMED` | `{"message": "..."}` | Server validates and accepts placement |
| Setup | S -> C | `SHIPS_REJECTED` | `{"message": "Invalid placement: ..."}` | Server rejects invalid placement |
| Setup | S -> Both | `ALL_READY` | `{"turn": 1}` | Both players placed ships, game begins |
| Gameplay | S -> Both | `YOUR_TURN` / `OPPONENT_TURN` | `{"turn": 1}` | Server announces whose turn it is |
| Gameplay | C -> S | `FIRE` | `{"row": 3, "col": 5}` | Active player fires a shot |
| Gameplay | S -> Both | `RESULT` | `{"row": 3, "col": 5, "result": "hit", "sunk": "Destroyer" or null, "turn": 2}` | Shot result broadcast to both players |
| Gameplay | S -> C | `ERROR` | `{"message": "Not your turn"}` | Invalid action rejected |
| End | S -> Both | `GAME_OVER` | `{"winner": 1, "reason": "All ships sunk"}` | Game ended normally |
| Disconnect | S -> C | `OPPONENT_DISCONNECTED` | `{"message": "..."}` | Other player dropped |

**Acceptance criterion:** Both team members can explain these message types, their payloads, and the sequencing from memory before writing any implementation code.

---

## Phase 0 — Environment & Project Skeleton (Evening 1 — ~2 hours)

**Goal:** Both team members have identical dev environments, the repo has the folder structure checked in, empty module files exist with docstrings and function signatures, and both of you can run a trivial "hello" script through the venv.

### Task 0.1: Environment Setup (Both, 20 min)

- Install **Python 3.10+** from [python.org](https://www.python.org/) (NOT Homebrew on macOS — Homebrew Python sometimes lacks Tkinter).
- Verify Tkinter works:
  ```bash
  python3 -c "import tkinter; tkinter.Tk().destroy(); print('Tkinter OK')"
  ```
- Clone the repo. Create and activate a venv. Install dependencies (will be minimal at this stage).
- **Both** members verify this independently on their own machine.

**Acceptance criterion:** Both team members can run `python3 -c "import tkinter; print('OK')"` inside the venv without errors.

### Task 0.2: Project Skeleton (P1, 30 min)

Create the directory structure and empty files with module docstrings:

```
CMPT371_A3_BroadSide/
├── src/
│   ├── __init__.py            # Empty (makes src a package)
│   ├── server.py              # TCP server: matchmaking, game state, move validation
│   ├── client.py              # TCP client: connection handling, GUI event loop
│   ├── game_logic.py          # Board, Ship, hit detection, win checking
│   ├── protocol.py            # Length-prefixed JSON message encoding/decoding
│   └── gui.py                 # Tkinter GUI: board rendering, ship placement, firing
├── docs/
│   └── PLAN.md                # This file
├── requirements.txt           # Python dependencies
├── README.md                  # Submission README (already written)
├── .gitignore                 # Python gitignore (already exists)
└── demo/                      # Video demo directory
    └── .gitkeep
```

Every `.py` file gets:
- A module-level docstring explaining its purpose and its role in the architecture.
- Stub classes/functions matching the interface contract above (with `pass` or `raise NotImplementedError`).
- Import statements for the modules it will depend on.

**Acceptance criterion:** `python3 -c "from src import protocol, game_logic, server, client, gui"` succeeds without errors.

### Task 0.3: Requirements File (P2, 10 min)

```
# requirements.txt
# No external dependencies required for core functionality.
# Tkinter ships with the standard Python distribution.
# This file exists for completeness and to satisfy the assignment requirement.
```

If we add any non-stdlib dependencies later (e.g., `Pillow` for ship sprites for the bonus), add them here. For now, the entire project uses only the Python standard library: `socket`, `threading`, `json`, `struct`, `tkinter`, `dataclasses`, `enum`, `logging`.

**Acceptance criterion:** `pip install -r requirements.txt` succeeds (even if it installs nothing).

### Task 0.4: Git Workflow Agreement (Both, 10 min)

- **Branching strategy:** Simple — `main` is always runnable. Each person works on a feature branch (`feature/protocol`, `feature/game-logic`, `feature/server`, `feature/gui`). Merge via pull request with a quick review from the other person.
- **Commit messages:** Imperative mood, short first line: `Add length-prefixed message framing to protocol.py`
- **Merge conflict rule:** If a merge conflict arises, the person merging resolves it. No force-pushes to `main`.

---

## Phase 1 — Protocol & Game Logic (Evening 1 continued — ~3 hours)

**Goal:** The two lowest-level modules are complete, tested manually, and merged to `main`. These modules have zero dependencies on networking or GUI — they are pure logic and can be verified in isolation.

### Task 1.1: Message Framing Protocol (P1, 1 hour)

**File:** `src/protocol.py`

Implement exactly two functions:

```python
import socket
import json
import struct

HEADER_SIZE = 4  # 4-byte big-endian unsigned int

def send_message(sock: socket.socket, message: dict) -> None:
    """
    Serialize a dictionary to JSON, prepend a 4-byte big-endian length header,
    and send the entire frame over the TCP socket.

    Framing format: [uint32 length][UTF-8 JSON bytes]

    Uses sendall() to guarantee the entire frame is transmitted,
    even if the OS splits it across multiple TCP segments.
    """
    ...

def recv_message(sock: socket.socket) -> dict | None:
    """
    Read a single length-prefixed JSON message from the TCP socket.

    1. Read exactly 4 bytes (the length header).
    2. Unpack as a big-endian uint32 to get the payload length.
    3. Read exactly that many bytes (the JSON payload).
    4. Deserialize and return as a dict.

    Returns None if the connection is closed (recv returns b'').
    Raises ConnectionError if the stream is corrupted.
    """
    ...

def _recv_exactly(sock: socket.socket, num_bytes: int) -> bytes:
    """
    Helper: read exactly num_bytes from the socket.
    Handles the case where recv() returns fewer bytes than requested
    (TCP may fragment the stream).
    """
    ...
```

**Why length-prefixed and not newline-delimited (like the example repo)?**

The example repo uses `\n` as a message boundary and `data.strip().split('\n')` to parse. This works for small messages but is fragile:
- If a JSON payload ever contains a newline (e.g., in a string value), the parser breaks.
- The `strip().split()` approach silently drops partial messages if TCP delivers half a JSON object.

Length-prefixed framing is the industry standard (used by HTTP/2, gRPC, Kafka, etc.). It adds 4 bytes of overhead per message and eliminates an entire class of parsing bugs.

**Manual test:**

```python
# test_protocol_manual.py (run interactively, not part of submission)
import socket, threading
from src.protocol import send_message, recv_message

def mock_server(server_sock):
    conn, _ = server_sock.accept()
    msg = recv_message(conn)
    assert msg == {"type": "CONNECT"}, f"Expected CONNECT, got {msg}"
    send_message(conn, {"type": "WELCOME", "player_id": 1})
    conn.close()

server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.bind(("127.0.0.1", 0))
server_sock.listen(1)
port = server_sock.getsockname()[1]

t = threading.Thread(target=mock_server, args=(server_sock,))
t.start()

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(("127.0.0.1", port))
send_message(client, {"type": "CONNECT"})
response = recv_message(client)
assert response == {"type": "WELCOME", "player_id": 1}
print("Protocol test PASSED")
client.close()
t.join()
server_sock.close()
```

**Acceptance criterion:** The manual test passes. Messages survive rapid sequential sends (send 10 messages back-to-back, receive all 10 intact).

### Task 1.2: Game Logic — Ship & Board (P2, 1.5 hours)

**File:** `src/game_logic.py`

Implement the game state engine with zero networking dependencies:

```python
from dataclasses import dataclass, field

BOARD_SIZE = 10

SHIP_DEFINITIONS: dict[str, int] = {
    "Carrier": 5,
    "Battleship": 4,
    "Cruiser": 3,
    "Submarine": 3,
    "Destroyer": 2,
}

# Cell states
EMPTY = "~"
SHIP = "S"
HIT = "X"
MISS = "O"
```

**Class: `Ship`**
- `name: str` — Ship type
- `size: int` — Number of cells
- `positions: list[tuple[int, int]]` — Occupied cells (computed from row, col, horizontal)
- `hits: set[tuple[int, int]]` — Cells that have been hit
- `is_sunk() -> bool` — All positions hit

**Class: `Board`**
- `grid: list[list[str]]` — 10x10, initialized to `EMPTY`
- `ships: list[Ship]` — Placed ships

Methods:
- `place_ship(name, row, col, horizontal) -> bool` — Validate placement (in bounds, no overlap, no adjacency violation), add to grid. Return `True` if valid, `False` if rejected.
- `receive_shot(row, col) -> tuple[str, str | None]` — Process an incoming shot. Returns `("hit", None)`, `("miss", None)`, or `("sunk", "Destroyer")`. Mutates grid state.
- `all_sunk() -> bool` — All ships destroyed.
- `is_valid_target(row, col) -> bool` — Cell is in bounds and hasn't been shot at before.

**Class: `GameState`**
- `board_p1: Board`, `board_p2: Board`
- `current_turn: int` — 1 or 2
- `phase: str` — `"setup"`, `"playing"`, `"finished"`
- `winner: int | None`

Methods:
- `place_ships(player_id, ships_data) -> tuple[bool, str]` — Validate and place all 5 ships for a player. Return `(True, "OK")` or `(False, "error reason")`.
- `process_shot(player_id, row, col) -> dict` — Validate it's the player's turn, validate coordinates, apply shot to opponent's board, check for game over. Return the `RESULT` message payload.
- `both_players_ready() -> bool` — Both players have placed ships.

**Edge cases to handle explicitly:**
- Ship placement: out of bounds, overlapping another ship, duplicate ship name.
- Firing: not your turn, already fired at that cell, coordinates out of bounds, game already over.
- Win detection: check after every shot.

**Manual test:**

```python
board = Board()
assert board.place_ship("Carrier", 0, 0, horizontal=True) == True
assert board.place_ship("Destroyer", 0, 0, horizontal=True) == False  # overlap
assert board.place_ship("Destroyer", 2, 0, horizontal=True) == True

result, sunk = board.receive_shot(0, 0)
assert result == "hit" and sunk is None
# ... hit all 5 cells of Carrier ...
result, sunk = board.receive_shot(0, 4)
assert result == "sunk" and sunk == "Carrier"
```

**Acceptance criterion:** All ship placements validate correctly. All shot outcomes (hit/miss/sunk) are correct. `all_sunk()` triggers when the last ship cell is hit. Invalid moves raise or return errors, never crash.

### Task 1.3: Cross-Review & Merge (Both, 30 min)

- P1 reviews `game_logic.py`, P2 reviews `protocol.py`.
- Check: docstrings on every function, meaningful variable names, no magic numbers without comments.
- Merge both to `main`. Verify `from src.protocol import send_message, recv_message` and `from src.game_logic import GameState, Board` work.

**Acceptance criterion:** `main` branch has both modules, both import cleanly, both pass manual tests.

---

## Phase 2 — Server Implementation (Session 2 — ~3 hours)

**Goal:** A fully functional server that accepts two TCP clients, runs them through the handshake → setup → gameplay → termination lifecycle, with all edge cases handled. Testable with a simple CLI or `netcat`.

### Task 2.1: Server Core — Matchmaking & Session Spawning (P1, 1.5 hours)

**File:** `src/server.py`

```python
import socket
import threading
import logging
from src.protocol import send_message, recv_message
from src.game_logic import GameState

HOST = "127.0.0.1"
PORT = 5050

# Configure logging for server events
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BroadSide-Server")
```

**Architecture:**

```
Main Thread (start_server)
│
├─ accept() loop
│   ├─ Client connects → recv CONNECT → add to matchmaking_queue
│   └─ When queue has 2 players → pop both, spawn game_session thread
│
└─ game_session Thread (one per pair)
    ├─ Send WELCOME to both (assign player_id 1 and 2)
    ├─ Wait for PLACE_SHIPS from both (with timeout)
    ├─ Send ALL_READY
    ├─ Turn loop:
    │   ├─ Send YOUR_TURN / OPPONENT_TURN
    │   ├─ Recv FIRE from active player
    │   ├─ Validate via GameState.process_shot()
    │   ├─ Broadcast RESULT to both
    │   └─ If game over → send GAME_OVER, break
    └─ Close both sockets
```

**Thread safety:** The matchmaking queue is shared between the main thread and any concurrent sessions. Use a `threading.Lock` to protect it. (In practice, with only 2 clients connecting, this is defensive — but it demonstrates understanding of concurrency, which the rubric values.)

**Edge cases (required for full 40% on functionality):**

1. **Client disconnects during setup:**
   - Wrap `recv_message` in try/except for `ConnectionError`, `ConnectionResetError`, `BrokenPipeError`.
   - If P1 disconnects while P2 is placing ships → send `OPPONENT_DISCONNECTED` to P2, close session.

2. **Client disconnects during gameplay:**
   - Same try/except wrapping on every recv/send.
   - Notify remaining player, declare them the winner or end gracefully.

3. **Invalid FIRE coordinates:**
   - `GameState.process_shot()` returns an error dict.
   - Send `ERROR` message to the offending client. Do NOT advance the turn.

4. **Client sends wrong message type:**
   - During setup, if client sends `FIRE` instead of `PLACE_SHIPS` → send `ERROR`, keep waiting.
   - During gameplay, if it's not your turn → send `ERROR`.

5. **Server shutdown:**
   - `KeyboardInterrupt` handler: close all active sessions, close the server socket.
   - Log shutdown event.

6. **Third client connects while a game is in progress:**
   - They sit in the matchmaking queue. When another client joins, they get matched. Multiple concurrent games supported via threading.

**Acceptance criterion:** Server runs. Two telnet/netcat clients can connect and manually send JSON messages through the full game lifecycle. Server logs every event. Disconnecting one client notifies the other. Invalid moves are rejected with `ERROR`.

### Task 2.2: Server Robustness Pass (P1, 30 min)

Go through every `send_message` and `recv_message` call and ensure:
- It is wrapped in `try/except (ConnectionError, BrokenPipeError, ConnectionResetError, OSError)`.
- The except block logs the error, notifies the other player (if possible), and cleans up both sockets.
- No exception can crash the server's main accept loop (only the game_session thread should die).

Add a **ship placement timeout** (optional but impressive): if a player doesn't place ships within 120 seconds, disconnect them and notify the opponent.

**Acceptance criterion:** You cannot crash the server by disconnecting clients at any point in the lifecycle. The server always returns to a clean state and can accept new games.

### Task 2.3: CLI Test Client (P2, 1 hour)

Before building the GUI, build a minimal CLI client that can play through the full game. This is your debugging tool for the server:

```python
# Temporary test client (will be replaced by GUI client)
# Connect, send CONNECT, receive WELCOME
# Place ships (hardcoded for testing)
# Loop: if my turn, prompt for row/col, send FIRE, display result
```

This client exists to **validate the server independently of the GUI**. It can be as ugly as needed — it's a debugging tool, not a submission artifact.

**Acceptance criterion:** Two CLI test clients can play a complete game against each other through the server. Full lifecycle: connect → place ships → take turns → win/lose → disconnect.

---

## Phase 3 — Client Networking & GUI Foundation (Session 3 — ~4 hours)

**Goal:** The real client with Tkinter GUI. Ship placement works. The networking runs on a background thread so the GUI never freezes.

### Task 3.1: Client Networking Layer (P1, 1.5 hours)

**File:** `src/client.py`

The client has two threads:
1. **Main thread:** Runs the Tkinter event loop (`gui.run()`).
2. **Network thread:** Runs a `recv_message` loop, pushes incoming messages to the GUI via `root.after()`.

```python
import socket
import threading
from src.protocol import send_message, recv_message
from src.gui import BattleshipGUI

class GameClient:
    """
    Manages the TCP connection to the server and bridges between
    the network thread and the Tkinter GUI thread.
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock: socket.socket | None = None
        self.gui: BattleshipGUI | None = None
        self.running = False

    def connect(self) -> None:
        """Establish TCP connection and send CONNECT handshake."""
        ...

    def send(self, message: dict) -> None:
        """Thread-safe send. Called by GUI on user actions."""
        ...

    def _network_loop(self) -> None:
        """
        Background thread: continuously receive messages from server.
        Dispatch to GUI via root.after() to stay thread-safe with Tkinter.
        """
        ...

    def start(self) -> None:
        """Connect, create GUI, start network thread, run GUI event loop."""
        ...
```

**Critical threading rule:** Tkinter is NOT thread-safe. The network thread must NEVER call GUI methods directly. Instead, use `self.gui.root.after(0, self.gui.handle_server_message, msg)` to schedule GUI updates on the main thread's event loop.

**Acceptance criterion:** Client connects to server, receives WELCOME, and the GUI window opens. Network messages arrive on the background thread and are dispatched to the GUI without freezing or crashing.

### Task 3.2: GUI — Layout & Ship Placement (P2, 2.5 hours)

**File:** `src/gui.py`

**Layout (two-grid design):**

```
┌─────────────────────────────────────────────────────────┐
│                    BroadSide                            │
│                                                         │
│  YOUR FLEET              ATTACK BOARD                   │
│  ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐  ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐      │
│  │ │ │ │ │ │ │ │ │ │ │  │ │ │ │ │ │ │ │ │ │ │      │
│  ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤  ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤      │
│  │ │■│■│■│■│■│ │ │ │ │  │ │ │ │ │ │ │ │ │ │ │      │
│  ...                      ...                           │
│  └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘  └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘      │
│                                                         │
│  Ship: [Carrier (5)]  [Rotate: Horizontal]              │
│  Status: Place your Carrier (5 cells)                   │
│                                                         │
│  ┌─────────────────────────────────────────────┐        │
│  │ Game Log                                    │        │
│  │ > Connected to server.                      │        │
│  │ > Waiting for opponent...                   │        │
│  └─────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────┘
```

**Implementation using Tkinter Canvas (not grid of Buttons):**

Using `tk.Canvas` for each board gives pixel-level control for animations and coloring — critical for the bonus marks. Each board is a 10x10 grid of `CELL_SIZE x CELL_SIZE` rectangles drawn on a Canvas.

**Color scheme:**

| State | Color | Hex |
|-------|-------|-----|
| Empty (water) | Dark blue | `#1a3a5c` |
| Ship (own board) | Steel gray | `#708090` |
| Hit (enemy ship) | Red | `#e74c3c` |
| Miss (empty water) | White | `#ecf0f1` |
| Sunk (confirmed sunk ship) | Dark red | `#c0392b` |
| Hover / valid target | Light cyan | `#3498db` |
| Invalid target (already fired) | N/A (cursor changes to "X") | — |

**Ship placement flow:**

1. GUI enters "placement mode." The status bar shows: `"Place your Carrier (5 cells)"`.
2. Hovering over the own-board grid shows a preview of the ship (highlighted cells).
3. Left-click places the ship. Right-click or keyboard `R` rotates between horizontal/vertical.
4. After all 5 ships are placed, the GUI sends `PLACE_SHIPS` to the server and shows `"Waiting for opponent to place ships..."`.
5. When server sends `ALL_READY`, transition to gameplay mode.

**Key Tkinter elements:**

- `tk.Canvas` (x2) — own board and attack board
- `tk.Label` — status bar (current turn, messages)
- `tk.Text` or `tk.Listbox` — game log (scrollable, shows events)
- `tk.Button` — rotate ship (during placement)
- Canvas `bind("<Button-1>")` — left click handler for placement/firing
- Canvas `bind("<Motion>")` — hover handler for placement preview / target highlight
- Canvas `bind("<Button-3>")` — right click to rotate during placement

**Acceptance criterion:** GUI opens with two 10x10 grids. Player can place all 5 ships via click (with rotation). Ship preview appears on hover. Invalid placements are visually rejected (cell flashes red). After placing all ships, the placement UI is disabled.

---

## Phase 4 — Gameplay Integration (Session 4 — ~3 hours)

**Goal:** The full gameplay loop works end-to-end: server starts, two GUI clients connect, place ships, fire shots, see results, game ends with a winner.

### Task 4.1: Firing Mechanics (P2, 1.5 hours)

After `ALL_READY`:
- The attack board becomes clickable.
- Clicking a cell sends `{"type": "FIRE", "row": r, "col": c}` to the server.
- The GUI greys out the attack board while waiting for the result (prevents double-firing).
- When `RESULT` arrives:
  - If hit: color the attack board cell red. Play a brief flash animation (bonus).
  - If miss: color the attack board cell white.
  - If sunk: color all cells of the sunk ship dark red on the attack board. Show ship name in log.
  - Update the own-board if the result was for an incoming shot (opponent's FIRE).
- When `GAME_OVER` arrives: show a victory/defeat overlay. Disable all interaction. Close socket after 3 seconds or on click.

**The tricky part — incoming shots on your own board:**

When the server broadcasts a `RESULT`, both players receive it. The GUI must determine:
- "Was this MY shot?" → update the attack board.
- "Was this the OPPONENT'S shot at me?" → update my board.

The `RESULT` message includes `"turn"` (the player who WILL move next). Combined with the client's own `player_id`, this disambiguates.

**Acceptance criterion:** Two GUI clients can play a complete game. Hits, misses, and sinks render correctly on both clients' boards. The game ends with a winner/loser message.

### Task 4.2: Error Handling & UX Polish (P1, 1 hour)

- **Connection refused:** If the server isn't running, show a dialog: "Cannot connect to server at 127.0.0.1:5050. Is the server running?"
- **Server disconnect mid-game:** Show dialog: "Connection lost. The server or your opponent disconnected."
- **Already-fired cell:** If the player clicks a cell they already fired at, show a brief "Already targeted!" tooltip or status message. Do NOT send to server.
- **Turn enforcement on client side:** Grey out the attack board when it's not your turn. Show "Opponent's turn..." in the status bar. (Server also enforces this, but client-side enforcement prevents wasted network round-trips.)
- **Window close:** If the player closes the Tkinter window, cleanly close the socket (send nothing — the server detects the broken pipe).

### Task 4.3: Full Integration Test (Both, 30 min)

Run the complete system:

1. `python3 src/server.py` — server starts, logs "listening on 127.0.0.1:5050".
2. `python3 src/client.py` — Player 1 GUI opens, shows "Waiting for opponent..."
3. `python3 src/client.py` — Player 2 GUI opens, both transition to ship placement.
4. Both place ships. Server logs "Both players ready."
5. Play ~10 turns. Verify hits/misses render correctly on both clients.
6. One player wins. Victory/defeat screens appear.
7. Close both clients. Server returns to accept loop.
8. Repeat — start two new clients. Verify the server handles a second game correctly.

**Bug hunt checklist:**
- [ ] Can you play two consecutive games without restarting the server?
- [ ] What happens if Player 1 closes their window during Player 2's turn?
- [ ] What happens if you rapidly click the attack board 5 times?
- [ ] Do ship placements render correctly on the own-board?
- [ ] Does the game log show every event?

**Acceptance criterion:** Two complete games played back-to-back. All edge cases from the checklist verified. No crashes.

---

## Phase 5 — Code Quality, Comments & README Finalization (Session 5 — ~2.5 hours)

**Goal:** Lock in the 20% readability marks and 20% README marks. These are the easiest points to get — pure effort, no creativity required.

### Task 5.1: Comment Pass — Every File (Both, 1.5 hours split)

**P1 comments:** `server.py`, `protocol.py`
**P2 comments:** `client.py`, `gui.py`, `game_logic.py`

**Comment standard (matches rubric: "commented thoroughly so a new person can understand easily"):**

1. **Module docstring** (top of every file):
   ```python
   """
   CMPT 371 A3: BroadSide — [Module Name]

   Purpose: [2-3 sentences explaining what this module does and how it
   fits into the overall architecture.]

   Architecture: [Client-server / Protocol layer / Game logic / etc.]

   References:
       - [Any tutorials or docs used]
   """
   ```

2. **Class docstring:**
   ```python
   class Board:
       """
       Represents a single player's 10x10 Battleship grid.

       The board tracks ship positions and shot history. It is the
       authoritative state for one player's fleet — the server
       creates two Board instances (one per player) and delegates
       shot processing to them.

       Attributes:
           grid: 10x10 list of cell states (EMPTY, SHIP, HIT, MISS).
           ships: List of Ship instances placed on this board.
       """
   ```

3. **Function docstring:**
   ```python
   def place_ship(self, name: str, row: int, col: int, horizontal: bool) -> bool:
       """
       Attempt to place a ship on the board.

       Validates that:
           - The ship fits within the 10x10 grid boundaries.
           - No cells overlap with an existing ship.

       Args:
           name: Ship type (e.g., "Carrier"). Must be in SHIP_DEFINITIONS.
           row: Starting row (0-9).
           col: Starting column (0-9).
           horizontal: If True, ship extends rightward. If False, downward.

       Returns:
           True if placement succeeded, False if validation failed.
       """
   ```

4. **Inline comments on non-obvious operations:**
   ```python
   # Pack the payload length as a 4-byte big-endian unsigned integer.
   # This creates a fixed-size header that the receiver reads first
   # to know how many bytes of JSON payload follow.
   header = struct.pack("!I", len(payload))
   ```

   ```python
   # Use daemon=True so the game thread dies automatically if the
   # main server process is terminated (e.g., via Ctrl+C).
   thread = threading.Thread(target=game_session, args=(p1, p2), daemon=True)
   ```

**What NOT to comment:**
- Obvious operations: `i += 1  # increment i` — NO.
- Getter/setter one-liners: `def is_sunk(self): return len(self.hits) == self.size` — the code is self-documenting.

### Task 5.2: Code Structure Audit (Both, 30 min)

Walk through each file and verify:

| Check | Standard |
|-------|----------|
| Variable names | `player_board`, `ship_name`, `is_horizontal` — never `b`, `s`, `h` |
| Function length | No function exceeds ~50 lines. If it does, extract a helper. |
| Magic numbers | Every number has a named constant: `BOARD_SIZE = 10`, `HEADER_SIZE = 4`, `PORT = 5050` |
| Imports | Grouped: stdlib, then project modules. No unused imports. |
| Error messages | User-facing strings are clear: `"Invalid placement: ship extends beyond board"` not `"Error 3"` |
| Type hints | All function signatures have type hints: `def place_ship(self, name: str, ...) -> bool:` |
| Logging | Server uses `logging` module, not `print()`. Client can use `print()` for game log. |

### Task 5.3: README Final Review (P2, 30 min)

Open the README and verify against the rubric:

- [ ] Group members table has real names, IDs, emails
- [ ] Project description is clear and accurate
- [ ] Architecture diagram matches the actual implementation
- [ ] Limitations section covers at least 4 concrete limitations
- [ ] Run guide works on a fresh machine — **actually test it** (delete the venv, re-create, follow your own instructions)
- [ ] Mac AND Windows instructions are present for every step
- [ ] `requirements.txt` step is included even if it's empty
- [ ] Video demo link is present (or placeholder is clearly marked)

**Acceptance criterion:** A teammate (or friend) who has never seen the project can follow the README from scratch and be playing within 3 minutes.

---

## Phase 6 — Video Demo & Final Submission (Final Session — ~2 hours)

**Goal:** Record the demo video (under 120 seconds), do a final smoke test, push everything to GitHub.

### Task 6.1: Video Script & Recording (P2 leads, P1 assists — 1 hour)

**Script (target: 90-100 seconds):**

| Timestamp | What to Show | What to Say/Caption |
|-----------|-------------|---------------------|
| 0:00–0:10 | Terminal: `python3 src/server.py` | "Starting the BroadSide server on localhost:5050" |
| 0:10–0:20 | Terminal: `python3 src/client.py` (x2) | "Two clients connect. The server matches them." |
| 0:20–0:40 | GUI: Both players place ships | "Each player places 5 ships on their grid." |
| 0:40–0:55 | GUI: Player 1 fires, hit animation | "Player 1 fires at B5 — it's a hit!" |
| 0:55–1:05 | GUI: Player 2 fires, miss | "Player 2 fires at D3 — miss." |
| 1:05–1:20 | GUI: A few more turns, a ship sinks | "Player 1 sinks the Destroyer!" |
| 1:20–1:30 | GUI: Final shot, victory screen | "All ships sunk — Player 1 wins!" |
| 1:30–1:40 | Server terminal: logs showing graceful shutdown | "Connections close cleanly." |
| 1:40–1:45 | Optional: brief code walkthrough (split screen) | "Server-authoritative architecture with length-prefixed JSON protocol." |

**Recording tips:**
- Use QuickTime (macOS) or OBS (Windows) for screen recording.
- Arrange windows so all 3 terminals/GUIs are visible simultaneously (split screen or tiled).
- If doing a voiceover, keep it concise. If not, add background music (royalty-free).
- **Hard stop at 110 seconds.** Leave 10-second buffer under the 120-second penalty threshold.

**Acceptance criterion:** Video is under 120 seconds. Shows: server start, client connections, ship placement, multiple turns with hits/misses, a win, and clean termination.

### Task 6.2: Upload Video (P2, 10 min)

Upload to one of:
- YouTube (unlisted) — recommended for reliability.
- GitHub repo directly in `demo/` — works if file is <100MB.
- Google Drive (share link set to "anyone with the link").

Update the README with the actual video link.

### Task 6.3: Final Smoke Test (Both, 30 min)

**The "fresh machine" test:**

1. Clone the repo to a completely different directory (or ask a friend).
2. Follow the README exactly — do not deviate or use memory.
3. Create venv, install requirements, start server, start two clients.
4. Play a complete game.
5. If ANYTHING fails → fix it immediately. This test catches:
   - Hardcoded absolute paths
   - Missing files not committed to git
   - Import errors from wrong module paths
   - README instructions that skip a step

### Task 6.4: Final Push & Submission Checklist (Both, 15 min)

- [ ] All code committed and pushed to `main`
- [ ] Repo is named `CMPT371_A3_BroadSide`
- [ ] Repo is public (or CMPT-371 org gives TA access)
- [ ] `README.md` has real team member info
- [ ] `README.md` video link works
- [ ] `requirements.txt` exists
- [ ] `.gitignore` is present (no `__pycache__`, no `.pyc`, no `venv/`)
- [ ] `docs/PLAN.md` exists (this file)
- [ ] Video is under 120 seconds
- [ ] One team member submits the GitHub repo link on Canvas with both names and student IDs

---

## Key Technical Decisions (Resolved)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Protocol framing | 4-byte length-prefix | Industry standard. Eliminates message boundary bugs. More robust than `\n`-delimited (used in example repo). |
| Game state authority | Server-authoritative | Prevents desync bugs. Clients cannot cheat. Simpler to reason about. |
| Concurrency model | `threading` (one thread per game session) | Simple, sufficient for 2-player games. Matches course material. No need for `asyncio` complexity. |
| GUI framework | Tkinter `Canvas` (not `Button` grid) | Pixel-level control for colors, animations, hover effects. Required for bonus marks. Ships with stdlib. |
| GUI threading | Background recv thread + `root.after()` dispatch | Tkinter is not thread-safe. This is the standard pattern for network + GUI in Python. |
| Board size | 10x10 | Standard Battleship. Large enough to be interesting, small enough to render cleanly. |
| Ship set | Carrier(5), Battleship(4), Cruiser(3), Submarine(3), Destroyer(2) | Classic Hasbro Battleship rules. 17 total ship cells = ~34 turns average game. |
| Data format | JSON | Human-readable, built into Python stdlib. Sufficient for this message complexity. |
| Logging | `logging` module on server, `print`/game log on client | Server needs structured logs for debugging. Client has the GUI game log. |
| External dependencies | None (stdlib only) | Eliminates `requirements.txt` installation failures. Tkinter is bundled. Zero risk of "code doesn't run." |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Code doesn't run on grader's machine | Medium | **Critical (lose 40%)** | Fresh-machine test in Phase 6. Zero external dependencies. Mac + Windows instructions. |
| Tkinter not installed on grader's machine | Low | High | Document the fix in README (macOS: use python.org installer; Linux: `apt-get install python3-tk`). Tkinter ships with standard Python on all platforms. |
| Video over 2 minutes | Medium | Medium (penalized) | Script to 90 seconds. Hard stop at 110. Review before uploading. |
| GUI freezes during gameplay | Medium | High | Network thread pattern with `root.after()`. Never block the main thread. |
| Merge conflicts between P1 and P2 | Medium | Low | Clean module boundaries. `protocol.py` and `game_logic.py` are independent. Only `client.py` touches both networking and GUI. |
| Running out of time on GUI polish | High | Medium (lose bonus) | Core gameplay first. Polish is Phase 5. The bonus is 10% — don't sacrifice the 40% functionality for it. |
| Server crashes with concurrent games | Low | Medium | Each game session is an isolated thread with its own `GameState`. Shared state (matchmaking queue) protected by `threading.Lock`. |

---

## File Dependency Graph

```
protocol.py          game_logic.py
    │                     │
    ├─────────┬───────────┤
    │         │           │
    ▼         ▼           ▼
server.py  client.py   gui.py
              │           │
              └─────┬─────┘
                    │
              (Tkinter main loop)
```

- `protocol.py` — depends on: `socket`, `json`, `struct` (stdlib only)
- `game_logic.py` — depends on: `dataclasses` (stdlib only)
- `server.py` — depends on: `protocol.py`, `game_logic.py`
- `client.py` — depends on: `protocol.py`, `gui.py`
- `gui.py` — depends on: `tkinter` (stdlib)

**No circular dependencies. Every module can be imported and tested in isolation.**

---

## Phase-by-Phase Time Estimates

| Phase | Tasks | Estimated Time | Cumulative |
|-------|-------|---------------|------------|
| Phase 0 | Environment, skeleton, git setup | 2 hours | 2 hours |
| Phase 1 | Protocol + game logic (parallel) | 3 hours | 5 hours |
| Phase 2 | Server + CLI test client | 3 hours | 8 hours |
| Phase 3 | Client networking + GUI ship placement | 4 hours | 12 hours |
| Phase 4 | Gameplay integration + edge cases | 3 hours | 15 hours |
| Phase 5 | Comments, code quality, README review | 2.5 hours | 17.5 hours |
| Phase 6 | Video demo, smoke test, submission | 2 hours | 19.5 hours |
| **Total** | | **~20 hours** | (split across two people = ~10 hours each) |

**Buffer:** 4.5 hours before the April 5 deadline. Use for bug fixes, polish, or the unexpected.
