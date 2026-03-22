"""
ui/config.py
Shared constants, paths, and colour palettes for the BattSim Streamlit UI.
"""
from __future__ import annotations
from pathlib import Path
import sys

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH      = PROJECT_ROOT / "battery_db.xlsx"
CFG_PATH     = PROJECT_ROOT / "analysis_config.json"
REPORTS_DIR  = PROJECT_ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# Add project root to sys.path so batteries/mission imports work
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from batteries.ardupilot_modes import (
    ALL_MODES, POWER_CATEGORIES, mode_name_to_category,
)

# ── Phase colours (hex) — keyed by power category ────────────────────────────
_CATEGORY_COLORS: dict[str, str] = {
    "IDLE":            "#EEEEEE",
    "TAKEOFF":         "#FFD9B3",
    "CLIMB":           "#FFF0B3",
    "CRUISE":          "#C8EBD4",
    "HOVER":           "#C0D9F5",
    "DESCEND":         "#D5E4F7",
    "LAND":            "#E8D9F5",
    "PAYLOAD_OPS":     "#FFD0DD",
    "EMERGENCY":       "#FFB3B3",
    "VTOL_TRANSITION": "#FFE0B3",
    "VTOL_HOVER":      "#B3D5F5",
    "FW_CRUISE":       "#B3EBD4",
    "FW_CLIMB":        "#FFF5B3",
    "FW_DESCEND":      "#E0F5FF",
}

# Extend with ArduPilot mode names — each mapped to its category colour
# so phase_color("LOITER") and phase_color("HOVER") both return "#C0D9F5"
PHASE_COLORS: dict[str, str] = {**_CATEGORY_COLORS}
for _m in ALL_MODES.values():
    PHASE_COLORS[_m.name] = _CATEGORY_COLORS.get(_m.power_category, "#DDDDDD")

# ── Phase types — power categories + all ArduPilot mode names ─────────────────
PHASE_TYPES: list[str] = POWER_CATEGORIES + sorted(
    n for n in ALL_MODES.keys() if n not in set(POWER_CATEGORIES)
)

# ── Mode descriptions (for tooltips in the Mission Builder) ──────────────────
PHASE_DESCRIPTIONS: dict[str, str] = {m.name: m.description for m in ALL_MODES.values()}

# ── Chemistry colours ─────────────────────────────────────────────────────────
CHEM_COLORS: dict[str, str] = {
    "LIPO":    "#2196F3",
    "LIHV":    "#03A9F4",
    "LION":    "#4CAF50",
    "LION21":  "#8BC34A",
    "LIFEPO4": "#FF9800",
    "LITO":    "#9C27B0",
    "SSS":     "#F44336",
    "SOLID":   "#795548",
    "NIMH":    "#607D8B",
}

# Status colour coding
STATUS_COLORS: dict[str, str] = {
    "PASS":     "#4CAF50",
    "MARGINAL": "#FF9800",
    "FAIL":     "#F44336",
}

ACCENT = "#1F3864"
