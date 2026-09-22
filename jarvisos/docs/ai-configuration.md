# AI provider configuration

JARVISOS uses **cloud AI only** (no local LLM fits a 4 GB laptop).
Providers are modular with automatic fallback:

```
preferred (ai.provider) → other configured providers → honest "offline" msg
```

## Setup (2 minutes)

1. Open **Settings → AI Providers**.
2. Pick a preferred provider, paste its key, optionally adjust the model,
   press **Test connection** (expects “JARVIS online.”).
3. Keys are stored in `~/.config/jarvisos/secrets.json` (mode 0600) —
   never in git, never in the ISO, never logged.

| Provider | Get a key | Default model | Notes |
|---|---|---|---|
| Gemini | [Google AI Studio](https://aistudio.google.com) | `gemini-3.8-flash` | best vision + low latency; free tier; auto-fallback on retired models |
| OpenRouter | [openrouter.ai](https://openrouter.ai) | `…-vision-instruct:free` | many models incl. free ones |
| Hugging Face | [tokens page](https://huggingface.co/settings/tokens) | `zephyr-7b-beta` | also powers cloud STT |

You can configure 1–3 providers; JARVIS fails over automatically.

## What the AI may receive

- Your typed/spoken question (+ optional local memory facts).
- One downscaled screenshot per automation batch / analysis request.
- Short voice clips only when cloud STT is used (push-to-talk).

Master switches: Settings → Privacy (`send_screenshots_to_ai`,
`send_voice_to_cloud`). Clap detection is always 100% local.

## Safety reminders

- The AI emits **structured actions only**; dangerous ones always confirm.
- If a provider is down, JARVIS says so and every offline feature keeps
  working (desktop, files, terminal, settings, clap, local commands).
