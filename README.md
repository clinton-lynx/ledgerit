# Ledgerit

**Offline bookkeeping intelligence for African small businesses.**

Getting your own records cleaned, checked and explained shouldn't need an
internet connection and a monthly fee.

![Ledgerit](screenshots/sample-file.jpeg)

My mother is a petty trader. She wrote everything in a notebook: what sold, how
many packs, who paid cash and who took it on credit. At the end of every month
she'd sit with that notebook and a calculator trying to work out whether she'd
made any money. Cash in hand, goods still on the shelf, money owed by people who
never came back. Three piles that had to reconcile, no way to check her own
working, and hours gone.

Ledgerit reads the file a small business already keeps, cleans it, flags the
entries that don't add up, and answers questions about it in plain English.
Entirely on an 8 GB laptop, with no internet.

**How it works:** pandas computes every figure; the local model only explains
what pandas already calculated. It never does arithmetic, and every number in
its output is checked against the figures it was given.

---

## Setup

```
pip install -r requirements.txt
```

You also need [llama.cpp](https://github.com/ggml-org/llama.cpp) installed, and
the model weights:

```
bash download_model.sh
```

The download resumes and retries, because a 1.5 GB transfer over an unreliable
connection routinely drops. It verifies the checksum before finishing.

---

## Running it

**As an app**, in a dedicated window rather than a browser tab:

```
python3 launch.py
```

Starts a local server on `127.0.0.1` and opens Ledgerit in your installed
Chrome, Chromium, Edge or Brave using `--app` mode. Falls back to your default
browser if none are installed. Closing the window shuts the server down, as does
Ctrl+C.

**As a CLI:**

```
python3 main.py data/sales_raw.csv
```

---

## Supported files

| | |
|---|---|
| **Formats** | `.csv`, `.xlsx` |
| **Encodings** | UTF-8, UTF-8 with BOM, Windows-1252, UTF-16. Detected automatically. |
| **Delimiters** | comma, semicolon, tab. Sniffed automatically. |
| **Column names** | Any. Ledgerit maps them to what it needs and asks you to confirm. |
| **Multi-sheet workbooks** | Supported. Ledgerit asks which sheet to read. |
| **Header not in row 1** | Detected. Ledgerit asks when it isn't confident. |
| **Extra columns** | Preserved and ignored. |
| **Not supported** | `.xls`, PDF, scanned or photographed input |

Load your own file by clicking the filename in the top bar, or drop it onto the
window.

---

## What it does with a file

1. **Reads it**, whatever shape it's in. If the columns are named `Item`, `Rate`
   and `Amount` rather than `product`, `unit_price` and `total`, it shows a
   mapping with its best guesses and sample values so you can confirm. If a
   workbook has several sheets, it asks which one. If the header isn't the first
   row, it works out where the header is.
2. **Cleans it.** Parses mixed date formats, strips currency text from number
   columns, removes duplicate rows, normalises category casing.
3. **Flags what doesn't add up.** Where a recorded total doesn't equal quantity
   times unit price, both figures are shown. Nothing is silently corrected.
4. **Answers questions** in plain English: best and worst sellers, monthly
   trend, quietest day, breakdown by vendor, channel or payment method.
5. **Exports** any answer, or the cleaning report, as a receipt-styled PDF.

---

## Offline

No network calls at any point after installation. The interface includes a live
indicator that watches every request the page makes and latches red permanently
if anything non-local is ever attempted.

---

## Project layout

```
metadata.json        ADTC submission metadata
download_model.sh    Fetches the GGUF weights
REPORT.md            Technical report
cleaner.py           Deterministic cleaning. No model involved.
analyst.py           BM25 retrieval and eight pandas analyses
explain.py           Model narration, routing, number verification
server.py            Local HTTP server, file reading, column mapping, PDF export
launch.py            Starts the server and opens the app window
web/                 Interface
docs/                Evaluation writeups
tests/               Routing accuracy and quantization comparison
```

---

## Model

SmolLM3-3B, Q3_K_M quantization, GGUF, served through llama.cpp.
1.5 GB on disk, 1,976 MB peak RSS, 6.13 tok/s on CPU.

Quantized and published at
[huggingface.co/clintonlynx](https://huggingface.co/clintonlynx).

Full benchmarks, design decisions and known limitations are in
[REPORT.md](REPORT.md).

---

## Licence

Apache-2.0.