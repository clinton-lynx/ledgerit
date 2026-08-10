"""Deterministic cleaning + analysis. No model involved anywhere in this file.

Every number the worker ever states comes from here. The LLM only explains
what this module computes — that separation is the whole design, and it is
what makes the answers trustworthy on a 3B model.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
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
OPTIONAL_CANONICAL_COLUMNS = ["order_id", "vendor", "channel", "payment_method", "delivery_fee"]
MAPPING_COLUMNS = ["order_id"] + REQUIRED_COLUMNS

TARGET_SYNONYMS: dict[str, set[str]] = {
    "date": {
        "date", "day", "invoice_date", "sale_date", "sales_date", "order_date",
        "txn_date", "transaction_date", "posted_date", "receipt_date",
    },
    "product": {"product", "item", "items", "sku", "description", "goods", "stock", "name"},
    "qty": {"qty", "quantity", "units", "unit", "count", "pieces", "pcs", "no_of_units"},
    "unit_price": {
        "unit_price", "unitprice", "price", "rate", "unit_rate", "cost",
        "selling_price", "sale_price", "line_price",
    },
    "total": {
        "total", "amount", "line_total", "gross", "gross_amount", "net",
        "line_amount", "value", "sum", "sales_total",
    },
    "order_id": {
        "order_id", "invoice_no", "invoice_number", "invoice", "receipt_no",
        "receipt_number", "bill_no", "reference", "ref", "transaction_id", "sale_id",
    },
    "vendor": {"vendor", "supplier", "source", "branch"},
    "channel": {"channel", "platform", "source_channel", "sales_channel", "outlet"},
    "payment_method": {
        "payment_method", "payment", "pay_method", "method", "tender", "mode", "paid_via",
    },
    "delivery_fee": {"delivery_fee", "delivery", "shipping", "shipping_fee", "fee"},
}

NUMERIC_TARGETS = {"qty", "unit_price", "total", "order_id", "delivery_fee"}
DATE_RE = re.compile(r"\d")
DATE_HINT_RE = re.compile(r"[/-]|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", re.I)
OPTIONAL_TARGET_THRESHOLD = 1.25


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


def _match_key(name: str) -> str:
    return _snake(name).replace("_", "")


def _column_samples(series: pd.Series, limit: int = 3) -> list[str]:
    out: list[str] = []
    for value in series.dropna().tolist():
        text = str(value).strip()
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _source_kind(series: pd.Series) -> tuple[str, float, float]:
    values = [v for v in series.dropna().tolist() if str(v).strip()]
    if not values:
        return "empty", 0.0, 0.0
    sample = values[: min(6, len(values))]
    numeric_hits = 0
    date_hits = 0
    for value in sample:
        if _to_number(value) is not None:
            numeric_hits += 1
        text = str(value).strip()
        if DATE_RE.search(text) and DATE_HINT_RE.search(text):
            if pd.notna(pd.to_datetime(text, errors="coerce", dayfirst=True)):
                date_hits += 1
    total = len(sample)
    numeric_ratio = numeric_hits / total
    date_ratio = date_hits / total
    if date_ratio >= 0.5:
        return "date", numeric_ratio, date_ratio
    if numeric_ratio >= 0.5:
        return "numeric", numeric_ratio, date_ratio
    return "text", numeric_ratio, date_ratio


def _candidate_score(target: str, source_name: str, kind: str, numeric_ratio: float, date_ratio: float,
                     remembered: str | None = None) -> float:
    target_key = _match_key(target)
    source_key = _match_key(source_name)
    target_syn = TARGET_SYNONYMS.get(target, {target})

    score = SequenceMatcher(None, target_key, source_key).ratio()
    if source_key == target_key:
        score += 1.0
    if source_key in target_syn:
        score += 0.95
    if any(alias in source_key or source_key in alias for alias in target_syn):
        score += 0.55
    if source_key.replace(target_key, "") == "" or target_key.replace(source_key, "") == "":
        score += 0.35

    if target == "order_id":
        if "invoice" in source_key or "receipt" in source_key or "ref" in source_key or "order" in source_key:
            score += 1.2
        if kind == "date":
            score -= 1.0
        elif kind == "numeric":
            score += 0.15

    if target in NUMERIC_TARGETS:
        score += numeric_ratio * 0.35
        if kind == "numeric":
            score += 0.35
        elif kind == "text":
            score -= 0.2
    elif target == "date":
        score += date_ratio * 0.4
        if kind == "date":
            score += 0.45
        elif kind == "numeric":
            score -= 0.45
    else:
        if kind == "text":
            score += 0.15
        elif kind == "numeric":
            score -= 0.1

    if remembered and _match_key(remembered) == source_key:
        score += 0.6

    return score


def _map_columns(df: pd.DataFrame, remembered: dict[str, str] | None = None) -> tuple[dict[str, str], dict]:
    sources = []
    for col in df.columns:
        kind, numeric_ratio, date_ratio = _source_kind(df[col])
        sources.append({
            "name": col,
            "normalized": _snake(col),
            "samples": _column_samples(df[col]),
            "kind": kind,
            "numeric_ratio": numeric_ratio,
            "date_ratio": date_ratio,
        })

    selected: dict[str, str] = {}
    used: set[str] = set()
    remembered = remembered or {}
    target_order = MAPPING_COLUMNS

    mapping_rows = []
    for target in target_order:
        candidates = []
        for source in sources:
            score = _candidate_score(
                target,
                source["name"],
                source["kind"],
                source["numeric_ratio"],
                source["date_ratio"],
                remembered=remembered.get(target),
            )
            candidates.append({
                "source": source["name"],
                "score": round(score, 3),
                "kind": source["kind"],
                "samples": source["samples"],
                "available": source["name"] not in used,
            })
        candidates.sort(key=lambda item: (item["score"], item["available"]), reverse=True)
        chosen = None
        for candidate in candidates:
            if candidate["source"] not in used:
                chosen = candidate["source"]
                used.add(chosen)
                break
        if chosen is None and candidates:
            chosen = candidates[0]["source"]
        top_score = candidates[0]["score"] if candidates else 0.0
        target_keys = {_match_key(a) for a in TARGET_SYNONYMS.get(target, {target})}
        if target in REQUIRED_COLUMNS or target == "order_id":
            if chosen is not None:
                selected[target] = chosen
        mapping_rows.append({
            "target": target,
            "label": target.replace("_", " ").title(),
            "selected": chosen,
            "candidates": candidates,
        })

    return selected, {"sources": sources, "targets": mapping_rows}


def infer_column_mapping(df: pd.DataFrame, remembered: dict[str, str] | None = None) -> dict:
    selected, details = _map_columns(df, remembered=remembered)
    missing = [c for c in REQUIRED_COLUMNS if c not in selected]
    essential_missing: list[str] = []
    if "total" not in selected:
        total_candidates = [s for s in details["sources"] if s["kind"] == "numeric"]
        if not total_candidates:
            essential_missing.append("total")
    if "qty" not in selected and not any(s["kind"] == "numeric" for s in details["sources"]):
        essential_missing.append("qty")
    if "unit_price" not in selected and not any(s["kind"] == "numeric" for s in details["sources"]):
        essential_missing.append("unit_price")
    if "date" not in selected and not any(s["kind"] in {"date", "text"} for s in details["sources"]):
        essential_missing.append("date")
    return {
        "selected": selected,
        "missing": missing,
        "essential_missing": essential_missing,
        "sources": details["sources"],
        "targets": details["targets"],
    }


def _apply_mapping(df: pd.DataFrame, column_map: dict[str, str] | None = None) -> pd.DataFrame:
    if column_map is None:
        column_map = infer_column_mapping(df)["selected"]
    normalized = {_snake(c): c for c in df.columns}
    rename: dict[str, str] = {}

    for target, source in column_map.items():
        if source not in df.columns:
            source = normalized.get(_snake(source), source)
        if source not in df.columns:
            continue
        rename[source] = target

    for col in df.columns:
        if col not in rename:
            rename[col] = _snake(col)

    return df.rename(columns=rename)


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


def clean(df: pd.DataFrame, column_map: dict[str, str] | None = None) -> tuple[pd.DataFrame, CleanReport]:
    rep = CleanReport(rows_in=len(df))

    original_columns = list(df.columns)
    if column_map is None:
        inferred = infer_column_mapping(df)
        column_map = inferred["selected"]
        if inferred["essential_missing"]:
            raise MissingColumnsError(REQUIRED_COLUMNS, original_columns)

    df = _apply_mapping(df, column_map=column_map)
    rep.columns_renamed = {k: v for k, v in zip(original_columns, df.columns) if k != v}

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
