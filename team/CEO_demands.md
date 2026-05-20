# CEO Demands

Direct mandates from the CEO. Each item requires sprint assignment before work can begin.

---

- [ ] **Briefing attribution fix (prompt guard)**
  Hana must only claim an assignment in a briefing if it actually called `add_todo` or `reassign_task` that session.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Briefing attribution fix (structural)**
  Change `write_briefing` tool schema to use a `briefing_assertions` array with source tags (`'email'` vs `'hana_decision'`) so the chat layer can distinguish what Hana read vs. what Hana decided.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Restore email summary**
  Brief gray AI-generated preview text on each email card so users can decide at a glance whether to read it.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Restore task determination**
  AI extraction of potential to-dos from email content.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Restore task swiping**
  Swipe left/right on extracted tasks to accept or reject them.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Restore email highlights**
  Pertinent parts of each email highlighted for quick scanning (`source_spans` / excerpt feature).
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Briefing-to-chat context handoff**
  When user taps "Let's chat" on a morning briefing card, the chat opens with Hana's briefing message pre-loaded at the top of the conversation so Hana has full context for follow-up questions.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **Note deduplication / merge fix**
  Fix Hana's note memory so she reads existing notes before writing (search_memory first), states corrections explicitly, and the merge prompt removes the old version rather than keeping contradictory statements side by side.
  **Status:** ✓ COMPLETE — Sprint 9

- [ ] **To-do → source email → highlights**
  When a user taps a to-do and navigates to its source email, the email view should highlight the pertinent text that caused the to-do to be created (source_spans / excerpt feature).
  **Status:** ✓ COMPLETE — Sprint 10
