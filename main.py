import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from sheets import get_sheet_rows
from processor import process
from snapshots import save_snapshot, load_snapshots

app = FastAPI(title="Birdie Tracking Accuracy API")

# ---------------------------------------------------------------------------
# Static files (frontend)
# ---------------------------------------------------------------------------
FRONTEND_DIR = Path(__file__).parent / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", include_in_schema=False)
def root():
    # no-cache forces browser to always fetch fresh HTML/JS
    content = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/data")
def get_data():
    """
    Reads the Google Sheet, processes all accuracy metrics, and returns
    the full payload consumed by the dashboard frontend.
    """
    try:
        rows = get_sheet_rows()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google Sheets error: {exc}")

    if not rows:
        raise HTTPException(status_code=404, detail="No data found in sheet.")

    result = process(rows)
    save_snapshot(result)
    return result


@app.post("/api/data/reload")
def reload_data():
    """
    Same as GET /api/data — exists as a POST so the dashboard's 'Cargar datos'
    button can trigger a server-side refresh without touching the sheet URL.
    """
    return get_data()


@app.get("/api/snapshots")
def get_snapshots():
    """Returns stored accuracy snapshots, newest first."""
    return {"snapshots": load_snapshots()}


@app.get("/api/version")
def version():
    """Quick check — confirms deployed commit and feature flags."""
    return {
        "version": "2026-04-24-v2",
        "features": ["weekly_trend", "wow_badges", "snapshots", "column_fix_new_sheet"],
    }


@app.get("/api/debug")
def debug():
    """Returns connection config, row count, and version — use to diagnose Sheets issues."""
    import os
    sheet_id = os.getenv("GOOGLE_SHEETS_ID", "NOT SET")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "ag-grid")
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
    sa_exists = Path(sa_file).exists()
    try:
        rows = get_sheet_rows()
        real = [r for r in rows if r.get("Contenedor","").strip()]

        def filled(rows, col):
            return sum(1 for r in rows if r.get(col,"").strip())

        # Show first real row
        sample = next((r for r in real), {})

        # Count how many rows have each key column filled
        col_fill = {
            "ATD":            filled(real, "ATD"),
            "ATD Birdie":     filled(real, "ATD Birdie"),
            "NETD Coppel":    filled(real, "NETD Coppel"),
            "ATD Coppel":     filled(real, "ATD Coppel"),
            "Diferencia":     filled(real, "Diferencia"),
            "ATA":            filled(real, "ATA"),
            "ATA Birdie":     filled(real, "ATA Birdie"),
            "ATA/ETA Coppel": filled(real, "ATA/ETA Coppel"),
            "Diferencia.1":   filled(real, "Diferencia.1"),
            "Status de solicitud": filled(real, "Status de solicitud"),
        }
        status_dist = {}
        for r in real:
            s = r.get("Status de solicitud","").strip()
            status_dist[s] = status_dist.get(s, 0) + 1

        return {
            "status": "ok",
            "code_version": "fix-metrics-v1",
            "rows_found": len(rows),
            "real_rows": len(real),
            "col_filled_count": col_fill,
            "status_distribution": status_dist,
            "first_real_row_keys": list(sample.keys()),
            "first_real_row_sample": {k: sample.get(k,"") for k in list(sample.keys())[:10]},
        }
    except Exception as exc:
        return {
            "status": "error",
            "code_version": "f79a308",
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "service_account_file": sa_file,
            "service_account_exists": sa_exists,
            "error": str(exc),
        }


@app.get("/api/debug/diffs")
def debug_diffs():
    """Muestra diffs computados para diagnosticar mapeo de columnas."""
    from processor import (
        _atd_diff, _ata_diff, _atd_birdie_val, _atd_coppel_val,
        _ata_birdie_val, _ata_coppel_val, _status, _has_value,
    )
    try:
        rows = get_sheet_rows()
        real = [r for r in rows if r.get("Contenedor", "").strip()]
        atd_valid = sum(1 for r in real if _atd_diff(r) is not None)
        ata_valid = sum(1 for r in real if _ata_diff(r) is not None)
        sample = []
        for r in real[:20]:
            sample.append({
                "contenedor": r.get("Contenedor", ""),
                "status": _status(r),
                "atd_birdie": _atd_birdie_val(r),
                "atd_coppel": _atd_coppel_val(r),
                "atd_diff": _atd_diff(r),
                "ata_birdie": _ata_birdie_val(r),
                "ata_coppel": _ata_coppel_val(r),
                "ata_diff": _ata_diff(r),
            })
        return {
            "atd_valid_rows": atd_valid,
            "ata_valid_rows": ata_valid,
            "total_real_rows": len(real),
            "sample": sample,
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
