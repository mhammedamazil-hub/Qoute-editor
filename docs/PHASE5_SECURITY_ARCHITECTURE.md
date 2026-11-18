# Phase 5 — Security Architecture

**Sprint:** NACE 5.0 security remediation
**Baseline:** `1c476dd` + audit commit `764c112`
**Scope:** authorization, grants, replay protection, audit, CORS. No learning changes.
**Status of the code:** implemented and covered by `minicoder/tests/test_phase5_security.py` (114 tests).

---

## 1. What was broken

The independent Phase 4 audit (`docs/PHASE4_INDEPENDENT_AUDIT.md`) recorded:

| Finding | Evidence |
|---|---|
| F1 (CRITICAL) | `POST /api/editor/tool` executed `new_project`, `add_text`, `add_shape`, `delete_elements` with **no authorization and no audit row** (`audit_log` stayed at 2 while the canvas went 1 → 0). |
| F2 (HIGH) | 12 of 18 destructive rephrasings were classified `question` with `authorized=false`, because `requires_authorization` was computed *before* the final type/verb scan. |
| F7 (HIGH) | "Authorization" was a client-supplied boolean (`{"authorize": true}`), replayable, attributable to nobody. |
| F1b | `Access-Control-Allow-Origin: *` let any web page the operator visited drive the local editor. |
| F1c | `GET /api/export/snapshot` wrote a file — a state-changing GET, reachable by `<img src>`. |

The structural cause in one sentence: **authority lived in one Python call path (`DesignAgent.execute`) instead of at the place where tools actually execute**, so every other entry point (HTTP tool passthrough, scripts, internal helpers) was outside the policy.

---

## 2. Old vs new execution flow

### Old (Phase 4)

```
HTTP request ──► endpoint ──┬──► DesignAgent.execute(authorize: bool)
                            │        └─ intent.requires_authorization? (sometimes wrong)
                            │            └─ bridge.call(tool)      ← no check here
                            └──► bridge.call(tool)                  ← no check at all
                                     └─ Node editor (mutates)
                            (audit row written by the agent, if the agent was used)
```

Two paths, one policy, and the policy sat on the wrong one.

### New (Phase 5)

```
                       ┌──────────────────────────────┐
HTTP request ──► route │ 1. principal      (bearer)   │
                       │ 2. grant consume  (atomic)   │──► 401 / 403 / 409
                       │ 3. audit "authorized"        │    (nothing executes)
                       └──────────────┬───────────────┘
                                      ▼
                              agent.execute(auth=ctx)
                                      ▼
                    ┌───────────────────────────────┐
                    │ check_plan(planned, ctx)      │  ← whole plan, before step 1
                    └───────────────┬───────────────┘
                                    ▼
        ┌────────────────────────────────────────────────────────┐
        │ EditorBridge.call(tool, args, auth)                    │
        │   check_tool(tool, args, auth)   ← THE CHOKE POINT     │
        │   unknown tool? → AuthorizationRequired                │
        │   read-only?    → allow                                │
        │   else          → require a matching grant context     │
        └───────────────────────────┬────────────────────────────┘
                                    ▼
                            Node editor (mutates)
                                    ▼
                       audit "executed" / "failed"
```

The check now sits **immediately before the bytes go to the editor process**, in `EditorBridge.call` — the one function every tool path must use, including scripts, the learning pipeline and the sleep worker. A new endpoint cannot forget it; forgetting it means calling the editor some other way, which the architecture does not offer.

---

## 3. Components

| Module | Responsibility |
|---|---|
| `minicoder/security/policy.py` | Classification of all 37 tools; grantable actions; resource mapping; canonical instruction hashing. |
| `minicoder/security/grants.py` | Issuance, HMAC signing, scope checks, **atomic single-use consumption**, revocation, secrets on disk (0600). |
| `minicoder/security/audit.py` | Hash-chained, append-only audit; `verify()`; anchored head; refuses to log secrets. |
| `minicoder/security/service.py` | The boundary: authenticate → consume → audit → context; `finish()` for the outcome. |
| `minicoder/security/guard.py` | `check_tool` / `check_plan` — the last line of defence inside the bridge. |
| `minicoder/tools/editor_bridge.py` | Calls `check_tool` in `call()` and `reset()` before touching the transport. |

---

## 4. Tool permission matrix

37 tools, classified explicitly in `policy.TOOL_CLASSES`. Anything not in the
table is **rejected** (fail closed), not treated as read-only.

| Class | n | Requires grant | Tools |
|---|---|---|---|
| `read_only` | 2 | no | `get_app_state`, `list_templates` |
| `reversible` | 30 | **yes** | `zoom`, `set_preview_mode`, `open_panel`, `set_ui_preference`, `select_elements`, `set_canvas_size`, `set_background`, `apply_palette`, `apply_template`, `add_text`, `add_quote_mark`, `add_shape`, `add_light`, `add_gradient_layer`, `add_particles`, `add_decoration`, `update_elements`, `set_text_content`, `set_typography`, `set_layer_style`, `translate_elements`, `resize_elements`, `duplicate_elements`, `reorder_elements`, `group_elements`, `ungroup_elements`, `align_elements`, `distribute_elements`, `undo`, `redo` |
| `consequential` | 3 | **yes** | `save_project`, `export_image`, `generate_design` |
| `destructive` | 2 | **yes** | `new_project`, `delete_elements` |

`EditorBridge.reset()` — which wipes the canvas without naming a tool — is
authorized as `new_project`.

Print it any time: `python -m minicoder.cli security inventory`.

---

## 5. Protected endpoints

### Mutating (gated)

| Endpoint | Method | Grant action | Scope | Bearer |
|---|---|---|---|---|
| `/api/chat` (when the plan mutates or the intent is consequential) | POST | `editor.instruction` | `sha256(canonical instruction)` | yes |
| `/api/editor/tool` | POST | `editor.tool` | exact tool name | yes |
| `/api/editor/canvas` | POST | `editor.canvas` | `"WxH"` | yes |
| `/api/memory` | POST | `memory.write` | label | yes |
| `/api/sleep` | POST | `sleep.run` | `"cycle"` | yes |
| `/api/vision/inspect` | POST | `vision.inspect` | `"upload"` | yes |
| `/api/export/snapshot` | **POST** (was a GET) | `memory.snapshot` | `"brain"` | yes |

### Security surface

| Endpoint | Method | Who | Purpose |
|---|---|---|---|
| `/api/security/grant` | POST | operator token | mint a grant |
| `/api/security/grants/{id}` | GET | operator token | inspect one grant |
| `/api/security/grants/{id}/revoke` | POST | operator token | revoke an unused grant |
| `/api/security/audit` | GET | operator token | recent rows + chain state |
| `/api/security/status` | GET | anyone | non-secret boundary summary |
| `/api/security/inventory` | GET | anyone | tool matrix |

### Read-only (unchanged)

`/api/health`, `/api/status`, `/api/editor/tools`, `/api/editor/state`,
`/api/vision`, `/api/vision/{id}/image`, `/api/memory/search`, `/api/graph`,
`/api/episodes`, `/api/skills`, `/api/sleep/reports`, `/api/sleep/latest`,
`/api/eval`, `/api/training`, `/api/cognition/overview`,
`/api/generalization/overview`, `/api/sleep/adaptive`, `/api/research/overview`,
`/api/learning/*`, `/ws/telemetry`, `/`, `/assets/*`.

`/ws/telemetry` is a read-only stream; it exposes no mutation path and no secret.

---

## 6. Grant lifecycle

```
        POST /api/security/grant  (Authorization: Bearer <operator token>)
                    │
                    ▼
   ┌──────────────────────────────────────────────┐
   │ id            g_<32 hex>                     │  random, not guessable
   │ principal     operator:<sha256(token)[:12]>  │  never the token itself
   │ action        editor.tool | editor.instruction | sleep.run | ...
   │ resource      canvas | memory | memory:semantic | memory:visual
   │ scope         exact tool name | sha256(instruction) | label
   │ created_at / expires_at   120 s (60 s for editor actions)
   │ nonce         random, part of the signature
   │ signature     HMAC-SHA256(key, id|principal|action|resource|scope|…)
   └──────────────┬───────────────────────────────┘
                  ▼
        presented as  X-NACE-Grant: <id>   (+ the same bearer token)
                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │ BEGIN IMMEDIATE                                              │
   │   load → verify signature → check principal/action/resource/ │
   │   scope → check revoked → check expiry →                     │
   │   UPDATE … SET consumed_at=? WHERE id=? AND consumed_at IS NULL│
   │   INSERT audit(decision='authorized')                        │
   │ COMMIT                                                       │
   └──────────────┬───────────────────────────────────────────────┘
                  ▼
           execute ──► audit 'executed' or 'failed' ──► grant.outcome
```

**Invariants**

* A grant is bound to one action, one resource and one scope. A grant for
  `export_image` cannot run `delete_elements`; a grant for instruction A cannot
  run instruction B (scope is the canonical hash: whitespace and case normalise,
  meaning does not).
* The signature covers every field, including `expires_at`, so editing the row
  to extend a grant is detected as forgery, not honoured.
* Consumption and authorization-audit happen in **one transaction**. If the audit
  row cannot be written, the transaction rolls back: the grant stays unconsumed
  and nothing executes.
* Consumption is `UPDATE … WHERE consumed_at IS NULL` inside `BEGIN IMMEDIATE`,
  so N concurrent callers produce exactly one winner. The losers get `409`.
* A failed execution consumes the grant and records `outcome='failed'`. That is
  deliberate: a failure is not a licence to retry silently with the same
  authority.
* Revocation is immediate for unused grants; a consumed grant is already spent.

---

## 7. Replay protection

| Vector | Control |
|---|---|
| Same grant replayed | `consumed_at` claim; second use → `409 replayed`, audit `replayed`. |
| Two concurrent requests, one grant | Atomic claim inside `BEGIN IMMEDIATE`; exactly one executes (test `d01`, `d02`). |
| Forged/guessed grant id | HMAC signature verified against the stored record. |
| Grant minted by a stranger | Issuance requires the operator token; the principal fingerprint is stored and must match. |
| Grant smuggled in the body | Only the `x-nace-grant` header is read; `grant`, `grant_id`, `authorize` body fields are ignored. |
| Expired grant | Rejected before consumption. |
| Revoked grant | Rejected. |

The request id (`x-request-id`, generated per request) is what ties
`authorized` → `executed` rows together and appears in every error response.

---

## 8. Audit design

Table `security_audit`: `ts, request_id, principal, action, resource, decision,
grant_id, result, reason, correlation, prev_hash, hash`.

* **States:** `requested`, `authorized`, `executed`, `failed`, `rejected`, `replayed`.
* **Chain:** `hash = sha256(prev_hash | canonical(row))`; the head is anchored in
  `schema_meta.security_audit_head`, so deleting the newest row is detected as
  well as editing a middle one. `python -m minicoder.cli security verify` exits
  non-zero on a break.
* **No secrets:** `record()` refuses payloads matching the token/Bearer patterns;
  principals are fingerprints, never tokens.
* **No silent omission:** a mutation cannot proceed when its authorization row
  cannot be written (`503 audit_unavailable`), and the outcome row is written
  after execution on every path, including exceptions.

Retention: rows are never updated or deleted by product code (test `f09` asserts
the module contains no `UPDATE`/`DELETE` against the table).

---

## 9. Authentication model — what it is and is not

There is **no user authentication** in NACE. There are no accounts, passwords or
sessions identifying a person. What exists is a **capability**:

* a 43-character token in `<home>/.security/operator.token`, mode `0600`, owned by
  the OS user running the server;
* the ability to read that file is the ability to act as the local operator;
* principals are recorded as `operator:<sha256(token)[:12]>` — enough to
  distinguish capability holders, not to name a human.

Consequences, stated plainly:

* The boundary is between **the operator's process and network clients**, not
  between two humans on the same machine.
* Any process running as the same OS user can read the token and act. That is the
  same trust domain that can read `brain.db` directly.
* In-process code (CLI, sleep worker, learning pipeline, tests) constructs an
  `internal_context` — an explicit, audited decision, not an accident. It cannot
  be constructed from an HTTP request without a consumed grant.

This is the honest maximum available without inventing an identity system. It is
enough to eliminate the Phase 4 defect (an arbitrary page or `curl` could delete
the canvas) and not enough to claim multi-user security. See
`docs/PHASE5_THREAT_MODEL.md` §6.

---

## 10. CORS policy

Before: `allow_origins=["*"]`, `allow_headers=["*"]`, `allow_methods=["*"]`.

After (`config.ApiConfig`):

```python
cors_origins = ("http://localhost:5173", "http://127.0.0.1:5173",
                "http://localhost:8000", "http://127.0.0.1:8000")   # or NACE_ALLOWED_ORIGINS
cors_origin_regex = r"https://[0-9]{2,5}-[a-z0-9-]+\.e2b\.app"      # or NACE_ALLOWED_ORIGIN_REGEX
allow_credentials = False
allow_methods = ["GET", "POST", "OPTIONS"]
allow_headers = ["content-type", "authorization", "x-nace-grant", "x-request-id"]
expose_headers = ["x-request-id"]
```

Notes:

* CORS is **not** authentication. It stops a browser page from *reading* a
  response; it never stopped a page (or curl) from *sending* a request. The grant
  boundary is what stops the mutation. Verified: an `OPTIONS` preflight from
  `https://evil.example` receives no `Access-Control-Allow-Origin`.
* `allow_credentials=False` because no cookie is used — credentials travel as an
  explicit `Authorization` header, which a cross-site page cannot set.
* The preview proxy hosts are covered by the regex, not by `*`.

---

## 11. Failure behaviour (fail closed)

| Failure | Behaviour |
|---|---|
| No bearer token on a mutation | `401`, audit `rejected`, nothing executes. |
| No grant | `403 missing_grant` + `requires_grant {action, resource, scope}`, audit `rejected`. |
| Wrong scope/tool/resource/action | `403 scope_mismatch` / `action_mismatch` / `resource_mismatch`. |
| Expired / revoked | `403 expired` / `revoked`. |
| Replayed / concurrent reuse | `409 replayed`, audit `replayed`, exactly one execution. |
| Unknown tool | `403` + audit `rejected` (even with a valid token). |
| Audit write fails | `503 audit_unavailable`, grant not consumed, nothing executes. |
| Editor raises mid-call | `503`, audit `failed`, grant consumed, no retry with the same grant. |
| DB write raises during memory mutation | transaction rolls back, no row, audit `failed`. |
| Invalid JSON | `422` before any authorization. |

**Not atomic (documented):** editor mutations run over a pipe to a separate Node
process, so the grant consumption (SQLite) and the canvas change cannot share a
transaction. The order is: consume + audit → execute → audited outcome. A crash
between "consumed" and "executed" therefore leaves a consumed grant with no
`executed` row and no `failed` row — the operation may or may not have reached
the editor. This is detectable (`authorized` with no terminal row) and is the one
gap the design cannot close; see the threat model R5.

---

## 12. Files changed

| File | Change |
|---|---|
| `minicoder/security/*` | new package (policy, grants, audit, service, guard) |
| `minicoder/memory/schema.sql` | `auth_grants`, `security_audit`, anchored head, schema v4 |
| `minicoder/tools/editor_bridge.py` | authorization check in `call()`/`reset()`; optional per-client `auth` |
| `minicoder/cognition/agent.py` | `auth=` context; plan authorized before first step; legacy boolean grants nothing |
| `minicoder/cognition/intent.py` | detection rewritten: risk phrases, negation, request-form, obfuscation; authorization computed after typing |
| `minicoder/api/app.py` | request-id + security headers middleware, explicit CORS, guarded mutating routes, security endpoints |
| `minicoder/config.py` | explicit CORS origins + preview regex, no `*` |
| `minicoder/cli.py` | `security token/inventory/status/audit/verify/mint/revoke` |
| `minicoder/learning/{engine,planner,replay}.py`, `minicoder/sleep/engine.py` | internal contexts at the call sites (no implicit bypass) |
| `minicoder/dashboard/src/{api.ts,ChatView.tsx}` | bearer + grant headers, 401 token prompt, explicit "authorize & run" step |
| `.gitignore` | `.security/`, `*.token` |
| `minicoder/tests/test_phase5_security.py` | 114-test adversarial suite |
| `minicoder/tests/{test_phase4,test_systems}.py` | updated to the new contract (see results §5) |
