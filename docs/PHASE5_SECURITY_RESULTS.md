# Phase 5 — Security Remediation Results

**Baseline:** `1c476dd` + audit commit `764c112`
**Method:** every claim below was produced by running the code, not by describing it.
Two sources: the adversarial suite (114 tests) and a replay of the Phase 4 attacks
against the live server on `0.0.0.0:8000`.

---

## 1. The Phase 4 attacks, replayed against the fixed server

Same tool, same request shape, same server port as the audit. Executed with `curl`
and no credentials.

| # | Attack (Phase 4 result) | Phase 5 result | State check |
|---|---|---|---|
| 1 | `POST /api/editor/tool {"tool":"new_project"}` → **executed**, canvas wiped, no audit row | `401 unauthenticated` | canvas unchanged (`layerCount` 0 before and after; nothing executed) |
| 2 | `{"tool":"add_text"}` → **executed** | `401 unauthenticated` | no layer created |
| 3 | `{"tool":"delete_elements","types":["shape"]}` → **executed**, "Deleted 1 layer(s)", `audit_log` 2→2 | `401 unauthenticated` | no deletion; a `rejected` row is written |
| 4 | `POST /api/chat {"message":…, "authorize":true}` → **executed** | `401 unauthenticated` | legacy boolean recorded as a rejected attempt (`chat.legacy_authorize`) |
| 5 | Preflight from `https://evil.example` → `Access-Control-Allow-Origin: *` | **no** ACAO header (origin rejected) | — |
| 6 | Preflight from `http://localhost:5173` | `Access-Control-Allow-Origin: http://localhost:5173` | intended origin still works |
| 7 | `GET /api/export/snapshot` → wrote a file | `405 Method Not Allowed` | POST + grant required |

### Authorized path, same server

```
POST /api/security/grant  {action: editor.tool, scope: add_text}
  → grant g_f4bcec1b…, expires in 120 s
POST /api/editor/tool     (bearer + x-nace-grant)
  → 200, executed: true, "Added Quote “Phase 5 authorized edit” at (120, 300)."
  → tool_class: reversible
POST /api/editor/tool     (same grant again)
  → 409 replayed
```

The product still works; the authority is now explicit, scoped and spent.

---

## 2. The 12 original intent bypasses

All twelve are now flagged by the detection layer **and** — independently —
blocked at the execution boundary, so a classifier miss would not execute
anything.

| Phrase (Phase 4: `question`, `authorized=false`) | Phase 5 type | `requires_authorization` |
|---|---|---|
| wipe everything | execution | **true** |
| start from scratch | execution | **true** |
| get rid of all the layers | execution | **true** |
| take them out | execution | **true** |
| blank canvas | execution | **true** |
| throw away the current design | execution | **true** |
| make it empty | execution | **true** |
| nuke the file system | execution | **true** |
| paste the token | execution | **true** |
| d3lete every layer | execution | **true** |
| could you delete all the layers? | execution | **true** |
| do not delete anything | question, `negated=true` | **true** (fail closed) |

Beyond the twelve: 32 destructive phrasings and 8 benign ones are asserted in the
suite, plus obfuscation (`w1pe everything`, zero-width characters) and the
informational/imperative distinction (`how do I delete a layer?` stays answerable;
`could you delete…` does not).

---

## 3. Adversarial suite results

`minicoder/tests/test_phase5_security.py` — **114 tests, all passing.**

| Category | Required | Implemented | What is asserted |
|---|---|---|---|
| Natural-language bypass | ≥ 30 | **43** (32 destructive, 8 benign, 3 semantics) | classification *and* that the state-changing path stays closed |
| Direct API attacks | ≥ 20 | **22** | status code **plus** bridge call list and DB rows |
| Grant manipulation / replay | ≥ 15 | **17** | forgery, tamper, scope, resource, principal, expiry, revocation, body smuggling |
| Concurrency | ≥ 10 | **10** | 2- and 5-thread races on one grant → exactly one execution |
| DB failure / rollback | ≥ 10 | **10** | injected audit failure, injected write failure, interrupted transaction |
| Audit integrity | ≥ 10 | **10** | chain verify, tamper, interior delete + truncation, no secrets, states |
| Static drift guards | — | **2** | every declared editor tool has a policy class; no `bridge.call` in the API omits `auth=` |

Selected results, verbatim from the run:

* two concurrent requests with one grant → `[200, 409]`, bridge called **once**;
* five concurrent requests with one grant → exactly one `200`;
* editing `auth_grants.expires_at` in SQLite → `403 forged_grant` (the signature
  covers the expiry, so "extend the grant" is forgery, not administration);
* `SecurityAudit.record` monkeypatched to raise → `403/503`, **zero** bridge calls,
  `consumed_at` still `NULL` (the transaction rolled back);
* deleting an interior audit row → `verify()` reports `broken_at` that row;
* deleting the newest row → `verify()` reports the anchored head mismatch;
* no token or `Bearer` string appears anywhere in `security_audit`.

---

## 4. Regression results

| Suite | Before (Phase 4) | After (Phase 5) |
|---|---|---|
| collected | 134 | **248** |
| passed | 133 | **247** |
| skipped | 1 | 1 |
| failed | 0 | **0** |
| new tests | — | 114 |

Also re-run: `ruff check minicoder/` clean; `tsc --noEmit` 0 errors;
`vite build` 267.40 kB (79.79 kB gzip); `render-check.tsx` **14/14**.

Functionality spot-checked after remediation: `/api/status` 200, `/api/cognition/overview`
200, `/api/generalization/overview` 200, dashboard renders all ten tabs, an
authorized tool call mutates the real editor, sleep/learning paths carry internal
contexts and their tests pass unchanged.

### Two Phase 4 tests were changed — here is exactly what and why

| Test | Old assertion | New assertion | Why it is not a weakening |
|---|---|---|---|
| `test_phase4.py::test_audit_log_records_refusal_and_grant` | `authorize=True` produces an audit row with `authorized=1` | the same call is recorded as `authorized=0`, and an explicit internal context is what produces `authorized=1` | The old assertion encoded the vulnerability: a body boolean granting authority. The new one asserts the opposite *and* adds the legitimate path. |
| `test_systems.py::test_api_chat_routes_a_poster_request_to_a_verified_skill` | POST chat → steps | POST chat → `401`; then mint a grant → same request → same steps | Keeps the behavioural assertion and adds the security one. The build path still produces editor steps. |

No assertion was deleted without an equal-or-stronger replacement.

---

## 5. Production state (what changed, what did not)

| Table | At Phase 4 audit | After Phase 5 | Explanation |
|---|---|---|---|
| episodes | 152 | 160 | executions during verification |
| semantic_nodes | 52 | 52 | unchanged |
| skills | 30 | 30 | unchanged |
| calibration | 30 | 36 | one sample per executed request |
| `audit_log` (Phase 4) | 5 | 5 | unchanged |
| `security_audit` (new) | — | 24 | 8 authorized, 4 executed, 11 rejected, 1 replayed |
| `auth_grants` (new) | — | 4 | 2 executed, 2 failed/consumed |
| provenance_events | 5 880 | 7 112 | emitters on the execution path |

* **No historical row was deleted, edited or rewritten.** No dataset, report or
  `*_latest.json` was touched by this sprint. `datasets/research/library.json` and
  `library_frozen.json` are byte-identical to their Phase 4 hashes.
* Schema migration only **adds** tables (`auth_grants`, `security_audit`) and a
  `schema_meta` key; `schema_version` 3 → 4.
* **Honest note on 13 rows:** during verification, `test_systems.py` created a
  runtime before its temporary home was active, so 13 audit rows landed in the
  live database. The fixture is now hardened (`assert db_path.startswith(home)`)
  and the leak is closed. The rows are retained because the audit trail is
  append-only and deleting them would break the chain — which is the behaviour we
  want from an audit trail.

---

## 6. Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Every consequential execution path protected | **MET** | single choke point in `EditorBridge.call`/`reset`; all mutating routes guarded (§5 of architecture) |
| 2 | Direct tool API bypasses eliminated | **MET** | attack 1–3 → `401`, zero bridge calls, canvas unchanged |
| 3 | All 12 original intent bypasses addressed | **MET** | §2 table, 32-phrase parametrised test |
| 4 | Invalid and replayed grants rejected | **MET** | forge/tamper/scope/expiry/revocation/replay tests |
| 5 | Concurrent grant reuse cannot execute twice | **MET** | 2- and 5-thread races, exactly one execution |
| 6 | Successful mutations have corresponding audit records | **MET** | `authorized` + `executed` per request id; audit failure blocks execution |
| 7 | Failed operations leave no unintended partial state | **MET (with one documented gap)** | DB mutations roll back; editor calls are single, audited `failed`; crash-between-consume-and-execute documented in architecture §11 |
| 8 | CORS explicitly configured | **MET** | allowlist + preview regex, `*` removed; evil origin gets no ACAO |
| 9 | Existing functionality passes regression | **MET** | 247 passed, 1 skipped, 0 failed |
| 10 | Adversarial suite passes | **MET** | 114/114 |
| 11 | No production memory or research history silently rewritten | **MET** | additive rows only; hashes unchanged; the 13 test rows are disclosed in §5, not hidden |

**Nothing in the acceptance list is unmet.** Two things are *limited* rather than
unmet, and they are documented rather than papered over: there is no user
identity (a capability token is not an account), and the editor mutation cannot be
made transactional with the grant consumption.

---

## 7. Remaining risks

| # | Risk | Severity | Why it remains |
|---|---|---|---|
| R1 | **No user authentication.** Any process that can read `.security/operator.token` (same OS user) is the operator. | HIGH (inherent) | Out of scope to invent an identity system; documented in the threat model. |
| R2 | **Token replay by a local attacker.** A stolen token can mint grants until revoked. | MEDIUM | No token rotation/revocation endpoint yet; bind to a TTL and rotate by deleting the file, which regenerates a token on restart. |
| R3 | **Same-process code is trusted.** `internal_context()` can be constructed by any Python code in the process. | MEDIUM (by design) | The boundary is network-facing; code execution in the process is already game over for the DB. Audited when created by an operator action. |
| R4 | **Audit anchor lives in the same database.** An attacker with full write access can recompute the chain. | MEDIUM | Hash chain detects casual edits/truncation, not a determined attacker with DB write. External anchoring is a Phase 6 candidate. |
| R5 | **Crash between grant consumption and execution** leaves an ambiguous record (consumed, no terminal row). | LOW | Cannot be made atomic across the Node pipe; detectable by querying grants with `outcome='consumed'` and no matching `executed` row. |
| R6 | **No rate limiting / DoS protection.** An unauthenticated client can spam rejected requests and grow the audit table. | LOW | Out of sprint scope; every rejection is a row. A retention policy is a follow-up. |
| R7 | **`/ws/telemetry` is unauthenticated** and streams live status to any loopback client. | LOW | Read-only, no secrets, no mutation path. Documented rather than silently accepted. |
| R8 | **The planner cannot express deletion.** "delete every layer" is refused for two independent reasons (no authority *and* no destructive step exists). | INFO | Not a security defect; a capability gap that makes the refusal look like it is doing more than it is. |

---

## 8. What a reader should not conclude

* That NACE is "secure". It has an enforceable boundary around consequential
  execution and an auditable trail of every decision. It has no user accounts, no
  per-person attribution, and no defence against code running as the operator.
* That the test suite proves safety. The suite proves the specific properties in
  §3. The threat model lists what is not covered.
* That the classification layer is the control. It is a detector; the control is
  the grant check inside `EditorBridge.call`. If the detector were deleted
  tomorrow, no unauthorized mutation would become possible — only less legible.
