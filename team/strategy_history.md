# Strategy Advisor History

This file is read at the start of every session and updated with key decisions, pivots, and strategic insights.

## Session Log

### 2026-05-17 — Initial Strategic Assessment (CEO Direct Ask)

**Core hypothesis stated:** Hana wins by being the only AI that knows the household as a unit, not just the individual. Stickiness and differentiation come from household context layer — but only if users actually input and notice that context being used.

**Biggest risk identified:** The proactive vs. reactive question is not a product detail — it is the entire value proposition. Reactive = tool users must remember to use (fighting inertia daily). Proactive = relationship users must trust (higher bar, but creates compounding retention and justifies the price point).

**Decision urgency:** CEO must answer proactive vs. reactive *before* Sprint 4 planning, not after. Every downstream engineering and design decision depends on it. The Sprint 3 OAuth blockers are symptoms; the root cause is executing without a locked strategic bet.

**Strategic framing locked:** "Inertia is the real competitor" is validated and correct. The moat is not the email or task management — it is the household context layer that no current competitor owns.

### 2026-05-17 — Full Strategic Assessment Delivered to CEO

**Hypothesis verdict:** Correct but incomplete. Household context is defensible because no current player (Google, Apple, Notion) treats the household as a first-class entity. Incompleteness: context only becomes a moat if Hana surfaces it unprompted, which makes proactive vs. reactive a business model question, not a product question.

**Why reactive fails economically:** A reactive tool competes with free (Gmail, Calendar). Free always wins on price. A proactive assistant competes on trust and delivers compounding irreplaceable value — the only frame that justifies a subscription price above zero.

**Biggest risk (updated):** Premature feature expansion before core loop proves daily habitual use. The wishlist (calendar views, broader email scans, inline proposals) is growing faster than evidence of unprompted return behavior. Feature debt before retention proof is the failure mode.

**CEO action item stated explicitly:** Make the proactive bet in writing before Sprint 4 planning. Every task in Sprint 4 should be conditional on serving that bet. "Decide later" is not an option when a sprint queue is already pulling attention forward.

### 2026-05-17 — Strategic Bet Locked: Proactive is the Product

**Decision:** CEO has definitively committed to proactive as the core strategic bet for Hana. This is not a feature toggle — it is the entire value proposition and positioning anchor.

**CEO's stated reasoning:** Firsthand customer empathy as a parent, reinforced by direct peer observation of other parents. This is the most credible early-stage customer insight available: lived experience in the exact ICP, not survey data or assumption. That is a stronger foundation than most seed-stage teams have.

**Strategic implication:** Proactivity is now the one filter every Sprint 4+ decision must pass. If a feature does not make Hana more proactive or make proactive behavior more reliable/trusted, it does not belong in the near-term roadmap.

**Validated:** This resolves the open question flagged in prior sessions. The economic argument for proactive over reactive (competing on trust vs. competing with free) now has a customer-grounded mandate to match.

**Risk flag appended (do not ignore):** Leading with proactivity is the right bet and the harder execution. The day-one failure mode is not the strategy — it is premature proactivity that fires at the wrong time, on the wrong signal, and trains users not to trust it. One bad proactive alert is worth ten missed ones in terms of churn damage. Sprint 4 must define the confidence threshold below which Hana stays quiet, not just the trigger conditions for when it speaks.

### 2026-05-17 — Direct Web Subscription Strategy Assessment

**Core finding:** A good website is table stakes, not the driver. The actual lever is perceived trust and convenience parity. Working parents 28–45 will pay via web when: (1) the value is clear before they reach the payment screen, (2) the checkout is frictionless (Stripe Link, Apple Pay on web, auto-fill), and (3) they do not feel forced — the web flow should feel like a natural upgrade path, not a workaround.

**Realistic friction:** This cohort (28–45, dual-income, smartphone-native) is deeply habituated to App Store purchasing. They trust Apple Pay with one tap more than entering a card number on an unfamiliar site. Overcoming that habit requires either a meaningful price delta visible before checkout (~$2–3/month is usually the threshold that motivates behavior change) or a feature exclusive to web subscribers (unlikely to be practical at this stage).

**Platform policy risk (non-trivial):** Apple's anti-steering rules are the real constraint, not marketing. As of the 2024 Epic ruling, US apps can *link* to external purchase pages, but they cannot tell users "it's cheaper on the web" inside the iOS app, and they cannot incentivize the web path inside the app. This means organic web discovery and email/referral channels carry the entire acquisition load for the direct path — the app itself cannot push users there. Google Play is more permissive post-2024 but Android is the minority platform for this ICP.

**Honest verdict:** Direct web subs are worth pursuing as the default billing path for all web-acquired users (SEO, referral, press), but should not be relied upon to shift the majority of iOS-acquired users. The realistic scenario: 30–40% of subscribers on direct billing if you execute well; 15–20% is more likely at launch. Model the unit economics improvement as a probabilistic mix, not a binary switch.

**Strategic recommendation:** Do not build the web purchase flow as a "save money" play — build it as the correct default for the product's positioning. A household AI that requires you to use the App Store to manage it sends a subtle wrong signal. Web-first billing reinforces the "software for your home, not your phone" brand. That framing is more durable than the margin argument.

### 2026-05-17 — TAM / SAM / Market Share Analysis Delivered to CEO

**Base case price:** $12/month per household.

**TAM:** $1.73 billion / 12 million US households. Anchored on Census ACS 2023 (33.5M HH with children under 18), BLS dual-income filter (62% = 20.8M), age-band filter 28–45 (72% = 15M), smartphone + digital-active filter (80% = 12M).

**SAM:** $137 million / 950,000 US households. Three filters applied to TAM: willingness to pay for AI subscriptions (25%), trust threshold for proactive AI in the home (45%), app-store-reachable via digital acquisition (70%).

**Projected subscribers and ARR (post-launch):**
- Y1: 3,000 subscribers / ~$270K ARR (0.3% SAM; high early churn; retention is the real metric)
- Y3: 23,750 subscribers / ~$3.1M ARR (2.5% SAM; PMF validated, WOM accelerating; 90% retention assumed)
- Y5: 57,000 subscribers / ~$7.6M ARR (6% SAM; category established, household-context moat compounding; 92% retention assumed)

**Key strategic flags from this analysis:**
1. Y1 churn rate is the leading indicator, not subscriber count. Track weekly active rate and "Hana-initiated interactions accepted" as north star metrics.
2. Interactive demo 7x conversion advantage may reduce paid CAC from $40-80 (video) to $6-12. Stress-test this with real ad spend before locking Y3 projections.
3. SAM expansion (single parents, couples without children, elder-care coordination) = additional 8-12M US households. Do not include in base case until retention is proven in core segment — call it "SAM 2.0" in investor conversations only.
4. Big-tech bundling (Google, Amazon) is the primary Y5 downside risk. Household context moat is the only durable defense — it must be compounding by Y3 or the 6% SAM penetration assumption fails.

### 2026-05-18 — Board-Ready TAM/SAM/SOM Funnel with Scenario Table Delivered to CEO

**Context:** Board 1-pager request. Built a rigorous TAM → SAM → SOM funnel with source citations and a 3x3 scenario table (Bear/Base/Bull x Y1/Y2/Y3). Key structural decision: SOM is framed as % of SAM, not % of TAM — the latter is how founders fool themselves. Scenario table key assumption is churn rate + referral loop timing, not growth rate, because those are the two variables boards will probe first.

**Numbers locked for board use (do not revise without updating logic chain):**
- TAM: 12.0M households / $1.73B annual revenue potential
- SAM: 950K households / $136.8M annual revenue potential
- SOM Y1 Base: 3,000 / $432K ARR | Y2 Base: 9,500 / $1.37M ARR | Y3 Base: 23,750 / $3.42M ARR

**Scenario table key drivers:**
- Bear: monthly churn stays at 5% through Y3; referral loop not activated; CAC above $40
- Base: churn compresses to 0.67%/month by Y3; referral loop live Month 14; CAC proven below $25 by Month 10
- Bull: churn compresses to 0.5%/month by Y2; viral referral loop live Month 8; CAC below $15 driven by interactive demo conversion

### 2026-05-18 — Board-Ready Financial Model: Strategic Assumptions Delivered to Finance

**Context:** Finance is building a board-ready 1-pager on revenue, cost, and profit. The following assumptions are the strategic inputs Finance should use as the model foundation.

**Pricing — $12/month validated with ceiling at $15:**
$12/month is defensible and correct as a launch price against the current market. It clears the "impulse buy" threshold (under $15/month is where working parents approve subscriptions without a budget conversation) while staying above commodity AI pricing ($10 is the floor that reads as low-confidence). Do not go to $9.99 — it signals feature tool, not household assistant. A $15 tier is credible for Year 2 once retention data exists to justify it.

**Target market — 950,000 reachable households in 2 years:**
Primary ICP: dual-income US households with children under 18, ages 28–45, smartphone-native. Addressable SAM is 950K households derived from a filtered TAM of 12M (Census + BLS + age-band + digital-active). The 950K figure already applies three conservative conversion filters: 25% AI-subscription willingness-to-pay, 45% trust threshold for proactive AI in the home, 70% digital-acquisition reachable. Do not pad this for a board — the defensibility of the number is the point.

**Growth model — word of mouth is the engine, not paid:**
Paid acquisition (Meta, Instagram) is a signal-testing tool, not a growth lever, until CAC is proven below $25. The realistic 2-year path is: 3,000 subscribers Y1 from founder network + beta referrals + organic search, scaling to 23,750 by Y3 via word-of-mouth compounding once PMF is validated in the core parent segment. Referral mechanics (share-a-link, family invite) should be designed before Sprint 11, not after — they are the Y2 growth flywheel.

**Churn — 5% monthly Y1, declining to 8% annual by Y3:**
5% monthly churn in Year 1 (40% annual) is the honest assumption for a new-category AI product with no established trust. This is not a failure signal — it is the calibration period. If Hana's proactive triggers fire correctly and household context accumulates, churn compresses sharply: model 8% annual (0.67%/month) by Year 3. The single biggest churn driver will be bad proactive alerts in the first 60 days. Engineering must treat the confidence threshold as a retention metric, not a product feature.

**Competitive moat — context accumulation that ChatGPT cannot replicate:**
ChatGPT is free and excellent at one-off tasks. The reason someone pays $12/month for Hana is not because Hana answers questions better — it is because Hana knows their household across time (school schedules, recurring bills, family dynamics) and acts without being asked. That context layer is the moat, and it is self-reinforcing: the longer a family uses Hana, the more irreplaceable it becomes. ChatGPT resets with every conversation; Hana compounds. No free tool can replicate persistent, proactive, household-scoped memory without the user doing the work themselves.

### 2026-05-19 — Sprint 12 Circle Input

**Auto-calendar is a trust escalation.** Items before this sprint (Gmail drafts, swipe-to-accept to-dos) required user confirmation. Calendar event creation (Item 4) is the first time Hana acts on the user's real calendar without a confirmation step. The Gemini prompt must be the most restrictive event-detection instruction written. "Sale ends Sunday" = no event. "Julia's soccer game Saturday 10am" = yes. Rule: only create if there is a human commitment the user would want tracked.

**Item 1 (filter bug) is a churn-before-retention risk.** An external user seeing random senders in their feed will not report it — they will stop using the app. Fix first.

**Highlights (Items 3, 7, 8) have strategic value beyond polish.** "Here is the sentence that triggered this" is a transparency affordance that builds long-term trust. Worth doing precisely.

Sprint estimate: **medium**, manageable. No deferrals. Engineer's dependency order is correct.

---

### 2026-05-20 — Niche-First GTM Analysis (Campily Analogy)

**Question posed:** Does a Campily-style niche-first GTM strategy hold water for Saucer instead of broad "busy professionals" positioning?

**Verdict:** Niche-first is structurally correct for Saucer — but the CEO has already been executing it without naming it. The ICP (dual-income parents 28–45) is the niche. The strategic gap is that the product positioning language has not caught up to the implicit targeting already embedded in the TAM/SAM work. Naming and committing to the niche publicly is the next move.

**Campily analogy quality:** Good analog but imperfect. Campily's problem was acute, fragmented, and completely unserved — no incumbent. Saucer's problem (email/calendar overwhelm) is acute but partially served by Gmail, Calendar, and Notion. The niche advantage is not "no solution exists" — it is "no solution knows your household as a unit." That framing is stronger and more defensible than generic overwhelm.

**Moat question:** Niche creates moat via context density (household data accumulates faster with committed segment users), word-of-mouth efficiency (parents talk to parents), and brand recall specificity. A large player (Google) can copy the feature; it cannot replicate the trust signal of "built for families like mine."

**Backfire condition:** Niche-first fails if the niche is too small to sustain the business until SAM expansion. At 950K reachable households and $12/month, the math closes. The risk is not the niche — it is premature SAM expansion before retention is proven in the core segment.

**Recommendation logged:** Narrow the public positioning to dual-income parents explicitly. Stop saying "busy professionals" in any marketing or pitch material. This is not a pivot — it is making the implicit explicit.

---

### 2026-05-20 — CEO Direct Challenge: Why Wasn't Niche-First Raised Earlier?

**Honest verdict:** Partial own. The TAM/SAM work from May 17th already implicitly locked the ICP to dual-income parents. A disciplined strategist should have immediately connected that to a positioning mandate in the same session. The failure was not raising the positioning language gap the moment the segment math crystallized.

**Partial defense (limited):** The Campily analogy was a useful concrete forcing function. "Niche-first" as an abstract recommendation can read as a retreat from ambition; a comparable company gave the conversation traction. Waiting for the right frame is sometimes correct — but not when a sprint queue is running and copy is being written with the wrong ICP in it.

**Process rule locked:** When TAM/SAM numbers crystallize around a specific cohort, positioning language must lock in the same session. The two decisions are not sequential — they are simultaneous. Flag this dependency every future market sizing exercise.

---

### 2026-05-18 — Huddle: Hana Purpose Statement (140-char)

**Prompt:** CEO asked all agents to state Hana's purpose in 140 characters max.

**Response submitted:** "Hana eliminates the mental load of running a household by acting before you think to ask — the only AI that knows your family, not just you."

**Strategic note:** The word "eliminates" is deliberate — not "reduces" or "helps with." Elimination is the category-defining claim. "Knows your family" anchors the household-context moat in plain language. This phrasing should be tested as tagline copy.
