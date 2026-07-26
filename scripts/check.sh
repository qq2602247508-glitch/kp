#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

./scripts/check-domain-isolation.sh
./scripts/check-launcher.sh

require_all="${COC_KP_REQUIRE_ALL_CHECKS:-0}"

if [ -f backend/pyproject.toml ] && [ -x backend/.venv/bin/python ]; then
  uv run --project backend ruff check backend
  uv run --project backend mypy backend/src
  uv run --project backend pytest backend/tests
else
  if [ "$require_all" = "1" ]; then
    echo "Backend environment is not ready." >&2
    exit 2
  fi
  echo "Skipping backend checks: backend environment is not ready."
fi

if [ -x frontend/node_modules/.bin/vitest ]; then
  npm --prefix frontend run lint
  npm --prefix frontend run typecheck
  npm --prefix frontend test
  npm --prefix frontend run build
else
  if [ "$require_all" = "1" ]; then
    echo "Frontend dependencies are not ready." >&2
    exit 2
  fi
  echo "Skipping frontend checks: dependencies are not installed."
fi
