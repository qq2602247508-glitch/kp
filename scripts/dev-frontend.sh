#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:8010/api/v1}"
exec npm --prefix frontend run dev -- --host 127.0.0.1 --port 5180 --strictPort

