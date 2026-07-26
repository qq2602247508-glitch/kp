#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [ -f backend/pyproject.toml ]; then
  if [ -f backend/uv.lock ]; then
    uv sync --project backend --locked --extra dev
  else
    uv sync --project backend --extra dev
  fi
fi

if [ -f frontend/package-lock.json ]; then
  npm --prefix frontend ci
else
  npm --prefix frontend install
fi

if [ -f backend/alembic.ini ]; then
  uv run --project backend alembic -c backend/alembic.ini upgrade head
fi

echo "Setup complete. Run ./scripts/dev.sh"
