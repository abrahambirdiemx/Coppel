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
        "version": "2026-04-24-snapshots",
        "features": ["weekly_trend", "wow_badges", "snapshots", "column_fix_puerto_arribo"],
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
        return {
            "status": "ok",
            "code_version": "f85b90d",
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "service_account_file": sa_file,
            "service_account_exists": sa_exists,
            "rows_found": len(rows),
            "first_row_keys": list(rows[0].keys()) if rows else [],
        }
    except Exception as exc:
        return {
            "status": "error",
            "code_version": "f85b90d",
            "sheet_id": sheet_id,
            "sheet_name": sheet_name,
            "service_account_file": sa_file,
            "service_account_exists": sa_exists,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
