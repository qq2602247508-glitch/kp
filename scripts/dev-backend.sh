#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [ ! -f backend/pyproject.toml ]; then
  echo "Backend has not been scaffolded yet." >&2
  exit 2
fi

mkdir -p "$repo_dir/data"

if [ -f backend/alembic.ini ]; then
  uv run --project backend alembic -c backend/alembic.ini upgrade head
fi

export COC_KP_HOST="${COC_KP_HOST:-127.0.0.1}"
export COC_KP_PORT="${COC_KP_PORT:-8010}"
exec uv run --project backend uvicorn coc_kp_assistant.app:app \
  --host "$COC_KP_HOST" \
  --port "$COC_KP_PORT"
