@echo off
set REPO_URL=https://github.com/subvhome/m59-companion.git
set DEST_DIR=m59-companion

echo =========================================
echo   M59 Companion Installer (Windows)
echo =========================================

:: Check for Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed.
    echo Please download and install Git from: https://git-scm.com/download/win
    echo After installing, please restart this script.
    pause
    exit /b
)

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed.
    echo Please download and install Python 3.10+ from: https://www.python.org/downloads/
    echo NOTE: During installation, make sure to check "Add Python to PATH".
    echo After installing, please restart this script.
    pause
    exit /b
)

:: Clone or Update
if exist %DEST_DIR% (
    echo [INFO] Updating existing installation in %DEST_DIR%...
    cd %DEST_DIR%
    git pull
) else (
    echo [INFO] Cloning repository to %DEST_DIR%...
    git clone %REPO_URL% %DEST_DIR%
    cd %DEST_DIR%
)

:: Setup Virtual Environment
echo [INFO] Setting up virtual environment...
python -m venv venv
call venv\Scripts\activate

:: Install requirements
echo [INFO] Installing dependencies (this may take a minute)...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo =========================================
echo   Installation Complete!
echo =========================================
echo.
echo To run the M59 Companion:
echo   1. cd %DEST_DIR%
echo   2. venv\Scripts\activate
echo   3. python main.py
echo.
pause
