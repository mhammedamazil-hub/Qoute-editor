"""Core pipeline: safe commands run, dangerous ones confirm, AI gates."""
import jarvis.control.apps as apps_mod
import jarvis.system.power as power_mod


def test_safe_query_runs(core):
    res = core.handle_text("what is using my ram?")
    assert res.ok and "RAM" in res.say
    assert res.needs_confirm is False


def test_open_app_routed(core, monkeypatch):
    calls = []
    monkeypatch.setattr(apps_mod, "launch",
                        lambda a, args=None: (calls.append(a), (True, "ok"))[1])
    res = core.handle_text("open blender")
    assert res.ok and calls == ["blender"]


def test_confirm_flow(core, monkeypatch):
    monkeypatch.setattr(power_mod, "reboot", lambda: (True, "rebooting"))
    res = core.handle_text("reboot")
    assert res.needs_confirm and res.confirm_token
    # wrong token → expired
    assert core.confirm("nope", True).ok is False
    # decline → cancelled, never executed
    res2 = core.handle_text("reboot")
    assert core.confirm(res2.confirm_token, False).say == "Cancelled."
    # accept → executes
    res3 = core.handle_text("reboot")
    done = core.confirm(res3.confirm_token, True)
    assert done.ok and done.say == "rebooting"


def test_deny_blocks(core):
    res = core.handle_text("format my disk")
    assert res.ok is False and res.needs_confirm is False


def test_clap_mapping(core, monkeypatch):
    monkeypatch.setattr(apps_mod, "launch",
                        lambda a, args=None: (True, "%s opened" % a))
    res = core.handle_clap("double")  # default map → open vs code
    assert res.ok and res.source == "clap"


def test_clap_unmapped(core):
    res = core.handle_clap("quadruple")
    assert res.ok is False


def test_ai_gated_without_keys(core):
    res = core.handle_text("what is the capital of France?")
    assert "API key" in res.say or "Settings" in res.say


def test_unknown_offline_helpful(core):
    res = core.handle_text("blorple the fnord")
    assert "what can you do" in res.say


def test_events_emitted(core):
    seen = []
    core.on_event(lambda e: seen.append(e["kind"]))
    core.handle_text("what is using my ram?")
    assert "say" in seen


def test_memory_learn_via_core(core):
    res = core.handle_text("call me Ada")
    assert res.ok and "Ada" in res.say
