#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Remove macOS quarantine flag (blocks execution when unzipped from Downloads)
xattr -dr com.apple.quarantine "$DIR" 2>/dev/null

echo "Starting CS Fitness..."
python3 -m pip install -r requirements.txt -q --user 2>/dev/null || true
python3 app.py
