# ledgerit
Offline AI bookkeeper for Nigerian small businesses. Cleans messy sales records, answers questions about them, and flags entries that don't add up. Built to run entirely on an 8GB laptop with no internet.

## Setup

```
pip install -r requirements.txt
```

## Running it

**As an app** (recommended — a dedicated window, not a browser tab):

```
python3 launch.py
```

Starts a local server on `127.0.0.1` (stdlib `http.server` — the web framework is the only new dependency the local server itself needed, and it doesn't) and opens `worker/web/index.html` in your installed Chrome/Chromium/Edge/Brave using `--app` mode. Falls back to your default browser if none of those are installed. Closing the window shuts the server down; so does Ctrl+C.

Accepts `.csv` or `.xlsx` — click the filename in the top bar to load your own file. CSV encoding is detected automatically (UTF-8, UTF-8 with BOM, Windows-1252, UTF-16); comma, semicolon, and tab delimiters are all sniffed automatically too. Whatever file you load needs `date`, `product`, `qty`, `unit_price`, and `total` columns (any spelling/casing — they're matched after normalising); if they're not found, Ledgerit tells you which ones it needed and which ones it saw. `.xls` (the old binary Excel format), PDF, and scanned/image input are not supported.

**As a CLI:**

```
python3 main.py data/sales_raw.csv
```

