#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env if present, then .env.local as an override layer.
# .env holds the shared defaults (prod instance); .env.local (gitignored)
# lets you point AITO_API_URL/AITO_API_KEY at a personal dev instance for
# R&D without editing tracked files or touching prod. See README
# "R&D environment". Sourcing .env.local last means its values win over
# .env — but a variable you exported yourself wins over both.
#
# Source dotenv files without overriding the caller's environment. A variable
# that was already set (non-empty) when ./do started wins over every file, so
# `AITO_API_URL=http://localhost:8080 ./do load-data` really targets
# localhost; among the files, a later one wins over an earlier one. Plain
# `set -a; source` let the file win: on 2026-09-20 a loader pointed at a
# local engine silently wrote to production (shared.aito.ai) instead.
_source_env_files() {
  local file name kv
  local -a explicit=()
  for file in "$@"; do
    [[ -f "$file" ]] || continue
    while IFS= read -r name; do
      [[ -n "${!name:-}" ]] && explicit+=("$name=${!name}")
    done < <(sed -nE 's/^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=.*/\2/p' "$file")
  done
  for file in "$@"; do
    [[ -f "$file" ]] || continue
    set -a
    # shellcheck disable=SC1090
    source "$file"
    set +a
  done
  for kv in ${explicit[@]+"${explicit[@]}"}; do export "$kv"; done
}
# A git worktree is a fresh checkout without the gitignored .env, so it
# borrows the main checkout's credentials. A worktree's own .env still wins,
# and its own .env.local overrides either; _show_target says which was used.
_credentials_dir() {
  [[ -f "$SCRIPT_DIR/.env" ]] && { echo "$SCRIPT_DIR"; return; }
  local common
  common="$(git -C "$SCRIPT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
    || { echo "$SCRIPT_DIR"; return; }
  local main_checkout="${common%/.git}"
  if [[ -f "$main_checkout/.env" ]]; then echo "$main_checkout"; else echo "$SCRIPT_DIR"; fi
}
CREDENTIALS_DIR="$(_credentials_dir)"
if [[ "$CREDENTIALS_DIR" == "$SCRIPT_DIR" ]]; then
  _source_env_files "$SCRIPT_DIR/.env" "$SCRIPT_DIR/.env.local"
else
  _source_env_files "$CREDENTIALS_DIR/.env" "$CREDENTIALS_DIR/.env.local" "$SCRIPT_DIR/.env.local"
fi

# Print the Aito instance a data command is about to touch, so you never
# load/clear the wrong environment. Loud when it's the shared prod DB.
_show_target() {
  local url="${AITO_API_URL:-<unset>}"
  if [[ "$url" == *"/aito-ecommerce-demo" ]]; then
    echo "⚠️  Target Aito: $url  (SHARED / prod)"
  else
    echo "Target Aito: $url"
  fi
  if [[ "$CREDENTIALS_DIR" != "$SCRIPT_DIR" ]]; then
    echo "   credentials from the main checkout: $CREDENTIALS_DIR/.env"
  fi
}

# Refuse a WRITE against the shared prod instance unless it is asked for
# explicitly. Printing a warning was not enough: `./do load-data` was run
# against shared prod with no .env.local, its optimize step did not
# finish, and /api/dashboard started answering 500 — the live demo, from
# a command meant for a dev box. Reads stay unguarded; only verbs that
# mutate data call this.
#
# The paved path is .env.local (gitignored) pointing at your own
# instance — see README "R&D environment". Then the URL is not prod and
# the routine case needs no flag and no prompt. The guard checks the URL
# actually in effect, not whether .env.local exists: an exported
# AITO_API_URL wins over .env.local, so its existence proves nothing.
_guard_prod_write() {
  local verb="$1"
  local url="${AITO_API_URL:-}"

  [[ "$url" == *"/aito-ecommerce-demo" ]] || return 0        # not prod
  [[ "${AITO_ALLOW_PROD:-}" == "1" ]] && return 0            # opted in

  echo "⛔ REFUSING '$verb' — it writes, and the target is the SHARED demo instance:"
  echo "     $url"
  echo
  echo "   This is the instance fronting ecommerce.aito.ai."
  echo "   Either point .env.local at your own instance (README \"R&D environment\"),"
  echo "   or, if you really mean prod:  AITO_ALLOW_PROD=1 ./do $verb"
  exit 1
}

# Refuse a UCI write unless it targets env `uci`, exactly. The UCI
# tables share names with the pet shop's (`customers`), so the same load
# into master, or into another test env, would replace that env's tables.
_guard_uci_env() {
  local verb="$1"
  [[ "${AITO_ENV:-}" == "uci" ]] && return 0
  echo "⛔ REFUSING '$verb' — it writes the UCI tables, and AITO_ENV is '${AITO_ENV:-}' (not 'uci')."
  echo "   Run it as:  AITO_ENV=uci ./do $verb"
  exit 1
}

# Refuse a write that replaces every table unless AITO_ENV names an env
# other than master: a data release is loaded into its own env first, and
# reaches master only through ADR 0035's promote.
_guard_named_env() {
  local verb="$1"
  case "${AITO_ENV:-}" in
    ""|master)
      echo "⛔ REFUSING '$verb' — it drops and reloads every table, and AITO_ENV is '${AITO_ENV:-<unset>}' (master)."
      echo "   Run it as:  AITO_ENV=<a new env> ./do $verb"
      exit 1 ;;
  esac
}

# Ports: frontend on 8500 (user-facing), backend on 8501 (internal).
# Allocated by the cross-demo framework doc — see
# aito-demo-framework.md §2 "Port allocation". Don't reuse other
# demos' pairs. Override both to run a second copy beside the demo, e.g.
# PORT_BACKEND=8640 ./do backend-dev from a worktree.
PORT_FRONTEND="${PORT_FRONTEND:-8500}"
PORT_BACKEND="${PORT_BACKEND:-8501}"
export PORT_BACKEND   # next.config.ts proxies the dev API to it

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
  env-load          Drop and reload every table into a named env (needs AITO_ENV=<env>; refuses master)
  reset-data        Drop and reload all Aito tables + warm the cache
  optimize          Merge batch segments on all tables for faster reads
  clear-cache       Clear in-memory + Aito persistent prediction cache
  target            Show which Aito instance commands use, and whose credentials
  warm-cache        Pre-compute every cacheable endpoint once
  precompute        Snapshot the six heavy endpoints to Aito + git JSON (ADR 0024)
                    --as master: compute on AITO_ENV's env, file as master (ADR 0035)
  release-file      <env>: write data/release-env.json from the env's row counts (read-only)
  release-check     [<env>]: does the env (default: the release's) match data/release-env.json? (read-only)
  sandbox-template-load  Load the release fixtures into the sandbox DB's master, then warm it (ADR 0043)
  sandbox-new       Branch a sandbox off the template, warm it, print its ?db= link
  sandbox-list      The live sandboxes and when they expire (read-only)
  sandbox-time      Time the lever → Shop loop 5× on a throwaway branch (deleted after)
  agent-demo        <branch> ["question"]: an agent (aito-mcp, read-only key) on one sandbox branch
  uci-prepare       UCI Online Retail II xlsx → data/uci/*.json (local, no Aito; ADR 0034)
  uci-load          Load data/uci/ into Aito env uci (needs AITO_ENV=uci)
  workbook          (Re)create the console workbook from docs/aito-workbook-ecommerce-demo.json

Quality
  test              Run pytest
  aito-check        Sanity-check Aito queries against the loaded data
  uci-check         The UCI checks in aito-check, on env uci (reproduces the benchmark)
  backtest-prepare  shopify <export.csv> <name>: a merchant's orders → data/backtest/<name>/ (ADR 0036)
  backtest-load     <name>: training orders → Aito env backtest-<name> (needs AITO_ENV=backtest-<name>)
  backtest          <uci|name> [--offline]: Aito vs three baselines → data/backtest/<name>/report.md
  search-eval       Score search arms on the judged query set (nDCG, recall, controls)
  evidence          <entry>: rewrite data/evidence/<entry>.json (ADR 0037; reads only):
                    search-relevance | model-checks | personalised-search [--probe]
  v2-env            Stage the v2 (Rep2) env — ADR 0025 (dry run unless --apply)
  verify <feature>  Run the adversary Playwright agent for one feature
  verify-demo       End-to-end demo-path check
  verify-mobile     Mobile sweep of every view: screenshots, then an overflow check that fails on any overflow
  test-urls         Build the static export; check every view's link opens as shared
  planted-effects   Generate planted and null fixtures for 3 seeds; judge every planted effect (~30 min)
  pooled-effects    The impression-side checks over 10 seeds, pooled with intervals (~45 min)
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
  # A local app reads the shared demo DB: memory-only cache unless PUBLIC_DEMO=0 is set.
  export PUBLIC_DEMO="${PUBLIC_DEMO:-1}"
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
  uv run python -m data.generate_fixtures
}

# The impressions and contexts fixtures are gitignored (too large to
# commit, see ADR 0021 and ADR 0040). Regenerate the whole deterministic
# fixture set if either is absent — a no-op for the committed tables
# (seed=42 ⇒ byte-identical).
_ensure_impressions() {
  local table
  for table in impressions contexts; do
    if [[ ! -f "$SCRIPT_DIR/data/$table.json" ]]; then
      echo "data/$table.json missing (gitignored) — regenerating fixtures..."
      cmd_generate_fixtures
      return
    fi
  done
}

cmd_load_data() {
  cd "$SCRIPT_DIR"
  if [[ ! -f src/data_loader.py ]]; then
    echo "src/data_loader.py not implemented yet (build-order step 3)."
    exit 1
  fi
  _guard_prod_write load-data
  _show_target
  _ensure_impressions
  uv run python -m src.data_loader "$@"
}

cmd_env_load() {
  # A data release goes into its own env (ADR 0035): every table of
  # src/schema.py, dropped and reloaded. The env must exist already.
  cd "$SCRIPT_DIR"
  _guard_named_env env-load
  _show_target
  echo "   env: $AITO_ENV"
  _ensure_impressions
  uv run python -m src.data_loader --reset --refuse-master "$@"
}

cmd_reset_data() {
  cd "$SCRIPT_DIR"
  if [[ ! -f src/data_loader.py ]]; then
    echo "src/data_loader.py not implemented yet (build-order step 3)."
    exit 1
  fi
  _guard_prod_write reset-data
  _show_target
  _ensure_impressions
  uv run python -m src.data_loader --reset "$@"
  echo
  # Warm the prediction_cache table so the next ./do dev boot is
  # fast on the first request. Without this, Churn / Inventory /
  # Demand pay their full cold cost (up to 22 s) on the first
  # user click after a reset. See src/cache_warmup.py.
  uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src import cache
from src.cache_warmup import warm_all
from src.precompute import precompute_all

config = load_config()
client = AitoClient(config)
cache.init_persistent_cache(client)
# Light endpoints: lazy L2 warm. Heavy endpoints: offline snapshot into
# the precompute store (ADR 0024). Chained here so the snapshot can
# never drift behind a data reload.
warm_all(client, verbose=True)
precompute_all(client, verbose=True)
"
}

cmd_clear_cache() {
  echo "Clearing caches..."
  cd "$SCRIPT_DIR"
  _guard_prod_write clear-cache
  _show_target
  uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src import cache as cache_mod
cfg = load_config()
client = AitoClient(cfg)
cache_mod.init_persistent_cache(client)
cache_mod.clear_all()
print('Done. Run ./do warm-cache to pre-populate, or ./do dev (warmup starts on boot).')
"
}

cmd_warm_cache() {
  echo "Warming all cacheable endpoints..."
  cd "$SCRIPT_DIR"
  _show_target
  uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src import cache as cache_mod
from src.cache_warmup import warm_all
cfg = load_config()
client = AitoClient(cfg)
cache_mod.init_persistent_cache(client)
warm_all(client, verbose=True)
"
}

cmd_precompute() {
  # Snapshot the six heavy endpoints (churn, demand, evaluation,
  # inventory, markdown, winback) into the Aito precompute_entries
  # table + the git-committed JSON bootstrap. See ADR 0024. Runs the
  # heavy _evaluate / fan-out work OFFLINE so the running container
  # (and the read-only public deploy) only ever reads. Deliberately
  # does NOT init the lazy persistent cache, so each endpoint computes
  # live and its real per-call timings are captured for the pill.
  #
  # --as <env>: compute on the env AITO_ENV names, but file the snapshots
  # under <env>'s namespace. A release computes on its env "as master",
  # since after the promote master holds those same rows (ADR 0035):
  #   AITO_ENV=observable ./do precompute --as master
  local write_as=""
  if [[ $# -gt 0 ]]; then
    if [[ "$1" != "--as" || $# -ne 2 || -z "$2" ]]; then
      echo "Usage: ./do precompute [--as <env>]" >&2
      exit 1
    fi
    write_as="$2"
  fi
  echo "Precomputing heavy endpoints (churn, demand, evaluation, inventory, markdown, winback)..."
  cd "$SCRIPT_DIR"
  _show_target
  echo "   computed on env: ${AITO_ENV:-master}; written as env: ${write_as:-${AITO_ENV:-master}}"
  WRITE_AS="$write_as" uv run python -c "
import os
from src.config import load_config
from src.aito_client import AitoClient
from src.precompute import precompute_all
cfg = load_config()
client = AitoClient(cfg)
precompute_all(client, verbose=True, write_as_env=os.environ['WRITE_AS'] or None)
"
}

cmd_release_file() {
  # Write data/release-env.json from an env's live row counts (ADR 0035).
  # Read-only: one _search with limit 0 per table.
  if [[ $# -ne 1 || -z "$1" ]]; then
    echo "Usage: ./do release-file <env>" >&2
    exit 1
  fi
  cd "$SCRIPT_DIR"
  _show_target
  AITO_ENV="$1" uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src.release_file import RELEASE_FILE, Release, read_counts, write_release
cfg = load_config()
release = Release(env=cfg.aito_env, counts=read_counts(AitoClient(cfg)))
write_release(release)
for table, count in release.to_dict()['counts'].items():
    print(f'  {table:20s} {count:>9,}')
print(f'Wrote {RELEASE_FILE} for env {release.env}.')
"
}

# The sandbox database (ADR 0043): AITO_SANDBOX_URL + AITO_SANDBOX_API_KEY.
# src/sandbox_cli.py refuses unless the URL names a sandbox database.
cmd_sandbox() {
  cd "$SCRIPT_DIR"
  echo "Sandbox database: ${AITO_SANDBOX_URL:-<unset>}"
  [[ "$1" == "template-load" ]] && _ensure_impressions
  uv run python -m src.sandbox_cli "$1"
}

# Flow 3 of the partner demo (ADR 0043): a merchant's agent, Claude Code
# with aito-mcp as its only tools, reading one sandbox branch with the
# sandbox database's read-only key. The key stays in its file: the MCP
# config written here holds paths, never the key. Writes are refused twice,
# by the key and by aito-mcp (no AITO_MCP_ALLOW_WRITES). The rehearsal is in
# docs/notes/2026-10-26-ambientia-run-sheet.md.
cmd_agent_demo() {
  local branch="${1:-}"
  [[ $# -gt 0 ]] && shift
  local question="$*"
  local pattern='^tmp-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9a-f]{16}$'
  if [[ ! "$branch" =~ $pattern ]]; then
    echo "Usage: ./do agent-demo <sandbox branch> [\"first question\"]" >&2
    echo "  the branch is a live sandbox's ?db= value (./do sandbox-list), e.g." >&2
    echo "  tmp-2026-10-26-11-30-00-3f9c2a1b7d4e6f80" >&2
    exit 1
  fi
  local key_file="${SANDBOX_RO_KEY_FILE:-$HOME/.config/aito-mcp/sandbox-readonly-key}"
  if [[ ! -r "$key_file" ]]; then
    echo "⛔ REFUSING: no read-only key at $key_file." >&2
    echo "   Put the sandbox database's read-only key there (one line, chmod 600)." >&2
    exit 1
  fi
  local tool
  for tool in claude uvx; do
    command -v "$tool" >/dev/null || { echo "$tool is not on PATH" >&2; exit 1; }
  done

  local dir="$SCRIPT_DIR/scripts/agent-demo"
  local db_url="${AITO_SANDBOX_URL:-https://shared.aito.ai/db/aito-ecommerce-sandbox}"
  # The agent runs in an empty folder, so it reads no project files and no
  # CLAUDE.md of this repo: a merchant's agent knows only its brief.
  local workdir config
  workdir="$(mktemp -d -t agent-demo-XXXXXX)"
  config="$workdir/mcp.json"
  cat > "$config" <<EOF
{ "mcpServers": { "aito": {
    "command": "$dir/aito-mcp-sandbox.sh",
    "env": { "SANDBOX_BRANCH": "$branch", "SANDBOX_DB_URL": "$db_url", "SANDBOX_RO_KEY_FILE": "$key_file" } } } }
EOF
  echo "Agent on $db_url/env/$branch"
  echo "  key: read-only, from $key_file; aito-mcp's writes: refused"
  local read_tools="mcp__aito__get_schema,mcp__aito__search,mcp__aito__predict,mcp__aito__recommend"
  read_tools+=",mcp__aito__relate,mcp__aito__match,mcp__aito__query,mcp__aito__evaluate"
  local status=0
  (cd "$workdir" && env -u AITO_API_KEY -u AITO_SANDBOX_API_KEY -u ADMIN_TOKEN -u AITO_MCP_ALLOW_WRITES \
    claude ${question:+"$question"} \
      --append-system-prompt "$(cat "$dir/brief.txt")" \
      --mcp-config "$config" --strict-mcp-config \
      --allowedTools "$read_tools" \
      --disallowedTools "mcp__aito__put_schema,mcp__aito__upload_rows,Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,Task,NotebookEdit") \
      || status=$?
  rm -rf "$workdir"
  return "$status"
}

cmd_release_check() {
  # The cutover's pre-flight (ADR 0035), read-only: does an env hold the
  # release file's tables and row counts? Defaults to the release's own
  # env; `./do release-check master` checks master after the promote.
  # Exits 1 and names each differing table on a mismatch.
  if [[ $# -gt 1 ]]; then
    echo "Usage: ./do release-check [<env>]" >&2
    exit 1
  fi
  cd "$SCRIPT_DIR"
  _show_target
  CHECK_ENV="${1:-}" uv run python -c "
import os, sys
from dataclasses import replace
from src.config import load_config
from src.aito_client import AitoClient
from src.release_file import RELEASE_FILE, differences, load_release, read_counts
release = load_release()
env = os.environ['CHECK_ENV'] or release.env
cfg = replace(load_config(), aito_env=env)
found = differences(release.counts, read_counts(AitoClient(cfg)))
if found:
    print(f'Env {env} does not match {RELEASE_FILE.name} (release env {release.env}):')
    for line in found:
        print(f'  {line}')
    sys.exit(1)
print(f'Env {env} matches {RELEASE_FILE.name}: {len(release.counts)} tables, release env {release.env}.')
"
}

cmd_optimize() {
  # Merge each table's batch-upload segments into one for faster reads
  # (POST /data/<table>/optimize). reset-data already does this after a
  # load; this verb re-runs it by hand on an already-loaded instance.
  echo "Optimizing all tables (merge batch segments)..."
  cd "$SCRIPT_DIR"
  _show_target
  uv run python -m src.data_loader --optimize-only
}

# ── UCI Online Retail II, env `uci` (ADR 0034) ─────────────────────

cmd_uci_prepare() {
  # Reads the local xlsx (UCI_XLSX, md5-checked), writes data/uci/.
  cd "$SCRIPT_DIR"
  PYTHONPATH=. uv run python scripts/uci_prepare.py
}

cmd_uci_load() {
  cd "$SCRIPT_DIR"
  _guard_uci_env uci-load
  _show_target
  echo "   env: uci"
  uv run python -m src.uci_loader
}

cmd_uci_check() {
  # The aito-check tests named *uci*, which skip unless AITO_ENV=uci.
  cd "$SCRIPT_DIR"
  AITO_ENV=uci uv run pytest tests/test_aito_check.py -v -k uci
}

# ── Reorder backtest on a merchant's orders (ADR 0036) ────────────

cmd_backtest_prepare() {
  # Local only. The Email salt comes from BACKTEST_EMAIL_SALT; never commit it.
  cd "$SCRIPT_DIR"
  PYTHONPATH=. uv run --group backtest python scripts/backtest.py prepare "$@"
}

cmd_backtest_load() {
  cd "$SCRIPT_DIR"
  _guard_prod_write backtest-load
  _show_target
  echo "   env: ${AITO_ENV:-<unset>}"
  uv run python -m src.backtest_loader "$@"
}

cmd_backtest() {
  # --offline: the three baselines only. Otherwise AITO_ENV must be the
  # dataset's env (uci, or backtest-<name>); only _predict is read.
  cd "$SCRIPT_DIR"
  PYTHONPATH=. uv run --group backtest python scripts/backtest.py run "$@"
}

# ── Workbook ────────────────────────────────────────────────────────

# (Re)create the Aito console workbook from its JSON definition. The
# workbook API lives on the *console*, not the Aito instance — auth is
# the same AITO_API_KEY (.env) sent as x-api-key. Idempotent: any
# existing workbook with the same name is deleted first, so re-running
# always yields exactly one copy. See
# docs/aito-workbook-instructions-aito-ecommerce-demo.md.
cmd_workbook() {
  cd "$SCRIPT_DIR"
  local def="docs/aito-workbook-ecommerce-demo.json"
  local console_url="${AITO_CONSOLE_URL:-https://console.aito.ai}"
  local api="${console_url}/api/workbooks/api-key/workbooks"

  if [[ -z "${AITO_API_KEY:-}" ]]; then
    echo "AITO_API_KEY not set (expected in .env)." >&2
    exit 1
  fi
  if [[ ! -f "$def" ]]; then
    echo "Workbook definition not found: $def" >&2
    exit 1
  fi

  local name
  name=$(python3 -c "import json,sys; print(json.load(open('$def'))['name'])")

  # Delete any existing workbook(s) with the same name so re-runs don't pile up.
  curl -s "$api" -H "x-api-key: ${AITO_API_KEY}" \
    | python3 -c "import json,sys; [print(w['id']) for w in json.load(sys.stdin) if w['name']==sys.argv[1]]" "$name" \
    | while read -r id; do
        echo "Deleting existing workbook $id ($name)"
        curl -s -X DELETE "$api/$id" -H "x-api-key: ${AITO_API_KEY}" >/dev/null
      done

  echo "Creating workbook \"$name\" on ${console_url}..."
  curl -s -X POST "$api/from-definition" \
    -H "Content-Type: application/json" \
    -H "x-api-key: ${AITO_API_KEY}" \
    -d @"$def" \
    | python3 -c "import json,sys; w=json.load(sys.stdin)['workbook']; print(f'  ✓ {w[\"id\"]} — {len(w[\"sections\"])} sections')"
}

# ── Quality ─────────────────────────────────────────────────────────

cmd_test() {
  cd "$SCRIPT_DIR"
  # Live checks read the shared demo DB with the read-write key; they must never
  # write its cache (aito-azure saw 14 cache writes on master on 2026-10-24).
  export PUBLIC_DEMO="${PUBLIC_DEMO:-1}"
  # The backtest group adds numpy, which the EASE baseline's tests need (ADR 0036).
  uv run --group backtest pytest "${@:-tests/}" -v
}

cmd_aito_check() {
  cd "$SCRIPT_DIR"
  export PUBLIC_DEMO="${PUBLIC_DEMO:-1}"   # reads only: no cache rows on the shared DB
  if [[ ! -f tests/test_aito_check.py ]]; then
    echo "tests/test_aito_check.py not implemented yet (lands with the first view that calls Aito)."
    exit 0
  fi
  uv run pytest tests/test_aito_check.py -v "$@"
}

cmd_search_eval() {
  # Score every search arm on the judged query set (read-only queries).
  # Writes docs/verification/search-eval.{md,json}; exits non-zero if a
  # control (random arm, shuffled labels) scores too well to trust.
  cd "$SCRIPT_DIR"
  uv run python -m src.search_eval.run
}

cmd_evidence() {
  # ADR 0037 §2: an Evidence page reads a committed result file, never a live
  # benchmark. Each entry's writer is re-runnable; all of them only read Aito.
  cd "$SCRIPT_DIR"
  local entry="${1:-}"
  shift || true
  case "$entry" in
    search-relevance)    uv run python -m src.evidence.search_relevance "$@" ;;
    model-checks)        uv run python -m src.evidence.model_checks "$@" ;;
    personalised-search)
      # --probe: the query shapes and the BM25 agreement, before the run (ADR 0037 §3).
      if [[ "${1:-}" == "--probe" ]]; then
        uv run python -m src.personalised_search.probe
      else
        uv run python -m src.personalised_search.run "$@"
      fi
      ;;
    *)
      echo "Usage: ./do evidence <search-relevance|model-checks|personalised-search> [--probe]" >&2
      exit 1
      ;;
  esac
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
  # Every view on the DEPLOYED demo (or --base http://localhost:8500), read-only:
  # fails on an error OR a hollow view. scripts/live_smoke.py; also runs daily in CI.
  cd "$SCRIPT_DIR"
  python3 scripts/live_smoke.py "$@"
}

cmd_test_urls() {
  # A pasted link must open a view exactly as shared, and back/forward must
  # step through choices. Serves the static export and intercepts the API, so
  # it needs no backend and never touches Aito. frontend/scripts/deeplink-test.cjs
  cd "$SCRIPT_DIR/frontend"
  npx next build --webpack
  node scripts/deeplink-test.cjs
}

cmd_planted_effects() {
  # Each planted effect (ADRs 0032, 0033, 0038-0040) against the same seed's
  # generation without it, for three seeds in parallel. Writes
  # docs/verification/actionable-states-data.md; leaves data/ alone.
  cd "$SCRIPT_DIR"
  PYTHONPATH=. uv run python scripts/planted_effects.py
}

cmd_pooled_effects() {
  # The impression-side checks over 10 seeds, pooled (ADR 0045's amendment):
  # writes docs/verification/actionable-states-pooled.md; leaves data/ alone.
  cd "$SCRIPT_DIR"
  PYTHONPATH=. uv run python scripts/pooled_effects.py
}

cmd_verify_mobile() {
  # Mobile layout sanity-check — runs `frontend/scripts/inspect-mobile.cjs`
  # against the already-running dev server (./do dev). Captures every
  # sidebar view at 414 × 900 into `screenshots/inspect-mobile/` for
  # visual review. The output dir is gitignored.
  if ! curl -s -o /dev/null -w "%{http_code}" "http://localhost:8500/" | grep -q "^2"; then
    echo "Dev server doesn't seem to be at http://localhost:8500. Start it with: ./do dev"
    exit 1
  fi
  cd "$SCRIPT_DIR"
  node frontend/scripts/inspect-mobile.cjs
  # Screenshots miss a popover wider than the phone; this measures every view and state and
  # exits non-zero if any overflows (frontend/scripts/mobile-overflow.cjs).
  NODE_PATH="$SCRIPT_DIR/frontend/node_modules" node frontend/scripts/mobile-overflow.cjs
}

cmd_v2_env() {
  cd "$SCRIPT_DIR"
  uv run python -m src.v2_env "$@"
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
  target)            _show_target ;;
  dev)               cmd_dev ;;
  backend-dev)       cmd_backend_dev ;;
  frontend-dev)      cmd_frontend_dev ;;
  frontend-build)    cmd_frontend_build ;;
  stop)              cmd_stop ;;
  restart)           cmd_restart ;;
  demo)              cmd_demo ;;
  generate-fixtures) cmd_generate_fixtures ;;
  load-data)         shift; cmd_load_data "$@" ;;
  env-load)          shift; cmd_env_load "$@" ;;
  reset-data)        shift; cmd_reset_data "$@" ;;
  clear-cache)       cmd_clear_cache ;;
  warm-cache)        cmd_warm_cache ;;
  precompute)        shift; cmd_precompute "$@" ;;
  release-file)      shift; cmd_release_file "$@" ;;
  release-check)     shift; cmd_release_check "$@" ;;
  optimize)          cmd_optimize ;;
  uci-prepare)       cmd_uci_prepare ;;
  uci-load)          cmd_uci_load ;;
  uci-check)         cmd_uci_check ;;
  backtest-prepare)  shift; cmd_backtest_prepare "$@" ;;
  backtest-load)     shift; cmd_backtest_load "$@" ;;
  backtest)          shift; cmd_backtest "$@" ;;
  workbook)          cmd_workbook ;;
  sandbox-template-load) cmd_sandbox template-load ;;
  sandbox-new)       cmd_sandbox new ;;
  sandbox-list)      cmd_sandbox list ;;
  sandbox-time)      cmd_sandbox time ;;
  agent-demo)        shift; cmd_agent_demo "$@" ;;
  test)              shift; cmd_test "$@" ;;
  aito-check)        shift; cmd_aito_check "$@" ;;
  search-eval)       cmd_search_eval ;;
  evidence)          shift; cmd_evidence "$@" ;;
  v2-env)          cmd_v2_env "${@:2}" ;;
  verify)            shift; cmd_verify "$@" ;;
  verify-demo)       cmd_verify_demo ;;
  verify-mobile)     cmd_verify_mobile ;;
  test-urls)         cmd_test_urls ;;
  planted-effects)   cmd_planted_effects ;;
  pooled-effects)    cmd_pooled_effects ;;
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
