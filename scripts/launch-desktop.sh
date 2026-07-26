#!/bin/bash
set -u

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_url="http://127.0.0.1:5180/"
backend_health="http://127.0.0.1:8010/api/v1/health"
frontend_health="http://127.0.0.1:5180/"
log_dir="$repo_dir/data/logs"
uv_cache_dir="/Users/inagi/codex/900-杂项/uv-cache"

mkdir -p "$log_dir"

is_ready() {
  /usr/bin/curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

if ! is_ready "$backend_health"; then
  nohup env UV_CACHE_DIR="$uv_cache_dir" \
    "$repo_dir/scripts/dev-backend.sh" \
    >"$log_dir/backend.log" 2>&1 &
fi

if ! is_ready "$frontend_health"; then
  nohup "$repo_dir/scripts/dev-frontend.sh" \
    >"$log_dir/frontend.log" 2>&1 &
fi

attempt=0
while [ "$attempt" -lt 60 ]; do
  if is_ready "$backend_health" && is_ready "$frontend_health"; then
    /usr/bin/open "$app_url"
    exit 0
  fi
  attempt=$((attempt + 1))
  sleep 1
done

echo "COC KP 助手未能在 60 秒内启动。" >&2
echo "后端日志：$log_dir/backend.log" >&2
echo "前端日志：$log_dir/frontend.log" >&2
echo
read -r -p "按回车键关闭窗口……" _
exit 1
