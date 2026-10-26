# Notes for Claude sessions in this repo

## OmniRoute switch
- `tools/omniroute/` holds an on/off switch for OmniRoute, a local AI gateway for side coding work. See `tools/omniroute/README.md`.
- When Josh says "omni on", "omni off" or "omni status", run `tools/omniroute/omni.sh on|off|status`.
- A session whose environment sets `OMNIROUTE=on` starts it automatically through `.claude/hooks/session-start.sh`.
- Never point the scheduled bots, their prompts or anything in `autopilot/` at OmniRoute. They run on Josh's Claude subscription.
- Provider keys live only in environment variables. Never put a key or the OmniRoute admin password in chat, on the board, in a doc or in a commit.
