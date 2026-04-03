#!/usr/bin/env python3
"""Google Sheets helper for work hours tracking."""

import sys
import json
import calendar
from pathlib import Path
from typing import Optional
from datetime import date, timedelta

import gspread
from google.oauth2.service_account import Credentials


def hex_to_rgb(hex_color: str) -> dict:
    """Convert #RRGGBB to a Sheets API color dict (values 0.0–1.0)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


def tint(color: dict, factor: float = 0.35) -> dict:
    """Blend a color toward white by factor (0=original, 1=white)."""
    return {k: v + (1.0 - v) * factor for k, v in color.items()}


def is_dark_text_needed(color: dict) -> bool:
    """Return True if dark text is more readable on this background."""
    luminance = 0.299 * color["red"] + 0.587 * color["green"] + 0.114 * color["blue"]
    return luminance > 0.5

CONFIG_PATH = Path(__file__).parent / "config.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"Config not found at {CONFIG_PATH}. Copy config.json.example there and edit it.", file=sys.stderr)
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_client(config: dict) -> gspread.Client:
    creds_path = Path(config["credentials_path"]).expanduser()
    if not creds_path.is_absolute():
        creds_path = CONFIG_PATH.parent / creds_path
    if not creds_path.exists():
        print(f"Credentials file not found: {creds_path}", file=sys.stderr)
        sys.exit(1)
    creds = Credentials.from_service_account_file(str(creds_path), scopes=SCOPES)
    return gspread.authorize(creds)


def month_tab_name(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def month_days(year: int, month: int):
    """Yield each date in the given month."""
    _, num_days = calendar.monthrange(year, month)
    for day in range(1, num_days + 1):
        yield date(year, month, day)


def make_diff_formula(row: int) -> str:
    return f'=IF(C{row}="", "", C{row}-D{row})'


def make_saldo_formula(
    row: int,
    is_first_row_of_tab: bool,
    is_january: bool,
    prev_tab_name: Optional[str],
    prev_tab_last_row: Optional[int],
) -> str:
    if is_first_row_of_tab:
        if is_january:
            return f'=IF(C{row}="", "", E{row})'
        else:
            return (
                f'=IF(C{row}="", '
                f"'{prev_tab_name}'!F{prev_tab_last_row}, "
                f"'{prev_tab_name}'!F{prev_tab_last_row}+E{row})"
            )
    else:
        prev = row - 1
        return (
            f'=IF(C{row}="", '
            f'IF(F{prev}="", "", F{prev}), '
            f"F{prev}+E{row})"
        )


def format_worksheet(spreadsheet, ws, year: int, month: int, config: dict) -> None:
    sheet_id = ws.id
    _, num_days = calendar.monthrange(year, month)
    last_data_row = num_days + 1  # 1-indexed, includes header offset

    # Theme color from config (default: dark navy)
    theme_hex = config.get("theme_color", "#1e3a5f")
    COLOR_HEADER      = hex_to_rgb(theme_hex)
    COLOR_SUMMARY_HDR = tint(COLOR_HEADER, 0.25)
    COLOR_SUMMARY_VAL = tint(COLOR_HEADER, 0.75)
    COLOR_HEADER_TEXT = {"red": 0.1, "green": 0.1, "blue": 0.1} if is_dark_text_needed(COLOR_HEADER) else {"red": 1.0, "green": 1.0, "blue": 1.0}
    COLOR_WEEKEND      = {"red": 0.925, "green": 0.925, "blue": 0.925}
    COLOR_POSITIVE     = {"red": 0.851, "green": 0.918, "blue": 0.827}
    COLOR_NEGATIVE     = {"red": 0.988, "green": 0.910, "blue": 0.910}

    def cell_fmt(row_start, row_end, col_start, col_end, fmt):
        return {"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": row_start, "endRowIndex": row_end,
                      "startColumnIndex": col_start, "endColumnIndex": col_end},
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(" + ",".join(fmt.keys()) + ")",
        }}

    def cond_fmt(col_idx, condition_type, value, bg_color):
        return {"addConditionalFormatRule": {"rule": {
            "ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": last_data_row,
                        "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1}],
            "booleanRule": {
                "condition": {"type": condition_type, "values": [{"userEnteredValue": value}]},
                "format": {"backgroundColor": bg_color},
            },
        }, "index": 0}}

    def col_width(col_idx, pixels):
        return {"updateDimensionProperties": {
            "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                      "startIndex": col_idx, "endIndex": col_idx + 1},
            "properties": {"pixelSize": pixels},
            "fields": "pixelSize",
        }}

    number_fmt = {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}}

    requests = [
        # Freeze header row
        {"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount",
        }},

        # Main header row (A1:F1)
        cell_fmt(0, 1, 0, 6, {
            "backgroundColor": COLOR_HEADER,
            "textFormat": {"bold": True, "foregroundColor": COLOR_HEADER_TEXT, "fontSize": 10},
            "horizontalAlignment": "CENTER",
        }),

        # Summary header row (H1:J1)
        cell_fmt(0, 1, 7, 10, {
            "backgroundColor": COLOR_SUMMARY_HDR,
            "textFormat": {"bold": True, "foregroundColor": COLOR_HEADER_TEXT, "fontSize": 10},
            "horizontalAlignment": "CENTER",
        }),

        # Summary values row (H2:J2)
        cell_fmt(1, 2, 7, 10, {
            "backgroundColor": COLOR_SUMMARY_VAL,
            "textFormat": {"bold": True, "fontSize": 11},
            "horizontalAlignment": "CENTER",
            **number_fmt,
        }),

        # Number format for Hours Worked, Daily Diff, Cumulative Saldo (C, E, F)
        cell_fmt(1, last_data_row, 2, 3, number_fmt),
        cell_fmt(1, last_data_row, 4, 5, number_fmt),
        cell_fmt(1, last_data_row, 5, 6, number_fmt),

        # Conditional formatting: green/red for Daily Diff (E=4), Cumul Saldo (F=5), Month Saldo (I=8), Cumul (J=9)
        *[cond_fmt(col, "NUMBER_GREATER", "0", COLOR_POSITIVE) for col in [4, 5, 8, 9]],
        *[cond_fmt(col, "NUMBER_LESS",    "0", COLOR_NEGATIVE) for col in [4, 5, 8, 9]],

        # Column widths
        col_width(0, 100),  # A Date
        col_width(1, 95),   # B Weekday
        col_width(2, 105),  # C Hours Worked
        col_width(3, 105),  # D Target Hours
        col_width(4, 90),   # E Daily Diff
        col_width(5, 125),  # F Cumulative Saldo
        col_width(6, 24),   # G spacer
        col_width(7, 110),  # H Month Hours
        col_width(8, 110),  # I Month Saldo
        col_width(9, 125),  # J Cumulative Saldo
    ]

    # Weekend row backgrounds
    for day_date in month_days(year, month):
        if day_date.weekday() >= 5:
            row = day_date.day + 1  # +1 for header
            requests.append(cell_fmt(row - 1, row, 0, 6, {"backgroundColor": COLOR_WEEKEND}))

    spreadsheet.batch_update({"requests": requests})


def ensure_worksheet(spreadsheet, tab_name: str) -> gspread.Worksheet:
    """Get worksheet by name, creating it if it doesn't exist."""
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=tab_name, rows=35, cols=10)


def bootstrap_month(spreadsheet, year: int, month: int, config: dict) -> None:
    tab_name = month_tab_name(year, month)
    ws = ensure_worksheet(spreadsheet, tab_name)

    # Determine previous month info for carry-over formula
    if month == 1:
        prev_tab_name = None
        prev_tab_last_row = None
    else:
        prev_month = month - 1
        prev_tab_name = month_tab_name(year, prev_month)
        _, prev_month_days = calendar.monthrange(year, prev_month)
        prev_tab_last_row = prev_month_days + 1  # +1 for header row

    _, num_days = calendar.monthrange(year, month)
    last_data_row = num_days + 1  # last day row index (1-indexed, +1 for header)

    headers = ["Date", "Weekday", "Hours Worked", "Target Hours", "Daily Diff", "Cumulative Saldo",
               "", "Month Hours", "Month Saldo", "Cumulative Saldo"]
    cells = [gspread.Cell(1, col + 1, val) for col, val in enumerate(headers)]

    # Summary cells in columns H/I/J (8/9/10), row 2
    cells.append(gspread.Cell(2, 8,  f"=SUM(C2:C{last_data_row})"))
    cells.append(gspread.Cell(2, 9,  f"=SUM(E2:E{last_data_row})"))
    cells.append(gspread.Cell(2, 10, f"=F{last_data_row}"))

    target_weekday = config.get("target_hours_weekday", 7.5)
    target_weekend = config.get("target_hours_weekend", 0)

    for row_idx, day_date in enumerate(month_days(year, month), start=2):
        is_weekend = day_date.weekday() >= 5
        target = target_weekend if is_weekend else target_weekday

        cells.append(gspread.Cell(row_idx, 1, str(day_date)))
        cells.append(gspread.Cell(row_idx, 2, day_date.strftime("%A")))
        # Column 3 (Hours Worked) left empty intentionally
        cells.append(gspread.Cell(row_idx, 4, target))
        cells.append(gspread.Cell(row_idx, 5, make_diff_formula(row_idx)))
        cells.append(gspread.Cell(
            row_idx, 6,
            make_saldo_formula(
                row=row_idx,
                is_first_row_of_tab=(row_idx == 2),
                is_january=(month == 1),
                prev_tab_name=prev_tab_name,
                prev_tab_last_row=prev_tab_last_row,
            )
        ))

    ws.update_cells(cells, value_input_option="USER_ENTERED")
    format_worksheet(spreadsheet, ws, year, month, config)
    print(f"  Bootstrapped tab: {tab_name}")


def cmd_bootstrap(config: dict, client: gspread.Client) -> None:
    year = date.today().year

    if config.get("spreadsheet_id"):
        try:
            spreadsheet = client.open_by_key(config["spreadsheet_id"])
            print(f"Using existing spreadsheet: {spreadsheet.url}")
        except gspread.SpreadsheetNotFound:
            print("Spreadsheet ID in config not found. Creating new one...", file=sys.stderr)
            spreadsheet = client.create(f"Working Hours {year}")
            config["spreadsheet_id"] = spreadsheet.id
            save_config(config)
    else:
        spreadsheet = client.create(f"Working Hours {year}")
        config["spreadsheet_id"] = spreadsheet.id
        save_config(config)
        print(f"Created new spreadsheet: {spreadsheet.url}")

    # Set locale to en_US so formula separators are always commas
    spreadsheet.batch_update({"requests": [{"updateSpreadsheetProperties": {
        "properties": {"locale": "en_US"},
        "fields": "locale",
    }}]})

    # Delete default "Sheet1" if it exists and we're creating tabs
    existing_tabs = [ws.title for ws in spreadsheet.worksheets()]

    print(f"Bootstrapping {year} (12 months)...")
    for month in range(1, 13):
        bootstrap_month(spreadsheet, year, month, config)

    # Remove the default empty sheet if it's still there
    for default_name in ["Sheet1", "Лист1", "Feuille 1"]:
        if default_name in existing_tabs and len(spreadsheet.worksheets()) > 12:
            try:
                spreadsheet.del_worksheet(spreadsheet.worksheet(default_name))
            except Exception:
                pass

    print(f"\nDone! Open your spreadsheet:")
    print(spreadsheet.url)


def cmd_sync_day(config: dict, client: gspread.Client, date_str: str, hours: float) -> None:
    if not config.get("spreadsheet_id"):
        print("No spreadsheet_id in config. Run 'work bootstrap' first.", file=sys.stderr)
        sys.exit(1)

    d = date.fromisoformat(date_str)
    tab_name = month_tab_name(d.year, d.month)
    row = d.day + 1  # day 1 → row 2 (row 1 is header)

    spreadsheet = client.open_by_key(config["spreadsheet_id"])
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        print(f"Tab '{tab_name}' not found. Run 'work bootstrap' first.", file=sys.stderr)
        sys.exit(1)

    ws.update_cell(row, 3, round(hours, 4))


def cmd_get_saldo(config: dict, client: gspread.Client) -> None:
    if not config.get("spreadsheet_id"):
        print("0", end="")
        return

    today = date.today()
    tab_name = month_tab_name(today.year, today.month)

    try:
        spreadsheet = client.open_by_key(config["spreadsheet_id"])
        ws = spreadsheet.worksheet(tab_name)
    except (gspread.SpreadsheetNotFound, gspread.WorksheetNotFound):
        print("0", end="")
        return

    col_f = ws.col_values(6)  # 1-indexed, column F = 6
    # Walk backwards to find last non-empty, non-header value
    for val in reversed(col_f[1:]):  # skip header
        if val and val != "Cumulative Saldo":
            try:
                print(float(val), end="")
                return
            except ValueError:
                continue

    print("0", end="")


def main():
    if len(sys.argv) < 2:
        print("Usage: sheets.py <bootstrap|sync-day|get-saldo> [args...]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    config = load_config()
    client = get_client(config)

    if command == "bootstrap":
        cmd_bootstrap(config, client)
    elif command == "sync-day":
        if len(sys.argv) < 4:
            print("Usage: sheets.py sync-day <date> <hours>", file=sys.stderr)
            sys.exit(1)
        cmd_sync_day(config, client, sys.argv[2], float(sys.argv[3]))
    elif command == "get-saldo":
        cmd_get_saldo(config, client)
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
