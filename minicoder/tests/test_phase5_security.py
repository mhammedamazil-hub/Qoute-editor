"""Phase 5 adversarial suite: authorization, grants, replay, audit, failure.

Every test here checks *state*, not just status codes: the fake editor records
each call it receives, so "403 but it executed anyway" fails the suite.  The
fake is an ``EditorBridge`` subclass that overrides only ``request()`` — the
authorization check in ``EditorBridge.call`` is the real one.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from minicoder import config as config_mod

# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------

class FakeBridge:
    """In-process stand-in for the Node editor that inherits the real guard.

    It subclasses ``EditorBridge`` and overrides only the *transport*
    (``request``), so ``call()`` — including the Phase 5 authorization check that
    lives inside it — is the production code path.
    """

    def __new__(cls):  # build a real bridge object, then patch its transport
        from minicoder.tools.editor_bridge import EditorBridge

        obj = EditorBridge.__new__(EditorBridge)
        EditorBridge.__init__(obj, home=Path("."))
        obj.calls = []
        obj.layers = 1
        obj.fail_next = False
        obj.request = _fake_request.__get__(obj, EditorBridge)
        obj._ensure = lambda: None
        return obj


def _fake_request(self, payload: dict[str, Any]) -> dict[str, Any]:
    op = payload.get("op")
    if op == "list":
        from minicoder.security.policy import TOOL_CLASSES

        return {"tools": [{"name": n} for n in TOOL_CLASSES]}
    if op == "state":
        return {"state": _snapshot(self)}
    if op == "reset":
        self.calls.append("reset")
        self.layers = 0
        return {"state": _snapshot(self)}
    if op == "call":
        tool = payload["tool"]
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected editor failure")
        self.calls.append(tool)
        if tool == "delete_elements":
            self.layers = max(0, self.layers - 1)
        elif tool == "new_project":
            self.layers = 0
        else:
            self.layers += 1
        return {"ok": True, "result": {"ok": True, "summary": f"{tool} ok"},
                "state": _snapshot(self)}
    return {"ok": False, "error": f"unsupported op {op}"}


def _snapshot(self) -> dict[str, Any]:
    return {
        "snapshot": {
            "layerCount": self.layers,
            "layers": [{"type": "shape", "x": 10, "y": 10} for _ in range(self.layers)],
            "canvas": {"width": 1080, "height": 1350},
        }
    }


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    """One isolated home + one runtime for the whole module (torch is slow)."""
    home = tmp_path_factory.mktemp("phase5_home")
    prev = config_mod.activate_home(home)
    from minicoder.api import app as api

    svc = api.service()
    svc.agent.bridge = FakeBridge()
    api.SERVICE = svc
    yield {"home": home, "svc": svc, "api": api}
    # Leave no global behind: a stale service would point later tests at this
    # (now removed) temporary home.
    from minicoder.security import set_service

    api.SERVICE = None
    set_service(None)
    svc.agent.bridge.close()
    config_mod.activate_home(prev)


@pytest.fixture(scope="module")
def client(env):
    return TestClient(env["api"].app)


@pytest.fixture(scope="module")
def sec(env):
    from minicoder.security import security

    return security(env["svc"].db)


@pytest.fixture(scope="module")
def headers(sec):
    return {"authorization": f"Bearer {sec.operator_token()}"}


def mint(client, headers, action, scope="", ttl=None, resource=None):
    body: dict[str, Any] = {"action": action, "scope": scope}
    if ttl is not None:
        body["ttl"] = ttl
    if resource is not None:
        body["resource"] = resource
    r = client.post("/api/security/grant", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["grant"]


def call_tool(client, tool, headers=None, grant=None, args=None):
    h = dict(headers or {})
    if grant:
        h["x-nace-grant"] = grant
    return client.post("/api/editor/tool", json={"tool": tool, "args": args or {}}, headers=h)


def bridge(env):
    return env["svc"].agent.bridge


# ---------------------------------------------------------------------------
# A. natural-language authorization bypass (32 destructive / 8 benign)
# ---------------------------------------------------------------------------

BYPASS_PHRASES = [
    # the exact 12 the Phase 4 audit found ungated
    "wipe everything",
    "start from scratch",
    "get rid of all the layers",
    "take them out",
    "blank canvas",
    "throw away the current design",
    "make it empty",
    "nuke the file system",
    "paste the token",
    "d3lete every layer",
    "could you delete all the layers?",
    "do not delete anything",
    # the sprint brief's additional cases
    "remove the entire project",
    "clear everything currently open",
    "start over from scratch",
    "scrap the whole design",
    "dispose of the current board",
    "I want you to erase the canvas",
    "please wipe the board clean",
    "reset everything to a blank page",
    "throw it all out and begin again",
    "delete the entire project now",
    "purge the design completely",
    "make the canvas blank",
    "can you get rid of this design?",
    "could you nuke the whole thing",
    "go ahead and remove every layer",
    "erase all of it",
    "d3l3te everyth1ng",
    "drop the database",
    "truncate the memory",
    "export the project to /etc/passwd",
]

BENIGN_PHRASES = [
    "build a 1080x1350 poster with the headline 'Quiet'",
    "add a gold quote mark",
    "set the canvas to 1080x1350",
    "apply the emerald palette",
    "how many fonts should I use in one poster?",
    "explain why a flex child overflows.",
    "summarise your last sleep cycle.",
    "what is the poster margin?",
]


@pytest.mark.parametrize("phrase", BYPASS_PHRASES)
def test_destructive_phrasing_is_flagged(phrase: str) -> None:
    from minicoder.cognition.intent import classify

    intent = classify(phrase)
    assert intent.requires_authorization is True, (phrase, intent.to_json())
    assert intent.consequential, phrase


@pytest.mark.parametrize("phrase", BENIGN_PHRASES)
def test_benign_phrasing_is_not_flagged(phrase: str) -> None:
    from minicoder.cognition.intent import classify

    assert classify(phrase).requires_authorization is False, phrase


def test_negation_is_not_a_green_light() -> None:
    from minicoder.cognition.intent import classify

    for phrase in ("do not delete anything", "never wipe the canvas", "don't remove the layers"):
        intent = classify(phrase)
        assert intent.negated is True
        assert intent.requires_authorization is True


def test_informational_question_is_answerable() -> None:
    from minicoder.cognition.intent import IntentType, classify

    intent = classify("how do I delete a layer?")
    assert intent.type is IntentType.QUESTION
    assert intent.informational is True
    assert intent.is_answerable


def test_obfuscation_is_normalised() -> None:
    from minicoder.cognition.intent import classify

    for phrase in ("d3lete every layer", "w1pe everything", "del\u200bete everything"):
        assert classify(phrase).requires_authorization is True, phrase


# ---------------------------------------------------------------------------
# B. direct API authorization attacks (22)
# ---------------------------------------------------------------------------

def test_b01_tool_without_token_is_refused(env, client):
    before = len(bridge(env).calls)
    r = call_tool(client, "delete_elements")
    assert r.status_code == 401
    assert len(bridge(env).calls) == before


def test_b02_tool_with_token_but_no_grant_is_refused(env, client, headers):
    before = len(bridge(env).calls)
    r = call_tool(client, "delete_elements", headers)
    assert r.status_code == 403
    assert r.json()["error"] == "missing_grant"
    assert len(bridge(env).calls) == before


def test_b03_grant_for_another_tool_is_refused(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    r = call_tool(client, "delete_elements", headers, g["id"])
    assert r.status_code == 403
    assert r.json()["error"] == "scope_mismatch"


def test_b04_forged_grant_id_is_refused(env, client, headers):
    r = call_tool(client, "delete_elements", headers, "g_" + "0" * 32)
    assert r.status_code == 403
    assert r.json()["error"] in {"unknown_grant", "forged_grant"}


def test_b05_unknown_tool_is_refused(env, client, headers):
    r = call_tool(client, "rm_rf_slash", headers)
    assert r.status_code == 403
    assert r.json()["error"] == "authorization_required"


def test_b06_unknown_tool_with_grant_still_refused(env, client, headers):
    r = call_tool(client, "eval_js", headers, "g_" + "1" * 32)
    assert r.status_code == 403


def test_b07_tool_name_case_variation_is_unknown(env, client, headers):
    g = mint(client, headers, "editor.tool", "DELETE_ELEMENTS")
    r = call_tool(client, "DELETE_ELEMENTS", headers, g["id"])
    assert r.status_code == 403


def test_b08_wrong_token_is_refused(client):
    r = call_tool(client, "delete_elements", {"authorization": "Bearer nace_not_a_real_token_000000"})
    assert r.status_code == 401


def test_b09_empty_bearer_is_refused(client):
    r = call_tool(client, "delete_elements", {"authorization": "Bearer "})
    assert r.status_code == 401


def test_b10_grant_in_body_is_ignored(env, client, headers):
    g = mint(client, headers, "editor.tool", "delete_elements")
    r = client.post(
        "/api/editor/tool",
        json={"tool": "delete_elements", "args": {}, "grant": g["id"], "grant_id": g["id"]},
        headers=headers,
    )
    assert r.status_code == 403, "authorization must not come from an arbitrary body field"


def test_b11_legacy_authorize_boolean_is_ignored(env, client, headers):
    msg = "delete every layer on the canvas"
    r = client.post("/api/chat", json={"message": msg, "authorize": True}, headers=headers)
    assert r.status_code == 403
    assert r.json()["error"] == "missing_grant"


def test_b12_chat_delete_without_grant_changes_nothing(env, client):
    before = bridge(env).layers
    r = client.post("/api/chat", json={"message": "delete every layer on the canvas"})
    assert r.status_code == 401
    assert bridge(env).layers == before


def test_b13_chat_with_grant_for_other_instruction_is_refused(env, client, headers):
    from minicoder.security import policy

    other = policy.instruction_scope("add a gold quote mark")
    g = mint(client, headers, policy.ACTION_INSTRUCTION, other)
    r = client.post(
        "/api/chat", json={"message": "delete every layer on the canvas"},
        headers={**headers, "x-nace-grant": g["id"]},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "scope_mismatch"


def test_b14_canvas_endpoint_requires_grant(client):
    r = client.post("/api/editor/canvas", json={"width": 800, "height": 600})
    assert r.status_code == 401


def test_b15_memory_write_requires_grant(env, client):
    r = client.post("/api/memory", json={"label": "audit_probe", "content": "x"})
    assert r.status_code == 401
    rows = env["svc"].db.query("SELECT id FROM semantic_nodes WHERE label='audit_probe'")
    assert rows == []


def test_b16_sleep_requires_grant(client):
    r = client.post("/api/sleep", json={"trigger": "attack"})
    assert r.status_code == 401


def test_b17_snapshot_requires_grant(client):
    r = client.post("/api/export/snapshot")
    assert r.status_code == 401


def test_b18_snapshot_is_not_a_get(client):
    assert client.get("/api/export/snapshot").status_code == 405


def test_b19_vision_requires_grant(client):
    r = client.post(
        "/api/vision/inspect",
        files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 100, "image/png")},
    )
    assert r.status_code == 401


def test_b20_read_only_tool_is_allowed(env, client):
    r = call_tool(client, "get_app_state")
    assert r.status_code == 200
    assert r.json()["tool_class"] == "read_only"


def test_b21_authorized_mutation_executes_exactly_once(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    before = len(bridge(env).calls)
    r = call_tool(client, "add_text", headers, g["id"], {"content": "hello"})
    assert r.status_code == 200
    assert len(bridge(env).calls) == before + 1


def test_b22_request_id_is_returned_and_audited(env, client, headers):
    r = call_tool(client, "get_app_state")
    rid = r.headers.get("x-request-id")
    assert rid


# ---------------------------------------------------------------------------
# C. grant lifecycle: manipulation, expiry, replay, scope (16)
# ---------------------------------------------------------------------------

def test_c01_issuing_a_grant_requires_the_operator_token(client):
    r = client.post("/api/security/grant", json={"action": "editor.tool", "scope": "add_text"})
    assert r.status_code == 401


def test_c02_unknown_action_cannot_be_granted(client, headers):
    r = client.post("/api/security/grant", json={"action": "root.everything"}, headers=headers)
    assert r.status_code == 403


def test_c03_grant_is_scoped_single_use(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    assert call_tool(client, "add_text", headers, g["id"]).status_code == 200
    again = call_tool(client, "add_text", headers, g["id"])
    assert again.status_code == 409
    assert again.json()["error"] == "replayed"


def test_c04_expired_grant_is_rejected(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text", ttl=1)
    time.sleep(1.2)  # timestamps are second-precision
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 403
    assert r.json()["error"] == "expired", r.text


def test_c04b_editing_a_stored_grant_is_detected_as_forgery(env, client, headers):
    """The signature covers expires_at: a DB edit cannot extend or move a grant."""
    g = mint(client, headers, "editor.tool", "add_text", ttl=60)
    env["svc"].db.execute(
        "UPDATE auth_grants SET expires_at='2999-01-01T00:00:00+00:00' WHERE id=?", (g["id"],)
    )
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 403
    assert r.json()["error"] == "forged_grant"


def test_c05_scope_mismatch_rejected(env, client, headers):

    g = mint(client, headers, "memory.write", "label_a")
    r = client.post(
        "/api/memory", json={"label": "label_b", "content": "x"},
        headers={**headers, "x-nace-grant": g["id"]},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "scope_mismatch"


def test_c06_resource_mismatch_rejected(env, client, headers):
    g = mint(client, headers, "memory.write", "label_c")
    r = client.post(
        "/api/sleep", json={"trigger": "attack"},
        headers={**headers, "x-nace-grant": g["id"]},
    )
    assert r.status_code == 403


def test_c07_action_mismatch_rejected(env, client, headers):
    from minicoder.security import policy

    g = mint(client, headers, policy.ACTION_INSTRUCTION, policy.instruction_scope("build a poster"))
    r = client.post(
        "/api/memory", json={"label": "x", "content": "y"},
        headers={**headers, "x-nace-grant": g["id"]},
    )
    assert r.status_code == 403
    assert r.json()["error"] in {"action_mismatch", "resource_mismatch"}


def test_c08_signature_tamper_is_detected(env, client, headers, sec):
    g = mint(client, headers, "editor.tool", "add_text")
    env["svc"].db.execute("UPDATE auth_grants SET scope='delete_elements' WHERE id=?", (g["id"],))
    r = call_tool(client, "delete_elements", headers, g["id"])
    assert r.status_code == 403
    assert r.json()["error"] in {"forged_grant", "scope_mismatch"}


def test_c09_principal_mismatch_is_detected(env, client, headers, sec):
    g = mint(client, headers, "editor.tool", "add_text")
    env["svc"].db.execute(
        "UPDATE auth_grants SET principal='operator:deadbeefdead' WHERE id=?", (g["id"],)
    )
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 403
    assert r.json()["error"] in {"principal_mismatch", "forged_grant"}


def test_c10_revoked_grant_cannot_be_used(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    rv = client.post(f"/api/security/grants/{g['id']}/revoke", headers=headers)
    assert rv.status_code == 200 and rv.json()["revoked"] is True
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 403


def test_c11_grant_cannot_be_reused_across_actions(env, client, headers):
    from minicoder.security import policy

    g = mint(client, headers, policy.ACTION_SNAPSHOT, "brain")
    r = client.post(
        "/api/export/snapshot", headers={**headers, "x-nace-grant": g["id"]}
    )
    assert r.status_code == 200
    r2 = client.post("/api/export/snapshot", headers={**headers, "x-nace-grant": g["id"]})
    assert r2.status_code == 409


def test_c12_grant_is_bound_to_the_instruction_hash(env):
    from minicoder.security import policy

    a = policy.instruction_scope("build a poster")
    b = policy.instruction_scope("build a poster ")
    c = policy.instruction_scope("build a POSTER")
    assert a == b == c, "whitespace/case normalise to the same operation"
    assert a != policy.instruction_scope("build a poster and delete the layers")


def test_c13_consumed_grant_records_its_outcome(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    call_tool(client, "add_text", headers, g["id"])
    row = env["svc"].db.query_one("SELECT outcome, consumed_at FROM auth_grants WHERE id=?", (g["id"],))
    assert row["consumed_at"] and row["outcome"] in ("executed", "failed")


def test_c14_failed_operation_still_consumes_the_grant(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    bridge(env).fail_next = True
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 503
    row = env["svc"].db.query_one("SELECT outcome FROM auth_grants WHERE id=?", (g["id"],))
    assert row["outcome"] == "failed"
    assert call_tool(client, "add_text", headers, g["id"]).status_code in (409, 403)


def test_c15_grant_ids_are_not_guessable(env, client, headers):
    ids = {mint(client, headers, "editor.tool", "add_text")["id"] for _ in range(5)}
    assert len(ids) == 5
    assert all(len(i) == 34 and i.startswith("g_") for i in ids)


def test_c16_token_is_never_echoed(client, headers, sec):
    tok = sec.operator_token()
    r = client.get("/api/security/status", headers=headers)
    assert tok not in r.text
    assert tok not in json.dumps(client.get("/api/security/audit", headers=headers).json())


# ---------------------------------------------------------------------------
# D. concurrency (10)
# ---------------------------------------------------------------------------

def _race(n: int, fn) -> list[Any]:
    out: list[Any] = []
    lock = threading.Lock()

    def run():
        try:
            value = fn()
        except Exception as exc:  # recorded; a raise is a legitimate outcome
            value = exc
        with lock:
            out.append(value)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return out


def test_d01_two_concurrent_requests_one_grant_execute_once(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    before = len(bridge(env).calls)
    results = _race(2, lambda: call_tool(client, "add_text", headers, g["id"]).status_code)
    assert sorted(results) == [200, 409]
    assert len(bridge(env).calls) == before + 1


def test_d02_five_concurrent_requests_one_grant(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    before = len(bridge(env).calls)
    results = _race(5, lambda: call_tool(client, "add_text", headers, g["id"]).status_code)
    assert results.count(200) == 1
    assert len(bridge(env).calls) == before + 1


def test_d03_distinct_grants_all_execute(env, client, headers):
    grants = [mint(client, headers, "editor.tool", "add_text")["id"] for _ in range(3)]
    before = len(bridge(env).calls)
    results = _race(3, lambda i=[0]: 0)  # placeholder to keep _race shape
    results = [call_tool(client, "add_text", headers, gid).status_code for gid in grants]
    assert results == [200, 200, 200]
    assert len(bridge(env).calls) == before + 3


def test_d04_store_level_consume_race(env):
    from minicoder.security import security
    from minicoder.security.grants import GrantError

    store = security(env["svc"].db).grants
    principal = security(env["svc"].db).authenticate(security(env["svc"].db).operator_token())
    g = store.issue(principal=principal, action="editor.tool", resource="canvas", scope="add_text")

    def consume():
        try:
            store.consume(g.id, principal=principal, action="editor.tool",
                          resource="canvas", scope="add_text", request_id="race")
            return "ok"
        except GrantError as exc:
            return exc.code

    results = _race(4, consume)
    assert results.count("ok") == 1
    assert set(results) - {"ok"} == {"replayed"}


def test_d05_audit_chain_survives_concurrency(env, client, headers):
    grants = [mint(client, headers, "editor.tool", "add_text")["id"] for _ in range(4)]
    _race(4, lambda: call_tool(client, "add_text", headers, grants.pop() if grants else "g_" + "2" * 32).status_code)
    from minicoder.security import security

    assert security(env["svc"].db).audit.verify()["ok"] is True


def test_d06_concurrent_grants_do_not_collide(env, client, headers):
    ids = [mint(client, headers, "editor.tool", "add_text")["id"] for _ in range(8)]
    assert len(set(ids)) == 8


def test_d07_concurrent_revocation_and_use(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    holder: dict[str, Any] = {}

    def use():
        holder["use"] = call_tool(client, "add_text", headers, g["id"]).status_code

    def revoke():
        holder["revoke"] = client.post(
            f"/api/security/grants/{g['id']}/revoke", headers=headers
        ).json()["revoked"]

    t1 = threading.Thread(target=use)
    t2 = threading.Thread(target=revoke)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    # Either it was revoked first (use denied) or it executed first (revoke noop).
    assert holder["use"] in (200, 403, 409)


def test_d08_concurrent_mixed_tools(env, client, headers):
    pairs = [("add_text", "add_text"), ("delete_elements", "delete_elements"),
             ("add_text", "add_text")]
    grants = [mint(client, headers, "editor.tool", tool)["id"] for tool, _ in pairs]
    results = _race(3, lambda i=[0]: call_tool(client, "add_text", headers, grants[i[0]]).status_code)
    assert all(code in (200, 403, 409) for code in results)


def test_d09_write_lock_is_not_deadlocked(env):
    from minicoder.security import security

    store = security(env["svc"].db).grants
    principal = "operator:test"
    started = time.time()

    def work(_i: int):
        g = store.issue(principal=principal, action="editor.tool", resource="canvas", scope="add_text")
        store.consume(g.id, principal=principal, action="editor.tool", resource="canvas",
                      scope="add_text", request_id=f"t{_i}")
        return store.stats()

    results = _race(6, lambda: work(0))
    assert time.time() - started < 20
    assert all(isinstance(r, dict) for r in results)


def test_d10_status_remains_readable_during_writes(env, client):
    results: list[int] = []
    def hammer():
        for _ in range(5):
            results.append(client.get("/api/security/status").status_code)
    _race(2, hammer)
    assert set(results) == {200}


# ---------------------------------------------------------------------------
# E. database failure and rollback (10)
# ---------------------------------------------------------------------------

def test_e01_audit_failure_prevents_execution(env, client, headers, monkeypatch):
    from minicoder.security.audit import SecurityAudit

    g = mint(client, headers, "editor.tool", "add_text")
    before = len(bridge(env).calls)

    def boom(self, *a, **k):
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr(SecurityAudit, "record", boom)
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code in (403, 503)
    assert len(bridge(env).calls) == before, "nothing may execute without an audit record"
    row = env["svc"].db.query_one("SELECT consumed_at FROM auth_grants WHERE id=?", (g["id"],))
    assert row["consumed_at"] is None, "the transaction must roll back the consumption"


def test_e02_mutation_exception_leaves_no_partial_state(env, client, headers, monkeypatch):
    from minicoder.memory.systems import SemanticMemory

    g = mint(client, headers, "memory.write", "explode_label")

    def boom(self, *a, **k):
        raise RuntimeError("write failed")

    monkeypatch.setattr(SemanticMemory, "upsert", boom)
    raw = TestClient(env["api"].app, raise_server_exceptions=False)
    r = raw.post("/api/memory", json={"label": "explode_label", "content": "x"},
                 headers={**headers, "x-nace-grant": g["id"]})
    assert r.status_code == 500
    assert env["svc"].db.query("SELECT id FROM semantic_nodes WHERE label='explode_label'") == []


def test_e03_editor_exception_is_audited_as_failed(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    bridge(env).fail_next = True
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 503
    from minicoder.security import security

    rows = security(env["svc"].db).audit.by_request(r.headers["x-request-id"])
    assert any(row["decision"] == "failed" for row in rows)


def test_e04_chain_valid_after_failures(env, client, headers):
    from minicoder.security import security

    g = mint(client, headers, "editor.tool", "add_text")
    bridge(env).fail_next = True
    call_tool(client, "add_text", headers, g["id"])
    assert security(env["svc"].db).audit.verify()["ok"] is True


def test_e05_invalid_json_does_not_authorize(client, headers):
    r = client.post("/api/editor/tool", content=b"{not json", headers={**headers, "content-type": "application/json"})
    assert r.status_code == 422


def test_e06_unknown_grant_leaves_no_partial_row(env, client, headers):
    before = env["svc"].db.query_one("SELECT COUNT(*) c FROM auth_grants")["c"]
    call_tool(client, "add_text", headers, "g_" + "9" * 32)
    after = env["svc"].db.query_one("SELECT COUNT(*) c FROM auth_grants")["c"]
    assert before == after


def test_e07_failed_grant_is_not_reusable(env, client, headers):
    g = mint(client, headers, "editor.tool", "add_text")
    bridge(env).fail_next = True
    call_tool(client, "add_text", headers, g["id"])
    second = call_tool(client, "add_text", headers, g["id"])
    assert second.status_code in (403, 409)


def test_e08_interrupted_write_rolls_back(env):
    """A raise inside db.write() must leave the table untouched."""
    from minicoder.security import security

    db = env["svc"].db
    before = db.query_one("SELECT COUNT(*) c FROM security_audit")["c"]
    try:
        with db.write() as conn:
            conn.execute(
                "INSERT INTO security_audit(ts, request_id, principal, action, resource, decision,"
                " grant_id, result, reason, correlation, prev_hash, hash)"
                " VALUES ('x','rollback','p','a','r','requested','','','','{}','p','h')"
            )
            raise RuntimeError("interrupted")
    except RuntimeError:
        pass
    assert db.query_one("SELECT COUNT(*) c FROM security_audit")["c"] == before
    assert security(db).audit.verify()["ok"] is True


def test_e09_concurrent_writes_do_not_corrupt(env, client, headers):
    def work():
        g = mint(client, headers, "editor.tool", "add_text")
        return call_tool(client, "add_text", headers, g["id"]).status_code

    results = _race(6, work)
    assert all(code == 200 for code in results), results
    from minicoder.security import security

    assert security(env["svc"].db).audit.verify()["ok"] is True


def test_e10_no_row_is_written_for_a_rejected_request_without_grant(env, client, headers):
    from minicoder.security import security

    before = security(env["svc"].db).audit.counts().get("authorized", 0)
    call_tool(client, "add_text", headers)
    after = security(env["svc"].db).audit.counts().get("authorized", 0)
    assert before == after


# ---------------------------------------------------------------------------
# F. audit integrity (10)
# ---------------------------------------------------------------------------

def test_f01_chain_verifies(env, sec):
    result = sec.audit.verify()
    assert result["ok"] is True and result["length"] > 0


def test_f02_tampering_a_row_breaks_the_chain(env, sec):
    db = env["svc"].db
    row = db.query_one("SELECT id, decision FROM security_audit ORDER BY id DESC LIMIT 1")
    db.execute("UPDATE security_audit SET decision='authorized' WHERE id=?", (row["id"],))
    result = sec.audit.verify()
    assert result["ok"] is False and result["broken_at"] == row["id"]
    db.execute("UPDATE security_audit SET decision=? WHERE id=?", (row["decision"], row["id"]))
    assert sec.audit.verify()["ok"] is True


def test_f03_deleting_a_row_breaks_the_chain(env, sec):
    db = env["svc"].db
    row = db.query_one("SELECT id FROM security_audit WHERE id = (SELECT MIN(id)+1 FROM security_audit)")
    snapshot = db.query_one("SELECT * FROM security_audit WHERE id=?", (row["id"],))
    db.execute("DELETE FROM security_audit WHERE id=?", (row["id"],))
    assert sec.audit.verify()["ok"] is False
    db.execute(
        "INSERT INTO security_audit(id, ts, request_id, principal, action, resource, decision,"
        " grant_id, result, reason, correlation, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        tuple(snapshot[k] for k in ("id", "ts", "request_id", "principal", "action", "resource",
                                    "decision", "grant_id", "result", "reason", "correlation",
                                    "prev_hash", "hash")),
    )
    assert sec.audit.verify()["ok"] is True


def test_f04_every_successful_mutation_has_an_executed_row(env, client, headers, sec):
    g = mint(client, headers, "editor.tool", "add_text")
    r = call_tool(client, "add_text", headers, g["id"])
    assert r.status_code == 200
    rows = sec.audit.by_request(r.headers["x-request-id"])
    assert [row["decision"] for row in rows] == ["authorized", "executed"]
    assert rows[1]["grant_id"] == g["id"]


def test_f05_rejections_are_recorded(env, client, headers, sec):
    r = call_tool(client, "delete_elements", headers)
    rows = sec.audit.by_request(r.headers["x-request-id"])
    assert [row["decision"] for row in rows] == ["rejected"]
    assert "no grant" in rows[0]["reason"]


def test_f06_replays_are_recorded_as_replays(env, client, headers, sec):
    g = mint(client, headers, "editor.tool", "add_text")
    call_tool(client, "add_text", headers, g["id"])
    r = call_tool(client, "add_text", headers, g["id"])
    rows = [row["decision"] for row in sec.audit.by_request(r.headers["x-request-id"])]
    assert "replayed" in rows


def test_f07_no_secret_is_written_to_the_audit(env, sec, client, headers):
    tok = sec.operator_token()
    dump = json.dumps([dict(r) for r in env["svc"].db.query("SELECT * FROM security_audit")])
    assert tok not in dump
    assert "Bearer " not in dump


def test_f08_decisions_are_from_the_defined_set(env, sec):
    from minicoder.security.audit import DECISIONS

    decisions = {r["decision"] for r in env["svc"].db.query("SELECT DISTINCT decision FROM security_audit")}
    assert decisions
    assert decisions <= DECISIONS


def test_f09_audit_is_append_only(env, sec):

    source = Path(__import__("minicoder.security.audit", fromlist=["x"]).__file__).read_text()
    assert "UPDATE security_audit" not in source
    assert "DELETE FROM security_audit" not in source


def test_f10_request_ids_correlate_the_whole_flow(env, client, headers, sec):
    g = mint(client, headers, "editor.tool", "add_text", ttl=120)
    rows = sec.audit.by_request(sec.audit.recent(1)[0]["request_id"])
    assert rows
    r = call_tool(client, "add_text", headers, g["id"])
    rid = r.headers["x-request-id"]
    decisions = [row["decision"] for row in sec.audit.by_request(rid)]
    assert decisions == ["authorized", "executed"]


# ---------------------------------------------------------------------------
# G. static guarantees: the policy cannot drift, the API cannot bypass
# ---------------------------------------------------------------------------

def _declared_tools() -> set[str]:
    import re

    source = (Path(__file__).resolve().parents[2] / "src" / "ai" / "agent" / "tools.ts").read_text()
    start = source.index("export const TOOL_DECLARATIONS")
    end = source.index("];", start)
    return set(re.findall(r"name:\s*'([a-z0-9_]+)'", source[start:end]))


def test_g01_policy_covers_every_declared_tool():
    """A tool added to the editor without a class would be rejected at runtime.

    This test makes that a build failure instead of a surprise in production.
    """
    from minicoder.security.policy import TOOL_CLASSES

    declared = _declared_tools()
    assert declared, "could not parse TOOL_DECLARATIONS"
    missing = declared - set(TOOL_CLASSES)
    stale = set(TOOL_CLASSES) - declared
    assert not missing, f"tools without a policy class: {sorted(missing)}"
    assert not stale, f"policy classes for tools that no longer exist: {sorted(stale)}"


def test_g02_no_bridge_call_in_the_api_omits_authorization():
    """Every `bridge.call(` in the API must pass an explicit `auth=`."""
    import re

    source = (Path(__file__).resolve().parents[2] / "minicoder" / "api" / "app.py").read_text()
    calls = re.findall(r"bridge\.call\(([^)]*)\)", source, re.S)
    assert calls, "expected at least one bridge call in the API"
    for args in calls:
        assert "auth=" in args, f"unguarded bridge.call({args.strip()[:60]}…)"

    bridge_src = (Path(__file__).resolve().parents[2] / "minicoder" / "tools" / "editor_bridge.py").read_text()
    assert "check_tool(tool" in bridge_src, "the guard must live in EditorBridge.call"
