"""
batteries/ecm_store.py
Flight-log ECM parameter registry — temperature-aware store for fitted ECMParameters.

Each registered entry records the ECM fit from one flight log at one temperature.
The registry supports interpolation between entries to supply ECMParameters at any
requested temperature, enabling accurate PRECISE-mode simulation across climates.
"""
from __future__ import annotations

import json
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from batteries.voltage_model import ECMParameters


_REGISTRY_DIR  = Path.home() / ".battsim"
_REGISTRY_FILE = _REGISTRY_DIR / "log_registry.json"
_TEMP_THRESHOLD = 15.0   # degrees C: interpolate within, extrapolate beyond


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class LogRegistryEntry:
    """One fitted ECM entry, derived from a single flight log."""
    entry_id:      str           # UUID4
    pack_id:       str
    log_filename:  str           # basename only -- never a full path
    fitted_at:     str           # ISO-8601 datetime string
    temperature_c: float         # mean pack temperature during the flight
    ecm_params:    ECMParameters
    fit_summary:   dict          # {"R0_mohm": ..., "R1_mohm": ..., "tau1_s": ..., ...}
    notes:         str = ""

    def to_dict(self) -> dict:
        return {
            "entry_id":      self.entry_id,
            "pack_id":       self.pack_id,
            "log_filename":  self.log_filename,
            "fitted_at":     self.fitted_at,
            "temperature_c": self.temperature_c,
            "ecm_params":    self.ecm_params.to_dict(),
            "fit_summary":   self.fit_summary,
            "notes":         self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "LogRegistryEntry":
        return LogRegistryEntry(
            entry_id=d["entry_id"],
            pack_id=d["pack_id"],
            log_filename=d["log_filename"],
            fitted_at=d["fitted_at"],
            temperature_c=float(d["temperature_c"]),
            ecm_params=ECMParameters.from_dict(d["ecm_params"]),
            fit_summary=d.get("fit_summary", {}),
            notes=d.get("notes", ""),
        )


# ── Registry ──────────────────────────────────────────────────────────────────

class LogRegistry:
    """
    JSON-backed store of LogRegistryEntry objects.

    Stored at ~/.battsim/log_registry.json -- human-readable, never stores
    raw log file content (only fitted parameters and summary statistics).
    """

    def __init__(self, path: Optional[Path] = None):
        self._path: Path = Path(path) if path else _REGISTRY_FILE
        self._entries: list[LogRegistryEntry] = []

    def load(self) -> "LogRegistry":
        """Load registry from disk. Returns self for chaining."""
        if not self._path.exists():
            return self
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = [
                LogRegistryEntry.from_dict(e)
                for e in data.get("entries", [])
            ]
        except Exception as exc:
            warnings.warn(
                f"Could not load log registry from {self._path}: {exc}",
                UserWarning, stacklevel=2,
            )
        return self

    def save(self) -> None:
        """Persist registry to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.to_dict() for e in self._entries]}
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add(self, entry: LogRegistryEntry) -> None:
        """Append an entry and save."""
        self._entries.append(entry)
        self.save()

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by UUID. Returns True if found and removed."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        if len(self._entries) < before:
            self.save()
            return True
        return False

    def entries_for_pack(self, pack_id: str) -> list[LogRegistryEntry]:
        """Return all entries for a given pack, unsorted."""
        return [e for e in self._entries if e.pack_id == pack_id]

    def all_entries(self) -> list[LogRegistryEntry]:
        """Return all entries sorted by fitted_at descending (newest first)."""
        return sorted(self._entries, key=lambda e: e.fitted_at, reverse=True)


# ── Temperature-aware ECM lookup ─────────────────────────────────────────────

def get_ecm_for_temperature(
    registry: LogRegistry,
    pack_id: str,
    temp_c: float,
    threshold_c: float = _TEMP_THRESHOLD,
) -> Optional[ECMParameters]:
    """
    Return an ECMParameters for pack_id at the requested temperature.

    Four cases (in priority order):
      1. >=2 entries within +-threshold_c of temp_c:
             interpolate between the two nearest entries by temperature.
      2. >=2 entries but none within threshold:
             extrapolate from the two nearest entries (warns).
      3. Exactly 1 entry:
             return it directly (warns if |entry.temp - temp_c| > threshold).
      4. 0 entries:
             return None.
    """
    entries = registry.entries_for_pack(pack_id)
    if not entries:
        return None

    if len(entries) == 1:
        e = entries[0]
        if abs(e.temperature_c - temp_c) > threshold_c:
            warnings.warn(
                f"Only one ECM entry for pack '{pack_id}' at "
                f"{e.temperature_c:.1f}C; requested {temp_c:.1f}C "
                f"(delta={abs(e.temperature_c - temp_c):.1f}C). "
                "Using single entry without interpolation.",
                UserWarning, stacklevel=2,
            )
        return e.ecm_params

    # Find entries within threshold
    within = [e for e in entries if abs(e.temperature_c - temp_c) <= threshold_c]

    if len(within) >= 2:
        # Interpolate between the two nearest within threshold
        within.sort(key=lambda e: abs(e.temperature_c - temp_c))
        e1, e2 = within[0], within[1]
    else:
        # Extrapolate using the two nearest overall
        all_sorted = sorted(entries, key=lambda e: abs(e.temperature_c - temp_c))
        e1, e2 = all_sorted[0], all_sorted[1]
        temp_range = [e.temperature_c for e in entries]
        warnings.warn(
            f"Requested temperature {temp_c:.1f}C is outside the fitted "
            f"range [{min(temp_range):.1f}, {max(temp_range):.1f}]C for "
            f"pack '{pack_id}'. Extrapolating ECM parameters -- accuracy "
            "may be reduced.",
            UserWarning, stacklevel=2,
        )

    # Sort so t1 <= t2 for consistent alpha direction
    if e1.temperature_c > e2.temperature_c:
        e1, e2 = e2, e1

    t1, t2 = e1.temperature_c, e2.temperature_c
    if t2 == t1:
        return e1.ecm_params

    alpha = (temp_c - t1) / (t2 - t1)   # may exceed [0,1] for extrapolation
    return _interpolate_ecm(e1.ecm_params, e2.ecm_params, alpha)


def get_ecm_with_info(
    registry: LogRegistry,
    pack_id: str,
    temp_c: float,
    threshold_c: float = _TEMP_THRESHOLD,
) -> tuple[Optional[ECMParameters], dict]:
    """
    Like get_ecm_for_temperature but also returns a dict describing the resolution.

    Returns (ecm_or_None, info) where info contains:
      "status":         "none" | "single" | "interpolated" | "extrapolated"
      "entries_used":   list of {"log_filename", "temperature_c", "fitted_at"} dicts
      "requested_temp": temp_c (float)
      "description":    human-readable string
    """
    entries = registry.entries_for_pack(pack_id)

    def _ei(e):
        return {
            "log_filename":  e.log_filename,
            "temperature_c": e.temperature_c,
            "fitted_at":     e.fitted_at[:10],
        }

    if not entries:
        return None, {
            "status":         "none",
            "entries_used":   [],
            "requested_temp": temp_c,
            "description":    "No registered log entries for this pack.",
        }

    if len(entries) == 1:
        e = entries[0]
        delta = abs(e.temperature_c - temp_c)
        if delta > threshold_c:
            desc = (
                f"Single entry at {e.temperature_c:.1f}C used "
                f"(requested {temp_c:.1f}C, delta={delta:.1f}C > threshold "
                f"{threshold_c:.0f}C). Accuracy may be reduced."
            )
        else:
            desc = (
                f"Single entry at {e.temperature_c:.1f}C used "
                f"(requested {temp_c:.1f}C, delta={delta:.1f}C)."
            )
        return e.ecm_params, {
            "status":         "single",
            "entries_used":   [_ei(e)],
            "requested_temp": temp_c,
            "description":    desc,
        }

    # Find entries within threshold
    within = [e for e in entries if abs(e.temperature_c - temp_c) <= threshold_c]

    if len(within) >= 2:
        within.sort(key=lambda e: abs(e.temperature_c - temp_c))
        e1, e2 = within[0], within[1]
        if e1.temperature_c > e2.temperature_c:
            e1, e2 = e2, e1
        t1, t2 = e1.temperature_c, e2.temperature_c
        alpha = (temp_c - t1) / (t2 - t1) if t2 != t1 else 0.5
        ecm = _interpolate_ecm(e1.ecm_params, e2.ecm_params, alpha)
        desc = (
            f"Interpolated between {t1:.1f}C ({e1.log_filename}) and "
            f"{t2:.1f}C ({e2.log_filename}) for requested {temp_c:.1f}C "
            f"(alpha={alpha:.2f})."
        )
        return ecm, {
            "status":         "interpolated",
            "entries_used":   [_ei(e1), _ei(e2)],
            "requested_temp": temp_c,
            "description":    desc,
        }
    else:
        # Extrapolate from two nearest
        all_sorted = sorted(entries, key=lambda e: abs(e.temperature_c - temp_c))
        e1, e2 = all_sorted[0], all_sorted[1]
        if e1.temperature_c > e2.temperature_c:
            e1, e2 = e2, e1
        t1, t2 = e1.temperature_c, e2.temperature_c
        alpha = (temp_c - t1) / (t2 - t1) if t2 != t1 else 0.5
        ecm = _interpolate_ecm(e1.ecm_params, e2.ecm_params, alpha)
        temp_range = sorted(e.temperature_c for e in entries)
        desc = (
            f"Extrapolated to {temp_c:.1f}C from fitted range "
            f"[{temp_range[0]:.1f}, {temp_range[-1]:.1f}]C using "
            f"{e1.log_filename} and {e2.log_filename}. "
            "Accuracy may be reduced outside fitted range."
        )
        return ecm, {
            "status":         "extrapolated",
            "entries_used":   [_ei(e1), _ei(e2)],
            "requested_temp": temp_c,
            "description":    desc,
        }


def _interpolate_ecm(
    a: ECMParameters,
    b: ECMParameters,
    alpha: float,
) -> ECMParameters:
    """
    Linearly interpolate two ECMParameters.
    alpha=0 returns a, alpha=1 returns b; values outside [0,1] extrapolate.
    """
    def lerp_table(ta, tb):
        if not ta or not tb or len(ta) != len(tb):
            return ta or tb
        return [
            [
                ta[i][j] * (1.0 - alpha) + tb[i][j] * alpha
                for j in range(len(ta[i]))
            ]
            for i in range(len(ta))
        ]

    return ECMParameters(
        soc_breakpoints=a.soc_breakpoints,
        temp_breakpoints=a.temp_breakpoints,
        R0_table=lerp_table(a.R0_table, b.R0_table),
        R1_table=lerp_table(a.R1_table, b.R1_table),
        C1_table=lerp_table(a.C1_table, b.C1_table),
        R2_table=lerp_table(a.R2_table, b.R2_table),
        C2_table=lerp_table(a.C2_table, b.C2_table),
    )


# ── Convenience factory ───────────────────────────────────────────────────────

def make_entry(
    pack_id: str,
    log_filename: str,
    temperature_c: float,
    ecm_params: ECMParameters,
    fit_summary: dict,
    notes: str = "",
) -> LogRegistryEntry:
    """Create a new LogRegistryEntry with a fresh UUID and current timestamp."""
    return LogRegistryEntry(
        entry_id=str(uuid.uuid4()),
        pack_id=pack_id,
        log_filename=log_filename,
        fitted_at=datetime.now(timezone.utc).isoformat(),
        temperature_c=temperature_c,
        ecm_params=ecm_params,
        fit_summary=fit_summary,
        notes=notes,
    )
