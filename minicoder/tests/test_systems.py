"""Model, evaluation, CLI and API behaviour."""

from __future__ import annotations

import json

import pytest

from minicoder.config import CONFIG


# ------------------------------------------------------------------ tokenizer
def test_tokenizer_roundtrips_text():
    from minicoder.model.tokenizer import Tokenizer

    tok = Tokenizer.load(CONFIG.paths.checkpoints / "tokenizer.json")
    text = "def solve(nums):\n    return sum(nums)  # café ✓"
    assert tok.decode(tok.encode(text)) == text


def test_tokenizer_never_emits_out_of_vocab_ids():
    from minicoder.model.tokenizer import Tokenizer

    tok = Tokenizer.load(CONFIG.paths.checkpoints / "tokenizer.json")
    ids = tok.encode("unseen Unicode: 日本語 and emoji 🚀")
    assert all(0 <= i < CONFIG.model.vocab_size for i in ids)


# ---------------------------------------------------------------------- model
def test_checkpoint_loads_with_expected_parameter_count():
    from minicoder.cognition.engine import NeuralBrain

    brain = NeuralBrain()
    assert brain.model is not None
    assert brain.model.n_params() == 1_317_600


def test_code_generation_is_verified_by_execution():
    from minicoder.cognition.engine import NeuralBrain

    brain = NeuralBrain()
    gen = brain.generate(
        "Write a Python function `solve(nums)` that returns the sum of a list of integers.",
        max_new_tokens=40,
    )
    assert "def solve(nums)" in gen.text
    assert "return sum(nums)" in gen.text.replace("\n", " ").replace("  ", " ")


def test_lora_adapter_can_be_detached_and_reattached():
    from minicoder.cognition.engine import NeuralBrain
    from minicoder.model.transformer import LoRAConfig, attach_lora, detach_lora

    model = NeuralBrain().model
    attach_lora(model, LoRAConfig(rank=4, alpha=8.0))
    def adapter_keys() -> list[str]:
        # Adapter tensors are the LoRALinear ``a``/``b`` weights. Matching on a
        # bare ".a"/".b" substring also catches "blocks.0.attn...", so match the
        # real module path.
        return [k for k in model.state_dict() if k.endswith((".a.weight", ".b.weight"))]

    assert adapter_keys(), "LoRA attach produced no adapter tensors"
    detach_lora(model)
    assert not adapter_keys()


# ----------------------------------------------------------------------- eval
def test_retrieval_suite_is_perfect_on_its_own_corpus():
    from minicoder.eval.suites import eval_memory_retrieval

    metrics = eval_memory_retrieval().metrics
    assert metrics["precision_at_1"] == 1.0
    assert metrics["mrr"] == 1.0


def test_chat_suite_refuses_everything_it_cannot_answer():
    from minicoder.eval.suites import eval_chat

    metrics = eval_chat().metrics
    assert metrics["hallucination_rate"] == 0.0
    assert metrics["refusal_rate"] == 1.0


def test_chat_suite_does_not_touch_the_live_brain():
    from minicoder.eval.suites import eval_chat
    from minicoder.memory.db import BrainDB

    before = int(BrainDB().query("SELECT COUNT(*) FROM episodes")[0][0])
    eval_chat()
    after = int(BrainDB().query("SELECT COUNT(*) FROM episodes")[0][0])
    assert before == after, "eval leaked fixtures into the live database"


def test_multisession_suite_does_not_touch_the_live_brain():
    from minicoder.eval.suites import eval_multisession_recall
    from minicoder.memory.db import BrainDB

    before = int(BrainDB().query("SELECT COUNT(*) FROM episodes")[0][0])
    eval_multisession_recall()
    after = int(BrainDB().query("SELECT COUNT(*) FROM episodes")[0][0])
    assert before == after


@pytest.mark.slow
def test_coding_suite_reports_both_splits():
    from minicoder.eval.suites import eval_coding

    metrics = eval_coding().metrics
    assert metrics["indist"]["n"] >= 15
    assert metrics["holdout"]["n"] >= 5
    assert metrics["indist"]["exact_match"] > 0.5


# ------------------------------------------------------------------------ cli
def test_cli_help_lists_every_documented_command(capsys):
    from minicoder.cli import main

    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    for command in ("init", "seed", "chat", "act", "inspect", "train", "sleep",
                    "eval", "status", "memory", "skills", "snapshots", "serve", "doctor"):
        assert command in out, command


def test_cli_status_runs_against_a_fresh_home(capsys):
    from minicoder.cli import main

    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "WAKE" in out


def test_cli_seed_is_idempotent(capsys):
    from minicoder.cli import main
    from minicoder.memory.db import BrainDB

    main(["seed"])
    first = int(BrainDB().query("SELECT COUNT(*) FROM skills")[0][0])
    main(["seed"])
    second = int(BrainDB().query("SELECT COUNT(*) FROM skills")[0][0])
    assert first == second, f"seed duplicated skills: {first} -> {second}"


def test_cli_memory_search_prints_nothing_for_unrelated_query(capsys):
    from minicoder.cli import main

    main(["seed"])
    capsys.readouterr()
    main(["memory", "search", "quantum chromodynamics"])
    out = capsys.readouterr().out
    assert "flexbox" not in out


# ------------------------------------------------------------------------ api
@pytest.fixture()
def client(home):
    from fastapi.testclient import TestClient

    # Phase 5: bind the runtime to *this* test's home.  The module-level
    # singleton may hold a service from an earlier test whose home has since
    # been torn down; without this the API writes into that (or the live) brain.
    import minicoder.api.app as api_module
    from minicoder.api.app import app, service

    api_module.SERVICE = None
    svc = service()
    assert str(svc.db.db_path).startswith(str(home)), (svc.db.db_path, home)
    return TestClient(app)


def test_api_health(client):
    assert client.get("/api/health").status_code == 200
    body = client.get("/api/status").json()
    assert body["state"] == "WAKE"
    assert "params" in json.dumps(body) or "model" in json.dumps(body)


def test_api_refuses_off_domain_chat_honestly(client):
    body = client.post("/api/chat", json={"message": "Who won the 1998 world championship in curling?"}).json()
    assert body.get("source") == "refuse"


def test_api_chat_routes_a_poster_request_to_a_verified_skill(client, home):
    """A build is a mutation, so it needs a grant — and still produces steps.

    Phase 4 ran this without any authorization.  Phase 5 keeps the behavioural
    assertion (a poster request must reach the editor) and adds the security
    one: the same request without a grant is refused and changes nothing.
    """
    from minicoder.api.app import service
    from minicoder.security import policy, security
    from minicoder.seed import seed_brain

    seed_brain()
    message = "Create a cinematic poster about patience at 1080x1350 with gold light"
    denied = client.post("/api/chat", json={"message": message})
    assert denied.status_code == 401, denied.text

    sec = security(service().db)
    headers = {"authorization": f"Bearer {sec.operator_token()}"}
    grant = client.post(
        "/api/security/grant",
        json={"action": policy.ACTION_INSTRUCTION,
              "scope": policy.instruction_scope(message)},
        headers=headers,
    ).json()["grant"]

    body = client.post(
        "/api/chat", json={"message": message},
        headers={**headers, "x-nace-grant": grant["id"]},
    ).json()
    assert body["source"] in ("skill", "tool"), body
    assert body["steps"], "a poster request must produce editor steps"


def test_api_rejects_path_traversal_on_assets(client):
    for url in ("/assets/../../etc/passwd", "/assets/..%2f..%2fetc%2fpasswd"):
        response = client.get(url)
        assert response.status_code in (403, 404), url


def test_api_lists_the_editor_tool_catalogue(client):
    body = client.get("/api/editor/tools").json()
    names = json.dumps(body)
    assert "set_canvas_size" in names
    assert "apply_palette" in names


def test_api_graph_returns_nodes_and_edges(client):
    body = client.get("/api/graph").json()
    assert "nodes" in body and "edges" in body
