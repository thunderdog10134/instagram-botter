#!/bin/bash
# Restores ~/autopilot from the code zip URL in $1 (ops/autopilot.codeZip). The session writes ~/secrets/connect.json
# from the Drive file "AgentCity-autopilot-connect.json" before running this, then tokens are refilled from the vault.
set -e
mkdir -p ~/autopilot/{bin,queue,out,state,kits,logs} ~/secrets && chmod 700 ~/autopilot ~/secrets
curl -sS -f -L -o /tmp/ap-restore.zip "$1"
cd ~ && unzip -oq /tmp/ap-restore.zip && rm -f /tmp/ap-restore.zip
chmod +x ~/autopilot/bin/*.py ~/autopilot/bin/*.sh
chmod 600 ~/secrets/*.json 2>/dev/null || true
test -f ~/secrets/connect.json && python3 ~/autopilot/bin/connect_pull.py --all || echo "connect.json missing: write it from Drive first"
