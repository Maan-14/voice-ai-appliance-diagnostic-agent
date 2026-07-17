#!/bin/bash
# PostToolUse hook: lint any Python file Claude just edited.
# Exit 2 feeds ruff's findings back to Claude so it fixes them immediately,
# instead of the issues surfacing later in pre-commit / CI.
set -u
input=$(cat)
path=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null)

[[ "$path" == *.py ]] || exit 0
[[ -f "$path" ]] || exit 0

# ruff may be a standalone binary or only importable as a module
if command -v ruff >/dev/null 2>&1; then
  ruff_cmd=(ruff)
elif python3 -m ruff --version >/dev/null 2>&1; then
  ruff_cmd=(python3 -m ruff)
else
  exit 0
fi

if ! "${ruff_cmd[@]}" check "$path" 1>&2; then
  exit 2   # PostToolUse: stderr is shown to Claude as feedback
fi
exit 0
