@echo off
setlocal enabledelayedexpansion

:: M59 Companion - Git Push and Versioning Tool
:: This script manages the VERSION file and automates the Git workflow.

:: 1. Extract Current Version from VERSION file
if not exist VERSION (
    echo v0.58> VERSION
)
set /p CURRENT_VERSION=<VERSION

if "%CURRENT_VERSION%"=="" (
    echo [ERROR] Could not read from VERSION file.
    pause
    exit /b 1
)

echo ==========================================
echo   M59 Companion Version Manager
echo ==========================================
echo Current Version: %CURRENT_VERSION%

:: 2. Calculate Default Next Version (e.g., v0.58 -> v0.59)
for /f "tokens=1,2 delims=." %%A in ("%CURRENT_VERSION%") do (
    set "prefix=%%A"
    set "last_num=%%B"
)

:: Strip leading zero to avoid octal math errors in Batch
set "last_num_clean=%last_num%"
if "%last_num:~0,1%"=="0" if "%last_num%" neq "0" set "last_num_clean=%last_num:~1%"

set /a next_num_calc=%last_num_clean% + 1

if %next_num_calc% LSS 10 (
    set "DEFAULT_NEXT=%prefix%.0%next_num_calc%"
) else (
    set "DEFAULT_NEXT=%prefix%.%next_num_calc%"
)

:: 3. User Prompts for Versioning
echo.
set /p "USER_VER=Enter target version [%DEFAULT_NEXT%]: "
if "%USER_VER%"=="" (
    set "FINAL_VER=%DEFAULT_NEXT%"
) else (
    set "FINAL_VER=%USER_VER%"
)

:: 4. User Prompt for Commit Message
echo.
set "DEFAULT_MSG=Bump version to %FINAL_VER%"
set /p "USER_MSG=Enter commit message [%DEFAULT_MSG%]: "
if "%USER_MSG%"=="" (
    set "FINAL_MSG=%DEFAULT_MSG%"
) else (
    set "FINAL_MSG=%USER_MSG%"
)

:: 5. Update VERSION file (Surgical write to avoid trailing spaces)
<nul set /p="%FINAL_VER%"> VERSION

:: 6. Git Automation
echo.
echo ------------------------------------------
echo   Staging, Committing and Pushing...
echo ------------------------------------------
git add .
git commit -m "%FINAL_MSG%"
git push

if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] Pushed %FINAL_VER% to GitHub.
) else (
    echo.
    echo [WARNING] Git push failed. Check your connection or credentials.
)

echo ==========================================
pause
endlocal
