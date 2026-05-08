@echo off
set REPO_URL=https://github.com/YOUR_USER/YOUR_REPO.git
set DEST_DIR=m59-companion

echo === M59 Companion Installer (Windows) ===

:: Check for Git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Git is not installed. Please install Git from https://git-scm.com/
    pause
    exit /b
)

:: Check for Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: Python is not installed. Please install Python from https://www.python.org/
    pause
    exit /b
)

:: Clone or Update
if exist %DEST_DIR% (
    echo Updating existing installation...
    cd %DEST_DIR%
    git pull
) else (
    echo Cloning repository...
    git clone %REPO_URL% %DEST_DIR%
    cd %DEST_DIR%
)

:: Setup Virtual Environment
echo Setting up virtual environment...
python -m venv venv
call venv\Scripts\activate

:: Install requirements
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo === Installation Complete ===
echo To run the app:
echo cd %DEST_DIR%
echo venv\Scripts\activate
echo python main.py
pause
