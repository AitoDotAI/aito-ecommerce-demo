#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env if present
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  source "$SCRIPT_DIR/.env"
  set +a
fi

# Ports: frontend on 8500 (user-facing), backend on 8501 (internal).
# Allocated by the cross-demo framework doc — see
# aito-demo-framework.md §2 "Port allocation". Don't reuse other
# demos' pairs.
PORT_FRONTEND=8500
PORT_BACKEND=8501

cmd_help() {
  cat <<EOF
Usage: ./do <command>

Common
  help              Show this help
  setup             uv sync + npm install
  dev               Start backend + frontend (http://localhost:${PORT_FRONTEND})
  backend-dev       Start FastAPI only (port ${PORT_BACKEND})
  frontend-dev      Start Next.js only (port ${PORT_FRONTEND}, proxies API to ${PORT_BACKEND})
  frontend-build    Build Next.js static export to frontend/out/
  stop              Stop all running dev servers
  restart           Stop then start dev servers
  demo              Open the demo in the default browser

Data
  generate-fixtures (Re)run data/generate_fixtures.py
  load-data         Upload schema + fixtures to Aito
  reset-data        Drop and reload all Aito tables
  clear-cache       Clear in-memory + Aito persistent prediction cache

Quality
  test              Run pytest
  aito-check        Sanity-check Aito queries against the loaded data
  verify <feature>  Run the adversary Playwright agent for one feature
  verify-demo       End-to-end demo-path check
  check             Pre-merge gate (test + fmt + aito-check)
  fmt               Format code

Frontend
  npm-install       Install frontend npm dependencies
  uv-sync           Sync Python dependencies
  typecheck         Run TypeScript type checking
  lint              Lint frontend code

Assets (require screenshots/inspect/ — see frontend/scripts/inspect-views.cjs)
  product-sheet     Compile docs/product-sheet/product-sheet.typ → PDF (requires typst)
  teaser            Render assets/teaser.html → assets/teaser.png via headless chromium

Each verb either runs immediately or prints the path of the script it
will run. New multi-step recipes live here, not in your shell history.
EOF
}

cmd_dev() {
  echo "Starting Predictive E-commerce"
  echo "  Backend:  http://localhost:${PORT_BACKEND} (internal)"
  echo "  Frontend: http://localhost:${PORT_FRONTEND} (open this)"
  echo ""

  cd "$SCRIPT_DIR"
  uv run uvicorn src.app:app --reload --port "$PORT_BACKEND" &
  BACKEND_PID=$!

  cd "$SCRIPT_DIR/frontend"
  npx next dev -p "$PORT_FRONTEND" &
  FRONTEND_PID=$!

  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM EXIT

  echo ""
  echo "  Both servers running. Press Ctrl+C to stop."
  wait
}

cmd_backend_dev() {
  echo "Starting Predictive E-commerce API on http://localhost:${PORT_BACKEND}"
  cd "$SCRIPT_DIR"
  uv run uvicorn src.app:app --reload --port "$PORT_BACKEND"
}

cmd_frontend_dev() {
  echo "Starting Next.js dev server on http://localhost:${PORT_FRONTEND}"
  echo "  API proxy → http://localhost:${PORT_BACKEND}"
  cd "$SCRIPT_DIR/frontend"
  npx next dev -p "$PORT_FRONTEND"
}

cmd_frontend_build() {
  echo "Building Next.js static export..."
  cd "$SCRIPT_DIR/frontend"
  npx next build
  echo "Built to frontend/out/ — ./do backend-dev will serve it."
}

cmd_demo() {
  local url="http://localhost:${PORT_FRONTEND}"
  if curl -s -o /dev/null "$url" 2>/dev/null; then
    echo "Opening $url"
    if command -v xdg-open &>/dev/null; then
      xdg-open "$url"
    elif command -v open &>/dev/null; then
      open "$url"
    else
      echo "Open manually: $url"
    fi
  else
    echo "Not running. Start with: ./do dev"
  fi
}

_kill_port() {
  local port="$1"
  if command -v fuser &>/dev/null; then
    fuser -k "${port}/tcp" 2>/dev/null || true
    return
  fi
  if command -v lsof &>/dev/null; then
    lsof -ti:"$port" 2>/dev/null | xargs -r kill 2>/dev/null || true
  fi
}

cmd_stop() {
  echo "Stopping dev servers..."
  pkill -f "uvicorn src.app" 2>/dev/null || true
  pkill -f "next dev.*-p ${PORT_FRONTEND}" 2>/dev/null || true
  pkill -f "next-server" 2>/dev/null || true
  _kill_port "${PORT_BACKEND}"
  _kill_port "${PORT_FRONTEND}"
  sleep 1
  echo "Stopped."
}

cmd_restart() {
  cmd_stop
  cmd_dev
}

# ── Data ────────────────────────────────────────────────────────────

cmd_generate_fixtures() {
  cd "$SCRIPT_DIR"
  if [[ ! -f data/generate_fixtures.py ]]; then
    echo "data/generate_fixtures.py not implemented yet (build-order step 2)."
    exit 1
  fi
  uv run python data/generate_fixtures.py
}

cmd_load_data() {
  cd "$SCRIPT_DIR"
  if [[ ! -f src/data_loader.py ]]; then
    echo "src/data_loader.py not implemented yet (build-order step 3)."
    exit 1
  fi
  uv run python -m src.data_loader "$@"
}

cmd_reset_data() {
  cd "$SCRIPT_DIR"
  if [[ ! -f src/data_loader.py ]]; then
    echo "src/data_loader.py not implemented yet (build-order step 3)."
    exit 1
  fi
  uv run python -m src.data_loader --reset "$@"
}

cmd_clear_cache() {
  echo "Clearing caches..."
  cd "$SCRIPT_DIR"
  uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src import cache as cache_mod
cfg = load_config()
client = AitoClient(cfg)
cache_mod.init_persistent_cache(client)
cache_mod.clear_all()
print('Done. Restart ./do dev to recompute predictions.')
"
}

# ── Quality ─────────────────────────────────────────────────────────

cmd_test() {
  cd "$SCRIPT_DIR"
  uv run pytest tests/ -v
}

cmd_aito_check() {
  cd "$SCRIPT_DIR"
  if [[ ! -f tests/test_aito_check.py ]]; then
    echo "tests/test_aito_check.py not implemented yet (lands with the first view that calls Aito)."
    exit 0
  fi
  uv run pytest tests/test_aito_check.py -v
}

cmd_verify() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: ./do verify <feature>"
    exit 1
  fi
  echo "Adversary Playwright agent not wired yet — see CLAUDE.md §Adversary verification."
  exit 1
}

cmd_verify_demo() {
  echo "End-to-end demo-path check not wired yet — lands once the demo script in docs/demo-script.md is finalised."
  exit 1
}

cmd_check() {
  cmd_test
  cmd_fmt
  cmd_aito_check
}

cmd_fmt() {
  echo "No formatter configured yet."
}

# ── Frontend & deps ─────────────────────────────────────────────────

cmd_npm_install() {
  echo "Installing frontend dependencies..."
  cd "$SCRIPT_DIR/frontend"
  npm install
}

cmd_uv_sync() {
  echo "Syncing Python dependencies..."
  cd "$SCRIPT_DIR"
  uv sync
}

cmd_setup() {
  cmd_uv_sync
  cmd_npm_install
  echo "Setup complete."
}

cmd_typecheck() {
  echo "Running TypeScript type check..."
  cd "$SCRIPT_DIR/frontend"
  npx tsc --noEmit
}

cmd_lint() {
  echo "Linting frontend..."
  cd "$SCRIPT_DIR/frontend"
  npx next lint 2>/dev/null || echo "No linter configured."
}

# ── Product sheet + teaser (assets for outreach) ─────────────────────

_find_chrome() {
  # 1. Playwright-managed browsers
  for c in ${PLAYWRIGHT_BROWSERS_PATH:-/nonexistent}/chromium-*/chrome-linux/chrome; do
    [[ -x "$c" ]] && { echo "$c"; return; }
  done
  # 2. Nix playwright-chromium package
  for c in /nix/store/*playwright-chromium*/chrome-linux/chrome; do
    [[ -x "$c" ]] && { echo "$c"; return; }
  done
  # 3. PATH lookups
  for cmd in chromium chromium-browser google-chrome; do
    local path
    path=$(command -v "$cmd" 2>/dev/null)
    [[ -n "$path" && -x "$path" ]] && { echo "$path"; return; }
  done
  echo ""
}

cmd_product_sheet() {
  echo "Compiling product sheet..."
  cd "$SCRIPT_DIR"
  if ! command -v typst >/dev/null 2>&1; then
    echo "  typst not on PATH — try: nix-shell -p typst" >&2
    exit 1
  fi
  # Bring up the screenshots the .typ file references if they're missing.
  if [[ ! -f screenshots/inspect/01-dashboard.png ]]; then
    echo "  screenshots/inspect/ missing — run ./do dev in one terminal," >&2
    echo "  then 'node frontend/scripts/inspect-views.cjs' to (re-)generate." >&2
    exit 2
  fi
  # --root points typst at the repo root so the .typ file can `image()`
  # screenshots that live outside `docs/product-sheet/`.
  typst compile --root "$SCRIPT_DIR" \
    docs/product-sheet/product-sheet.typ \
    docs/product-sheet/product-sheet.pdf
  echo "  ✓ docs/product-sheet/product-sheet.pdf"
}

cmd_teaser() {
  # Render assets/teaser.html → assets/teaser.png via headless chromium.
  # A transient python http.server lets the HTML's relative
  # ../screenshots/... paths resolve as http URLs (chromium denies
  # cross-dir subresources from file://).
  local chrome
  chrome=$(_find_chrome)
  if [[ -z "$chrome" ]]; then
    echo "Error: chromium not found. Install chromium or set PLAYWRIGHT_BROWSERS_PATH." >&2
    exit 1
  fi
  if [[ ! -f screenshots/inspect/01-dashboard.png ]]; then
    echo "  screenshots/inspect/ missing — regenerate via" >&2
    echo "  'node frontend/scripts/inspect-views.cjs'" >&2
    exit 2
  fi
  cd "$SCRIPT_DIR"

  python3 -m http.server 8765 --bind 127.0.0.1 --directory "$SCRIPT_DIR" \
    > /tmp/ecom_teaser_http.log 2>&1 &
  local http_pid=$!
  trap "kill $http_pid 2>/dev/null" EXIT
  sleep 1

  "$chrome" --headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage \
    --hide-scrollbars \
    --window-size=1500,1900 \
    --force-device-scale-factor=2 \
    --screenshot="$SCRIPT_DIR/assets/teaser.png" \
    "http://127.0.0.1:8765/assets/teaser.html" 2>&1 | tail -2

  kill $http_pid 2>/dev/null
  trap - EXIT
  echo "  ✓ assets/teaser.png"
}

case "${1:-help}" in
  help)              cmd_help ;;
  dev)               cmd_dev ;;
  backend-dev)       cmd_backend_dev ;;
  frontend-dev)      cmd_frontend_dev ;;
  frontend-build)    cmd_frontend_build ;;
  stop)              cmd_stop ;;
  restart)           cmd_restart ;;
  demo)              cmd_demo ;;
  generate-fixtures) cmd_generate_fixtures ;;
  load-data)         shift; cmd_load_data "$@" ;;
  reset-data)        shift; cmd_reset_data "$@" ;;
  clear-cache)       cmd_clear_cache ;;
  test)              cmd_test ;;
  aito-check)        cmd_aito_check ;;
  verify)            shift; cmd_verify "$@" ;;
  verify-demo)       cmd_verify_demo ;;
  check)             cmd_check ;;
  fmt)               cmd_fmt ;;
  npm-install)       cmd_npm_install ;;
  uv-sync)           cmd_uv_sync ;;
  setup)             cmd_setup ;;
  typecheck)         cmd_typecheck ;;
  lint)              cmd_lint ;;
  product-sheet)     cmd_product_sheet ;;
  teaser)            cmd_teaser ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
