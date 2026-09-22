"""OpenRouter provider (OpenAI-compatible chat completions + vision)."""
from __future__ import annotations

from .base import Provider, ProviderError, post_json
from .prompts import SYSTEM_CHAT, plan_prompt
from ..automation.screen import to_data_url

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(Provider):
    name = "openrouter"

    def _call(self, messages, max_tokens=1024, timeout=90):
        if not self.api_key:
            raise ProviderError("missing OpenRouter API key")
        headers = {"Authorization": "Bearer " + self.api_key,
                   "HTTP-Referer": "https://jarvisos.local",
                   "X-Title": "JARVISOS"}
        payload = {"model": self.model,
                   "messages": messages,
                   "max_tokens": max_tokens,
                   "temperature": 0.3}
        _, data = post_json(url=API_URL, payload=payload, headers=headers,
                            timeout=timeout)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (IndexError, KeyError, TypeError):
            raise ProviderError("unexpected OpenRouter response: %s" %
                                str(data)[:300])

    def ask(self, question, context=None):
        ctx = ""
        if context:
            ctx = "User context:\n- " + "\n- ".join(context) + "\n\n"
        return self._call([
            {"role": "system", "content": SYSTEM_CHAT},
            {"role": "user", "content": ctx + question}], max_tokens=800,
            timeout=60)

    def describe_image(self, image_bytes, prompt):
        if not image_bytes:
            raise ProviderError("no image to analyze")
        return self._call([
            {"role": "system", "content": SYSTEM_CHAT},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": to_data_url(image_bytes)}}]}],
            max_tokens=1500, timeout=120)

    def plan_actions(self, task, image_bytes, screen_size):
        text = self.describe_image(
            image_bytes, plan_prompt(task, screen_size))
        from .manager import extract_actions
        return extract_actions(text)
