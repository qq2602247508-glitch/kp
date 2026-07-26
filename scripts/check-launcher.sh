#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash -n "$repo_dir/scripts/launch-desktop.sh"
bash -n "$repo_dir/scripts/dev-backend.sh"
bash -n "$repo_dir/scripts/dev-frontend.sh"
bash -n "$repo_dir/启动本地COC-KP助手.command"

grep -F 'http://127.0.0.1:8010/api/v1/health' "$repo_dir/scripts/launch-desktop.sh" >/dev/null
grep -F 'http://127.0.0.1:5180/' "$repo_dir/scripts/launch-desktop.sh" >/dev/null
grep -F 'data/logs' "$repo_dir/scripts/launch-desktop.sh" >/dev/null
grep -F 'local-coc-kp-assistant/scripts/launch-desktop.sh' \
  "$repo_dir/启动本地COC-KP助手.command" >/dev/null

echo "Desktop launcher regression checks passed."
