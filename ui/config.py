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

# ── Phase colours (hex) ───────────────────────────────────────────────────────
PHASE_COLORS: dict[str, str] = {
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
