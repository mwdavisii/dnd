#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${OLLAMA_HOST:-}" || -z "${OLLAMA_MODEL:-}" ]]; then
  echo "OLLAMA_HOST and OLLAMA_MODEL must be set."
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. pytest -m ollama -q "$@"
