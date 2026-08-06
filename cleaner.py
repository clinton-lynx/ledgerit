"""Deterministic cleaning + analysis. No model involved anywhere in this file.

Every number the worker ever states comes from here. The LLM only explains
what this module computes — that separation is the whole design, and it is
what makes the answers trustworthy on a 3B model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%m/%d/%Y"]

# The minimum a file needs for Ledgerit to do anything useful with it: a
# date and product to slice by, and the three numbers every arithmetic
# check and revenue figure is built from. vendor/channel/payment_method are
# deliberately NOT required — a single-outlet, single-channel, cash-only
# shop's export can reasonably omit them, and the rest of clean() already
# degrades gracefully (via the `if col in df.columns` guards below) when
# they're missing. A real POS export (Moniepoint, Opay, Paystack) uses
# column names nothing like these, which is exactly the case this check
# exists to catch early and explain, rather than let fail three steps later
# as a raw KeyError inside some handler in analyst.py.
REQUIRED_COLUMNS = ["date", "product", "qty", "unit_price", "total"]


class MissingColumnsError(ValueError):
    """Raised by clean() when a file doesn't have the columns Ledgerit
    needs, with enough detail for the caller to show a genuinely useful
    message instead of a raw KeyError from wherever the missing column
    first got touched downstream."""

    def __init__(self, required: list[str], found: list[str]):
        self.required = required
        self.found = found
        self.missing = [c for c in required if c not in found]
        super().__init__(
            "This doesn't look like a sales file Ledgerit recognises.\n"
            f"Missing column{'s' if len(self.missing) != 1 else ''}: "
            f"{', '.join(self.missing)}.\n"
            f"Ledgerit needs: {', '.join(required)}.\n"
            f"Found in your file: {', '.join(found) if found else '(no columns at all)'}."
        )


class EmptyDatasetError(ValueError):
    """Raised by clean() when nothing survives cleaning — a header-only
    file, or one where every row got filtered out (most commonly: every
    date failed to parse). Left unchecked, a 0-row "successful" load reaches
    build_index() and every analysis handler downstream, both of which
    crash on an empty DataFrame with a raw pandas exception nowhere near
    where the actual cause was (see
    docs/adversarial-testing-2026-08-07.md, #2). Catching it here, where
    the reason is already known, means the message can say why."""

    def __init__(self, rows_in: int, dates_failed: int, duplicates_removed: int):
        self.rows_in = rows_in
        if rows_in == 0:
            detail = "The file has no data rows — only a header, or nothing at all."
        elif dates_failed and dates_failed >= rows_in - duplicates_removed:
            detail = (
                f"All {rows_in} row(s) were read, but every date failed to parse — "
                f"check the date column's format."
            )
        elif duplicates_removed >= rows_in:
            detail = f"All {rows_in} row(s) were exact duplicates of each other."
        else:
            detail = f"{rows_in} row(s) were read, but none survived cleaning."
        super().__init__(f"This file has nothing left to show after cleaning. {detail}")


@dataclass
class CleanReport:
    """What changed, so the UI can show its work rather than assert it."""
    rows_in: int = 0
    rows_out: int = 0
    duplicates_removed: int = 0
    dates_parsed: int = 0
    dates_failed: int = 0
    currency_stripped: int = 0
    blanks_filled: dict[str, int] = field(default_factory=dict)
    total_mismatches: list[dict] = field(default_factory=list)
    columns_renamed: dict[str, str] = field(default_factory=dict)

    def summary_lines(self) -> list[str]:
        out = [f"Loaded {self.rows_in} rows, kept {self.rows_out}."]
        if self.duplicates_removed:
            out.append(f"Removed {self.duplicates_removed} duplicate rows.")
        if self.currency_stripped:
            out.append(f"Stripped currency text from {self.currency_stripped} price cells.")
        if self.dates_failed:
            out.append(f"{self.dates_failed} dates could not be parsed.")
        for col, n in self.blanks_filled.items():
            out.append(f"Filled {n} blank values in '{col}' as 'unknown'.")
        if self.total_mismatches:
            out.append(
                f"Found {len(self.total_mismatches)} rows where Total does not equal "
                f"Qty x Unit Price — likely manual entry errors."
            )
        return out


def _snake(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")


def _to_number(value) -> float | None:
    """'NGN1,800' -> 1800.0 ; '' -> None ; 1800 -> 1800.0"""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in ("", "-", "."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_dates(series: pd.Series) -> tuple[pd.Series, int, int]:
    """Parse mixed date formats, resolving DD/MM vs MM/DD column-wide.

    '02/07/2026' is ambiguous per row and always will be. Guessing row by row
    silently invents months — a file spanning May-July came out spanning
    January-October. So: for slash dates, try both orderings across the whole
    column and keep whichever parses more rows. A file is written by one person
    with one convention, so the column-wide winner is the right answer even
    though no single row can prove it.
    """
    result = pd.Series([pd.NaT] * len(series), index=series.index, dtype="datetime64[ns]")

    # Unambiguous formats first.
    for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
        pending = result.isna()
        if not pending.any():
            break
        result[pending] = pd.to_datetime(series[pending], format=fmt, errors="coerce")

    # Slash dates: decide the ordering once, for the whole column.
    pending = result.isna()
    if pending.any():
        remaining = series[pending]
        dmy = pd.to_datetime(remaining, format="%d/%m/%Y", errors="coerce")
        mdy = pd.to_datetime(remaining, format="%m/%d/%Y", errors="coerce")
        result[pending] = dmy if dmy.notna().sum() >= mdy.notna().sum() else mdy

    return result, int(result.notna().sum()), int(result.isna().sum())


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, CleanReport]:
    rep = CleanReport(rows_in=len(df))

    rename = {c: _snake(c) for c in df.columns}
    rep.columns_renamed = {k: v for k, v in rename.items() if k != v}
    df = df.rename(columns=rename)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise MissingColumnsError(REQUIRED_COLUMNS, list(df.columns))

    before = len(df)
    df = df.drop_duplicates()
    rep.duplicates_removed = before - len(df)

    if "date" in df.columns:
        df["date"], rep.dates_parsed, rep.dates_failed = _parse_dates(df["date"])
        df = df[df["date"].notna()]

    for col in ("qty", "unit_price", "total", "delivery_fee"):
        if col in df.columns:
            raw = df[col]
            converted = raw.map(_to_number)
            if col == "unit_price":
                rep.currency_stripped = int(
                    sum(1 for v in raw if isinstance(v, str) and re.search(r"[^\d.]", v))
                )
            df[col] = converted

    for col in ("product", "vendor", "channel", "payment_method"):
        if col in df.columns:
            n_blank = int(df[col].isna().sum())
            if n_blank:
                rep.blanks_filled[col] = n_blank
            df[col] = df[col].fillna("unknown").astype(str).str.strip()

    # Normalise casing variants: 'APP' / 'App' / 'app' are one channel.
    for col in ("channel", "payment_method"):
        if col in df.columns:
            df[col] = df[col].str.lower().str.replace(r"[\s_-]+", " ", regex=True).str.strip()
    if "channel" in df.columns:
        df["channel"] = df["channel"].replace({"walk in": "walk-in", "walkin": "walk-in"})
    if "payment_method" in df.columns:
        df["payment_method"] = df["payment_method"].replace({"pos": "card"})
    if "product" in df.columns:
        df["product"] = df["product"].str.title().str.replace(r"\s+", " ", regex=True)

    # Flag arithmetic that doesn't add up. Flag, don't silently "fix" —
    # a business owner needs to see these, not have them quietly overwritten.
    if {"qty", "unit_price", "total"} <= set(df.columns):
        expected = df["qty"] * df["unit_price"]
        off = (df["total"] - expected).abs() > 1
        for idx in df[off].index[:50]:
            rep.total_mismatches.append({
                "order_id": str(df.at[idx, "order_id"]) if "order_id" in df.columns else str(idx),
                "recorded_total": float(df.at[idx, "total"]),
                "expected_total": float(expected.at[idx]),
            })

    rep.rows_out = len(df)
    if rep.rows_out == 0:
        raise EmptyDatasetError(rep.rows_in, rep.dates_failed, rep.duplicates_removed)
    return df.reset_index(drop=True), rep
