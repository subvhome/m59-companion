# M59 Companion: Architectural Blueprint & Module Analysis

## 1. Executive Summary: The "Self-Healing" Design
The M59 Companion is engineered with a **DNS-like memory resolution model**. Instead of relying on fragile hardcoded offsets (IP addresses), it utilizes **Hostnames** (Function Exports and Code Patterns) to dynamically locate data at runtime. This makes the application highly resilient to Address Space Layout Randomization (ASLR) and game version updates.

---

## 2. Core Modules (Integrated with m59_dashboard.py)

### 2.1 m59_dashboard.py (Main Entry Point)
*   **Role:** Orchestrates the UI (Tkinter) and manages the state of all sub-modules.
*   **Key Feature:** Implements a **Windows AppBar Docking** system, allowing the "Who List" to pin itself to the desktop edge and reserve screen space via Windows API (`SHAppBarMessage`).
*   **Logic:** Handles UI scaling, theme management, and the high-frequency polling loops for chat logs and vital stats.

### 2.2 m59_lifecycle.py (Process Management)
*   **Role:** Manages the "Always-On" connection to the game.
*   **Mechanism:** Implements an `InstanceManager` that uses a heartbeat check (`read_int(base_address)`) to detect if the game has closed. It automatically triggers a re-scan and identity handshake upon restart.

### 2.3 m59_bridge.py (Multi-Instance Coordination)
*   **Role:** Prevents conflicts when running multiple game clients.
*   **Mechanism:** Uses atomic file-locking in the `%TEMP%` directory. Each Companion instance "claims" a specific Game PID. This ensures that Dashboard A doesn't accidentally read memory from Game B.

### 2.4 m59_inventory.py (The PE-Parsing Scraper)
*   **Role:** The most robust memory-reading module in the suite.
*   **Mechanism:** 
    *   **PE Header Parsing:** Manually traverses the game's Portable Executable (PE) export table in memory.
    *   **Signature Scanning:** Scans for specific machine code (Opcodes like `0xB8` for `mov eax`) to find object pointers.
    *   **Safety:** 100% ASLR-safe; it rediscovers the "Player" and "Resource Table" pointers every time it connects.

### 2.5 m59_wholist.py (Frida Memory Polling)
*   **Role:** Real-time monitoring of players and their alignment status.
*   **Mechanism:** Injects a Frida script that dynamically resolves `GetPlayerInfo` and `LookupRsc` hostnames. It traverses the game's linked list of active users and decodes alignment flags (Murderer, Outlaw, Staff).

### 2.6 m59_vault.py (UI-Based Automation)
*   **Role:** Scans the remote vault storage.
*   **Mechanism:** Uses Windows GUI messages (`LB_GETTEXT`) to read data directly from the game's ListBox controls.
*   **Self-Healing:** By reading the UI instead of memory, it is immune to nearly all game code changes. It simulates mouse clicks on rows to force the game server to send item quantities.

### 2.7 m59_gps.py & m59_pathfinder.py (Navigation Engine)
*   **Role:** World-wide pathfinding and navigation HUD.
*   **Mechanism:** 
    *   **Dijkstra's Algorithm:** Uses a weighted graph of the game world to find the fastest route.
    *   **8-Point Navigation:** Translates 2D coordinates into a Cardinal HUD (e.g., "North-West ↖").
    *   **Proximity Logic:** Intelligently picks the closest door or transition point based on the player's current entry coordinates.

### 2.8 m59_scraper.py (UI/Memory Hybrid)
*   **Role:** Handles character identity and skill/spell knowledge.
*   **Mechanism:** 
    *   **Handshake:** Triggers the in-game "Bio" window to capture the character's name via UI automation.
    *   **Tab Dance:** Automatically cycles between the game's UI tabs (Spells/Skills/Stats) to refresh internal buffers, then scrapes the results.

### 2.9 m59_logging.py & m59_utils.py
*   **Role:** Standardized logging and shared helper functions.
*   **Key Logic:** `m59_utils` handles `resource_path` for bundled assets and common Regex patterns for parsing chat logs.

---

## 3. Data Extraction Hierarchy
The companion uses three distinct "Tiers" of data extraction, ordered by stability:

1.  **Tier 1: Windows GUI Messages (Most Stable)**
    *   Used for: Vault, Chat Logs, Identity, Stats.
    *   *Why:* Survives almost any code change because it uses the OS-level UI controls.
2.  **Tier 2: Export Parsing (Highly Stable)**
    *   Used for: Inventory, Player Pointers.
    *   *Why:* Uses the game's own internal "Table of Contents" to find addresses.
3.  **Tier 3: Frida Injection (Stable)**
    *   Used for: Wholist alignment flags.
    *   *Why:* Allows running native code inside the game process for complex list traversal.

---

## 4. Maintenance Guide for Future Rebuilds
If the game is patched and a feature breaks:
*   **If Inventory breaks:** Check the opcode patterns in `m59_inventory.py`. The compiler may have changed how it handles the `mov` instruction.
*   **If Wholist breaks:** Check the `offset = 0x2A89A0` in `m59_wholist.py`. This is the single "hardest" offset in the project and the most likely to shift.
*   **If UI scraping fails:** The game likely changed a Control ID (e.g., Chat input is no longer `1001`). Use a tool like "WinSpy++" to find the new ID.
