# Réplique: optional local style memory

The existing cream / terracotta / sage design, typography, layout and explicit light controls are preserved. Memory appears as a collapsed optional disclosure below writing preferences, and a short explicit save flow beneath each editable reply.

## User controls
- The default is temporary. No memory fetch occurs on initial load; generation sends `use_memory:false` unless the user opts in.
- “Retenir pour mon style” opens a review step. Saves contain the current edited reply, explicit feedback, user-approved validation status, and only an optional manually entered excerpt. No conversation is copied into persistence automatically.
- Critical feedback cannot become a validated example. Copy and export of replies do not save memory or imply successful outcomes.
- The disclosure shows stored examples/feedback and lets the user create/edit explicit length/register/emoji preferences, including a fresh database whose profile is null. Unsaved default choices are labelled clearly.
- Persistence is disclosed as local, unencrypted, common to users of the server, independent of the ChatGPT account, with 30-day example retention and preferences until deletion.
- Export uses JSON download. Individual/all deletion needs a second explicit on-screen confirmation; cancellation does not call DELETE. Deletion warns that exports remain.
- “Nouvelle conversation” clears the session and says memory remains, with the separate deletion control identified.
- “Utiliser ma mémoire pour cette génération seulement” is separate from saving and off by default. It displays selected examples, optional excerpts and profile, invalidates prior provider consent, and sends the preview revision. The provider consent explicitly includes that selected saved context. It resets after generation and auth refresh/logout/session reset. Saving/deleting/editing memory also switches it off.

## Evidence
- `frontend/tests/memory.mjs` tests this flow against a synthetic API, including edited reply retention, default-empty excerpts, negative feedback exclusion, null profile onboarding, cloud disclosure/revision, one-generation opt-in, export, delete confirmation/cancellation, and reset wording.
- Existing DOM/OAuth and CSS contrast tests continue passing. CSS tokens are reused for memory.
- `replique-apercu.html` is self-contained, with embedded fonts and snapshots of the exact built React DOM. Its fourth view is explicitly synthetic memory; selected/checked states are serialized. It is a static design preview and does not claim real stored user data, model generation, browser rendering or visual QA.
- No browser was used, no OAuth or external provider call was performed, and no user memory was created/deleted for these UI tests.
