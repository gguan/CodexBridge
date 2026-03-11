#!/usr/bin/env bash
set -euo pipefail

PYTHON_EXE="${1:-.venv/bin/python}"

if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "Python executable not found: $PYTHON_EXE" >&2
  exit 1
fi

"$PYTHON_EXE" -m pip install -e ".[build]"
"$PYTHON_EXE" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name "CodexBridgeGUI" \
  --hidden-import "tkinter" \
  codexbridge_gui.py

echo "Build completed. Output: dist/CodexBridgeGUI.app"

