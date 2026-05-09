@echo off
set REPO_URL=https://github.com/subvhome/m59-companion.git
set DEST_DIR=m59-companion

echo =========================================
echo   M59 Companion Installer (Windows)
echo =========================================

:: 1. Check for winget
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 'winget' is missing. Please install it from the Microsoft Store. [cite: 1]
    pause
    exit /b
)

:: 2. Check/Install Git (Elevated)
git --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Git is missing. Attempting elevated installation...
    powershell -Command "Start-Process winget -ArgumentList 'install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements' -Verb RunAs -Wait" 
    if %errorlevel% neq 0 (
        echo [ERROR] Git installation failed. 
        pause
        exit /b
    )
    echo [SUCCESS] Git installed. PLEASE RESTART YOUR TERMINAL. 
    pause
    exit /b
)

:: 3. Check/Install Python and verify version
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Python is missing. Attempting elevated installation... 
    powershell -Command "Start-Process winget -ArgumentList 'install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements' -Verb RunAs -Wait"
    if %errorlevel% neq 0 (
        echo [ERROR] Python installation failed.
        pause
        exit /b
    )
    echo [SUCCESS] Python installed. PLEASE RESTART YOUR TERMINAL. [cite: 4]
    pause
    exit /b
)

:: 4. Clone or Update [cite: 5]
if exist %DEST_DIR% (
    echo [INFO] Updating existing installation...
    cd %DEST_DIR%
    git pull
) else (
    echo [INFO] Cloning repository...
    git clone %REPO_URL% %DEST_DIR%
    cd %DEST_DIR%
)

:: 5. Setup Virtual Environment
echo [INFO] Setting up virtual environment...
python -m venv venv
call venv\Scripts\activate

:: 6. Install requirements (including pymem and pywin32)
echo [INFO] Installing dependencies...
python -m pip install --upgrade pip
pip install pymem pywin32 
:: Also install from requirements.txt if it exists
if exist requirements.txt (
    pip install -r requirements.txt
)

echo =========================================
echo   Installation Complete! [cite: 6]
echo =========================================
echo To run: python main.py [cite: 6]
pause
