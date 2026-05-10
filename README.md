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

## 🚀 Key Features

### 📊 Dashboard
* **Real-time Stats:** Monitor HP, MP, and Vigor directly from the game window.
* **Live Improves Tracker:** Automatically captures "You have improved in the art of..." messages.
* **School Progression:** Automatically calculates sum-of-top-3 and remaining points for school unlocks.

### 📝 Chat Logs
* **Integrated Viewer:** Review your current session or historical logs.
* **Log Management:** Right-click to delete old logs and keep your workspace clean.

---

## 📋 Prerequisites (For CLI/Source Install)

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
