"""Turn a plain-English question into a computed answer.

Design rule, same as cleaner.py: pandas computes, the model narrates.
This module never calls an LLM. It returns structured facts; explain.py
turns those facts into a sentence.

Retrieval is BM25 over row-level text. Deliberately not embeddings:
an embedding model is another download and another few hundred MB
resident on a machine with 8 GB total. Business records share vocabulary
with the questions asked about them ("jollof", "transfer", "Munchies"),
so lexical matching is a good fit, not a compromise.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import pandas as pd


# --------------------------------------------------------------------------
# BM25 over row text
# --------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(text).lower())


class BM25:
    """Standard BM25. ~40 lines, no dependency, no model download."""

    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [_tokens(d) for d in docs]
        self.n = len(self.docs)
        self.avg_len = sum(len(d) for d in self.docs) / max(self.n, 1)
        self.tf = [Counter(d) for d in self.docs]
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        q = _tokens(query)
        scores: list[tuple[int, float]] = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = self.idf.get(term, 0.0)
                num = tf[term] * (self.k1 + 1)
                den = tf[term] + self.k1 * (1 - self.b + self.b * dl / self.avg_len)
                s += idf * num / den
            if s > 0:
                scores.append((i, s))
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


def build_index(df: pd.DataFrame) -> BM25:
    """One searchable text line per order."""
    cols = [c for c in ("product", "vendor", "channel", "payment_method") if c in df.columns]
    docs = df[cols].astype(str).agg(" ".join, axis=1)
    if "date" in df.columns:
        docs = docs + " " + df["date"].dt.strftime("%B %Y %A").fillna("")
    return BM25(docs.tolist())


# --------------------------------------------------------------------------
# Deterministic analyses
# --------------------------------------------------------------------------

@dataclass
class Finding:
    """A computed fact plus the evidence behind it."""
    question: str
    headline: str
    table: pd.DataFrame | None = None
    facts: dict = None
    # Plain-language statement of what the finding means directionally, e.g.
    # "these are the weakest performers, not a strength." The model has
    # inverted findings before when the facts text was ambiguous (see
    # bottom_products); guidance exists to make misreading it hard even for
    # a small model. Every analysis function below sets this.
    guidance: str | None = None

    def as_context(self) -> str:
        """Compact text form, for handing to the model as grounding."""
        parts = [self.headline]
        if self.facts:
            parts += [f"{k}: {v}" for k, v in self.facts.items()]
        if self.table is not None and not self.table.empty:
            parts.append(self.table.head(10).to_string(index=False))
        if self.guidance:
            parts.append(f"How to interpret this: {self.guidance}")
        return "\n".join(parts)


def revenue_summary(df: pd.DataFrame) -> Finding:
    total = df["total"].sum()
    orders = len(df)
    facts = {
        "total revenue": f"NGN {total:,.0f}",
        "orders": f"{orders:,}",
        "average order value": f"NGN {total / max(orders, 1):,.0f}",
        "period": f"{df['date'].min():%d %b %Y} to {df['date'].max():%d %b %Y}",
    }
    # Split the period in half and compare — cheap, and it turns a static
    # summary into a direction the owner can act on.
    if orders > 20:
        mid = df["date"].min() + (df["date"].max() - df["date"].min()) / 2
        first, second = df[df["date"] <= mid]["total"].sum(), df[df["date"] > mid]["total"].sum()
        if first:
            delta = (second - first) / first * 100
            facts["note"] = (
                f"Second half of the period earned NGN {second:,.0f} vs NGN {first:,.0f} "
                f"in the first half ({delta:+.0f}%)."
            )
    return Finding(
        question="revenue summary", headline="Overall sales performance", facts=facts,
        guidance=(
            "This is the overall snapshot, not a single product or day. If a "
            "second-half-vs-first-half note is present, a positive percentage means "
            "business grew; a negative percentage means it shrank. Do not describe "
            "growth as decline or vice versa."
        ),
    )


def top_products(df: pd.DataFrame, n: int = 5) -> Finding:
    raw = df.groupby("product").agg(revenue=("total", "sum"), units=("qty", "sum"),
                                    orders=("total", "size"))
    t = raw.sort_values("revenue", ascending=False).head(n).reset_index()
    t["revenue"] = t["revenue"].map(lambda v: f"{v:,.0f}")

    facts = {}
    rev_leader, unit_leader = raw["revenue"].idxmax(), raw["units"].idxmax()
    if rev_leader != unit_leader:
        facts["note"] = (
            f"{unit_leader} sells the most units ({raw.at[unit_leader, 'units']:.0f}) but "
            f"{rev_leader} earns the most revenue (NGN {raw.at[rev_leader, 'revenue']:,.0f}). "
            f"Different margin profiles — one is volume, the other is value."
        )
    top_share = raw["revenue"].nlargest(n).sum() / raw["revenue"].sum() * 100
    facts["concentration"] = (
        f"These {n} products are {top_share:.0f}% of total revenue "
        f"across {len(raw)} products sold."
    )
    return Finding(
        question="top products", headline=f"Top {n} products by revenue",
        table=t, facts=facts,
        guidance=(
            "These are the STRONGEST performers, ranked highest revenue first. They "
            "are what is working: candidates to protect stock of, promote further, or "
            "use as an anchor. Do NOT describe them as underperforming or as a risk."
        ),
    )


def monthly_trend(df: pd.DataFrame) -> Finding:
    m = (df.set_index("date").resample("ME")
         .agg(revenue=("total", "sum"), orders=("total", "size")).reset_index())
    m["month"] = m["date"].dt.strftime("%b %Y")
    m = m[["month", "revenue", "orders"]]

    facts = {}
    if len(m) >= 2:
        prev, last = m["revenue"].iloc[-2], m["revenue"].iloc[-1]
        if prev:
            facts["latest change"] = f"{(last - prev) / prev * 100:+.1f}% vs previous month"
        best, worst = m.loc[m["revenue"].idxmax()], m.loc[m["revenue"].idxmin()]
        facts["range"] = (
            f"Best month {best['month']} (NGN {best['revenue']:,.0f}), "
            f"weakest {worst['month']} (NGN {worst['revenue']:,.0f})."
        )
        # Average order value moving independently of revenue is the useful signal.
        aov_first = m["revenue"].iloc[0] / max(m["orders"].iloc[0], 1)
        aov_last = m["revenue"].iloc[-1] / max(m["orders"].iloc[-1], 1)
        if abs(aov_last - aov_first) / max(aov_first, 1) > 0.10:
            facts["basket size"] = (
                f"Average order moved from NGN {aov_first:,.0f} to NGN {aov_last:,.0f} — "
                f"customers are {'spending more' if aov_last > aov_first else 'spending less'} "
                f"per order, separate from how many are buying."
            )
    m["revenue"] = m["revenue"].map(lambda v: f"{v:,.0f}")
    return Finding(
        question="monthly trend", headline="Revenue by month",
        table=m, facts=facts or None,
        guidance=(
            "The table is in calendar order, not ranked. A rising revenue figure "
            "month over month is good news; a falling one is a warning sign. The "
            "'weakest' month in the range note is a low point, not the norm — do not "
            "generalise a single weak month into 'the business is dead'."
        ),
    )

def bottom_products(df: pd.DataFrame, n: int = 5) -> Finding:
    raw = df.groupby("product").agg(revenue=("total", "sum"), units=("qty", "sum"),
                                    orders=("total", "size"))
    t = raw.sort_values("revenue").head(n).reset_index()
    t["revenue"] = t["revenue"].map(lambda v: f"{v:,.0f}")
    tail = raw["revenue"].nsmallest(n).sum() / raw["revenue"].sum() * 100

    facts = {
        "ranking": (
            f"These are the {n} LOWEST-earning products out of {len(raw)} total products "
            f"sold, ordered worst-earner first. They are the bottom of the list, not "
            f"the top."
        ),
        "share": (
            f"Combined, these {n} weakest products brought in only {tail:.0f}% of total "
            f"revenue — a small, not a large, slice of the business."
        ),
    }

    # Low revenue can mean low demand OR low price on a lot of volume — those
    # call for opposite actions (drop vs reprice), so flag the overlap rather
    # than let the model guess which one it's looking at. Soft Drink is the
    # motivating case: bottom-5 by revenue, but also top-5 by units sold.
    high_volume = raw["units"].nlargest(5).index
    overlap = [p for p in t["product"] if p in high_volume]
    if overlap:
        facts["volume warning"] = (
            f"{', '.join(overlap)} rank low on revenue but are also among the top 5 "
            f"products by units sold — low price, not low demand. Repricing is more "
            f"appropriate than discontinuing for these."
        )

    return Finding(
        question="weakest products",
        headline=f"{n} weakest-selling products by revenue (lowest earners)", table=t,
        facts=facts,
        guidance=(
            "These are the WEAKEST performers by revenue. They are candidates to drop, "
            "reprice or promote — not products the business depends on. Do NOT describe "
            "them as a concentration risk, as important to the business, or advise "
            "'reducing dependence' on them; low revenue means the opposite of dependence. "
            "EXCEPTION: if a 'volume warning' fact is present, the products it names sell "
            "in high volume at a low price — they are not low-demand and should NOT be "
            "described as candidates to drop or discontinue. For those specific products, "
            "recommend repricing instead."
        ),
    )

def by_dimension(df: pd.DataFrame, column: str) -> Finding:
    raw = (df.groupby(column).agg(revenue=("total", "sum"), orders=("total", "size"))
           .sort_values("revenue", ascending=False))
    t = raw.reset_index()
    share = t["revenue"] / t["revenue"].sum() * 100
    t["share %"] = share.map(lambda v: f"{v:.1f}")
    t["revenue"] = t["revenue"].map(lambda v: f"{v:,.0f}")

    facts = {}
    leader_share = raw["revenue"].iloc[0] / raw["revenue"].sum() * 100
    if leader_share > 50:
        facts["concentration risk"] = (
            f"{raw.index[0]} alone is {leader_share:.0f}% of revenue — heavy dependence "
            f"on a single {column.replace('_', ' ')}."
        )
    # Average order value differs by segment far more often than owners expect.
    aov = (raw["revenue"] / raw["orders"]).sort_values(ascending=False)
    if len(aov) >= 2 and aov.iloc[0] > aov.iloc[-1] * 1.2:
        facts["basket size"] = (
            f"Orders via {aov.index[0]} average NGN {aov.iloc[0]:,.0f} versus "
            f"NGN {aov.iloc[-1]:,.0f} via {aov.index[-1]}."
        )
    if "unknown" in raw.index:
        pct = raw.at["unknown", "revenue"] / raw["revenue"].sum() * 100
        if pct > 2:
            facts["data gap"] = f"{pct:.0f}% of revenue has no {column.replace('_', ' ')} recorded."
    label = column.replace("_", " ")
    return Finding(
        question=f"breakdown by {column}",
        headline=f"Revenue by {label}",
        table=t, facts=facts or None,
        guidance=(
            f"Rows are ranked highest revenue first, lowest last. The top row is the "
            f"strongest {label}; the bottom row is the weakest. If a 'concentration "
            f"risk' fact is present, that describes over-reliance on the TOP row, "
            f"which is a fragility to flag, not an achievement to praise."
        ),
    )


def quiet_days(df: pd.DataFrame) -> Finding:
    raw = (df.assign(dow=df["date"].dt.day_name())
           .groupby("dow").agg(revenue=("total", "sum"), orders=("total", "size"))
           .sort_values("revenue"))
    d = raw.reset_index()
    d["revenue"] = d["revenue"].map(lambda v: f"{v:,.0f}")

    weekend = raw.loc[raw.index.isin(["Saturday", "Sunday"]), "revenue"].sum() / 2
    weekday = raw.loc[~raw.index.isin(["Saturday", "Sunday"]), "revenue"].sum() / 5

    # BUG this replaces: the old wording put the BUSIEST day first in the
    # sentence ("{index[-1]} earns X against Y on {index[0]}") right after a
    # headline that says "weakest first" — every model in the quant
    # comparison read that ordering as meaning the first-named day was the
    # quiet one. Name each end explicitly so there is no positional cue to
    # misread; same fix pattern as bottom_products' inversion.
    quietest_day, quietest_rev = raw.index[0], raw["revenue"].iloc[0]
    busiest_day, busiest_rev = raw.index[-1], raw["revenue"].iloc[-1]
    facts = {
        "spread": (
            f"QUIETEST day: {quietest_day}, NGN {quietest_rev:,.0f}. "
            f"BUSIEST day: {busiest_day}, NGN {busiest_rev:,.0f}. "
            f"Busiest earns {busiest_rev / max(quietest_rev, 1):.1f}x what quietest does."
        )
    }
    if weekday and abs(weekend - weekday) / weekday > 0.15:
        # Same latent risk here: always naming "weekend" before "weekday"
        # regardless of which actually earns more is only safe by
        # coincidence in today's data. Name the higher-earning one first
        # explicitly instead of relying on dict/sentence order.
        if weekend > weekday:
            higher_label, higher_val, lower_label, lower_val = "weekend", weekend, "weekday", weekday
        else:
            higher_label, higher_val, lower_label, lower_val = "weekday", weekday, "weekend", weekend
        facts["weekend effect"] = (
            f"HIGHER-earning: {higher_label}s average NGN {higher_val:,.0f} per day. "
            f"LOWER-earning: {lower_label}s average NGN {lower_val:,.0f} per day."
        )
    return Finding(
        question="day of week pattern",
        headline="Revenue by day of week, weakest first",
        table=d, facts=facts,
        guidance=(
            "The table is sorted weakest day first, busiest day last — and the 'spread' "
            "fact labels each end explicitly with the words QUIETEST and BUSIEST. The "
            "quietest day has the LOWEST revenue, fewest customers, and is the closest "
            "thing to 'when is the shop dead' — a candidate for shorter hours, a "
            "promotion, or closing altogether. The busiest day has the HIGHEST revenue. "
            "Do NOT swap these two: whichever day is named 'QUIETEST' in the spread fact "
            "is the weak one, not the strong one, no matter which day it appears next to "
            "in the sentence."
        ),
    )

# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------

HANDLERS = {
    "ranking_by_product": top_products,
    "worst_by_product": bottom_products,
    "monthly_trend": monthly_trend,
    "ranking_by_vendor": lambda df: by_dimension(df, "vendor"),
    "ranking_by_channel": lambda df: by_dimension(df, "channel"),
    "ranking_by_payment": lambda df: by_dimension(df, "payment_method"),
    "quiet_days": quiet_days,
    "revenue_summary": revenue_summary,
}


def answer(df: pd.DataFrame, question: str, index: BM25 | None = None,
           classifier=None, label: str | None = None) -> Finding:
    """Route a question to a computation.

    The model classifies into a fixed label set — measured at 13/14 on held-out
    phrasings, which beats a hand-written keyword table that could never cover
    the vocabulary real users bring. Classification is a far easier task than
    open-ended function selection: the model picks a label, it never invents.

    Where classification returns nothing valid, BM25 retrieval answers over the
    most relevant rows rather than guessing at a category.

    `label` lets a caller pass an already-computed classification (e.g. because
    it wants to show the routed category to the user before running the query)
    instead of paying for a second inference call here.
    """
    if label is None and classifier is not None:
        label = classifier(question)
    if label in HANDLERS:
        return HANDLERS[label](df)

    if index is not None:
        hits = index.search(question, top_k=50)
        if hits:
            subset = df.iloc[[i for i, _ in hits]]
            f = revenue_summary(subset)
            f.headline = f"Summary of the {len(subset)} orders most relevant to your question"
            return f
    return revenue_summary(df)