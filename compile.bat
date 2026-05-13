@echo off
setlocal enabledelayedexpansion

:: M59 Companion - Compilation Script
:: This script builds the EXE using PyInstaller and includes necessary data files.

:: 1. Extract Current Version
if not exist VERSION (
    echo [ERROR] VERSION file not found.
    pause
    exit /b 1
)
set /p APP_VERSION=<VERSION
echo ==========================================
echo   Building M59 Companion %APP_VERSION%
echo ==========================================

:: 2. Setup Directories
if not exist dist mkdir dist

:: 3. Manage existing EXE in root
if exist M59Companion.exe (
    echo Moving existing M59Companion.exe to dist folder...
    move /y M59Companion.exe dist\M59Companion-old.exe
)

:: 4. Run PyInstaller
:: --onefile: Bundle everything into a single EXE
:: --noconsole: Hide the terminal window (it's a GUI app)
:: --add-data: Include non-python files (Syntax: source;dest)
:: --name: Specify the output filename
echo.
echo Running PyInstaller...
python -m PyInstaller --onefile --noconsole ^
    --add-data "VERSION;." ^
    --add-data "m59_data.json;." ^
    --add-data "moblist.csv;." ^
    --add-data "config.json;." ^
    --name "M59Companion-%APP_VERSION%" ^
    main.py

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Build complete.
    echo Output: dist\M59Companion-%APP_VERSION%.exe
    
    :: Optional: Cleanup build artifacts
    echo Cleaning up build artifacts...
    rmdir /s /q build
    del /q "M59Companion-%APP_VERSION%.spec"
) else (
    echo.
    echo [ERROR] PyInstaller build failed.
)

echo ==========================================
pause
endlocal
