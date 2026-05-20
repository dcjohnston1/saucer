# Sprint 16 Meeting Notes
*Date: 2026-05-20 | PM: Project Manager Agent*

---

## Deferred Items (Carried Forward)

From prior meetings (still open, not blocking Sprint 16):
1. Privacy Policy and Terms of Service must be published before adding external users beyond Emily.
2. Calendar OAuth must move from shared service account to per-user credentials before public onboarding.
3. Sprint 15 blockers — CEO smoke-test sign-off, 5 backlog decisions — explicitly deferred per huddle.

None of the above blocks Sprint 16 engineering.

---

## Token Budget Check

Last 5h — output tokens: 48,339 | cache created: 227,486 | messages: 68
Sprint health: BORDERLINE — under 50K threshold but only barely. Sprint 16 scope must stay tight to the four staged tasks. No additions.

---

## Sprint 16 Agenda (Locked Pre-Meeting)

Sprint scope was staged in a live huddle this morning following the CEO screenshot review. The full scope, acceptance criteria, and complexity estimates are in `/home/dcjohnston1/saucer/team/sprint_16.md`.

### Four Tasks

1. **Honest Dismissed labels** — replace "No to-dos found" with "Not scanned" on filter-blocked emails in `buildProposalsSection`.
2. **"Known sender" pill** — left of sender address on main inbox cards when `verdict_reason='Sender is on the permitted list'`. Marketing copy locked: "From someone you trust" or "You allowlisted this sender" — pick at implementation.
3. **"Matched: {phrase}" pill** — under subject line on main inbox cards. Backend adds new `matched_topic` field. Phrase truncated at ~20 chars.
4. **No fallback pill** — render nothing when neither rule applies. An inbox email with no pills is a filter hole, NOT a UI gap.

### Hard Constraints

- Both pills: low-weight outline styling, separate rows.
- `matched_topic` is additive — no migration, no backfill.
- Pre-sprint: commit and push current state to GitHub (Standing Rule 1).
- All terminal work runs through agents/Coder — no CEO commands (Standing Rule 2).

---

## Meeting Circle Log

### Round 1

**Engineer:**
Sprint scope already validated in huddle. Implementation notes for Coder:
- Task 1 detection signal: check `verdict` field on the email doc. If `verdict='blocked'` and there's no `proposals` field (i.e., agent never ran), show "Not scanned." If `verdict='permitted'` and `proposals` is empty/null, show "No to-dos found" (agent looked and found nothing). Need to confirm at implementation — may need additional flag if verdict alone is ambiguous.
- Task 2 backend field already exists. Frontend reads `email.verdict_reason` and renders the pill conditionally. Trivial.
- Task 3 backend: keyword fast-track in `routes/agent.py` and `routes/emails.py` already records which keyword matched at filter time (Sprint 15 hotfix). Just need to persist the matched keyword on the email doc. For freetext case, extend `_INTENT_VERDICT_RULES` JSON schema in `email_scanner.py` to return a `matched_topic` string when verdict=permitted via topic match.
- Task 4 enforcement: explicit guard in frontend — only render pill DOM when condition met. No else-branch.
- Estimate: medium overall. Backend ~1.5 hrs, frontend ~1.5 hrs. ~5,000–6,000 tokens.
- Pre-sprint git push: will run as first step.
No objection.

**Marketing:**
Copy already locked in huddle. One follow-up: prefer "From someone you trust" over "You allowlisted this sender" for emotional warmth — recommend Coder pick the first option at implementation. The second sounds technical/IT. No other concerns.

**Designer:**
Visual constraints locked. Two reinforcements for Coder:
- "Low-weight outline pill" = 1px border, no fill, small font (0.7em), 4px horizontal padding, 2px vertical, rounded corners ~3px. Color: neutral gray (#999 border, #666 text) — NOT accent color.
- "Separate rows" = the trust pill (Task 2) lives in the sender row (top of card); the topic pill (Task 3) lives in the subject/body row. They must NEVER appear in the same DOM row, even if both apply to the same email.
- Truncation: CSS `text-overflow: ellipsis` with `max-width: 140px` on the topic pill. The "Matched: " prefix stays full; the user phrase truncates.
No objection.

**Finance:**
Cost impact negligible — additive field on email docs, no new Gemini calls, no extra reads. Freetext case adds one extra string to the existing Gemini JSON response, which is rounding error on prompt cost. Approved. No objection.

**Business:**
The honesty fix in Task 1 is the highest business value item this sprint — it's the direct CEO trust signal. The diagnostic pill philosophy in Task 4 is strategically right: building diagnostics now means we catch filter holes before users do. No objection. Approved.

**Strategy:**
Closing the circle. Two strategic notes:
1. The "no fallback pill" rule (Task 4) creates a forward commitment: Sprint 17+ must include a process for investigating no-pill emails as filter bugs. Recommend the PM add a standing item to the post-sprint review: "Did any no-pill emails reach the inbox? If yes, investigate upstream." Not blocking Sprint 16 — just flagging it for the plan.
2. Token budget at 48K is the real risk. If anything in Sprint 16 expands scope mid-flight (e.g., "while we're in there, let's also fix X"), defer it to Sprint 17. No exceptions.
No objection to Sprint 16 scope as staged.

### Round 1 — Result

Clean consensus. No objections raised. No Round 2 needed.

---

## Token Estimates

| Agent | Estimate |
| --- | --- |
| Engineer | 5,000–6,000 tokens (Task 3 backend is heaviest) |
| Marketing | None (copy locked) |
| Designer | None (visuals locked) |
| Finance | None |
| Business | None |
| Strategy | None |

Total sprint estimate: 5,000–6,000 tokens. Well within the remaining headroom even with current 5h usage at 48K.

---

## Sprint 16 Plan — Coder Instructions

See `/home/dcjohnston1/saucer/team/sprint_16.md` for the locked sprint definition. Coder should treat that file as source of truth.

### Pre-Sprint (Standing Rule 1 — mandatory)

Before any code change:
```
cd /home/dcjohnston1/saucer && git status && git log --oneline -3
```
If uncommitted changes exist (including Sprint 15 hotfixes), commit and push to GitHub before writing Sprint 16 code.

### Task Execution Order

1. **Task 1** (honest Dismissed label) first — pure frontend, fastest win, restores trust on the most visible screen.
2. **Task 3 backend** (matched_topic field write) — must ship before Task 3 frontend can render.
3. **Task 3 frontend** (topic pill rendering).
4. **Task 2** (known-sender pill) — pure frontend, can be done in parallel with Task 3 frontend.
5. **Task 4** (no-fallback enforcement) is a discipline rule on Tasks 2 and 3 — verify by inspection at the end.

### Acceptance Criteria

Per `sprint_16.md`. All seven criteria must pass before sprint close.

### Deploy

After code changes: `./deploy.sh backend` and `./deploy.sh frontend`. Record new revision numbers. Verify each acceptance criterion in the live app before declaring sprint complete.

### Standing Rule 2

All terminal work is on Coder/agents. Do NOT route any command to the CEO unless it requires OAuth, billing, or account-level authorization. Smoke testing and verification: Coder runs against the live deploy, not the CEO.
