"""Google Gemini provider (generateContent REST API, incl. vision)."""
from __future__ import annotations

import base64

from .base import Provider, ProviderError, post_json
from .prompts import SYSTEM_CHAT, plan_prompt

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Older Flash models get retired for new keys — walk the chain on 404.
MODEL_FALLBACKS = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
                   "gemini-3.5-flash", "gemini-flash-latest")


class GeminiProvider(Provider):
    name = "gemini"

    def _call(self, parts, max_tokens=1024, timeout=60):
        if not self.api_key:
            raise ProviderError("missing Gemini API key")
        models = [self.model] if self.model else []
        models += [m for m in MODEL_FALLBACKS if m not in models]
        last_error = None
        for model in models:
            url = "%s/%s:generateContent?key=%s" % (
                API_ROOT, model, self.api_key)
            payload = {
                "system_instruction": {"parts": [{"text": SYSTEM_CHAT}]},
                "contents": [{"parts": parts}],
                "generationConfig": {"maxOutputTokens": max_tokens,
                                     "temperature": 0.3},
            }
            try:
                _, data = post_json(url, payload, timeout=timeout)
                self.model = model  # remember the working model
                break
            except ProviderError as exc:
                last_error = exc
                if "404" not in str(exc):
                    raise
                continue
        else:
            raise last_error
        try:
            cands = data.get("candidates", [])
            texts = []
            for part in cands[0]["content"]["parts"]:
                if "text" in part:
                    texts.append(part["text"])
            return "".join(texts).strip()
        except (IndexError, KeyError, TypeError):
            raise ProviderError("unexpected Gemini response: %s" %
                                str(data)[:300])

    def ask(self, question, context=None):
        ctx = ""
        if context:
            ctx = "User context:\n- " + "\n- ".join(context) + "\n\n"
        return self._call([{"text": ctx + question}], max_tokens=800)

    def describe_image(self, image_bytes, prompt):
        if not image_bytes:
            raise ProviderError("no image to analyze")
        parts = [
            {"text": prompt},
            {"inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("ascii")}},
        ]
        return self._call(parts, max_tokens=1200, timeout=90)

    def plan_actions(self, task, image_bytes, screen_size):
        text = self.describe_image(
            image_bytes, plan_prompt(task, screen_size))
        from .manager import extract_actions
        return extract_actions(text)
