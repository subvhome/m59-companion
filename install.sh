#!/bin/bash

# M59 Companion Installer (macOS/Linux)
# Usage: curl -sSL https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/install.sh | bash

REPO_URL="https://github.com/YOUR_USER/YOUR_REPO.git"
DEST_DIR="m59-companion"

echo "=== M59 Companion Installer ==="

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed."
    exit 1
fi

# Clone or Update
if [ -d "$DEST_DIR" ]; then
    echo "Updating existing installation..."
    cd "$DEST_DIR" && git pull
else
    echo "Cloning repository..."
    git clone "$REPO_URL" "$DEST_DIR"
    cd "$DEST_DIR"
fi

# Setup Virtual Environment
echo "Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Installation Complete ==="
echo "To run the app: cd $DEST_DIR && source venv/bin/activate && python3 main.py"
