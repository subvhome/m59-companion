# M59 Companion

A powerful, real-time utility for **Meridian 59** players. Track your progress, monitor your chat, and analyze your school progression with ease.

![Version](https://img.shields.io/badge/version-v0.38-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)

---

## 🚀 Key Features

### 📊 Dashboard
* **Real-time Stats:** Monitor HP, MP, and Vigor directly from the game window.
* **Live Improves Tracker:** Automatically captures "You have improved in the art of..." messages.
* **Skill Formatting:** Correctly formats skill names (e.g., `Hunter's Aim`, `Hand-To-Hand`).
* **Time Delta:** See exactly how long it's been since your last skill gain.
* **School Progression:** Automatically calculates sum-of-top-3 and remaining points for school unlocks.

### 📝 Chat Logs
* **Integrated Viewer:** Review your current session or historical logs without leaving the app.
* **Date-Based History:** Browsing previous logs organized by date/time.
* **Live Scroll:** Toggle live updates to follow the action in real-time.
* **Log Management:** Right-click to delete old logs and keep your workspace clean.

### 🛠 Console & System
* **Logical Logs:** Dedicated console tab with terminal styling for system events.
* **Testing Mode:** Toggle a "Relaxed Filter" in settings to test improvements via private messages.
* **Auto-Sync:** Fingerprinting system to resume logs across different sessions seamlessly.

---

## 📥 Installation

Choose the installation method for your operating system below. Replace `YOUR_USER/YOUR_REPO` with the actual path to your repository.

### 🪟 Windows
**Option 1: Quick Install (Standalone EXE)**
1. Download `M59Companion.exe` from the [Releases](https://github.com/YOUR_USER/YOUR_REPO/releases) page.
2. Run the EXE. (Click "Run Anyway" if prompted by Windows Defender).

**Option 2: CLI Install (Source)**
Run this in **Command Prompt** or **PowerShell**:
```batch
curl -sSL https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/install.bat -o install.bat && install.bat
```

### 🍎 macOS
Run this in your **Terminal**:
```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/install.sh | bash
```

### 🐧 Linux
Run this in your **Terminal**:
```bash
curl -sSL https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/install.sh | bash
```

---

## 🛠️ Development & Compilation

### Requirements
* Python 3.8+
* `pip install -r requirements.txt`

### Compiling to EXE (Windows)
To create a standalone executable:
```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --add-data "config.json;." main.py
```

### Updating Version & Repository
Use the provided update script to bump the version and push changes:
```bash
./update_script.sh v0.39 "Added new features"
```

---

## 🤝 Contributing
Contributions are welcome! Please submit a Pull Request or open an issue for bugs and feature requests.

---

## 📜 License
This project is licensed under the MIT License.

---
*Created for the Meridian 59 community.*
