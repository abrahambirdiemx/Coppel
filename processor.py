"""
Transforms raw Google Sheets rows into the metrics dict consumed by the dashboard.

Sheet columns (hoja ag-grid) — order as received from Google Sheets API:
  A  Contenedor
  B  Puerto origen
  C  Puerto arribo Birdie
  D  Línea de entrega
  E  ATD Birdie
  F  ATD Coppel
  G  Diferencia          ← ATD Birdie − ATD Coppel (pre-computed in sheet)
  H  ATA Birdie
  I  ATA/ETA Coppel      ← "column 8" referenced by user (1-indexed = col I)
  J  ETA Birdie          ← column J referenced by user
  K  Diferencia.1        ← ATA Birdie − ATA/ETA Coppel (pre-computed in sheet)
  L  Status de solicitud
  M  Comentarios Coppel

ETA PREDICTIVO: computed here as (ETA Birdie) − (ATA/ETA Coppel) in days.
  → NOT Diferencia.1, which measures ATA Birdie vs ATA/ETA Coppel.
"""

from collections import Counter, defaultdict
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_FMTS = ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y")


def _parse_date(val: str):
    """Try common date formats; return datetime or None."""
    v = str(val).strip()
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def _date_diff(a: str, b: str) -> int | None:
    """Return (date_a - date_b).days or None if either is unparseable."""
    da, db = _parse_date(a), _parse_date(b)
    if da is None or db is None:
        return None
    return (da - db).days


def _int(val: str) -> int | None:
    """Parse integer from a sheet cell; returns None if empty/invalid."""
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return None


def _has_value(val: str) -> bool:
    return bool(val and str(val).strip())


def _pct(count: int, total: int) -> float:
    return round(count / total * 100, 1) if total else 0.0


def _mean(values: list[int | float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


# ---------------------------------------------------------------------------
# Per-group ATD/ATA breakdown builder
# ---------------------------------------------------------------------------

def _group_accuracy(
    rows: list[dict],
    group_key: str,
    diff_col: str,
    min_n: int = 2,
) -> list[dict]:
    """Compute exact / within-1 / mean-diff per group for a given diff column."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        name = r.get(group_key, "").strip()
        d = _int(r.get(diff_col, ""))
        if not name or d is None:
            continue
        buckets[name].append(d)

    result = []
    for name, diffs in buckets.items():
        n = len(diffs)
        if n < min_n:
            continue
        exact = sum(1 for d in diffs if d == 0)
        w1 = sum(1 for d in diffs if abs(d) <= 1)
        result.append(
            {
                "name": name,
                "n": n,
                "pct_exact": _pct(exact, n),
                "pct_w1": _pct(w1, n),
                "mean_diff": _mean(diffs),
            }
        )
    result.sort(key=lambda x: -x["pct_exact"])
    return result


def _atd_group(rows: list[dict], group_key: str, min_n: int = 2) -> list[dict]:
    """ATD-style single-metric breakdown (pct = exact)."""
    raw = _group_accuracy(rows, group_key, "Diferencia", min_n)
    return [
        {"name": r["name"], "n": r["n"], "pct": r["pct_exact"], "mean_diff": r["mean_diff"]}
        for r in raw
    ]


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

def process(rows: list[dict]) -> dict:
    total = len(rows)

    # --- ATD rows (both ATD dates present = Diferencia is a number) ----------
    atd_rows = [r for r in rows if _int(r.get("Diferencia", "")) is not None]
    atd_diffs = [_int(r["Diferencia"]) for r in atd_rows]

    atd_exact = sum(1 for d in atd_diffs if d == 0)
    atd_w1 = sum(1 for d in atd_diffs if abs(d) <= 1)
    atd_total = len(atd_diffs)

    # --- ATA rows (Diferencia.1 is a number) ----------------------------------
    ata_rows = [r for r in rows if _int(r.get("Diferencia.1", "")) is not None]
    ata_diffs = [_int(r["Diferencia.1"]) for r in ata_rows]

    ata_exact = sum(1 for d in ata_diffs if d == 0)
    ata_w1 = sum(1 for d in ata_diffs if abs(d) <= 1)
    ata_total = len(ata_diffs)

    # --- Status counts --------------------------------------------------------
    status_counts = Counter(r.get("Status de solicitud", "").strip() for r in rows)

    # --- ATD distribution -----------------------------------------------------
    atd_dist_counter: Counter = Counter(atd_diffs)
    atd_dist = [
        {"diff": k, "count": v}
        for k, v in sorted(atd_dist_counter.items())
    ]

    # --- ATA distribution (exclude ETA-only rows = Sailing) -------------------
    ata_actual_rows = [
        r for r in ata_rows
        if r.get("Status de solicitud", "").strip() in ("Discharged", "Arrived")
    ]
    ata_actual_diffs = [_int(r["Diferencia.1"]) for r in ata_actual_rows]
    ata_dist_counter: Counter = Counter(ata_actual_diffs)
    ata_dist = [
        {"diff": k, "count": v}
        for k, v in sorted(ata_dist_counter.items())
    ]

    # --- ATA navieras ---------------------------------------------------------
    ata_navieras = _group_accuracy(ata_rows, "Línea de entrega", "Diferencia.1")

    # --- ATA PODs (Puerto arribo Birdie) --------------------------------------
    ata_pods = _group_accuracy(ata_rows, "Puerto arribo Birdie", "Diferencia.1")

    # --- ATD navieras ---------------------------------------------------------
    navieras = _atd_group(atd_rows, "Línea de entrega", min_n=1)

    # --- ATD puertos (top 12 by volume) ---------------------------------------
    puertos_raw = _atd_group(atd_rows, "Puerto origen", min_n=1)
    # Sort by n desc, take top 12
    puertos = sorted(puertos_raw, key=lambda x: -x["n"])[:12]

    # --- ETA prediction (Discharged rows: ETA Birdie col J vs ATA/ETA Coppel col I) ---
    # Compute the date difference directly — NOT Diferencia.1 (which is ATA Birdie vs ATA Coppel).
    discharged = []
    for r in rows:
        if r.get("Status de solicitud", "").strip() != "Discharged":
            continue
        eta = r.get("ETA Birdie", "").strip()
        ata_coppel = r.get("ATA/ETA Coppel", "").strip()
        if not eta or not ata_coppel:
            continue
        diff = _date_diff(eta, ata_coppel)
        if diff is None:
            continue
        discharged.append({"row": r, "eta_diff": diff})

    eta_diffs = [d["eta_diff"] for d in discharged]
    eta_n = len(eta_diffs)
    eta_exact = sum(1 for d in eta_diffs if d == 0)
    eta_w1 = sum(1 for d in eta_diffs if abs(d) <= 1)
    eta_w3 = sum(1 for d in eta_diffs if abs(d) <= 3)
    eta_dist_counter: Counter = Counter(eta_diffs)
    eta_dist = [
        {"diff": k, "count": v}
        for k, v in sorted(eta_dist_counter.items())
    ]

    # --- Comment groups -------------------------------------------------------
    comment_counter: Counter = Counter()
    for r in rows:
        c = r.get("Comentarios Coppel", "").strip()
        if c:
            comment_counter[c] += 1
    comment_groups = [
        {"label": label, "count": cnt}
        for label, cnt in comment_counter.most_common(10)
    ]

    # --- Missing SO (Línea de entrega empty) ----------------------------------
    missing_so = sum(1 for r in rows if not _has_value(r.get("Línea de entrega", "")))

    # --- Duplicates (Contenedor appearing more than once) ---------------------
    cntr_counts = Counter(r.get("Contenedor", "").strip() for r in rows if _has_value(r.get("Contenedor", "")))
    duplicates = sum(1 for v in cntr_counts.values() if v > 1)

    # --- Table (all rows, raw) ------------------------------------------------
    table_cols = [
        "Contenedor", "Puerto origen", "Puerto arribo Birdie",
        "Línea de entrega", "ATD Birdie", "ATD Coppel", "Diferencia",
        "ATA Birdie", "ATA/ETA Coppel", "Diferencia.1", "ETA Birdie",
        "Status de solicitud", "Comentarios Coppel",
    ]
    table = [
        {col: r.get(col, "") for col in table_cols}
        for r in rows
    ]

    return {
        "summary": {
            "total": total,
            "sailing": status_counts.get("Sailing", 0),
            "discharged": status_counts.get("Discharged", 0),
            "arrived": status_counts.get("Arrived", 0),
            "atd_exact": atd_exact,
            "atd_total": atd_total,
            "atd_pct": _pct(atd_exact, atd_total),
            "atd_within1": _pct(atd_w1, atd_total),
            "atd_mean_diff": _mean(atd_diffs),
            "atd_discrepancies": atd_total - atd_exact,
            "ata_exact": ata_exact,
            "ata_total": ata_total,
            "ata_pct": _pct(ata_exact, ata_total),
            "ata_within1": _pct(ata_w1, ata_total),
            "ata_mean_diff": _mean(ata_diffs),
            "missing_so": missing_so,
            "duplicates": duplicates,
        },
        "atd_dist": atd_dist,
        "ata_dist": ata_dist,
        "ata_navieras": ata_navieras,
        "ata_pods": ata_pods,
        "eta_prediction": {
            "n": eta_n,
            "exact": eta_exact,
            "pct_exact": _pct(eta_exact, eta_n),
            "pct_w1": _pct(eta_w1, eta_n),
            "pct_w3": _pct(eta_w3, eta_n),
            "mean_diff": _mean(eta_diffs),
            "dist": eta_dist,
        },
        "navieras": navieras,
        "puertos": puertos,
        "comment_groups": comment_groups,
        "table": table,
    }
