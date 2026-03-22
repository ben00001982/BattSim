"""
ui/components/user_guide_pdf.py

Generate a comprehensive user guide PDF for BattSim using matplotlib PdfPages.
No external dependencies beyond matplotlib (already required).
"""
from __future__ import annotations
import io
import textwrap
from datetime import datetime

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_pdf import PdfPages

# ── Brand colours ─────────────────────────────────────────────────────────────
_DARK    = "#1F3864"   # primary dark blue
_MID     = "#2E5F9E"   # mid blue
_LIGHT   = "#D6E4F7"   # light blue background
_ACCENT  = "#F0A500"   # amber accent
_TEXT    = "#1A1A2E"   # near-black body text
_MUTED   = "#5A6A7A"   # muted grey
_WHITE   = "#FFFFFF"
_SUCCESS = "#2E7D32"
_WARN    = "#E65100"

# Page dimensions (A4 landscape in inches)
_W, _H = 11.69, 8.27


def _new_fig():
    fig = plt.figure(figsize=(_W, _H))
    fig.patch.set_facecolor(_WHITE)
    return fig


def _header_band(fig, title: str, subtitle: str = "", page_num: str = ""):
    """Draw the top header band shared by all content pages."""
    ax = fig.add_axes([0, 0.88, 1, 0.12])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="square,pad=0",
        facecolor=_DARK, edgecolor="none", transform=ax.transAxes,
    ))
    ax.text(0.02, 0.62, "BattSim", color=_ACCENT, fontsize=16,
            fontweight="bold", va="center", transform=ax.transAxes)
    ax.text(0.02, 0.25, "UAV Battery Analysis Tool — User Guide", color=_LIGHT,
            fontsize=8, va="center", transform=ax.transAxes)
    ax.text(0.18, 0.55, title, color=_WHITE, fontsize=14,
            fontweight="bold", va="center", transform=ax.transAxes)
    if subtitle:
        ax.text(0.18, 0.22, subtitle, color=_LIGHT, fontsize=9,
                va="center", transform=ax.transAxes)
    if page_num:
        ax.text(0.97, 0.4, page_num, color=_LIGHT, fontsize=8,
                ha="right", va="center", transform=ax.transAxes)


def _footer(fig, text: str = ""):
    ax = fig.add_axes([0, 0, 1, 0.04])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(mpatches.FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="square,pad=0",
        facecolor=_LIGHT, edgecolor="none",
    ))
    ax.text(0.5, 0.5, text or f"BattSim User Guide  ·  Generated {datetime.now():%B %Y}",
            color=_MUTED, fontsize=7, ha="center", va="center")


def _content_ax(fig, left=0.04, bottom=0.08, width=0.92, height=0.78):
    ax = fig.add_axes([left, bottom, width, height])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")
    return ax


def _section_title(ax, text: str, y: float, color=_MID):
    ax.add_patch(mpatches.FancyBboxPatch(
        (0, y - 0.025), 1, 0.055,
        boxstyle="round,pad=0.005",
        facecolor=_LIGHT, edgecolor=color, linewidth=0.8,
    ))
    ax.text(0.012, y + 0.005, text, color=color, fontsize=11,
            fontweight="bold", va="center")
    return y - 0.04


def _bullet(ax, text: str, y: float, indent: float = 0.025, color=_TEXT,
            size: float = 8.5, bold: bool = False):
    wrapped = textwrap.fill(text, width=110)
    ax.text(indent, y, "•  " + wrapped, color=color, fontsize=size,
            va="top", fontweight="bold" if bold else "normal",
            linespacing=1.4)
    lines = wrapped.count("\n") + 1
    return y - 0.038 * lines - 0.01


def _para(ax, text: str, y: float, indent: float = 0.02, color=_TEXT, size: float = 8.5):
    wrapped = textwrap.fill(text, width=120)
    ax.text(indent, y, wrapped, color=color, fontsize=size,
            va="top", linespacing=1.5)
    lines = wrapped.count("\n") + 1
    return y - 0.036 * lines - 0.01


def _info_box(ax, text: str, y: float, height: float = 0.08,
              bg=_LIGHT, border=_MID, icon="ℹ"):
    ax.add_patch(mpatches.FancyBboxPatch(
        (0, y - height), 1, height,
        boxstyle="round,pad=0.008",
        facecolor=bg, edgecolor=border, linewidth=1,
    ))
    wrapped = textwrap.fill(text, width=115)
    ax.text(0.015, y - 0.015, f"{icon}  {wrapped}", color=_TEXT, fontsize=8,
            va="top", linespacing=1.4)
    return y - height - 0.015


def _two_cols(ax, left_items: list[str], right_items: list[str],
              y: float, title_l: str = "", title_r: str = ""):
    """Render two bullet columns side by side."""
    mid = 0.52
    if title_l:
        ax.text(0.0, y, title_l, color=_MID, fontsize=9, fontweight="bold")
        ax.text(mid, y, title_r, color=_MID, fontsize=9, fontweight="bold")
        y -= 0.04
    for item in left_items:
        ax.text(0.02, y, f"• {textwrap.fill(item, 52)}", color=_TEXT,
                fontsize=8.0, va="top", linespacing=1.3)
        y -= 0.038
    y_right = y + 0.038 * len(left_items)
    for item in right_items:
        ax.text(mid + 0.01, y_right, f"• {textwrap.fill(item, 52)}", color=_TEXT,
                fontsize=8.0, va="top", linespacing=1.3)
        y_right -= 0.038
    return min(y, y_right) - 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Page builders
# ─────────────────────────────────────────────────────────────────────────────

def _page_cover(pdf: PdfPages):
    fig = _new_fig()
    # Background
    ax_bg = fig.add_axes([0, 0, 1, 1])
    ax_bg.set_xlim(0, 1); ax_bg.set_ylim(0, 1)
    ax_bg.axis("off")
    ax_bg.add_patch(mpatches.FancyBboxPatch(
        (0, 0), 1, 1, boxstyle="square,pad=0",
        facecolor=_DARK, edgecolor="none",
    ))
    # Decorative band
    ax_bg.add_patch(mpatches.FancyBboxPatch(
        (0, 0.38), 1, 0.005, boxstyle="square,pad=0",
        facecolor=_ACCENT, edgecolor="none",
    ))
    ax_bg.add_patch(mpatches.FancyBboxPatch(
        (0, 0.36), 1, 0.005, boxstyle="square,pad=0",
        facecolor=_MID, edgecolor="none",
    ))

    # Titles
    ax_bg.text(0.5, 0.72, "BattSim", color=_ACCENT, fontsize=60,
               fontweight="bold", ha="center", va="center", alpha=0.9)
    ax_bg.text(0.5, 0.60, "UAV Battery Analysis Tool", color=_WHITE, fontsize=22,
               ha="center", va="center")
    ax_bg.text(0.5, 0.52, "Comprehensive User Guide", color=_LIGHT, fontsize=15,
               ha="center", va="center", style="italic")
    ax_bg.text(0.5, 0.31, "For users with a technical background — no prior experience required",
               color=_LIGHT, fontsize=10, ha="center", va="center", alpha=0.8)
    ax_bg.text(0.5, 0.24,
               "Physics-based battery discharge simulation and mission planning for UAV operations",
               color=_MUTED, fontsize=9, ha="center", va="center", alpha=0.9)
    ax_bg.text(0.5, 0.10, f"Generated {datetime.now():%B %Y}",
               color=_MUTED, fontsize=8, ha="center", va="center")

    # Feature pills
    features = ["Battery Database", "Discharge Simulation", "Mission Planning",
                 "Log Analysis", "Report Generation"]
    x0 = 0.1
    step = 0.17
    for i, feat in enumerate(features):
        cx = x0 + i * step
        ax_bg.add_patch(mpatches.FancyBboxPatch(
            (cx - 0.07, 0.14), 0.145, 0.045,
            boxstyle="round,pad=0.008",
            facecolor=_MID, edgecolor=_ACCENT, linewidth=0.8, alpha=0.7,
        ))
        ax_bg.text(cx, 0.163, feat, color=_WHITE, fontsize=7.5,
                   ha="center", va="center")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_toc(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Table of Contents", page_num="Page 2")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    ax.text(0.0, y, "This guide covers all major features of BattSim in the order they appear "
            "in the sidebar navigation.", color=_MUTED, fontsize=8.5, va="top")
    y -= 0.06

    sections = [
        ("1", "Getting Started",            "Overview, navigation, and initial setup",              "3"),
        ("2", "Main Dashboard",             "KPI cards, configuration status, quick navigation",    "4"),
        ("3", "Battery Browser",            "Searching, filtering, and comparing battery packs",    "5"),
        ("4", "UAV Configurator",           "Equipment database and UAV power profiles",            "6"),
        ("5", "Mission Configurator",       "Battery selection, mission setup, and phase details",  "7"),
        ("6", "Simulation",                 "Running discharge simulations and reading results",    "8"),
        ("7", "Reports",                    "Temperature sweep, scorecard, and PDF/Excel export",  "9"),
        ("8", "Tools",                      "Pack Builder, Model Validation, and Bulk Import",     "10"),
        ("9", "Log Tools",                  "Log Analysis, ECM fitting, and Log→Mission extractor","11"),
        ("10","Key Concepts & Terminology", "Battery physics, confidence levels, phase types",     "13"),
        ("11","Troubleshooting",            "Common issues and how to resolve them",               "14"),
    ]

    # Column headers
    ax.text(0.01, y, "#",     color=_MID, fontsize=9, fontweight="bold")
    ax.text(0.07, y, "Section",  color=_MID, fontsize=9, fontweight="bold")
    ax.text(0.40, y, "Description", color=_MID, fontsize=9, fontweight="bold")
    ax.text(0.90, y, "Page",    color=_MID, fontsize=9, fontweight="bold", ha="right")
    y -= 0.025
    ax.add_patch(mpatches.FancyBboxPatch(
        (0, y), 1, 0.002, boxstyle="square,pad=0",
        facecolor=_MID, edgecolor="none",
    ))
    y -= 0.025

    for num, title, desc, pg in sections:
        bg = _LIGHT if int(num) % 2 == 0 else _WHITE
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, y - 0.025), 1, 0.04,
            boxstyle="square,pad=0",
            facecolor=bg, edgecolor="none",
        ))
        ax.text(0.01, y - 0.005, num,   color=_DARK,  fontsize=8.5, va="center", fontweight="bold")
        ax.text(0.07, y - 0.005, title, color=_DARK,  fontsize=8.5, va="center", fontweight="bold")
        ax.text(0.40, y - 0.005, desc,  color=_MUTED, fontsize=8,   va="center")
        ax.text(0.90, y - 0.005, pg,    color=_MID,   fontsize=8.5, va="center", ha="right",
                fontweight="bold")
        y -= 0.048

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_getting_started(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Getting Started", "Overview, navigation, and initial setup", "Page 3")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "BattSim is a physics-based battery simulation and selection tool designed for UAV "
        "mission planning. It lets you model how different battery chemistries and pack "
        "configurations will perform across varying mission profiles, temperatures, and "
        "equipment loads — without requiring real flight data.",
        y)
    y -= 0.02

    y = _section_title(ax, "Navigation", y)
    y = _para(ax,
        "All pages are listed in the left sidebar. Click any page name to navigate directly. "
        "Pages are numbered to suggest a logical workflow, but you can visit them in any order.",
        y)
    y -= 0.01

    y = _two_cols(ax,
        left_items=[
            "Main Dashboard — status overview and database summary",
            "Battery Browser — explore and compare all packs",
            "UAV Configurator — define equipment and UAV profiles",
            "Mission Configurator — set up the analysis run",
            "Simulation — run discharge models",
            "Reports — export results",
        ],
        right_items=[
            "Tools — pack building, validation, and bulk import",
            "Log Tools — real flight log analysis and mission extraction",
            "User Guide — this document (interactive version)",
            "",
            "Use the sidebar collapse button (◀) to gain screen space",
            "Session state is preserved while the app is running",
        ],
        y=y, title_l="Pages (left sidebar)", title_r="Tips")
    y -= 0.02

    y = _section_title(ax, "Recommended First-Run Workflow", y)
    steps = [
        ("1", "Open Mission Configurator — select a mission profile and UAV configuration"),
        ("2", "Select battery packs from the Battery Browser or by chemistry filter"),
        ("3", "Click Save Config on the Mission Configurator page"),
        ("4", "Go to Simulation — click Run Simulation and review voltage/SoC curves"),
        ("5", "Open Reports — generate a PDF or Excel scorecard for all selected packs"),
        ("6", "Optionally upload a real flight log in Log Tools to validate the simulation"),
    ]
    for num, text in steps:
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, y - 0.032), 0.025, 0.04,
            boxstyle="round,pad=0.004",
            facecolor=_MID, edgecolor="none",
        ))
        ax.text(0.0125, y - 0.013, num, color=_WHITE, fontsize=9,
                ha="center", va="center", fontweight="bold")
        ax.text(0.035, y - 0.008, text, color=_TEXT, fontsize=8.5, va="center")
        y -= 0.048

    y = _info_box(ax,
        "The database (battery_db.xlsx) is the single source of truth. All battery packs, "
        "cells, equipment, UAV configs, missions, and discharge profiles are stored there. "
        "The file is read at startup and can be refreshed with the reload button on any page.",
        y - 0.01, height=0.085, bg="#FFF8E1", border=_ACCENT, icon="⚠")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_dashboard(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Main Dashboard", "KPI cards, configuration status, and quick navigation", "Page 4")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Main Dashboard is your starting point. It shows a live summary of the database "
        "contents, the current analysis configuration, and simulation status.",
        y)
    y -= 0.02

    y = _section_title(ax, "KPI Cards (top row)", y)
    items = [
        ("Battery Packs", "Total number of packs loaded from Battery_Catalog sheet"),
        ("Cell Types",    "Unique cell models in Cell_Catalog"),
        ("Missions",      "Mission profiles in Mission_Profiles sheet"),
        ("UAV Configs",   "UAV configurations defined in UAV_Configurations sheet"),
        ("Chemistries",   "Chemistry definitions in Chemistry_Library sheet"),
    ]
    for name, desc in items:
        y = _bullet(ax, f"{name} — {desc}", y)
    y -= 0.01

    y = _section_title(ax, "Active Configuration Panel", y)
    y = _para(ax,
        "Displays the mission, UAV, temperature, and battery packs saved by the Mission "
        "Configurator. This is the configuration that will be used when you click Run "
        "Simulation. If it shows dashes (—) you have not yet saved a config.",
        y)
    y -= 0.01

    y = _section_title(ax, "Simulation Status Panel", y)
    y = _bullet(ax, "Simulation results — count of packs with completed simulations this session", y)
    y = _bullet(ax, "Temp sweep results — count of packs with temperature sweep data", y)
    y = _bullet(ax, "Flight log — shows duration if a log was loaded in Log Tools", y)
    y -= 0.01

    y = _section_title(ax, "Reset Button", y)
    y = _para(ax,
        "Clears all selected batteries, the active config, and all simulation results. "
        "The database itself is not affected — only the in-session analysis state is cleared. "
        "Use this when starting a fresh analysis run.",
        y)

    y = _info_box(ax,
        "Session state is per-browser-tab. If you open BattSim in a second tab, it starts "
        "with a clean session. Simulation results are NOT persisted to disk — only the "
        "analysis_config.json file (battery selection, mission, UAV, temperature) is saved.",
        y - 0.01, height=0.085, bg=_LIGHT, border=_MID, icon="ℹ")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_battery_browser(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Battery Browser", "Searching, filtering, and comparing battery packs", "Page 5")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Battery Browser gives you access to all packs in the database. You can filter "
        "by chemistry, energy range, cell configuration, and UAV class, then add selections "
        "directly to the Mission Configurator.",
        y)
    y -= 0.02

    y = _section_title(ax, "Filtering Options", y)
    y = _bullet(ax, "Chemistry — select one or more chemistries (LiPo, Li-Ion, LiFePO4, LiHV, etc.)", y)
    y = _bullet(ax, "Energy range — set minimum and maximum Wh bounds", y)
    y = _bullet(ax, "S count — filter by series cell count (e.g. 6S, 12S)", y)
    y = _bullet(ax, "UAV class — filter by target platform type (e.g. 'Heavy VTOL', 'Multirotor')", y)
    y -= 0.01

    y = _section_title(ax, "Pack Table", y)
    y = _para(ax,
        "The table shows all matching packs with key specifications: voltage, capacity (Ah), "
        "energy (Wh), weight (g), specific energy (Wh/kg), max continuous discharge current, "
        "and internal resistance. Columns are sortable — click a header to sort.",
        y)
    y -= 0.01

    y = _section_title(ax, "Pack Details Expander", y)
    y = _para(ax,
        "Click any row or use the detail expander to see the full specification including "
        "discharge curves and chemistry properties. A discharge curve chart shows voltage "
        "vs state-of-charge at different C-rates and temperatures.",
        y)
    y -= 0.01

    y = _section_title(ax, "Sending Packs to the Mission Configurator", y)
    y = _bullet(ax, "Tick the checkbox next to any pack to add it to your selection", y)
    y = _bullet(ax, "Click 'Send X pack(s) to Mission Configurator' to transfer the selection", y)
    y = _bullet(ax, "The Mission Configurator shows an import button when packs are pending transfer", y)
    y -= 0.01

    y = _info_box(ax,
        "Specific energy (Wh/kg) is the most important single number for UAV battery selection. "
        "Higher is better — it means more flight energy per gram of battery weight. "
        "LiHV and high-density Li-Ion cells typically lead this metric.",
        y - 0.01, height=0.085, bg="#E8F5E9", border=_SUCCESS, icon="✓")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_uav_configurator(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "UAV Configurator", "Equipment database and UAV power profiles", "Page 6")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The UAV Configurator manages two things: the Equipment Database (individual "
        "components like motors, ESCs, cameras) and UAV Configurations (assemblies of "
        "equipment that define the power model for a complete aircraft).",
        y)
    y -= 0.02

    y = _section_title(ax, "Equipment Database Tab", y)
    y = _bullet(ax, "Each equipment item has idle, operating, and max power levels (Watts)", y)
    y = _bullet(ax, "Categories include: motors, ESCs, cameras, payloads, sensors, avionics", y)
    y = _bullet(ax, "Use 'Add Equipment' form to enter a new item, then click Save", y)
    y = _bullet(ax, "Inactive items (Active = No) are hidden from UAV config dropdowns", y)
    y -= 0.01

    y = _section_title(ax, "Power Level Definitions", y)
    y = _bullet(ax, "Idle power — draw when powered on but not working (e.g. camera standby)", y)
    y = _bullet(ax, "Operating power — normal working draw used in simulations by default", y)
    y = _bullet(ax, "Max power — peak draw (e.g. camera capture burst, servo slewing)", y)
    y -= 0.01

    y = _section_title(ax, "UAV Configurations Tab", y)
    y = _para(ax,
        "A UAV Configuration is a named list of (Equipment item, quantity) pairs. The total "
        "power draw at any mission phase is the sum of operating_power × quantity for all items, "
        "unless overridden by phase-level equipment assignments.",
        y)
    y = _bullet(ax, "Create a new UAV config with a unique ID and name", y)
    y = _bullet(ax, "Add equipment items with quantities (e.g. 4× motors, 1× camera)", y)
    y = _bullet(ax, "The total weight shown helps cross-check against airframe specs", y)
    y -= 0.01

    y = _info_box(ax,
        "Per-phase equipment state assignments (On/Idle/Off/Custom) are configured in the "
        "Mission Configurator, not here. The UAV Configurator only defines what equipment "
        "exists and its power levels — the mission defines when each item is active.",
        y - 0.01, height=0.085, bg=_LIGHT, border=_MID, icon="ℹ")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_mission_configurator(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Mission Configurator", "Battery selection, mission setup, and phase details", "Page 7")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Mission Configurator is the control centre of BattSim. It connects batteries, "
        "a mission profile, and a UAV configuration into a single analysis config that drives "
        "all simulations and reports.",
        y)
    y -= 0.02

    y = _section_title(ax, "Mission & Battery Config Tab", y)
    y = _bullet(ax, "Mission — select the flight profile (defines phase sequence and durations)", y)
    y = _bullet(ax, "UAV Configuration — determines power draw per phase", y)
    y = _bullet(ax, "Ambient temperature — affects battery capacity and internal resistance", y)
    y = _bullet(ax, "Temperature sweep range — defines the range used in Reports temperature analysis", y)
    y = _bullet(ax, "Battery selection — choose one or more packs to compare in simulation", y)
    y = _bullet(ax, "Click Save Config to persist the selection to analysis_config.json", y)
    y -= 0.01

    y = _section_title(ax, "Mission Phase Breakdown", y)
    y = _para(ax,
        "Expanding 'Mission Phase Breakdown' shows each phase's duration, power demand, "
        "cumulative energy, and equipment states. The power timeline chart visualises how "
        "demand changes across the mission.",
        y)
    y -= 0.01

    y = _section_title(ax, "Mission Builder Tab", y)
    y = _para(ax,
        "Create and edit mission profiles directly in the UI. Each phase has a name, type "
        "(ArduPilot mode or power category), duration, optional distance/altitude, and an "
        "optional power override. Power overrides bypass the equipment model for that phase.",
        y)
    y = _bullet(ax, "Phase types map to power categories: HOVER, CRUISE, TAKEOFF, LAND, etc.", y)
    y = _bullet(ax, "power_override_w: if set, this exact wattage is used regardless of equipment config", y)
    y = _bullet(ax, "Per-phase equipment assignments: toggle each item On/Idle/Off/Custom per phase", y)

    y = _info_box(ax,
        "Tip: If your mission was flown with a real aircraft, use Log Tools → Log → Mission "
        "to automatically extract a mission profile from a flight log. This gives you "
        "realistic phase durations and measured power values.",
        y - 0.01, height=0.085, bg="#E8F5E9", border=_SUCCESS, icon="✓")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_simulation(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Simulation", "Running discharge simulations and interpreting results", "Page 8")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Simulation page runs the physics-based discharge model for all selected battery "
        "packs against the saved mission config. Results include voltage curves, SoC curves, "
        "temperature evolution, and a pass/fail scorecard.",
        y)
    y -= 0.02

    y = _section_title(ax, "Simulation Parameters", y)
    y = _bullet(ax, "Model mode — FAST (lookup table), STANDARD (full OCV model), or PRECISE (2RC ECM)", y)
    y = _bullet(ax, "Initial SoC — starting state of charge (normally 100%)", y)
    y = _bullet(ax, "Peukert exponent k — models capacity reduction at high discharge rates (default 1.05)", y)
    y = _bullet(ax, "Cutoff SoC — simulation stops when this SoC is reached (default 10%)", y)
    y = _bullet(ax, "Depth of discharge limit — maximum usable fraction of rated capacity (default 80%)", y)
    y -= 0.01

    y = _section_title(ax, "Model Modes Explained", y)
    y = _bullet(ax, "FAST — uses a pre-built OCV lookup table; very fast, suitable for initial screening", y)
    y = _bullet(ax, "STANDARD — full Shepherd/OCV model with temperature derating; recommended for planning", y)
    y = _bullet(ax, "PRECISE — requires fitted 2RC ECM parameters from a real flight log (via Log Tools)", y)
    y -= 0.01

    y = _section_title(ax, "Reading the Results", y)
    y = _bullet(ax, "PASS — battery completes the mission with >10% SoC margin remaining", y)
    y = _bullet(ax, "MARGINAL — completes with <10% margin, consider a larger pack", y)
    y = _bullet(ax, "FAIL — battery is depleted before the mission ends", y)
    y = _bullet(ax, "Voltage sag — higher internal resistance causes larger voltage drops under load", y)
    y = _bullet(ax, "Final SoC — the remaining charge at mission end; higher is safer", y)

    y = _info_box(ax,
        "PRECISE mode requires prior use of Log Tools → Parameter Fitter on a real flight "
        "log for the specific pack. Without fitted ECM parameters it will fall back to "
        "STANDARD. ECM parameters are temperature-specific — multiple logs at different "
        "ambient temperatures improve interpolation accuracy.",
        y - 0.01, height=0.09, bg=_LIGHT, border=_MID, icon="ℹ")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_reports(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Reports", "Temperature sweep, scorecard, and PDF/Excel export", "Page 9")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Reports page generates publication-quality output from your simulation results. "
        "It requires a saved configuration and at least one completed simulation run. "
        "Reports can be downloaded as PDF or Excel.",
        y)
    y -= 0.02

    y = _section_title(ax, "Temperature Sensitivity Sweep", y)
    y = _para(ax,
        "Runs the simulation across the temperature range defined in Mission Configurator. "
        "The resulting chart shows how each pack's final SoC varies with ambient temperature — "
        "critical for understanding cold-weather performance.",
        y)
    y = _bullet(ax, "Click Run Temperature Sweep to compute all temperature points", y)
    y = _bullet(ax, "Each curve represents one battery pack across the sweep range", y)
    y = _bullet(ax, "Packs that cross the failure threshold at certain temperatures are highlighted", y)
    y -= 0.01

    y = _section_title(ax, "Battery Scorecard", y)
    y = _para(ax,
        "A ranked table of all simulated packs showing energy, weight, final SoC, minimum "
        "voltage, peak current, and pass/fail status. Sort by any column to identify the "
        "best-performing pack for your mission.",
        y)
    y -= 0.01

    y = _section_title(ax, "Export Options", y)
    y = _bullet(ax, "Download PDF Report — multi-page PDF with charts, scorecard, and mission details", y)
    y = _bullet(ax, "Download Excel Report — structured workbook with raw data for further analysis", y)
    y = _bullet(ax, "Both formats include metadata: mission ID, UAV, temperature, simulation parameters", y)

    y = _info_box(ax,
        "Reports are generated on demand and not saved to disk automatically. Download them "
        "before closing the browser tab. The PDF uses matplotlib rendering — for best results "
        "ensure simulations have completed before generating reports.",
        y - 0.01, height=0.085, bg="#FFF8E1", border=_ACCENT, icon="⚠")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_tools(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Tools", "Pack Builder, Model Validation, and Bulk Data Import", "Page 10")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Tools page provides three utility functions for database management and "
        "simulation validation. All write directly to battery_db.xlsx.",
        y)
    y -= 0.02

    y = _section_title(ax, "Pack Builder Tab", y)
    y = _bullet(ax, "Build from Cell — select a cell from the catalog and specify S×P configuration", y)
    y = _bullet(ax, "Weight overhead (%) — accounts for BMS, wiring, and enclosure mass", y)
    y = _bullet(ax, "Preview shows computed voltage, capacity, energy, weight, and specific energy", y)
    y = _bullet(ax, "Combine Packs — connect existing packs in series (higher voltage) or parallel (higher capacity)", y)
    y = _bullet(ax, "Save to Database writes the new pack to Battery_Catalog in battery_db.xlsx", y)
    y -= 0.01

    y = _section_title(ax, "Model Validation Tab", y)
    y = _para(ax,
        "Compares FAST, STANDARD, and PRECISE simulation modes against a loaded flight log. "
        "Requires a flight log in session (load one via Log Tools first). Reports RMSE, MAE, "
        "R², and bias for each mode so you can select the most accurate option for your pack.",
        y)
    y -= 0.01

    y = _section_title(ax, "Bulk Data Upload Tab", y)
    y = _bullet(ax, "CSV Import — download a template, fill in up to hundreds of packs, upload to add them all at once", y)
    y = _bullet(ax, "Web Scraper — enter a product URL to auto-extract battery specifications from a web page", y)
    y = _bullet(ax, "PDF Datasheet — upload a manufacturer datasheet PDF; key specs are extracted automatically", y)
    y = _para(ax,
        "For all three methods, review the extracted data before saving — automatic extraction "
        "is approximate and fields should be verified against the original source.",
        y)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_log_tools(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Log Tools", "Log Analysis, ECM fitting, and Log → Mission Extractor", "Page 11")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "Log Tools is the bridge between real flight data and the BattSim simulation "
        "engine. It can parse ArduPilot binary (.bin) and text (.log) logs as well as "
        "Mission Planner CSV exports.",
        y)
    y -= 0.02

    y = _section_title(ax, "Log Analysis Tab", y)
    y = _bullet(ax, "Upload a real flight log or generate a synthetic one for testing", y)
    y = _bullet(ax, "Synthetic log — creates a simulated log from any pack/mission/UAV combo in the database", y)
    y = _bullet(ax, "Flight summary — duration, samples, peak current, total mAh, voltage range", y)
    y = _bullet(ax, "Charts: Voltage, Current, SoC, Temperature, and Phase Timeline tabs", y)
    y = _bullet(ax, "Simulation comparison — overlay real log data against a simulation result", y)
    y -= 0.01

    y = _section_title(ax, "Parameter Fitter (within Log Analysis)", y)
    y = _para(ax,
        "Fits a 2RC Equivalent Circuit Model (ECM) from step-response events in the log. "
        "The fitted parameters (R0, R1, R2, τ1, τ2) are stored in the Log Registry and "
        "used by PRECISE-mode simulation.",
        y)
    y = _bullet(ax, "Select the battery pack that was in the aircraft during the flight", y)
    y = _bullet(ax, "Enter the mean flight temperature — critical for temperature-dependent interpolation", y)
    y = _bullet(ax, "Click Fit & Register — fitting runs in seconds", y)
    y -= 0.01

    y = _section_title(ax, "Log Registry & ECM Viewer Tabs", y)
    y = _bullet(ax, "Log Registry lists all registered logs with fitted ECM parameters", y)
    y = _bullet(ax, "ECM Viewer plots resistance and time constants vs temperature for a pack", y)
    y = _bullet(ax, "Multiple logs at different temperatures build an interpolation curve for PRECISE mode", y)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_log_to_mission(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Log → Mission Extractor", "Converting a real flight log into a mission profile", "Page 12")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _para(ax,
        "The Log → Mission tab (within Log Tools) automates the creation of mission profiles "
        "from real flight logs. Instead of manually estimating phase durations, it segments "
        "the log by flight mode changes and measures actual power draw per phase.",
        y)
    y -= 0.02

    y = _section_title(ax, "Step 1: Select a Log Source", y)
    y = _bullet(ax, "Use the log already loaded in Log Analysis (tick 'Use this log'), or", y)
    y = _bullet(ax, "Upload a new .bin, .log, or .csv file directly in this tab", y)
    y -= 0.01

    y = _section_title(ax, "Step 2: Choose Import Mode", y)
    y = _bullet(ax,
        "Phase + duration only — stores phase names and durations, no power override. "
        "Simulations use the UAV equipment model for power. Best for comparing equipment configs.",
        y, bold=False)
    y = _bullet(ax,
        "Phase + duration + estimated power — also stores measured mean power (V × I) per phase "
        "as power_override_w. High/medium confidence phases get the measured value; low confidence "
        "phases fall back to the equipment model.",
        y, bold=False)
    y -= 0.01

    y = _section_title(ax, "Step 3: Extract and Edit Phases", y)
    y = _bullet(ax, "Click Extract Phases — segmentation runs automatically", y)
    y = _bullet(ax, "Review the phase table: rename phases, change mode type, adjust duration or power", y)
    y = _bullet(ax, "Delete short or irrelevant phases (e.g. pre-arm idle segments)", y)
    y = _bullet(ax, "Merge adjacent phases of the same type if the flight mode toggled briefly", y)
    y -= 0.01

    y = _section_title(ax, "Step 4: Save the Mission", y)
    y = _bullet(ax, "Enter a unique Mission ID and name", y)
    y = _bullet(ax, "Select the UAV configuration that was flown", y)
    y = _bullet(ax, "Click Save Mission — the profile appears in Mission Configurator immediately", y)
    y -= 0.01

    y = _info_box(ax,
        "Confidence levels indicate data quality per phase. 'High' = ≥10 power samples with "
        "low variance. 'Medium' = enough samples but higher variance. 'Low' = too few samples "
        "for reliable power estimation — power override will be None even in power-import mode.",
        y - 0.01, height=0.09, bg=_LIGHT, border=_MID, icon="ℹ")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_concepts(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Key Concepts & Terminology", "Battery physics, phase types, and technical terms", "Page 13")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    y = _section_title(ax, "Battery Fundamentals", y)
    concepts_l = [
        "SoC (State of Charge) — remaining capacity as a % of rated capacity",
        "OCV (Open Circuit Voltage) — voltage with no load; function of SoC and temperature",
        "Internal resistance (IR) — causes voltage sag under load; increases with age and cold",
        "C-rate — discharge current relative to capacity (1C = full discharge in 1 hour)",
        "Peukert exponent — models capacity reduction at higher C-rates (k > 1)",
        "DoD (Depth of Discharge) — fraction of capacity used; limiting DoD extends cycle life",
    ]
    concepts_r = [
        "Specific energy (Wh/kg) — energy stored per unit mass; key pack comparison metric",
        "Energy density (Wh/L) — energy per unit volume; important for space-constrained installs",
        "2RC ECM — two RC-branch Equivalent Circuit Model for transient voltage behaviour",
        "Voltage sag — instantaneous drop below OCV under load; determined by IR × I",
        "Temperature derating — capacity and power capability reduction at low temperatures",
        "Cycle life — number of full charge/discharge cycles before capacity degrades to ~80%",
    ]
    y = _two_cols(ax, concepts_l, concepts_r, y)
    y -= 0.02

    y = _section_title(ax, "Phase Types (Mission Profile)", y)
    phase_types = [
        ("IDLE",         "Aircraft powered, rotors stopped — pre-arm or post-land"),
        ("TAKEOFF",      "Vertical climb from ground to transition altitude"),
        ("HOVER",        "Station-keeping at altitude; high motor demand"),
        ("CRUISE",       "Forward flight at cruise speed; typically lower power than hover"),
        ("CLIMB",        "Gaining altitude during forward flight"),
        ("DESCEND",      "Losing altitude during forward flight"),
        ("LAND",         "Final approach and touchdown"),
        ("PAYLOAD_OPS",  "Hovering while operating a payload (spray, delivery, survey)"),
        ("EMERGENCY",    "Emergency mode — RTL, failsafe; assume maximum power draw"),
    ]
    for ptype, desc in phase_types:
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, y - 0.028), 0.14, 0.036,
            boxstyle="round,pad=0.004",
            facecolor=_LIGHT, edgecolor=_MID, linewidth=0.6,
        ))
        ax.text(0.07, y - 0.011, ptype, color=_DARK, fontsize=7.5,
                ha="center", va="center", fontweight="bold")
        ax.text(0.16, y - 0.011, desc, color=_TEXT, fontsize=8, va="center")
        y -= 0.040

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _page_troubleshooting(pdf: PdfPages):
    fig = _new_fig()
    _header_band(fig, "Troubleshooting", "Common issues and how to resolve them", "Page 14")
    _footer(fig)
    ax = _content_ax(fig)

    y = 0.96
    issues = [
        (
            "Simulation fails with 'No discharge data'",
            "The selected pack's chemistry has no entries in Discharge_Profiles. Add discharge "
            "curve data for that chemistry, or select a pack with a well-supported chemistry "
            "(LiPo, Li-Ion, LiFePO4).",
            _WARN,
        ),
        (
            "'Mission not found' or 'UAV not found' on Simulation page",
            "The saved config references a mission or UAV that has been deleted or renamed. "
            "Return to Mission Configurator, re-select your mission and UAV, then click Save Config.",
            _WARN,
        ),
        (
            "Log file fails to parse",
            "Binary .bin files require pymavlink (pip install pymavlink). Text .log files need "
            "BAT messages — check that battery logging is enabled in ArduPilot (LOG_BITMASK). "
            "CSV files must follow the Mission Planner telemetry export column format.",
            _WARN,
        ),
        (
            "Log → Mission shows 'log.phase_type is empty'",
            "The log file contains no MODE messages. This can happen if MODE logging was "
            "disabled or if the log starts after arming. Try enabling LOG_BITMASK bit 1 "
            "(mode changes) in ArduPilot, or use a log from a later firmware version.",
            _WARN,
        ),
        (
            "Pack Builder: Pack ID already exists",
            "The auto-generated ID collides with an existing pack. Enter a custom Pack ID "
            "in the text field (leave it blank to auto-generate, or type a unique string).",
            _MUTED,
        ),
        (
            "PRECISE mode not available",
            "No ECM parameters have been fitted for the selected pack. Load a flight log in "
            "Log Tools, run Parameter Fitter, then register the result. PRECISE mode will "
            "then be available for that pack at the logged temperature.",
            _MUTED,
        ),
        (
            "Temperature sweep is slow",
            "Each sweep point runs a full simulation. With many packs and a wide temperature "
            "range, this can take 10–30 seconds. Narrow the sweep range or reduce the number "
            "of selected packs to speed it up.",
            _MUTED,
        ),
        (
            "Reports page shows 'No valid packs found'",
            "The pack IDs in analysis_config.json no longer exist in the database. Re-select "
            "your packs in Mission Configurator and save the config again.",
            _WARN,
        ),
    ]

    for problem, solution, color in issues:
        ax.add_patch(mpatches.FancyBboxPatch(
            (0, y - 0.07), 1, 0.072,
            boxstyle="round,pad=0.005",
            facecolor="#FFF8E1" if color == _WARN else _LIGHT,
            edgecolor=color, linewidth=0.7,
        ))
        ax.text(0.012, y - 0.012, problem, color=_DARK, fontsize=8.5,
                va="top", fontweight="bold")
        ax.text(0.012, y - 0.032, textwrap.fill(solution, 105),
                color=_TEXT, fontsize=7.8, va="top", linespacing=1.35)
        y -= 0.08

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_user_guide_pdf() -> bytes:
    """
    Build the complete user guide PDF and return as raw bytes.
    No file is written to disk.
    """
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        pdf.infodict()["Title"]   = "BattSim User Guide"
        pdf.infodict()["Author"]  = "BattSim"
        pdf.infodict()["Subject"] = "UAV Battery Analysis Tool — Comprehensive User Guide"

        _page_cover(pdf)
        _page_toc(pdf)
        _page_getting_started(pdf)
        _page_dashboard(pdf)
        _page_battery_browser(pdf)
        _page_uav_configurator(pdf)
        _page_mission_configurator(pdf)
        _page_simulation(pdf)
        _page_reports(pdf)
        _page_tools(pdf)
        _page_log_tools(pdf)
        _page_log_to_mission(pdf)
        _page_concepts(pdf)
        _page_troubleshooting(pdf)

    buf.seek(0)
    return buf.read()
