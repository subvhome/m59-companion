#!/bin/bash

# M59 Companion Update Script
# Usage: ./update_script.sh [new_version] "[commit_message]"

NEW_VERSION=$1
CUSTOM_MSG=$2

if [ -z "$NEW_VERSION" ]; then
    echo "Usage: ./update_script.sh vX.XX \"Optional commit message\""
    exit 1
fi

# Use custom message if provided, otherwise default to version bump message
COMMIT_MSG=${CUSTOM_MSG:-"Bump version to $NEW_VERSION"}

echo "Updating M59 Companion to $NEW_VERSION..."

# 1. Update the VERSION variable in main.py
sed -i "s/VERSION = \".*\"/VERSION = \"$NEW_VERSION\"/" main.py

if [ $? -eq 0 ]; then
    echo "Success: Version updated to $NEW_VERSION in main.py"
else
    echo "Error: Failed to update version."
    exit 1
fi

# 2. Git Automation
echo "Committing and pushing to Git..."
git add .
git commit -m "$COMMIT_MSG"
git push

if [ $? -eq 0 ]; then
    echo "Success: Pushed $NEW_VERSION to repository with message: '$COMMIT_MSG'"
else
    echo "Warning: Git push failed. Please check your connection or credentials."
fi
