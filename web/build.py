base = "/private/tmp/claude-501/-Users-app-adtc/110f855e-5213-42ab-a721-22e419cf64bd/scratchpad/fontfiles/"
mono400 = open(base + "IBM_Plex_Mono_400.b64").read().strip()
mono600 = open(base + "IBM_Plex_Mono_600.b64").read().strip()
sans400 = open(base + "IBM_Plex_Sans_400.b64").read().strip()
sans600 = open(base + "IBM_Plex_Sans_600.b64").read().strip()

html = r"""<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ledgerit</title>
<style>
@font-face {
  font-family: 'Plex Mono';
  font-weight: 400;
  font-style: normal;
  src: url(data:font/woff2;base64,__MONO400__) format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Plex Mono';
  font-weight: 600;
  font-style: normal;
  src: url(data:font/woff2;base64,__MONO600__) format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Plex Sans';
  font-weight: 400;
  font-style: normal;
  src: url(data:font/woff2;base64,__SANS400__) format('woff2');
  font-display: swap;
}
@font-face {
  font-family: 'Plex Sans';
  font-weight: 600;
  font-style: normal;
  src: url(data:font/woff2;base64,__SANS600__) format('woff2');
  font-display: swap;
}

:root {
  --paper: #f9f4e7;
  --paper-shadow: #ece4d0;
  --ink: #3c362b;
  --ink-soft: #8a8171;
  --ink-faint: #b0a794;
  --rule: #ddd3bd;
  --accent: #a23a2c;
  --accent-wash: rgba(162, 58, 44, 0.07);
  --good: #4c7f5a;
  --bg: #e9e5da;
  --bg-vignette: #d8d3c4;
  --focus: #2f6fb0;

  /* chrome = the app shell (header/footer), theme-aware. The receipt paper
     itself is deliberately NOT theme-aware — a photo of a paper receipt
     doesn't change when your phone switches to dark mode, and that fixed
     identity is part of what makes it read as a physical object rather
     than UI. Chrome around it is ordinary interface and adapts normally. */
  --chrome-bg: #f2ede0;
  --chrome-border: var(--rule);
  --chrome-ink: var(--ink);
  --chrome-ink-soft: var(--ink-soft);
  --field-bg: #fdfbf3;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17140f;
    --bg-vignette: #0e0c09;
    --chrome-bg: #1d1912;
    --chrome-border: #343025;
    --chrome-ink: #ece7da;
    --chrome-ink-soft: #ab9f88;
    --field-bg: #262119;
  }
}
:root[data-theme="dark"] {
  --bg: #17140f;
  --bg-vignette: #0e0c09;
  --chrome-bg: #1d1912;
  --chrome-border: #343025;
  --chrome-ink: #ece7da;
  --chrome-ink-soft: #ab9f88;
  --field-bg: #262119;
}
:root[data-theme="light"] {
  --bg: #e9e5da;
  --bg-vignette: #d8d3c4;
  --chrome-bg: #f2ede0;
  --chrome-border: var(--rule);
  --chrome-ink: var(--ink);
  --chrome-ink-soft: var(--ink-soft);
  --field-bg: #fdfbf3;
}

* { box-sizing: border-box; }

html, body {
  height: 100%;
  margin: 0;
  overflow: hidden; /* the app owns three scroll zones; the page itself never scrolls */
}
body {
  font-family: 'Plex Sans', -apple-system, sans-serif;
  color: var(--ink);
}
/* the actual flex shell — body has exactly one real child (this div; the
   two <script> tags are the others and don't participate in layout), so
   the flex/height rules have to live here, not on body, or none of the
   flex:1/flex:0 sizing below the header takes effect and every zone just
   grows to fit its content instead of being constrained to the window. */
.app {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ================================================================== */
/* 1. topbar — fixed, thin, never scrolls                              */
/* ================================================================== */
.topbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px clamp(14px, 3vw, 28px);
  background: var(--chrome-bg);
  border-bottom: 1px solid var(--chrome-border);
  -webkit-app-region: drag; /* if ever wrapped in a frameless window */
}
.topbar-mark {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: 0.92rem;
  letter-spacing: 0.02em;
  color: var(--chrome-ink);
  white-space: nowrap;
}
.topbar-mark::before { content: "🧾 "; }
.topbar-right {
  display: flex;
  align-items: center;
  gap: 18px;
  min-width: 0;
}
.topbar-filename {
  font-family: 'Plex Mono', monospace;
  font-size: 0.8rem;
  color: var(--chrome-ink-soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 34vw;
  background: none;
  border: none;
  border-bottom: 1px dashed transparent;
  padding: 0;
  cursor: pointer;
}
.topbar-filename:hover, .topbar-filename:focus-visible {
  color: var(--chrome-ink);
  border-bottom-color: var(--chrome-ink-soft);
}
.topbar-filename:focus-visible { outline: 2.5px solid var(--focus); outline-offset: 3px; }
.topbar-filename:disabled { cursor: default; opacity: 0.6; }
.offline {
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'Plex Mono', monospace;
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--chrome-ink-soft);
  white-space: nowrap;
  cursor: default;
}
.offline-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ink-faint);
  transition: background 200ms, box-shadow 200ms;
  flex: 0 0 auto;
}
.offline-dot.confirmed {
  background: var(--good);
  box-shadow: 0 0 0 3px rgba(76, 127, 90, 0.16);
}
.offline-dot.bad {
  background: var(--accent);
  box-shadow: 0 0 0 3px rgba(162, 58, 44, 0.18);
}

/* ================================================================== */
/* 2. receipt viewport — centred column, owns its own scroll           */
/* ================================================================== */
.receipt-viewport {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: radial-gradient(ellipse at top, var(--bg) 0%, var(--bg-vignette) 100%);
}
.receipt-frame {
  width: 600px;
  max-width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.printer-bar {
  flex: 0 0 auto;
  height: 13px;
  margin: 16px 16px 0;
  background: var(--ink);
  border-radius: 1px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.18);
  position: relative;
  z-index: 3;
  overflow: hidden;
}
/* real work is in flight (a fetch is unresolved) — an indeterminate sweep,
   not a countdown, because we don't know how long the request will take. */
.printer-bar.working::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0; left: -40%;
  width: 40%;
  background: linear-gradient(90deg, transparent, rgba(249,244,231,0.35), transparent);
  animation: printerSweep 1.1s ease-in-out infinite;
}
@keyframes printerSweep {
  0% { left: -40%; }
  100% { left: 100%; }
}
.receipt-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 16px 28px;
  scrollbar-gutter: stable;
}
.receipt-scroll::-webkit-scrollbar { width: 9px; }
.receipt-scroll::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 6px; }
.receipt-scroll::-webkit-scrollbar-track { background: transparent; }

.stack {
  display: flex;
  flex-direction: column;
  gap: clamp(32px, 5vw, 48px);
  padding-top: 2px;
}

/* ---------------------------------------------------------------- */
/* the empty state — printer bar, no paper, a slot to feed a file into */
/* ---------------------------------------------------------------- */

.dropzone {
  border: 2px dashed var(--rule);
  border-radius: 6px;
  padding: clamp(40px, 9vw, 68px) clamp(20px, 5vw, 40px);
  text-align: center;
  transition: border-color 160ms ease-out, background-color 160ms ease-out;
}
.dropzone.drag-over {
  border-color: var(--accent);
  background: var(--accent-wash);
}
.dropzone-title {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: clamp(1rem, 3.6vw, 1.2rem);
  color: var(--ink);
  margin: 0 0 10px;
}
.dropzone-sub {
  font-family: 'Plex Sans', sans-serif;
  font-size: 0.94rem;
  color: var(--ink-soft);
  margin: 0 0 26px;
}
.dropzone-link {
  font: inherit;
  color: var(--accent);
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.dropzone-link:focus-visible { outline: 2.5px solid var(--focus); outline-offset: 2px; }
.dropzone-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 auto 22px;
  max-width: 180px;
  font-family: 'Plex Mono', monospace;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
}
.dropzone-divider::before, .dropzone-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--rule);
}
.dropzone-sample {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: 0.86rem;
  padding: 11px 24px;
  border: 1.5px solid var(--ink);
  border-radius: 3px;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
}
.dropzone-sample:hover { background: var(--ink); color: var(--paper); }
.dropzone-sample:focus-visible { outline: 2.5px solid var(--focus); outline-offset: 2px; }
.dropzone-error {
  margin: 24px 0 0;
  padding: 10px 14px;
  border: 1px dashed var(--accent);
  border-radius: 3px;
  background: var(--accent-wash);
  font-family: 'Plex Mono', monospace;
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--accent);
  text-align: left;
  white-space: pre-line;
}

/* ---------------------------------------------------------------- */
/* the receipt object                                                */
/* ---------------------------------------------------------------- */

.tear {
  width: 100%;
  height: 13px;
  position: relative;
  z-index: 2;
  margin-top: -1px;
}
.tear svg { display: block; width: 100%; height: 100%; }
.tear path { fill: var(--paper); }
.tear.tear--bottom { transform: scaleY(-1); margin-top: 0; margin-bottom: -1px; }

.receipt-card {
  transform: rotate(-0.7deg);
  filter: drop-shadow(0 16px 30px rgba(60, 54, 43, 0.20));
}

.paper {
  background: var(--paper);
  box-shadow: 0 1px 0 var(--paper-shadow);
  padding: clamp(20px, 4.5vw, 36px) clamp(20px, 5.5vw, 40px) clamp(24px, 4.5vw, 34px);
  transform-origin: top center;
  position: relative;
  z-index: 1;
}

.feed {
  animation: feedDown 460ms cubic-bezier(.2,.85,.35,1) both;
}
@keyframes feedDown {
  from { transform: scaleY(0.02); opacity: 0.4; }
  to   { transform: scaleY(1); opacity: 1; }
}

.receipt-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: 'Plex Mono', monospace;
  font-size: 0.82rem;
  color: var(--ink-soft);
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding-bottom: 14px;
  border-bottom: 1px dashed var(--rule);
  margin-bottom: 18px;
  opacity: 0;
}
.receipt-head.show { opacity: 1; }

.receipt-title {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: 1.3rem;
  margin: 0 0 22px;
  opacity: 0;
}
.receipt-title.show { opacity: 1; transition: opacity 200ms; }

.row {
  display: flex;
  align-items: baseline;
  gap: 0.6em;
  padding: 7px 0;
  opacity: 0;
  transform: translateY(6px);
}
.row.show {
  animation: rowUp 260ms ease-out both;
}
@keyframes rowUp {
  to { opacity: 1; transform: translateY(0); }
}
.row .label {
  font-family: 'Plex Mono', monospace;
  font-size: clamp(0.82rem, 3.3vw, 1rem);
  color: var(--ink);
}
.row .leader {
  flex: 1;
  border-bottom: 2px dotted var(--rule);
  height: 0;
  margin-bottom: 5px;
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 420ms ease-out;
}
.row.show .leader { transform: scaleX(1); }
.row .value {
  font-family: 'Plex Mono', monospace;
  font-size: clamp(0.82rem, 3.3vw, 1rem);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ink);
}
.row .value.dim { color: var(--ink-soft); }

.flag-block {
  margin: 6px -14px 4px;
  padding: 12px 14px;
  border-radius: 3px;
  position: relative;
  opacity: 0;
  transform: translateY(6px);
}
.flag-block.show { animation: rowUp 260ms ease-out both; }
.flag-block.is-culprit { background: var(--accent-wash); }
.flag-block .flag-row {
  display: flex;
  align-items: baseline;
  gap: 0.6em;
  padding: 3px 0;
}
.flag-block .flag-row .label { font-family: 'Plex Mono', monospace; color: var(--ink-soft); font-size: clamp(0.76rem, 3vw, 0.92rem); }
.flag-block .flag-row .leader {
  flex: 1;
  border-bottom: 2px dotted var(--rule);
  height: 0;
  margin-bottom: 4px;
}
.flag-block .flag-row .value {
  font-family: 'Plex Mono', monospace;
  font-size: clamp(0.76rem, 3vw, 0.92rem);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.flag-block .flag-row .value.was { text-decoration: line-through; text-decoration-color: var(--accent); color: var(--accent); }
.flag-block .flag-row .value.should { color: var(--ink); font-weight: 600; }

.summary {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 2px solid var(--ink);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary .row { padding: 3px 0; opacity: 1; transform: none; }
.summary .headline {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 6px;
  opacity: 0;
}
.summary .headline.show { animation: rowUp 320ms ease-out both; }
.summary .headline .label {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: clamp(0.78rem, 3.1vw, 1rem);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.summary .headline .num {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: clamp(1.9rem, 6vw, 2.5rem);
  font-variant-numeric: tabular-nums;
}

.status {
  margin-top: 10px;
  font-family: 'Plex Mono', monospace;
  font-size: 0.82rem;
  color: var(--ink-soft);
  opacity: 0;
}
.status.show { animation: rowUp 260ms ease-out both; }

/* facts — the Finding's computed facts dict, one line each. Prose
   sentences pandas already produced, not a fabricated single "headline
   stat": different question types don't share one number worth blowing up
   in giant type, so every fact gets equal, legible weight instead. */
.facts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 2px solid var(--ink);
}
.factline {
  font-family: 'Plex Mono', monospace;
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--ink-soft);
  opacity: 0;
}
.factline.show { animation: rowUp 260ms ease-out both; }
.factline b { color: var(--ink); font-weight: 600; }

/* stamp -------------------------------------------------------------- */
.stamp {
  position: absolute;
  left: 50%;
  top: 50%;
  border: 2.5px solid var(--accent);
  color: var(--accent);
  font-family: 'Plex Mono', monospace;
  font-weight: 700;
  font-size: 0.74rem;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  padding: 5px 9px;
  border-radius: 2px;
  background: rgba(249,244,231,0.92);
  transform: translate(-50%, -50%) rotate(-11deg) scale(1.7);
  opacity: 0;
  pointer-events: none;
  white-space: nowrap;
  z-index: 2;
}
/* sits in the dot-leader gap, not over the label or the value — the one
   part of either flag-row with no text in it, at any width, so a
   horizontally-centred stamp never touches a digit. */
.stamp.show {
  animation: stampLand 480ms cubic-bezier(.3,1.7,.5,1) both;
}
@keyframes stampLand {
  0%   { opacity: 0; transform: translate(-50%, -50%) rotate(-11deg) scale(1.9); }
  55%  { opacity: 1; transform: translate(-50%, -50%) rotate(-11deg) scale(0.92); }
  100% { opacity: 1; transform: translate(-50%, -50%) rotate(-11deg) scale(1); }
}

/* narration ------------------------------------------------------------ */
.narration {
  padding: 4px clamp(6px, 2vw, 14px) 0;
  opacity: 0;
}
.narration.show { animation: narrIn 500ms ease-out both; }
@keyframes narrIn { from { opacity: 0; transform: translateY(4px);} to { opacity: 1; transform: translateY(0);} }
.narration .tag {
  font-family: 'Plex Mono', monospace;
  font-size: 0.76rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--ink-faint);
  margin-bottom: 8px;
  display: block;
}
.narration p {
  font-family: 'Plex Sans', sans-serif;
  font-size: 1.06rem;
  line-height: 1.68;
  color: var(--ink-soft);
  margin: 0;
  max-width: 60ch;
}
/* indeterminate — real generation is 15s+ and we don't know the duration
   in advance, so this loops rather than counting down to a guess. */
.loading-dots { display: inline-flex; gap: 4px; vertical-align: middle; }
.loading-dots i {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--ink-faint);
  display: inline-block;
  animation: dotBlink 1.1s ease-in-out infinite;
}
.loading-dots i:nth-child(2) { animation-delay: 0.15s; }
.loading-dots i:nth-child(3) { animation-delay: 0.3s; }
@keyframes dotBlink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }

/* Narration.verified === false — surfaced, not swallowed. explain.py's
   verify-and-retry pass already tried once; if it still couldn't match
   every number in the text back to the Finding, the reader needs to know
   this paragraph may contain a number pandas didn't produce. */
.narration-warn {
  margin-top: 12px;
  padding: 8px 11px;
  border: 1px dashed var(--accent);
  border-radius: 3px;
  background: var(--accent-wash);
  font-family: 'Plex Mono', monospace;
  font-size: 0.76rem;
  line-height: 1.5;
  color: var(--accent);
  opacity: 0;
}
.narration-warn.show { animation: rowUp 260ms ease-out both; }


/* ================================================================== */
/* 3. ask bar — fixed footer, always reachable                         */
/* ================================================================== */
.ask-bar {
  flex: 0 0 auto;
  background: var(--chrome-bg);
  border-top: 1px solid var(--chrome-border);
  padding: 13px clamp(14px, 3vw, 28px) 16px;
  display: flex;
  justify-content: center;
}
.ask-inner {
  width: 100%;
  max-width: 600px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ask-inner label {
  font-family: 'Plex Mono', monospace;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--chrome-ink-soft);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chip {
  font-family: 'Plex Sans', sans-serif;
  font-size: 0.92rem;
  padding: 7px 13px;
  border: 1.5px dashed var(--chrome-border);
  border-radius: 20px;
  background: transparent;
  color: var(--chrome-ink-soft);
  cursor: pointer;
}
.chip:hover { border-color: var(--chrome-ink-soft); color: var(--chrome-ink); }
.chip:focus-visible { outline: 2.5px solid var(--focus); outline-offset: 2px; }

.ask-row {
  width: 100%;
  display: flex;
  gap: 10px;
}
.ask-row input {
  flex: 1;
  min-width: 0;
  font-family: 'Plex Sans', sans-serif;
  font-size: 1.02rem;
  padding: 12px 15px;
  border: 1.5px solid var(--chrome-border);
  border-radius: 3px;
  background: var(--field-bg);
  color: var(--chrome-ink);
}
.ask-row input::placeholder { color: var(--ink-faint); }
.ask-row input:focus-visible {
  outline: 2.5px solid var(--focus);
  outline-offset: 1px;
}
.ask-row button.go {
  font-family: 'Plex Mono', monospace;
  font-weight: 600;
  font-size: 0.92rem;
  padding: 0 20px;
  border: none;
  border-radius: 3px;
  background: var(--ink);
  color: var(--paper);
  cursor: pointer;
}
.ask-row button.go:hover { background: var(--accent); }
.ask-row button.go:focus-visible { outline: 2.5px solid var(--focus); outline-offset: 2px; }

.hint {
  font-family: 'Plex Sans', sans-serif;
  font-size: 0.86rem;
  color: var(--ink-faint);
  min-height: 1.3em;
}

[hidden] { display: none !important; }

@media (max-width: 480px) {
  .topbar-filename { display: none; }
}

@media (prefers-reduced-motion: reduce) {
  .feed, .row.show, .flag-block.show, .stamp.show, .summary .headline.show,
  .status.show, .narration.show, .receipt-head, .receipt-title,
  .factline.show, .narration-warn.show {
    animation: none !important;
    transform: none !important;
    opacity: 1 !important;
  }
  .row .leader { transform: scaleX(1) !important; }
  .printer-bar.working::after { animation: none !important; display: none; }
  .loading-dots i { animation: none !important; opacity: 0.6 !important; }
}
</style>

<div class="app">

  <!-- ============ 1. TOPBAR ============ -->
  <header class="topbar">
    <div class="topbar-mark">Ledgerit</div>
    <div class="topbar-right">
      <button type="button" class="topbar-filename" id="topbar-filename" title="Load a different file" hidden>&hellip;</button>
      <input type="file" id="file-input" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden />
      <span class="offline" id="offline-indicator" title="Live check: watches every network request this page makes and confirms none has left this machine.">
        <span class="offline-dot" id="offline-dot"></span>
        <span id="offline-label">checking&hellip;</span>
      </span>
    </div>
  </header>

  <!-- ============ 2. RECEIPT VIEWPORT ============ -->
  <main class="receipt-viewport">
    <div class="receipt-frame">
      <div class="printer-bar"></div>
      <div class="receipt-scroll" id="receipt-scroll">
        <div class="stack">

          <!-- EMPTY STATE: the first thing anyone sees. No receipt has
               printed yet — that's the point. The print animation is
               triggered by an upload, never by page load. -->
          <div class="unit" id="unit-empty">
            <div class="dropzone" id="dropzone">
              <p class="dropzone-title">Drop a CSV or Excel file here</p>
              <p class="dropzone-sub">or <button type="button" class="dropzone-link" id="dropzone-browse">choose a file</button></p>
              <div class="dropzone-divider"><span>or</span></div>
              <button type="button" class="dropzone-sample" id="dropzone-sample">Try the sample data</button>
              <p class="dropzone-error" id="dropzone-error" hidden></p>
            </div>
          </div>

          <!-- RECEIPT 1: the cleaning report -->
          <div class="unit" id="unit-clean" hidden>
            <div class="receipt-card">
              <div class="tear"><svg viewBox="0 0 400 14" preserveAspectRatio="none"></svg></div>
              <div class="paper" id="paper-clean">
                <div class="receipt-head" id="head-clean">
                  <span id="clean-filename">&hellip;</span>
                  <span id="clean-date">&hellip;</span>
                </div>
                <div class="receipt-title" id="title-clean">What we found in your file</div>

                <div id="rows-clean"></div>

                <div class="summary">
                  <div class="row show" style="opacity:1"><span class="label">Rows in file</span><span class="leader" style="transform:scaleX(1)"></span><span class="value dim" id="rows-in-clean">&mdash;</span></div>
                  <div class="headline" id="headline-clean">
                    <span class="label">Rows kept, clean</span>
                    <span class="num" id="num-clean">0</span>
                  </div>
                </div>
                <div class="status" id="status-clean"></div>
              </div>
              <div class="tear tear--bottom"><svg viewBox="0 0 400 14" preserveAspectRatio="none"></svg></div>
            </div>
          </div>

          <!-- RECEIPT 2: the answer -->
          <div class="unit" id="unit-answer" hidden>
            <div class="receipt-card">
              <div class="tear"><svg viewBox="0 0 400 14" preserveAspectRatio="none"></svg></div>
              <div class="paper" id="paper-answer">
                <div class="receipt-head" id="head-answer">
                  <span id="answer-date">29 jul 2026</span>
                  <span id="answer-tag">ledgerit</span>
                </div>
                <div class="receipt-title" id="title-answer"></div>
                <div id="rows-answer"></div>
                <div class="facts" id="facts-answer" hidden></div>
                <div class="status" id="status-answer"></div>
              </div>
              <div class="tear tear--bottom"><svg viewBox="0 0 400 14" preserveAspectRatio="none"></svg></div>
            </div>

            <div class="narration" id="narration-block">
              <span class="tag">Ledgerit says</span>
              <p id="narration-text"></p>
              <div class="narration-warn" id="narration-warn" hidden></div>
            </div>
          </div>

        </div>
      </div>
    </div>
  </main>

  <!-- ============ 3. ASK BAR ============ -->
  <!-- Hidden until a file loads — asking about data that doesn't exist
       yet isn't a state worth showing; the empty state above is the only
       thing on screen until then. -->
  <footer class="ask-bar" id="ask-bar" hidden>
    <div class="ask-inner">
      <div class="chips">
        <button class="chip">Which day is quietest?</button>
        <button class="chip">What are my best selling products?</button>
      </div>
      <div class="ask-row">
        <input id="ask-input" type="text" placeholder="Ask about your shop…" autocomplete="off" aria-label="Ask about your shop" />
        <button class="go" id="ask-go">Ask</button>
      </div>
      <div class="hint" id="ask-hint"></div>
    </div>
  </footer>

</div>

<script>
/* ---------------------------------------------------------------------
   Real offline check.

   This does not assert "offline" as a decorative label — it watches the
   browser's own network log (the Resource Timing API) for the page's
   entire lifetime and only shows "confirmed" if nothing has ever left
   this machine. A request to our own local server (same origin) doesn't
   count against it; a request to any other host does, immediately and
   permanently flips the dot, and stays flipped even if later checks
   would have passed — once real, "offline" is a claim that has to hold
   for the whole session, not just at the instant you looked.
------------------------------------------------------------------------ */
(function () {
  "use strict";
  var dot = document.getElementById('offline-dot');
  var label = document.getElementById('offline-label');
  var flagged = false;

  function isExternal(url) {
    try {
      var u = new URL(url, window.location.href);
      var here = window.location.hostname;
      if (u.hostname === here) return false;
      if ((here === 'localhost' || here === '127.0.0.1') &&
          (u.hostname === 'localhost' || u.hostname === '127.0.0.1')) return false;
      return true;
    } catch (e) {
      return false;
    }
  }

  function flagExternal(name) {
    if (flagged) return;
    flagged = true;
    dot.classList.remove('confirmed');
    dot.classList.add('bad');
    label.textContent = 'network call made';
    dot.parentElement.title = 'A request left this machine: ' + name;
  }

  function scan(entries) {
    entries.forEach(function (e) {
      if (isExternal(e.name)) flagExternal(e.name);
    });
  }

  if (window.performance && performance.getEntriesByType) {
    scan(performance.getEntriesByType('resource'));
  }
  if (window.PerformanceObserver) {
    try {
      new PerformanceObserver(function (list) { scan(list.getEntries()); })
        .observe({ entryTypes: ['resource'] });
    } catch (e) { /* unsupported — falls back to the load-time scan above */ }
  }

  setTimeout(function () {
    if (!flagged) {
      dot.classList.add('confirmed');
      label.textContent = 'offline';
    }
  }, 700);
})();
</script>

<script>
(function () {
  "use strict";
  var REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------- torn-edge zigzag, generated procedurally ---------------- */
  function buildTear(svg) {
    var W = 400, H = 14, tooth = 11;
    var n = Math.ceil(W / tooth);
    var d = "M0," + H;
    for (var i = 0; i <= n; i++) {
      var x = i * tooth;
      var y = (i % 2 === 0) ? 0 : H * 0.62;
      d += " L" + x + "," + y;
    }
    d += " L" + W + "," + H + " Z";
    var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  document.querySelectorAll('.tear svg').forEach(buildTear);

  /* ---------------- helpers ---------------- */
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function el(tag, cls, html) {
    var e = document.createElement('div');
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  function row(label, value, dim) {
    var r = el('div', 'row');
    r.innerHTML = '<span class="label">' + esc(label) + '</span><span class="leader"></span>' +
      '<span class="value' + (dim ? ' dim' : '') + '">' + esc(value) + '</span>';
    return r;
  }
  function sleep(ms) { return new Promise(function (res) { setTimeout(res, REDUCED ? 0 : ms); }); }

  function countUp(node, target, duration) {
    if (REDUCED) { node.textContent = target.toLocaleString(); return Promise.resolve(); }
    return new Promise(function (resolve) {
      var start = null;
      function step(ts) {
        if (!start) start = ts;
        var p = Math.min(1, (ts - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        node.textContent = Math.round(eased * target).toLocaleString();
        if (p < 1) requestAnimationFrame(step); else resolve();
      }
      requestAnimationFrame(step);
    });
  }

  async function reveal(node, gap) {
    node.classList.add('show');
    await sleep(gap == null ? 120 : gap);
  }

  function naira(n) {
    var num = typeof n === 'string' ? parseFloat(n.replace(/,/g, '')) : n;
    if (isNaN(num)) return 'NGN ' + n;
    return 'NGN ' + Math.round(num).toLocaleString('en-US');
  }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }
  function capFirst(s) { s = String(s); return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }
  function spaced(s) { return String(s).replace(/_/g, ' '); }
  function todayStamp() {
    var months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'];
    var d = new Date();
    return String(d.getDate()).padStart(2, '0') + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
  }

  /* The Finding's table shape varies by handler (product/vendor/channel/
     payment_method/month/day-of-week as the label column; revenue is the
     one numeric column every handler formats the same way), so this reads
     the shape rather than assuming one. It never touches finding.guidance —
     that field isn't part of this JSON in the first place; the server
     leaves it out before this ever reaches the browser. */
  function tableToRows(table) {
    if (!table || !table.length) return [];
    var cols = Object.keys(table[0]);
    var labelCol = cols[0];
    var valueCol = cols.indexOf('revenue') !== -1 ? 'revenue' : cols[1];
    return table.map(function (r) {
      var value = valueCol === 'revenue' ? naira(r[valueCol]) : String(r[valueCol]);
      return [String(r[labelCol]), value];
    });
  }

  /* ---------------- talking to the real backend ---------------- */
  var printerBar = document.querySelector('.printer-bar');
  var inFlight = 0;
  function setWorking(delta) {
    inFlight = Math.max(0, inFlight + delta);
    printerBar.classList.toggle('working', inFlight > 0);
  }
  async function api(path, body) {
    setWorking(1);
    try {
      var res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body || {})
      });
      var data = {};
      try { data = await res.json(); } catch (e) { /* non-JSON error body */ }
      if (!res.ok || data.error) throw new Error(data.error || ('request failed (' + res.status + ')'));
      return data;
    } finally {
      setWorking(-1);
    }
  }

  var STATE = { ready: false, asking: false };

  /* ================= RECEIPT 1: cleaning report — real cleaner.clean() ================= */
  async function printCleaningReceipt(report) {
    var paper = document.getElementById('paper-clean');
    var rowsHost = document.getElementById('rows-clean');
    rowsHost.innerHTML = '';
    document.getElementById('num-clean').textContent = '0';
    ['head-clean','title-clean'].forEach(function(id){ document.getElementById(id).classList.remove('show'); });
    document.getElementById('headline-clean').classList.remove('show');
    document.getElementById('status-clean').classList.remove('show');

    document.getElementById('clean-filename').textContent = report.filename;
    document.getElementById('clean-date').textContent = todayStamp();
    document.getElementById('rows-in-clean').textContent = report.rows_in.toLocaleString();

    paper.classList.remove('feed');
    void paper.offsetWidth;
    paper.classList.add('feed');
    await sleep(REDUCED ? 0 : 480);

    await reveal(document.getElementById('head-clean'), 90);
    await reveal(document.getElementById('title-clean'), 140);

    var basics = [];
    if (report.duplicates_removed) basics.push(['Duplicate rows removed', String(report.duplicates_removed)]);
    if (report.currency_stripped) basics.push(['Currency text cleaned up', plural(report.currency_stripped, 'cell')]);
    if (report.dates_failed) basics.push(["Dates that couldn't be read", plural(report.dates_failed, 'row')]);
    Object.keys(report.blanks_filled || {}).forEach(function (col) {
      basics.push(['Missing ' + spaced(col) + ' filled in', plural(report.blanks_filled[col], 'row')]);
    });
    for (var i = 0; i < basics.length; i++) {
      var r = row(basics[i][0], basics[i][1]);
      rowsHost.appendChild(r);
      await reveal(r, 130);
    }

    var mismatchCount = report.total_mismatches_count || 0;
    if (mismatchCount > 0) {
      var flagTitle = row("Entries that don't add up", mismatchCount + ' found');
      rowsHost.appendChild(flagTitle);
      await reveal(flagTitle, 160);

      var items = report.total_mismatches || [];
      for (var j = 0; j < items.length; j++) {
        var f = items[j];
        var block = el('div', 'flag-block' + (j === 0 ? ' is-culprit' : ''));
        block.innerHTML =
          '<div class="flag-row"><span class="label">' + esc(f.order_id) + '</span><span class="leader"></span>' +
          '<span class="value was">' + naira(f.recorded_total) + '</span></div>' +
          '<div class="flag-row"><span class="label">should be</span><span class="leader"></span>' +
          '<span class="value should">' + naira(f.expected_total) + '</span></div>';
        if (j === 0) {
          block.style.position = 'relative';
          var stampEl = el('div', 'stamp', 'Check this');
          stampEl.id = 'stamp-clean';
          block.appendChild(stampEl);
        }
        rowsHost.appendChild(block);
        await reveal(block, 120);
      }
    }

    var headline = document.getElementById('headline-clean');
    await reveal(headline, 0);
    await countUp(document.getElementById('num-clean'), report.rows_out, REDUCED ? 0 : 600);
    await sleep(80);

    var statusEl = document.getElementById('status-clean');
    statusEl.textContent = mismatchCount > 0
      ? 'Check these against your original records.'
      : 'Every entry in this file adds up — nothing flagged.';
    await reveal(statusEl, 260);

    var stamp = document.getElementById('stamp-clean');
    if (stamp) stamp.classList.add('show');
  }

  async function loadFile(fileBase64, filename) {
    var fnBtn = document.getElementById('topbar-filename');
    var dzError = document.getElementById('dropzone-error');
    var firstLoad = !STATE.ready;   // dropzone is still the thing on screen

    fnBtn.disabled = true;
    document.getElementById('ask-hint').textContent = '';
    dzError.hidden = true;
    dzError.textContent = '';
    document.getElementById('unit-answer').hidden = true;
    try {
      var report = await api('/api/load', fileBase64 ? { file: fileBase64, filename: filename } : {});
      STATE.ready = true;
      fnBtn.hidden = false;
      fnBtn.textContent = report.filename;
      document.title = 'Ledgerit — ' + report.filename;
      document.getElementById('unit-empty').hidden = true;
      document.getElementById('ask-bar').hidden = false;
      document.getElementById('unit-clean').hidden = false;
      await printCleaningReceipt(report);
    } catch (err) {
      // Wrong file type, unreadable, missing columns — whatever cleaner.py
      // rejected, shown where the user's attention already is: in the
      // dropzone before anything has loaded, in the usual ask-hint spot
      // once something has (so a bad swap doesn't blank the header).
      var message = "Couldn't load that file: " + err.message;
      if (firstLoad) {
        dzError.textContent = message;
        dzError.hidden = false;
      } else {
        document.getElementById('ask-hint').textContent = message;
      }
    } finally {
      fnBtn.disabled = false;
    }
  }

  /* ================= RECEIPT 2: answers — real analyst.answer() + explain.explain() ================= */
  async function printAnswer(question) {
    var unit = document.getElementById('unit-answer');
    unit.hidden = false;

    var paper = document.getElementById('paper-answer');
    var rowsHost = document.getElementById('rows-answer');
    var factsHost = document.getElementById('facts-answer');
    var nBlock = document.getElementById('narration-block');
    var nText = document.getElementById('narration-text');
    var nWarn = document.getElementById('narration-warn');
    var statusEl = document.getElementById('status-answer');

    rowsHost.innerHTML = '';
    factsHost.innerHTML = '';
    factsHost.hidden = true;
    nBlock.classList.remove('show');
    nText.innerHTML = '';
    nWarn.hidden = true;
    nWarn.classList.remove('show');
    statusEl.textContent = '';
    statusEl.classList.remove('show');
    ['head-answer','title-answer'].forEach(function(id){ document.getElementById(id).classList.remove('show'); });
    document.getElementById('title-answer').textContent = '';
    document.getElementById('answer-date').textContent = todayStamp();
    document.getElementById('answer-tag').textContent = question;

    paper.classList.remove('feed');
    void paper.offsetWidth;
    paper.classList.add('feed');
    unit.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });

    // /api/ask first, then /api/narrate — deliberately sequential, not
    // fired together. Both eventually call into the one loaded model
    // (classify() here, generation there) and llama.cpp's context isn't
    // safe for two threads to call into at once; running them back to
    // back is what keeps this crash-free. classify() alone is fast, so
    // the receipt still appears well before the 15s+ generation starts —
    // narration is passed the route /api/ask already resolved, so it
    // never reclassifies the question itself.
    var finding;
    try {
      finding = await api('/api/ask', { question: question });
    } catch (err) {
      await reveal(document.getElementById('head-answer'), 0);
      document.getElementById('title-answer').textContent = "Couldn't answer that";
      await reveal(document.getElementById('title-answer'), 0);
      statusEl.textContent = err.message;
      await reveal(statusEl, 0);
      return;
    }

    await sleep(REDUCED ? 0 : 480);
    await reveal(document.getElementById('head-answer'), 90);
    document.getElementById('title-answer').textContent = finding.headline;
    await reveal(document.getElementById('title-answer'), 140);

    var tableRows = tableToRows(finding.table);
    for (var i = 0; i < tableRows.length; i++) {
      var r = row(tableRows[i][0], tableRows[i][1]);
      rowsHost.appendChild(r);
      await reveal(r, 90);
    }

    var factKeys = Object.keys(finding.facts || {});
    if (factKeys.length) {
      factsHost.hidden = false;
      for (var k = 0; k < factKeys.length; k++) {
        var key = factKeys[k];
        var fl = el('div', 'factline');
        fl.innerHTML = '<b>' + esc(capFirst(key)) + ':</b> ' + esc(finding.facts[key]);
        factsHost.appendChild(fl);
        await reveal(fl, 110);
      }
    }

    statusEl.textContent = finding.route
      ? 'Routed to: ' + spaced(finding.route)
      : 'No exact match on a category — answered from the most relevant orders instead.';
    await reveal(statusEl, 220);

    // Narration — the slow half, requested only now that /api/ask has
    // resolved. Generation runs 15s+ on target hardware; this is an
    // indeterminate wait, not a fake countdown, because we genuinely
    // don't know how long is left.
    nBlock.classList.add('show');
    nText.innerHTML = '<span class="loading-dots"><i></i><i></i><i></i></span>';

    var narration = await api('/api/narrate', { question: question, label: finding.route })
      .catch(function (err) { return { error: true, message: err.message }; });
    nText.innerHTML = '';

    if (narration.error) {
      nText.textContent = "Couldn't generate an explanation: " + narration.message;
      return;
    }

    if (REDUCED) {
      nText.textContent = narration.text;
    } else {
      var words = narration.text.split(' ');
      for (var w = 0; w < words.length; w++) {
        nText.textContent += (w ? ' ' : '') + words[w];
        await sleep(16);
      }
    }

    if (narration.verified === false) {
      var msg = "Heads up: this explanation includes a figure Ledgerit couldn't verify against your data";
      if (narration.unsupported && narration.unsupported.length) {
        msg += ' (' + narration.unsupported.join(', ') + ')';
      }
      msg += narration.retried ? ' — even after a retry.' : '.';
      nWarn.hidden = false;
      nWarn.textContent = msg;
      await reveal(nWarn, 0);
    }
  }

  /* ---------------- wire up ---------------- */
  function submitAsk() {
    var input = document.getElementById('ask-input');
    var hint = document.getElementById('ask-hint');
    var val = input.value.trim();
    if (!val) return;
    if (!STATE.ready) { hint.textContent = 'Load a file first — drop one above, or try the sample.'; return; }
    if (STATE.asking) return;
    STATE.asking = true;
    hint.textContent = '';
    printAnswer(val).catch(function (err) {
      hint.textContent = 'Something went wrong: ' + err.message;
    }).finally(function () {
      STATE.asking = false;
    });
  }

  document.querySelectorAll('.chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      document.getElementById('ask-input').value = chip.textContent;
      submitAsk();
    });
  });
  document.getElementById('ask-go').addEventListener('click', submitAsk);
  document.getElementById('ask-input').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') submitAsk();
  });

  /* ---- file selection: header control (post-load), dropzone (pre-load) ---- */
  var fileInput = document.getElementById('file-input');
  document.getElementById('topbar-filename').addEventListener('click', function () { fileInput.click(); });

  function handleSelectedFile(file) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () {
      // readAsDataURL, not readAsText: the server does its own encoding
      // detection (UTF-8 BOM, Windows-1252, UTF-16, ...) against the raw
      // bytes. readAsText would force a decode to JS strings (UTF-8) in
      // the browser first, and once that's mis-decoded the original bytes
      // are gone — there'd be nothing left downstream to detect. Same
      // path for .xlsx, which is binary and was never text to begin with.
      var dataUrl = String(reader.result);
      var base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
      loadFile(base64, file.name);
    };
    reader.onerror = function () {
      var message = "Couldn't read that file.";
      if (STATE.ready) {
        document.getElementById('ask-hint').textContent = message;
      } else {
        var dzError = document.getElementById('dropzone-error');
        dzError.textContent = message;
        dzError.hidden = false;
      }
    };
    reader.readAsDataURL(file);
  }

  fileInput.addEventListener('change', function () {
    handleSelectedFile(fileInput.files && fileInput.files[0]);
    fileInput.value = '';
  });

  /* ---- the empty state: drop zone + browse + sample ---- */
  var dropzone = document.getElementById('dropzone');
  document.getElementById('dropzone-browse').addEventListener('click', function () { fileInput.click(); });
  document.getElementById('dropzone-sample').addEventListener('click', function () { loadFile(null, null); });

  var dragDepth = 0; // dragenter/dragleave fire on children too; a counter survives that, a boolean doesn't
  dropzone.addEventListener('dragenter', function (e) {
    e.preventDefault();
    dragDepth++;
    dropzone.classList.add('drag-over');
  });
  dropzone.addEventListener('dragover', function (e) { e.preventDefault(); });
  dropzone.addEventListener('dragleave', function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) dropzone.classList.remove('drag-over');
  });
  dropzone.addEventListener('drop', function (e) {
    e.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove('drag-over');
    var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    handleSelectedFile(file);
  });

  // The paper feeding out is caused by an upload, never by page load — so
  // there is deliberately no loadFile() call here. A miss on the drop
  // zone (dropped elsewhere on the page) would otherwise make the browser
  // navigate to/open the file, replacing the app — guard the whole
  // window against that.
  window.addEventListener('dragover', function (e) { e.preventDefault(); });
  window.addEventListener('drop', function (e) { e.preventDefault(); });
})();
</script>
"""

html = html.replace("__MONO400__", mono400)
html = html.replace("__MONO600__", mono600)
html = html.replace("__SANS400__", sans400)
html = html.replace("__SANS600__", sans600)

import os

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
with open(out_path, "w") as f:
    f.write(html)
print("wrote", out_path, len(html), "bytes")
print("wrote", out_path, len(html), "bytes")
