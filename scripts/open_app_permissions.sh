#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "SwitchType permission setup"
echo
echo "Grant permissions to the process that runs SwitchType, not DoubaoIme."
echo
echo "1. In Privacy & Security > Microphone, enable Codex, Terminal, iTerm, Cursor,"
echo "   SwitchType, SwitchTypeDoctor, or SwitchTypeDoubaoShadow if they appear."
echo "2. In Privacy & Security > Accessibility, enable the same launcher/process names."
echo "   This is needed for the hotkey listener and focused-text capture."
echo "3. Return here and run:"
echo
echo "   make app-request-permissions"
echo "   make package"
echo "   make app-request-permissions-packaged"
echo "   make app-doctor"
echo "   make app-focused-text-doctor"
echo "   SWITCHTYPE_HOTWORDS_CONFIG=\"\${SWITCHTYPE_HOTWORDS_CONFIG:-$ROOT_DIR/bench/config/hotwords.example.json}\" \\"
echo "     app/SwitchType/.build/debug/SwitchTypeDoctor --json"
echo

if [[ "${SWITCHTYPE_OPEN_PERMISSION_PANES:-1}" == "0" ]]; then
  echo "Skipping System Settings launch because SWITCHTYPE_OPEN_PERMISSION_PANES=0."
  exit 0
fi

open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
