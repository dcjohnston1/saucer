# Sprint 17 Meeting Notes
*Date: 2026-05-20 | PM: Project Manager Agent*

---

## Deferred Items (Carried Forward)

From Sprint 16 and prior meetings (still open, not blocking Sprint 17 engineering):
1. Privacy Policy and Terms of Service must be published before adding external users beyond Emily.
2. Calendar OAuth must move from shared service account to per-user credentials before public onboarding.
3. Sprint 15 backlog — CEO smoke-test sign-off + 5 backlog decisions — still outstanding.
4. Standing review item (Strategy, Sprint 16): After every sprint, check whether any pill-less emails reached the inbox. If yes, investigate as a filter hole.
5. GTM open decisions: real estate beachhead vs. dual-income parents as primary segment; $20/mo real estate price point (required before GTM work begins).
6. Emily gate: Emily must run Hana at least once (named gate, still open).

None of the above blocks Sprint 17 engineering.

---

## CEO Feedback on Sprint 16 (Delivered at Sprint Start)

Sprint 16 delivered trust pills and honest Dismissed labels. Two bugs reported by CEO in the live smoke test:

**Bug A — Pill-less spam in main view:**
A Nextdoor email (from reply@ss.email.nextdoor.com, subject "Closed for good!!") passed through the scanner, produced no to-dos, matched no keyword filter, and appeared in the main view with no pill and "No to-dos found." There is no signal to the user explaining why it's there.

CEO diagnosis: emails with no pill and no to-dos are invisible — the user cannot tell what Saucer thinks of them or why they are in the view.

**Bug B — Contradictory label on trusted-sender card:**
The first email (from dcjohnston1@gmail.com) shows "From someone you trust" pill AND has an extracted to-do AND also shows "No to-dos found" at the bottom of the same card. These are mutually contradictory — the card claims both that a to-do was found and that no to-dos were found.

---

## Token Budget Check

5h output token trend (estimated from Sprint 16 notes + Sprint 16 execution): ~53K–54K. Marginally above the 50K flag threshold. Sprint 17 scope held tight to two well-defined tasks. No additions.

---

## Sprint 17 Agenda (Locked Pre-Meeting)

Two CEO-reported bugs from Sprint 16 smoke test:

**Bug A — Pill-less spam in main view:**
Nextdoor email (reply@ss.email.nextdoor.com, "Closed for good!!") in primary inbox with no pill and "No to-dos found." No signal to user. Filter hole made visible by Sprint 16 no-fallback rule.

**Bug B — Contradictory label on trusted-sender card:**
Self-email (dcjohnston1@gmail.com) shows trust pill + swipeable to-do + "No to-dos found" on the same card. Mutually contradictory.

### Two Tasks

1. **Task 1 (Bug B)** — Fix `buildProposalsSection` to suppress "No to-dos found" when at least one proposal card was rendered. Pure frontend. Small.
2. **Task 2 (Bug A)** — Route pill-less emails to a collapsed "Other Emails" secondary tray at the bottom of the inbox. Pure frontend, in-memory classification using existing `verdict_reason` and `matched_topic` fields. Medium.

### Hard Constraints

- No new Gemini calls, no new Firestore reads — classification is in-memory.
- "Other Emails" tray is collapsed by default; emails are never silently hidden.
- Pre-sprint: commit and push current state to GitHub (Standing Rule 1).
- All terminal work runs through agents/Coder (Standing Rule 2).

---

## Meeting Circle Log

### Round 1

**Engineer:**
Bug B is a pure `buildProposalsSection` fix in `app.js`. The fallback "No to-dos found" is appended regardless of whether proposal rows were rendered. Fix: only render it when `proposals` is null/undefined/empty (length === 0). If any proposal card was rendered, suppress the fallback entirely. Small — ~30 minutes.

Bug A: The pill-less email is `verdict=permitted` but has no sender pill and no topic pill. This is the filter hole Sprint 16 was designed to expose. Backend options exist (filter-gap routing logic) but pure frontend classification is the right Sprint 17 call — use existing fields `verdict_reason` and `matched_topic` to split the email list in-memory into primary and secondary buckets. No backend work needed this sprint. Moderate — ~1.5–2 hours frontend.

Token estimate: 3,000–4,000 tokens. No objection.

**Marketing:**
Bug B is the most urgent trust issue. A user seeing "From someone you trust" on the same card as "No to-dos found" loses confidence in Hana's accuracy. Fix this first. Bug A routing is the right long-term call — the primary inbox must be a curated, high-signal space. Support "Other Emails" tray approach. No new pill needed. No objection.

**Designer:**
Bug B fix must restructure `buildProposalsSection` so the fallback is only injected when rendered card count is zero — not just when the proposals array is empty. Audit the function for other edge cases that could produce contradictory text. For Bug A: support "Other Emails" collapsed tray over silent auto-dismiss. Users must not feel Hana is hiding things. Collapsed section is transparent and non-alarming. No objection.

**Finance:**
Bug B: trivial, no cost impact. Bug A: classification must be pure in-memory from existing Firestore fields — no additional Gemini calls or Firestore reads. On that condition, approved. No objection.

**Business:**
Bug B is not optional — it directly undermines the Sprint 16 trust-pill investment. Bug A is a product integrity commitment: the "No pill = filter hole" rule we locked is a promise to the user that the inbox is curated. Route pill-less emails out to the secondary tray. No objection.

**Strategy:**
The pill-less email appeared on the CEO's first smoke test — this validates the Sprint 16 diagnostic philosophy and confirms real filter gaps. Sprint 17 should define the long-term routing policy, not just patch this one email. "Other Emails" tray is the durable answer. Also flag: the Bug B fix should be audited broadly to ensure no other card state in `buildProposalsSection` can produce contradictory text. No objection.

### Round 1 — Result

Clean consensus. No objections raised. No Round 2 needed.

---

## Token Estimates

| Agent | Estimate |
| --- | --- |
| Engineer | 3,000–4,000 tokens (Bug B small, Bug A medium) |
| Designer | ~500 tokens (layout review for tray) |
| Marketing | None |
| Finance | None |
| Business | None |
| Strategy | None |

Total sprint estimate: **3,000–4,500 tokens.** Within budget.

---

## Sprint 17 Plan — Coder Instructions

See `/home/dcjohnston1/saucer/team/sprint_17.md` for the locked sprint definition. Treat that file as source of truth.

### Pre-Sprint (Standing Rule 1 — mandatory)

Before any code change:
```
cd /home/dcjohnston1/saucer && git status && git log --oneline -3
```
If uncommitted changes exist, commit and push to GitHub before writing Sprint 17 code.

### Task Execution Order

1. **Task 1** (Bug B — contradictory label) first — smallest, highest trust impact, pure frontend.
2. **Task 2** (Bug A — Other Emails tray) second — pure frontend, in-memory classification.
3. After both tasks: `./deploy.sh frontend`. Record new revision number. Verify all 7 acceptance criteria against the live deploy before declaring sprint complete.

### Acceptance Criteria (all 7 must pass)

1. A card with a trust pill AND at least one swipeable proposal shows NO "No to-dos found" text.
2. A card with null/undefined/empty proposals still shows "No to-dos found."
3. Pill-less emails (verdict=permitted, no verdict_reason match, no matched_topic) are absent from the primary inbox list.
4. Those emails appear in the "Other Emails" collapsed secondary section.
5. The tray is collapsed by default and shows a count.
6. Expanding the tray shows normal email cards.
7. No additional Gemini calls, Firestore reads, or API requests introduced.

### Standing Rule 2

All terminal work is on Coder/agents. Do NOT route any command to the CEO unless it requires OAuth, billing, or account-level authorization.
