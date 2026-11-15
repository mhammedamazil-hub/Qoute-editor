from fastapi.testclient import TestClient
import pytest


@pytest.fixture()
def client(brain_home):
    from minicoder.api.app import create_app
    return TestClient(create_app())


def test_status_and_doctor(client):
    status = client.get("/api/brain/status").json()
    assert status["state"] == "awake"
    assert "memory_counts" in status and "hardware" in status
    doctor = client.get("/api/brain/doctor").json()
    assert doctor["db_exists"] is True


def test_chat_is_honest_offline(client):
    resp = client.post("/api/brain/chat", json={"message": "zzqxv qwobbleplatz quantum flimflam"}).json()
    assert resp["reply"]
    assert "episode_id" in resp


def test_remember_then_search(client):
    client.post("/api/brain/memory/remember", json={
        "situation": "User prefers tabs over spaces in Python", "tags": ["preference", "style"],
        "source": "user_instruction", "confidence": 0.9})
    hits = client.get("/api/brain/memory/search", params={"q": "tabs spaces python preference"}).json()
    assert any("tabs" in h["episode"]["situation"] for h in hits)


def test_verify_code_endpoint_gates(client):
    bad = client.post("/api/brain/skills/verify-code", json={
        "task": "always wrong", "solution": "def f():\n    return 1\n",
        "tests": "from solution import f\ndef test_f():\n    assert f() == 2\n"}).json()
    assert bad["verified"] is False
    good = client.post("/api/brain/skills/verify-code", json={
        "task": "identity function", "solution": "def ident(x):\n    return x\n",
        "tests": "from solution import ident\ndef test_ident():\n    assert ident('a') == 'a'\n"}).json()
    assert good["verified"] is True
    skills = client.get("/api/brain/skills", params={"status": "VERIFIED"}).json()
    assert any(s["name"] == "identity function" for s in skills)


def test_sleep_endpoint_and_report(client):
    client.post("/api/brain/chat", json={"message": "remember that I like concise answers"})
    resp = client.post("/api/brain/sleep", json={"trigger": "api_test"})
    assert resp.status_code == 200
    report = client.get("/api/brain/sleep/report").json()
    assert report["trigger"] == "api_test"


def test_graph_endpoint(client):
    client.post("/api/brain/memory/remember", json={"situation": "graphSeed", "tags": ["graphseed"]})
    client.post("/api/brain/sleep", json={"trigger": "graph_seed"})
    payload = client.get("/api/brain/graph").json()
    assert "nodes" in payload and "edges" in payload


def test_export_import_roundtrip(client, tmp_path):
    client.post("/api/brain/memory/remember", json={"situation": "snapshot survives me", "tags": ["snapshot"]})
    out = client.post("/api/brain/snapshot/export").json()
    assert out["size_bytes"] > 100
    from minicoder.snapshot import import_snapshot
    result = import_snapshot(out["path"])
    assert result["imported_rows"]["episodes"] >= 1
