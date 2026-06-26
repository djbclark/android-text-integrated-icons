#!/usr/bin/env bash
# Quick installer for launcher_icons.py
# Usage: ./install.sh   (will copy to ~/.local/bin)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$HOME/.local/bin/launcher_icons"

mkdir -p "$(dirname "$TARGET")"

echo "Installing launcher_icons to $TARGET"
cp "$SCRIPT_DIR/launcher_icons.py" "$TARGET"
chmod +x "$TARGET"

echo "Done."
echo
echo "Make sure ~/.local/bin is in your PATH:"
echo '  export PATH="$HOME/.local/bin:$PATH"'
echo
echo "You can now run: launcher_icons --help"
echo
echo "To install Pillow (if not on Termux):"
echo "  pip install --user Pillow"
