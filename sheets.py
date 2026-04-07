import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_ID", "")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "ag-grid")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")


def get_sheet_rows() -> list[dict]:
    """Fetch all rows from the configured Google Sheet as a list of dicts."""
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build("sheets", "v4", credentials=creds)
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range=SHEET_NAME)
        .execute()
    )
    values = result.get("values", [])
    if len(values) < 2:
        return []

    headers = values[0]
    rows = []
    for raw_row in values[1:]:
        padded = raw_row + [""] * (len(headers) - len(raw_row))
        rows.append(dict(zip(headers, padded)))
    return rows
