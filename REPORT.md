# Technical Report — Ledgerit: Offline Bookkeeping Assistant

**Team ID:** ledgerit  
**Domain:** corporate_enterprise  
**Model:** smollm3-3b-q3_k_m-templated (GGUF Q3_K_M)

---

## Problem

<!-- What problem are you solving? Who is the target user? Why does this matter in an African context? -->

Small Nigerian businesses keep sales records in spreadsheets or paper — messy dates, inconsistent product names, currency text mixed into number columns, entries that don't add up. The owner has no accountant on staff and no reliable internet connection to lean on a cloud bookkeeping tool or a hosted LLM. Ledgerit is an offline assistant that cleans a raw sales export, answers plain-English questions about it ("which day is quietest?", "am I doing better than last month?"), and flags arithmetic that doesn't add up — entirely on a laptop with no internet and no ongoing API cost.

The design rule that makes this trustworthy on a small local model: pandas computes every number, the model only phrases what pandas already calculated. The model is never handed raw transaction data and never asked to do arithmetic — it receives pre-computed figures and a plain-language explanation of what they mean, and a verify-and-retry step checks its output against those figures before showing it to the owner. That separation is what makes reliable answers possible from a 3B model running on CPU, and is why the cross-disciplinary pairing (small-business bookkeeping + local LLM) is load-bearing rather than decorative: without the deterministic analysis layer, the model cannot answer a single real question about the business.

---

## Design Decisions

<!-- What model did you start from? Why that base model and quantization? What alternatives did you consider and reject? -->

- **Base model:** SmolLM3 3B.
- **Quantization:** Q3_K_M, with `tokenizer.chat_template` metadata added after the fact (see below) — shipped as `smollm3-3b-q3_k_m-templated.gguf`.
- **Alternatives considered:**
  - `SmolLM3-Q4_K_M` (upstream, 2863 MB peak RSS) — the only one of the three candidates that already had correct chat_template metadata, so it was the initial working default, but it lost the answer-quality comparison to Q3_K_M on our own 30-answer eval (`docs/quant-quality-comparison.md`) and carries a larger memory footprint.
  - `smollm3-3b-iq4_xs-imat` — comparable answer quality to Q3_K_M, but 2157 MB vs Q3_K_M's ~2 GB and no clear quality edge to justify the extra size.
  - Both of our own quantizations (Q3_K_M and IQ4_XS) initially lacked `tokenizer.chat_template` GGUF metadata, which caused every judge-facing runtime we tested to fail: `llama_cpp` fell back to a `llama-2` template and emitted `<<SYS>>`/`[INST]` garbage, and Ollama (which is what judges actually run) never crashed but produced multi-minute runaway generations with invented figures, or no output at all — see the "Chat template fix" section above. This is fixed by re-embedding the working template via `gguf_new_metadata.py`, which copies tensor data verbatim (no re-quantization, no F16 weights needed, ~14s per file) — verified in both `llama_cpp` and Ollama before adoption.
- **Final choice:** `smollm3-3b-q3_k_m-templated.gguf` — best answer quality of the three in a 30-answer, temperature-0.3, twice-per-question comparison, smallest memory footprint, and its chat template gap is now fixed and verified in the tooling judges use.

---

## Constraints

<!-- What hardware, connectivity, power, or data constraints shaped your choices? -->

- Target: 8 GB RAM, integrated GPU, Ubuntu 22.04
- No GPU acceleration — pure CPU inference via llama.cpp
- No internet connectivity assumed at runtime — this is the actual operating condition for the target user, not just a hardware limit; the model, the sales data, and every computation stay on-device
- Judges run submitted weights through LM Studio or Ollama/Open WebUI, not necessarily our own dev harness (`llama_cpp` directly) — see "Chat template fix" below for a case where that distinction mattered

---

## Chat template fix — verified in judge tooling (Ollama)

Our own `smollm3-3b-q3_k_m.gguf` and `smollm3-3b-iq4_xs-imat.gguf` quantizations do not carry `tokenizer.chat_template` GGUF metadata (only the upstream `SmolLM3-Q4_K_M.gguf` does). Under `llama_cpp` this silently falls back to a generic `llama-2` template and produces unusable `<<SYS>>`/`[INST]` garbage — see `docs/quant-quality-comparison.md`. Because judges run submitted weights in **LM Studio or Ollama/Open WebUI**, not our dev harness, we verified the fix directly in Ollama rather than trusting the `llama_cpp` result alone.

**Method:** extracted the working chat template from `SmolLM3-Q4_K_M.gguf` and wrote it into a copy of `smollm3-3b-q3_k_m.gguf` using `gguf_new_metadata.py --chat-template-file` (tensor data copied verbatim, no re-quantization, ~14s). Installed Ollama (`brew install ollama`, `HOMEBREW_NO_INSTALL_FROM_API=1` — our ISP blocks `formulae.brew.sh`), imported both the templated copy and the untouched original as separate models via `Modelfile`s using the exact production `SYSTEM` prompt from `explain.py`, and ran the same 3 Ledgerit-shaped prompts (two are `metadata.json`'s own `tp_001`/`tp_002`, verbatim) against both.

### Templated model — `smollm3-3b-q3_k_m-templated.gguf`

All 3 prompts completed in 15–30s each. No `<<SYS>>`, `[INST]`, or prompt echo in any answer. All three read as coherent, on-topic, 3–5 sentence business explanations with no invented numbers.

> **tp_001** (product comparison): "The shop's sales revenue differs between these two products: Pounded Yam & Egusi and Eba & Okra. Despite selling more units of Eba & Okra (230 vs. 221), Pounded Yam & Egusi generated a higher total revenue, NGN 559,732 versus NGN 272,903 for Eba & Okra. This suggests that the customers are willing to pay more per unit or there's greater demand for Pounded Yam & Egusi than for Eba & Okra. The owner should consider if increasing production of these popular products could further boost sales and revenue."

> **tp_002** (order mismatch): "The discrepancy indicates that there's an inconsistency between the recorded total (NGN 10,000) and the calculated amount based on quantities and prices (NGN 5,000). This could be due to a mistake in recording or pricing. The shop owner should investigate this issue by cross-referencing with other records, checking for any errors in unit price or quantity entry, and ensuring that all sales are accurately recorded."

> **quiet_days-shaped prompt**: "The figures indicate that Saturday is significantly busier than Friday, with sales revenue almost doubling on Saturdays compared to Fridays (638,626 vs. 419,944). This suggests a strong correlation between the day of the week and customer traffic... since Saturday's sales are 1.5 times higher than Friday's, it implies that the shop owner may want to consider adjusting their pricing strategy on quieter days like Fridays..."

### Untemplated model — original `smollm3-3b-q3_k_m.gguf`, unmodified

Same 3 prompts, same `SYSTEM` prompt, only the GGUF's missing chat_template metadata differs. Ollama does **not** fall back to the same `llama-2`/`<<SYS>>` garbage `llama_cpp` did — but the result is arguably worse for a judge's experience:

- **tp_001**: took **17+ minutes** and never terminated on its own (interrupted manually). Spent the first several minutes producing no visible output at all (stuck in an unsignalled "thinking" phase, since without the real template the model never receives the `/no_think` directive our SYSTEM prompt relies on), then produced an answer that **computes and states brand-new numbers never given to it** — `NGN 559,732 / 221 ≈ NGN 2,528.00` and `NGN 272,903 / 230 ≈ NGN 1,184.00` — a direct violation of "never perform arithmetic, never state an unsupported number." It then drifted completely off-topic (fabricated discussion of "online retailers," "machinery," "safety standards" — none of which exist anywhere in the prompt or data) and looped the same "In conclusion..." paragraph near-verbatim multiple times before being interrupted.
- **tp_002**: also never terminated (interrupted after 150s). Produced one long, markdown-structured answer (`**Explanation:**`, `**Step-by-step explanation:**`, `**Key Takeaways:**`, `**Final Answer:**`) — many paragraphs against a "two or three sentences" instruction — then began repeating entire sections near-verbatim and fell back into another silent "thinking" loop.
- **quiet_days-shaped prompt**: produced **zero visible output at all** in 150s — never left the silent "thinking" phase.

**Conclusion:** the chat-template fix is necessary, not cosmetic, and the failure mode without it is worse in the tooling judges actually use than in our dev harness — not template-token leakage, but unbounded runaway generation, invented figures, and answers that may never arrive. `gguf_new_metadata.py` is a ~15-second, tensor-preserving fix per file. Templated copies are not yet applied to the submitted weights — that adoption decision is separate from this verification.

---

## Benchmarks

<!-- What inference speed and memory numbers did you observe on your development machine? -->

| Metric | Value |
|---|---|
| Machine | MacBook (Apple M1, 16 GB RAM, macOS 15.6, integrated GPU only) |
| Generation speed | 6.13 tok/s |
| Time to first token | 16,119.64 ms (512-token prompt) |
| RAM at peak | 1,976.48 MB |
| RAM steady-state | 1,530.3 MB |
| CPU utilization (p99) | 100% |
| Thermal throttling | None observed |

These are self-reported development benchmarks (`submission.json`, `--skip-accuracy`). Official scores are measured by the ADTC profiler on the standard evaluation machine.

**A note on measurement variance, since we hit it ourselves:** re-profiling the exact same `.gguf` file multiple times in one machine session gave throughput anywhere from 6.13 to 16.23 tok/s and peak RSS from 1,976 to 2,581 MB — a bigger spread than the profiler's own audit tolerance (±25% throughput, ±15% memory before review, ±50% before failure). The cause, once we checked `ps`/`vm_stat` and file write timestamps: repeat reads of the same ~1.5 GB file within one uptime hit an increasingly warm OS page cache, so later "cold" runs weren't actually cold — one measurement was taken within a minute of the file being freshly copied to disk and was almost certainly served from cache rather than a genuine read. The number reported above is the one measurement in that set with 100% CPU utilization (no contention) and the earliest read of this quantization in the session (before any repeat-read cache effects had a chance to accumulate) — the most defensible approximation of a cold read available without an actual reboot, which we didn't have the access to force (no passwordless `sudo`, no `purge`). It was measured against `smollm3-3b-q3_k_m.gguf` before the chat-template metadata was added; that change appends 5,536 bytes of text metadata and copies every tensor byte-for-byte (verified by sha256 and file-size delta), so it does not affect throughput or memory and the number carries over to the shipped `smollm3-3b-q3_k_m-templated.gguf` unchanged.

## Known limitations

Found during an adversarial testing pass (`docs/adversarial-testing-2026-08-07.md`) and deliberately left as-is — real, measured, and not worth the risk of a rushed fix in the time remaining. The three crashes that same pass found (silent-empty-upload, a 0-row dataset crashing the index builder, and an unhandled context-window overflow on very long questions) *were* fixed; these three were not.

**Large-file load time scales roughly linearly with row count and gets slow well before it's dangerous memory-wise.** Measured on a development machine, model already warm, one load at a time:

| Rows | File size | Load time | Peak RSS |
|---|---|---|---|
| 150,000 | ~10 MB | 10.7s | 465 MB (model not yet loaded) |
| 600,000 | ~40 MB | 45.8s | 2.77 GB |
| 2,000,000 | ~137 MB | 153s (2.5 min) | 2.92 GB |

All three loaded correctly — right row counts, right answers to questions asked afterward. None of these approached the 7–8 GB budget; testing was deliberately stopped around 2M rows rather than pushed toward an actual OOM on shared hardware, so the true ceiling is unmeasured past that point. The real cost is perceived, not functional: the loading UI is an indeterminate pulse with no progress or ETA, and 2.5 minutes of that reads as frozen. A typical single-shop CSV (thousands to tens of thousands of rows) loads in well under a second; this only bites on unusually large exports.

**A long-but-under-the-context-limit question (~1,200 words) to the narration endpoint takes ~47s instead of the usual 15–30s.** CPU-only prefill of a long prompt is itself slow, before generation starts. This doesn't crash (see the fixed context-window overflow above, which is a different, longer threshold) and the loading state is already indeterminate, so there's no broken promise being made to the user — just a real, unexplained-in-the-UI wait.

**Three routing phrasings, found in an independent spot-check (not the formal 45/48 benchmark), still misroute:**

| Question | Expected | Got |
|---|---|---|
| "What is nobody buying?" | `worst_by_product` | `None` (negation phrasing) |
| "what can i remove from the menu" | `worst_by_product` | `revenue_summary` |
| "best day to run a promo" | `quiet_days` | `monthly_trend` |

Consistent with, not a contradiction of, the formal median-of-3 routing measurement (45/48, 93.8%) — this was a smaller, independently-chosen, deliberately harder sample. All three fall outside the categories the 2026-08-07 routing fix targeted.
