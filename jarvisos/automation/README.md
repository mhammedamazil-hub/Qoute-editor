# Automation engine

Structured, batched, safety-validated screen control.

- Library: `jarvis-core/jarvis/automation/` (`engine.py`, `screen.py`)
- Safety policy: `jarvis-core/jarvis/permissions.py`
- CLI: `bin/jarvis-automate` (runs a JSON batch file, dry-run capable)

Pipeline: screenshot → AI analyzes once → 5–25 structured actions →
validator (DENY dropped, CONFIRM flagged) → engine executes → new
screenshot verifies. ESC / `jarvis stop` halts between any two actions.

Example batch file:

```json
{"task": "open the editor", "actions": [
  {"type": "open_app", "app": "editor"},
  {"type": "wait", "seconds": 2},
  {"type": "screenshot"}
]}
```

```bash
jarvis-automate plan.json --dry-run   # validate only, no execution
jarvis-automate plan.json --yes       # auto-approve CONFIRM actions (dangerous)
```
