#!/bin/bash
# Starts OmniRoute only in cloud sessions whose environment sets OMNIROUTE=on.
# Every other session (including the scheduled bots) exits here at once.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
case "${OMNIROUTE:-off}" in on|ON|1|true|yes) ;; *) exit 0 ;; esac
if "$CLAUDE_PROJECT_DIR/tools/omniroute/omni.sh" on; then
  [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export OMNIROUTE_BASE_URL=http://127.0.0.1:${OMNIROUTE_PORT:-20128}" >> "$CLAUDE_ENV_FILE"
  echo "OmniRoute session: server running; use tools/omniroute/omni.sh for coding helpers."
else
  echo "OmniRoute session requested but setup failed; run tools/omniroute/omni.sh on to retry."
fi
exit 0
