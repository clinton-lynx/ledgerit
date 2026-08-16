# Ledgerit Gate 1 Video

Hard limit: 2 minutes. Target length: 1:50 to leave room for upload/transcode
differences. Use a short camera introduction, then screen capture with voiceover.

## Final Script and Shot List

| Time | Picture | Narration |
|---|---|---|
| 0:00-0:10 | On camera, then cut to Ledgerit's empty state with airplane mode visible | "My mother is a petty trader. Writing down sales was never the hard part. The hard part was turning a messy notebook or spreadsheet into an answer she could trust." |
| 0:10-0:22 | Hold on the green OFFLINE indicator, then drag in `building_materials_sales.csv` | "Ledgerit is an offline bookkeeping assistant for African small businesses. It runs on an ordinary 8 GB laptop, with no API fees and no internet connection during use." |
| 0:22-0:38 | Show the column-mapping confirmation and accept it | "Real shop files are rarely clean. Ledgerit detects unfamiliar columns, mixed formats, multiple sheets, and misplaced headers, then asks the owner to confirm instead of silently guessing." |
| 0:38-0:55 | Cleaning receipt prints; pause on duplicate/cleaning totals and a CHECK THIS mismatch | "The cleaning pipeline is deterministic. It removes duplicate rows, parses dates and currency text, and flags totals that do not equal quantity times unit price. It never silently rewrites a suspicious sale." |
| 0:55-1:18 | Ask `What are my best sellers?`; show the computed table immediately, then the local narration | "When the owner asks a question, pandas computes every figure. A quantized SmolLM3 model running locally only explains the result in plain English. Every number in its answer is checked against the computed evidence before it is shown." |
| 1:18-1:30 | Export the answer as PDF and briefly open the receipt-style result | "The owner can export any answer or cleaning report as a simple PDF to keep or share." |
| 1:30-1:47 | Show a clean architecture slide or the report benchmark table | "I tested several models and quantizations, fixed a chat-template failure that appeared in judge-facing runtimes, and selected a 1.5 gigabyte Q3 model using about 1.98 gigabytes of peak memory at 6.13 tokens per second on my development machine." |
| 1:47-1:55 | Return on camera or to the app with the OFFLINE indicator visible | "Ledgerit brings trustworthy bookkeeping analysis to the laptop already sitting on the shop counter. No cloud, no subscription, and no invented arithmetic." |

## Recording Checklist

- Record at 1080p, 30 fps, with the app window large enough for table text to read.
- Keep the full edit below 2:00; aim for 1:50-1:55.
- Turn on airplane mode before recording and keep the OFFLINE indicator visible.
- Use the building-materials file because it demonstrates mapping and a flagged total.
- Wait for the local narration to finish before moving to the next shot.
- Hold the CHECK THIS state for at least two seconds.
- Do not claim the benchmarks were measured on the ADTC standard laptop.
- Put captions on the final export; many judges will watch muted.
- Upload unlisted, verify playback at 1080p, then paste the link into Devpost.

## Final Devpost Text

One-line description:

> Ledgerit is an offline bookkeeping assistant that cleans messy sales files,
> flags entries that do not add up, and answers business questions on an 8 GB
> laptop without cloud APIs or subscription fees.

Suggested tags: `offline-ai`, `llama-cpp`, `gguf`, `small-business`,
`bookkeeping`, `nigeria`, `local-first`.
