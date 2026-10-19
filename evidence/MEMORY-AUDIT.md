# Independent Réplique v0.4 memory and evaluation audit

Date: 2026-10-18. Scope: backend memory/evaluation integration and frontend consent, read-only review plus isolated synthetic tests. No real login, model invocation, private conversation, external transmission, or production database was used.

## Result

The reviewed implementation has explicit opt-in storage, separate per-generation reuse, bounded local retrieval, and explicit evaluation promotion/rollback. The security-relevant findings below were returned to their owners and fixed during review. This is a local single-user feature, not account-isolated storage or an authenticated multi-user service. No claim of demonstrated model improvement is justified by these tests.

## Findings resolved during review

1. A null initial profile hid all memory controls and existing examples. The UI now supplies unsaved form defaults and keeps the stored profile null until explicit save.
2. Initializing evaluation tables changed the builtin retrieval budget from 4500 to 6000 characters. Both paths now use 4500; an independent equality check confirms initialization alone leaves selected context and revision unchanged.
3. Promotion/rollback changed selected examples without invalidating prior preview consent. Both now bump memory revision. Independent tests demonstrate actual example-count changes plus revision increments in both directions.
4. Model changes retained earlier provider consent. The model-change handler now clears provider consent, memory use, and preview; a dedicated two-model OAuth DOM test covers this.
5. Headerless same-site cross-port navigation could initiate export. Every memory route now requires X-Replique-Request: 1, and the frontend supplies it on reads and writes. Host/Origin/Fetch-Metadata protections remain active, and no CORS permission is enabled. The synthetic navigation request is rejected.

## Verified behavior and boundaries

- Inspect/export/preview on a fresh store do not create a database. Generation and clipboard copying do not save examples. Saving requires explicit consent and review; validation requires a positive/edited rating. Negative feedback is excluded from retrieval.
- Context is opt-in for each generation. Preview includes selected examples/profile. Backend generation obtains a single selected snapshot and rejects a stale revision. Save/profile/delete/expiry and active-version changes invalidate the revision. Provider consent is also required before either external provider path is called.
- Saved context is serialized as user data, with system instructions treating it as untrusted stylistic illustrations, not facts or permissions. Actual model compliance is untested.
- Local storage has no OAuth tokens or account keys. The UI explicitly says storage is unencrypted and independent of the connected ChatGPT account. Auth refresh/logout clear memory-use consent; OAuth transport validates catalog/session and existing synthetic identity/logout-race tests pass.
- SQL values are parameterized; the independent injection-shaped string remains data. Item length/count and selected-context limits are enforced. SQLite transactions, foreign keys and busy timeout are present; failures are sanitized as 503. A filesystem compromise or malicious local process is outside the HTTP protection boundary.
- Deletion cascades feedback; source deletion/expiry invalidates derived versions and reports. Delete-all removes items/profile/feedback and evaluation versions/runs/history/active selection. Rollback cannot recreate deleted examples. Export contains memory and existing evaluation records, not authentication material.
- Deletion is logical deletion of the active database, not forensic erasure, and cannot delete independent exports/backups or previously transmitted provider data. This limitation is documented.
- Evaluation uses a separate synthetic holdout, detects declared/source/input overlap, reports mechanical checks separately from explicit human scores, and blocks fixture-only promotion. Versioning changes only retrieval count/budget; it does not retrain a model, rewrite code, or change prompts automatically.
- Human review and saved-model provenance are operator attestations, not cryptographic proof. Holdout independence beyond the supplied manifest cannot be proven. CLI input files remain under the operator’s control.

## Evidence

- `memory-independent-tests.log`: full backend suite, 109 tests passed at review time.
- `memory-adversarial-check.py` and `memory-adversarial-results.log`: independent isolated test of fresh reads, same-site export block, SQL-literal safety, builtin initialization invariance, real retrieval promotion/rollback and revisions, source cascade, and complete derivative deletion.
- Frontend `npm test` passed DOM, memory, OAuth and contrast suites; `npm run build` passed. These are synthetic DOM/build checks, not a live browser accessibility or provider-quality assessment.

## Remaining limitations / final integration checks

- The application is intentionally one local user per server. Switching connected accounts does not switch databases; use separate local data directories/processes for different people.
- Model-switch hardening is complete and its dedicated DOM regression test passes. Auth refresh/logout and memory changes also clear consent. Editing the conversation requires a fresh content-review confirmation; broadening that existing behavior was outside this patch scope.
- No real-account authentication, cloud-model quality evaluation, production migration or deployment was performed. Ship claims should remain limited to implemented local retention/retrieval and the offline evaluation workflow.
