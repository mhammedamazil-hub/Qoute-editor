"""AI manager: JSON extraction + provider fallback (stubbed, offline)."""
from jarvis.ai import manager as M


def test_extract_actions_clean():
    actions, say = M.extract_actions(
        '{"actions":[{"type":"click","x":1,"y":2}],"say":"hi"}')
    assert actions == [{"type": "click", "x": 1, "y": 2}]
    assert say == "hi"


def test_extract_actions_markdown_wrapped():
    actions, say = M.extract_actions(
        'Here you go:\n```json\n{"actions":[],"say":"done"}\n```')
    assert actions == [] and say == "done"


def test_extract_actions_garbage():
    actions, say = M.extract_actions("sorry, no plan today")
    assert actions == []
    actions, _ = M.extract_actions('{"actions": "notalist"}')
    assert actions == []
    actions, _ = M.extract_actions('{"actions":[{bad json')
    assert actions == []


class _Stub:
    name = "stub"

    def __init__(self, api_key="", model="", text="", fail=False):
        self.api_key = api_key
        self.model = model
        self._text = text
        self._fail = fail

    @property
    def configured(self):
        return bool(self.api_key)

    def ask(self, question, context=None):
        if self._fail:
            from jarvis.ai.base import ProviderError
            raise ProviderError("boom")
        return self._text


def test_fallback_chain(config, monkeypatch):
    config.set_secret("gemini", "K1")
    config.set_secret("openrouter", "K2")
    good = _Stub(api_key="K2", text="hello from stub")
    bad = _Stub(api_key="K1", fail=True)
    monkeypatch.setitem(M.CLASSES, "gemini", lambda **kw: bad)
    monkeypatch.setitem(M.CLASSES, "openrouter", lambda **kw: good)

    mgr = M.AIManager(config=config)
    assert mgr.configured is True
    assert mgr.ask("hi?") == "hello from stub"


def test_unconfigured_message(config):
    mgr = M.AIManager(config=config)
    assert mgr.configured is False
    assert "Settings" in mgr.ask("hi?")


def test_gemini_model_fallback(monkeypatch):
    from jarvis.ai import gemini as G
    from jarvis.ai.base import ProviderError
    calls = []

    def fake_post(url, payload, timeout=60):
        calls.append(url)
        if "gemini-3.8-flash" in url:
            raise ProviderError("HTTP 404: model not found")
        return 200, {"candidates": [{"content": {"parts": [
            {"text": "JARVIS online."}]}}]}

    monkeypatch.setattr(G, "post_json", fake_post)
    prov = G.GeminiProvider(api_key="K", model="gemini-3.8-flash")
    assert prov.ask("hi?") == "JARVIS online."
    assert len(calls) == 2 and prov.model == "gemini-3.7-flash"
