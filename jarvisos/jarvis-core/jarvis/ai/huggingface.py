"""Hugging Face Inference Providers (serverless inference endpoints)."""
from __future__ import annotations

import base64
import json
import urllib.request

from .base import Provider, ProviderError, post_json
from .prompts import SYSTEM_CHAT

ROUTER = "https://router.huggingface.co/hf-inference/models"


class HuggingFaceProvider(Provider):
    name = "huggingface"

    def _headers(self):
        return {"Authorization": "Bearer " + self.api_key} \
            if self.api_key else {}

    def ask(self, question, context=None):
        if not self.api_key:
            raise ProviderError("missing Hugging Face token")
        ctx = ""
        if context:
            ctx = "Context: " + "; ".join(context) + "\n"
        prompt = "%s\n%sQ: %s\nA:" % (SYSTEM_CHAT, ctx, question)
        url = "%s/%s" % (ROUTER, self.model)
        _, data = post_json(
            url, {"inputs": prompt,
                  "parameters": {"max_new_tokens": 400,
                                 "temperature": 0.4,
                                 "return_full_text": False}},
            headers=self._headers(), timeout=90)
        try:
            if isinstance(data, list):
                return data[0]["generated_text"].strip()
            return str(data.get("generated_text", data))[:2000]
        except (IndexError, KeyError, TypeError):
            raise ProviderError("unexpected HF response: %s" % str(data)[:300])

    def describe_image(self, image_bytes, prompt):
        """Visual question answering via a VLM endpoint."""
        if not self.api_key:
            raise ProviderError("missing Hugging Face token")
        if not image_bytes:
            raise ProviderError("no image to analyze")
        model = self.model if "vl" in self.model.lower() or \
            "llava" in self.model.lower() or "qwen" in self.model.lower() \
            else "Salesforce/blip-image-captioning-large"
        url = "%s/%s" % (ROUTER, model)
        payload = {"inputs": {
            "question": prompt,
            "image": base64.b64encode(image_bytes).decode("ascii")}}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in self._headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
        except Exception as exc:
            raise ProviderError("HF vision request failed: %s" % exc)
        try:
            if isinstance(body, list):
                return str(body[0].get("answer", body[0]))[:2000]
            return str(body)[:2000]
        except (IndexError, TypeError):
            raise ProviderError("unexpected HF vision response")

    def plan_actions(self, task, image_bytes, screen_size):
        # HF small VLMs are weak planners: describe first, then plan from text.
        desc = self.describe_image(
            image_bytes,
            "Describe every UI element, window, button and text field with "
            "approximate positions (screen %dx%d)." % screen_size)
        text = self.ask(
            "Screen description:\n%s\n\nTask: %s\n\nReply with ONLY JSON: "
            '{"actions":[{...}],"say":"..."} using click/key/type/open_app/'
            "wait actions." % (desc, task))
        from .manager import extract_actions
        return extract_actions(text)
