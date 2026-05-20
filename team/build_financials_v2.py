"""
Saucer Financial Model v2 — Board Slide
Produces /home/dcjohnston1/saucer/team/financials_v2.png

Layout:
  Left column  — Fixed/Variable cost breakdown + Breakeven + Unit Economics
  Right column — 3-year Bear/Base/Bull P&L table + $220K callout
  Bottom strip — footnotes

Run: python3 build_financials_v2.py
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

# ── Palette ──────────────────────────────────────────────────────────────────
BG      = "#0D1117"
CARD    = "#161B22"
CARD2   = "#1A2030"   # slightly lighter card for alternating rows
BORDER  = "#30363D"
WHITE   = "#F0F6FC"
MUTED   = "#8B949E"
ACCENT  = "#58A6FF"
GREEN   = "#3FB950"
GOLD    = "#E3B341"
RED     = "#FF7B72"
DIM_RED = "#3D1B1B"
DIM_GRN = "#1B3D1B"
DIM_GLD = "#3D3200"

BEAR_COL = "#FF7B72"   # red
BASE_COL = "#3FB950"   # green
BULL_COL = "#E3B341"   # gold

# ── Model Parameters ─────────────────────────────────────────────────────────
PRICE = 12.00  # $/user/month (direct web subscription, no store cut)
GOAL  = 220_000

# Fixed monthly costs
FIXED_ITEMS = [
    ("Cloud Run min-instances",   75.00),
    ("GCS bucket baseline",       20.00),
    ("Firebase Auth (est. avg)",  20.00),
    ("Sentry (error monitoring)", 26.00),
    ("Domain + DNS + misc",       30.00),
    ("CI/CD pad",                 10.00),
]
FIXED = sum(v for _, v in FIXED_ITEMS)   # $181/mo

# Variable costs per user/month
VAR_ITEMS = [
    ("Gemini API  500 calls × $0.001", 0.50),
    ("Cloud Run compute",              0.05),
    ("Firestore reads/writes",         0.01),
    ("GCS storage + bandwidth",        0.01),
    ("Cloud Tasks",                    0.01),
]
VAR = sum(v for _, v in VAR_ITEMS)   # $0.58/user/month

CONTRIB = PRICE - VAR   # $11.42/user/month

# Breakeven
BE_USERS = FIXED / CONTRIB           # ~15.8 users
BE_MRR   = PRICE * BE_USERS          # ~$190/mo

# $220K gate
GATE_USERS = (GOAL / 12 + FIXED) / CONTRIB   # ~1,621

# Unit economics
CHURN_Y1 = 0.40   # annual
CHURN_Y3 = 0.08   # annual
MCHURN_Y1 = 1 - (1 - CHURN_Y1) ** (1/12)
MCHURN_Y3 = 1 - (1 - CHURN_Y3) ** (1/12)
LIFE_Y1 = 1 / MCHURN_Y1     # ~24 months
LIFE_Y3 = 1 / MCHURN_Y3     # ~144 months
LTV_Y1  = PRICE * LIFE_Y1   # ~$288
LTV_Y3  = PRICE * LIFE_Y3   # ~$1,733
CAC_Y1  = LTV_Y1 / 3        # $96 ceiling
CAC_Y3  = LTV_Y3 / 3        # $578 ceiling

# Scenarios: Bear / Base / Bull  (Y1, Y2, Y3 users)
SCENARIOS = {
    "Bear": ([300, 800, 1_500],   BEAR_COL, DIM_RED),
    "Base": ([1_000, 2_180, 4_500], BASE_COL, DIM_GRN),
    "Bull": ([2_500, 5_000, 10_000], BULL_COL, DIM_GLD),
}

def pnl(users):
    mrr       = users * PRICE
    ann_rev   = mrr * 12
    mo_cost   = FIXED + users * VAR
    mo_profit = mrr - mo_cost
    ann_profit = mo_profit * 12
    return mrr, ann_rev, mo_cost, mo_profit, ann_profit


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Figure setup  —  16 × 11 board slide, 2-column layout
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig = plt.figure(figsize=(18, 11), facecolor=BG)
fig.subplots_adjust(left=0.03, right=0.97, top=0.90, bottom=0.06)

# ── Header ───────────────────────────────────────────────────────────────────
fig.text(0.50, 0.965, "Project Saucer  —  Board Financial Model",
         ha="center", va="top", color=WHITE,
         fontsize=22, fontweight="bold", fontfamily="monospace")
fig.text(0.50, 0.937,
         "Hana  |  AI Household Assistant  |  $12 / household / month  |  May 2026",
         ha="center", va="top", color=MUTED,
         fontsize=11, fontfamily="monospace")

fig.add_artist(plt.Line2D([0.03, 0.97], [0.924, 0.924],
               transform=fig.transFigure, color=BORDER, linewidth=1))

# ── 2-column, 3-row grid ─────────────────────────────────────────────────────
# Left col: [cost breakdown, breakeven, unit econ]
# Right col: [scenario P&L table spans all 3 rows]
gs = gridspec.GridSpec(3, 2, figure=fig,
                       left=0.03, right=0.97, top=0.916, bottom=0.065,
                       hspace=0.44, wspace=0.06,
                       width_ratios=[1, 1.05],
                       height_ratios=[1.15, 0.95, 0.90])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEFT TOP — Fixed vs. Variable Cost Breakdown
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ax_cost = fig.add_subplot(gs[0, 0])
ax_cost.set_facecolor(CARD)
for sp in ax_cost.spines.values():
    sp.set_edgecolor(BORDER)
ax_cost.set_xticks([])
ax_cost.set_yticks([])
ax_cost.set_title("Cost Structure", color=WHITE,
                  fontsize=11, fontweight="bold",
                  fontfamily="monospace", pad=7)

# Section label — FIXED
ax_cost.text(0.02, 0.965, "FIXED  (per month, regardless of users)",
             transform=ax_cost.transAxes,
             ha="left", va="top", color=ACCENT,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")

y = 0.906
for name, val in FIXED_ITEMS:
    ax_cost.text(0.04, y, name,
                 transform=ax_cost.transAxes,
                 ha="left", va="top", color=MUTED,
                 fontsize=8, fontfamily="monospace")
    ax_cost.text(0.96, y, f"${val:.0f}",
                 transform=ax_cost.transAxes,
                 ha="right", va="top", color=WHITE,
                 fontsize=8, fontfamily="monospace")
    y -= 0.085

# Fixed total line
ax_cost.plot([0.02, 0.98], [y + 0.045, y + 0.045],
             color=ACCENT, linewidth=0.7,
             transform=ax_cost.transAxes, clip_on=False)
ax_cost.text(0.04, y + 0.030, "Total Fixed",
             transform=ax_cost.transAxes,
             ha="left", va="top", color=ACCENT,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")
ax_cost.text(0.96, y + 0.030, f"${FIXED:.0f} / mo",
             transform=ax_cost.transAxes,
             ha="right", va="top", color=ACCENT,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")

# Spacer divider
y -= 0.075
ax_cost.plot([0.02, 0.98], [y + 0.06, y + 0.06],
             color=BORDER, linewidth=0.6,
             transform=ax_cost.transAxes, clip_on=False)

# Section label — VARIABLE
ax_cost.text(0.02, y + 0.048, "VARIABLE  (per user / per month)",
             transform=ax_cost.transAxes,
             ha="left", va="top", color=RED,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")
y -= 0.055
for name, val in VAR_ITEMS:
    ax_cost.text(0.04, y, name,
                 transform=ax_cost.transAxes,
                 ha="left", va="top", color=MUTED,
                 fontsize=8, fontfamily="monospace")
    ax_cost.text(0.96, y, f"${val:.3f}",
                 transform=ax_cost.transAxes,
                 ha="right", va="top", color=WHITE,
                 fontsize=8, fontfamily="monospace")
    y -= 0.082

ax_cost.plot([0.02, 0.98], [y + 0.045, y + 0.045],
             color=RED, linewidth=0.7,
             transform=ax_cost.transAxes, clip_on=False)
ax_cost.text(0.04, y + 0.030, "Total Variable",
             transform=ax_cost.transAxes,
             ha="left", va="top", color=RED,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")
ax_cost.text(0.96, y + 0.030, f"${VAR:.3f} / user / mo",
             transform=ax_cost.transAxes,
             ha="right", va="top", color=RED,
             fontsize=8.5, fontweight="bold", fontfamily="monospace")

# Formula
y -= 0.07
ax_cost.plot([0.02, 0.98], [y + 0.06, y + 0.06],
             color=BORDER, linewidth=0.6,
             transform=ax_cost.transAxes, clip_on=False)
ax_cost.text(0.50, y + 0.040,
             f"Total Cost = ${FIXED:.0f}  +  (${VAR:.3f} × Users)",
             transform=ax_cost.transAxes,
             ha="center", va="top", color=GOLD,
             fontsize=9, fontweight="bold", fontfamily="monospace",
             bbox=dict(boxstyle="round,pad=0.25",
                       facecolor=DIM_GLD, edgecolor=GOLD, linewidth=0.8))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEFT MIDDLE — Breakeven Analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ax_be = fig.add_subplot(gs[1, 0])
ax_be.set_facecolor(CARD)
for sp in ax_be.spines.values():
    sp.set_edgecolor(BORDER)
ax_be.set_xticks([])
ax_be.set_yticks([])
ax_be.set_title("Breakeven Analysis", color=WHITE,
                fontsize=11, fontweight="bold",
                fontfamily="monospace", pad=7)

be_rows = [
    ("Price",                     f"${PRICE:.2f}",          WHITE),
    ("Variable Cost",             f"${VAR:.3f}",            WHITE),
    ("Contribution Margin",       f"${CONTRIB:.3f}",        GREEN),
    ("Fixed Costs",               f"${FIXED:.0f}/mo",       WHITE),
    ("Breakeven Users",           f"{BE_USERS:.0f} users",  GOLD),
    ("Breakeven MRR",             f"${BE_MRR:.0f}/mo",      GOLD),
    ("Users for $220K profit",    f"{GATE_USERS:.0f} users",GREEN),
]

y = 0.930
for label, val, color in be_rows:
    ax_be.text(0.04, y, label,
               transform=ax_be.transAxes,
               ha="left", va="top", color=MUTED,
               fontsize=9, fontfamily="monospace")
    ax_be.text(0.96, y, val,
               transform=ax_be.transAxes,
               ha="right", va="top", color=color,
               fontsize=9, fontweight="bold", fontfamily="monospace")
    y -= 0.117
    if label in ("Contribution Margin", "Fixed Costs"):
        ax_be.plot([0.02, 0.98], [y + 0.076, y + 0.076],
                   color=BORDER, linewidth=0.5,
                   transform=ax_be.transAxes, clip_on=False)

# Breakeven callout box
ax_be.text(0.50, 0.045,
           f"BREAKEVEN AT {int(round(BE_USERS))} USERS  |  ${BE_MRR:.0f} MRR",
           transform=ax_be.transAxes,
           ha="center", va="bottom", color=GOLD,
           fontsize=9, fontweight="bold", fontfamily="monospace",
           bbox=dict(boxstyle="round,pad=0.30",
                     facecolor=DIM_GLD, edgecolor=GOLD, linewidth=1.2))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LEFT BOTTOM — Unit Economics
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ax_ue = fig.add_subplot(gs[2, 0])
ax_ue.set_facecolor(CARD)
for sp in ax_ue.spines.values():
    sp.set_edgecolor(BORDER)
ax_ue.set_xticks([])
ax_ue.set_yticks([])
ax_ue.set_title("Unit Economics", color=WHITE,
                fontsize=11, fontweight="bold",
                fontfamily="monospace", pad=7)

# Two-column sub-layout: Y1 (high churn) vs Y3 (mature)
for col_x, label, churn_pct, life, ltv, cac_ceil in [
    (0.02, "Y1  (40% annual churn)", 40, LIFE_Y1, LTV_Y1, CAC_Y1),
    (0.51, "Y3  (8% annual churn)",  8,  LIFE_Y3, LTV_Y3, CAC_Y3),
]:
    payback = (ltv / 4) / CONTRIB
    ax_ue.text(col_x, 0.96, label,
               transform=ax_ue.transAxes,
               ha="left", va="top", color=ACCENT,
               fontsize=8.5, fontweight="bold", fontfamily="monospace")
    ue_rows = [
        ("Avg Lifetime",  f"{life:.0f} mo"),
        ("LTV",           f"${ltv:,.0f}"),
        ("CAC Ceiling",   f"${cac_ceil:,.0f}"),
        ("LTV : CAC",     "3 : 1 rule"),
        ("Payback",       f"~{payback:.0f} mo"),
    ]
    y2 = 0.825
    for r_label, r_val in ue_rows:
        ax_ue.text(col_x + 0.01, y2, r_label,
                   transform=ax_ue.transAxes,
                   ha="left", va="top", color=MUTED,
                   fontsize=8.0, fontfamily="monospace")
        ax_ue.text(col_x + 0.47, y2, r_val,
                   transform=ax_ue.transAxes,
                   ha="right", va="top", color=WHITE,
                   fontsize=8.0, fontfamily="monospace")
        y2 -= 0.125

# vertical divider
ax_ue.plot([0.50, 0.50], [0.05, 0.97],
           color=BORDER, linewidth=0.8,
           transform=ax_ue.transAxes, clip_on=False)

ax_ue.text(0.50, 0.03,
           "LTV improves 6x as churn drops from 40% to 8% — retention is the multiplier",
           transform=ax_ue.transAxes,
           ha="center", va="bottom", color=MUTED,
           fontsize=7.5, fontfamily="monospace", style="italic")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RIGHT COLUMN — 3-Year Scenario P&L Table (spans all 3 rows)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ax_tbl = fig.add_subplot(gs[:, 1])
ax_tbl.set_facecolor(CARD)
for sp in ax_tbl.spines.values():
    sp.set_edgecolor(BORDER)
ax_tbl.set_xticks([])
ax_tbl.set_yticks([])
ax_tbl.set_title("3-Year Bear / Base / Bull  —  P&L Scenarios",
                 color=WHITE, fontsize=12, fontweight="bold",
                 fontfamily="monospace", pad=9)

# ── $220K callout banner ──────────────────────────────────────────────────────
ax_tbl.text(0.50, 0.975,
            f"$220K ANNUAL PROFIT TARGET  =  {int(round(GATE_USERS)):,} PAYING HOUSEHOLDS",
            transform=ax_tbl.transAxes,
            ha="center", va="top", color=GOLD,
            fontsize=9.5, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.35",
                      facecolor=DIM_GLD, edgecolor=GOLD, linewidth=1.5))

# ── Column layout ─────────────────────────────────────────────────────────────
# Columns: Metric | Bear Y1 Y2 Y3 | Base Y1 Y2 Y3 | Bull Y1 Y2 Y3
# We use manual x positions for max control

# x positions for each year block
#   col0 = metric label
#   Bear  = cols 1,2,3
#   Base  = cols 4,5,6
#   Bull  = cols 7,8,9
COL_METRIC = 0.02
COL_WIDTH_METRIC = 0.18
BLOCK_W = 0.265   # width per scenario block
YEAR_W  = BLOCK_W / 3.0
BLOCK_STARTS = {
    "Bear": 0.21,
    "Base": 0.475,
    "Bull": 0.74,
}

def year_x(scenario, yr_idx):
    """Center x for year column within a scenario block."""
    return BLOCK_STARTS[scenario] + (yr_idx + 0.5) * YEAR_W

# Scenario header row
y_hdr = 0.920
for sname, (users_list, color, dim) in SCENARIOS.items():
    bx = BLOCK_STARTS[sname]
    mid = bx + BLOCK_W / 2
    ax_tbl.text(mid, y_hdr, sname.upper(),
                transform=ax_tbl.transAxes,
                ha="center", va="top", color=color,
                fontsize=11, fontweight="bold", fontfamily="monospace")
    # colored underline
    ax_tbl.plot([bx + 0.005, bx + BLOCK_W - 0.005],
                [y_hdr - 0.027, y_hdr - 0.027],
                color=color, linewidth=1.5,
                transform=ax_tbl.transAxes, clip_on=False)

# Year sub-headers
y_yr = y_hdr - 0.050
for sname in SCENARIOS:
    for yi, yr_label in enumerate(["Y1", "Y2", "Y3"]):
        ax_tbl.text(year_x(sname, yi), y_yr, yr_label,
                    transform=ax_tbl.transAxes,
                    ha="center", va="top", color=MUTED,
                    fontsize=8.5, fontweight="bold", fontfamily="monospace")

ax_tbl.plot([0.01, 0.99], [y_yr - 0.030, y_yr - 0.030],
            color=BORDER, linewidth=0.8,
            transform=ax_tbl.transAxes, clip_on=False)

# Data rows
METRIC_ROWS = [
    ("Users",          lambda mrr, ann, c, p, ap, u: f"{u:,}"),
    ("MRR",            lambda mrr, ann, c, p, ap, u: f"${mrr:,.0f}"),
    ("Annual Rev",     lambda mrr, ann, c, p, ap, u: f"${ann/1000:.0f}K"),
    ("Total Mo. Cost", lambda mrr, ann, c, p, ap, u: f"${c:,.0f}"),
    ("Mo. Profit",     lambda mrr, ann, c, p, ap, u: f"${p:,.0f}"),
    ("Annual Profit",  lambda mrr, ann, c, p, ap, u: f"${ap/1000:.0f}K"),
]

# Build pre-computed table data
all_data = {}
for sname, (users_list, color, dim) in SCENARIOS.items():
    all_data[sname] = []
    for users in users_list:
        mrr, ann_rev, mo_cost, mo_profit, ann_profit = pnl(users)
        all_data[sname].append((mrr, ann_rev, mo_cost, mo_profit, ann_profit, users))

ROW_H = 0.076
y_start = y_yr - 0.055

for ri, (metric_label, fmt_fn) in enumerate(METRIC_ROWS):
    y = y_start - ri * ROW_H
    is_profit_row = metric_label in ("Mo. Profit", "Annual Profit")
    # Row shading
    if ri % 2 == 0:
        for sname, (_, sc, dim) in SCENARIOS.items():
            bx = BLOCK_STARTS[sname]
            rect = mpatches.FancyBboxPatch(
                (bx, y - ROW_H * 0.85), BLOCK_W - 0.004, ROW_H * 0.82,
                boxstyle="square,pad=0",
                facecolor=dim, edgecolor="none", alpha=0.35,
                transform=ax_tbl.transAxes, zorder=0
            )
            ax_tbl.add_patch(rect)

    # Metric label
    ax_tbl.text(COL_METRIC, y, metric_label,
                transform=ax_tbl.transAxes,
                ha="left", va="top", color=MUTED,
                fontsize=9, fontfamily="monospace")

    for sname, (users_list, sc, dim) in SCENARIOS.items():
        for yi, (mrr, ann_rev, mo_cost, mo_profit, ann_profit, users) in \
                enumerate(all_data[sname]):
            val = fmt_fn(mrr, ann_rev, mo_cost, mo_profit, ann_profit, users)
            if is_profit_row:
                txt_color = GREEN if ann_profit >= GOAL else RED
            else:
                txt_color = WHITE
            ax_tbl.text(year_x(sname, yi), y, val,
                        transform=ax_tbl.transAxes,
                        ha="center", va="top", color=txt_color,
                        fontsize=8.5, fontfamily="monospace",
                        fontweight="bold" if is_profit_row else "normal")

    # Row separator
    sep_y = y - ROW_H * 0.87
    ax_tbl.plot([0.01, 0.99], [sep_y, sep_y],
                color=BORDER, linewidth=0.4,
                transform=ax_tbl.transAxes, clip_on=False)

# ── Which years hit $220K callout ────────────────────────────────────────────
y_flags = y_start - len(METRIC_ROWS) * ROW_H - 0.025
ax_tbl.text(0.50, y_flags,
            "GREEN = annual profit >= $220K goal    RED = below target",
            transform=ax_tbl.transAxes,
            ha="center", va="top", color=MUTED,
            fontsize=8, fontfamily="monospace", style="italic")

# ── Scenario context notes ────────────────────────────────────────────────────
y_notes = y_flags - 0.055
notes = [
    ("BEAR",
     f"Y1={300:,}  Y2={800:,}  Y3={1500:,} users — slow adoption, "
     "misses $220K until Y3",
     BEAR_COL),
    ("BASE",
     f"Y1={1000:,}  Y2={2180:,}  Y3={4500:,} users — plan target, "
     "hits $220K in Y2",
     BASE_COL),
    ("BULL",
     f"Y1={2500:,}  Y2={5000:,}  Y3={10000:,} users — strong PMF, "
     "exceeds $220K Y1",
     BULL_COL),
]
for sname, note, color in notes:
    ax_tbl.text(0.03, y_notes, f"{sname}:",
                transform=ax_tbl.transAxes,
                ha="left", va="top", color=color,
                fontsize=8, fontweight="bold", fontfamily="monospace")
    ax_tbl.text(0.13, y_notes, note,
                transform=ax_tbl.transAxes,
                ha="left", va="top", color=MUTED,
                fontsize=8, fontfamily="monospace")
    y_notes -= 0.055

# ── Contribution margin highlight ────────────────────────────────────────────
y_cm = y_notes - 0.015
ax_tbl.text(0.50, y_cm,
            f"CONTRIBUTION MARGIN  =  ${CONTRIB:.2f} / user / month   "
            f"(95.2% gross margin)",
            transform=ax_tbl.transAxes,
            ha="center", va="top", color=GREEN,
            fontsize=9.5, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.30",
                      facecolor=DIM_GRN, edgecolor=GREEN, linewidth=1.2))

# ── Breakeven visual note ────────────────────────────────────────────────────
y_bn = y_cm - 0.085
ax_tbl.text(0.50, y_bn,
            f"INFRASTRUCTURE BREAKEVEN  =  {int(round(BE_USERS))} users  "
            f"(${BE_MRR:.0f} MRR)  —  fixed costs are low; scale is the prize",
            transform=ax_tbl.transAxes,
            ha="center", va="top", color=GOLD,
            fontsize=8.5, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.28",
                      facecolor=DIM_GLD, edgecolor=GOLD, linewidth=1.0))

# ── COGS footnote ─────────────────────────────────────────────────────────────
ax_tbl.text(0.50, 0.018,
            f"COGS: ${VAR:.3f}/user/mo variable  +  ${FIXED:.0f}/mo fixed  |  "
            "Gemini AI, Cloud Run, Firestore, GCS, Cloud Tasks",
            transform=ax_tbl.transAxes,
            ha="center", va="bottom", color=MUTED,
            fontsize=7.5, fontfamily="monospace", style="italic")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Footer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fig.add_artist(plt.Line2D([0.03, 0.97], [0.053, 0.053],
               transform=fig.transFigure, color=BORDER, linewidth=0.8))
fig.text(0.03, 0.034,
         "Infrastructure-only model. No headcount, no marketing spend, no app store cut. "
         "AI backend: Gemini API. Direct web subscription.",
         ha="left", va="top", color=MUTED,
         fontsize=7.5, fontfamily="monospace")
fig.text(0.97, 0.034,
         "Prepared: May 2026  |  v2  |  Finance Lead — Project Saucer",
         ha="right", va="top", color=MUTED,
         fontsize=7.5, fontfamily="monospace")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Save
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
out = "/home/dcjohnston1/saucer/team/financials_v2.png"
plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
plt.close(fig)
print(f"Saved: {out}")
