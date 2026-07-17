#!/bin/bash
# PostToolUse (Edit|Write): after changes under app/agents/, verify the
# Realtime registry and Agents-SDK tool names still match. Exit 2 feeds the
# mismatch back so Claude fixes parity in the same turn.
set -u
input=$(cat)
path=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null)

case "$path" in
  */app/agents/tool_registry.py|*/app/agents/diagnostic_agent.py|*/app/agents/tools.py|*/app/agents/schemas.py)
    ;;
  *)
    exit 0
    ;;
esac

root="${CLAUDE_PROJECT_DIR:-.}"
cd "$root" || exit 0

# Prefer project venv if present (system python may lack deps).
if [[ -x "$root/.venv/bin/python" ]]; then
  py="$root/.venv/bin/python"
else
  py="python3"
fi

out=$("$py" - <<'PY' 2>&1
try:
    from app.agents.tool_registry import build_tool_registry
    from app.agents.diagnostic_agent import diagnostic_agent_factory
except Exception as exc:
    # Incomplete edit or missing local deps — skip rather than false-alarm.
    print(f"tool parity skipped ({type(exc).__name__}: {exc})")
    raise SystemExit(0)

reg = sorted(d.name for d in build_tool_registry().all())
sdk = sorted(t.name for t in diagnostic_agent_factory.build_agent().tools)
if set(reg) != set(sdk):
    print(f"TOOL PARITY BROKEN\n  registry={reg}\n  sdk={sdk}")
    raise SystemExit(2)
print("tool parity OK:", ", ".join(reg))
PY
)
status=$?
if [[ $status -ne 0 ]]; then
  printf '%s\n' "$out" >&2
  echo "Fix: keep tool_registry.py and diagnostic_agent.py tools=[...] in lockstep. See skill: add-agent-tool." >&2
  exit 2
fi
exit 0
