# Business History
*Running log of registration requirements, tax considerations, compliance items, and CEO action items.*

## 2026-05-19 — Sprint 12 Circle Input

**Calendar OAuth scope (pre-external-user gate):** `gcalendar.py` uses a service account with `calendar.events` scope — full read/write/delete on all events. Acceptable for CEO as sole user. Before any external user is onboarded, each user needs their own calendar credentials (not a shared service account). Named gate: not Sprint 12, but must be resolved before public user onboarding.

**Privacy Policy / ToS:** Emily was invited to use the app. If she counts as an external user, these documents should have been published before she logged in. CEO action item: review and publish Privacy Policy and Terms of Service before additional external users are added.

Sprint estimate: **small** from a Business perspective. No blockers on this sprint's scope.

---

## Sprint 4 Pre-Flight Check (2026-05-18)
- No compliance or regulatory blockers for Sprint 4 (Cloud Tasks job queue, multi-user Firestore namespace schema, per-user enqueue cap).
- **Upcoming CEO action item (not Sprint 4 — pre-first-real-user):** Once multi-user infrastructure is live and any non-test user is onboarded, a Privacy Policy and Terms of Service are required. These must be drafted and published before external users touch the product. CEO must review and approve final copies.
