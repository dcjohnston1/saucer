# Sprint 17 — Inbox Signal Integrity

**Status:** Staged
**Date staged:** 2026-05-20
**Source:** CEO smoke-test feedback on Sprint 16 — two bugs reported

---

## Goal

Fix two trust regressions surfaced by CEO smoke-test of Sprint 16:
1. Trusted-sender cards show contradictory "to-do present" + "No to-dos found" at the same time.
2. Emails with no pill and no to-dos appear in the primary inbox with zero explanatory signal.

Both bugs undermine the trust-pill investment made in Sprint 16. They must ship together.

---

## Tasks

### Task 1 — Fix contradictory "No to-dos found" on cards with proposals (Bug B)

**File:** `frontend/app.js`, function `buildProposalsSection`
**Problem:** The "No to-dos found" fallback text is appended outside or after the proposals rendering loop. When `proposals` has items, at least one swipeable card renders — but the fallback text also renders below it, producing a contradictory card.
**Fix:** Make the fallback conditional on zero rendered proposal cards. Only show "No to-dos found" when `proposals` is null, undefined, or an empty array (length === 0). If any proposal card was rendered, suppress the fallback entirely.
**Scope:** Pure frontend. One conditional change to `buildProposalsSection`.
**Acceptance:** A card with at least one swipeable to-do proposal must never show "No to-dos found" anywhere on the card.
**Effort:** Small. ~30 minutes.

### Task 2 — Route pill-less emails to an "Other Emails" secondary tray (Bug A)

**Problem:** Emails that pass the filter (verdict=permitted) but have no matched sender pill and no matched topic pill appear in the primary inbox with no explanatory signal. Sprint 16 intentionally left these as diagnostic signals (filter holes), but they are now visible to the user without context.
**Fix:** In the frontend email list rendering (`app.js`), classify emails into two buckets:
- **Primary inbox** — emails that have at least one of: `verdict_reason === 'Sender is on the permitted list'` OR `matched_topic` is non-empty.
- **"Other Emails" tray** — emails where neither condition is met (no trust pill, no topic pill).

Render the "Other Emails" tray as a collapsed secondary section at the bottom of the inbox view, below the primary list. It should be visually distinct and labeled clearly. Users can expand it to review; emails are never silently hidden.

**Classification logic:** Pure frontend, in-memory. Uses existing Firestore fields `verdict_reason` and `matched_topic` — no new backend calls, no new Gemini evaluations, no new Firestore reads.
**Design:** Collapsed by default. Header: "Other Emails (N)". Low-prominence styling — not alarming, not hidden. Expandable by tap/click.
**Scope:** Pure frontend. No backend changes required.
**Acceptance:** Pill-less emails do not appear in the primary inbox. They appear in the "Other Emails" collapsed section. The section count is accurate.
**Effort:** Medium. ~1.5–2 hours frontend.

---

## Acceptance Criteria

1. A card with a "From someone you trust" pill AND at least one swipeable proposal card shows NO "No to-dos found" text anywhere on the card.
2. A card with no proposals (null/undefined/empty) continues to show "No to-dos found" — unchanged behavior for genuinely empty scans.
3. An email with `verdict=permitted`, no `verdict_reason` match, and no `matched_topic` does NOT appear in the primary inbox list.
4. That same email appears in the "Other Emails" collapsed secondary section at the bottom of the inbox.
5. The "Other Emails" tray is collapsed by default and displays a count of emails inside.
6. Expanding the tray shows the emails with their normal card rendering.
7. No additional Gemini calls, Firestore reads, or API requests are introduced by either fix. Classification is in-memory.

---

## Out of Scope (Explicitly Deferred)

- BACKLOG-01 (Gmail Watch Expiry Monitor) — still backlog, not urgent
- Privacy Policy / Terms of Service publication
- Calendar OAuth per-user credentials
- Emails namespace migration
- Emily named-gate close
- React Native vs. Flutter mobile decision
- Marketing / GTM strategy (beachhead decision)
- Any additional pill types beyond the two from Sprint 16
- Server-side routing of pill-less emails (filter gap fix) — deferred until pattern of pill-less emails is better understood from the "Other Emails" tray data

---

## Implementation Order

1. Task 1 first (Bug B) — smallest, highest trust impact, zero risk of regression.
2. Task 2 second (Bug A) — pure frontend classification, no backend changes.
3. After both tasks: deploy frontend. Record revision number. Verify acceptance criteria 1–7 against live deploy.

---

## Pre-Sprint (Standing Rule 1 — Mandatory)

Before any code change:
```
cd /home/dcjohnston1/saucer && git status && git log --oneline -3
```
If uncommitted changes exist, commit and push to GitHub before writing Sprint 17 code.

---

## Standing Rule 2

All terminal work runs through agents/Coder. Do NOT route any command to the CEO unless it requires OAuth, billing, or account-level authorization.
