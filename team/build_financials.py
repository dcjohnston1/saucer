"""
Saucer Financial 1-Pager
Produces /home/dcjohnston1/saucer/team/financials.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ── Palette ──────────────────────────────────────────────────────────────────
BG        = "#0D1117"
CARD      = "#161B22"
BORDER    = "#30363D"
WHITE     = "#F0F6FC"
MUTED     = "#8B949E"
ACCENT    = "#58A6FF"   # blue  — revenue
WARN      = "#FF7B72"   # red   — cost
GREEN     = "#3FB950"   # green — profit
GOLD      = "#E3B341"   # gold  — milestone
CONS_COL  = "#58A6FF"
BASE_COL  = "#3FB950"
OPT_COL   = "#E3B341"

# ── Model parameters ─────────────────────────────────────────────────────────
PRICE            = 12.00          # gross $/user/month
STORE_CUT        = 0.0            # direct web sub — no store cut (open question resolved optimistically)
NET_PRICE        = PRICE * (1 - STORE_CUT)   # = $12.00
AI_COST_PER_USER = 0.50           # Gemini, ~500 decisions × $0.001
INFRA_VAR        = 0.05 + 0.01 + 0.01  # Cloud Run + Firestore + GCS per user
VAR_COST         = AI_COST_PER_USER + INFRA_VAR   # $0.57 / user / month
FIXED_MONTHLY    = 75.0           # Cloud Run min-instances + GCS floor (mid-point of $50-100 range)
GOAL_ANNUAL      = 220_000

# ── Scenario: (label, month-24 users) ────────────────────────────────────────
SCENARIOS = [
    ("Conservative", 500,  CONS_COL),
    ("Base",         2_180, BASE_COL),
    ("Optimistic",   5_000, OPT_COL),
]

def monthly_economics(users):
    rev  = users * NET_PRICE
    cogs = users * VAR_COST + FIXED_MONTHLY
    gp   = rev - cogs
    return rev, cogs, gp

def annual_economics(users):
    rev, cogs, gp = monthly_economics(users)
    return rev * 12, cogs * 12, gp * 12

# ── Month-by-month ramp (assume linear growth from 0 to month-24 target) ─────
MONTHS = 24

def ramp(target):
    return np.linspace(0, target, MONTHS + 1)[1:]   # months 1..24

# ── Build figure ─────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(16, 10), facecolor=BG)
fig.subplots_adjust(left=0.04, right=0.96, top=0.88, bottom=0.07)

gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.55, wspace=0.35,
                       height_ratios=[1, 1.3])

# ── Header ────────────────────────────────────────────────────────────────────
fig.text(0.50, 0.955, "Project Saucer — Financial Model",
         ha="center", va="top", color=WHITE,
         fontsize=22, fontweight="bold", fontfamily="monospace")
fig.text(0.50, 0.928, "Hana — AI Household Assistant   |   $12 / household / month   |   May 2026",
         ha="center", va="top", color=MUTED, fontsize=11, fontfamily="monospace")

# ── Divider line ──────────────────────────────────────────────────────────────
line = plt.Line2D([0.04, 0.96], [0.916, 0.916], transform=fig.transFigure,
                  color=BORDER, linewidth=1)
fig.add_artist(line)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TOP ROW — three KPI cards (one per scenario)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

card_axes = []
for col, (label, users, color) in enumerate(SCENARIOS):
    ax = fig.add_subplot(gs[0, col])
    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_edgecolor(BORDER)
        spine.set_linewidth(1.2)
    ax.set_xticks([])
    ax.set_yticks([])
    card_axes.append(ax)

    rev_a, cogs_a, gp_a = annual_economics(users)
    mo_rev, mo_cogs, mo_gp = monthly_economics(users)
    margin = (gp_a / rev_a * 100) if rev_a else 0

    # scenario label
    ax.text(0.5, 0.96, label.upper(), transform=ax.transAxes,
            ha="center", va="top", color=color,
            fontsize=11, fontweight="bold", fontfamily="monospace")
    # users
    ax.text(0.5, 0.83, f"{users:,} subscribers",
            transform=ax.transAxes, ha="center", va="top",
            color=WHITE, fontsize=10, fontfamily="monospace")

    # annual profit headline
    gp_str = f"${gp_a/1000:.0f}K" if abs(gp_a) < 1_000_000 else f"${gp_a/1_000_000:.2f}M"
    gp_color = GREEN if gp_a >= GOAL_ANNUAL else WARN
    ax.text(0.5, 0.70, "Annual Gross Profit", transform=ax.transAxes,
            ha="center", va="top", color=MUTED, fontsize=8, fontfamily="monospace")
    ax.text(0.5, 0.57, gp_str, transform=ax.transAxes,
            ha="center", va="top", color=gp_color,
            fontsize=24, fontweight="bold", fontfamily="monospace")

    # thin divider
    ax.plot([0.06, 0.94], [0.38, 0.38], color=BORDER, linewidth=0.6,
            transform=ax.transAxes, clip_on=False)

    # mini table: rev / cost / margin
    rows = [
        ("Revenue",  f"${rev_a/1000:.0f}K / yr"),
        ("COGS",     f"-${cogs_a/1000:.1f}K / yr"),
        ("Margin",   f"{margin:.0f}%"),
    ]
    y_start = 0.35
    for rname, rval in rows:
        ax.text(0.08, y_start, rname, transform=ax.transAxes,
                ha="left", va="top", color=MUTED, fontsize=8, fontfamily="monospace")
        ax.text(0.92, y_start, rval, transform=ax.transAxes,
                ha="right", va="top", color=WHITE, fontsize=8, fontfamily="monospace")
        y_start -= 0.09

    # $220K badge — only if profitable enough
    if gp_a >= GOAL_ANNUAL:
        ax.text(0.5, 0.035, "HITS $220K GOAL", transform=ax.transAxes,
                ha="center", va="bottom", color=GOLD,
                fontsize=7.5, fontweight="bold", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="#2D2200",
                          edgecolor=GOLD, linewidth=1))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOTTOM LEFT — Revenue / Cost / Profit ramp chart (Base scenario)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ax_chart = fig.add_subplot(gs[1, :2])
ax_chart.set_facecolor(CARD)
for spine in ax_chart.spines.values():
    spine.set_edgecolor(BORDER)

months_arr = np.arange(1, MONTHS + 1)

# Draw all three scenario profit lines
for label, users, color in SCENARIOS:
    u = ramp(users)
    rev_m  = u * NET_PRICE
    cogs_m = u * VAR_COST + FIXED_MONTHLY
    gp_m   = (rev_m - cogs_m) * 12   # annualised run-rate
    lw = 2.5 if label == "Base" else 1.5
    ls = "-" if label == "Base" else "--"
    ax_chart.plot(months_arr, gp_m / 1000, color=color, linewidth=lw,
                  linestyle=ls, label=f"{label} profit (ann.)", zorder=4)

# Base scenario: also plot revenue and cost bands
u_base = ramp(2_180)
rev_base  = u_base * NET_PRICE * 12
cogs_base = (u_base * VAR_COST + FIXED_MONTHLY) * 12
ax_chart.fill_between(months_arr, cogs_base/1000, rev_base/1000,
                      alpha=0.08, color=GREEN, zorder=1)
ax_chart.plot(months_arr, rev_base/1000, color=ACCENT, linewidth=1.2,
              linestyle=":", alpha=0.6, label="Base revenue (ann.)", zorder=3)

# $220K milestone line
ax_chart.axhline(220, color=GOLD, linewidth=1.4, linestyle="--", zorder=5)
ax_chart.text(MONTHS - 0.2, 222, "$220K goal", ha="right", va="bottom",
              color=GOLD, fontsize=9, fontfamily="monospace", fontweight="bold")

# Mark where Base crosses $220K
gp_base_ann = (u_base * NET_PRICE - u_base * VAR_COST - FIXED_MONTHLY) * 12
cross = np.where(gp_base_ann >= GOAL_ANNUAL)[0]
if len(cross):
    mx = months_arr[cross[0]]
    my = gp_base_ann[cross[0]] / 1000
    ax_chart.scatter([mx], [my], color=GOLD, s=80, zorder=6)
    ax_chart.text(mx + 0.4, my - 15, f"Month {mx}", color=GOLD,
                  fontsize=8.5, fontfamily="monospace", va="top")

# Formatting
ax_chart.set_xlim(1, MONTHS)
ax_chart.set_ylim(-30, max(rev_base/1000) * 1.05)
ax_chart.set_xlabel("Month", color=MUTED, fontsize=9, fontfamily="monospace")
ax_chart.set_ylabel("$ (thousands, annualised)", color=MUTED,
                    fontsize=9, fontfamily="monospace")
ax_chart.set_title("Annual Run-Rate Profit — All Scenarios",
                   color=WHITE, fontsize=11, fontfamily="monospace",
                   fontweight="bold", pad=8)
ax_chart.tick_params(colors=MUTED, labelsize=8)
for spine in ax_chart.spines.values():
    spine.set_edgecolor(BORDER)
ax_chart.set_facecolor(CARD)
ax_chart.grid(axis="y", color=BORDER, linewidth=0.6, linestyle="--", alpha=0.5)
ax_chart.axhline(0, color=BORDER, linewidth=0.8)
ax_chart.xaxis.label.set_color(MUTED)
ax_chart.yaxis.label.set_color(MUTED)
ax_chart.tick_params(axis="x", colors=MUTED)
ax_chart.tick_params(axis="y", colors=MUTED)

legend = ax_chart.legend(loc="upper left", fontsize=8,
                          facecolor=BG, edgecolor=BORDER,
                          labelcolor=WHITE, framealpha=0.9)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOTTOM RIGHT — Summary table
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ax_tbl = fig.add_subplot(gs[1, 2])
ax_tbl.set_facecolor(CARD)
for spine in ax_tbl.spines.values():
    spine.set_edgecolor(BORDER)
ax_tbl.set_xticks([])
ax_tbl.set_yticks([])
ax_tbl.set_title("Month-24 Snapshot", color=WHITE,
                  fontsize=11, fontfamily="monospace", fontweight="bold", pad=8)

# Table data
col_labels = ["", "Cons.", "Base", "Opt."]
rows_data = [
    ["Users",        "500",     "2,180",   "5,000"],
    ["Mo. Revenue",  "$6,000",  "$26,160", "$60,000"],
    ["Mo. COGS",     "$360",    "$1,293",  "$2,900"],
    ["Mo. Profit",   "$5,640",  "$24,867", "$57,100"],
    ["Ann. Profit",  "$67.7K",  "$298K",   "$685K"],
    ["Margin",       "94%",     "95%",     "95%"],
]

# compute actual values for color coding
computed = []
for label, users, _ in SCENARIOS:
    rev_m, cogs_m, gp_m = monthly_economics(users)
    computed.append((users, rev_m, cogs_m, gp_m, gp_m*12))

# Override row data with computed values
rows_data = [
    ["Users"] + [f"{s[0]:,}" for s in computed],
    ["Mo. Revenue"] + [f"${s[1]:,.0f}" for s in computed],
    ["Mo. COGS"] + [f"-${s[2]:,.0f}" for s in computed],
    ["Mo. Profit"] + [f"${s[3]:,.0f}" for s in computed],
    ["Ann. Profit"] + [f"${s[4]/1000:.1f}K" for s in computed],
    ["Margin"] + [f"{s[3]/s[1]*100:.0f}%" if s[1] else "—" for s in computed],
]

n_rows = len(rows_data)
n_cols = 4
cell_h = 0.80 / n_rows
x_starts = [0.02, 0.35, 0.56, 0.77]
col_widths = [0.32, 0.20, 0.20, 0.20]

# Header row
header_colors = [MUTED, CONS_COL, BASE_COL, OPT_COL]
for ci, (hdr, hcol) in enumerate(zip(col_labels, header_colors)):
    ax_tbl.text(x_starts[ci] + col_widths[ci]/2 if ci > 0 else x_starts[ci],
                0.96, hdr,
                transform=ax_tbl.transAxes,
                ha="center" if ci > 0 else "left",
                va="top", color=hcol,
                fontsize=9, fontweight="bold", fontfamily="monospace")

# Divider
ax_tbl.plot([0.02, 0.98], [0.91, 0.91], color=BORDER, linewidth=0.8,
            transform=ax_tbl.transAxes, clip_on=False)

for ri, row in enumerate(rows_data):
    y = 0.88 - ri * cell_h
    for ci, cell in enumerate(row):
        is_profit_row = row[0] in ("Mo. Profit", "Ann. Profit")
        if ci == 0:
            color = MUTED
        elif is_profit_row:
            scenario_idx = ci - 1
            val = computed[scenario_idx][3]
            annual_val = computed[scenario_idx][4]
            color = GREEN if annual_val >= GOAL_ANNUAL else WHITE
        else:
            color = WHITE

        ax_tbl.text(x_starts[ci] + (col_widths[ci]/2 if ci > 0 else 0),
                    y, cell,
                    transform=ax_tbl.transAxes,
                    ha="center" if ci > 0 else "left",
                    va="top", color=color,
                    fontsize=8.5, fontfamily="monospace")

    # row separator
    if ri < n_rows - 1:
        sep_y = y - cell_h * 0.1
        ax_tbl.plot([0.02, 0.98], [sep_y, sep_y], color=BORDER, linewidth=0.4,
                    transform=ax_tbl.transAxes, clip_on=False)

# Cost assumptions footnote
ax_tbl.text(0.5, 0.02,
            "COGS: $0.50/user AI + $0.07/user infra + $75 fixed/mo",
            transform=ax_tbl.transAxes,
            ha="center", va="bottom", color=MUTED,
            fontsize=7, fontfamily="monospace", style="italic")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Footer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
line2 = plt.Line2D([0.04, 0.96], [0.045, 0.045], transform=fig.transFigure,
                   color=BORDER, linewidth=0.8)
fig.add_artist(line2)

fig.text(0.04, 0.025,
         "Infrastructure-only model. No headcount. Price: $12/mo direct web sub (no store cut). "
         "AI: Gemini, ~500 decisions/user/mo at $0.001 each.",
         ha="left", va="bottom", color=MUTED,
         fontsize=7.5, fontfamily="monospace")

fig.text(0.96, 0.025, "Prepared: May 2026  |  Finance — Project Saucer",
         ha="right", va="bottom", color=MUTED,
         fontsize=7.5, fontfamily="monospace")

# ── Save ─────────────────────────────────────────────────────────────────────
out = "/home/dcjohnston1/saucer/team/financials.png"
plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
print(f"Saved: {out}")
