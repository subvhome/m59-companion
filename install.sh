#!/bin/bash

# M59 Companion Installer (macOS/Linux)
# Usage: curl -sSL https://raw.githubusercontent.com/subvhome/m59-companion/main/install.sh | bash

REPO_URL="https://github.com/subvhome/m59-companion.git"
DEST_DIR="m59-companion"

echo "========================================="
echo "   M59 Companion Installer (Linux/macOS)"
echo "========================================="

# Check for Git
if ! command -v git &> /dev/null; then
    echo "[ERROR] git is not installed."
    echo "Please install git (e.g., 'sudo apt install git' on Ubuntu/Debian)."
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed."
    echo "Please install Python 3.10+ (e.g., 'sudo apt install python3 python3-venv' on Ubuntu/Debian)."
    exit 1
fi

# Clone or Update
if [ -d "$DEST_DIR" ]; then
    echo "[INFO] Updating existing installation in $DEST_DIR..."
    cd "$DEST_DIR" && git pull
else
    echo "[INFO] Cloning repository to $DEST_DIR..."
    git clone "$REPO_URL" "$DEST_DIR"
    cd "$DEST_DIR"
fi

# Setup Virtual Environment
echo "[INFO] Setting up virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install requirements
echo "[INFO] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "========================================="
echo "   Installation Complete!"
echo "========================================="
echo "To run the app:"
echo "  cd $DEST_DIR"
echo "  source venv/bin/activate"
echo "  python3 main.py"
