#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

scan_targets=()
for target in backend/src backend/alembic frontend/src; do
  if [ -e "$target" ]; then
    scan_targets+=("$target")
  fi
done

if [ "${#scan_targets[@]}" -eq 0 ]; then
  echo "Domain isolation: no production source targets found." >&2
  exit 2
fi

# Construct the expression in pieces so the scanner does not match its own policy.
legacy_prefix="dn"
legacy_suffix="d"
forbidden_expression="${legacy_prefix}${legacy_suffix}|dungeon[[:space:]_-]*master|armor_class|class_name|challenge_rating|encumbrance|price_cp|unit_weight_lb|five-foot|5-foot|strength[[:space:]]*[×x*][[:space:]]*15"

if rg -n -i \
  --glob '!**/*.map' \
  --glob '!**/dist/**' \
  "$forbidden_expression" \
  "${scan_targets[@]}"; then
  echo "Domain isolation failed: foreign-system terms found in production source." >&2
  exit 1
fi

if rg -n \
  --glob '!**/*.map' \
  --glob '!**/dist/**' \
  'localhost:5173|127\.0\.0\.1:5173|localhost:8000|127\.0\.0\.1:8000|DND_DM_' \
  "${scan_targets[@]}"; then
  echo "Domain isolation failed: foreign runtime namespace or ports found." >&2
  exit 1
fi

echo "Domain isolation check passed."
