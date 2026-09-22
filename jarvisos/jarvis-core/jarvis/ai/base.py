"""Shared HTTP + error helpers for AI providers."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class ProviderError(Exception):
    pass


def post_json(url, payload, headers=None, timeout=60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        try:
            return resp.status, json.loads(body)
        except ValueError:
            return resp.status, {"_raw": body}
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", "replace")[:400]
        except Exception:
            detail = ""
        raise ProviderError("HTTP %s: %s" % (exc.code, detail))
    except Exception as exc:  # network down, DNS, timeout…
        raise ProviderError("request failed: %s" % exc)


class Provider:
    """Base class. Subclasses implement ask() and describe_image()."""

    name = "base"

    def __init__(self, api_key="", model=""):
        self.api_key = api_key or ""
        self.model = model or ""

    @property
    def configured(self):
        return bool(self.api_key)

    def ask(self, question, context=None):
        raise NotImplementedError

    def describe_image(self, image_bytes, prompt):
        raise NotImplementedError

    def plan_actions(self, task, image_bytes, screen_size):
        """Vision → structured action batch. Returns (actions, say)."""
        raise NotImplementedError
