# M59 Companion

A powerful, real-time utility for **Meridian 59** players. Track your progress, monitor your chat, and analyze your school progression with ease.

![Version](https://img.shields.io/badge/version-v0.38-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)

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

---

## 📋 Prerequisites

Before installing, ensure you have the following installed on your system:

### 🪟 Windows (Recommended)
* **Python 3.10+**: [Download from Python.org](https://www.python.org/downloads/windows/). 
    * *Important: Check "Add Python to PATH" during installation.*
* **Git**: [Download from Git-scm.com](https://git-scm.com/download/win).
* **Meridian 59**: The application must be running to track stats and improves.

### 🐧 Linux
* **Python 3.10+** and **pip**
* **Git**
* **Tkinter**: Usually needs to be installed via your package manager:
    ```bash
    sudo apt install python3-tk  # Ubuntu/Debian
    sudo dnf install python3-tkinter # Fedora
    ```

---

## 📥 Installation

### 🪟 Windows
1. **Open PowerShell** as Administrator.
2. **Check Prerequisites:**
   Ensure Python and Git are installed by running:
   ```powershell
   python --version; git --version
   ```
   *If either fails, download them from the links in the Prerequisites section above.*

3. **Run the Installer:**
   Copy and paste this entire block into PowerShell:
   ```powershell
   Invoke-WebRequest -Uri "https://raw.githubusercontent.com/subvhome/m59-companion/main/install.bat" -OutFile "install.bat"; .\install.bat
   ```

### 🐧 Linux
Run this in your **Terminal**:
```bash
curl -sSL https://raw.githubusercontent.com/subvhome/m59-companion/main/install.sh | bash
```

---

## 🛠️ Manual Installation (Developers)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/subvhome/m59-companion.git
   cd m59-companion
   ```
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux
   venv\Scripts\activate     # Windows
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *Note: On Windows, this will install `pywin32` and `pymem` which are required for memory reading and window interaction.*

---

## 📜 License
This project is licensed under the MIT License.

---
*Created for the Meridian 59 community.*
