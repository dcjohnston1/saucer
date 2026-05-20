# Designer History
*Running log of UX decisions, flow designs, and usability concerns.*

## 2026-05-19 — Sprint 12 Circle Input

**Item 2 (swipe cards):** Directional discrimination threshold: `|deltaX| > |deltaY| * 1.5` to prevent accidental accepts on diagonal gestures. This is the critical calibration point.

**Item 3 (highlights on card):** Do not try to match source_spans phrases inline in the AI summary — they won't always align. Instead, render source_spans as a highlighted quote block below the summary on the card. Always visible, always accurate.

**Item 4 (auto calendar, dismissable):** Recommend a "Added to calendar" chip at top of calendar section that auto-fades after 5 seconds. Tap to undo. Subtle but alive.

**Items 7+8:** Same "View source email" affordance and same excerpt drawer behavior for both. No UX variance.

Overall sprint estimate: medium (gesture calibration + highlight-on-card interaction require precision).

---

## 2026-05-20 — CEO Screenshot Review

**Problem identified:** Red notification dots on all three filter tabs while email cards show "No to-dos found" is a direct contradiction. Red dots signal urgency; "No to-dos found" signals nothing to act on. This destroys the user's trust in the triage system.

**Recommendation:** "No to-dos found" cards should not surface in the main inbox view. If Hana determines no to-dos exist in an email, it belongs in Dismissed — not displayed with a null-state label. Showing the card at all undermines Hana's core value proposition (she triages so you don't have to).

**Secondary concern:** Notification dot logic needs to be tied to meaningful signal — a dot should only appear when there is genuinely actionable content in that filter tab.

---

## 2026-05-20 — Dismissed View (huddle)

A safety alert and a Best Buy promo bear the identical label "No to-dos found." Same treatment flattens user trust — promo and civic alert are not equivalent. Need category-aware dismissal reasons (e.g., "Promotion", "FYI / Community").

---

## 2026-05-20 — Trust-signal pills (huddle)

CEO proposed two pills to fix trust-flatness:
- "Known sender" pill — left of sender address
- "Relevant topic: [X]" pill — under subject line

**Decisions:**
- Approved in principle. Pills live in different spatial zones (sender row vs. subject row) so they don't compete visually.
- Low visual weight — subtle outline style, not filled. These are reassurance signals, not alerts.
- When NEITHER condition applies: show nothing. No "Uncategorized" or "Unknown" pill. Absence is the neutral state; a pill admitting "we don't know" actively erodes trust in Hana's judgment.
- Truncate topic pill text at ~20 chars with ellipsis. Freetext topic entries can be long and will blow up card layout.
- If both pills appear on same card, that's fine — they're in separate rows, no stacking conflict.

---

## 2026-05-20 — Trust pills, CEO challenge (huddle)

CEO: "if neither pill applies, why is the email in inbox at all?" Conceding. If our filter has exactly two paths in, absence of both = filter failure, not a neutral state. Email belongs in Dismissed, not in inbox naked. No fallback pill needed because the case shouldn't exist. If it does, that's an Engineering bug to log, not a UX surface to dress up.
