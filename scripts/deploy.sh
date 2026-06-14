#!/usr/bin/env bash
# Build and deploy Avatar to fly.io: create the app on first run, stage secrets
# from the root .env, then deploy one always-on machine. Run from anywhere; it
# finds the repo root. COOKIE_SECURE=1 and PORT are set in scripts/fly.toml [env].
set -euo pipefail

# Keep this in sync with `app = "..."` in scripts/fly.toml.
APP="personalavatar"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

command -v flyctl >/dev/null 2>&1 || { echo "flyctl not found — install it first (https://fly.io/docs/flyctl/install/)."; exit 1; }
flyctl auth whoami >/dev/null 2>&1 || { echo "Not logged in — run 'fly auth login'."; exit 1; }

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "Missing .env at repo root ($REPO_ROOT/.env). Its values become Fly secrets."
  exit 1
fi

# 1. Create the app on first run (name must be globally unique).
if ! flyctl status -a "$APP" >/dev/null 2>&1; then
  echo "Creating app '$APP'..."
  flyctl apps create "$APP"
fi

# 2. Stage secrets from .env (surrounding quotes stripped). PORT/COOKIE_SECURE
#    live in fly.toml [env], not here. --stage applies them on the next deploy.
KEYS="OPENROUTER_API_KEY MODEL OWNER_NAME ADMIN_PASSWORD PUSHOVER_USER PUSHOVER_TOKEN SUPABASE_URL SUPABASE_KEY SESSION_SECRET"
args=()
for k in $KEYS; do
  # Take the first matching line, value after the first '=', strip wrapping quotes.
  v=$(grep -E "^${k}=" .env | head -1 | cut -d= -f2-)
  v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
  [ -n "$v" ] && args+=("${k}=${v}")
done
if [ ${#args[@]} -gt 0 ]; then
  echo "Staging ${#args[@]} secret(s)..."
  flyctl secrets set --stage -a "$APP" "${args[@]}"
fi

# 3. Deploy (build context = repo root; one always-on machine — scale later if needed).
echo "Deploying '$APP'..."
flyctl deploy --config scripts/fly.toml --dockerfile Dockerfile -a "$APP" --ha=false

echo "Deployed: https://${APP}.fly.dev  (admin at /admin)"
