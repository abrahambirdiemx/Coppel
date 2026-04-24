"""
Manages snapshot storage for the dashboard.

Snapshots are written to data/snapshots.json. The file is committed to git
so it survives Render redeploys. A hardcoded BASELINE is always the last
entry so there is always a comparison point.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

MAX_SNAPSHOTS = 100
DATA_DIR = Path(__file__).parent / "data"
SNAP_FILE = DATA_DIR / "snapshots.json"

# Always-available baseline (Excel 17/04/2026).
# Stays at the bottom of the list so every new load has something to compare.
_BASELINE = {
    "timestamp":   "2026-04-17T00:00:00",
    "label":       "17/04/2026 — Baseline Excel (990 contenedores)",
    "total":       990,
    "sailing":     347,
    "discharged":  418,
    "arrived":     26,
    "atd_pct":     93.0,
    "atd_within1": 98.0,
    "ata_pct":     74.8,
    "ata_within1": 95.7,
    "eta_pct_w1":  96.4,
    "eta_n":       418,
    "weeks_count": 6,
}

# In-memory cache — survives across requests within the same process.
_cache: list | None = None


def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_snapshots() -> list:
    """Return all stored snapshots, newest first. Always includes baseline."""
    global _cache
    if _cache is not None:
        return _cache

    snaps: list = []
    _ensure_dir()
    if SNAP_FILE.exists():
        try:
            snaps = json.loads(SNAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            snaps = []

    # Ensure baseline is always last entry (don't duplicate it)
    has_baseline = any(s.get("timestamp") == _BASELINE["timestamp"] for s in snaps)
    if not has_baseline:
        snaps.append(_BASELINE)

    _cache = snaps
    return _cache


def _persist(snaps: list):
    global _cache
    _cache = snaps
    _ensure_dir()
    try:
        SNAP_FILE.write_text(
            json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass  # non-fatal — in-memory cache still works


def save_snapshot(processed: dict) -> dict:
    """Build a snapshot from a processed payload, prepend it, and persist."""
    s  = processed.get("summary", {})
    ep = processed.get("eta_prediction", {})
    wt = processed.get("weekly_trend", [])

    now = datetime.now()
    snap = {
        "timestamp":   now.isoformat(timespec="seconds"),
        "label":       now.strftime("%d/%m/%Y %H:%M"),
        "total":       s.get("total", 0),
        "sailing":     s.get("sailing", 0),
        "discharged":  s.get("discharged", 0),
        "arrived":     s.get("arrived", 0),
        "atd_pct":     s.get("atd_pct", 0),
        "atd_within1": s.get("atd_within1", 0),
        "ata_pct":     s.get("ata_pct", 0),
        "ata_within1": s.get("ata_within1", 0),
        "eta_pct_w1":  ep.get("pct_w1", 0),
        "eta_n":       ep.get("n", 0),
        "weeks_count": len(wt),
    }

    snaps = load_snapshots()

    # Skip exact duplicate (same second)
    if snaps and snaps[0].get("timestamp") == snap["timestamp"]:
        return snaps[0]

    # Insert before baseline (keep baseline always last)
    baseline_idx = next(
        (i for i, s in enumerate(snaps) if s.get("timestamp") == _BASELINE["timestamp"]),
        len(snaps),
    )
    snaps = [snap] + snaps[:baseline_idx] + snaps[baseline_idx:]
    snaps = snaps[:MAX_SNAPSHOTS]
    _persist(snaps)
    return snap
