#!/bin/bash
# PreToolUse hook: block Claude from reading or writing .env files.
# They hold live OpenAI / Twilio / SMTP credentials; .env.example is the
# sanctioned template and stays accessible.
set -u
input=$(cat)
path=$(printf '%s' "$input" | python3 -c "import sys, json; print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))" 2>/dev/null)

base=$(basename "$path" 2>/dev/null || echo "")
# .env and variants (keep .env.example readable)
if [[ "$base" == ".env" || ( "$base" == .env.* && "$base" != ".env.example" ) ]]; then
  echo "Blocked: $path contains live credentials. Use .env.example for structure; ask the user to change real secrets themselves." >&2
  exit 2
fi
# Other common secret filenames in this project / local tooling
case "$base" in
  credentials.json|service-account*.json|*.pem|id_rsa|id_ed25519)
    echo "Blocked: $path looks like a secret key/credential file." >&2
    exit 2
    ;;
esac
exit 0
