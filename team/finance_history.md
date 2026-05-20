# Finance History
*Running log of pricing decisions, cost estimates, profitability projections, and financial concerns.*

---

## Entry: 2026-05-17 — Full Cost and Profit Model (Y1 / Y3 / Y5)

### Context
Requested by CEO. Subscriber baseline from Strategy Advisor. Goal: $220K run-rate profitability within 2 years of launch (by May 2026 target).

---

### Pricing and App Store Net Revenue

Subscription price: $12.00/user/month
App store split: 60% iOS / 40% Android
App store cut: 30% in Y1 for both stores; 15% from Y2 onward (standard small-developer rate)
Blended effective cut: 30% in Y1; 15% in Y3 and Y5

Net revenue per subscriber/month (after store):
- Y1: $12.00 × 0.70 = $8.40
- Y3+: $12.00 × 0.85 = $10.20

---

### Variable Cost Assumptions (Per Subscriber / Per Month)

**Claude API — Sonnet 4.6**
Usage: 50K input tokens + 5K output tokens/user/month
Pricing: $3.00/M input, $15.00/M output (Sonnet 4.6 as of May 2026)
Cost: (50K × $3.00/1M) + (5K × $15.00/1M) = $0.150 + $0.075 = $0.225/user/month

**Firestore reads/writes**
~1,000 reads + 200 writes/user/month. Blended at Google Cloud list rates.
Cost: ~$0.01/user/month (loaded; actual is ~$0.001 but rounding up for batch/index overhead)

**GCS storage (email blobs)**
~50 MB stored per user/month at $0.020/GB. Add ops/egress.
Cost: ~$0.01/user/month

**Cloud Run compute**
~200 invocations/user/month, ~0.5 CPU-seconds each. 100 CPU-seconds at $0.000024/CPU-s.
Cost: ~$0.05/user/month (loaded for memory and burst)

**Cloud Tasks (proactive triggers)**
~30 tasks/user/month at $0.40/M.
Cost: ~$0.01/user/month (loaded; actual is sub-penny)

**Voice AI — Twilio + STT/TTS (Y3 and Y5 only)**
Engineer estimate: $0.20–$0.25/call; assume 5 calls/user/month average by Y3.
Cost: 5 × $0.225 (midpoint) = $1.125/user/month
NOTE: Voice is the single biggest variable cost lever. A 10% change in call volume moves Y3 variable cost by ~$35K/year.

**Total variable cost per subscriber/month:**
- Y1 (no voice): $0.225 + $0.01 + $0.01 + $0.05 + $0.01 = $0.305/user/month
- Y3 (voice live): $0.305 + $1.125 = $1.43/user/month
- Y5 (voice mature): $1.43/user/month

---

### Fixed Cost Assumptions (Per Month)

| Item | Y1 | Y3 | Y5 |
|---|---|---|---|
| Cloud Run min-instances (1–2 always-on) | $75 | $75 | $75 |
| GCS bucket baseline (ops/egress floor) | $20 | $20 | $20 |
| Firebase Auth (free up to 10K MAU; $0.0055/MAU above) | $0 | $76 | $259 |
| Sentry (Team plan) | $26 | $26 | $26 |
| Developer tooling / CI / domain / misc | $50 | $50 | $50 |
| **Total fixed / month** | **$171** | **$247** | **$430** |
| **Total fixed / year** | **$2,052** | **$2,964** | **$5,160** |

---

### Revenue and Profit Model

| Metric | Y1 | Y3 | Y5 |
|---|---|---|---|
| Subscribers | 3,000 | 23,750 | 57,000 |
| Gross revenue | $432,000 | $3,420,000 | $8,208,000 |
| App store cut | ($129,600) | ($513,000) | ($1,231,200) |
| **Net revenue (after store)** | **$302,400** | **$2,907,000** | **$6,976,800** |
| Variable cost/user/month | $0.305 | $1.43 | $1.43 |
| **Total variable cost (annual)** | **($10,980)** | **($407,550)** | **($977,640)** |
| **Total fixed cost (annual)** | **($2,052)** | **($2,964)** | **($5,160)** |
| **Net operating profit (infra-only)** | **$289,368** | **$2,496,486** | **$5,994,000** |
| **Infra margin** | **95.7%** | **85.8%** | **85.9%** |

---

### Critical Flag: Headcount Not Included

The margins above are infrastructure-only. They do not include any human labor costs. This is intentional — the model isolates what the infrastructure costs relative to revenue. To arrive at true operating profit, the CEO must layer in:

- Founder/CEO salary or opportunity cost (even a $0 draw today has a market value)
- Any contractor or part-time engineering spend
- Marketing spend (paid acquisition, content, App Store optimization)
- Customer support (email/chat — even 1 hour/week at market rate adds up at scale)
- Legal / accounting / compliance (especially if handling email data)

For context: if the team draws $220K/year in combined salaries (the 2-year profitability target), the Y1 infrastructure model still produces a positive result. The $220K run-rate goal is achievable on infrastructure economics alone at 3,000 subscribers — the real question is whether the team can get to 3,000 paying subscribers before cash runs out.

---

### The $220K Profitability Gate — How Many Subscribers?

Working backwards: to clear $220K/year after infrastructure costs (no headcount), we need net revenue minus variable and fixed costs = $220,000.

At Y1 rate ($8.40/user/month net, $0.305/user/month variable cost):
Contribution margin per user/month = $8.40 − $0.305 = $8.095
Annual contribution per user = $97.14
Fixed cost = $2,052/year
Break-even at $220K profit: ($220,000 + $2,052) / $97.14 = ~2,286 subscribers

At Y3+ rate ($10.20/user/month net, $1.43/user/month variable with voice):
Contribution margin per user/month = $10.20 − $1.43 = $8.77
Annual contribution per user = $105.24
Break-even at $220K profit: ($220,000 + $2,964) / $105.24 = ~2,114 subscribers

Bottom line: approximately 2,100–2,300 subscribers covers $220K in infrastructure-only profit. The 3,000 subscriber Y1 target from Strategy provides a ~30% buffer above the minimum threshold. This is achievable but not automatic — acquisition and retention execution determine whether we get there.

---

### Open Questions for CEO
1. What is the team's monthly cash burn during development? This determines runway before the 2,300-subscriber gate matters.
2. Is voice AI a Y3 feature or a Y2 feature? The $1.125/user/month voice cost materially compresses margins — delaying voice buys time for subscriber volume to absorb it.
3. Are we distributing exclusively through app stores, or is web/direct subscription an option? Direct billing eliminates the 15–30% store cut entirely and would lower the subscriber break-even to ~1,800.

---

## Entry: 2026-05-18 — Comprehensive Board Financial Model v2

### Context
Requested by CEO for a more detailed board presentation. Builds on the May 2026 1-pager. Adds fixed vs. variable cost itemization, formal breakeven analysis, 3-year Bear/Base/Bull P&L table, and unit economics (LTV/CAC/payback). All figures use the Gemini API backend and direct web subscription (no app store cut). Artifacts: `financials_v2.png` and `build_financials_v2.py`.

---

### 1. Fixed vs. Variable Cost Breakdown

**Fixed monthly costs (regardless of user count):**

| Item | $/month |
|---|---|
| Cloud Run min-instances (1-2 always-on) | $75.00 |
| GCS bucket baseline (ops/egress floor) | $20.00 |
| Firebase Auth (free <10K MAU; avg estimate) | $20.00 |
| Sentry (error monitoring, Team plan) | $26.00 |
| Domain + DNS + misc tooling | $30.00 |
| CI/CD pad (Cloud Build free tier + buffer) | $10.00 |
| **Total Fixed** | **$181/month** |

**Variable costs per user per month:**

| Item | $/user/month |
|---|---|
| Gemini API (~500 decisions × $0.001) | $0.500 |
| Cloud Run compute (~200 invoc/user/mo) | $0.050 |
| Firestore reads/writes (~1K reads, 200 writes) | $0.010 |
| GCS storage + bandwidth (~50MB/user/mo) | $0.010 |
| Cloud Tasks (~30 tasks/user/mo) | $0.010 |
| **Total Variable** | **$0.580/user/month** |

**Formula:** Total Monthly Cost = $181 + ($0.580 × Users)

Note: Fixed costs increased from $75 (prior model) to $181 because the prior model only included Cloud Run and GCS. Firebase Auth, Sentry, domain, and CI/CD are real recurring costs that belong in the model.

---

### 2. Breakeven Analysis

Price: $12.00/user/month (direct web, no store cut)
Variable cost: $0.580/user/month
Contribution margin: **$11.420/user/month**

Infrastructure breakeven = $181 / $11.42 = **16 users** at **$190 MRR**

This is an extremely low breakeven — fixed costs are modest and the contribution margin is high. The product is not economically fragile at small scale. The real gate is the $220K profit goal, not survival.

Users required for $220K annual profit = ($220,000/12 + $181) / $11.42 = **1,621 users**

At $12/month, that is an MRR of $19,452 and an annual run rate of $233K on revenue, after subtracting $181/month fixed and $0.58/user/month variable.

---

### 3. Scenario P&L Table — Bear / Base / Bull (3 Years)

**Assumptions:** $12/month price, $0.580/user/month variable COGS, $181/month fixed.

| Scenario | Year | Users | MRR | Ann. Revenue | Mo. Cost | Mo. Profit | Ann. Profit |
|---|---|---|---|---|---|---|---|
| Bear | Y1 | 300 | $3,600 | $43,200 | $355 | $3,245 | $38,940 |
| Bear | Y2 | 800 | $9,600 | $115,200 | $645 | $8,955 | $107,460 |
| Bear | Y3 | 1,500 | $18,000 | $216,000 | $1,051 | $16,949 | $203,388 |
| Base | Y1 | 1,000 | $12,000 | $144,000 | $761 | $11,239 | $134,868 |
| Base | Y2 | 2,180 | $26,160 | $313,920 | $1,445 | $24,715 | $296,575 |
| Base | Y3 | 4,500 | $54,000 | $648,000 | $2,791 | $51,209 | $614,508 |
| Bull | Y1 | 2,500 | $30,000 | $360,000 | $1,631 | $28,369 | $340,428 |
| Bull | Y2 | 5,000 | $60,000 | $720,000 | $3,081 | $56,919 | $683,028 |
| Bull | Y3 | 10,000 | $120,000 | $1,440,000 | $5,981 | $114,019 | $1,368,228 |

**$220K gate status:**
- Bear: misses in Y1 and Y2, barely misses Y3 ($203K — ~8% short). Bear scenario does not deliver the goal within 3 years.
- Base: misses Y1 ($135K), hits Y2 ($297K, +35% above goal), comfortably exceeds Y3. The goal is achievable in Year 2 on the Base trajectory.
- Bull: exceeds $220K in Y1. Not relevant to the survival question, but validates the price point has headroom.

---

### 4. Unit Economics

Churn assumptions: 40% annual in Y1 (early adopter cohort, high experimentation turnover), 8% annual by Y3 (mature, habitual users). These are intentionally wide to reflect realistic SaaS adoption dynamics for a new consumer product.

| Metric | Y1 (40% churn) | Y3 (8% churn) |
|---|---|---|
| Monthly churn rate | 4.17% | 0.69% |
| Average customer lifetime | 24 months | 144 months |
| LTV (ARPU × avg lifetime) | $288 | $1,733 |
| CAC ceiling (LTV ÷ 3) | $96 | $578 |
| Target CAC (LTV ÷ 4) | $72 | $433 |
| Payback period at target CAC | ~6 months | ~38 months |

Key observation: LTV improves 6× as churn drops from 40% to 8%. Retention is the multiplier. Investing in product quality and habit formation in Year 1 — even at the cost of slower acquisition — directly multiplies the LTV that supports sustainable CAC. A $96 CAC ceiling in Y1 means paid acquisition is constrained to lightweight channels (content, referral, organic social). That is not a problem if churn is declining as expected by Y3.

**Payback caveat:** The Y3 payback of ~38 months at target CAC ($433) assumes we are spending toward the ceiling, which we should not. In practice, if Hana can acquire users organically or via word-of-mouth for $20-50 CAC, payback drops to under 6 months at either churn rate. The team should treat organic CAC as the plan and paid CAC as a scale lever, not a baseline.

---

### Artifact
Board-ready 1-pager image: `/home/dcjohnston1/saucer/team/financials_v2.png`
Generator script: `/home/dcjohnston1/saucer/team/build_financials_v2.py`

---

## 2026-05-19 — Sprint 12 Circle Input

**Calendar API cost:** Google Calendar API is free up to 1M req/day. No cost concern at any realistic scale.

**Trust risk on Item 4 (auto calendar):** Calendar event creation is irreversible from the user's perspective. If Hana creates garbage events from promotional emails, trust erodes. Confidence gate for event detection must be high — only create an event if there is a clear date, a clear activity, and a human action required.

**Duplicate guard needed:** Calendar writes are inline (not Cloud Tasks), so they bypass the per-user daily cap. Recommend checking for an existing event with the same title and date before calling `create_event()` to prevent duplicates on email reprocessing.

Sprint estimate: **medium**. No blocking concerns.

---

## Entry: 2026-05-18 — Board-Ready Financial 1-Pager (Gemini API Model)

### Context
Produced jointly with Strategy for board presentation. This model uses the Gemini API (not Claude/Sonnet) as the AI backend for Hana's agent decisions, consistent with the current production architecture. Modeled at $12/month direct web subscription (no app store cut assumed — consistent with web-first launch before mobile Sprint 13).

---

### Cost Structure (This Model)

**AI cost (Gemini API):**
~500 agent decisions per user per month at $0.001/decision = $0.50/user/month

**Infrastructure variable (Cloud Run + Firestore + GCS):**
- Cloud Run: $0.05/user/month
- Firestore: $0.01/user/month
- GCS: $0.01/user/month
- Total variable infra: $0.07/user/month

**Total variable COGS per user per month: $0.57**

**Fixed monthly floor: $75** (Cloud Run min-instances + GCS baseline)

Note: This model is simpler than the 2026-05-17 entry because it omits voice AI (pre-Sprint 8) and app store cuts (web-first assumption). It represents current state economics.

---

### Three-Scenario Snapshot (Month 24)

| Scenario | Users | Mo. Revenue | Mo. COGS | Mo. Profit | Ann. Profit | Margin |
|---|---|---|---|---|---|---|
| Conservative | 500 | $6,000 | $360 | $5,640 | $67.7K | 94% |
| Base | 2,180 | $26,160 | $1,318 | $24,842 | $298K | 95% |
| Optimistic | 5,000 | $60,000 | $2,925 | $57,075 | $685K | 95.1% |

The gross margin is high (94-95%) because variable AI + infra costs ($0.57/user/month) are very low relative to a $12 price point. The $220K annual profit goal requires ~2,180 subscribers — exactly the Base scenario.

---

### Path to $220K

Assuming linear ramp from 0 to target over 24 months:
- Conservative (500 users): crosses $220K annual run-rate — never. Tops out at $67.7K/year. This scenario is a lifestyle business, not the goal.
- Base (2,180 users): crosses $220K annual run-rate at approximately Month 18 on a linear ramp.
- Optimistic (5,000 users): crosses $220K well before Month 12.

The $220K goal requires the Base scenario to deliver. That means converting and retaining ~2,180 paying households within 24 months of launch.

---

### Key Assumptions and Risks

1. **No app store cut modeled.** If Sprint 13 (App Store submission) precedes web subscription, the effective net price drops to $8.40/month (30% cut Y1), which raises the break-even subscriber count to ~2,900. The CEO should decide: web-first or app-first.
2. **Gemini API pricing stability.** $0.001/decision is an estimate. A 3x increase in Gemini pricing would move COGS to $1.57/user/month — still 87% gross margin at this price. Minimal risk.
3. **500 decisions/user/month.** This is the usage assumption. Heavy users who check in daily and trigger many background tasks could run 2-5x this volume. Monitoring actual decision counts in the audit log (Sprint 1) will validate this within 30 days of first real users.
4. **No headcount.** Solo founder model. Any salary draw, contractor spend, or marketing budget comes out of the gross profit line.

---

### Artifact
Board-ready 1-pager image: `/home/dcjohnston1/saucer/team/financials.png`
Generator script: `/home/dcjohnston1/saucer/team/build_financials.py`

---

## Entry: 2026-05-20 — Niche GTM Financial Read (Real Estate vs. Dual-Income Parents)

### Context
CEO requested a financial read on two niche-first GTM candidates: independent real estate agents (~2M US) and dual-income parents/households (~3.5M–5M reachable US). Compared against current broad approach and evaluated against the $220K profitability gate.

---

### Assumptions Carried Forward
- Price: $12/month direct web subscription (no app store cut)
- Variable COGS: $0.58/user/month (Gemini API + infra)
- Contribution margin: $11.42/user/month
- Fixed costs: $181/month ($2,172/year)
- $220K profitability gate requires ~1,621 active subscribers

---

### Niche 1: Independent Real Estate Agents (~2M US)

**Segment and conversion:**
- TAM: 2,000,000 agents
- Realistic SAM (reachable via NAR communities, coaching channels, creator economy): 10% = 200,000
- SaaS conversion rate for a new productivity tool: 1–3% of reachable SAM
  - Conservative: 1% = 2,000 users
  - Base: 2% = 4,000 users
  - Bull: 3% = 6,000 users

**Price point consideration:**
Agents have high willingness-to-pay — tools like Lofty, Follow Up Boss, and Chime run $50–$200/month. $12/month is likely below their pain threshold, which means there is headroom to price at $20–$25/month for this segment without friction. However, this model holds the existing $12/month price to compare apples-to-apples. A real estate-specific price increase is a separate decision.

**ARR model at $12/month:**

| Scenario | Users | MRR | ARR | Annual Profit |
|---|---|---|---|---|
| Conservative (Y1) | 2,000 | $24,000 | $288,000 | $270,264 |
| Base (Y2) | 4,000 | $48,000 | $576,000 | $546,528 |
| Bull (Y3) | 6,000 | $72,000 | $864,000 | $822,792 |

At 2,000 users — a 1% conversion on a reachable SAM of 200,000 — annual profit already clears $220K by a wide margin. The $220K gate is reachable in Year 1 at conservative conversion rates if the SAM estimate and channel access hold.

**CAC advantage:** Real estate agents are concentrated in professional communities (NAR, coaching programs, brokerage Slack groups). CAC should be materially lower than a broad consumer play. Rough estimate: $30–$60/agent via organic community seeding vs. $50–$100+ for broad consumer acquisition. At $11.42/month contribution margin, a $60 CAC pays back in under 6 months.

---

### Niche 2: Dual-Income Parents / Household Segment (~3.5M–5M reachable US)

**Segment and conversion:**
- Reachable SAM: 3,500,000–5,000,000 households (per prior Strategy work)
- Consumer app conversion rate (free trial or organic): 0.5–1.5% of reachable SAM
  - Conservative: 0.5% of 3.5M = 17,500 users
  - Base: 1% of 4M = 40,000 users
  - Bull: 1.5% of 5M = 75,000 users

**Price point consideration:**
$12/month is reasonable for this segment but at the upper edge of what a household will add without friction. Consumer SaaS products targeting parents tend to face more price elasticity than professional tools. $8–$10/month may convert faster; $12/month requires a strong perceived value prop. Holding $12/month for this model.

**ARR model at $12/month:**

| Scenario | Users | MRR | ARR | Annual Profit |
|---|---|---|---|---|
| Conservative (Y1) | 17,500 | $210,000 | $2,520,000 | $2,388,234 |
| Base (Y2) | 40,000 | $480,000 | $5,760,000 | $5,478,816 |
| Bull (Y3) | 75,000 | $900,000 | $10,800,000 | $10,280,280 |

The TAM is not the constraint. Even the conservative conversion on the parent segment produces numbers that dwarf the $220K gate. The constraint is CAC: this segment is diffuse. You reach them via parenting communities, mommy bloggers, TikTok, Instagram, and word-of-mouth — all slower and harder to measure than a professional B2B community. Expect CAC of $75–$150+ and longer payback in the early months.

---

### Does Either Niche Beat the Broad Approach?

Short answer: yes, both do — but for different reasons.

The broad approach (current state) targets a wide consumer audience with no dominant positioning. The conversion funnel for an undifferentiated audience in a crowded inbox-management space will produce lower conversion rates and higher CAC than a niche with a named, acute problem. The broad approach can still work but it is a slower, more expensive path to the 1,621-user gate.

Real estate wins on speed-to-gate: a small, concentrated, high-intent segment that can be reached cheaply through professional networks. 2,000 agents is a realistic Y1 number and it clears $220K. This is the Campily analogy.

The parent segment wins on ceiling: the TAM is an order of magnitude larger. But the cost of customer acquisition in a diffuse consumer segment is higher, and the conversion timeline is longer. The $220K gate is still reachable, but the path looks more like Base/Y2 than Conservative/Y1.

---

### Cost-Per-Active-User: Niche vs. Broad

| Dimension | Real Estate Niche | Parent Niche | Broad |
|---|---|---|---|
| Estimated CAC | $30–$60 | $75–$150 | $80–$150+ |
| Payback at $11.42 contribution margin | 3–6 months | 7–14 months | 7–14 months |
| Variable COGS/user/month | $0.58 (no change) | $0.58 (no change) | $0.58 (no change) |
| Channel | Professional communities | Consumer social / WOM | Multi-channel |
| Conversion rate assumption | 1–3% of SAM | 0.5–1.5% of SAM | 0.25–0.75% of SAM |

Infrastructure costs per user are identical across all three approaches — the product runs the same. The differentiation is entirely in CAC and conversion rate, which are GTM levers, not engineering ones.

---

### Verdict

Real estate is the faster path to $220K. The segment is small enough to dominate quickly, concentrated enough to acquire cheaply, and has willingness-to-pay that likely supports a price increase to $20–$25/month (which would cut the break-even user count by half). If the team wants to hit the profitability gate within 2 years, real estate is the smarter first bet.

The parent segment is the right long-term market — it is larger, more defensible against Google/Apple (per Strategy's point about household identity), and aligns with what has already been built. But it is not the fastest route to $220K because consumer acquisition is slower and noisier.

My recommendation: launch with real estate positioning to hit the profitability gate, then expand to the parent segment once unit economics are proven and CAC is optimized. This is not a pivot — the product is identical. It is a sequencing decision.

One open question for the CEO: is there a price-point decision to be made for real estate? At $20/month (still well below agent tool norms), the break-even drops to ~900 users and the Y1 conservative scenario produces ~$375K in annual profit. That is a meaningful accelerant and worth a separate discussion.

