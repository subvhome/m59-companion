@echo off
set REPO_URL=https://github.com/subvhome/m59-companion.git
set DEST_DIR=m59-companion

echo =========================================
echo   M59 Companion Installer (Windows)
echo =========================================

:: 1. Check for winget
where winget >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] 'winget' (Windows Package Manager) is missing.
    echo Please install it from the Microsoft Store or here: https://aka.ms/getwinget
    pause
    exit /b
)

:: 2. Check/Install Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Git is missing. Attempting to install via winget...
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Automatic Git installation failed. 
        echo Try running this script as Administrator.
        pause
        exit /b
    )
    echo [SUCCESS] Git installed. 
    echo PLEASE RESTART YOUR TERMINAL and run this script again.
    pause
    exit /b
)

:: 3. Check/Install Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Python is missing. Attempting to install via winget...
    winget install --id Python.Python.3.12 -e --source winget --accept-source-agreements --accept-package-agreements
    if %errorlevel% neq 0 (
        echo [ERROR] Automatic Python installation failed.
        echo Try running this script as Administrator.
        pause
        exit /b
    )
    echo [SUCCESS] Python installed.
    echo PLEASE RESTART YOUR TERMINAL and run this script again.
    pause
    exit /b
)

:: 4. Clone or Update
if exist %DEST_DIR% (
    echo [INFO] Updating existing installation in %DEST_DIR%...
    cd %DEST_DIR%
    git pull
) else (
    echo [INFO] Cloning repository to %DEST_DIR%...
    git clone %REPO_URL% %DEST_DIR%
    cd %DEST_DIR%
)

:: 5. Setup Virtual Environment
echo [INFO] Setting up virtual environment...
python -m venv venv
call venv\Scripts\activate

:: 6. Install requirements
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
