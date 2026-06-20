#!/usr/bin/env bash
# ===========================================================================
# Arranca el MVP completo desde Git Bash: worker PowerFactory + backend + frontend.
# Uso:   ./run.sh            (abre 3 ventanas + el navegador)
#        ./run.sh --bg       (corre los 3 en segundo plano, logs en results/)
# ===========================================================================
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Node: si no está en el PATH (sesión vieja), usa la instalación de winget.
NODE_DIR="/c/Users/VM-PF/AppData/Local/Microsoft/WinGet/Packages/OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe/node-v24.16.0-win-x64"
command -v node >/dev/null 2>&1 || export PATH="$NODE_DIR:$PATH"

WROOT="$(cygpath -w "$ROOT")"

if [ "$1" == "--bg" ]; then
  echo "Levantando en segundo plano (logs en results/)..."
  ( cd "$ROOT"          && python pf_worker/worker.py            > results/_worker.log   2>&1 & )
  ( cd "$ROOT/backend"  && python -m uvicorn app.main:app --port 8000 > "$ROOT/results/_backend.log" 2>&1 & )
  ( cd "$ROOT/frontend" && npm run dev                          > "$ROOT/results/_frontend.log" 2>&1 & )
  echo "Worker + backend (:8000) + frontend (:3000) corriendo. Abre http://localhost:3000"
  exit 0
fi

# Modo por defecto: una ventana por proceso (para ver los logs).
NODE_WIN="$(cygpath -w "$NODE_DIR")"
cmd //c start "PF Worker"  cmd //k "cd /d $WROOT && python pf_worker\\worker.py"
cmd //c start "Backend"    cmd //k "cd /d $WROOT\\backend && python -m uvicorn app.main:app --port 8000"
cmd //c start "Frontend"   cmd //k "cd /d $WROOT\\frontend && set \"PATH=$NODE_WIN;%PATH%\" && npm run dev"

echo "3 ventanas abiertas (Worker / Backend / Frontend)."
echo "Esperando al frontend y abriendo el navegador..."
sleep 8
cmd //c start http://localhost:3000
