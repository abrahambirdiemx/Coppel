"""
Manages snapshot storage for the dashboard.

Snapshots are written to data/snapshots.json each time the sheet is refreshed.
Up to MAX_SNAPSHOTS are kept (oldest removed first).

NOTE: Render free tier has ephemeral disk — snapshots persist while the service
      is running but are reset on each new deploy.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

MAX_SNAPSHOTS = 100
DATA_DIR = Path(__file__).parent / "data"
SNAP_FILE = DATA_DIR / "snapshots.json"


def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_snapshots() -> list[dict]:
    """Return all stored snapshots, newest first."""
    _ensure_dir()
    if not SNAP_FILE.exists():
        return []
    try:
        return json.loads(SNAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_snapshot(processed: dict) -> dict:
    """
    Extract key metrics from a processed payload and store as a snapshot.
    Returns the new snapshot dict.
    """
    _ensure_dir()
    s = processed.get("summary", {})
    ep = processed.get("eta_prediction", {})
    wt = processed.get("weekly_trend", [])
    snap = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "label": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "total": s.get("total", 0),
        "sailing": s.get("sailing", 0),
        "discharged": s.get("discharged", 0),
        "arrived": s.get("arrived", 0),
        "atd_pct": s.get("atd_pct", 0),
        "atd_within1": s.get("atd_within1", 0),
        "ata_pct": s.get("ata_pct", 0),
        "ata_within1": s.get("ata_within1", 0),
        "eta_pct_w1": ep.get("pct_w1", 0),
        "eta_n": ep.get("n", 0),
        "weeks_count": len(wt),
    }

    snaps = load_snapshots()
    # Avoid duplicates if reloaded within the same second
    if snaps and snaps[0].get("timestamp") == snap["timestamp"]:
        return snaps[0]

    snaps.insert(0, snap)
    snaps = snaps[:MAX_SNAPSHOTS]

    try:
        SNAP_FILE.write_text(json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass  # Non-fatal — ephemeral storage may not allow writes

    return snap
