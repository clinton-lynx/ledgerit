"""Ledgerit's local HTTP server — the real backend behind worker/web/.

Two jobs:
  - serve the static app (worker/web/index.html), same origin only
  - a small JSON API wired directly to the real pipeline: cleaner.clean(),
    analyst.answer(), explain.classify(), explain.explain(). No mock data,
    no separate demo layer — this calls the exact same functions main.py
    calls.

Stdlib only (http.server + json). No Flask/FastAPI: the target machine has
an 8 GB total / 7 GB hard-limit budget the model already dominates, and a
web framework isn't worth the memory here for three JSON endpoints.
"""
from __future__ import annotations

import base64
import binascii
import csv
import functools
import http.server
import io
import json
import sys
import threading
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent
WEB_DIR = WORKER_DIR / "web"
SAMPLE_CSV = WORKER_DIR / "data" / "sales_raw.csv"

sys.path.insert(0, str(WORKER_DIR))

import pandas as pd  # noqa: E402

from analyst import HANDLERS, answer, build_index  # noqa: E402
from cleaner import EmptyDatasetError, MissingColumnsError, clean  # noqa: E402
from explain import QuestionTooLongError, classify, explain  # noqa: E402
from explain import _llm as _load_model  # noqa: E402


# --------------------------------------------------------------------------
# Reading whatever file the browser sent up.
#
# The upload always arrives as base64 bytes (FileReader.readAsDataURL on
# the frontend, for both CSV and XLSX — see web/build.py) rather than
# CSV-as-text. That's deliberate: decoding text in the browser before
# sending it means committing to an encoding (JS defaults to UTF-8) before
# we ever get a look at the bytes, and a shop owner's CSV exported from
# Excel on Windows is routinely Windows-1252 or UTF-8-with-BOM, not UTF-8.
# Once JS has mis-decoded those bytes, the original bytes are gone — there
# is nothing left to detect an encoding from. Sending raw bytes and doing
# the decoding here, where we can try several encodings against the actual
# bytes, is the only way to recover the file as the owner's spreadsheet
# program actually wrote it.
# --------------------------------------------------------------------------

def _decode_csv_bytes(raw: bytes) -> str:
    """Try encodings in order of how likely they are to be both correct
    and detectable, not just "won't raise" — latin-1 never raises (it maps
    every byte 0-255 to a code point) so it's listed last, as the true
    last resort, not a first guess that happens to always succeed."""
    # UTF-16 has an unambiguous byte-order-mark; check for it explicitly
    # rather than letting it fall into the same try/except as the others,
    # since decoding UTF-16 bytes as a single-byte encoding "succeeds" with
    # garbage instead of raising, which would hide the real encoding.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "windows-1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")  # unreachable: latin-1 never raises


def _sniff_delimiter(text: str) -> str:
    """Comma is the overwhelming default, but a semicolon-delimited export
    (common from Excel set to a European/Nigerian locale, where comma is
    the decimal separator) or a tab-delimited one otherwise loads as a
    single mangled column with no error — csv.Sniffer catches that instead
    of pandas silently "succeeding" at reading the file wrong."""
    sample = text[:8192]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","  # sniffer gives up on very short/single-column samples; comma is the safe default


# Above this raw size, the memory cost of holding the previous dataset
# alongside a new one being validated stops being negligible against the
# 7 GB budget — measured up to ~2.92 GB peak RSS with the model warm, at
# 2M rows / 137 MB (docs/adversarial-testing-2026-08-07.md, #5). A typical
# shop's export is thousands to tens of thousands of rows — a few hundred
# KB to a few MB — where holding both is genuinely negligible, and where
# keeping the old dataset available as a fallback (in case the new upload
# turns out to be invalid) is worth far more than the memory it costs.
# Only above this backstop does that safety net get traded away for
# headroom; nothing this size was actually observed to risk the ceiling —
# it's a conservative line drawn well inside the smallest size that was.
_LARGE_UPLOAD_BYTES = 50 * 1024 * 1024  # ~50 MB raw (base64 length is checked pre-decode)


def _is_large_upload(body: dict) -> bool:
    # base64 expands bytes by ~4/3; comparing the encoded string's length
    # directly against a raw-byte threshold undercounts slightly, which
    # only makes this trigger a little earlier, not later.
    return len(body.get("file") or "") > _LARGE_UPLOAD_BYTES


def _read_uploaded_dataframe(body: dict) -> tuple[pd.DataFrame, str]:
    """Returns (raw_dataframe, filename). Raises ValueError with a message
    fit to show the user directly if the upload can't be read at all
    (corrupt file, wrong format, undecodable bytes)."""
    # "no 'file' key at all" (the sample-load / replay path — see
    # loadFile(null, null) in web/build.py) and "'file' key present but its
    # value is falsy" are different situations and used to be handled
    # identically, because base64.b64encode(b"") == "" is falsy. A genuine
    # 0-byte upload silently loaded the bundled sample instead of erroring
    # (docs/adversarial-testing-2026-08-07.md, #1) — checking key presence
    # instead of truthiness tells the two apart.
    if "file" not in body:
        return pd.read_csv(SAMPLE_CSV), SAMPLE_CSV.name

    file_b64 = body.get("file") or ""
    filename = (body.get("filename") or "").strip()

    if not file_b64:
        raise ValueError("That file appears to be empty — nothing to load.")

    try:
        raw = base64.b64decode(file_b64, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("That upload didn't arrive intact — try again.")

    is_xlsx = filename.lower().endswith(".xlsx") or raw[:4] == b"PK\x03\x04"
    if is_xlsx:
        try:
            return pd.read_excel(io.BytesIO(raw), engine="openpyxl"), filename or "upload.xlsx"
        except Exception as e:
            raise ValueError(f"Couldn't read that as an Excel file: {e}")

    try:
        text = _decode_csv_bytes(raw)
    except Exception as e:  # pragma: no cover - latin-1 fallback makes this unreachable in practice
        raise ValueError(f"Couldn't read that file's text encoding: {e}")

    delimiter = _sniff_delimiter(text)
    try:
        df = pd.read_csv(io.StringIO(text), sep=delimiter)
    except pd.errors.EmptyDataError:
        raise ValueError("That file is empty — nothing to read.")
    except Exception as e:
        raise ValueError(f"Couldn't read that as a CSV: {e}")
    return df, filename or "upload.csv"


class _State:
    """What has to persist between requests: the cleaned frame and its BM25
    index. Guarded by a lock — ThreadingHTTPServer means two requests can
    arrive at once, and swapping `df` out from under a read isn't safe."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.df = None
        self.index = None
        self.filename: str | None = None


STATE = _State()

# llama_cpp's loaded model is one C++ context with internal, mutable
# generation state (its KV cache) — it is not safe to call into from two
# threads at once. ThreadingHTTPServer hands each request its own thread,
# and the frontend's /api/ask and /api/narrate calls can be in flight
# together, so every call that reaches the model (classify() or explain(),
# both funnel through explain._llm()) has to be serialised through this
# lock. Found by running the real UI end to end: firing both requests
# concurrently segfaulted the server (SIGSEGV) the first time a question
# was asked. Pandas-only work (answer()) never touches this lock.
MODEL_LOCK = threading.Lock()


def warm_model_in_background() -> None:
    """Load the model once, before the user ever asks anything — otherwise
    the first real question pays the ~15-50s model-load cost on top of
    generation time, which reads as the app being broken, not just slow."""
    def _warm():
        try:
            print("warming the model…", file=sys.stderr)
            with MODEL_LOCK:
                _load_model()
            print("model ready", file=sys.stderr)
        except Exception as e:  # pragma: no cover - best-effort warm-up
            print(f"model warm-up failed, will load on first request instead: {e}", file=sys.stderr)

    threading.Thread(target=_warm, daemon=True).start()


def _finding_to_json(finding, question: str, route: str | None) -> dict:
    """Finding -> JSON for the frontend.

    Deliberately excludes `finding.guidance`: that field is instruction
    text for the model — how to read the numbers so it doesn't invert them
    — not something a shop owner should ever see rendered as if it were
    part of their data.
    """
    table = None
    if finding.table is not None and not finding.table.empty:
        # round-trip through pandas' own JSON encoder rather than
        # DataFrame.to_dict(), which leaves numpy int64/float64 in the
        # values and those aren't JSON-serialisable by the stdlib encoder.
        table = json.loads(finding.table.to_json(orient="records"))
    return {
        "question": question,
        "route": route,
        "headline": finding.headline,
        "facts": finding.facts or {},
        "table": table,
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def guess_type(self, path):
        """SimpleHTTPRequestHandler's guessed Content-Type never includes a
        charset. Serve this for real instead of through the artifact
        preview and that's exactly the gap that showed up: the receipt's
        emoji, its em dash, its multiplication sign all rendered as
        mojibake, because nothing told the browser this file is UTF-8. The
        page's own <meta charset="utf-8"> is the belt; this header is the
        suspenders — the HTTP header wins if the two ever disagree."""
        ctype = super().guess_type(path)
        if ctype.startswith("text/") or ctype == "application/javascript":
            return ctype + "; charset=utf-8"
        return ctype

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ---------------------------------------------------------------- #
    # JSON helpers
    # ---------------------------------------------------------------- #
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---------------------------------------------------------------- #
    # routes
    # ---------------------------------------------------------------- #
    def do_POST(self):
        try:
            if self.path == "/api/load":
                return self._handle_load()
            if self.path == "/api/ask":
                return self._handle_ask()
            if self.path == "/api/narrate":
                return self._handle_narrate()
            self._send_json({"error": "not found"}, 404)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_load(self):
        """Real cleaner.clean() run, on either the bundled sample or a file
        the browser sent up (CSV or XLSX, as base64 bytes — see
        _read_uploaded_dataframe for why not text). Bad input (wrong
        format, undecodable bytes, missing columns, nothing left after
        cleaning) comes back as 400 with a message meant to be shown to the
        user directly, not a 500 with a raw traceback three modules away
        from where the file was read."""
        body = self._read_json()

        # Only a large upload (see _LARGE_UPLOAD_BYTES) frees the previous
        # dataset up front. Below that size, validate-then-swap is strictly
        # better: the old dataset stays available as a fallback the whole
        # time, and only gets replaced once the new one is known-good —
        # so a bad upload never costs the user their working data. That
        # safety net is only traded away above the size where holding both
        # stops being negligible against the memory budget.
        large_upload = _is_large_upload(body)
        if large_upload:
            with STATE.lock:
                STATE.df = None
                STATE.index = None

        try:
            raw_df, filename = _read_uploaded_dataframe(body)
        except ValueError as e:
            return self._send_json({"error": str(e)}, 400)

        # The base64 payload (body["file"]) can be well over 100 MB for a
        # large file and isn't needed again — drop it before the
        # clean()/build_index() work below rather than let it sit resident
        # in `body` for the rest of this method purely because `body` is
        # still in scope.
        body.clear()

        try:
            df, report = clean(raw_df)
        except (MissingColumnsError, EmptyDatasetError) as e:
            return self._send_json({"error": str(e)}, 400)
        del raw_df

        index = build_index(df)

        with STATE.lock:
            STATE.df = df
            STATE.index = index
            STATE.filename = filename

        self._send_json({
            "filename": filename,
            "rows_in": report.rows_in,
            "rows_out": report.rows_out,
            "duplicates_removed": report.duplicates_removed,
            "currency_stripped": report.currency_stripped,
            "dates_failed": report.dates_failed,
            "blanks_filled": report.blanks_filled,
            "total_mismatches": report.total_mismatches[:5],
            "total_mismatches_count": len(report.total_mismatches),
        })

    def _handle_ask(self):
        """Fast half of asking a question: routing + pandas only. classify()
        is a model call (small — a single-label prediction) so it goes
        through MODEL_LOCK, but it's short; answer() itself is pure pandas
        and never touches the model. Returns as soon as the Finding exists,
        so the receipt can be on screen well before narration is ready."""
        body = self._read_json()
        question = (body.get("question") or "").strip()
        if not question:
            return self._send_json({"error": "empty question"}, 400)

        with STATE.lock:
            df, index = STATE.df, STATE.index
        if df is None:
            return self._send_json({"error": "no file loaded yet"}, 400)

        try:
            with MODEL_LOCK:
                label = classify(question)
        except QuestionTooLongError as e:
            return self._send_json({"error": str(e)}, 400)
        route = label if label in HANDLERS else None
        finding = answer(df, question, index, label=label)
        self._send_json(_finding_to_json(finding, question, route))

    def _handle_narrate(self):
        """Slow half: recomputes the same Finding (cheap — pandas, not the
        model) and calls the real explain() — including its verify-and-
        retry pass — for the narration. Takes the route/label /api/ask
        already resolved (`label` in the body) so this never reclassifies
        the question itself; that keeps this endpoint's only model call to
        the one that matters (generation) and avoids a second classify()
        call racing the first one for MODEL_LOCK. Kept as a separate
        request from /api/ask on purpose: the frontend already has a
        Finding to render before this one resolves, rather than blocking
        the whole receipt on 15+ seconds of generation."""
        body = self._read_json()
        question = (body.get("question") or "").strip()
        if not question:
            return self._send_json({"error": "empty question"}, 400)

        with STATE.lock:
            df, index = STATE.df, STATE.index
        if df is None:
            return self._send_json({"error": "no file loaded yet"}, 400)

        label = body.get("label")  # None is valid: "no handler matched" case
        finding = answer(df, question, index, label=label)
        try:
            with MODEL_LOCK:
                narration = explain(finding, question)
        except QuestionTooLongError as e:
            return self._send_json({"error": str(e)}, 400)

        self._send_json({
            "text": narration.text,
            "verified": narration.verified,
            "unsupported": narration.unsupported,
            "retried": narration.retried,
        })


def create_server(host: str, port: int) -> http.server.ThreadingHTTPServer:
    return http.server.ThreadingHTTPServer((host, port), Handler)
