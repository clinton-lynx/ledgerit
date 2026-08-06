"""Generate a deliberately messy sales export, like a real Nigerian SME would keep.

The mess is the point: the cleaning step has to earn its place in the demo.
Run:  python make_sample_data.py
Out:  data/sales_raw.csv
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

PRODUCTS = [
    ("Jollof Rice", 1800), ("Fried Rice", 1800), ("White Rice & Stew", 1500),
    ("Amala & Ewedu", 2000), ("Pounded Yam & Egusi", 2500), ("Eba & Okra", 1500),
    ("Moi Moi", 700), ("Puff Puff (6pcs)", 500), ("Meat Pie", 800),
    ("Chicken (piece)", 1500), ("Beef (piece)", 800), ("Fish (piece)", 1200),
    ("Bottled Water", 200), ("Soft Drink", 400), ("Zobo", 500),
]
VENDORS = ["Munchies", "Alaga Spot", "Jummie Kitchen", "Amala Pavilion", "Butter N Crumbs"]
CHANNELS = ["app", "App", "APP", "walk-in", "Walk In", "walkin", "phone", "Phone"]
PAY = ["transfer", "Transfer", "cash", "Cash", "card", "POS", "pos"]


def messy_date(d: datetime) -> str:
    """One dominant convention, plus a minority of hand-edited rows.

    Real exports are written by one system or one person, so DD/MM/YYYY here
    is consistent. The 20% in other formats stands in for rows someone typed
    or pasted manually later — which is what actually happens.
    """
    r = random.random()
    if r < 0.80:
        return d.strftime("%d/%m/%Y")
    if r < 0.92:
        return d.strftime("%d-%b-%Y")
    return d.strftime("%Y-%m-%d")


def main() -> None:
    start = datetime(2026, 5, 1)
    rows = []
    for day in range(90):
        date = start + timedelta(days=day)
        # Weekends are busier on campus; month-end is quieter (students broke).
        base = 25 if date.weekday() >= 5 else 18
        if date.day > 25:
            base = int(base * 0.6)
        for _ in range(random.randint(base - 5, base + 8)):
            product, unit = random.choice(PRODUCTS)
            qty = random.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
            price = unit
            if random.random() < 0.05:            # occasional price drift
                price = int(unit * random.uniform(0.9, 1.15))
            rows.append({
                "Date": messy_date(date),
                "order id": f"BD{random.randint(10000, 99999)}",
                "Product ": product if random.random() > 0.1 else f"  {product.upper()}  ",
                "Qty": qty,
                "Unit Price (NGN)": price,
                "Total": qty * price,
                "Vendor": random.choice(VENDORS),
                "channel": random.choice(CHANNELS),
                "Payment Method": random.choice(PAY),
                "Delivery Fee": random.choice([0, 0, 200, 300, 500]),
            })

    df = pd.DataFrame(rows)

    # --- inject the kind of damage real files carry -------------------------
    # blank cells
    for col in ["Payment Method", "channel"]:
        idx = df.sample(frac=0.03, random_state=1).index
        df.loc[idx, col] = None
    # duplicated rows (double-entered orders)
    df = pd.concat([df, df.sample(15, random_state=2)], ignore_index=True)
    # a few totals that don't match qty x price (manual entry errors)
    bad = df.sample(8, random_state=3).index
    df.loc[bad, "Total"] = df.loc[bad, "Total"] * random.choice([2, 10])
    # currency symbols in a numeric column
    df["Unit Price (NGN)"] = df["Unit Price (NGN)"].astype(object)
    sym = df.sample(frac=0.04, random_state=4).index
    df.loc[sym, "Unit Price (NGN)"] = df.loc[sym, "Unit Price (NGN)"].apply(lambda v: f"NGN{v:,}")

    df = df.sample(frac=1, random_state=5).reset_index(drop=True)  # shuffle

    Path("data").mkdir(exist_ok=True)
    out = Path("data/sales_raw.csv")
    df.to_csv(out, index=False)
    print(f"wrote {out}  rows={len(df)}  cols={len(df.columns)}")
    print(f"date span: 2026-05-01 .. {(start + timedelta(days=89)).date()}")


if __name__ == "__main__":
    main()
