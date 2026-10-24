#!/usr/bin/env bash
# Starts aito-mcp, read-only, on one sandbox branch (ADR 0043, Flow 3).
# `./do agent-demo <branch>` points Claude Code's MCP config at this file;
# it is not meant to be run by hand.
#
#   SANDBOX_BRANCH   tmp-YYYY-MM-DD-HH-MM-SS-<16 hex>, as "New sandbox" made it
#   SANDBOX_DB_URL   the sandbox database, e.g. https://shared.aito.ai/db/aito-ecommerce-sandbox
#   SANDBOX_RO_KEY_FILE  default ~/.config/aito-mcp/sandbox-readonly-key
#
# The agent reads the branch at  <SANDBOX_DB_URL>/env/<branch>,  the same
# data the app's lever just wrote. Two fences keep it read-only:
#   - the key is the sandbox database's READ-ONLY key, read from a file
#     (chmod 600) and never printed, logged or put in a config;
#   - aito-mcp refuses its write tools (put_schema, upload_rows) unless
#     AITO_MCP_ALLOW_WRITES=1, and the server starts in an environment
#     that holds only what it needs, so that variable can't leak in.
set -euo pipefail

fail() { echo "aito-mcp-sandbox: $*" >&2; exit 1; }

# The pattern of src/sandbox_envs.py: BRANCH_PATTERN. Only a throwaway branch.
branch="${SANDBOX_BRANCH:-}"
[[ "$branch" =~ ^tmp-[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9a-f]{16}$ ]] \
  || fail "SANDBOX_BRANCH '${branch}' is not a sandbox branch (tmp-YYYY-MM-DD-HH-MM-SS-<16 hex>)"

db_url="${SANDBOX_DB_URL%/}"
# The fence of src/sandbox_config.py: the database's name must say sandbox.
[[ "$db_url" =~ ^https?://[^/]+/db/[^/]*sandbox[^/]*$ ]] \
  || fail "SANDBOX_DB_URL '${db_url}' doesn't name a sandbox database (/db/<name containing 'sandbox'>)"

key_file="${SANDBOX_RO_KEY_FILE:-$HOME/.config/aito-mcp/sandbox-readonly-key}"
[[ -r "$key_file" ]] || fail "no read-only key at $key_file (create it: one line, chmod 600)"
key="$(tr -d '[:space:]' < "$key_file")"
[[ -n "$key" ]] || fail "the key file $key_file is empty"

# A clean environment: no PetNord key, no sandbox read-write key, no
# AITO_MCP_ALLOW_WRITES. uvx needs HOME and PATH (and its cache, if moved).
exec env -i \
  HOME="$HOME" PATH="$PATH" LANG="${LANG:-C.UTF-8}" \
  ${XDG_CACHE_HOME:+XDG_CACHE_HOME="$XDG_CACHE_HOME"} ${UV_CACHE_DIR:+UV_CACHE_DIR="$UV_CACHE_DIR"} \
  AITO_URL="$db_url/env/$branch" \
  AITO_API_KEY="$key" \
  uvx "${AITO_MCP_SPEC:-aito-mcp@1.2.0}"
