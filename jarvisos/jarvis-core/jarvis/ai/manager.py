"""AIManager: provider selection, fallback chain, and batch planning.

- preferred provider first (config ai.provider), then the others that have
  keys, in a fixed order. A failed provider is skipped, never fatal.
- plan_from_screen(task): screenshot → analyze → strict-JSON action batch →
  validator pass (DENY actions dropped, CONFIRM actions kept but flagged).
"""
from __future__ import annotations

import json
import re

from .base import ProviderError
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider
from .huggingface import HuggingFaceProvider
from .. import permissions as _perm

ORDER = ("gemini", "openrouter", "huggingface")

DEFAULT_MODELS = {
    "gemini": "gemini-3.8-flash",
    "openrouter": "meta-llama/llama-3.2-11b-vision-instruct:free",
    "huggingface": "HuggingFaceH4/zephyr-7b-beta",
}

CLASSES = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    "huggingface": HuggingFaceProvider,
}


def extract_actions(text):
    """Pull the FIRST {...} JSON object out of model output.

    Returns (actions:list, say:str). Never raises — garbage in → ([], note).
    """
    text = (text or "").strip()
    start = text.find("{")
    if start < 0:
        return [], "The AI did not return a plan."
    depth, end = 0, -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return [], "The AI returned a broken plan."
    try:
        obj = json.loads(text[start:end])
    except ValueError:
        return [], "The AI returned invalid JSON."
    actions = obj.get("actions", [])
    say = str(obj.get("say", ""))[:300]
    if not isinstance(actions, list):
        return [], "The AI plan had no action list."
    clean = [a for a in actions if isinstance(a, dict)][:30]
    return clean, say or "Plan ready."


class AIManager:
    def __init__(self, config=None):
        from ..config import get_config
        self.config = config or get_config()
        self._providers = {}
        self.last_error = ""

    def _provider(self, name):
        if name not in self._providers:
            cls = CLASSES[name]
            key = self.config.get_secret(name)
            model = self.config.get("ai.%s_model" % name,
                                    DEFAULT_MODELS[name])
            self._providers[name] = cls(api_key=key, model=model)
        else:  # refresh key/model in case Settings changed them
            prov = self._providers[name]
            prov.api_key = self.config.get_secret(name)
            prov.model = self.config.get("ai.%s_model" % name,
                                         DEFAULT_MODELS[name])
        return self._providers[name]

    @property
    def configured_providers(self):
        return [n for n in ORDER if self._provider(n).configured]

    @property
    def configured(self):
        return bool(self.configured_providers)

    @property
    def preferred(self):
        want = (self.config.get("ai.provider", "gemini") or "gemini").lower()
        chain = [want] if want in ORDER else []
        return chain + [n for n in ORDER if n != want]

    def _each(self):
        for name in self.preferred:
            prov = self._provider(name)
            if prov.configured:
                yield prov

    # -- public API ----------------------------------------------------
    def ask(self, question, context=None):
        if not self.configured:
            return "No AI provider is configured. Add a key in Settings → AI Providers."
        for prov in self._each():
            try:
                answer = prov.ask(question, context)
                if answer:
                    return answer
            except ProviderError as exc:
                self.last_error = "%s: %s" % (prov.name, exc)
        return "All AI providers failed. %s" % self.last_error

    def describe_image(self, path, prompt):
        if not self.configured:
            return "No AI provider is configured. Add a key in Settings → AI Providers."
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            return "Could not read the screenshot."
        from ..automation.screen import downscale_for_ai
        small = downscale_for_ai(raw)
        if not small:
            return "Could not process the screenshot."
        for prov in self._each():
            try:
                answer = prov.describe_image(small, prompt)
                if answer:
                    return answer
            except ProviderError as exc:
                self.last_error = "%s: %s" % (prov.name, exc)
        return "All AI providers failed. %s" % self.last_error

    def plan_from_screen(self, task):
        """Full batch-planning pipeline. Returns {actions, say, shot}."""
        from ..automation.screen import capture, downscale_for_ai
        from ..system import display as _display
        if not self.configured:
            return {"actions": [],
                    "say": "No AI provider configured.",
                    "shot": ""}
        shot_path, raw = capture()
        small = downscale_for_ai(raw)
        if not small:
            return {"actions": [], "say": "Could not capture the screen.",
                    "shot": ""}
        w, h = _display.resolution()
        size = (w or 1920, h or 1080)
        errors = []
        for prov in self._each():
            try:
                actions, say = prov.plan_actions(task, small, size)
            except ProviderError as exc:
                errors.append("%s: %s" % (prov.name, exc))
                continue
            except Exception as exc:  # provider bug must not kill Core
                errors.append("%s: %s" % (prov.name, exc))
                continue
            if not actions:
                errors.append("%s: empty plan (%s)" % (prov.name, say))
                continue
            # validator pass: drop DENY, keep SAFE + flagged CONFIRM
            kept, dropped = [], 0
            for action in actions:
                verdict = _perm.classify_action(action)
                if verdict.level == _perm.DENY:
                    dropped += 1
                    continue
                if verdict.level == _perm.CONFIRM:
                    action = dict(action)
                    action["_needs_confirm"] = True
                kept.append(action)
            if dropped:
                say += " (%d unsafe actions removed.)" % dropped
            return {"actions": kept, "say": say, "shot": shot_path,
                    "provider": prov.name}
        return {"actions": [],
                "say": "Planning failed: %s" % "; ".join(errors)[:300],
                "shot": shot_path}
