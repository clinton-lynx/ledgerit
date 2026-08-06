# """Ledgerit — offline bookkeeping worker. Ask questions about a sales file."""
# import sys
# from pathlib import Path

# import pandas as pd

# from analyst import answer, build_index
# from cleaner import clean


# def main() -> None:
#     path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sales_raw.csv")
#     print(f"Loading {path}...")
#     df, report = clean(pd.read_csv(path))

#     print("\n--- Cleaning report ---")
#     for line in report.summary_lines():
#         print(" ", line)
#     if report.total_mismatches:
#         print("\n  Entries that don't add up:")
#         for m in report.total_mismatches[:5]:
#             print(f"    {m['order_id']}: recorded NGN {m['recorded_total']:,.0f}, "
#                   f"expected NGN {m['expected_total']:,.0f}")

#     index = build_index(df)
#     print("\nReady. Ask a question, or 'quit'.\n")

#     while True:
#         try:
#             q = input("> ").strip()
#         except (EOFError, KeyboardInterrupt):
#             break
#         if not q or q.lower() in {"quit", "exit"}:
#             break

#         finding = answer(df, q, index)
#         print("\n" + finding.as_context())
#         print("\nThinking...", end="", flush=True)
#         from explain import explain          # imported late so startup stays fast
#         print("\r" + " " * 12 + "\r", end="")
#         print(explain(finding, q) + "\n")


# if __name__ == "__main__":
#     main()



"""Ledgerit — offline bookkeeping worker. Ask questions about a sales file."""
import sys
from pathlib import Path

import pandas as pd

from analyst import HANDLERS, answer, build_index
from cleaner import clean
from explain import classify, explain


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/sales_raw.csv")
    print(f"Loading {path}...")
    df, report = clean(pd.read_csv(path))

    print("\n--- Cleaning report ---")
    for line in report.summary_lines():
        print(" ", line)
    if report.total_mismatches:
        print("\n  Entries that don't add up:")
        for m in report.total_mismatches[:5]:
            print(f"    {m['order_id']}: recorded NGN {m['recorded_total']:,.0f}, "
                  f"expected NGN {m['expected_total']:,.0f}")

    index = build_index(df)
    print("\nReady. Ask a question, or 'quit'.\n")

    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() in {"quit", "exit"}:
            break

        print("Thinking...", end="", flush=True)
        label = classify(q)
        print("\r" + " " * 12 + "\r", end="")
        route = label if label in HANDLERS else "none (falling back to keyword search)"
        print(f"[routed to: {route}]")

        finding = answer(df, q, index, label=label)
        print(finding.as_context())
        print()
        narration = explain(finding, q)
        print(narration.text)
        if not narration.verified:
            print("(number verification failed even after a retry — see the flag above)")
        print()


if __name__ == "__main__":
    main()