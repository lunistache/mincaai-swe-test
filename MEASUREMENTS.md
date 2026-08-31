# Measurements

Experiment log. Every row is one command: `python score.py --predictions out.jsonl --labels corpus/dev/labels.csv --per-file`, run after `PYTHONPATH=src python -m extractor.cli --corpus corpus/dev --out out.jsonl`. Reverted changes stay in the table.

| # | Change | Macro utility | LLM calls/file | `make test` | Kept? | Note |
|---|---|---|---|---|---|---|
| 0 | Baseline (as inherited) | -1.0577 | 9.6 | 12/15 pass | — | See breakdown below |
| 1 | Rewrote `normalise_use` to be deterministic (no LLM call); added `complete_mapping_by_elimination` for blank-header columns; added per-file numeric use-code legend parsing (B3, plus two undocumented dev-corpus defects) | **-0.3304** | **1.0** | 12/15 pass (same 3 as baseline) | **yes** | See below |
| 2 | `value_mxn`: `prefer_insured_value_column` to stop the invoice-value column stealing the mapping; European accounting-format parsing (`"1.528.000,00"`); `(miles)` header → ×1000 scaling (B4, plus one undocumented dev-corpus defect) | **+0.3969** | **1.0** | 13/15 pass (B4's test now passes; B1/B2 remain, same file) | **yes** | See below |
| 3 | `fix_swapped_model_year_columns`: detects a model/year column transposition (sampled, unanimous vote across rows) and swaps the mapping — undocumented dev-corpus defect, not on the backlog | **+0.5787** | **1.0** | 13/15 pass (same 2 as #2, both B1/B2 on `dev_03`) | **yes** | See below |
| 4 | B1: `read_rows` falls back utf-8 → cp1252 → latin-1. B2: `find_header_rows` (plural) detects every header-like row and maps each section independently. Plus: corrupted-accent tolerance in header matching, and `merge_missing_fields` so a partial LLM/stub mapping can't silently shadow a field plain keyword matching would have found | **+0.7605** | **1.3** | **15/15 pass** | **yes** | See below |
| 5 | B7: `deduplicate` keeps the first occurrence per file (matched by plate, falling back to VIN), using the same alphanumeric-only key the scorer itself uses | **+0.7889** | **1.3** | 15/15 pass | **yes** | See below |
| 6 | B6: `vin_check_digit_valid` (ISO 3779) — a VIN that fails it is emitted as `null`, not passed through. B5: USD-marked cells converted at 17.5 MXN/USD (see note below on the file's own conflicting rate). Plus: `parse_year` tolerant of Excel's `'` force-text marker and of a full date where only a year was wanted (undocumented, found diagnosing dev_07) | **+1.0000** | **1.3** | **15/15 pass** | **yes** | See below |

---

## 0. Baseline

```
MACRO UTILITY  -1.0577   <- headline, mean over 11 files
```

- `make test` (no Makefile on this machine, ran `python -m pytest -q` directly): **12 passed, 3 failed** — `test_latin1_file_is_readable`, `test_second_section_header_is_detected`, `test_thousands_column_is_scaled`. All three are the known B1/B2/B4 defects, not environment issues.
- LLM calls: 106 across 11 files = **9.6/file**, already over the 8/file ceiling on files with at most 19 rows.

Per-file, worst to best:

| File | Score | Cause |
|---|---|---|
| `dev_02_preamble.xlsx` | -3.00 | all 14 records wrong on `use` |
| `dev_05_thousands.csv` | -3.00 | all 12 `value_mxn` off by 1000x (B4) |
| `dev_10_accounting.csv` | -3.00 | all 12 `value_mxn` wrong (two value columns + European number format) |
| `dev_11_use_codes.csv` | -3.00 | all 11 `use` wrong (numeric use codes `1/2/3` read literally) |
| `dev_03_multisection.csv` | -1.00 | 19 never emitted (Latin-1 crash, B1) |
| `dev_09_swapped.csv` | -1.00 | 9 never emitted (model/year columns swapped vs. header) |
| `dev_07_vin_errors.csv` | -0.23 | 3 bad VINs passed through unvalidated (B6) |
| `dev_04_usd.xlsx` | -0.09 | 3 USD-in-pesos cells read as pesos (B5) |
| `dev_06_duplicates.xlsx` | +0.69 | 16 correct, 10 duplicates emitted (B7) |
| `dev_01_clean.csv` | +1.00 | clean |
| `dev_08_motos.xlsx` | +1.00 | clean |

**Read:** four files sit at the worst possible score (-3.00) and none of them are "never emitted" — all are "emitted confidently and wrong." Because scoring is macro-averaged per file, fixing those four is the single biggest lever available, ahead of working the backlog in its listed order.

---

## 1. Deterministic `use` normalisation (fixes B3, plus two dev-corpus defects not on the backlog)

**Diagnosis** (`grep dev_02_preamble.xlsx out.jsonl` / `grep dev_11_use_codes.csv out.jsonl` against baseline `out.jsonl`, then inspected the raw files with openpyxl):

- `dev_02_preamble.xlsx`: every `use` came out `null`. Root cause: the header row has a **blank cell** over the data column that holds "Particular"/"Carga"/etc. — keyword matching has no header text to match against, so the column is silently unmapped. Not on the official backlog; found by reading the raw file.
- `dev_11_use_codes.csv`: every `use` came out as a raw digit (`"1"`, `"3"`). The file codes use as `1/2/3` and explains the mapping in a metadata line ("Clave de uso: 1 = Particular, 2 = Carga, 3 = Pasajeros") that nothing read. Also not on the backlog.
- `normalise_use` also called the LLM once per data row (B3) — 95 of the baseline's 106 calls were this.

**Change** (`src/extractor/pipeline.py`):
1. `complete_mapping_by_elimination`: when exactly one canonical field is still unmapped and exactly one header column is still unmapped after keyword/LLM matching, pair them. Only fires on an unambiguous 1-to-1 gap — general rule, not specific to this file.
2. `build_use_legend`: regex-scans every cell in the file for a `"N = Word"` pattern and builds a per-file code→category table, so the code scheme is read from the file rather than hard-coded (a different broker could use a different numbering).
3. `normalise_use` rewritten to be pure Python: passes text through uppercased (matches scorer's leading-token comparison), resolves a numeric code through that file's legend, and — if a numeric code has no legend to resolve it — sets `needs_review=True` instead of guessing, rather than calling a model.

**Result:**
```
MACRO UTILITY  -0.3304   <- was -1.0577
```
- `dev_02_preamble.xlsx`: -3.00 → **+1.00** (14/14 correct)
- `dev_11_use_codes.csv`: -3.00 → **+1.00** (11/11 correct)
- LLM calls: 106 → **11** total (9.6/file → 1.0/file) — now comfortably under the 8-call ceiling, and stays there on a 40k-row file since the call is per-file, not per-row.
- `make test`: still 12/15 — same three pre-existing failures (B1, B2, B4), untouched by this change. No new failures introduced.
- Not reverted.

**Still -3.00 and unexplained by this change:** `dev_05_thousands.csv` and `dev_10_accounting.csv` (both `value_mxn`, i.e. B4 and the accounting-format column) — next target.

---

## 2. `value_mxn` fixes on `dev_05_thousands.csv` and `dev_10_accounting.csv` (B4, plus one undocumented dev-corpus defect)

**Diagnosis** (compared raw file contents to `out.jsonl` after change #1):

- `dev_05_thousands.csv`: header is `Valor Asegurado MXN (miles)`. `parse_value("147")` → `147.0`; label wants `147000.00`. Exactly B4 as described in the backlog — no scaling logic existed anywhere.
- `dev_10_accounting.csv`: header has **two** `valor`-containing columns — `Valor Factura` (invoice price) and `Valor Asegurado MXN` (the actual insured value, what we want). `map_columns_by_keyword` claims the *first* column matching a needle for each field and moves on, so `value_mxn` got bound to `Valor Factura` — a completely different amount, not a formatting variant. Not on the official backlog; found by reading the raw file. Compounding it: numbers are in European accounting format (`"1.528.000,00"`, dot = thousands separator, comma = decimal). The old `parse_value` only strips non-digit/non-dot characters, so `"287.000,00"` silently became `287.0` (comma dropped, one dot left standing) and `"1.528.000,00"` (two dots) failed to parse at all and returned `None`. Two independent bugs stacked on the same column.

**Change** (`src/extractor/pipeline.py`):
1. `prefer_insured_value_column`: if the column mapped to `value_mxn` has "factura"/"invoice" in its header text, and another unclaimed column has "asegurad"/"insured" in its header text, redirect the mapping to that column instead. General rule (any file with an invoice-vs-insured decoy column benefits), not specific to this file.
2. `parse_value`: added a strict regex check for the European accounting shape (`\d{1,3}(\.\d{3})+,\d{2}`) — only when a number unambiguously matches that shape does it strip dots and convert the comma to a decimal point first. Verified this doesn't touch the existing passing case (`"285,000"` — single comma, no dot — still parses as `285000.0` via the untouched fallback path).
3. `value_column_is_thousands`: checks the mapped `value_mxn` column's header text for "miles"; if present, every parsed value in that column is multiplied by 1000.

**Result:**
```
MACRO UTILITY  +0.3969   <- was -0.3304
```
- `dev_05_thousands.csv`: -3.00 → **+1.00** (12/12 correct)
- `dev_10_accounting.csv`: -3.00 → **+1.00** (12/12 correct)
- **Zero files remain at -3.00.** The worst files are now -1.00 (never-emitted — `dev_03_multisection.csv`, `dev_09_swapped.csv`), a category the utility table treats as three times cheaper than confidently-wrong.
- `make test`: 13/15 now — `test_thousands_column_is_scaled` passes. `test_latin1_file_is_readable` and `test_second_section_header_is_detected` remain (B1/B2, same untouched file). No regressions.
- LLM calls unchanged at 1.0/file.
- Not reverted.

**Next targets, both -1.00 (never emitted), both on the "never emitted" side rather than "wrong":** `dev_03_multisection.csv` (B1 Latin-1 crash + B2 second header section) and `dev_09_swapped.csv` (undocumented — header says `Modelo, Año`, data rows have them reversed).

---

## 3. Fixed the model/year column swap in `dev_09_swapped.csv` (undocumented defect)

**Diagnosis:** header row is `NIV,Placa,Marca,Modelo,Año,Valor Asegurado MXN,Uso`, but every data row underneath has those two columns transposed — e.g. `...,Toyota,2018,Rav4,382000,...` (year value where the header says "Modelo", model text where it says "Año"). Not a per-row typo; every single row in the file has it, confirmed by reading the raw CSV directly. With the header-driven mapping trusted literally, `cells["year"]` received the text `"Rav4"`, `parse_year("Rav4")` returned `None`, and the row-rejection check (`if not brand or not model or year is None: reject`) silently dropped every row — hence -1.00, not -3.00: the program never got far enough to be *wrong*, it just gave up on all 9 rows before emitting anything.

**Change** (`src/extractor/pipeline.py`): added `fix_swapped_model_year_columns`, called right after header mapping. It samples up to 5 data rows and checks, per row, whether the cell under the "model" column parses as a plausible year (1980–2027) while the cell under the "year" column does not. Only if that holds **unanimously** across at least 2 sampled rows does it swap the two column assignments. The unanimity requirement is deliberate: a single row with a coincidentally numeric model name (e.g. a motorcycle model literally named "250", as seen in `dev_08_motos.xlsx`) must not trigger a false swap — only a column-wide, multi-row pattern does. General rule, not keyed to this filename.

**Result:**
```
MACRO UTILITY  +0.5787   <- was +0.3969
```
- `dev_09_swapped.csv`: -1.00 → **+1.00** (9/9 correct)
- `make test`: still 13/15 — same two pre-existing failures (B1, B2), both on `dev_03_multisection.csv`, untouched by this change. No regressions, including `dev_08_motos.xlsx` (the numeric-model-name file that the unanimity guard was specifically written to not misfire on) — still 11/11 correct.
- LLM calls unchanged at 1.0/file.
- Not reverted.

**Remaining -1.00 file:** `dev_03_multisection.csv` (B1 Latin-1 crash + B2 second header section) — last "never emitted" file, next target. After that, only partial-file damage remains: `dev_04_usd.xlsx` (-0.09, B5), `dev_07_vin_errors.csv` (-0.23, B6), `dev_06_duplicates.xlsx` (+0.69, B7 — 10 spurious duplicates on an otherwise-perfect file).

---

## 4. `dev_03_multisection.csv` — B1 (Latin-1) + B2 (second header section), plus two mapping-robustness fixes surfaced while diagnosing it

**Diagnosis:** two separate things stacked on the same file.

- **Not literally a decode crash in this checkout.** I checked the raw bytes: this specific copy of the file is valid UTF-8 byte-for-byte, so `read_rows`'s `path.read_text(encoding="utf-8")` doesn't actually raise here. But the "Año" header cell contains the literal UTF-8 bytes for U+FFFD (the Unicode replacement character) in place of "ñ" — the accent was already destroyed by some upstream process before this fixture reached me. So B1's documented symptom (a raised `UnicodeDecodeError` that the CLI swallows) isn't what reproduces locally; the same underlying damage (encoding mangling a Spanish accented character) instead shows up as a header word that fails every keyword match. I implemented the general fix anyway — `read_rows` now tries utf-8, then cp1252, then falls back to latin-1 (which never raises, since it maps all 256 byte values) — because the grading corpus is virtually certain to contain a file that genuinely fails to decode, and the backlog explicitly describes that exact crash.
- **B2 was real and straightforward to confirm:** the file has a second header row at line 16 (`Plate,Make,Model,Year,VIN,Vehicle Use,Insured Value` — English, different column order) introduced by a `--- Pagina 2 / Page 2 ---` marker row. `find_header_row` (singular) only ever returns the first match, so every row after the first header — including the second section — was mapped using the *first* section's column order.
- **A third bug only showed up while fixing the first two:** even after adding corrupted-accent tolerance to `map_columns_by_keyword`, the file still produced 0 records. Root cause: `extract()` primarily calls `map_columns_with_llm`, which has its own independent, cruder text matching and returns as soon as it finds *any* non-empty mapping — it never falls back to (the now-fixed) `map_columns_by_keyword`. The stub's matching also couldn't recognise the corrupted "año" text, silently dropped `year` from its result, and — since it still found the other 6 fields — returned that incomplete mapping as a "success." `complete_mapping_by_elimination` (from change #1) didn't catch it either: this CSV pads every row with 13 trailing empty columns, so "exactly one unmapped column" was never true (14 unmapped, not 1).

**Change** (`src/extractor/pipeline.py`):
1. `read_rows`: utf-8 → cp1252 → latin-1 fallback chain (B1, general).
2. `find_header_rows` (new, plural): scans every row, not just the first; a row counts as a header when it has ≥3 filled cells *and* keyword-matches ≥3 canonical fields (a data row is VINs and numbers, not the words "vin"/"marca"). Falls back to the old single-header behaviour if nothing scores that high, so single-header files are unaffected. `extract()` now loops over every detected header section, mapping and parsing each independently (B2).
3. `HEADER_PATTERNS["year"]`: a word-bounded regex `\ba.o\b` as a fallback when no needle matches — tolerates a single corrupted character where "año"/"ano" should be, without matching inside unrelated words (checked against false-positiving on words like "trabajo").
4. `merge_missing_fields` (new): after `map_columns_with_llm` returns, fill in any canonical field it missed using `map_columns_by_keyword` — without this, an incomplete-but-non-empty LLM/stub mapping permanently shadows the keyword fallback and its corrupted-accent tolerance.

**Result:**
```
MACRO UTILITY  +0.7605   <- was +0.5787
```
- `dev_03_multisection.csv`: -1.00 → **+1.00** (19/19 correct — both sections)
- `make test`: **15/15 pass** — the last two known defects (B1, B2) are cleared, no regressions anywhere else in the suite.
- LLM calls: 11 → 14 total, 1.0/file → 1.3/file (a multi-section file now makes one header-mapping call per section instead of one per file) — still far under the 8/file ceiling.
- Not reverted.

**Remaining, all partial-file damage now (no file left at -1.00 or -3.00):** `dev_07_vin_errors.csv` (-0.23, B6), `dev_04_usd.xlsx` (-0.09, B5), `dev_06_duplicates.xlsx` (+0.69, B7 — 10 spurious duplicates on an otherwise-perfect 16/16 file).

---

## 5. Deduplication on `dev_06_duplicates.xlsx` (B7)

**Diagnosis:** the workbook has 3 sheets — `Enero` (10 vehicles), `Altas` (6 new vehicles), `Consolidado` (a year-end restatement sheet that repeats all 10 `Enero` vehicles verbatim — same VIN, same everything — with the plate reformatted without dashes, e.g. `AAA-002-Z` → `AAA002Z`). 10 + 6 = 16, matching the label count exactly, confirming `Consolidado` contributes zero new vehicles. `read_rows` already concatenates all sheets into one row list and `extract` emitted every row from every sheet, so those 10 restated rows came out as 10 extra records with the same underlying vehicle as their `Enero` counterpart. The scorer's own duplicate detection (`load_predictions` in `score.py`) already caught this — it joins on `(source_file, normalised plate)`, and its `norm_identifier` strips all non-alphanumeric characters, so `AAA-002-Z` and `AAA002Z` collapse to the same key there — but it can only mark the second occurrence "spurious" (-0.50 each); it has no way to *not* penalize a duplicate we chose to emit.

**Change** (`src/extractor/pipeline.py`): added `deduplicate`, called once at the end of `extract()` across every section's combined record list. It keeps the first occurrence of each vehicle and drops the rest, matched by plate — using `_identifier_key`, alphanumeric-only and uppercased, the same normalisation `score.py`'s `norm_identifier` uses, specifically so a formatting difference in the plate (dashes, spaces) can never cause our own dedup to miss what the scorer would still consider identical. Falls back to VIN when a plate is missing; a record with neither is left alone (nothing reliable to match it on) rather than guessed away.

**Result:**
```
MACRO UTILITY  +0.7889   <- was +0.7605
```
- `dev_06_duplicates.xlsx`: +0.6875 → **+1.00** (16/16 correct, 0 spurious — was 10)
- **Zero spurious records anywhere in the corpus** (previously 10, all from this file).
- `make test`: still 15/15, no regressions.
- LLM calls unchanged at 1.3/file.
- Not reverted.

**9 of 11 files now score a perfect +1.00.** Remaining: `dev_07_vin_errors.csv` (-0.23, B6 — 3/13 wrong on `vin`) and `dev_04_usd.xlsx` (-0.09, B5 — 3/11 wrong on `value_mxn`), both partial-file damage, next targets.

---

## 6. B6 (VIN check digit) and B5 (USD conversion) together, plus two more undocumented year-parsing defects found diagnosing `dev_07`

**Diagnosis, `dev_07_vin_errors.csv`:** compared raw rows to `labels.csv`. Three rows (`AAA003T`, `AAA003Y`, `AAA004D`) have a 17-character, alphanumeric VIN that *looks* legitimate but the label expects `null` — these are the "retyped by hand" VINs the backlog describes, and passing the length check alone isn't enough to catch them. Two more rows never appeared in the output at all: `AAA003W`'s year cell is `'23` (Excel's leading-apostrophe marker that forces a cell to store as text, here on a 2-digit year) and `AAA004A`'s year cell is `2020-01-01` (a full date instead of a bare year) — both fail the original `int(float(str(cell)))` parse outright, so the row is silently rejected before validation is even attempted. Not on the backlog; found by reading the raw file after the VIN diagnosis turned up two other unexplained "never emitted" rows.

**Diagnosis, `dev_04_usd.xlsx` (the rate conflict):** the file's own metadata reads `Tipo de cambio aplicado: TC 18.90 MXN/USD`. I checked the arithmetic against the labels directly: `USD 64,742.86` (row `AAA002B`) × 17.5 = 1,133,000.05 ≈ the label's 1,133,000.00; the same cell × 18.90 = 1,223,640.05, nowhere close. Same result for the other two USD rows (`AAA002E`: 73,714.29 × 17.5 = 1,290,000.08 ≈ label 1,290,000.00; `AAA002J`: 8,571.43 × 17.5 = 150,000.03 ≈ label 150,000.00). **Decision: convert at the brief's stated 17.5 MXN/USD and ignore this file's own claimed rate** — the labels were unambiguously built on 17.5, and a file's self-reported rate is exactly the kind of unverified broker input this service exists to not trust blindly.

**Change** (`src/extractor/pipeline.py`):
1. `vin_check_digit_valid`: full ISO 3779 check-digit implementation (transliteration table, position weights, mod-11, `X` for remainder 10). `parse_vin` now returns `None` for a VIN that fails it, instead of accepting anything 17 characters long.
2. `parse_value`: detects a `USD`/`US$` marker, strips it, and multiplies the parsed number by the `USD_TO_MXN = 17.5` constant (documented at the constant, with the arithmetic above, precisely because the file itself argues for a different number).
3. `parse_year`: strips a leading `'`; a bare 2-digit result is expanded to whichever of 2000+YY or 1900+YY falls inside `[YEAR_MIN, YEAR_MAX]`; otherwise falls back to extracting a `(19|20)\d{2}` run from the text (matching the scorer's own `norm_year`, so a full date resolves to its year) before the original plain-number parse.

**Result:**
```
MACRO UTILITY  +1.0000   <- was +0.7889
```
- **All 11 files at a perfect +1.00.** 140/140 records correct, 0 wrong, 0 missed, 0 spurious, 0 over-budget flags.
- `dev_07_vin_errors.csv`: -0.23 → **+1.00** (13/13 — including the 2 previously-missing rows now parsed and the 3 previously-wrong VINs now correctly nulled)
- `dev_04_usd.xlsx`: -0.09 → **+1.00** (11/11)
- `make test`: **15/15**, no regressions — specifically checked that no *other* file's VINs got wrongly nulled by the new check-digit logic (they didn't; every already-correct file stayed at +1.00).
- LLM calls unchanged at 1.3/file.
- Not reverted.

**Dev corpus is now maxed out at the scorer's own headline number.** Remaining time goes to the axes the scorer can't show locally: resilience (the hostile-LLM harness), determinism, throughput at 40k-row scale, and robustness (hostile files) — see `PRIORITIES.md`.

---

## 7. The four axes `score.py` can't show: resilience, determinism, throughput, robustness

Not tied to a single code change — a set of checks against what's already built, plus two robustness fixes the checks surfaced.

**Determinism.** Ran the CLI twice over `corpus/dev`, sorted both outputs, diffed: identical. **PASS.**

**Resilience.** Built a `HostileClient` (`scratchpad/resilience_client.py`, not part of the submission) matching the README's description: 20% rate-limited, 15% simulated timeout, 15% well-formed-non-JSON, 15% well-formed-JSON-but-wrong-content, 35% genuine. Ran it across 5 different random seeds, plus a second client that fails **100% of the time** unconditionally.
```
Normal StubClient:     macro utility +1.0000
Hostile (5 seeds):     macro utility +1.0000 (every seed)
Always-fails client:   macro utility +1.0000
```
Not a fluke — it's structural. The LLM is used for exactly one thing (header mapping, 1 call per section), and every failure mode already routes to a real fallback: `map_columns_with_llm` catches `LLMError`/`JSONDecodeError` and calls `map_columns_by_keyword`; a well-formed-but-wrong answer produces an empty or garbage mapping that the `if mapping:` check treats the same as a failure; and `merge_missing_fields` (change #4) patches any partial success regardless of cause. The pipeline's correctness on this corpus does not depend on the model working at all — consistent with the README's own claim that a zero-LLM-call implementation reaches +1.00.

**Throughput at scale.** The dev corpus tops out at 19 rows/file, so the 40,000-row, 8-calls/file ceiling can't be tested directly — built two synthetic files to check the two things that could break it:
- 40,000 rows, one header section: **1 LLM call**, 40,000/40,000 records, **1.1 seconds**.
- 40,000 rows, 5 header sections (broker pagination): **5 LLM calls**, 40,000/40,000 records, **1.1 seconds**.
Calls scale with header *sections*, not rows — confirms `find_header_rows`' full-file scan (needed for B2) doesn't reintroduce the per-row cost that B3's fix removed elsewhere. Would need roughly 9 sections in one file to breach the 8-call ceiling; nothing in the dev corpus goes past 2.

**Robustness.** Tested a truncated `.xlsx` (first 500 bytes of a real file) and a real zip archive saved with a `.csv` extension:
- Mislabelled archive: handled correctly already — 0 records, all rows rejected as invalid data (matches the README's stated correct behaviour for a non-spreadsheet file).
- Truncated `.xlsx`: **raised an unhandled `BadZipFile`.** The CLI's own `try/except Exception` around each file already prevents this from stopping a batch run, but `POST /extract` in `api.py` has no equivalent guard — an uploaded corrupt file would 500 with no graceful handling. Fixed by wrapping the `read_rows` call in `extract()` itself in a `try/except`, returning the same "zero records, warned" shape used for an empty file (`warnings=["file_unreadable:<ExceptionType>"]`) — this protects both callers from one place instead of duplicating a guard in each. Verified: no exception now, `make test` still 15/15, dev-corpus score still +1.0000.

**Memory (B9), quantified rather than assumed.** Measured peak memory (`tracemalloc`) extracting a synthetic 40,000-row, 2.5MB CSV: **73 MB peak — a ~28x multiplier over file size.** Extrapolated to the README's stated 220MB hostile CSV, that's roughly **6GB of peak memory**, a real crash risk on a typical container, not a theoretical one. A full streaming rewrite (generator-based `read_rows` plus reworking `find_header_rows`, which needs to see the whole file to locate every section, and the whole `extract` loop to consume an iterator instead of a list) is a large, high-risk refactor for the time remaining. Took the cheap, low-risk partial win instead: added `read_only=True` to openpyxl's `load_workbook` call for `.xlsx` files — a one-line change specifically designed for large-file memory efficiency (it stops openpyxl building its own full in-memory DOM of the worksheet on top of the row list we build anyway). Measured its effect directly on a synthetic 40,000-row `.xlsx`: **108MB → 20MB peak during parsing, a 5.4x reduction**, for near-zero implementation risk. `.csv` remains fully materialised — see `PRIORITIES.md` for why that's not being tackled now.

**Net effect on the headline number: none of this changed macro utility (still +1.0000) or `make test` (still 15/15)** — these are the axes the brief said are graded separately from the score, and this section is exactly the audit trail for them.
