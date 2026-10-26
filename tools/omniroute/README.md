# OmniRoute switch (coding helpers only)

OmniRoute is a free, open-source gateway that puts many AI providers behind one local address
(`http://127.0.0.1:20128`, OpenAI- and Anthropic-compatible). Here it is used only for side coding
work: scripts, reviews, improvements. **The scheduled bots never use it.** FACTORY, SHIP, STORY,
CLAIM, DEAL, KEEPER, SCOUT and LEARN keep running on Josh's Claude subscription, and nothing in
`autopilot/` calls OmniRoute.

## Turning it on or off

- **A whole session:** give the cloud environment the variable `OMNIROUTE=on`. The session-start
  hook (`.claude/hooks/session-start.sh`) then installs and starts OmniRoute when the session opens.
  Best done as a *separate* environment (for example "OmniRoute") so the bots' environment is untouched.
  Without the variable the hook exits at once. The hook only runs once it is on the repo's default branch (`main`).
- **Mid-session:** say "omni on" or "omni off", or run `tools/omniroute/omni.sh on` / `off`.

## Keys

Add the keys as environment variables in the environment's settings (never paste them in chat).
`omni.sh on` loads every one that is set:

| Variable | Provider | Free? |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini | free tier |
| `GROQ_API_KEY` | Groq (Llama, Kimi K2, Qwen) | free tier |
| `OPENROUTER_API_KEY` | OpenRouter (many `:free` models, incl. DeepSeek and Kimi) | free models |
| `CEREBRAS_API_KEY` | Cerebras | free tier |
| `NVIDIA_API_KEY` | NVIDIA NIM (DeepSeek, Kimi, Qwen) | free credits |
| `MISTRAL_API_KEY` | Mistral / Codestral | free tier |
| `DEEPSEEK_API_KEY` | DeepSeek direct | paid (cheap) |
| `MOONSHOT_API_KEY` | Kimi (Moonshot) direct | paid (cheap) |

The environment's network must allow the provider's API host. On Oct 26, 2026 only
`generativelanguage.googleapis.com` (Gemini) got through; these were refused and need adding under
Allowed domains: `api.groq.com`, `openrouter.ai`, `api.mistral.ai`, `api.cerebras.ai`,
`integrate.api.nvidia.com`, `api.deepseek.com`, `api.moonshot.ai`.

OmniRoute also ships "keyless" providers that ride on services which never offered an API
(DuckDuckGo chat, Chipotle's support bot, Augment, and others). The switch never routes to them.

## Commands

```
tools/omniroute/omni.sh status
tools/omniroute/omni.sh ask "write a bash script that ..."
cat autopilot/bin/scanner.py | tools/omniroute/omni.sh ask "find bugs in this"
OMNI_MODEL=gemini/gemini-2.5-flash tools/omniroute/omni.sh ask "..."
tools/omniroute/omni.sh claude -p "..."   # Claude Code worker on OmniRoute models
```

## Limits (tested Oct 26, 2026, OmniRoute 3.8.48)

- The chat you type into always runs on Josh's Claude plan; a cloud session's main model cannot be
  switched. OmniRoute does the side work you send it.
- `omni.sh claude` fails with Gemini: Gemini rejects a schema field (`prefixItems`) in Claude Code's
  tool definitions and OmniRoute 3.8.48 does not strip it. Not yet tested with the OpenAI-style
  providers (their hosts are blocked here).
- A cloud container is deleted when the session ends, so OmniRoute is reinstalled each session
  (about 3 minutes). On a Mac, `npm install -g omniroute` stays, and `omniroute launch` runs a whole
  Claude Code session on OmniRoute models.
- The admin password is random per container, kept in `~/.omniroute-secret/pw` (mode 600), and never written to the repo or the board.
