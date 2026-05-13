@echo off
setlocal enabledelayedexpansion

:: M59 Companion Update Script for Windows
:: Usage: update_script.bat [new_version] "[commit_message]"

:: 1. Extract Current Version from main.py
set "CURRENT_VERSION="
for /f "tokens=2 delims==" %%A in ('findstr /r "^VERSION =" main.py') do (
    set "line=%%A"
    :: Remove spaces and quotes
    set "line=!line: =!"
    set "line=!line:"=!"
    set "CURRENT_VERSION=!line!"
)

if "%CURRENT_VERSION%"=="" (
    echo [ERROR] Could not find VERSION string in main.py
    exit /b 1
)

echo Current Version: %CURRENT_VERSION%

:: 2. Determine Next Version
set "NEW_VERSION=%~1"
if "%NEW_VERSION%"=="" (
    :: Auto-increment logic (e.g., v0.57 -> v0.58)
    :: This expects a format like v0.57
    for /f "tokens=1,2 delims=." %%A in ("%CURRENT_VERSION%") do (
        set "prefix=%%A"
        set "last_num=%%B"
    )
    set /a next_num=last_num + 1
    :: Handle leading zero padding if necessary (e.g., .09 -> .10)
    if !next_num! LSS 10 (
        set "NEW_VERSION=!prefix!.0!next_num!"
    ) else (
        set "NEW_VERSION=!prefix!.!next_num!"
    )
    echo No version specified. Auto-incrementing to: !NEW_VERSION!
) else (
    echo Using specified version: %NEW_VERSION%
)

:: 3. Handle Commit Message
set "CUSTOM_MSG=%~2"
if "%CUSTOM_MSG%"=="" (
    set "COMMIT_MSG=Bump version to !NEW_VERSION!"
) else (
    set "COMMIT_MSG=%CUSTOM_MSG%"
)

echo Updating M59 Companion to !NEW_VERSION!...

:: 4. Update the VERSION variable in main.py
:: We use powershell for a reliable in-place replacement
powershell -Command "(Get-Content main.py) -replace '^VERSION = \".*\"', 'VERSION = \"!NEW_VERSION!\"' | Set-Content main.py"

if %ERRORLEVEL% equ 0 (
    echo Success: Version updated in main.py
) else (
    echo Error: Failed to update version in main.py
    exit /b 1
)

:: 5. Git Automation
echo Committing and pushing to Git...
git add .
:: Use !COMMIT_MSG! to handle quotes/spaces correctly in the command
git commit -m "!COMMIT_MSG!"
git push

if %ERRORLEVEL% equ 0 (
    echo Success: Pushed !NEW_VERSION! to repository.
) else (
    echo Warning: Git push failed. Please check your connection or credentials.
)

endlocal
