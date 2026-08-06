#!/usr/bin/env bash
# Download your model weight file.
#
# Rules:
#   - Must be idempotent (safe to run multiple times).
#   - Must download without any credentials (public URL only).
#   - The output path must match `_runtime.model_path` in metadata.json.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="$HERE/model"
MODEL_FILE="$MODEL_DIR/smollm3-3b-q3_k_m-templated.gguf"
PARTIAL_FILE="$MODEL_FILE.partial"

# ── Replace this URL with your public model weight URL ─────────────────────────
MODEL_URL="https://huggingface.co/clintonlynx/smollm3-3b-q3_k_m-templated/resolve/main/smollm3-3b-q3_k_m-templated.gguf"
EXPECTED_SHA256="72488ecf9f7972cb0b38eaeaf162f5cc3590c76f22c78e4fac70eaf145689dc7"
EXPECTED_SIZE=1571069728
# ───────────────────────────────────────────────────────────────────────────────

mkdir -p "$MODEL_DIR"

verify() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local size
  size=$(wc -c < "$file" | tr -d ' ')
  [[ "$size" == "$EXPECTED_SIZE" ]] || return 1
  if command -v shasum > /dev/null 2>&1; then
    [[ "$(shasum -a 256 "$file" | cut -d' ' -f1)" == "$EXPECTED_SHA256" ]] || return 1
  elif command -v sha256sum > /dev/null 2>&1; then
    [[ "$(sha256sum "$file" | cut -d' ' -f1)" == "$EXPECTED_SHA256" ]] || return 1
  fi
  return 0
}

if verify "$MODEL_FILE"; then
  echo "model already present and verified at $MODEL_FILE — skipping download"
  exit 0
fi
rm -f "$MODEL_FILE"  # present but failed verification — re-download rather than trust it

echo "downloading $MODEL_URL → $MODEL_FILE (~1.5 GB)…"

# HF's Xet-backed CDN has been observed dropping the connection mid-transfer
# every few MB on unauthenticated requests (this is a public, credential-free
# download, so it always takes that path) — far more often than a single
# curl/wget invocation's own --retry budget accounts for. So: retry in an
# outer loop, resuming (-C -/--continue) from wherever the last attempt left
# off, and keep going until the file verifies or a generous attempt budget
# runs out. Each attempt only needs to make forward progress, not finish.
MAX_ATTEMPTS=40
attempt=1
while [[ $attempt -le $MAX_ATTEMPTS ]]; do
  echo "  attempt $attempt/$MAX_ATTEMPTS…"
  if command -v curl > /dev/null 2>&1; then
    curl -L --fail --http1.1 -C - --retry 3 --retry-delay 2 --retry-connrefused \
      --progress-bar -o "$PARTIAL_FILE" "$MODEL_URL" && break || true
  elif command -v wget > /dev/null 2>&1; then
    wget --show-progress --continue --tries=3 -O "$PARTIAL_FILE" "$MODEL_URL" && break || true
  else
    echo "error: neither curl nor wget found" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 2
done

if ! verify "$PARTIAL_FILE"; then
  echo "error: download did not complete/verify after $MAX_ATTEMPTS attempts" >&2
  echo "  (partial file kept at $PARTIAL_FILE — re-run this script to resume)" >&2
  exit 1
fi

mv "$PARTIAL_FILE" "$MODEL_FILE"
echo "done: $MODEL_FILE (sha256 verified)"
