# Phase 5 — Threat Model

Scope: the NACE runtime as it exists after the Phase 5 remediation — one FastAPI
process, one SQLite brain, one Node editor process, one single-user local
deployment.

---

## 1. Assets

| Asset | Why it matters | Where it lives |
|---|---|---|
| The design on the canvas | Direct user work; destructive loss is unrecoverable within a session | Node editor process |
| Brain memory (`brain.db`) | Episodic/semantic/procedural knowledge, provenance, calibration | `memory/brain.db` |
| Research datasets and history | Blind experiments, seeds, frozen libraries — the evidential record | `datasets/research/*` |
| Audit trail | The record of who did what; worthless if editable | `security_audit` |
| Operator credential | The capability that authorizes everything | `.security/operator.token` (0600) |
| Grant signing key | Prevents forged grants | `.security/grant.key` (0600) |
| Private evaluation store | Salt + hidden tasks; leakage invalidates results | `~/.local/share/nace-private` (0700) |

---

## 2. Actors

| Actor | Capability | Trust |
|---|---|---|
| **Operator (human)** | Owns the machine account, reads `.security/operator.token` | Fully trusted |
| **Operator's browser** | Same-origin dashboard; can be given the token by the operator | Trusted after the token is pasted |
| **Local process, same OS user** | Can read the token file and `brain.db` | Equivalent to the operator (documented) |
| **Local process, different OS user** | Can reach loopback HTTP, cannot read files (0600/0700) | **Untrusted** — this is what the token boundary excludes |
| **Web page in the operator's browser** | Can send cross-origin requests; cannot read responses (CORS) or the token | **Untrusted** — the Phase 4 critical defect |
| **Remote network client** | Only if the operator binds `0.0.0.0` and exposes the port | **Untrusted** |
| **Candidate program / model output** | Runs inside the sandbox during research | **Untrusted** (handled by the private store + escape suite) |

---

## 3. Trust boundaries

```
┌──────────────────────────── operator's OS user ────────────────────────────┐
│                                                                            │
│  CLI / scripts ── internal_context() ─┐                                    │
│  sleep worker ── internal_context() ──┤                                    │
│                                       ├──► EditorBridge.call ──► editor    │
│  dashboard ── bearer + grant ─────────┤        ▲                           │
│                                       │        │ check_tool (choke point)  │
│  HTTP clients ── bearer + grant ──────┘        │                           │
│         ▲                                      │                           │
└─────────┼──────────────────────────────────────┼───────────────────────────┘
          │                                      │
   ───────┴──── boundary 1: token ────────   boundary 2: grant (single-use)
          │
   ───────┴──── boundary 3: CORS (browser only, not authentication)
```

* **Boundary 1 — capability:** only holders of the operator token can mint grants
  or present a valid principal.
* **Boundary 2 — grant:** even with a token, every consequential operation needs a
  fresh, scoped, single-use grant consumed at the execution point.
* **Boundary 3 — browser origin:** CORS stops a hostile page from reading
  responses and stops preflighted requests; it is a browser control, not a server
  control, and the design does not rely on it.

---

## 4. Threats considered (and the control)

| # | Threat | Control | Verified by |
|---|---|---|---|
| T1 | Unauthenticated destructive request to the tool endpoint | Bearer + grant at the bridge | attacks 1–3, tests `b01`–`b03` |
| T2 | Destructive *phrasing* that the classifier misses | Enforcement does not depend on classification; the grant must name the instruction hash | 32-phrase suite, `b13`, `c12` |
| T3 | Replaying a captured grant | `consumed_at` atomic claim → `409` | `c03`, `d01`, `d02` |
| T4 | Two concurrent uses of one grant | `BEGIN IMMEDIATE` + conditional `UPDATE`; one winner | `d01`,`d02`,`d04` |
| T5 | Forging or guessing a grant id | HMAC over every field | `b04`, `c08`, `c09`, `c04b` |
| T6 | Widening a grant (different tool, resource, instruction) | Scope/resource/action binding | `b03`, `c05`, `c06`, `c07` |
| T7 | Extending an expired grant by editing the DB | Signature covers `expires_at` → `forged_grant` | `c04`, `c04b` |
| T8 | Smuggling authorization in the request body | Only `x-nace-grant` header is read; `authorize` is dead | `b10`, `b11` |
| T9 | Unknown tool smuggled past the policy | Unknown ⇒ rejected, even with a token and grant | `b05`, `b06`, `b07` |
| T10 | Audit tampering to hide an action | Hash chain + anchored head | `f02`, `f03` |
| T11 | Executing when the audit cannot record it | Consumption + audit in one transaction; `503` otherwise | `e01` |
| T12 | Partial writes on failure | Transactional DB mutations; audited `failed` for editor errors | `e02`, `e03`, `e08` |
| T13 | Hostile web page driving the editor | CORS allowlist; no `*`; no credentials | live preflight check, `b*` |
| T14 | State-changing GET (CSRF via `<img>`) | snapshot is POST + grant | `b18` |
| T15 | Token leaking into logs/audit | `record()` rejects token-shaped payloads; principal is a fingerprint | `f07`, `c16` |
| T16 | Privilege via internal helpers | Internal contexts require in-process code, not an HTTP request | `c*` (no HTTP path constructs one) |
| T17 | Leaking hidden evaluation data to a candidate | Private store outside the repo, 0700/0600, 22-probe escape suite | Phase 4 audit E-08/E-14, re-run |

---

## 5. Out of scope (and why)

| Area | Reason |
|---|---|
| User accounts, passwords, SSO | The product has no user model; inventing one to look secure was explicitly excluded by the brief. |
| Multi-tenant isolation | Single-user local deployment. |
| Transport security (TLS) | Terminated by whatever fronts the process; the app speaks plain HTTP on loopback. |
| Malware on the operator's machine | If the OS account is compromised, the token and the database are readable. |
| Model-level attacks (prompt injection that convinces a human to approve a grant) | A human approving a scoped, single-use grant is the intended safety property, not a bypass. |
| Denial of service | No rate limiting; documented as R6. |

---

## 6. The honest limitation: this is not authentication

NACE has **no identity system**. It has a **capability**:

* the token file is readable only by its owner (0600) in a 0700 directory;
* holding it is indistinguishable from being the operator;
* principals are `operator:<fingerprint>` — they distinguish *tokens*, not people.

Therefore:

1. **Do not** describe NACE as "authenticated" in a multi-user sense. The correct
   description is "consequential operations require a local capability and a
   single-use grant".
2. On a shared machine, another user cannot read the token file, but *can* reach
   the loopback port. They receive `401` — which is the improvement over Phase 4.
3. If the operator enables remote access (`0.0.0.0`), anyone who obtains the token
   becomes the operator. There is no second factor and no session expiry beyond
   the grant TTL. Bind to loopback unless a reverse proxy with its own
   authentication is in front.

---

## 7. Residual risk register

| ID | Risk | Likelihood | Impact | Severity | Treatment |
|---|---|---|---|---|---|
| R1 | Same-OS-user process reads the token | Medium | High | HIGH | Accepted; inherent to a local single-user tool |
| R2 | Stolen token replayed until rotated | Low | High | MEDIUM | Rotate by deleting `.security/operator.token` and restarting; grant TTLs bound exposure |
| R3 | In-process code constructs `internal_context` | Low | High | MEDIUM | Accepted: process-level code execution already implies DB access |
| R4 | Audit chain recomputed by an attacker with DB write | Low | Medium | MEDIUM | Detectable only against casual edits; external anchoring proposed for Phase 6 |
| R5 | Crash between consume and execute leaves ambiguity | Low | Low | LOW | Detectable: `outcome='consumed'` with no terminal audit row |
| R6 | Unbounded rejected-request growth | Medium | Low | LOW | Retention/rate-limit follow-up |
| R7 | `/ws/telemetry` unauthenticated on loopback | Low | Low | LOW | Read-only; documented |
| R8 | Classifier false positive blocks a benign build | Low | Low | INFO | Fail-closed by design; the operator can mint a grant and proceed |

---

## 8. Assumptions

1. The server runs as a single OS user; `.security/` is not group/world readable.
2. `brain.db` and `.security/` are on a local filesystem the operator controls.
3. The Node editor process is a child of the API process and is not separately
   exposed to the network.
4. The operator does not paste the token into an untrusted page. (The dashboard
   keeps it in `sessionStorage`, scoped to the tab.)
5. Time is monotonic enough for TTLs; the system uses UTC second precision, so a
   grant may live up to ~1 s longer than its nominal TTL. This is acceptable for
   60–120 s grants and is noted for completeness.

---

## 9. Review triggers

Re-open this model if any of the following changes:

* a second user or a hosted deployment appears (R1 becomes a real gap);
* an endpoint is added that calls `bridge.call` without a context;
* the tool table grows (a new tool must be classified, or it is rejected and the
  inventory test fails);
* the audit table is written from any module other than `security/audit.py`;
* the token file moves outside the home or its mode changes.
