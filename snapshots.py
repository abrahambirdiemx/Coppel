"""
Manages snapshot storage for the dashboard.

Snapshots are written to data/snapshots.json each time the sheet is refreshed.
The file is committed to git so it survives Render redeploys — each deploy
starts with at least the last manually committed baseline.

Up to MAX_SNAPSHOTS are kept (oldest removed first).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

MAX_SNAPSHOTS = 100
DATA_DIR = Path(__file__).parent / "data"
SNAP_FILE = DATA_DIR / "snapshots.json"

# In-memory cache so snapshots survive across requests within the same process.
# Loaded once on first access, then kept in sync with disk.
_cache: list[dict] | None = None


def _ensure_dir():
    DATA_DIR.mkdir(exist_ok=True)


def load_snapshots() -> list[dict]:
    """Return all stored snapshots, newest first."""
    global _cache
    if _cache is not None:
        return _cache
    _ensure_dir()
    if SNAP_FILE.exists():
        try:
            _cache = json.loads(SNAP_FILE.read_text(encoding="utf-8"))
            return _cache
        except Exception:
            pass
    _cache = []
    return _cache


def _persist(snaps: list[dict]):
    """Write to disk and update in-memory cache."""
    global _cache
    _cache = snaps
    _ensure_dir()
    try:
        SNAP_FILE.write_text(
            json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass  # Non-fatal on ephemeral storage


def save_snapshot(processed: dict) -> dict:
    """
    Extract key metrics from a processed payload, store as snapshot, and return it.
    Deduplicates by timestamp (second precision).
    """
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

    snaps = [snap] + snaps
    snaps = snaps[:MAX_SNAPSHOTS]
    _persist(snaps)
    return snap
