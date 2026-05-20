# Sprint 16 — Trust Pills + Honest Dismissed Labels

**Status:** Staged
**Date staged:** 2026-05-20
**Source:** Live huddle following CEO screenshot review

---

## Goal

Restore inbox trust by (a) telling the truth about emails Hana never scanned and (b) showing the user *why* an email earned a spot in the inbox. Pills function as diagnostics — every inbox email should carry at least one. Missing pills signal a filter hole, not a neutral case.

---

## Tasks

### Task 1 — Honest Dismissed labels (frontend)
- **File:** `frontend/app.js`, function `buildProposalsSection`
- **Change:** On emails that were dismissed because the filter blocked them (i.e. Hana never ran), replace the "No to-dos found" string with **"Not scanned"** (or equivalent honest label).
- **Distinguish from:** Emails Hana actually scanned and found nothing actionable — those keep "No to-dos found."
- **Detection signal:** Use the existing dismissal/verdict metadata on the email doc. Engineer to confirm exact field at implementation time.
- **Effort:** ~15 min, pure frontend.

### Task 2 — "Known sender" pill (allowlist diagnostic)
- **Placement:** Left of sender address, top of email card. Main inbox only.
- **Trigger:** Filter verdict_reason equals `'Sender is on the permitted list'` (already written by backend).
- **Copy (Marketing locked):** **"From someone you trust"** or **"You allowlisted this sender"** — pick one at implementation. Do NOT use "Known sender."
- **Visual (Designer locked):** Low-weight outline pill. Reassurance, not alert.
- **Effort:** ~30 min, pure frontend.

### Task 3 — "Relevant topic" pill (topic-match diagnostic)
- **Placement:** Under subject line. Main inbox only. Separate row from Task 2 pill — pills must not compete.
- **Trigger:** Email matched either the "What emails belong here?" freetext box OR the Include Keywords list.
- **Display:** Echo the user's own matched phrase. Format: **"Matched: {phrase}"**. Truncate phrase at ~20 chars.
- **Backend work:** Add new field `matched_topic` to the email doc.
  - Keyword case: trivial — record which keyword matched.
  - Freetext case: extend the Gemini JSON schema to return the matched topic phrase.
- **Effort:** ~1–2 hrs backend + ~1 hr frontend.
- **Migration:** None. Additive field. Cost impact negligible.

### Task 4 — Enforce "no fallback pill" rule
- When neither Task 2 nor Task 3 conditions are met, render no pill.
- Do NOT add a generic "Inbox" or "Other" fallback. The absence of a pill is a deliberate diagnostic signal.

---

## Acceptance Criteria

1. Dismissed Emails view: an email that was blocked by the filter (e.g., promotional sender, blocked category) shows "Not scanned" (or chosen equivalent), NOT "No to-dos found."
2. Dismissed Emails view: an email that Hana actually scanned and found no actions still shows "No to-dos found."
3. Main inbox: an email from an allowlisted sender displays the "From someone you trust" / "You allowlisted this sender" pill to the left of the sender address.
4. Main inbox: an email that matched a user-supplied keyword or freetext topic displays a "Matched: {phrase}" pill under the subject line, truncated at ~20 chars.
5. Main inbox: an email where neither rule applies shows NO pill — and this state is treated as a filter bug to investigate, not a UI gap to fill.
6. Both pills use low-weight outline styling. They do not occupy the same row.
7. Backend writes `matched_topic` on all newly scanned emails. Existing emails without the field render without the topic pill (graceful degradation).

---

## Out of Scope (Explicitly Deferred to Later)

- Sprint 15 blockers (CEO smoke-test sign-off, 5 backlog decisions)
- Calendar integration ("This Week" / "Next Week" hamburger views)
- Emails flat namespace migration (`users/{user_id}/emails/`)
- React Native vs. Flutter mobile decision
- Marketing strategy definition
- Emily named-gate close
- Backfilling `matched_topic` on historical emails
- Any pill design beyond the two locked above (no category pills, no urgency pills, no fallback pills)

---

## Token / Complexity Estimates

- Engineer: medium (Task 3 backend is the heaviest piece; Tasks 1, 2, and 4 are trivial frontend)
- Marketing: small (copy already locked in huddle)
- Designer: small (visual constraints already locked in huddle)
- Finance: small (cost impact negligible — additive field, no new API calls)
- Business: small
- Strategy: small

Total sprint estimate: well within 50K output token budget.

---

## Critical Design Note (Strategy)

Pills are a diagnostic surface. An inbox email with no pill means the filter passed it for a reason the user did not configure — a hole. Sprint 16 deliberately does NOT add a fallback pill. Subsequent sprints will treat "no-pill emails" as filter bugs to investigate upstream, not UI gaps to paper over.
