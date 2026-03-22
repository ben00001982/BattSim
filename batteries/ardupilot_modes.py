"""
batteries/ardupilot_modes.py

Single source of truth for ArduPilot flight mode definitions.
Zero imports from other batteries/ modules — imported by models, log_importer,
database, and ui/config; circular-import safety is mandatory.
"""
from __future__ import annotations
from dataclasses import dataclass


# ── Mode definition ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class APMode:
    """Immutable descriptor for one ArduPilot flight mode."""
    name:           str   # ArduPilot canonical mode name  ("LOITER")
    num:            int   # Numeric mode ID in firmware
    vehicle:        str   # "copter" | "plane"
    power_category: str   # Equipment.power_for_phase() key ("HOVER")
    description:    str = ""


# ── Power categories (Equipment power-attribute keys + legacy VTOL/FW) ────────

POWER_CATEGORIES: list[str] = [
    "IDLE", "TAKEOFF", "CLIMB", "CRUISE", "HOVER",
    "DESCEND", "LAND", "PAYLOAD_OPS", "EMERGENCY",
    # Fixed-wing VTOL legacy labels (still valid in mission profiles)
    "VTOL_TRANSITION", "VTOL_HOVER", "FW_CRUISE", "FW_CLIMB", "FW_DESCEND",
]

# ── ArduCopter modes ──────────────────────────────────────────────────────────

_COPTER_LIST: list[APMode] = [
    APMode("STABILIZE",    0,  "copter", "CRUISE",     "Manual stabilization"),
    APMode("ACRO",         1,  "copter", "CRUISE",     "Full manual / acrobatic"),
    APMode("ALT_HOLD",     2,  "copter", "HOVER",      "Altitude hold"),
    APMode("AUTO",         3,  "copter", "CRUISE",     "Autonomous waypoint flight"),
    APMode("GUIDED",       4,  "copter", "CRUISE",     "Guided by GCS or companion"),
    APMode("LOITER",       5,  "copter", "HOVER",      "Position & altitude hold"),
    APMode("RTL",          6,  "copter", "CRUISE",     "Return to launch"),
    APMode("CIRCLE",       7,  "copter", "HOVER",      "Circular loiter"),
    APMode("LAND",         9,  "copter", "LAND",       "Autonomous landing"),
    APMode("DRIFT",        11, "copter", "CRUISE",     "Drift / FPV mode"),
    APMode("SPORT",        13, "copter", "CRUISE",     "Velocity control"),
    APMode("AUTOTUNE",     14, "copter", "HOVER",      "PID autotuning hover"),
    APMode("POSHOLD",      15, "copter", "HOVER",      "Position hold with stick input"),
    APMode("BRAKE",        16, "copter", "HOVER",      "Immediate brake / stop"),
    APMode("THROW",        17, "copter", "TAKEOFF",    "Hand-throw launch"),
    APMode("AVOID_ADSB",   18, "copter", "CRUISE",     "ADS-B collision avoidance"),
    APMode("GUIDED_NOGPS", 19, "copter", "HOVER",      "Guided without GPS"),
    APMode("SMART_RTL",    20, "copter", "CRUISE",     "Smart return to launch"),
    APMode("FLOWHOLD",     21, "copter", "HOVER",      "Optical flow position hold"),
    APMode("FOLLOW",       22, "copter", "CRUISE",     "Follow a vehicle or target"),
    APMode("ZIGZAG",       23, "copter", "CRUISE",     "Survey zigzag pattern"),
    APMode("SYSTEMID",     24, "copter", "HOVER",      "System identification"),
    APMode("AUTOROTATE",   25, "copter", "DESCEND",    "Autorotation descent"),
]

# ── ArduPlane modes ───────────────────────────────────────────────────────────

_PLANE_LIST: list[APMode] = [
    APMode("MANUAL",         0,  "plane", "CRUISE",  "Full manual control"),
    APMode("CIRCLE_PLANE",   1,  "plane", "HOVER",   "Circle loiter (plane)"),
    APMode("STABILIZE",      2,  "plane", "CRUISE",  "Manual stabilization (plane)"),
    APMode("TRAINING",       3,  "plane", "CRUISE",  "Training / limited stabilise"),
    APMode("ACRO",           4,  "plane", "CRUISE",  "Acrobatic (plane)"),
    APMode("FLY_BY_WIRE_A",  5,  "plane", "CRUISE",  "FBWA — attitude stabilised"),
    APMode("FLY_BY_WIRE_B",  6,  "plane", "CRUISE",  "FBWB — speed/altitude hold"),
    APMode("AUTO",           10, "plane", "CRUISE",  "Autonomous mission (plane)"),
    APMode("RTL",            11, "plane", "CRUISE",  "Return to launch (plane)"),
    APMode("LOITER",         12, "plane", "HOVER",   "Loiter at altitude (plane)"),
    APMode("GUIDED",         15, "plane", "CRUISE",  "Guided by GCS (plane)"),
    APMode("TAKEOFF_PLANE",  17, "plane", "TAKEOFF", "Automatic takeoff (plane)"),
    APMode("QSTABILIZE",     19, "plane", "HOVER",   "VTOL stabilize"),
    APMode("QHOVER",         20, "plane", "HOVER",   "VTOL altitude hold"),
    APMode("QLOITER",        21, "plane", "HOVER",   "VTOL position hold"),
    APMode("QLAND",          22, "plane", "LAND",    "VTOL landing"),
    APMode("QRTL",           23, "plane", "CRUISE",  "VTOL return to launch"),
    APMode("QAUTOTUNE",      25, "plane", "HOVER",   "VTOL PID autotuning"),
    APMode("QACRO",          26, "plane", "CRUISE",  "VTOL acrobatic"),
]


# ── Lookup structures ─────────────────────────────────────────────────────────

COPTER_MODES: dict[int, APMode] = {m.num: m for m in _COPTER_LIST}
PLANE_MODES:  dict[int, APMode] = {m.num: m for m in _PLANE_LIST}

# Name → APMode (plane entries overwrite copter for shared names;
# power_category is identical for all shared names so ordering is safe)
ALL_MODES: dict[str, APMode] = {
    m.name: m for m in _COPTER_LIST + _PLANE_LIST
}

# Mode name → power category (fast O(1) lookup)
MODE_TO_CATEGORY: dict[str, str] = {
    m.name: m.power_category for m in _COPTER_LIST + _PLANE_LIST
}

# Full set of strings accepted as phase_type values
ALL_VALID_PHASE_TYPES: set[str] = set(POWER_CATEGORIES) | set(ALL_MODES.keys())


# ── Helper functions ──────────────────────────────────────────────────────────

def mode_name_to_category(mode_name: str) -> str:
    """
    Return the power category for a mode name or category string.

    - If mode_name is already a POWER_CATEGORY (e.g. "HOVER"), return it.
    - If mode_name is a known ArduPilot mode (e.g. "LOITER"), return its category.
    - Otherwise return "CRUISE" as a safe fallback.
    """
    upper = mode_name.upper()
    if upper in POWER_CATEGORIES:
        return upper
    m = ALL_MODES.get(upper)
    return m.power_category if m else "CRUISE"


def copter_num_to_name(num: int) -> str:
    """Copter flight mode number → mode name string (e.g. 5 → 'LOITER')."""
    m = COPTER_MODES.get(num)
    return m.name if m else "UNKNOWN"


def plane_num_to_name(num: int) -> str:
    """Plane flight mode number → mode name string (e.g. 22 → 'QLAND')."""
    m = PLANE_MODES.get(num)
    return m.name if m else "UNKNOWN"


def modes_by_vehicle(vehicle: str) -> list[APMode]:
    """Return all modes for the given vehicle type ('copter' or 'plane')."""
    return [m for m in _COPTER_LIST + _PLANE_LIST if m.vehicle == vehicle]


def modes_by_category(category: str) -> list[APMode]:
    """Return all modes whose power_category matches the given category."""
    return [m for m in ALL_MODES.values() if m.power_category == category]
