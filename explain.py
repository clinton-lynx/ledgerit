"""Turn computed findings into plain English. The model's only job.

It never sees raw data and never does arithmetic — it receives the numbers
analyst.py already computed and writes a sentence about them. Hallucinated
figures are impossible because no figure is ever the model's to invent.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Default, used when nothing else specifies a model. Overridable two ways,
# without editing this file:
#   - per-call: explain(..., model_path=...) / classify(..., model_path=...)
#   - process-wide: the LEDGERIT_MODEL_PATH environment variable
# The per-call argument wins if both are given. This is what lets
# tests/compare_quants.py load three different quantizations in one process
# without touching this module.
MODEL_PATH = Path(__file__).resolve().parent / "model" / "smollm3-3b-q3_k_m-templated.gguf"


def _resolve_model_path(model_path: str | Path | None) -> str:
    if model_path is not None:
        return str(model_path)
    return os.environ.get("LEDGERIT_MODEL_PATH", str(MODEL_PATH))


SYSTEM = (
    "/no_think\n"
    "You are a bookkeeping assistant for a small Nigerian business. "
    "You are given figures already calculated from the owner's sales records. "
    "Do NOT list or restate the figures — the owner can see them. Instead point "
    "out what is worth noticing: a pattern, a comparison between rows, or "
    "something they should act on. Two or three sentences. "
    "Never perform arithmetic. Never state a number that does not appear "
    "verbatim in the figures given to you. If you want to express a difference "
    "or percentage that is not already provided, describe it in words instead."
)

# (key, description). One rule the description text has to follow, learned
# from a real failure (docs/routing-evaluation.md, 2026-08-06/07): a
# question asking "What are my best sellers?" got completed with the literal
# word "bestsellers", copied out of ranking_by_product's own description
# text, instead of the label key — the model found the single word in the
# prompt that best matched the question and echoed it back, because nothing
# stopped a description word from being a more tempting completion than the
# key itself. No description below contains a standalone noun that is
# itself a plausible one-word answer to a real question in that category
# (no "bestsellers", "underperformers", etc.) — every one describes the
# CONCEPT, not a name for it.
#
# A second structural fix was tried and measured, not just reasoned about:
# moving the model's output space to a number (1-8) instead of the category
# name, on the theory that a digit can never collide with a description
# word. It fixed the original bug but broke worse elsewhere — the model
# frequently just echoed "1. ranking_by_product" (the first line of the
# numbered list) regardless of the actual question, and revenue_summary
# collapsed from 100% to 0%. Measured 33/48 (69%) median over 3 runs,
# *below* the 37/48 (77%) this was meant to improve on. Reverted. The
# cleaned descriptions below, kept with the original text-key output format,
# measured 45/48 (93.8%), stable across 3 runs with zero flaky cases — see
# docs/routing-evaluation.md, 2026-08-07, for both experiments' numbers.
CATEGORY_LIST: list[tuple[str, str]] = [
    ("ranking_by_product", "which products earn the most or sell the most, and which "
     "to stock up on"),
    ("worst_by_product", "which products earn the least or barely sell, and which to "
     "drop, discount, or stop carrying"),
    ("monthly_trend", "how revenue is changing over time — growing, shrinking, or "
     "following a seasonal pattern"),
    ("ranking_by_vendor", "comparing vendors, suppliers, branches, or outlets against "
     "each other"),
    ("ranking_by_channel", "comparing sales channels against each other — app, "
     "walk-in, phone, online, in-store, delivery"),
    ("ranking_by_payment", "comparing payment methods against each other — cash, "
     "transfer, card, POS"),
    ("quiet_days", "which day of the week does best or worst — including when the "
     "shop is emptiest, or when to close early or cut staff hours"),
    ("revenue_summary", "the overall totals and general performance of the business, "
     "the big picture rather than any one slice of it"),
]
_CATEGORY_LABELS = {key for key, _ in CATEGORY_LIST}


def _text_categories() -> str:
    return "\n".join(f"{key}: {desc}" for key, desc in CATEGORY_LIST)


class QuestionTooLongError(ValueError):
    """Raised before ever calling into llama_cpp, when a prompt would
    exceed the model's context window. Left unguarded, llama_cpp raises its
    own exception for this ('Requested tokens (4498) exceed context window
    of 2048') straight out of create_chat_completion — accurate, but not
    something a shop owner would understand, and not caught anywhere
    upstream (see docs/adversarial-testing-2026-08-07.md, #3). Checking the
    token count first means Ledgerit can say something useful instead."""

    def __init__(self, token_count: int, limit: int):
        self.token_count = token_count
        self.limit = limit
        super().__init__(
            "That question is too long for Ledgerit to read in one go. "
            "Try asking something shorter."
        )


# A little headroom beyond the exact count: token-counting the raw message
# text is a close but not perfect stand-in for what create_chat_completion
# actually sends (the chat template wraps it in a handful of its own
# special tokens). Erring toward rejecting a question that would have just
# barely fit is a far smaller problem than the crash this replaces.
_CONTEXT_SAFETY_MARGIN = 64


def _ensure_fits_context(system: str, user: str, max_tokens: int, model_path=None) -> None:
    llm = _llm(model_path)
    count = len(llm.tokenize((system + "\n" + user).encode("utf-8"), add_bos=True))
    limit = llm.n_ctx()
    if count + max_tokens + _CONTEXT_SAFETY_MARGIN > limit:
        raise QuestionTooLongError(count, limit)


@lru_cache(maxsize=1)
def _load_llm(model_path: str):
    """The actual load, cached by resolved path string.

    maxsize=1: only one model is ever resident. Requesting a different path
    evicts the previous one (freed by ordinary garbage collection once
    nothing references it) rather than holding several 2-3 GB models in RAM
    at once — the target hardware has 8 GB total.
    """
    from llama_cpp import Llama
    return Llama(
        model_path=model_path,
        n_ctx=2048,        # matches the profiler's context; keeps RAM predictable
        n_threads=4,       # the ADTC Standard Laptop has 4 cores
        n_gpu_layers=0,    # CPU only, same as the audit
        verbose=False,
    )


def _llm(model_path: str | Path | None = None):
    return _load_llm(_resolve_model_path(model_path))


def _strip_think(text: str) -> str:
    return text.split("</think>", 1)[1].strip() if "</think>" in text else text.strip()


def _build_prompt(finding, question: str) -> str:
    """Factored out of explain() so tests/compare_quants.py can reuse the
    exact production prompt text without duplicating it."""
    return (
        f"The shop owner asked: {question}\n\n"
        f"These figures were calculated from their records:\n\n"
        f"{finding.as_context()}\n\n"
        f"Explain what this means for their business."
    )


# --------------------------------------------------------------------------
# Number verification.
#
# The architecture's whole premise is that pandas computes, the model only
# phrases — "no figure is ever the model's to invent" (see module docstring).
# But the quant comparison measured 1-2 unsupported numbers per 10 answers
# on EVERY model, including the production default: one model computed
# 15 - 5 = 10 itself (small, right answer, still arithmetic it was told
# never to do); another computed a monthly difference and got it wrong by
# 10. The system prompt asking nicely is not enough — this checks after the
# fact and retries rather than trusting the model to have complied.
# --------------------------------------------------------------------------

# Integers, optionally comma-grouped and/or decimal, with an optional
# trailing percent sign: "3,600", "14%", "1.5", "83".
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def _normalize_number(token: str) -> str:
    """'14%' -> '14', '223.0' -> '223', '3,600' -> '3600' — so formatting
    differences between the source facts and the model's paraphrase (e.g.
    dropping a redundant '.0') aren't flagged as unsupported."""
    token = token.rstrip("%").replace(",", "")
    if token.endswith(".0"):
        token = token[:-2]
    return token


def _is_plain_small_count(token: str) -> bool:
    """True for a bare single digit (no comma, no decimal point, no percent
    sign) — the kind of number a model uses as ordinary prose scaffolding
    ('here are 3 things to consider', 'for these 2 products') rather than a
    claimed data figure. Two-plus-digit numbers and anything with currency/
    percent formatting are always checked — that's exactly the shape of the
    real hallucinations found (a computed '10', a computed '155,804')."""
    return token.isdigit() and len(token) == 1


def unsupported_numbers(answer: str, context: str) -> list[str]:
    """Numbers in `answer` (original, unnormalized form) whose normalized
    value does not appear anywhere in `context` — the exact facts text handed
    to the model for this call. Exposed (not underscore-prefixed) so the UI
    and tests can inspect what would be flagged, independent of explain()."""
    context_numbers = {_normalize_number(m) for m in _NUMBER_RE.findall(context)}
    bad = []
    for m in _NUMBER_RE.findall(answer):
        if _is_plain_small_count(m):
            continue
        if _normalize_number(m) not in context_numbers:
            bad.append(m)
    return bad


def _flag_unsupported(text: str, unsupported: list[str]) -> str:
    unique = ", ".join(sorted(set(unsupported)))
    return (
        f"{text}\n\n"
        f"⚠️ Unverified: this answer states a number not found in the computed "
        f"figures ({unique}) — treat it with caution."
    )


def _retry_prompt(base_prompt: str, unsupported: list[str]) -> str:
    unique = ", ".join(sorted(set(unsupported)))
    return (
        f"{base_prompt}\n\n"
        f"Your previous answer stated number(s) that do not appear anywhere in the "
        f"figures above: {unique}. That is not allowed. You may only use numbers "
        f"copied verbatim from the figures given, and you must never calculate a "
        f"new number yourself — not even a simple subtraction. Write your answer "
        f"again without inventing or computing any figure."
    )


@dataclass
class Narration:
    """The model's narration plus what verification found — exposed so the
    UI can show a caveat and tests can assert on it directly, instead of
    verification being an invisible internal step."""
    text: str
    verified: bool
    unsupported: list[str] = field(default_factory=list)
    retried: bool = False


def verify_and_retry(context: str, base_prompt: str, generate) -> Narration:
    """Model-agnostic verify/retry/flag loop.

    `generate(prompt: str) -> str` performs exactly one generation — this
    function doesn't care whether that's llama_cpp's chat-completion API or
    a manually-templated raw completion (see tests/compare_quants.py, which
    has to use the latter for GGUFs missing chat_template metadata but still
    wants this exact verification logic, not a reimplementation of it).
    """
    answer = generate(base_prompt)
    bad = unsupported_numbers(answer, context)
    if not bad:
        return Narration(text=answer, verified=True)

    answer2 = generate(_retry_prompt(base_prompt, bad))
    bad2 = unsupported_numbers(answer2, context)
    if not bad2:
        return Narration(text=answer2, verified=True, retried=True)

    return Narration(text=_flag_unsupported(answer2, bad2), verified=False,
                      unsupported=bad2, retried=True)


def explain(finding, question: str, model_path: str | Path | None = None) -> Narration:
    """finding: an analyst.Finding. Returns a Narration (see above) — not a
    bare string, so callers can see whether verification passed instead of
    silently trusting whatever the model said.

    `model_path` overrides MODEL_PATH/LEDGERIT_MODEL_PATH for this call only
    — every existing caller that omits it keeps current behaviour, aside
    from now getting a Narration back instead of a str (see main.py).
    """
    context = finding.as_context()
    base_prompt = _build_prompt(finding, question)

    def generate(prompt_text: str) -> str:
        # Guards both the initial call and verify_and_retry's retry call —
        # the retry prompt is the original plus more text (the unsupported
        # numbers to fix), so it's never shorter. Same QuestionTooLongError
        # as classify(); a long question can overflow here even when the
        # figures themselves are short.
        max_tokens = 300
        _ensure_fits_context(SYSTEM, prompt_text, max_tokens, model_path)
        out = _llm(model_path).create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt_text},
            ],
            max_tokens=max_tokens,
            temperature=0.3,   # low: this is explanation, not creative writing
        )
        return _strip_think(out["choices"][0]["message"]["content"])

    return verify_and_retry(context, base_prompt, generate)


# --------------------------------------------------------------------------
# Routing: dimension hint, single call.
#
# classify() was originally one call over all 8 categories, back when they
# were named top_products/bottom_products/by_vendor/by_channel/by_payment.
# by_vendor and by_channel measured weak (20% / 40%) because the classifier
# had to get two independent things right in a single choice — WHICH SLICE
# of the business the question is about, and WHAT KIND of question it is —
# and the category wording overlapped too much for a small model to
# separate them reliably.
#
# Two fixes were evaluated against tests/test_routing.py (see
# docs/routing-evaluation.md for the full comparison):
#   - a two-stage classifier (separate dimension and view calls, composed in
#     code) fixed by_vendor/by_channel but broke categories it wasn't
#     targeting — 51% overall, at ~4x the latency.
#   - a dimension hint folded into the existing single call — 83% overall, at
#     roughly the same latency as the original.
# The hint won on both accuracy and cost, so it's the only path kept here.
#
# Categories were later renamed to a parallel ranking_by_X / worst_by_X
# scheme (see docs/routing-evaluation.md, "rename for parallel structure")
# so the dimension is explicit in every label and none of them reads as a
# generic catch-all the model defaults to on ties.
#
# The hint itself is a cheap keyword lookup over the question text. It is NOT
# routing: the words below never choose the handler and are never checked
# against HANDLERS — they only bias the wording the model sees in its prompt,
# and the model still makes the final call and can ignore the hint entirely.
# If nothing matches, the prompt is unchanged from the original single-call
# design.
# --------------------------------------------------------------------------

_DIMENSION_HINT_WORDS = {
    "ranking_by_vendor": ("vendor", "vendors", "branch", "branches", "outlet", "outlets",
                          "supplier", "suppliers"),
    "ranking_by_channel": ("channel", "channels", "app", "walk-in", "walk in", "walkin",
                           "online", "in-store", "in store", "delivery"),
    "ranking_by_payment": ("payment", "payments", "paying", "paid", "cash", "transfer",
                           "card", "pos"),
}


def _dimension_hint(question: str) -> str | None:
    q = question.lower()
    for category, words in _DIMENSION_HINT_WORDS.items():
        if any(w in q for w in words):
            return category
    return None


def _hint_line(question: str) -> str:
    category = _dimension_hint(question)
    if category is None:
        return ""
    return (
        f"\nHint: the wording of this question leans toward '{category}' — weigh "
        f"that, but pick whichever category actually fits best.\n"
    )


def classify(question: str, model_path: str | Path | None = None) -> str | None:
    """Pick one category for a question. None if nothing fits.

    Labelling into a fixed set is a much easier task than open-ended function
    selection — the model chooses, it doesn't invent. Capped at a few tokens
    so it can only emit a label. See the module comment above for why this
    is a single call with a dimension hint, not a two-stage classifier.

    Reply format is the category name, not a number — see the numbered-list
    experiment noted above CATEGORY_LIST for why that alternative was tried
    and dropped. This measured 45/48 (93.8%), stable across 3 runs.

    `model_path` overrides MODEL_PATH/LEDGERIT_MODEL_PATH for this call only.

    Raises QuestionTooLongError if `question` alone would overflow the
    model's context window — checked before the call, not caught after.
    """
    system = ("/no_think\nYou label questions. Reply with exactly one category "
               "name from the list and nothing else. If none fit, reply: none")
    user = (f"Categories:\n{_text_categories()}\n{_hint_line(question)}\n"
            f"Question: {question}\n\nCategory:")
    max_tokens = 10
    _ensure_fits_context(system, user, max_tokens, model_path)

    out = _llm(model_path).create_chat_completion(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.0,
    )
    label = _strip_think(out["choices"][0]["message"]["content"]).lower()
    label = label.split()[0].strip(":.,") if label else ""
    return label if label in _CATEGORY_LABELS else None