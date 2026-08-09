#!/usr/bin/env bash
# deploy.sh — pull latest, rebuild the image, restart the bot.
#
# Runs ON the VPS (tars-prod) as the `tars` user. Idempotent; safe anytime.
#
# Mirrors the TARS deploy.sh contract: the remote checkout is disposable and
# gets hard-reset to origin, so never edit files directly on the box — commit
# and push instead, then run this.
#
# Secrets are not touched here. They live in /etc/caltrack/caltrack.env and are
# read by docker-compose.yml via env_file.
#
# Usage:
#   ./deploy.sh              # deploy origin/master
#   BRANCH=some-branch ./deploy.sh

set -euo pipefail

BRANCH="${BRANCH:-master}"
cd "$(dirname "$0")"

echo "==> Fetching origin/$BRANCH"
git fetch --all --prune
git reset --hard "origin/$BRANCH"
echo "    now at: $(git log --oneline -1)"

echo "==> Rebuilding + restarting"
docker compose up -d --build

echo "==> Waiting for startup"
sleep 10

echo
docker compose ps
echo
echo "==> Recent logs"
docker compose logs --tail 30

echo
echo "✓ deploy complete"
