#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"
UVICORN="$VENV/bin/uvicorn"

if [ ! -x "$PY" ]; then
  echo "Creation de l'environnement virtuel backend..."
  python3 -m venv "$VENV"
fi
if [ ! -x "$UVICORN" ]; then
  echo "Installation des dependances backend..."
  "$PY" -m pip install -r "$BACKEND/requirements.txt"
fi
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "Installation des dependances frontend..."
  (cd "$FRONTEND" && npm install)
fi

BACKEND_CMD="export T3D_CONFIG_DIR='.devdata/config'; export T3D_STORAGE_DIR='.devdata/storage'; export T3D_OPEN_MODE='local'; exec '$UVICORN' app.main:app --reload --port 8000"
FRONTEND_CMD="cd '$FRONTEND' && exec npm run dev"

open_terminal() {
  local name="$1"
  local command="$2"
  if [ "$(uname -s)" = "Darwin" ]; then
    osascript -e "tell application \"Terminal\" to do script \"$command\""
    return 0
  fi
  if command -v gnome-terminal >/dev/null 2>&1; then
    gnome-terminal --title="PolyKeep $name" -- bash -lc "$command; exec \${SHELL:-bash}"
    return 0
  fi
  if command -v konsole >/dev/null 2>&1; then
    konsole --hold --title="PolyKeep $name" -e bash -lc "$command"
    return 0
  fi
  if command -v xterm >/dev/null 2>&1; then
    xterm -title "PolyKeep $name" -e bash -lc "$command; exec \${SHELL:-bash}"
    return 0
  fi
  return 1
}

if ! open_terminal "Backend" "$BACKEND_CMD"; then
  echo "Aucun emulateur de terminal detecte, lancement en arriere-plan (logs dans /tmp) :"
  (cd "$BACKEND" && bash -lc "$BACKEND_CMD" > /tmp/polykeep-backend.log 2>&1) &
fi
if ! open_terminal "Frontend" "$FRONTEND_CMD"; then
  (cd "$FRONTEND" && bash -lc "$FRONTEND_CMD" > /tmp/polykeep-frontend.log 2>&1) &
fi

echo ""
echo "Backend  : http://localhost:8000"
echo "Frontend : http://localhost:5173"