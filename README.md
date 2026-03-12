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

BroadSide uses a **client-server architecture**:

```
┌──────────┐       TCP        ┌──────────┐       TCP        ┌──────────┐
│ Client 1 │◄────────────────►│  Server  │◄────────────────►│ Client 2 │
│  (GUI)   │  JSON messages   │ (Game    │  JSON messages   │  (GUI)   │
│          │  length-prefixed │  State)  │  length-prefixed │          │
└──────────┘                  └──────────┘                  └──────────┘
```

- **Server** — Listens for connections, matches two players, manages authoritative game state, validates moves, and broadcasts results.
- **Client** — Connects to the server, renders the Tkinter GUI (your board + attack board), sends shot coordinates, and receives game updates.

---

## **2. System Limitations & Edge Cases**

As required by the project specifications, we have identified and handled (or defined) the following limitations and potential issues within our application scope:

- **Handling Multiple Clients Concurrently:**
  - *Solution:* The server uses Python's `threading` module. When two clients connect, they are popped from the matchmaking queue and assigned to an isolated `game_session` daemon thread. This ensures concurrent games do not block the main server listener.
  - *Limitation:* Thread creation is bounded by system resources. A production-scale application would require a thread pool or asynchronous I/O (`asyncio`) to handle thousands of concurrent connections.

- **TCP Stream Buffering:**
  - *Solution:* TCP is a continuous byte stream, meaning multiple JSON messages can arrive concatenated in a single `recv()` call. We implemented a **4-byte length-prefix framing protocol** — each message is preceded by its byte length as a big-endian unsigned integer. The receiver reads the length first, then reads exactly that many bytes, ensuring messages are processed atomically regardless of how TCP segments them.

- **Client Disconnection Mid-Game:**
  - *Solution:* All socket operations are wrapped in `try/except` blocks. If a client disconnects unexpectedly (`BrokenPipeError`, `ConnectionResetError`), the server notifies the remaining player with a `DISCONNECT` message and cleanly closes the session.
  - *Limitation:* There is no reconnection mechanism. If a player drops, the game ends.

- **Input Validation & Security:**
  - *Solution:* The server validates every move: checks that coordinates are within bounds (0-9), that the cell hasn't already been fired upon, and that it is the correct player's turn. Invalid moves are rejected with an `ERROR` message.
  - *Limitation:* The JSON protocol is not encrypted. A malicious user on the same network could theoretically intercept or forge packets. This is acceptable for a LAN-based educational project.

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
  - Used for custom ship sprites and visual assets in the GUI

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

### **Step 4: Start the Server**

The server binds to `127.0.0.1` on port `5050` by default.

**macOS / Linux:**
```bash
python3 src/server.py
# Output: "[STARTING] Server is listening on 127.0.0.1:5050"
```

**Windows:**
```cmd
python src/server.py
# Output: "[STARTING] Server is listening on 127.0.0.1:5050"
```

### **Step 5: Connect Player 1**

Open a **new** terminal window (keep the server running). Activate the venv again, then run:

**macOS / Linux:**
```bash
cd CMPT371_A3_BroadSide
source venv/bin/activate
python3 src/client.py
# Output: "Connected to server. Waiting for opponent..."
```

**Windows:**
```cmd
cd CMPT371_A3_BroadSide
venv\Scripts\activate
python src/client.py
# Output: "Connected to server. Waiting for opponent..."
```

### **Step 6: Connect Player 2**

Open a **third** terminal window. Activate the venv again, then run the client script a second time (same commands as Step 5).

```
# Output: "Connected to server. Waiting for opponent..."
# Output: "Match found! The battle begins."
```

### **Step 7: Gameplay**

1. Both players place their ships on the grid using the GUI.
2. **Player 1** fires first — click a cell on the attack board to fire a shot.
3. The server validates the move and broadcasts the result (hit/miss/sunk) to both players.
4. **Player 2** takes their turn.
5. The game ends when one player sinks all of the opponent's ships. A victory/defeat screen is displayed and the connections close gracefully.

---

## **6. Technical Protocol Details (JSON over TCP)**

We designed a custom application-layer protocol using **length-prefixed JSON over TCP**:

### Message Framing

Every message is sent as: `[4-byte big-endian length][JSON payload bytes]`

This ensures reliable message boundaries over the TCP byte stream.

### Message Types

| Phase | Direction | Message |
| :---- | :---- | :---- |
| Handshake | Client -> Server | `{"type": "CONNECT"}` |
| Handshake | Server -> Client | `{"type": "WELCOME", "player_id": 1}` |
| Setup | Client -> Server | `{"type": "PLACE_SHIPS", "ships": [...]}` |
| Setup | Server -> Client | `{"type": "SHIPS_CONFIRMED"}` |
| Setup | Server -> Both | `{"type": "GAME_START", "your_turn": true/false}` |
| Gameplay | Client -> Server | `{"type": "FIRE", "row": 3, "col": 5}` |
| Gameplay | Server -> Both | `{"type": "RESULT", "row": 3, "col": 5, "hit": true, "sunk": "Destroyer", "turn": 2}` |
| End | Server -> Both | `{"type": "GAME_OVER", "winner": 1}` |
| Error | Server -> Client | `{"type": "ERROR", "message": "Not your turn"}` |
| Disconnect | Server -> Client | `{"type": "DISCONNECT", "reason": "Opponent left"}` |

---

## **7. Project Structure**

```
CMPT371_A3_BroadSide/
├── src/
│   ├── server.py          # TCP server: matchmaking, game state, move validation
│   ├── client.py          # TCP client: connection handling, GUI event loop
│   ├── game_logic.py      # Board, Ship, hit detection, win checking
│   ├── protocol.py        # Length-prefixed JSON message encoding/decoding
│   └── gui.py             # Tkinter GUI: board rendering, ship placement, firing
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── .gitignore             # Python gitignore
└── demo/                  # Video demo (or link in README)
```

---

## **8. Academic Integrity & References**

- **Code Origin:**
  - The socket boilerplate was adapted from the CMPT 371 course tutorial "TCP Echo Server". The multithreaded game session logic, Battleship game rules, length-prefixed protocol framing, and GUI were written by the group.

- **GenAI Usage:**
  - Claude Code was used to assist with structuring the codebase, generating the Tkinter GUI layout, and drafting the README.
  - GitHub Copilot was used for code autocompletion during development.

- **References:**
  - [Python Socket Programming HOWTO](https://docs.python.org/3/howto/sockets.html)
  - [Real Python: Intro to Python Threading](https://realpython.com/intro-to-python-threading/)
  - [Tkinter Documentation](https://docs.python.org/3/library/tkinter.html)
