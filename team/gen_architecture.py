"""
Saucer backend architecture diagram — v3.
Clean two-column layout. Left: 4 horizontal layers (top=main.py, bottom=domain).
Right: GCP services stacked vertically + legend below.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Canvas ────────────────────────────────────────────────────────────────────
FIG_W, FIG_H = 24, 17
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
BG = "#F2F5FA"
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# ── Palette ───────────────────────────────────────────────────────────────────
C_MAIN        = "#1A3A5C"
C_ROUTE_DONE  = "#1C6E4A"
C_ROUTE_PLAN  = "#8B4513"
C_LIB         = "#2E5FA3"
C_DOMAIN      = "#5B4B8A"
C_GCP_HEADER  = "#C75B00"

# ── Helpers ───────────────────────────────────────────────────────────────────

def rbox(ax, x, y, w, h, fc, ec=None, lw=1.4, ls="solid", r=0.22, z=3):
    ec = ec if ec else fc
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc, edgecolor=ec,
        linewidth=lw, linestyle=ls, zorder=z))

def t(ax, x, y, s, fs=9, c="white", bold=False, ha="center", va="center",
      z=6, alpha=1.0, wrap=False):
    ax.text(x, y, s, fontsize=fs, color=c, ha=ha, va=va,
            weight="bold" if bold else "normal", zorder=z, alpha=alpha)

def panel_bg(ax, x, y, w, h, title, tc, fc, ec, tfs=10):
    rbox(ax, x, y, w, h, fc=fc, ec=ec, lw=1.6, r=0.35, z=1)
    ax.text(x + w/2, y + h - 0.20, title,
            fontsize=tfs, color=tc, ha="center", va="top",
            weight="bold", zorder=4)

def badge(ax, x, y, label, fc):
    rbox(ax, x, y, 0.95, 0.28, fc=fc, ec="white", lw=0.7, r=0.08, z=7)
    t(ax, x + 0.475, y + 0.14, label, fs=6.0, bold=True, z=8)

def v_arrow(ax, x, y0, y1, c="#6090BB"):
    ax.annotate("", xy=(x, y1), xytext=(x, y0),
                arrowprops=dict(
                    arrowstyle="<->, head_width=0.30, head_length=0.22",
                    color=c, lw=1.8), zorder=5)

# =============================================================================
# TITLE
# =============================================================================
t(ax, 9.5, 16.72,
  "Saucer Backend — Blueprint Refactor Architecture",
  fs=18, c=C_MAIN, bold=True, va="top")
t(ax, 9.5, 16.26,
  "The monolith (main.py) is being split into focused Blueprint files — one concern per file",
  fs=10.5, c="#555", va="top")

# =============================================================================
# LEFT COLUMN   x: 0.25 → 18.80
# =============================================================================
LX   = 0.25
LW   = 18.55

# ─── LAYER A: main.py   y: 14.20 → 15.90 ────────────────────────────────────
panel_bg(ax, LX, 14.15, LW, 1.75,
         "main.py  —  Flask App Entry Point",
         C_MAIN, fc="#D4E4F2", ec=C_MAIN, tfs=10)

# today box
rbox(ax, 0.55, 14.35, 8.20, 1.10, fc=C_MAIN)
t(ax, 4.65, 15.06, "TODAY:  main.py  (~1,593 lines)", fs=10.5, bold=True)
t(ax, 4.65, 14.67, "Most routes live here — being extracted sprint by sprint",
  fs=8.5, c="#B0CCE8")

# arrow
ax.annotate("", xy=(11.20, 14.90), xytext=(8.95, 14.90),
            arrowprops=dict(arrowstyle="->, head_width=0.35, head_length=0.22",
                            color=C_MAIN, lw=2.2), zorder=5)
t(ax, 10.07, 15.14, "refactor", fs=8, c=C_MAIN)

# target box
rbox(ax, 11.20, 14.35, 7.10, 1.10, fc=C_ROUTE_DONE)
t(ax, 14.75, 15.06, "TARGET:  main.py", fs=10.5, bold=True)
t(ax, 14.75, 14.67,
  "Thin bootstrap only  (/health + blueprint registration)",
  fs=8.5, c="#B8EED0")

# ─── inter-arrow A→B ─────────────────────────────────────────────────────────
v_arrow(ax, 0.10, 14.15, 12.65)

# ─── LAYER B: routes/   y: 10.05 → 12.65 ────────────────────────────────────
panel_bg(ax, LX, 10.00, LW, 2.65,
         "routes/  —  Flask Blueprints  (each file owns one concern)",
         C_ROUTE_DONE, fc="#E0F2E8", ec=C_ROUTE_DONE, tfs=10)

RW = 3.10   # route box width
RH = 1.00
RGAP = 0.22

done_routes = [
    ("routes/agent.py",   "AI agent\n& briefings"),
    ("routes/tasks.py",   "Cloud Tasks\nhandlers"),
]
planned_routes = [
    ("routes/emails.py",   "Email listing\nfilter / dismiss"),
    ("routes/calendar.py", "Calendar\nCRUD"),
    ("routes/files.py",    "File upload\n& download"),
    ("routes/filters.py",  "Keyword & sender\nfilter rules"),
    ("routes/memory.py",   "Hana notes\n& questions"),
    ("routes/admin.py",    "Debug / stats\nuser settings"),
]

# Top row: 2 done + 3 planned   (5 across)
TOP_Y = 11.38
BOT_Y = 10.18
RX0   = 0.52

all_top = done_routes + planned_routes[:3]
for i, (name, desc) in enumerate(all_top):
    rx = RX0 + i * (RW + RGAP)
    done = i < 2
    fc   = C_ROUTE_DONE if done else "#F5EBD8"
    ec   = C_ROUTE_DONE if done else C_ROUTE_PLAN
    ls   = "solid"      if done else "dashed"
    rbox(ax, rx, TOP_Y, RW, RH, fc=fc, ec=ec, lw=2.0, ls=ls)
    nc = "white"   if done else C_ROUTE_PLAN
    dc = "#B8EED0" if done else "#8B5A30"
    t(ax, rx + RW/2, TOP_Y + RH - 0.26, name,  fs=8.0, bold=True, c=nc)
    t(ax, rx + RW/2, TOP_Y + 0.35,      desc,  fs=7.5,             c=dc)
    if done:
        badge(ax, rx + RW - 1.02, TOP_Y + RH - 0.02, "DONE",    fc="#0A4D2C")
    else:
        badge(ax, rx + RW - 1.02, TOP_Y + RH - 0.02, "PLANNED", fc="#B86010")

# Bottom row: 3 planned
for i, (name, desc) in enumerate(planned_routes[3:]):
    rx = RX0 + i * (RW + RGAP)
    rbox(ax, rx, BOT_Y, RW, RH, fc="#F5EBD8", ec=C_ROUTE_PLAN, lw=2.0, ls="dashed")
    t(ax, rx + RW/2, BOT_Y + RH - 0.26, name,  fs=8.0, bold=True, c=C_ROUTE_PLAN)
    t(ax, rx + RW/2, BOT_Y + 0.35,      desc,  fs=7.5,             c="#8B5A30")
    badge(ax, rx + RW - 1.02, BOT_Y + RH - 0.02, "PLANNED", fc="#B86010")

# ─── inter-arrow B→C ─────────────────────────────────────────────────────────
v_arrow(ax, 0.10, 10.00, 8.35)

# ─── LAYER C: lib/   y: 6.65 → 8.35 ─────────────────────────────────────────
panel_bg(ax, LX, 6.60, LW, 1.75,
         "lib/  —  Shared Infrastructure  (imported by all blueprint routes)",
         C_LIB, fc="#D8E8F8", ec=C_LIB, tfs=10)

LIB_W = 4.10
LIB_H = 1.08
LIB_GAP = 0.32
lib_items = [
    ("firestore_client.py", "Firestore DB init"),
    ("config.py",           "Shared constants, queue names, URLs"),
    ("auth.py",             "OIDC token\nverification"),
    ("email_helpers.py",    "Email utility functions"),
]
lx0 = 0.52
for i, (name, desc) in enumerate(lib_items):
    lx = lx0 + i * (LIB_W + LIB_GAP)
    rbox(ax, lx, 6.88, LIB_W, LIB_H, fc=C_LIB)
    t(ax, lx + LIB_W/2, 6.88 + LIB_H - 0.26, name, fs=8.5, bold=True)
    t(ax, lx + LIB_W/2, 6.88 + 0.38,          desc, fs=7.8, c="#C0D8F8")

# ─── inter-arrow C→D ─────────────────────────────────────────────────────────
v_arrow(ax, 0.10, 6.60, 5.00)

# ─── LAYER D: Domain modules   y: 0.30 → 5.00 ───────────────────────────────
panel_bg(ax, LX, 0.25, LW, 4.75,
         "Domain Modules  —  Business Logic  (unchanged by the Blueprint refactor)",
         C_DOMAIN, fc="#EAE6F5", ec=C_DOMAIN, tfs=10)

domain_items = [
    ("agent.py",           "AI decision\nengine"),
    ("email_store.py",     "Email Firestore\n& GCS storage"),
    ("pending_actions.py", "Queued actions\n& outcomes"),
    ("task_queue.py",      "Cloud Tasks\nenqueue helpers"),
    ("gmail_scanner.py",   "Gmail inbox\nscanning"),
    ("email_scanner.py",   "Email intent\nclassification"),
    ("mediator.py",        "Household conflict\nmediation logic"),
    ("memory.py",          "Hana long-term\nmemory & notes"),
    ("gcalendar.py",       "Google Calendar\nintegration"),
    ("gdocs.py / gcs.py",  "Docs & Storage\nfile helpers"),
]

DW = 3.30
DH = 1.05
DX_GAP = 0.24
DY_GAP = 0.40
dx0 = 0.52

# 2 rows of 5
for i, (name, desc) in enumerate(domain_items):
    col = i % 5
    row = i // 5
    dx = dx0 + col * (DW + DX_GAP)
    dy = 3.55 - row * (DH + DY_GAP)
    rbox(ax, dx, dy, DW, DH, fc=C_DOMAIN)
    t(ax, dx + DW/2, dy + DH - 0.28, name, fs=8.2, bold=True)
    t(ax, dx + DW/2, dy + 0.34,      desc, fs=7.5, c="#D0C8F0")

# =============================================================================
# RIGHT COLUMN  x: 19.20 → 23.75
# GCP services + legend
# =============================================================================

GX   = 19.15
GW   =  4.60

panel_bg(ax, GX, 0.25, GW, 15.65,
         "Google Cloud\nInfrastructure",
         C_GCP_HEADER, fc="#FEF0E3", ec=C_GCP_HEADER, tfs=11)

gcp = [
    ("Cloud Run",       "Hosts the Flask app\nas a managed container", "#C0390A"),
    ("Cloud Firestore", "Database — tasks,\nemails, user data",        "#D4830A"),
    ("Cloud Storage",   "File blobs, config\n& email archive",         "#2878B8"),
    ("Cloud Tasks",     "Background job\nqueue with retry",            "#1C8C4A"),
    ("Gmail / Pub/Sub", "Email push\ntriggers via subscription",       "#B82020"),
    ("Cloud Scheduler", "Cron jobs:\nmorning briefing & scans",        "#7030A0"),
]

SVW = 4.00
SVH = 1.82
SV_GAP = 0.28
svx = GX + (GW - SVW) / 2

for i, (name, desc, color) in enumerate(gcp):
    # stack from top down
    sy = 15.55 - (i + 1) * (SVH + SV_GAP) + SVH + SV_GAP - 0.15
    sy = 13.58 - i * (SVH + SV_GAP)
    rbox(ax, svx, sy, SVW, SVH, fc=color, ec=color)
    t(ax, svx + SVW/2, sy + SVH - 0.36, name, fs=11, bold=True)
    t(ax, svx + SVW/2, sy + 0.56,       desc, fs=8.2, c="#FFF0E0")

# ── Legend ────────────────────────────────────────────────────────────────────
LEG_X = GX + 0.18
LEG_Y = 0.32

t(ax, GX + GW/2, LEG_Y + 1.72, "Legend", fs=9, c="#333", bold=True)

legend_items = [
    (C_ROUTE_DONE, "solid",   "Route file — DONE"),
    (C_ROUTE_PLAN, "dashed",  "Route file — PLANNED"),
    (C_LIB,        "solid",   "Shared lib/ layer"),
    (C_DOMAIN,     "solid",   "Domain module"),
    (C_MAIN,       "solid",   "main.py entry point"),
]
for j, (color, ls, label_text) in enumerate(legend_items):
    ly = LEG_Y + 1.40 - j * 0.30
    fc = "#F5EBD8" if ls == "dashed" else color
    rbox(ax, LEG_X, ly - 0.10, 0.46, 0.22,
         fc=fc, ec=color, lw=1.5 if ls == "dashed" else 1.0,
         ls=ls, r=0.05, z=5)
    t(ax, LEG_X + 0.60, ly, label_text, fs=7.8, c="#333", ha="left", va="center", z=6)

# ── Connector arrows left → right ─────────────────────────────────────────────
ARROW_C = "#9AAABB"

def side_conn(y_left, y_right, label_text):
    ax.annotate("",
        xy=(GX, y_right), xytext=(LX + LW, y_left),
        arrowprops=dict(arrowstyle="->, head_width=0.22, head_length=0.15",
                        color=ARROW_C, lw=1.2,
                        connectionstyle="arc3,rad=0.0"),
        zorder=5)
    mx = (LX + LW + GX) / 2
    my = (y_left + y_right) / 2 + 0.11
    t(ax, mx, my, label_text, fs=6.5, c="#999", z=6)

# Each GCP service center-y (approximate):
# Cloud Run    → row 0  → sy = 13.58
# Firestore    → row 1  → sy = 13.58 - 1*(1.82+0.28) = 11.48
# GCS          → row 2  → sy = 9.38
# Cloud Tasks  → row 3  → sy = 7.28
# Gmail        → row 4  → sy = 5.18
# Scheduler    → row 5  → sy = 3.08

# main.py  → Cloud Run
side_conn(14.90, 13.58 + 1.82/2, "runs on")
# routes/  → Cloud Tasks
side_conn(11.32, 7.28  + 1.82/2, "enqueues")
# routes/  → Gmail/Pub-Sub
side_conn(10.58, 5.18  + 1.82/2, "push trigger")
# lib/     → Firestore
side_conn(7.52,  11.48 + 1.82/2, "reads/writes DB")
# domain   → GCS
side_conn(2.00,  9.38  + 1.82/2, "reads/writes blobs")

# =============================================================================
# SAVE
# =============================================================================
out = "/home/dcjohnston1/saucer/team/architecture.png"
plt.savefig(out, dpi=155, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print(f"Saved: {out}")
