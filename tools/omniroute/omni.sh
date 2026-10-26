#!/usr/bin/env bash
# OmniRoute switch for Claude Code cloud sessions.
# For coding helpers only. The scheduled bots (FACTORY, SHIP, STORY, ...) never use it:
# they keep running on Josh's Claude subscription.
#
#   omni.sh on        install if missing, start the server, load provider keys from env vars
#   omni.sh off       stop the server
#   omni.sh status    is it up, which providers are connected, which model is the default
#   omni.sh ask "..." one-shot question through OmniRoute; piped text is added under it:
#                     cat script.py | omni.sh ask "improve this script"
#   omni.sh claude -p "..."   run a Claude Code worker whose model calls go through OmniRoute
#                     (fails with Gemini in 3.8.48: Gemini rejects a field in Claude Code's tool schemas)
#
# Provider keys come from environment variables set in the cloud environment's settings:
#   GEMINI_API_KEY  GROQ_API_KEY  OPENROUTER_API_KEY  MISTRAL_API_KEY
#   DEEPSEEK_API_KEY  MOONSHOT_API_KEY (Kimi)  CEREBRAS_API_KEY  NVIDIA_API_KEY
# OMNI_MODEL picks the model (default: the best coding model of your connected providers).
set -euo pipefail

VERSION="${OMNIROUTE_VERSION:-3.8.48}"
PORT="${OMNIROUTE_PORT:-20128}"
BASE="http://127.0.0.1:${PORT}"
SECRET="${HOME}/.omniroute-secret"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Built-in keyless providers that ride on services which never offered an API: never route to them.
SKIP_PREFIXES='aug|auto|ddgw|mcode|no-think|oc|pepper|tllm|veo-free|veoaifree-web|pol'

say() { echo "omniroute: $*" >&2; }

install() {
  if command -v omniroute >/dev/null 2>&1; then return 0; fi
  say "installing omniroute@${VERSION} (about 3 minutes the first time)"
  npm install -g --no-fund --no-audit "omniroute@${VERSION}" > /tmp/omniroute-install.log 2>&1 \
    || { say "npm install failed, see /tmp/omniroute-install.log"; return 1; }
}

password() {
  mkdir -p "$SECRET" && chmod 700 "$SECRET"
  if [ ! -s "$SECRET/pw" ]; then openssl rand -base64 24 > "$SECRET/pw"; fi
  chmod 600 "$SECRET/pw"
}

up() { [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' "$BASE/v1/models" 2>/dev/null)" = "200" ]; }

start() {
  if up; then return 0; fi
  ( cd "$HOME" && INITIAL_PASSWORD="$(cat "$SECRET/pw")" PORT="$PORT" \
      setsid nohup omniroute serve > "$SECRET/serve.log" 2>&1 & )
  for _ in $(seq 1 40); do sleep 2; if up; then return 0; fi; done
  say "server did not come up, see $SECRET/serve.log"; return 1
}

load_keys() {
  local n=0 var provider pair
  for pair in GEMINI_API_KEY:gemini GROQ_API_KEY:groq OPENROUTER_API_KEY:openrouter MISTRAL_API_KEY:mistral \
              DEEPSEEK_API_KEY:deepseek MOONSHOT_API_KEY:moonshot CEREBRAS_API_KEY:cerebras NVIDIA_API_KEY:nvidia; do
    var="${pair%%:*}"; provider="${pair##*:}"
    if [ -n "${!var:-}" ]; then
      OMNI_KEY_VALUE="${!var}" node "$HERE/addkey.mjs" add "$provider" "${provider} (env ${var})" >/dev/null
      n=$((n+1))
    fi
  done
  say "${n} provider key(s) loaded from the environment"
  # the server picks up new keys within a few seconds
  if [ "$n" -gt 0 ]; then for _ in $(seq 1 10); do [ -n "$(own_models)" ] && break; sleep 1; done; fi
}

# Models from Josh's own provider keys, best free-tier coding pick first.
own_models() {
  curl -s -m 10 "$BASE/v1/models" | SKIP="$SKIP_PREFIXES" python3 -c '
import json, os, re, sys
skip = re.compile(r"^(" + os.environ["SKIP"] + r")/")
ids = [m["id"] for m in json.load(sys.stdin).get("data", []) if not skip.match(m["id"])]
prefer = [r"kimi-k2", r"deepseek-(v3|chat|coder)", r"gemini-2\.5-flash$", r"gemini-[0-9.]+-flash$", r"qwen.*coder", r"llama-3\.3-70b", r"codestral", r"mistral-large", r":free$"]
def rank(i):
    for n, p in enumerate(prefer):
        if re.search(p, i):
            return n
    return len(prefer)
for i in sorted(ids, key=rank):
    print(i)'
}

model() {
  if [ -n "${OMNI_MODEL:-}" ]; then echo "$OMNI_MODEL"; return; fi
  local all; all="$(own_models)"
  if [ -z "$all" ]; then say "no provider connected yet: add a key (see tools/omniroute/README.md)"; return 1; fi
  echo "${all%%$'\n'*}"
}

ask() {
  local m extra=""; m="$(model)"
  if [ ! -t 0 ]; then extra="$(cat)"; fi
  python3 -c '
import json, sys, urllib.error, urllib.request
base, model, prompt, extra = sys.argv[1:5]
if extra:
    prompt = prompt + "\n\n" + extra
body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
req = urllib.request.Request(base + "/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
try:
    print(json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"])
except urllib.error.HTTPError as e:
    print("omniroute error:", e.read().decode()[:500], file=sys.stderr)
    sys.exit(1)' "$BASE" "$m" "$1" "$extra"
}

cmd="${1:-status}"; shift || true
case "$cmd" in
  on)
    install; password; start; load_keys
    say "on at $BASE" ;;
  off)
    if command -v omniroute >/dev/null 2>&1; then (cd "$HOME" && omniroute stop >/dev/null 2>&1) || true; fi
    pkill -f '[o]mniroute serve' 2>/dev/null || true
    say "off" ;;
  status)
    if ! command -v omniroute >/dev/null 2>&1; then echo "not installed"; exit 0; fi
    if up; then echo "running at $BASE"; else echo "installed, not running"; exit 0; fi
    echo "providers:"; node "$HERE/addkey.mjs" list | sed 's/^/  /' || true
    echo "models from your providers: $(own_models | wc -l)"
    echo "default model: $(model 2>/dev/null || echo none)" ;;
  ask)
    ask "$*" ;;
  claude)
    m="$(model)"
    mkdir -p "$SECRET/claude-profile"
    ANTHROPIC_BASE_URL="$BASE" ANTHROPIC_AUTH_TOKEN="omniroute-local" ANTHROPIC_API_KEY="" \
    ANTHROPIC_MODEL="$m" ANTHROPIC_SMALL_FAST_MODEL="$m" CLAUDE_CONFIG_DIR="$SECRET/claude-profile" \
      exec claude "$@" ;;
  *)
    echo "usage: omni.sh on|off|status|ask \"question\"|claude [claude args]" >&2; exit 2 ;;
esac
