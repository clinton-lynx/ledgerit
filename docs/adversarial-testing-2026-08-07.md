# Adversarial testing: file support + real-world input, 2026-08-07

Everything below was run against the real server (`server.py`) over real HTTP,
not by inspection. Peak RSS was watched throughout via `ps` sampling of the
live process. Nothing in this document has been fixed yet — this is the
find-and-report pass; fixes are a separate decision.

## Feature work delivered first

- **`.xlsx` support** via `openpyxl` (`requirements.txt` created — none
  existed before this). Detected by extension *or* by the file's own ZIP
  magic bytes (`PK\x03\x04`), so a mislabeled file still gets read correctly.
- **CSV encoding detection**: UTF-16 (via BOM), UTF-8-with-BOM, Windows-1252,
  latin-1 (last-resort, never fails) — tried in that order against the raw
  uploaded bytes. This required changing the upload transport: the frontend
  used to call `FileReader.readAsText()`, which forces a UTF-8 decode in the
  browser before the bytes ever reach the server — once wrong, there's
  nothing left to detect from. Now both CSV and XLSX go up as base64 via
  `readAsDataURL()`, and all decoding happens server-side against the actual
  bytes.
- **Delimiter sniffing** (comma/semicolon/tab) via `csv.Sniffer`.
- **Missing-columns error**: `cleaner.clean()` now raises `MissingColumnsError`
  with the required list and what was actually found, surfaced to the user
  as a 400, not a KeyError three steps downstream inside some handler.

All four verified working end-to-end (real HTTP requests, real files) before
the adversarial pass below started.

## Found: crashes

### 1. Empty file upload is silently swallowed — loads the bundled sample instead
`base64.b64encode(b"")` is `""`, and `if not file_b64:` treats that
identically to "no file was sent," which is the signal used to fall back to
the bundled sample. A user who uploads a genuinely empty file gets the demo
data back with zero indication their upload didn't take.

**Repro:** `POST /api/load {"file": "", "filename": "empty.csv"}` (or select
a literal 0-byte file in the file picker) → `200`, returns
`sales_raw.csv`'s data, not an error.

### 2. Any file that cleans down to 0 rows crashes `/api/load` with a raw 500
`analyst.build_index()` does `df[cols].astype(str).agg(" ".join, axis=1)`,
which returns a `DataFrame` instead of a `Series` when `df` is empty, and
`.tolist()` doesn't exist on a DataFrame → `AttributeError`. Two distinct,
plausible real-world triggers land on the exact same crash:

- a header-only CSV (valid columns, zero data rows)
- a file where every row's date fails to parse — `clean()`'s
  `df = df[df["date"].notna()]` drops every row, leaving 0

**Repro:** `POST /api/load` with body
`order_id,date,product,qty,unit_price,total\n` (header only, valid columns,
no data) → `500`, `{"error": "'DataFrame' object has no attribute 'tolist'"}`.
Same result from a file where every `date` cell is unparseable garbage.

### 3. A question over ~2048 tokens crashes `/api/ask` with a raw llama_cpp error
Fails fast (0.03s) but the message is an internal implementation detail:
`{"error": "Requested tokens (4498) exceed context window of 2048"}`, HTTP
500. Nothing catches this specific exception to turn it into something a
shop owner would understand.

**Repro:** a ~3,900-word question to `/api/ask`.

## Found: real, but not crashes

### 4. Load time scales roughly linearly with row count and gets user-hostile well before it's dangerous memory-wise
Measured on this machine, model already warm, one load at a time:

| Rows | File size | Load time |
|---|---|---|
| 150,000 | ~10 MB | 10.7s |
| 600,000 | ~40 MB | 45.8s |
| 2,000,000 | ~137 MB | 153s (2.5 min) |

All three succeeded — correct row counts, correct answers afterward. This is
a perception problem, not a functional one: the printer-bar's indeterminate
pulse gives no sense of progress or ETA, and 2.5 minutes of that reads as
frozen. There is no file-size guardrail anywhere today, so nothing warns a
user before they commit to that wait.

### 5. Peak memory during a load/reload spikes well above steady-state
The previous dataset and its BM25 index stay resident while the new one is
being built, on top of the upload existing in memory in ~3 forms at once
(base64 string, decoded bytes, decoded text/DataFrame) before the old ones
are freed. Peak RSS observed (model already warm — the realistic case for
600k/2M):

| Rows | Peak RSS |
|---|---|
| 150,000 (model not yet loaded) | 465 MB |
| 600,000 | 2.77 GB |
| 2,000,000 | 2.92 GB |

None of these approached the 7–8 GB budget. **I did not push further** —
stopped around 2M rows / 137 MB deliberately, to avoid actually inducing an
OOM on this shared dev machine. The true ceiling is somewhere past that
point, untested. Peak-vs-steady-state gap is real and grows with file size;
worth knowing even though it didn't breach budget here.

### 6. A long-but-under-2048-token question (~1,200 words) to `/api/narrate` doesn't crash, but takes ~47s instead of the usual 15–30s
CPU-only prefill of a long prompt is itself slow, before generation starts.
No user-facing signal that question length is why a given wait is longer —
the loading state is already indeterminate, so this may not need a fix, but
it's worth knowing that's what's happening if it comes up during the demo.

### 7. Fresh routing spot-check: 13/16 (81%) on phrasings not in the test suite
Independent of Part 1's formal 45/48 (93.8%) measurement — smaller sample,
deliberately harder/more idiomatic phrasings, consistent with (not
contradicting) that number. Three misses:

- "What is nobody buying?" → `None` (negation phrasing; expected `worst_by_product`)
- "what can i remove from the menu" → `revenue_summary` (expected `worst_by_product`)
- "best day to run a promo" → `monthly_trend` (expected `quiet_days`)

## Confirmed working (tested, not broken)

- Header-only / single-row CSVs that keep at least one real data row.
- Extra unexpected columns — silently and harmlessly ignored.
- Semicolon and tab delimiters — correctly sniffed and parsed.
- UTF-8, UTF-8 BOM, Windows-1252, UTF-16 — all decode correctly; verified an
  actual en-dash survives the full pipeline into the rendered DOM.
- `.xlsx` uploads, including a mislabeled file (`.csv` extension, real xlsx
  bytes) correctly recovered via magic-byte sniffing.
- Non-sales-data files (prose text, raw PNG bytes) renamed `.csv` — safely
  rejected with the missing-columns message, never crash. The message does
  get visually cluttered (one giant nonsense "column name") when the input
  isn't remotely tabular — cosmetic, not a break.
- Multiple file loads/switches — state correctly reflects the most recently
  loaded file every time, verified across 4 consecutive switches
  (150k → 600k → 2M → back to the bundled sample).
- Empty / whitespace / missing `question` field — all correctly caught
  before reaching the model, clean `400 "empty question"`.
- One-word questions ("revenue", "products") — route plausibly, no crash.
- Asking before any file is loaded — both `/api/ask` and `/api/narrate`
  correctly return `400 "no file loaded yet"`. Already handled; did not need
  fixing.

## Not tested / explicitly out of scope

`.xls` (legacy binary Excel), PDF, and image/OCR input — excluded per
instruction, not attempted.
