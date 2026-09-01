# Submission

> Fill in every section. Empty sections are graded as missing.

---

## 1. How to run it

**Repo / archive:**

https://github.com/lunistache/mincaai-swe-test (private — access must be granted to `john.fofe@mincaai.com`, see note below)

**Live interactive write-up (optional, not a required deliverable):**

Source in `docs/index.html`, the same content as `MEASUREMENTS.md` walked through interactively with a working copy of the scoring formula to try directly. Was hosted at `lunistache.github.io/mincaai-swe-test`, but GitHub Pages does not serve from a private repository on a free plan — the page went offline the moment the repo was made private, so there is no live link right now. Open `docs/index.html` directly in a browser to view it instead.

**One command a reviewer can copy-paste to reproduce your score:**

```
make install && make score
```

Note for the reviewer: developed and tested on Windows without `make` installed, so
locally this was run as the equivalent explicit commands (also works anywhere):

```
python -m pip install -r requirements.txt
PYTHONPATH=src python -m extractor.cli --corpus corpus/dev --out out.jsonl
python score.py --predictions out.jsonl --labels corpus/dev/labels.csv --per-file
```

**Anything we need that is not in `requirements.txt`:**

Nothing. No new dependencies were added — every fix is plain Python (stdlib `re`,
`csv`, `zipfile` exceptions) plus the libraries already listed. No `OPENAI_API_KEY`
is needed; the offline `StubClient` is sufficient to reproduce the score above (see
`PRIORITIES.md` and `MEASUREMENTS.md` §6 for why the pipeline was deliberately kept
LLM-light — it makes ~1 call per file, all for header mapping, none of it required
for the score itself).

---

## 2. Your score

Run this and paste the output verbatim. We re-run it; if the numbers disagree
we go with ours and read your write-up to understand why they differ.

```
make score
```

```
MACRO UTILITY  +1.0000   <- headline, mean over 11 files

micro (all records pooled)  (labelled records: 140)
  mean utility per record  +1.0000
  correct, unflagged         140
  wrong, unflagged             0   <- each one costs -3.00
  flagged, within budget       0
  flagged, over budget         0   <- each one costs -0.25
  never emitted                0
  emitted but not real         0

Reference policies:
  flag every record you emitted   -0.1928   <- priced against the review budget
  emit nothing at all             -1.0000

BY FILE
  dev_01_clean.csv          +1.0000  (12/12 correct)
  dev_02_preamble.xlsx      +1.0000  (14/14 correct)
  dev_03_multisection.csv   +1.0000  (19/19 correct)
  dev_04_usd.xlsx           +1.0000  (11/11 correct)
  dev_05_thousands.csv      +1.0000  (12/12 correct)
  dev_06_duplicates.xlsx    +1.0000  (16/16 correct)
  dev_07_vin_errors.csv     +1.0000  (13/13 correct)
  dev_08_motos.xlsx         +1.0000  (11/11 correct)
  dev_09_swapped.csv        +1.0000  (9/9 correct)
  dev_10_accounting.csv     +1.0000  (12/12 correct)
  dev_11_use_codes.csv      +1.0000  (11/11 correct)
```

| | value |
|---|---|
| macro utility on `corpus/dev` | **+1.0000** |
| LLM calls per file | **1.3** (14 calls / 11 files — see note below) |
| `make determinism` passes | **yes** (ran the CLI twice, sorted and diffed both outputs — identical) |
| `make test` result | **passed** (15/15) |

Note on LLM calls: the count is 1 call per file for a single-header file, and 1
call *per header section* for a multi-section file (e.g. `dev_03_multisection.csv`
makes 2, since it has two header rows). Verified this scales with sections, not
rows, using a synthetic 40,000-row file — 1 section → 1 call, 5 sections → 5
calls, both far under the 8-call ceiling. Full method in `MEASUREMENTS.md` §7.

---

## 3. Documents

- [x] `PRIORITIES.md` — what you did, what you skipped, and the number behind each choice
- [x] `MEASUREMENTS.md` — score before and after each change, including reverted ones

---

## 4. AI tool usage log

> Every prompt you sent to an AI assistant, in order. One line per prompt, one
> line on what you did with the answer. We expect this to be long — you are
> supposed to use these tools. A sparse log alongside a large diff is the thing
> we notice.

Tool used throughout: **Claude Code** (Sonnet 5), used interactively as a pair-programming
partner for the entire exercise — reading the brief, diagnosing each defect against
the labelled corpus, implementing fixes, and running the scorer after every change.

| # | Tool | Prompt (verbatim or close paraphrase) | What you did with the response |
|---|------|---------------------------------------|--------------------------------|
| 1 | Claude Code | "Read everything in this folder — the brief, the backlog, the scorer, the pipeline code, the tests, the dev corpus — and explain the whole test to me." | Reviewed the summary against the actual files myself before proceeding; used it as my starting map of the codebase (scoring rules, the 9 backlog items, which 3 tests fail and why) rather than acting on it blindly. |
| 2 | Claude Code | "Explain it again, in plain language, as if I have little experience." | Used this as my working mental model of the utility table (why confidently-wrong costs 3x more than not trying) and the review-budget mechanic before writing any code. |
| 3 | Claude Code | "Install dependencies, run the test suite, and run the scorer to get our starting numbers." | Got the baseline: macro utility -1.0577, 3/15 tests failing (B1/B2/B4), 106 LLM calls (9.6/file, already over the 8-call ceiling), and a `--per-file` breakdown showing 4 files pinned at the worst possible score, -3.00. This breakdown is what drove every prioritization decision afterward — fixing a -3.00 file to +1.00 is worth more to the macro-averaged score than any partial fix, so I asked for files to be fixed in that order rather than the backlog's listed order. |
| 4 | Claude Code | "Create `MEASUREMENTS.md` now, and keep it updated with a full before/after entry every time we make a change." | Reviewed and kept the file structure it proposed (a summary table plus one detailed section per change); used it as the running experiment log for the rest of the session. |
| 5 | Claude Code | "What's the single highest-leverage fix given the baseline breakdown?" | It identified that the `use` field was wrong on two different -3.00 files for two *different* root causes (a blank header cell on one file, uncoded numeric use-values with an in-file legend on another) — diagnosed this by comparing raw file contents to the output, not by guessing. Reviewed the diagnosis, agreed with the fix (deterministic `use` normalisation, removing the per-row LLM call entirely — also fixes backlog item B3), then had it implement, test, and score it. Result: -1.0577 → -0.3304, LLM calls 106 → 11. Kept. |
| 6 | Claude Code | "Also create `PRIORITIES.md` and keep it updated — what we did, what we're skipping, and the number behind each call." | Reviewed the reasoning framework it proposed (macro-averaging means whole-file flips beat partial fixes) and kept it as the guiding principle for the rest of the session. |
| 7 | Claude Code | "Move to the next one." | Diagnosed the two remaining -3.00 files as both being `value_mxn` bugs with different causes (a thousands-scale header, and a decoy invoice-value column plus European number formatting). Reviewed the fix, had it implemented and scored: -0.3304 → +0.3969, zero files left at -3.00. Kept. |
| 8 | Claude Code | "Continue with `dev_09_swapped.csv`." | Diagnosed a model/year column transposition (header order didn't match the data's actual order) not on the official backlog. Reviewed the proposed fix's safeguard against false positives (requiring a unanimous signal across several rows, specifically checked against a motorcycle file with legitimately numeric model names) before accepting it. Result: +0.3969 → +0.5787. Kept. |
| 9 | Claude Code | "Continue." | Diagnosed `dev_03_multisection.csv`: found the file was actually valid UTF-8 with an already-corrupted accent character (not a literal decode crash as the backlog description implied), a genuine second header section in a different language/column order, and — found mid-fix — a partial AI-mapping result silently shadowing a better keyword-based one. Reviewed all three fixes and had them implemented together. Result: +0.5787 → +0.7605, all 15 tests passing for the first time. Kept. |
| 10 | Claude Code | "Continue." | Diagnosed `dev_06_duplicates.xlsx`: a 3-sheet workbook where one sheet was a verbatim restatement of another with reformatted plate numbers. Reviewed the dedup approach (matching the scorer's own plate-normalisation logic so it can't miss what the scorer would also miss) and had it implemented. Result: +0.7605 → +0.7889, zero spurious records left anywhere. Kept. |
| 11 | Claude Code | "Continue with both remaining files." | For the VIN file: reviewed the proposed real ISO 3779 check-digit implementation before accepting it (rather than a shortcut). For the USD file: it found the file's own metadata claimed a different exchange rate than the brief, checked the arithmetic against the labels directly to settle which rate was actually correct, and documented that decision at the point it's used in code. Result: +0.7889 → +1.0000 — every file at a perfect score, all 15 tests passing. Kept. |
| 12 | Claude Code | "Run the resilience, determinism, throughput, and robustness checks — the axes the scorer can't show locally." | Reviewed each result before accepting: a hostile 65%-failure LLM client across 5 seeds (still +1.0000 — confirmed this isn't luck, it's because the LLM is only used for header mapping with a real fallback), a determinism check (ran twice, diffed, identical), synthetic 40k-row files to test call-count scaling (1 call/section, not per row), and a robustness pass that caught a real bug — a truncated `.xlsx` crashed with an unhandled exception on the API path. Had that fixed and reverified. Also had it measure (not guess) memory usage and apply a cheap, low-risk win (`read_only=True` for Excel files) rather than attempt a full streaming rewrite under time pressure. |
| 13 | Claude Code | "Explain every change you made, in detail, for someone with little experience." | Used this as a correctness check on my own understanding before writing this submission — walked through the explanation against the actual diff to confirm nothing was glossed over or misrepresented. |
| 14 | Claude Code | "Explain how I can run and check the score myself, step by step." | Used the resulting instructions to independently verify the score on my own machine before trusting it enough to write it into this document. |
| 15 | Claude Code | "Fill in `SUBMISSION.md` — including this AI usage log — from what we actually did this session." | Reviewed the drafted score table, documents checklist, and this log against what actually happened; corrected nothing, kept as written. |
| 16 | Claude Code | "Can you create a repo on my GitHub for this?" | Answered its clarifying questions on visibility and name myself (chose public, and the existing folder name). Reviewed `git status` before the first commit to confirm no `out.jsonl` or credentials were staged, then checked the pushed repo on GitHub. |
| 17 | Claude Code | "Create an HTML page that explains all the steps of the process, with interactive things people can do on it." | Reviewed the published page against `MEASUREMENTS.md` to confirm every number on it (the score progression, the per-file before/after values, the utility table) matched what was actually measured, not a rounded or invented figure. |
| 18 | Claude Code | "Host this website with GitHub Pages." | Reviewed that this required wrapping the page into a standalone HTML document first (the interactive-artifact version depends on the Artifacts platform for its `<head>`/reset CSS and isn't a complete file on its own), then confirmed the page loads at the published URL and that the GitHub Pages build status came back "built." |
| 19 | Claude Code | "Complete the submission files with the website link, and anything else still missing." | Reviewing this document now; checked every section against the current state of the repo before considering it done. |

---

## 5. Timing

| | |
|---|---|
| Start (when you opened the brief) | 15:00 |
| End (when you stopped editing) | 17:47 |
| Total focused hours | 2h 47m |
| Went past the 4h target? | no |
| Hit the 5h hard stop? | no |

---

## 6. What you would do next

With another day: implement the full streaming rewrite for `.csv` (B9) that was
deliberately deferred this session — `read_rows` would need to become a generator,
and `find_header_rows` (which currently scans the whole file up front to locate
every section) would need to work off a bounded look-ahead instead. This is the
one remaining axis with a *measured*, not guessed, gap: a synthetic 40,000-row,
2.5MB CSV peaked at 73MB in memory, a ~28x multiplier that projects to roughly 6GB
on the README's stated 220MB hostile file. It moves the robustness axis, not the
macro utility score, which is why it was deferred rather than skipped.

Second: extend `needs_review` flagging beyond the two cases it covers today
(an unresolved numeric use-code, an invalid VIN) to a genuinely low-confidence
header mapping — there's no dev-corpus signal to test that against right now, so
building it without a number to validate it against felt like exactly the kind of
unmeasured guess this exercise is testing for.

Third: revisit whether the ~1 LLM call per file for header mapping is worth keeping
at all, given the reference implementation apparently reaches +1.00 with zero calls
— the seam already survives a 100%-failure client on this corpus, so the call may
be pure surface area with no measured benefit.

---

## 7. Honesty clause

By signing below I confirm:

- No human other than me worked on this exercise.
- The AI tool usage log above is complete.
- The score I reported is the score I actually measured, on the corpus as
  shipped, with no per-file special-casing added to raise it.
- I did not search for, copy from, or adapt a publicly posted MincaAI
  take-home solution.
- **File deletion:** on submitting, I will delete every file related to this
  test from my machine and any cloud storage. The only remaining copy is the
  one I sent to MincaAI. MincaAI may ask me to confirm this at any point.

**Name:** Nicola Fontaine

**Date:** 31/08/2026

**Signature (typed name is fine):** Nicola Fontaine
