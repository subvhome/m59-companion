# M59 Companion

A lightweight, multi-instance companion tool for Meridian 59 that helps you track your character's progression and masters the "Knowledge Math" for you.

[**Download Latest Release (EXE)**](https://github.com/subvhome/m59-companion/raw/main/M59Companion.exe)

## Key Features

### 1. School Progression Tracker
*   **Target Calculation**: Automatically determines the exact % sum required to unlock your next school rank.
*   **Progress Monitoring**: Shows your current "Top 3" sum and exactly how many more points you need to advance.
*   **Smart Calibration**: Factors in your Intellect and "Generalization Penalty" (how many other schools you've trained) to give you accurate goals.

### 2. Live Gain Monitor (Improves)
*   **Real-time Tracking**: Detects "You have improved..." messages instantly.
*   **Gain Counters**: Tracks how many times each skill has improved during your current session.
*   **Efficiency Timer**: Shows the time elapsed between your last two gains, helping you monitor your "cast bonus" efficiency.

### 3. Connection Manager
*   **Multi-Instance Support**: Easily switch between different running `Meridian.exe` windows.
*   **Identity Mapping**: Remembers individual character stats and knowledge sets even when running multiple game sessions simultaneously.

### 4. Chat Log Explorer
*   **Session Archiving**: Automatically saves all game text into timestamped `.log` files.
*   **Live Viewer**: Read and search through your current and historical game logs without leaving the companion app.

## Installation

### Windows (One-Liner)
*Placeholder: Coming Soon*
```powershell
# [PowerShell command placeholder]
```

### Linux / Wine (One-Liner)
*Placeholder: Coming Soon*
```bash
# [Bash command placeholder]
```

---

## How it Works (Technical Details)

The M59 Companion interacts with the game through a combination of memory reading and UI scraping to ensure 100% accuracy without interfering with game performance.

### The Progression Engine
The tool uses the standard server advancement formula to calculate your `iNeed` (the sum of your top 3 spells/skills in a rank).
*   **Intellect Buffer**: The higher your Intellect, the lower your required % sum becomes.
*   **iPoints Calculation**: Every school rank you've already achieved adds a "Generalization Penalty," raising the requirement for your next unlock.
*   **Detection**: The tool identifies your current level by scanning your spellbook and prioritizes the lowest "unfinished" level to ensure you always know what to work on next.

### Data Capture
*   **Memory Hooks**: Uses `Pymem` to read core character stats directly from the game's memory.
*   **UI Scrapers**: Utilizes standard Windows API calls to read text from the game's ListBoxes and Chat components safely.
*   **Sync Logic**: The "Sync Now" feature performs a sequence of UI tab switches to refresh your character's internal knowledge base.
