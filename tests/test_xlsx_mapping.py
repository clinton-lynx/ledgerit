"""Regression suite for the xlsx-mapping crash and the silent-500 bug that
let it survive two rounds of "fixed and verified" (see REPORT.md history /
the 2026-08-10 session notes for the actual incident).

Standalone script — no pytest dependency (none is installed in the target
environment, and the brief forbids adding one), same convention as
test_routing.py. Run directly:

    python3 tests/test_xlsx_mapping.py

Every test_*() function is also a plain pytest entry point if pytest happens
to be available.

Coverage, per the postmortem:
  1. Mixed text/numeric columns surviving mapping (openpyxl hands back
     different per-cell types than pandas' CSV reader, which is what made
     this xlsx-only).
  2. The duplicate-column-label collision found while chasing (1) — an
     unmapped column whose snake-cased name collides with a mapped target.
  3. The mapping path exercised against a real xlsx file end to end,
     through the same server-side read function /api/load actually calls.
  4. That a server error on the mapping-confirm path is not just returned,
     but actually rendered visibly — the bug that mattered more than (1),
     since (1) alone would have been a visible error message rather than a
     silent no-op.
"""
from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKER_DIR))

import pandas as pd  # noqa: E402
from openpyxl import Workbook  # noqa: E402

import cleaner  # noqa: E402
import server  # noqa: E402

MAPPING = {
    "order_id": "Invoice No", "date": "Date", "product": "Item",
    "qty": "Qty", "unit_price": "Rate", "total": "Amount",
}

BASE_ROWS = [
    ["16-Jul-2026", "INV1001", "12mm Iron Rod", 76, 7517.0, 571292.0],
    ["05/05/2026", "INV1002", "Blocks 6in", 285, 380.0, 108300.0],
    ["15/06/2026", "INV1003", "Stepping Tiles", 37, 8500.0, 314500.0],
]
HEADERS = ["Date", "Invoice No", "Item", "Qty", "Rate", "Amount"]


def _base_df() -> pd.DataFrame:
    return pd.DataFrame(BASE_ROWS, columns=HEADERS)


# --------------------------------------------------------------------------
# 1. Mixed text/numeric columns after mapping
# --------------------------------------------------------------------------

def test_mixed_text_numeric_columns_after_mapping():
    """openpyxl can hand back a column as genuinely mixed dtype — some
    cells read as int/float, others as str, depending on how each cell was
    formatted in Excel (a "Qty" column with a couple of cells formatted as
    Text is common, not exotic). pandas' CSV reader never produces this
    shape — it infers one dtype for the whole column — which is exactly
    why this didn't surface until xlsx. qty and unit_price must come out
    of clean() as numeric regardless, and the mismatch arithmetic must not
    raise on it."""
    df = _base_df()
    df["Qty"] = ["76", 285, "37"]                    # str next to int
    df["Rate"] = [7517.0, "NGN 380", "8,500"]         # float next to currency text

    out, rep = cleaner.clean(df, column_map=MAPPING)

    assert out["qty"].dtype.kind == "f", out["qty"].dtype
    assert out["unit_price"].dtype.kind == "f", out["unit_price"].dtype
    assert list(out["qty"]) == [76.0, 285.0, 37.0]
    assert list(out["unit_price"]) == [7517.0, 380.0, 8500.0]
    # rows already agree (qty * unit_price == total) — coercion should not
    # invent mismatches out of correctly-parsed values.
    assert rep.total_mismatches == []


def test_mixed_columns_with_blanks_and_garbage():
    """Blank cells and genuinely unparseable text (not just currency
    formatting) must become NaN, not crash the multiply."""
    df = _base_df()
    df["Qty"] = ["76", None, "not-a-number"]
    df["Rate"] = [7517.0, 380.0, ""]

    out, rep = cleaner.clean(df, column_map=MAPPING)
    assert out["qty"].dtype.kind == "f"
    assert out["unit_price"].dtype.kind == "f"
    # row 0 is the only one with both qty and unit_price present and total
    # matching; rows with a NaN operand can't be flagged as a mismatch —
    # NaN comparisons are always False, so they're silently excluded,
    # not falsely flagged.
    assert rep.rows_out >= 1


# --------------------------------------------------------------------------
# 2. Duplicate column label collision
# --------------------------------------------------------------------------

def test_duplicate_column_label_collision():
    """An unmapped column can snake-case to the same name as a
    deliberately mapped target — a leftover "Unit Price" column sitting
    next to a "Rate" the user explicitly mapped to unit_price. Before the
    fix, _apply_mapping's fallback rename let both become "unit_price",
    so df["unit_price"] returned a 2-column DataFrame instead of a Series
    and broke arithmetic downstream in whatever way that particular
    operation happens to break on a duplicate-labeled axis."""
    df = _base_df()
    df["Unit Price"] = ["decoy", "values", "here"]  # unmapped, collides after _snake()

    out, rep = cleaner.clean(df, column_map=MAPPING)

    assert out.columns.is_unique, list(out.columns)
    assert "unit_price" in out.columns
    assert out["unit_price"].dtype.kind == "f"
    # the decoy must survive under a disambiguated name, not vanish or
    # silently merge into the real column
    assert any(c.startswith("unit_price_") for c in out.columns), list(out.columns)


def test_duplicate_collision_on_a_required_column():
    """Same collision, but on a REQUIRED column (qty) rather than an
    optional one — the missing-columns check runs before the coercion
    loop, so this path is worth covering separately."""
    df = _base_df()
    df["Qty (pcs)"] = [1, 2, 3]  # _snake("Qty (pcs)") -> "qty" (parens stripped)

    out, rep = cleaner.clean(df, column_map=MAPPING)
    assert out.columns.is_unique, list(out.columns)
    assert out["qty"].dtype.kind == "f"
    assert list(out["qty"]) == [76.0, 285.0, 37.0]


# --------------------------------------------------------------------------
# 3. Mapping applied to xlsx specifically, through the real server read path
# --------------------------------------------------------------------------

def _xlsx_body(df: pd.DataFrame, filename: str = "shop-sales.xlsx", **extra) -> dict:
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    body = {"file": base64.b64encode(buf.getvalue()).decode(), "filename": filename}
    body.update(extra)
    return body


def test_mapping_applied_to_xlsx():
    """The full read path /api/load actually uses for an xlsx upload —
    server._read_uploaded_dataframe (sheet/header resolution included) —
    followed by cleaner.clean() with an explicit mapping, exactly like the
    confirm request after a user clicks "Use this mapping". A single-sheet
    workbook with the header on row 1 needs neither a sheet nor a
    header_row answer, so this covers the ordinary case without also
    re-testing the header/sheet pickers themselves (see test_server.py's
    sibling coverage, or the manual browser runs in the session notes, for
    those)."""
    df = _base_df()
    df["Qty"] = ["76", 285, "37"]  # openpyxl-shaped messiness, not CSV-shaped

    body = _xlsx_body(df)
    raw_df, filename = server._read_uploaded_dataframe(body)
    assert filename == "shop-sales.xlsx"
    assert list(raw_df.columns) == HEADERS  # str-coerced, stripped, in order

    out, rep = cleaner.clean(raw_df, column_map=MAPPING)
    assert out["qty"].dtype.kind == "f"
    assert out["unit_price"].dtype.kind == "f"
    assert rep.rows_out == 3


def test_xlsx_non_string_header_cell_no_longer_crashes():
    """A header cell that's a genuine int/float (not text) used to crash
    _snake() with "'int' object has no attribute 'strip'" before any
    mapping even ran. Covered here alongside the mapping tests since it's
    the same read path."""
    df = _base_df()
    df.columns = ["Date", "Invoice No", "Item", "Qty", "Rate", 2026]  # last header is an int
    body = _xlsx_body(df)
    raw_df, _ = server._read_uploaded_dataframe(body)
    assert all(isinstance(c, str) for c in raw_df.columns)
    assert "2026" in raw_df.columns


# --------------------------------------------------------------------------
# 4. A server error surfacing VISIBLY in the UI, not just being returned
# --------------------------------------------------------------------------

def test_server_error_surfaces_visibly_in_ui():
    """This is the one that matters most. A 500 on the mapping-confirm
    request was always turned into a JS exception and caught — the bug was
    never "the error is swallowed", it was "the error is written into the
    DOM and then never actually shown": #status-map/#status-sheet/
    #status-header default to opacity: 0 in CSS, and only .classList.add
    ('show') reveals them, the same way every other status message on this
    page already works. Setting .textContent alone leaves the message
    sitting invisibly in the DOM — indistinguishable, to the user, from
    the button doing nothing at all.

    This doesn't spin up a browser: no browser-automation dependency
    exists anywhere in this project (same "no pytest" constraint applies
    to test tooling generally — an offline, stdlib-only app doesn't carry
    a Node/Playwright toolchain to grade itself), and adding one just for
    this one assertion would be a heavier fix than the bug it's guarding.
    Instead this reads the actual shipped HTML/CSS/JS and checks the
    contract directly: it fails the moment either half of it regresses —
    the CSS stops gating on .show, or an error path forgets to add it.
    The live-browser version of this exact check (induced 500, real
    Chromium, screenshot of the visible message) was run by hand during
    the session that found this bug; this is its permanent, dependency-free
    form."""
    html = (WORKER_DIR / "web" / "index.html").read_text()

    assert re.search(r"\.status\s*\{[^}]*opacity:\s*0", html), (
        "expected #status-map/#status-sheet/#status-header (class=\"status\") "
        "to default to opacity: 0 — if that's no longer true this test's "
        "premise has changed and it needs re-thinking, not just re-running"
    )
    assert re.search(r"\.status\.show\s*\{", html), (
        "expected a .status.show rule that actually reveals the message"
    )

    for element_id in ("status-sheet", "status-header", "status-map"):
        # var X = document.getElementById('status-...');
        # X.textContent = message;
        # X.classList.add('show');
        # — same variable, both statements present, in that neighbourhood.
        pattern = re.compile(
            r"getElementById\('" + re.escape(element_id) + r"'\)\s*;\s*"
            r"(\w+)\.textContent\s*=\s*message\s*;\s*"
            r"\1\.classList\.add\(\s*['\"]show['\"]\s*\)",
        )
        assert pattern.search(html), (
            f"#{element_id}'s error-display code sets .textContent without "
            "also calling .classList.add('show') — the message will be "
            "written into the DOM but never rendered. This is exactly how "
            "a 500 on \"Use this mapping\" survived two rounds of "
            "\"fixed and verified\": the fix was returning the error "
            "correctly, not showing it."
        )


TESTS = [
    test_mixed_text_numeric_columns_after_mapping,
    test_mixed_columns_with_blanks_and_garbage,
    test_duplicate_column_label_collision,
    test_duplicate_collision_on_a_required_column,
    test_mapping_applied_to_xlsx,
    test_xlsx_non_string_header_cell_no_longer_crashes,
    test_server_error_surfaces_visibly_in_ui,
]


if __name__ == "__main__":
    failed = []
    for test in TESTS:
        try:
            test()
        except AssertionError as e:
            failed.append((test.__name__, str(e)))
            print(f"  [FAIL] {test.__name__}: {e}")
        else:
            print(f"  [ OK ] {test.__name__}")

    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} passed.")
    if failed:
        sys.exit(1)
