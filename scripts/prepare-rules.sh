#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is required. This script will not install it or download models." >&2
  exit 1
fi

installed_models="$(ollama list 2>/dev/null || true)"
for required_model in "bge-m3" "qwen3:30b-instruct"; do
  if ! grep -q "$required_model" <<<"$installed_models"; then
    echo "Missing installed model: $required_model (no automatic download)." >&2
    exit 1
  fi
done

backend/.venv/bin/python -m coc_kp_assistant.ingestion \
  --catalog config/source-packs.example.json \
  --output-root data/generated-content/coc7

backend/.venv/bin/python -m coc_kp_assistant.indexing \
  --generated-root data/generated-content/coc7 \
  --vector-root data/vectors

echo "COC7 rules corpus and vector index are ready."
