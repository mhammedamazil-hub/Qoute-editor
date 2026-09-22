# AI providers (modular cloud AI)

- Library: `jarvis-core/jarvis/ai/` — `manager.py` + `gemini.py`,
  `openrouter.py`, `huggingface.py`, `prompts.py`, `base.py`.
- No local LLM anywhere (4 GB RAM target). Providers are tried in order:
  preferred (`ai.provider`) → remaining configured ones. Any failure
  falls through; offline → honest "unavailable" message, OS keeps working.
- Keys: Settings → AI Providers → stored in `~/.config/jarvisos/secrets.json`
  (0600). Never in git, never in the ISO. See
  [docs/ai-configuration.md](../docs/ai-configuration.md).
- Vision: `AIManager.plan_from_screen(task)` — one screenshot, one analysis
  pass, one strict-JSON batch of 5–25 structured actions, validator pass,
  engine executes, new screenshot verifies.

Adding a provider = new `Provider` subclass + one line in `manager.CLASSES`.
