# Routing evaluation: metric-vs-dimension confusion, and the fix

Date: 2026-08-05
Test set: `worker/tests/test_routing.py`, 41 questions across all 8 categories,
16 deliberately awkward/indirect phrasings, unmodified across every run below.
Model: SmolLM3-Q4_K_M via llama_cpp, CPU only, 4 threads, temperature 0.0.

## Diagnosis

An earlier fix (see routing bug write-up) brought overall routing accuracy to
78% (32/41), but two categories stayed weak: `by_vendor` (1/5, 20%) and
`by_channel` (2/5, 40%). The failures were not random — they shared one
pattern: **the classifier got the metric right and the dimension wrong.**

> "Which vendor brings in the most revenue?" → routed to `top_products`

The model correctly heard "most revenue" (a ranking) but attached it to the
wrong axis — products instead of vendors. The 8-category label set asks the
model to get two independent things right in a single choice: which slice of
the business the question is about (dimension), and what kind of question it
is (a ranking, a trend, a total). The category wording overlaps enough
("best/strongest/highest" appears under `top_products`, and ranking language
applies equally to `by_vendor`/`by_channel`/`by_payment`) that a small model
conflates them.

Two fixes were built behind a flag and measured against the same 41-question
set, unmodified, before either was picked.

## Results

| Mode | Overall | Mean latency | Total latency |
|---|---|---|---|
| baseline (single call, 8 categories) | 32/41 (78%) | 2.60s/q | 106.4s |
| Fix A — two-stage classification | 21/41 (51%) | 10.19s/q | 417.7s |
| Fix B — dimension hint, single call | 34/41 (83%) | 3.13s/q | 128.3s |
| Fix A + B combined | 23/41 (56%) | 8.78s/q | 360.0s |

Per-category breakdown, all four modes:

| Category | baseline | two_stage | hint | two_stage+hint |
|---|---|---|---|---|
| bottom_products | 5/5 (100%) | 0/5 (0%) | 5/5 (100%) | 0/5 (0%) |
| by_channel | 2/5 (40%) | 4/5 (80%) | 3/5 (60%) | 5/5 (100%) |
| by_payment | 4/5 (80%) | 4/5 (80%) | 5/5 (100%) | 3/5 (60%) |
| by_vendor | 1/5 (20%) | 2/5 (40%) | 1/5 (20%) | 4/5 (80%) |
| monthly_trend | 5/5 (100%) | 1/5 (20%) | 5/5 (100%) | 1/5 (20%) |
| quiet_days | 5/6 (83%) | 2/6 (33%) | 5/6 (83%) | 2/6 (33%) |
| revenue_summary | 5/5 (100%) | 5/5 (100%) | 5/5 (100%) | 5/5 (100%) |
| top_products | 5/5 (100%) | 3/5 (60%) | 5/5 (100%) | 3/5 (60%) |

## Fix A — two-stage classification

Call 1 asked which dimension the question concerns (product / vendor /
channel / payment / time / day-of-week / overall). Call 2 asked which view
it wants (best / worst / trend / summary), independently of call 1. Plain
code composed the pair into a handler name — no LLM call decided the
mapping.

This fixed exactly the categories it targeted: `by_vendor` 20%→40%,
`by_channel` 40%→80%. That confirms the diagnosis was correct for those two.

But it broke categories the baseline already had at 100%: `bottom_products`
collapsed to 0%, `monthly_trend` to 20%, `quiet_days` to 33%, `top_products`
to 60%. Reading the transcripts, the second call ("view") is asked with no
memory of what dimension call 1 picked, and for a large share of questions
that don't name an explicit entity — "What's not selling well?", "Is my
revenue growing or shrinking?" — the dimension call itself drifted toward the
generic `overall` label rather than the specific one, because `overall` /
"general performance" is a safe-sounding catch-all next to any business
question once the choice is split this finely. Splitting a working 8-way
decision into two smaller decisions didn't just add a second chance to be
right — the two chances now have to both land, and the model's failure mode
under this framing was to hedge toward the vaguest option. Net: fixing the
targeted weak spot cost four previously-solid categories, and overall
accuracy fell from 78% to 51%.

Latency was also worse than the "obvious" 2x: 10.19s/q vs 2.60s/q baseline,
~3.9x. Each stage re-primes its own prompt independently (no shared context
between the two calls), so the cost compounds beyond just "twice as many
tokens generated."

## Fix B — dimension hint, single call

Same single-call structure as baseline. A plain keyword lookup over the
question text (`vendor`, `branch`, `outlet`, `supplier` → vendor; `channel`,
`app`, `walk-in`, `online`, `delivery` → channel; `payment`, `cash`,
`transfer`, `card`, `pos` → payment) adds one optional line to the existing
prompt: *"Hint: the wording of this question leans toward 'by_X' — weigh
that, but pick whichever category actually fits best."* The model still
makes the final choice and can ignore the hint; nothing here checks the
keyword list against `HANDLERS` or decides a route by itself.

This preserved everything the baseline already had solved (every
100%-scoring category stayed 100%) and fixed two of the baseline's nine
misses outright: a `by_channel` question and a `by_payment` question, lifting
those categories to 60% and 100%. `by_vendor` did not improve (stayed at
20%) — see below. Overall: 78% → 83%, at roughly the same latency as
baseline (3.13s/q vs 2.60s/q — the hint adds a couple of lines of prompt
text, not a second model call).

## Fix A + B combined

Folding the same hint into Fix A's dimension call fixed `by_vendor` (20%→80%)
and `by_channel` (40%→100%) — the hint clearly helps the dimension call do
its one job. But it inherited Fix A's structural problem on every other
category (`bottom_products` 0%, `monthly_trend` 20%, `quiet_days` 33%,
`top_products` 60%), because the second, hint-free "view" call still drifts
toward `overall` the same way it does in Fix A alone. Overall: 56%, still
well below baseline.

## Recommendation

**Ship Fix B.** It is the only candidate that improves on baseline rather
than trading one weak spot for others, it does so at roughly baseline
latency (no second model call), and it required no change to the routing
architecture — only additional context in the existing prompt. Fix A's
core idea (separate the dimension decision from the metric decision) is
sound in isolation, evidenced by how much it and the combined variant
improved `by_vendor`/`by_channel` specifically, but splitting the full
8-category decision into two independently-answered calls introduces a new
failure mode (drift toward the generic `overall` label) that costs more
accuracy than it recovers. It is not a viable production path without
further redesign (e.g. giving the view call the dimension as context, or
replacing "overall" as a default), which is out of scope here.

Fix B is now the only routing path in `explain.py` — `two_stage` and the
`mode` flag have been removed rather than kept as dead code.

## What's still wrong at 83%

Two categories keep the score below ~90%, and both fit the original
diagnosis: the model over-weighs the ranking language ("most", "best",
"performs best") and under-weighs the dimension word even when it's present
in the question, or misses it when the dimension is implied rather than
named:

- `by_vendor` (1/5, 20%) — "Which vendor brings in the most revenue?" still
  routes to `top_products` even with the word "vendor" right there and the
  hint firing; "most revenue" is apparently the stronger signal to this
  model than an explicit dimension noun next to it. "Which branch is doing
  best?" returns no valid label at all (`branch` isn't in the hint word list
  — a real gap, not just a stubborn model). "Break down sales by outlet."
  goes to `by_channel` — outlet and channel are close enough in the model's
  training that the hint (which does cover "outlet") doesn't fully separate
  them from `by_channel`'s own vocabulary.
- `by_channel` (3/5, 60%) — "Are online orders bigger than in-store ones?"
  and "Where are most of my orders actually coming from?" both lack a
  channel-family keyword the hint list currently catches ("online" is
  covered, but the question emphasizes "orders" and "bigger", steering the
  model toward `top_products`/`monthly_trend` instead).
- `quiet_days` (5/6, 83%) — "Is it even worth opening on Mondays?" has no
  day-of-week or "quiet/dead" vocabulary at all; it's a genuinely indirect
  phrasing with nothing lexical to hook a hint on, and the model reads it as
  a trend question instead.

83% does not clear the ~90% bar. The remaining misses are concentrated in
`by_vendor` specifically, where the hint fires but the model overrides it —
a prompt-engineering ceiling, not something a bigger hint word list alone
will fix.

---

## Follow-up experiments: category naming and scope reduction

Two further experiments, run in sequence, each measured against the same
question set (rename only where noted — no wording changes, no new
keywords, no tuning to results) before any decision was made.

### Experiment 1 — rename categories for parallel structure

Diagnosis: every `by_vendor` failure above had "vendor", "branch" or
"outlet" in the question and the hint firing, and still lost to
`top_products`. `top_products` and `by_vendor` both mean "ranking by
revenue" and differ only in what's ranked, but `top_products` reads as a
generic best-things bucket next to a dimension-scoped label like
`by_vendor` — a naming asymmetry, not a vocabulary gap.

Renamed for parallel structure, so the dimension is explicit in every label
and none of them reads as a catch-all:

| Old | New |
|---|---|
| `top_products` | `ranking_by_product` |
| `bottom_products` | `worst_by_product` |
| `by_vendor` | `ranking_by_vendor` |
| `by_channel` | `ranking_by_channel` |
| `by_payment` | `ranking_by_payment` |
| `monthly_trend`, `quiet_days`, `revenue_summary` | unchanged |

Rename only — `CATEGORIES` descriptions, `HANDLERS`, and the test set's
expected labels were updated to match; no keyword or logic changes.

**Result: 39/41 (95%)**, mean latency 3.55s/q.

| Category | Score |
|---|---|
| `ranking_by_vendor` | 5/5 (100%) |
| `ranking_by_channel` | 5/5 (100%) |
| `ranking_by_payment` | 5/5 (100%) |
| `monthly_trend` | 5/5 (100%) |
| `quiet_days` | 6/6 (100%) |
| `revenue_summary` | 5/5 (100%) |
| `ranking_by_product` | 4/5 (80%) |
| `worst_by_product` | 4/5 (80%) |

`ranking_by_vendor` went from 20% to 100% — the naming-collision diagnosis
was correct, and it was the dominant cause of the category's failures, not
a vocabulary or hint problem. `by_channel`/`ranking_by_channel` and
`by_payment`/`ranking_by_payment` also reached 100%.

Two *different* misses appeared that weren't present before, on categories
that were previously perfect:

- "What should I make sure I never run out of?" (expected
  `ranking_by_product`) → `worst_by_product`
- "What's just sitting on the shelf gathering dust?" (expected
  `worst_by_product`) → `quiet_days`

Neither question mentions a competing category's vocabulary in any obvious
way; at temperature 0.0 the changed prompt (different label tokens, same
positions) landed on a different deterministic output for these two. Net
effect is still strongly positive — 78% → 95%, +9 correct, -2 previously
correct — but it's not a free lunch with zero side effects.

### Experiment 2 — drop `ranking_by_vendor` entirely (applied on top of Experiment 1)

Rationale offered: Ledgerit is pitched at a single small business; vendor/
branch comparison is a multi-outlet use case the demo and competition
prompts won't exercise. Removed `ranking_by_vendor` from `CATEGORIES` and
`HANDLERS`, and its 5 questions from the test set (36 remain).

**Result: 34/36 (94%) raw**, mean latency 4.54s/q.

| Category | Score |
|---|---|
| `ranking_by_channel` | 5/5 (100%) |
| `ranking_by_payment` | 5/5 (100%) |
| `monthly_trend` | 5/5 (100%) |
| `quiet_days` | 6/6 (100%) |
| `revenue_summary` | 5/5 (100%) |
| `ranking_by_product` | 4/5 (80%) |
| `worst_by_product` | 4/5 (80%) |

The same two Experiment-1 misses recur unchanged (neither involves vendor
wording, so removing the category doesn't touch them). No new failures
appeared, and none of the surviving categories' scores moved, which is what
you'd expect — removing a category that was already at 100% shouldn't
affect how the model resolves questions about the other seven.

**On comparability:** 34/36 (94%) is measured over a smaller, easier
question set — it is not directly comparable to the 41-question figures
above. If the 5 removed vendor questions are counted as failures (i.e.
scored against the original 41), the comparable figure is **34/41 (83%)**
— identical to Fix B's original 83%, though via a different failure set
(no vendor misses at all this time; the two Experiment-1 misses plus the 5
now-unaskable vendor questions).

### Summary of all measurements

| Stage | Score | Comparable to 41 | Mean latency |
|---|---|---|---|
| Current (Fix B, original names) | 34/41 (83%) | 83% | 3.13s/q |
| After Experiment 1 (rename) | 39/41 (95%) | 95% | 3.55s/q |
| After Experiment 2 (rename + drop vendor) | 34/36 (94%) raw | 83% (vendor Qs scored as failures) | 4.54s/q |

**State left in the repo:** Experiment 1 (rename) only. `ranking_by_vendor`
is back in `CATEGORIES`/`HANDLERS` and its 5 questions are back in the test
set — Experiment 2's removal was measured, then reverted, and is not
applied. Whether to drop vendor analysis from the product is a scope
decision, not a routing-accuracy decision: on the numbers alone there is no
accuracy reason to drop it (it scores 100% post-rename), so the case for
removal would have to rest on product scope, not on this metric.

## 2026-08-06 — "best sellers" gap: a vocabulary collision, and a stale headline number

A demo chip reading "What are my best sellers?" was wired to the real
`/api/ask` endpoint and misrouted to the `revenue_summary` fallback instead
of `ranking_by_product`. That exact phrasing was never in the 41-question
set — the closest existing case, "What are my best-selling products?", is a
different surface form. Investigated rather than just swapped the chip's
wording.

**Root cause.** Logged the raw model completion (not just the parsed
label) for the failing question. It reads:

```
bestsellers

I labeled the question as "
```

The model is echoing the literal word **"bestsellers"** straight out of
`CATEGORIES`'s own description line —
`ranking_by_product: ... most popular selling products; bestsellers; what
sells the most; ...` — instead of emitting the label key
`ranking_by_product`. `classify()`'s parser correctly rejects that stray
word (it isn't in `_CATEGORY_LABELS`) and returns `None`. This is not the
model failing to understand the question; it understood it well enough to
find the single most relevant word in the prompt and repeat it back — the
description text just happens to contain a word that reads, to the model,
as more like an answer than a category name.

Tested 7 additional natural phrasings for "top products" that were not
already covered (one more, "Which products make me the most money?", was
tested but not added — it passed, and duplicates the coverage of the
existing "Which items bring in the most money?" case). Every one of the 7
hit the identical failure mode — same "bestsellers"-echo pattern in the raw
completion, confirmed by re-running each 3 times:

| Question | Result | Awkward? |
|---|---|---|
| "What are my best sellers?" | miss (`None`) | no |
| "Show me my best sellers." | miss (`None`) | no |
| "What sells the most?" | miss (`None`) | no |
| "What's my most popular product?" | miss (`None`) | no |
| "What do customers buy most often?" | miss (`None`) | no |
| "What are people buying the most?" | miss (`None`) | yes |
| "What's flying off the shelves?" | miss (`None`) | yes |

None of these are contrived — they're ordinary ways to ask the single
question `ranking_by_product` exists to answer, and none of them are
"awkward" in the deliberately-indirect sense the rest of this test set
uses that tag for. All 7 are now in `CASES`, left in as failures (not
tuned away): see `worker/tests/test_routing.py`.

**Also found while investigating: classification is not fully
deterministic at temperature 0.0.** Repeated calls to `classify()` on the
same question, same process, same everything, occasionally disagree — "What
are my best-selling products?" (an existing, previously-passing case)
returned `ranking_by_product` 4 times out of 5 and `None` once. This is
consistent with known llama.cpp behaviour: multi-threaded matrix
multiplication (`n_threads=4` here) is not bit-associative, so greedy
decoding can land on a different top token run to run when two candidates'
logits are close. It means any single routing run — including every number
in this document — carries some unquantified noise near decision
boundaries; a score reported from one pass is a point estimate, not an
exact figure.

**Also found: the 95% headline above was measured on a different model
file.** This document's header still reads "Model: SmolLM3-Q4_K_M via
llama_cpp" — the original quantization. Production now loads
`smollm3-3b-q3_k_m-templated.gguf` (see the chat-template and quant-adoption
work). The routing suite was never re-run against that file until this
investigation. Neither `explain.py` nor `CATEGORIES` changed in between, so
this isn't the cause of the "bestsellers" collision (that's a static prompt
bug, reproducible on any model), but it does mean the 95% figure was never
actually validated against what ships. `explain.py`'s `MODEL_PATH` constant
also still points at the old
`~/adtc/adtc-2026-submission-template/model/...` location rather than
`worker/model/...` — both files are currently present and the same size, so
this did not affect today's measurement, but it's a separate piece of
leftover state from the quant-adoption step worth cleaning up.

**Honest re-measurement, full 48-question set (41 original + 7 new),
current production model, one run:**

```
Overall: 37/48 (77%)
```

| Category | Score |
|---|---|
| `monthly_trend` | 5/5 (100%) |
| `quiet_days` | 6/6 (100%) |
| `ranking_by_channel` | 5/5 (100%) |
| `ranking_by_payment` | 5/5 (100%) |
| `ranking_by_vendor` | 4/5 (80%) |
| `revenue_summary` | 5/5 (100%) |
| `worst_by_product` | 4/5 (80%) |
| **`ranking_by_product`** | **3/12 (25%)** |

`ranking_by_product` alone accounts for 9 of the 11 total misses. The other
two categories' misses are the pre-existing Experiment-1 side effects noted
above ("never run out of" → `worst_by_product`; vendor "buying the most
product from" → `None`) — unrelated to this investigation, still open.

This is not tuned to look worse than it is, the same way the 95% figure
above was not tuned to look better: the 7 new questions were chosen before
running them, by asking "how would someone actually phrase this," not by
searching for phrasings that fail. It happens that 7 of 8 candidates tried
did fail, which is itself the finding — coverage of the single most likely
real question ("what sells best") was thin, and the one description word
causing it (`bestsellers` in `CATEGORIES`) is a small, localized, and
almost certainly fixable prompt issue, not evidence the model can't do
this task. No fix has been applied here; this section is measurement and
diagnosis only, per instruction.

## 2026-08-07 — fixing the "bestsellers" collision: two structural attempts, one shipped

Directive: restructure so the label is the only plausible output — either
strip description words that compete with the key, or force selection from
an explicit enumerated list. Both were tried and measured; only one shipped.
**Median of 3 runs is reported throughout this section, not a single-run
point estimate** — 2026-08-06 already found classification isn't fully
deterministic at temperature 0.0 even on an unchanged prompt, so any one
run is noise on top of signal. The 48-question test set (41 original + 7
added 2026-08-06) is unmodified.

**Starting point, current production model, median of 3 (re-confirmed
before changing anything):** 33/48 (68.8%) — lower than the single-run 37/48
(77%) reported 2026-08-06, because that was one run; three runs surfaced
more of the pre-existing flakiness the same investigation had already found.

### Attempt 1 — numbered list, model replies with a digit

Rationale: a digit cannot lexically collide with any word in any
description, in this category list or a future one — closes off the whole
failure *class*, not just the one instance of it that was found.
`CATEGORY_LIST` restructured to `(key, description)` pairs with collision
nouns removed ("bestsellers", "underperformers", etc. — describe the
concept, not a name for it); prompt presents them as `1. key: description`
… `8. key: description` and asks for the number only.

**Result: 33/48 (68.8%) median of 3, fully stable (0 flaky).** Fixed the
targeted bug (`ranking_by_product` 3/12 → 11/12) but broke categories that
were previously near-perfect:

| Category | Before | Attempt 1 |
|---|---|---|
| `ranking_by_product` | 3/12 (25%) | 11/12 (92%) |
| `revenue_summary` | 5/5 (100%) | **0/5 (0%)** |
| `monthly_trend` | 5/5 (100%) | 2/5 (40%) |
| `ranking_by_vendor` | 4/5 (80%) | 3/5 (60%) |
| `quiet_days` | 6/6 (100%) | 4/6 (67%) |

Net: **worse than the starting point** (33/48 vs 33/48 — same overall
score, but with previously-solid categories now broken instead of the one
originally-broken one). Logged raw completions to find out why:
`"Is my revenue growing or shrinking?"` and `"Which vendor brings in the
most revenue?"` both returned the literal string `"1. ranking_by_product"`
— the model echoing the *first line of the numbered list verbatim*,
regardless of the question. Enumerated-list formatting introduced a new
failure mode worse than the one it fixed: this model completes a numbered
list by continuing the pattern it sees, not reliably by reasoning about
which number is correct. Reverted — not shipped.

### Attempt 2 — same cleaned descriptions, keep text-key output (shipped)

Isolates the other half of the original directive: keep the plain
`key: description` prompt format (no enumeration, no numbers), remove only
the collision nouns from the description text.

**Result: 45/48 (93.8%) median of 3, fully stable — 0 flaky cases across
all 3 runs** (compare: the *unchanged* prompt had at least one flaky case
per the 2026-08-06 finding). Removing the collision words appears to have
made ties less likely generally, not just fixed the one targeted question.

| Category | Before | Shipped |
|---|---|---|
| `ranking_by_product` | 3/12 (25%) | 11/12 (92%) |
| `worst_by_product` | 4/5 (80%) | 4/5 (80%) |
| `monthly_trend` | 5/5 (100%) | 4/5 (80%) |
| `ranking_by_vendor` | 4/5 (80%) | 5/5 (100%) |
| `ranking_by_channel` | 5/5 (100%) | 5/5 (100%) |
| `ranking_by_payment` | 5/5 (100%) | 5/5 (100%) |
| `quiet_days` | 6/6 (100%) | 6/6 (100%) |
| `revenue_summary` | 5/5 (100%) | 5/5 (100%) |

**This is what's shipped.** `CATEGORY_LIST` in `explain.py` is now a
`(key, description)` list with no collision nouns; `classify()` still asks
for the category name (not a number), unchanged in every other respect —
same single call, same dimension hint, same temperature 0.0.

**One new, real regression, not hidden:** `"Is my revenue growing or
shrinking?"` was passing before (→ `monthly_trend`) and now returns
`revenue_summary`, stable across all 3 runs — logged the raw completion,
it's a clean, deliberate pick, not truncated or malformed output. This is a
genuine close call — the question is arguably about revenue in general as
much as it's about a trend over time — not the same class of bug as the
original collision. Left as-is rather than chased: reactively rewording
descriptions to chase every individual question is how "bestsellers" ended
up in the prompt in the first place. Two idiomatic phrasings added
2026-08-06 also remain unsolved in every configuration tried:
`"What's flying off the shelves?"` and `"What's just sitting on the shelf
gathering dust?"` — genuinely hard, slang-heavy phrasings; not regressions.

**Also fixed:** `explain.py`'s `MODEL_PATH` pointed at the old
`~/adtc/adtc-2026-submission-template/model/` location (2026-08-06 flagged
this as leftover state from the quant-adoption step). Now computed relative
to `explain.py`'s own location — `worker/model/smollm3-3b-q3_k_m-templated.gguf`
— matching where `server.py` and the rest of the submission already look.

### Summary of every measurement in this document

| Stage | Score | Method |
|---|---|---|
| Original 41-question set, original model file | 39/41 (95%) | single run |
| Same, current production model file (2026-08-06) | 37/48 (77%)¹ | single run |
| Same, median of 3 | 33/48 (68.8%) | median of 3 |
| Numbered-digit attempt | 33/48 (68.8%) | median of 3, 0 flaky |
| **Shipped: cleaned descriptions, text-key output** | **45/48 (93.8%)** | **median of 3, 0 flaky** |

¹ 48-question set from this row on (41 original + 7 added 2026-08-06).
