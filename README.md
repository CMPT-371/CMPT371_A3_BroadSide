# **CMPT 371 A3 Socket Programming — `BroadSide`**

**Course:** CMPT 371 \- Data Communications & Networking
**Instructor:** Mirza Zaeem Baig
**Semester:** Spring 2026

> *Only one group member will submit the link to this repository on Canvas.*

---

## **Group Members**

| Name | Student ID | Email |
| :---- | :---- | :---- |
| Member 1 | 301XXXXXX | member1@sfu.ca |
| Member 2 | 301XXXXXX | member2@sfu.ca |

---

## **1. Project Overview & Description**

**BroadSide** is a real-time two-player Battleship game built using Python's Socket API over **TCP**. Two clients connect to a central server, place ships on a 10x10 grid, and take turns firing shots at each other's fleet. The server acts as the single source of truth — it manages the authoritative board state, validates every move, enforces turn order, and determines hit/miss/sunk/win outcomes. This prevents either client from cheating by modifying their local game state.

### Architecture

BroadSide uses a **client-server architecture** with a multithreaded server and two-thread clients:

```
┌──────────────────┐           TCP            ┌──────────────────┐
│    Client 1       │◄───────────────────────►│      Server       │
│                   │  Length-prefixed JSON    │                   │
│  Main Thread      │                         │  Main Thread      │
│  (Tkinter GUI)    │                         │  (accept loop +   │
│                   │                         │   matchmaking)    │
│  Network Thread   │                         │                   │
│  (recv loop)      │                         │  Game Session     │
└──────────────────┘                          │  Thread (daemon)  │
                                              │                   │
┌──────────────────┐           TCP            │  GameState        │
│    Client 2       │◄───────────────────────►│  (authoritative)  │
│  (same as above)  │  Length-prefixed JSON    └──────────────────┘
└──────────────────┘
```

- **Server (`server.py`)** — Listens for TCP connections, matches pairs of players via a matchmaking queue, and spawns an isolated daemon thread per game session. Each session owns a `GameState` instance that validates every action.
- **Client (`client.py`)** — Connects to the server and runs two threads: the main thread drives the Tkinter GUI, while a daemon network thread receives server messages and dispatches them to the GUI via `root.after()` for thread safety.
- **GUI (`gui.py`)** — Renders two 10x10 Canvas grids (own fleet + attack board), handles ship placement with hover preview and rotation, and displays shot results with color-coded cells.
- **Protocol (`protocol.py`)** — Implements 4-byte length-prefixed JSON framing over TCP, ensuring atomic message delivery regardless of how TCP segments the byte stream.
- **Game Logic (`game_logic.py`)** — Pure-logic layer with zero I/O dependencies. Defines `Ship`, `Board`, and `GameState` classes that enforce all Battleship rules.

---

## **2. System Limitations & Edge Cases**

As required by the project specifications, we have identified and handled (or defined) the following limitations and potential issues within our application scope:

- **Handling Multiple Clients Concurrently:**
  - *Solution:* The server uses Python's `threading` module. When two clients connect, they are popped from the matchmaking queue and assigned to an isolated `game_session` daemon thread. The matchmaking queue is protected by a `threading.Lock` to prevent race conditions. Multiple game sessions can run concurrently.
  - *Limitation:* Thread creation is bounded by system resources. A production-scale application would require a thread pool or asynchronous I/O (`asyncio`) to handle thousands of concurrent connections.

- **TCP Stream Buffering:**
  - *Solution:* TCP is a continuous byte stream, meaning multiple JSON messages can arrive concatenated in a single `recv()` call. We implemented a **4-byte length-prefix framing protocol** (`protocol.py`) — each message is preceded by its byte length as a big-endian unsigned integer. The receiver reads the length first, then reads exactly that many bytes via a `_recv_exactly()` helper that handles TCP fragmentation. Payload size is capped at 1 MB to prevent memory exhaustion from malformed headers.

- **Client Disconnection Mid-Game:**
  - *Solution:* All socket operations in the server are wrapped in safe helper functions (`_safe_send`, `_safe_recv`) that catch `ConnectionError`, `BrokenPipeError`, `ConnectionResetError`, and `OSError`. If a client disconnects unexpectedly, the server sends an `OPPONENT_DISCONNECTED` message to the remaining player and cleanly closes both sockets.
  - *Limitation:* There is no reconnection mechanism. If a player drops, the game session ends.

- **Input Validation & Security:**
  - *Solution:* The server validates every move through the `GameState` class: checks that coordinates are within bounds (0–9), that the cell has not already been targeted, and that it is the correct player's turn. Invalid moves are rejected with an `ERROR` message and the turn is not advanced.
  - *Limitation:* The JSON protocol is not encrypted. A malicious user on the same network could theoretically intercept or forge packets. This is acceptable for a LAN-based educational project.

- **GUI Thread Safety:**
  - *Solution:* Tkinter is not thread-safe. The client's network thread never calls GUI methods directly — it schedules all updates via `root.after(0, callback, args)`, which queues the callback on the Tkinter main thread's event loop.

- **Network Scope:**
  - *Limitation:* The application is designed for **localhost or LAN** play. There is no NAT traversal or relay server, so players behind different routers cannot connect without manual port forwarding.

---

## **3. Video Demo**

> *Include a clickable link to the demo video (max 2 minutes).*

Our 2-minute video demonstration covering connection establishment, ship placement, real-time gameplay, and graceful termination can be viewed below:

[**Watch Project Demo**](INSERT_VIDEO_LINK_HERE)

---

## **4. Prerequisites (Fresh Environment)**

To run this project, you need:

- **Python 3.10** or higher
- **pip** (comes bundled with Python)
- **Tkinter** (included with standard Python on most systems)
  - macOS: Included with the official Python installer from [python.org](https://www.python.org/)
  - Windows: Included by default with the official Python installer (ensure "tcl/tk" is checked during install)
  - Linux: Install via `sudo apt-get install python3-tk` (Debian/Ubuntu)
- **Pillow** (installed automatically via `requirements.txt`)
  - Used for custom visual assets in the GUI

---

## **5. Step-by-Step Run Guide**

> *The grader must be able to copy-paste these commands on a fresh environment.*

### **Step 1: Clone the Repository**

```bash
git clone https://github.com/CMPT-371/CMPT371_A3_BroadSide.git
cd CMPT371_A3_BroadSide
```

### **Step 2: Create a Virtual Environment**

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### **Step 3: Install Dependencies**

```bash
pip install -r requirements.txt
```

### **Step 3b: Developer Setup — Formatting & Linting (Contributors Only)**

> *This step is only needed if you are developing/modifying the code. If you are a grader or just running the application, skip to Step 4.*

Install the developer tools (Black formatter, Ruff linter, pre-commit framework):

```bash
pip install -r requirements-dev.txt
```

Activate the pre-commit hooks (one-time setup per clone):

```bash
pre-commit install
```

From this point on, every `git commit` will **automatically format and lint** your code. If Black or Ruff modify any files, the commit will pause so you can review the changes — simply run `git add . && git commit` again.

To manually format the entire codebase at any time:

```bash
pre-commit run --all-files
```

**CI safety net:** Even if you skip this step, the GitHub Actions workflow will auto-fix and push formatting corrections on every push to `main`.

### **Step 4: Start the Server**

The server binds to `127.0.0.1` on port `5050` by default.

**macOS / Linux:**
```bash
python3 -m src.server
```

**Windows:**
```cmd
python -m src.server
```

You should see:
```
[HH:MM:SS] [INFO] BroadSide server listening on 127.0.0.1:5050
[HH:MM:SS] [INFO] Waiting for players to connect...
```

### **Step 5: Connect Player 1**

Open a **new** terminal window (keep the server running). Activate the venv again, then run:

**macOS / Linux:**
```bash
cd CMPT371_A3_BroadSide
source venv/bin/activate
python3 -m src.client
```

**Windows:**
```cmd
cd CMPT371_A3_BroadSide
venv\Scripts\activate
python -m src.client
```

The GUI window opens. The status bar shows "Waiting for an opponent to connect..."

### **Step 6: Connect Player 2**

Open a **third** terminal window. Activate the venv again, then run the client again (same commands as Step 5). Both GUIs transition to ship placement mode.

### **Step 7: Gameplay**

1. **Place ships:** Click on your fleet grid to place each ship. Press **R** or right-click to rotate between horizontal and vertical. A blue hover preview shows valid placements; red indicates invalid.
2. **Fire shots:** Once both players place ships, Player 1 fires first. Click a cell on the attack board to fire. Hits show red, misses show white, and sunk ships show dark red.
3. **Win condition:** The game ends when one player sinks all 5 of the opponent's ships (17 total cells). A victory/defeat overlay is displayed.
4. **Disconnect handling:** If either player closes their window, the opponent receives a notification.

---

## **6. Technical Protocol Details (JSON over TCP)**

We designed a custom application-layer protocol using **length-prefixed JSON over TCP**:

### Message Framing

Every message is sent as: `[4-byte big-endian uint32 length][UTF-8 JSON payload]`

This ensures reliable message boundaries over the TCP byte stream. The `_recv_exactly()` helper handles TCP fragmentation by looping until the full requested byte count is accumulated.

### Message Types

| Phase | Direction | Type | Key Fields |
| :---- | :---- | :---- | :---- |
| Handshake | Client → Server | `CONNECT` | — |
| Handshake | Server → Client | `WAIT` | `message` |
| Handshake | Server → Client | `WELCOME` | `player_id`, `message` |
| Handshake | Server → Both | `GAME_START` | `message` |
| Setup | Client → Server | `PLACE_SHIPS` | `ships` (list of ship dicts) |
| Setup | Server → Client | `SHIPS_CONFIRMED` | `message` |
| Setup | Server → Client | `SHIPS_REJECTED` | `message` |
| Setup | Server → Both | `ALL_READY` | `turn` |
| Gameplay | Server → Client | `YOUR_TURN` | `turn` |
| Gameplay | Server → Client | `OPPONENT_TURN` | `turn` |
| Gameplay | Client → Server | `FIRE` | `row`, `col` |
| Gameplay | Server → Both | `RESULT` | `player`, `row`, `col`, `result`, `sunk_ship`, `game_over`, `winner`, `next_turn` |
| End | Server → Both | `GAME_OVER` | `winner`, `reason` |
| Error | Server → Client | `ERROR` | `message` |
| Disconnect | Server → Client | `OPPONENT_DISCONNECTED` | `message` |

### Game Lifecycle

```
Client              Server              Client
  |--- CONNECT ------->|                   |
  |<------ WAIT -------|                   |
  |                     |<--- CONNECT -----|
  |<---- WELCOME ------|------- WELCOME -->|
  |<-- GAME_START -----|---- GAME_START -->|
  |--- PLACE_SHIPS --->|                   |
  |<- SHIPS_CONFIRMED -|                   |
  |                     |<-- PLACE_SHIPS --|
  |                     |-- SHIPS_CONFIRMED -->|
  |<--- ALL_READY -----|---- ALL_READY --->|
  |<--- YOUR_TURN -----|-- OPPONENT_TURN ->|
  |--- FIRE ---------->|                   |
  |<---- RESULT -------|------ RESULT ---->|
  |<- OPPONENT_TURN ---|--- YOUR_TURN ---->|
  |                     |<------ FIRE -----|
  |<---- RESULT -------|------ RESULT ---->|
  |       ...           |       ...         |
  |<-- GAME_OVER ------|--- GAME_OVER ---->|
```

---

## **7. Project Structure**

```
CMPT371_A3_BroadSide/
├── src/
│   ├── __init__.py        # Package marker
│   ├── server.py          # TCP server: matchmaking, game sessions, move validation
│   ├── client.py          # TCP client: connection management, GUI bridge, network thread
│   ├── game_logic.py      # Pure game logic: Ship, Board, GameState (no I/O)
│   ├── protocol.py        # Length-prefixed JSON message framing over TCP
│   └── gui.py             # Tkinter Canvas GUI: grids, placement, firing, game log
├── tests/
│   ├── __init__.py        # Package marker
│   ├── conftest.py        # Shared pytest fixtures (socket helpers, ship placements)
│   ├── test_game_logic.py # 56 tests: Ship, Board, GameState rules
│   ├── test_protocol.py   # 16 tests: framing, large payloads, EOF, validation
│   └── test_server.py     # 21 tests: handshake, placement, gameplay, lifecycle
├── docs/
│   └── PLAN.md            # Implementation plan and architectural decisions
├── .github/
│   └── workflows/
│       ├── lint.yml       # CI: Black + Ruff auto-formatting on push
│       └── test.yml       # CI: pytest across 3 OS x 2 Python versions
├── requirements.txt       # Runtime dependencies (Pillow)
├── requirements-dev.txt   # Dev dependencies (Black, Ruff, pre-commit, pytest)
├── pyproject.toml         # Project config (pytest, Black, Ruff settings)
├── .pre-commit-config.yaml # Pre-commit hook configuration
├── .gitignore             # Python gitignore (venv, __pycache__, .pyc, etc.)
├── README.md              # This file
└── demo/                  # Video demo assets
```

---

## **8. Running Tests**

The project includes a comprehensive test suite (93 tests) covering game logic, protocol framing, and server behavior:

```bash
# Activate the virtual environment first, then:
pip install -r requirements-dev.txt
python3 -m pytest -v
```

Tests cover:
- **Game logic (56 tests):** Ship placement validation, shot processing, turn alternation, win detection, edge cases (out of bounds, duplicates, overlaps).
- **Protocol (16 tests):** Round-trip serialization, large payloads, rapid sequential sends, clean/dirty EOF handling, payload size limits.
- **Server (21 tests):** WELCOME/GAME_START handshake, ship placement flow, gameplay turn loop, full 17-shot game lifecycle, disconnect handling, helper function robustness.

---

## **9. Academic Integrity & References**

- **Code Origin:**
  - The socket boilerplate was adapted from the CMPT 371 course tutorial "TCP Echo Server". The multithreaded game session logic, Battleship game rules, length-prefixed protocol framing, and Tkinter GUI were written by the group.

- **GenAI Usage:**
  - Claude Code was used to assist with structuring the codebase, generating the Tkinter GUI layout, and drafting the README.
  - GitHub Copilot was used for code autocompletion during development.

- **References:**
  - [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html)
  - [Python `struct` Module](https://docs.python.org/3/library/struct.html)
  - [Python `threading` Module](https://docs.python.org/3/library/threading.html)
  - [Tkinter Documentation](https://docs.python.org/3/library/tkinter.html)
  - [Real Python: Intro to Python Threading](https://realpython.com/intro-to-python-threading/)
