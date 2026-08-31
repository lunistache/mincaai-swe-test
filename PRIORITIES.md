# Priorities

Live document, updated as work progresses. Full before/after numbers and diagnosis for every change are in `MEASUREMENTS.md`; this page is the reasoning for *why* each thing was picked or skipped.

## How I picked what to work on

Not the backlog's order. `score.py --per-file` on the baseline (-1.0577 macro) showed **4 of 11 files pinned at -3.00, the worst possible score** — and none of them were "never emitted"; all were "emitted confidently and wrong." Scoring is macro-averaged by file, so fixing a -3.00 file to +1.00 is worth exactly as much as fixing a -1.00 file to +1.00 and far more than optimizing a file that's already positive. So the plan is: **fix whatever is dragging a file to -3.00, in the order that clears the most files fastest**, then come back to the backlog items that don't show up as a -3.00 file in the dev corpus.

## Done

- **Deterministic `use` normalisation** (removes the per-row LLM call = backlog **B3**, plus fixes two defects *not* on the official backlog that I found by reading the raw files: a blank header cell over the `use` column in `dev_02_preamble.xlsx`, and numeric use-codes with an in-file legend in `dev_11_use_codes.csv`).
  Number: macro utility **-1.0577 → -0.3304**; those two files individually went -3.00 → +1.00; LLM calls **106 → 11** (9.6/file → 1.0/file, now under the 8/file ceiling and stays there at 40k rows since it's no longer per-row). Full diagnosis in `MEASUREMENTS.md` §1.

- **`value_mxn` fixes on `dev_05_thousands.csv` (B4) and `dev_10_accounting.csv`** (plus one undocumented defect: an invoice-value column stealing the mapping meant for the insured-value column).
  Number: macro utility **-0.3304 → +0.3969**; those two files individually went -3.00 → +1.00. **Zero files remain at -3.00** — the worst score anywhere in the corpus is now -1.00. `make test` 13/15 (B4's test now passes). Full diagnosis in `MEASUREMENTS.md` §2.

- **`dev_09_swapped.csv`** (undocumented — header says `Modelo, Año`, data rows have them reversed for every row): added a sampled, unanimous-vote detector that swaps the model/year column mapping when the data consistently contradicts the header.
  Number: macro utility **+0.3969 → +0.5787**; file went -1.00 → +1.00 (9/9 correct). `make test` still 13/15, no regressions (specifically checked `dev_08_motos.xlsx`, whose numeric model names like "250" the detector's unanimity guard is designed not to misfire on — still 11/11). Full diagnosis in `MEASUREMENTS.md` §3.

- **`dev_03_multisection.csv` (B1 Latin-1 fallback + B2 second header section)**, plus two mapping-robustness fixes this file's diagnosis surfaced (corrupted-accent tolerance in header matching; a partial LLM/stub mapping no longer permanently shadows the keyword fallback that could have completed it).
  Number: macro utility **+0.5787 → +0.7605**; file went -1.00 → +1.00 (19/19, both sections). **`make test` 15/15 — every originally-failing test now passes.** No file in the corpus remains at -1.00 or -3.00. Full diagnosis in `MEASUREMENTS.md` §4.

- **`dev_06_duplicates.xlsx` (B7)**: `deduplicate` keeps the first occurrence per file, matched by plate (falling back to VIN), using the same alphanumeric-only key `score.py` itself uses.
  Number: macro utility **+0.7605 → +0.7889**; file went +0.6875 → +1.00 (16/16, 0 spurious — was 10). **Zero spurious records anywhere in the corpus.** `make test` still 15/15. Full diagnosis in `MEASUREMENTS.md` §5.

- **B6 (VIN check-digit) + B5 (USD conversion), plus two undocumented year-parsing defects found along the way** (Excel's `'` force-text marker on a 2-digit year; a full date where only a year was wanted). For B5, the file's own metadata claims an 18.90 MXN/USD rate; I checked the arithmetic against the labels directly and it's unambiguously built on the brief's 17.5 — documented that decision at the point it's used in code, not just here.
  Number: macro utility **+0.7889 → +1.0000**. **Every file in the dev corpus now scores a perfect +1.00 — 140/140 records correct, 0 wrong, 0 missed, 0 spurious.** `make test` 15/15. Full diagnosis in `MEASUREMENTS.md` §6.

## Where this leaves the backlog

Every backlog item with a dev-corpus-visible effect (B1–B7) is done, plus five defects not on the official list that `score.py --per-file` surfaced along the way (a blank header cell, numeric use-codes with an in-file legend, an invoice-value decoy column, a swapped model/year column pair, and two year-format variants). B8 is partially addressed as a side effect of the `use`-normalisation and VIN fixes (an unresolved numeric use-code and an invalid VIN check digit both already flag/null rather than guess) — I'm not extending it further speculatively, since there's no dev-corpus signal left to test a broader flagging policy against, and guessing at what "low confidence" should mean without a number to check it against is exactly the kind of untested judgement call this exercise is about avoiding.

## Done — the four axes `score.py` can't show

- **Determinism**: ran the CLI twice, diffed the sorted output. Identical. Pass.
- **Resilience**: built a hostile LLM client matching the README's description (20% rate-limited, 15% timeout, 15% non-JSON, 15% well-formed-but-wrong, 35% genuine), ran it across 5 seeds, plus a client that fails 100% of the time. **Every run: macro utility +1.0000**, identical to the normal client. Not luck — the LLM is used for exactly one thing (header mapping) and every failure mode already has a real fallback (`map_columns_by_keyword`) or gets patched by `merge_missing_fields`.
- **Throughput**: the dev corpus tops out at 19 rows/file, so built two synthetic files to test what it can't: 40,000 rows / 1 section → 1 LLM call, 1.1s; 40,000 rows / 5 sections → 5 LLM calls, 1.1s. Calls scale with header *sections*, not rows — confirms `find_header_rows`' full-file scan didn't quietly reintroduce a per-row cost.
- **Robustness**: tested a truncated `.xlsx` and a real zip archive saved with a `.csv` extension. The archive case was already handled correctly (0 records, matches the README's stated correct answer). The truncated `.xlsx` **raised an unhandled `BadZipFile`** — caught by the CLI's own per-file `try/except` already, but not by `POST /extract`, which has no guard of its own. Fixed once, in `extract()` itself, so both callers are covered from one place: `read_rows` is now called inside a `try/except` that returns the same "zero records, warned" shape used for an empty file.
- **B9, quantified rather than assumed**: measured (not guessed) peak memory on a synthetic 40,000-row, 2.5MB CSV — **73MB peak, a ~28x multiplier.** Extrapolated to the README's stated 220MB hostile file, that's ~6GB peak — a real crash risk, not theoretical. A full streaming rewrite is too large a refactor for the time left (my B2 multi-section detection needs to see the whole file). Took the cheap partial win instead: `read_only=True` on openpyxl's `load_workbook`, a one-line change purpose-built for this — measured **108MB → 20MB (5.4x)** on a synthetic 40k-row `.xlsx`. `.csv` stays fully materialised.

None of this moved macro utility (still +1.0000) or `make test` (still 15/15) — these are exactly the axes the brief said are graded separately from the score. Full numbers and method in `MEASUREMENTS.md` §7.

## Deliberately not doing

- **A full streaming rewrite of `read_rows` for `.csv`** — the `.xlsx` half of B9 got a cheap, measured, low-risk win (`read_only=True`); the `.csv` half would require `find_header_rows` (needed for B2) to work off a bounded look-ahead instead of a full-file scan, and the whole `extract` loop to consume an iterator instead of a list. That's a structural rewrite with real regression risk to the +1.0000 dev-corpus score, for a benefit that's real but graded on a separate axis from the number I've spent this session protecting. Worth doing with a full day, not the time left here.
- **Dockerfile, structured logging, retry/backoff on the LLM call, richer OpenAPI docs, `.ods` support** — all listed in `BACKLOG.md` as "also mentioned, unprioritised." None of them move `score.py`'s macro utility, the LLM-calls-per-file ceiling, determinism, or robustness. Retry/backoff in particular is close to actively wrong here: the resilience test measures behavior *under* a failing LLM, and the seam is already down to ~1 call/file for header mapping only, with a working fallback — adding retries would only slow that failure path down, not improve correctness.
