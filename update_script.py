#!/bin/bash

# 1. Try to find the latest version from git tags
# If no tags exist, it defaults to v0.5
LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
if [ -z "$LATEST_TAG" ]; then
    LATEST_TAG="v0.5"
fi

# 2. Calculate the suggested next version (e.g., v0.5 -> v0.6)
BASE_VERSION=$(echo $LATEST_TAG | cut -d. -f1)
MINOR_VERSION=$(echo $LATEST_TAG | cut -d. -f2)
SUGGESTED_VERSION="$BASE_VERSION.$((MINOR_VERSION + 1))"

# 3. Prompt User for Version Number
read -p "Enter version number (Default: $SUGGESTED_VERSION): " USER_VERSION
USER_VERSION=${USER_VERSION:-$SUGGESTED_VERSION}

# 4. Prompt User for Commit Message
read -p "Enter commit message: " COMMIT_MSG
if [ -z "$COMMIT_MSG" ]; then
    COMMIT_MSG="Updates for version $USER_VERSION"
fi

echo ">>> Proceeding with Version: $USER_VERSION"
echo ">>> Message: $COMMIT_MSG"

# 5. Git Operations
git add .
git commit -m "[$USER_VERSION] $COMMIT_MSG"
git tag -a "$USER_VERSION" -m "Version $USER_VERSION"
git push origin main --tags

echo "---------------------------------------"
echo "Project successfully pushed and tagged!"
echo "---------------------------------------"
