"""Which SmolLM3 quantization gives the best ANSWERS — not just the fastest.

Telemetry (tokens/sec, memory footprint) is already measured elsewhere. This
script is the tiebreaker: half the competition score is a human panel reading
model responses, so this captures actual narrations side by side, question by
question, for the three candidate quantizations:

    SmolLM3-Q4_K_M.gguf           8.26 tok/s, 2863 MB
    smollm3-3b-q3_k_m.gguf        6.13 tok/s, 1976 MB
    smollm3-3b-iq4_xs-imat.gguf   6.04 tok/s, 2157 MB

IMPORTANT — chat template workaround, read before changing this file:
Only SmolLM3-Q4_K_M.gguf carries `tokenizer.chat_template` metadata. The
other two GGUFs have none, so llama_cpp's create_chat_completion() silently
falls back to a generic "llama-2" template (<<SYS>>...<</SYS>> [INST]...
[/INST]) instead of SmolLM3's actual ChatML-style format. The model was
never trained on that format, so it doesn't recognise the turn boundaries
and either echoes the raw prompt back or degenerates into repeating
"<<SYS>>" until it hits max_tokens — every single one of its outputs is
unusable garbage, for both under-templated models, on every question. This
was caught by hand-inspecting the first raw run of this script (see
docs/quant-quality-comparison.md's "chat template bug" section) and
confirmed by loading each GGUF and checking `llm.metadata` and
`llm.chat_format` directly.
    A raw quality comparison run through create_chat_completion() as-is
would therefore not measure quantization quality at all — it would measure
"has chat_template metadata" vs "doesn't", which tells you nothing about
which model is better once correctly prompted. So: this script extracts the
one working chat_template (from SmolLM3-Q4_K_M, the reference) and renders
it itself via jinja2, then calls the raw completion API (create_completion)
for ALL THREE models uniformly, bypassing llama_cpp's per-file chat-format
auto-detection entirely. This makes the comparison apples-to-apples: same
template, same tokenizer family (all three are the same base model, just
quantized differently), only the weights differ.
    This workaround lives ONLY in this script. It does not change how
explain.py behaves in production — if either alternate quantization is
adopted via LEDGERIT_MODEL_PATH, this same chat-template gap must be fixed
there too (e.g. by re-exporting the GGUF with correct metadata, or by
porting this script's manual-render approach into explain.py) or production
answers will be the same garbage this script had to work around.

Design:
  - The five Findings (the deterministic, pandas-computed facts) are computed
    ONCE, up front, and reused for every model. Only the narration varies —
    the underlying facts never do, so this measures answer quality in
    isolation, not routing or arithmetic (both handled elsewhere and are
    model-independent by construction).
  - Each question is asked twice per model (temperature 0.3, not 0.0, so
    repeat runs can legitimately disagree) so inconsistency is visible
    rather than papered over by a single sample.
  - Each model is loaded once and reused for all 10 calls (5 questions x 2
    runs) — no reload per question. Models are visited one at a time;
    explain.py's _load_llm has maxsize=1, so requesting a new path evicts
    the previous model (freed by ordinary GC) rather than holding several
    2-3 GB models in RAM at once, matching the 8 GB target machine.
  - Hallucination check + retry: every generation goes through explain.py's
    verify_and_retry() — the SAME verification code path production uses,
    not a local reimplementation. A number in the answer unsupported by the
    context triggers one retry with a stronger instruction; if the retry
    still has unsupported numbers, the final text carries a visible flag
    (Narration.verified is False) rather than silently passing. See
    explain.py's "Number verification" section for why this exists.

Run directly:  python3 tests/compare_quants.py
Long-running (~30 real generations, up to 300 tokens each, plus 3 model
loads, plus a retry generation for any answer that fails verification) —
expect several minutes on CPU-only 4-core hardware.
"""
from __future__ import annotations

import gc
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = WORKER_DIR.parent
sys.path.insert(0, str(WORKER_DIR))

import jinja2  # noqa: E402
import pandas as pd  # noqa: E402

from analyst import bottom_products, by_dimension, monthly_trend, quiet_days, top_products  # noqa: E402
from cleaner import clean  # noqa: E402
from explain import SYSTEM, _build_prompt, _load_llm, _strip_think, verify_and_retry  # noqa: E402

MODEL_DIR = Path.home() / "adtc/adtc-2026-submission-template/model"
MODELS = [
    # (display name, filename, telemetry already measured — for the report header only)
    ("SmolLM3-Q4_K_M", "SmolLM3-Q4_K_M.gguf", "8.26 tok/s, 2863 MB"),
    ("smollm3-3b-q3_k_m", "smollm3-3b-q3_k_m.gguf", "6.13 tok/s, 1976 MB"),
    ("smollm3-3b-iq4_xs-imat", "smollm3-3b-iq4_xs-imat.gguf", "6.04 tok/s, 2157 MB"),
]

RUNS_PER_QUESTION = 2
MAX_TOKENS = 300
TEMPERATURE = 0.3   # matches explain.explain()

QUESTIONS = [
    ("what are my best sellers?", lambda df: top_products(df)),
    ("worst sellers", lambda df: bottom_products(df)),
    ("am I doing better than last month?", lambda df: monthly_trend(df)),
    ("which day is quietest?", lambda df: quiet_days(df)),
    ("how do customers pay me?", lambda df: by_dimension(df, "payment_method")),
]

OUT_PATH = REPO_ROOT / "docs/quant-quality-comparison.md"

# --------------------------------------------------------------------------
# Manual chat-template rendering (see module docstring for why)
# --------------------------------------------------------------------------

_JINJA_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
_JINJA_ENV.globals["strftime_now"] = lambda fmt: datetime.now().strftime(fmt)

# HF's chat templates use {% generation %}/{% endgeneration %} to mark the
# assistant span for training-time loss masking. They render no text of
# their own — a plain jinja2.Environment doesn't know the tag and errors on
# it, so strip it before compiling. This does not change the rendered
# output, only whether it compiles outside `transformers`.
_GENERATION_TAG_RE = re.compile(r"\{%-?\s*(?:end)?generation\s*-?%\}")


def find_working_chat_template() -> tuple[str, str]:
    """Return (model_name, template_string) from the first model whose GGUF
    actually carries tokenizer.chat_template metadata."""
    for model_name, filename, _ in MODELS:
        path = MODEL_DIR / filename
        if not path.exists():
            continue
        llm = _load_llm(str(path))
        template = llm.metadata.get("tokenizer.chat_template")
        if template:
            return model_name, _GENERATION_TAG_RE.sub("", template)
    raise RuntimeError(
        "No model in MODELS has tokenizer.chat_template metadata — "
        "cannot run a fair comparison without a known-good template."
    )


def render_prompt(template_str: str, question_prompt: str) -> str:
    template = _JINJA_ENV.from_string(template_str)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question_prompt},
    ]
    return template.render(messages=messages, add_generation_prompt=True)


def narrate(llm, template_str: str, finding, question: str):
    """Render the prompt ourselves and use raw completion — see module
    docstring for why. Verification/retry itself is explain.verify_and_retry,
    not reimplemented here, so this exercises the exact same logic
    production uses. Returns (Narration, total_seconds_across_all_attempts —
    2 generations if a retry happened, 1 otherwise)."""
    context = finding.as_context()
    base_prompt = _build_prompt(finding, question)
    total_time = 0.0

    def generate(prompt_text: str) -> str:
        nonlocal total_time
        t0 = time.perf_counter()
        out = llm.create_completion(
            prompt=render_prompt(template_str, prompt_text),
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stop=["<|im_end|>"],
        )
        total_time += time.perf_counter() - t0
        return _strip_think(out["choices"][0]["text"])

    narration = verify_and_retry(context, base_prompt, generate)
    return narration, total_time


def run() -> None:
    print("Loading and cleaning data...")
    df, _ = clean(pd.read_csv(WORKER_DIR / "data/sales_raw.csv"))

    print("Computing findings (deterministic, model-independent — computed once, reused for every model)...")
    findings = []
    for question, make_finding in QUESTIONS:
        finding = make_finding(df)
        findings.append((question, finding))
        print(f"  {question!r:<38} -> {finding.headline}")

    print("\nLocating a working chat template (see module docstring: 2 of 3 "
          "GGUFs are missing tokenizer.chat_template metadata)...")
    template_source, template_str = find_working_chat_template()
    print(f"  using the chat_template embedded in {template_source} for ALL THREE models "
          f"— same base model + tokenizer family, so this is an apples-to-apples test of "
          f"quantization quality, not of which GGUF happened to keep its chat metadata.")
    gc.collect()

    # question -> model_name -> [ {run, narration, seconds}, ... ]
    results: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    stats: dict[str, dict] = {}

    for model_name, filename, telemetry in MODELS:
        model_path = MODEL_DIR / filename
        if not model_path.exists():
            print(f"\n!! {model_name}: {model_path} not found — skipping")
            continue

        print(f"\n{'=' * 20} {model_name} {'=' * 20}")
        stats[model_name] = {
            "telemetry": telemetry,
            "lengths": [],
            "times": [],
            "unsupported_total": 0,       # numbers unsupported in the FINAL text (post-retry)
            "retried_total": 0,           # answers that needed a retry
            "fixed_by_retry_total": 0,    # retried and ended up verified
            "still_bad_total": 0,         # retried and STILL unverified
            "unsupported_examples": [],
        }

        llm = _load_llm(str(model_path))

        # Warm-up call, outside any timed/reported result.
        t0 = time.perf_counter()
        narrate(llm, template_str, findings[0][1], findings[0][0])
        print(f"  (model load + warm-up call: {time.perf_counter() - t0:.1f}s)")

        for question, finding in findings:
            for run_idx in range(1, RUNS_PER_QUESTION + 1):
                narration, dt = narrate(llm, template_str, finding, question)

                results[question][model_name].append({
                    "run": run_idx, "narration": narration, "seconds": dt,
                })
                s = stats[model_name]
                s["lengths"].append(len(narration.text))
                s["times"].append(dt)
                s["unsupported_total"] += len(narration.unsupported)
                if narration.retried:
                    s["retried_total"] += 1
                    if narration.verified:
                        s["fixed_by_retry_total"] += 1
                    else:
                        s["still_bad_total"] += 1
                if narration.unsupported:
                    s["unsupported_examples"].append(
                        (question, run_idx, narration.unsupported, narration.verified))

                if narration.retried:
                    flag = ("  [retry fixed it]" if narration.verified
                            else f"  [retried, STILL UNVERIFIED: {narration.unsupported}]")
                else:
                    flag = ""
                print(f"  [{question[:32]:<32}] run {run_idx} {dt:5.1f}s "
                      f"len={len(narration.text):<4}{flag}")

        gc.collect()

    write_report(findings, results, stats, template_source)
    print(f"\nWrote {OUT_PATH}")


def write_report(findings, results, stats, template_source) -> None:
    model_names = list(stats.keys())
    lines = []
    lines.append("# Quantization quality comparison")
    lines.append("")
    lines.append(
        "Answer-quality tiebreaker between the three SmolLM3 quantizations under "
        "consideration. Telemetry (speed, memory) is measured separately; this "
        "compares what a human panel would actually read. Each question is run "
        f"{RUNS_PER_QUESTION}x per model against the exact same computed facts "
        "(the Finding is calculated once with pandas and reused across every "
        "model — only the narration varies), so per-model inconsistency is "
        "visible instead of hidden behind a single sample."
    )
    lines.append("")

    lines.append("## Chat template bug (read this first)")
    lines.append("")
    lines.append(
        "Only `SmolLM3-Q4_K_M.gguf` carries `tokenizer.chat_template` metadata. "
        "The other two GGUFs have none — confirmed by loading each and inspecting "
        "`llm.metadata` directly. Without that metadata, llama_cpp's "
        "`create_chat_completion()` silently falls back to a generic **llama-2** "
        "chat format (`<<SYS>>...<</SYS>> [INST]...[/INST]`) instead of SmolLM3's "
        "actual ChatML-style template. The model was never trained on that format: "
        "it doesn't recognise the turn boundaries, so it either echoes the raw "
        "prompt back verbatim or degenerates into repeating `<<SYS>>` until it hits "
        "`max_tokens`. A first raw run of this script through the normal "
        "`explain.explain()` path — i.e. going through llama_cpp's auto-detected "
        "chat format per file — produced unusable output for **every single "
        "answer** from both under-templated models, on every question."
    )
    lines.append("")
    lines.append(
        f"The results below work around this: the one working chat_template (from "
        f"`{template_source}`) is extracted and rendered manually with `jinja2`, then "
        "fed to all three models through the raw completion API "
        "(`create_completion`), bypassing llama_cpp's per-file auto-detection "
        "entirely. All three are the same base model and tokenizer family, so this "
        "makes the comparison apples-to-apples — a test of quantization quality, "
        "not of which GGUF happened to keep its chat metadata."
    )
    lines.append("")
    lines.append(
        "**This workaround lives only in `tests/compare_quants.py`.** It does not "
        "change `explain.py`'s production behaviour. If either alternate "
        "quantization is adopted via `LEDGERIT_MODEL_PATH`, this same "
        "chat-template gap must be fixed there too — either by re-exporting the "
        "GGUF with correct `tokenizer.chat_template` metadata, or by porting this "
        "script's manual-render approach into `explain.py` — or production answers "
        "will be the same garbage this script had to work around."
    )
    lines.append("")

    lines.append("| Model | Telemetry (measured separately) |")
    lines.append("|---|---|")
    for model_name, _, telemetry in MODELS:
        if model_name in stats:
            lines.append(f"| `{model_name}` | {telemetry} |")
    lines.append("")

    lines.append("## Per-model summary")
    lines.append("")
    lines.append("| Model | Mean answer length (chars) | Mean generation time | "
                  "Unsupported numbers (hallucination check) |")
    lines.append("|---|---|---|---|")
    for model_name in model_names:
        s = stats[model_name]
        mean_len = sum(s["lengths"]) / len(s["lengths"]) if s["lengths"] else 0
        mean_time = sum(s["times"]) / len(s["times"]) if s["times"] else 0
        lines.append(
            f"| `{model_name}` | {mean_len:.0f} | {mean_time:.1f}s | "
            f"**{s['unsupported_total']}** across {len(s['times'])} answers |"
        )
    lines.append("")
    lines.append(
        "\"Unsupported numbers\" above is the FINAL count — after every flagged "
        "answer already got one retry with a stronger instruction (see "
        "`explain.verify_and_retry`). It is not the raw first-pass hallucination "
        "rate; the retry table below shows that separately."
    )
    lines.append("")

    lines.append("### Retry outcomes")
    lines.append("")
    lines.append("| Model | Answers needing a retry | Fixed by retry | Still unverified after retry |")
    lines.append("|---|---|---|---|")
    for model_name in model_names:
        s = stats[model_name]
        lines.append(
            f"| `{model_name}` | {s['retried_total']} / {len(s['times'])} | "
            f"{s['fixed_by_retry_total']} | {s['still_bad_total']} |"
        )
    lines.append("")

    any_unsupported = any(stats[m]["unsupported_total"] for m in model_names)
    if any_unsupported:
        lines.append("### Unsupported-number detail")
        lines.append("")
        lines.append(
            "A number is flagged if it appears in the narration but its normalized "
            "form does not appear anywhere in the exact context text "
            "(`finding.as_context()`) given to the model for that call. This is a "
            "heuristic, not a certified proof of hallucination — skim the flagged "
            "answers below before concluding a model invented a figure. 'STILL "
            "UNVERIFIED' means this is the number(s) left in the answer the owner "
            "would actually see, after the retry; anything not marked that way was "
            "fixed by the retry and isn't in the final text."
        )
        lines.append("")
        for model_name in model_names:
            examples = stats[model_name]["unsupported_examples"]
            if not examples:
                continue
            lines.append(f"**`{model_name}`**")
            for question, run_idx, bad, verified in examples:
                status = "fixed by retry, not in final text" if verified else "STILL UNVERIFIED in final text"
                lines.append(f"- {question!r} (run {run_idx}): {bad} — {status}")
            lines.append("")
    else:
        lines.append("No unsupported numbers detected in any final answer, any model.")
        lines.append("")

    lines.append("## Answers by question")
    lines.append("")
    lines.append(
        "Grouped by question, models side by side, so the same question's answers "
        "are directly comparable across models. Text shown is the FINAL text "
        "(after a retry, if one happened)."
    )
    lines.append("")

    for question, finding in findings:
        lines.append(f"### \"{question}\"")
        lines.append("")
        lines.append("*Computed facts given to every model:*")
        lines.append("")
        lines.append("```")
        lines.append(finding.as_context())
        lines.append("```")
        lines.append("")

        for model_name in model_names:
            lines.append(f"**`{model_name}`**")
            lines.append("")
            for entry in results[question][model_name]:
                n = entry["narration"]
                tags = []
                if n.retried:
                    tags.append("retried")
                if not n.verified:
                    tags.append(f"⚠️ unsupported: {n.unsupported}")
                flag = f" — {', '.join(tags)}" if tags else ""
                lines.append(f"- Run {entry['run']} ({entry['seconds']:.1f}s){flag}:")
                lines.append(f"  > {n.text}")
            lines.append("")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines))


if __name__ == "__main__":
    run()
