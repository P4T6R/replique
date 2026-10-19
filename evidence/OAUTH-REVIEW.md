# OAuth security and protocol review

Reviewed: 2026-10-18. Scope: single-user, single-worker application bound to IPv4 loopback. This is a code and mocked-protocol review, not a live OpenAI interoperability certification.

## Result

No remaining blocking finding identified for the documented personal local scope. Full backend suite: **67 tests passed**. Frontend production build and DOM mock suite passed independently. Fourteen additional audit tests are in `backend/test_oauth_audit.py`; run output is in `oauth-independent-tests.log`.

## Verified controls

- Fresh PKCE S256 verifier, state and nonce; five-minute attempt lifetime; one-shot callback consumption; HttpOnly, host-only, SameSite=Lax browser binding.
- Exact `127.0.0.1` callback URI reused for exchange, issued client ID rather than the registration bootstrap ID, fixed OpenAI authorization/token/resource endpoints.
- PyJWT RSA signature validation against trusted discovery/JWKS, issuer, issued-client audience, expiry, issue time, nonce, subject continuity and authorized party checks. Access tokens are not decoded as trusted identities.
- Token-response permission checks before model use, credentials retained only in process memory, no credentials in browser storage or status responses. Only host and verified registration metadata persist locally.
- Serialized rotating refresh. A mocked concurrent refresh/logout test verifies logout cancels tracked generation and cannot restore the session afterward.
- Same-origin/custom-header requirements for sensitive actions; callback-only cross-site navigation exception; no access logging in the launch script.
- Account-specific model catalog; public Responses endpoint; `store=false`, `stream=true`; completed terminal event required. Interrupted, failed, incomplete and oversized streams never yield partial proposals.
- Total network timeouts and raw stream bounds, validated metadata/auth URLs, safe structured errors, quota recovery, model-list clearing on refresh, and explicit remote-revocation uncertainty.

## Findings corrected during review

Cross-site callback guard incompatibility; malformed token/JWKS fields; absent total OAuth timeout; unbounded single SSE line; stale model catalog; missing structured error display; non-ASCII state comparison failures; catalog-level 401 recovery; logout/generation race; missing authorized-party validation; expired attempt status; nonsecret registration reuse after restart.

## Remaining limits

- One account registration per configured local data directory; this is not a hosted or multi-user service.
- Credentials do not survive process restart. Reauthorization reuses retained nonsecret registration metadata.
- No real login, consent grant, token extraction, or model request was performed. Browser/provider interoperability remains to be verified by the owner.
- Remote logout makes a bounded revocation attempt and reports uncertainty if it fails; it does not yet retry revocation with backoff.
- Initial-registration `invalid_grant` recovery does not yet retain the unverified issued client from that failed attempt.

## Official protocol references

- https://developers.openai.com/siwc/token-sharing-open-source/sign-in
- https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions
- https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference
