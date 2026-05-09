#!/bin/bash

# M59 Companion Update Script
# Usage: ./update_script.sh [new_version] "[commit_message]"

# 1. Extract Current Version from main.py
# This looks for the VERSION = "..." line specifically
CURRENT_VERSION=$(grep -E '^VERSION = ".*"' main.py | cut -d'"' -f2)

if [ -z "$CURRENT_VERSION" ]; then
    echo "[ERROR] Could not find VERSION string in main.py"
    exit 1
fi

echo "Current Version: $CURRENT_VERSION"

# 2. Determine Next Version
if [ -z "$1" ] || [ "$1" == "" ]; then
    # Auto-increment logic (handles v0.38 -> v0.39)
    # Strip the 'v', increment the number, put the 'v' back
    VERSION_NUM=$(echo $CURRENT_VERSION | sed 's/^v//')
    BASE_VERSION=$(echo $VERSION_NUM | sed 's/\.[0-9]*$//')
    LAST_NUM=$(echo $VERSION_NUM | grep -o '[0-9]*$')
    NEXT_NUM=$((LAST_NUM + 1))
    NEW_VERSION="v${BASE_VERSION}.${NEXT_NUM}"
    echo "No version specified. Auto-incrementing to: $NEW_VERSION"
else
    NEW_VERSION=$1
    echo "Using specified version: $NEW_VERSION"
fi

# 3. Handle Commit Message
# We use "$2" with quotes to ensure spaces and special chars (&) are preserved
CUSTOM_MSG="$2"
COMMIT_MSG=${CUSTOM_MSG:-"Bump version to $NEW_VERSION"}

echo "Updating M59 Companion to $NEW_VERSION..."

# 4. Update the VERSION variable in main.py
# We use a specific match to avoid accidental replacements elsewhere
sed -i "s/^VERSION = \"$CURRENT_VERSION\"/VERSION = \"$NEW_VERSION\"/" main.py

if [ $? -eq 0 ]; then
    echo "Success: Version updated in main.py"
else
    echo "Error: Failed to update version in main.py"
    exit 1
fi

# 5. Git Automation
echo "Committing and pushing to Git..."
git add .
# Using quotes around $COMMIT_MSG is vital here
git commit -m "$COMMIT_MSG"
git push

if [ $? -eq 0 ]; then
    echo "Success: Pushed $NEW_VERSION to repository."
else
    echo "Warning: Git push failed. Please check your connection or credentials."
fi
