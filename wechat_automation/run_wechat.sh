#!/usr/bin/env bash
set -euo pipefail

TASK_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$TASK_ROOT"

if [[ -x ".venv/bin/python" ]]; then
  exec .venv/bin/python -m wechat_automation "$@"
fi
exec python3 -m wechat_automation "$@"
