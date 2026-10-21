#!/usr/bin/env bash
# Launch Google Chrome for the chrome-devtools MCP server (.mcp.json).
# When Claude Code runs inside snap-packaged VS Code, the snap's GTK/GIO/
# gsettings paths leak into child processes and Chrome aborts on start
# ("Settings schema ... does not contain a key named 'antialiasing'").
# Restore the host desktop environment, then exec the real Chrome.
set -euo pipefail

if [[ -n "${SNAP:-}" ]]; then
  [[ -n "${XDG_DATA_DIRS_VSCODE_SNAP_ORIG:-}" ]] && export XDG_DATA_DIRS="$XDG_DATA_DIRS_VSCODE_SNAP_ORIG"
  [[ -n "${XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG:-}" ]] && export XDG_CONFIG_DIRS="$XDG_CONFIG_DIRS_VSCODE_SNAP_ORIG"
  unset GSETTINGS_SCHEMA_DIR GTK_PATH GTK_EXE_PREFIX GTK_IM_MODULE_FILE GIO_MODULE_DIR \
        GDK_PIXBUF_MODULE_FILE GDK_PIXBUF_MODULEDIR LOCPATH GTK_MODULES \
        GIO_LAUNCHED_DESKTOP_FILE GIO_LAUNCHED_DESKTOP_FILE_PID
  while IFS='=' read -r name _; do
    [[ "$name" == SNAP* ]] && unset "$name"
  done < <(env)
fi

exec "${CHROME_BIN:-/usr/bin/google-chrome-stable}" "$@"
