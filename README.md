# M59 Companion

A powerful, real-time utility for **Meridian 59** players. Track your progress, monitor your chat, and analyze your school progression with ease.

![Version](https://img.shields.io/badge/version-v0.38-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)

---

## 📥 Download (Latest Release)

For most users, simply download the pre-compiled executable:

👉 **[Download M59Companion.exe](https://github.com/subvhome/m59-companion/releases)**

---

## ✨ Key Features

### 📊 Real-Time Dashboard
*   **Live Vital Monitoring:** View your **HP, Mana, and Vigor** directly in the companion window.
*   **Identity Detection:** Automatically captures your character name so you know exactly which session is being logged.
*   **Top-Most Window:** The companion stays pinned on top of your game client for constant visibility.

### 🎯 Skill & Spell Tracker (Improves)
*   **Automatic Detection:** Captures every "You have improved..." message instantly.
*   **Improvement History:** See exactly how many times you've gained in a specific skill during your current session.
*   **Time Deltas:** Tracks the **time elapsed** between improvements, helping you optimize your training speed and detect "droughts."
*   **Smart Formatting:** Automatically cleans and formats skill names (e.g., `axe wielding` becomes `Axe Wielding`) for a professional look.

### 🎓 School Progression Engine
*   **Knowledge Sync:** With one click, the app "scans" your Spells and Skills tabs in-game to build a local cache of your percentages.
*   **Unlock Predictor:** Uses advanced formulas (taking into account your **Intellect** and server settings) to calculate exactly how much more training you need to unlock the next level of a school.
*   **Sum-of-Top-3 Logic:** Automatically identifies your three highest skills in a school level to give you an accurate "Progress %" toward your next unlock.

### 📝 Integrated Chat & System Logs
*   **Live Chat Viewer:** Read your game chat in a clean, scrollable window with "Live Scroll" support.
*   **Historical Browsing:** All sessions are saved as `.log` files in the `/logs` directory. Review past adventures or combat logs without leaving the app.
*   **Log Management:** Right-click any log in the list to quickly delete old or unnecessary files.
*   **System Console:** A dedicated tab for technical events, showing you exactly when the app connects to the game or syncs data.

---

## 🛠️ How It Works

M59 Companion uses a hybrid approach to provide its features:
1.  **Window Interaction:** It communicates with the Meridian 59 window components to "scrape" text from the chat and listboxes.
2.  **Memory Reading:** It uses a secure, read-only memory hook to retrieve your HP/MP/Vigor and specific skill percentages for maximum accuracy.
3.  **Local Intelligence:** All calculations are performed locally using data from `m59_data.json`, ensuring your data stays private and fast.

---

## 📋 Prerequisites (For CLI/Source Install)
...

Before installing from source, ensure you have the following:

### 🪟 Windows
* **Windows 10/11** (Includes `winget` for automated setup)

### 🐧 Linux
* **Python 3.10+** and **Tkinter**
    ```bash
    sudo apt install python3-tk  # Ubuntu/Debian
    ```

---

## 🛠️ Installation (Source/CLI)

### 🪟 Windows
Run this in **PowerShell** to automatically set up the project (installs Python/Git if needed):
```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/subvhome/m59-companion/main/install.bat" -OutFile "install.bat"; .\install.bat
```

### 🐧 Linux
Run this in your **Terminal**:
```bash
curl -sSL https://raw.githubusercontent.com/subvhome/m59-companion/main/install.sh | bash
```

---

## 🏗️ Development & Compilation

To compile your own standalone executable on Windows:

1. **Activate Environment:**
   ```powershell
   .\venv\Scripts\activate
   ```
2. **Install Build Tools:**
   ```powershell
   pip install pyinstaller
   ```
3. **Run Compilation:**
   ```powershell
   pyinstaller --noconsole --onefile --clean --name "M59Companion" --add-data "config.json;." --add-data "m59_data.json;." --add-data "moblist.csv;." main.py
   ```
   The finished EXE will be in the `dist/` folder.

---

## 📜 License
This project is licensed under the MIT License.

---
*Created for the Meridian 59 community.*
