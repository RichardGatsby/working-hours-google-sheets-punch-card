# Working Hours Tracker

Log your working hours from the terminal. Sessions are tracked locally and synced to Google Sheets automatically.

## How it works

- `work start` — start a session
- `work end` — end the session and sync to Google Sheets
- `work status` — see today's hours and your cumulative saldo
- `work bootstrap` — one-time setup to create the spreadsheet

Starting again on the same day accumulates hours. Each month gets its own sheet tab with dates, target hours (7.5h weekdays, 0 weekends), and a running saldo.

---

## Setup

### 1. Install Python dependencies

```bash
pip install gspread google-auth
```

### 2. Create a Google Cloud service account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Go to **APIs & Services → Library**, search for and enable:
   - **Google Sheets API**
   - **Google Drive API**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → Service account**
6. Give it any name, click through to finish
7. Click the service account you just created → **Keys** tab → **Add Key → Create new key → JSON**
8. Save the downloaded `.json` file somewhere safe (e.g. `~/.config/gcloud/work-hours-key.json`)

### 3. Create a Google Sheets spreadsheet

The service account cannot create spreadsheets on your behalf due to Drive storage restrictions. Create one yourself:

1. Go to [sheets.google.com](https://sheets.google.com) and create a new blank spreadsheet
2. Name it **"Working Hours 2026"** (or any name you like)
3. Click **Share**, add the service account email as **Editor** — find it in your credentials JSON as `client_email`, e.g.:
   ```
   worksheet-excel@my-project-123.iam.gserviceaccount.com
   ```
4. Copy the spreadsheet ID from the URL — the long string between `/d/` and `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit
   ```

### 4. Configure the tracker

Place the downloaded service account JSON key in the project directory as `credentials.json`, then:

```bash
cp config.json.example config.json
```

Edit `config.json`:

```json
{
  "spreadsheet_id": "paste-your-spreadsheet-id-here",
  "credentials_path": "credentials.json",
  "target_hours_weekday": 7.5,
  "target_hours_weekend": 0,
  "theme_color": "#1e3a5f"
}
```

- **`spreadsheet_id`** — the ID copied in step 3
- **`credentials_path`** — path to your service account JSON key (relative to the project directory, or absolute)
- **`target_hours_weekday`** — your daily target in hours (e.g. `7.5` for 7h 30min)
- **`target_hours_weekend`** — typically `0`
- **`theme_color`** — hex color used for spreadsheet header and summary styling (e.g. `#17DE80` for your company color)

### 5. Make the script executable and available

```bash
chmod +x work
# Optional: add to PATH so you can run it from anywhere
ln -s "$PWD/work" /usr/local/bin/work
```

### 6. Bootstrap the spreadsheet

```bash
work bootstrap
```

This fills the spreadsheet with one tab per month for the current year — dates, weekdays, target hours, and formulas. It prints the URL when done.

---

## Daily usage

```bash
work start     # clock in
work end       # clock out — syncs hours to Sheets

work start     # resume after a break
work end       # clock out again — hours accumulate

work status    # check today's hours and cumulative saldo
```

### Example output

```
$ work start
Session started at 08:45.

$ work status
Date:    2026-03-11
Session: active since 08:45 (1h 23m ago)
Today:   1h 23m (1.38h) — session open

Fetching saldo from Sheets...
Saldo:   +2h 15m (2.25h)

$ work end
Session ended. Syncing to Google Sheets...
Done. Total logged for 2026-03-11: 1h 23m (1.3833h)
```

---

## Spreadsheet structure

Each monthly tab (e.g. `2026-03`) has these columns:

| A | B | C | D | E | F | | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Date | Weekday | Hours Worked | Target Hours | Daily Diff | Cumulative Saldo | | Month Hours | Month Saldo | Cumulative Saldo |

- **Hours Worked** — filled in by `work end`
- **Daily Diff** — Hours Worked − Target Hours
- **Cumulative Saldo** — running total that carries over from the previous month
- **Month Hours** (H2) — total hours worked this month
- **Month Saldo** (I2) — this month's saldo contribution only
- **Cumulative Saldo** (J2) — same as the last day's F value; overall saldo through end of month

---

## Troubleshooting

**`Config not found`** — Make sure `config.json` exists in the project directory and is valid JSON.

**`Credentials file not found`** — Check that `credentials_path` in your config points to the correct file.

**`Tab '2026-03' not found`** — Run `work bootstrap` first.

**Permission denied on the spreadsheet** — The service account email (found in the credentials JSON as `client_email`) needs Editor access to the spreadsheet. Share it from the Sheets UI or re-run `work bootstrap` to create a fresh one.

**Unclosed session warning on `work start`** — You forgot to run `work end` yesterday. Run `work end` to close and sync the previous day, then `work start` for today.
