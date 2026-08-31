# MincaAI — Senior Software Engineer take-home

You are inheriting a service that works, is in production, and is quietly
producing bad data. Your job is to make it better in four hours.

This is not a build-from-scratch exercise. The scaffolding is done. Everything
you spend time on should be work that moves a number.

---

## The situation

Insurance brokers send us spreadsheets of vehicle fleets. The files are messy:
bilingual headers, metadata blocks on top, subtotal rows that look like data,
a second table halfway down with the columns in a different order, values in
thousands, values in dollars, encodings chosen in 2009 and never revisited.

We turn those files into canonical records that a downstream system quotes
against. Wrong records reach clients as wrong quotes, so a confidently wrong
record costs us far more than a record we flagged for a human.

The service in `src/extractor/` does this today. It scores **-1.06** on the
corpus in `corpus/dev/`. A perfect score is +1.00. Doing nothing at all — never
emitting a record — scores -1.00.

Yes: as shipped, it is worse than switching it off. It is confident and it is
wrong, and the utility table below explains why that is the expensive
combination.

---

## Setup

```bash
make install
make test        # 15 tests. Three fail. They are not flaky.
make score       # runs the extractor over corpus/dev and scores it
```

No API key is required. The LLM seam ships with an offline stub so everything
runs immediately. If you set `OPENAI_API_KEY`, the real client is used instead.
Either way, you are not expected to spend money on this.

---

## How you are measured

`score.py` is the scorer we run. It is not a summary of the scorer — it is the
scorer. Read it. The utility table:

| outcome | utility |
|---|---|
| emitted, not flagged, every field correct | **+1.00** |
| emitted, not flagged, any field wrong | **-3.00** |
| emitted and flagged, within the review budget | **+0.10** |
| emitted and flagged, over the review budget | **-0.25** |
| a record you never emitted | **-1.00** |
| a record you emitted that does not exist | **-0.50** |

The headline is **macro-averaged by file**: each file's mean is computed on its
own, then averaged. Every file is worth the same regardless of its row count.

**The review budget is 20% of a file.** The people who work the review queue
have a capacity and that is it. Flags inside the budget earn +0.10; flags
beyond it cost -0.25, whether or not the record was any good.

So blanket flagging is not a floor you can sit on. Flag every record and you
score about **-0.38** with the parsing you inherited, or about **-0.19** if your
parsing were perfect. Both of those beat the **-1.06** you start from — which
tells you exactly how expensive confident-and-wrong is — and both are a long way
from +1.00. The question is not whether to flag. It is which 20% to spend the
queue on, and that is a judgement about your own uncertainty.

We also measure four things the scorer does not see:

- **Resilience.** We re-run everything with an LLM that fails 65% of the time:
  malformed JSON, hangs, rate limits, and — the interesting one — well-formed
  answers that are wrong. Your score under that client is compared to your
  score under the normal one.
- **Determinism.** We run the same corpus twice and compare. Same input, same
  records.
- **Throughput.** Wall clock over the whole corpus, and **LLM calls per file**.
  The ceiling is 8 calls per file and it is a gate, not a target. The service
  currently averages over 1,900.

  **You cannot reproduce that number locally, and we are telling you so.** The
  largest file in `corpus/dev/` is nineteen rows, so the service scores about
  9.5 calls per file there and looks almost compliant. The grading corpus
  contains a 40,000-row file, and the ceiling is judged against that. This is
  the one axis you have to reason about from the code rather than measure —
  read what happens per row and count.
- **Robustness.** A set of hostile files — empty, truncated, mislabelled
  extension, a 220 MB CSV, an archive that expands to 400 MB. Nothing may crash
  the process or exhaust memory. Emitting zero records for a file that is not a
  spreadsheet is the right answer.

### The LLM seam

Every model call must go through `LLMClient` in `src/extractor/llm.py`. The
grading harness substitutes its own implementation there. A call that reaches a
model by another route is invisible to it, and a submission whose call count is
zero under our client while the shipped client showed calls is treated as
having bypassed the seam.

Note what this implies: **the headline score is reachable with no model at
all.** Our own reference implementation scores +1.00 and makes zero LLM calls.
Where you put the model, and whether you put it anywhere, is your decision to
make and to defend.

---

## Scope

`BACKLOG.md` has nine items. **You cannot do nine items in four hours.** Picking
is the exercise. You have the scorer and the labelled dev corpus, so you can
measure which items are worth doing instead of guessing.

The backlog is what the team happened to report. Nobody audited the service
before writing it. `score.py --per-file` is the only thing in this repo that has
looked at every file, and it is one command.

We would rather see three items done well, measured, and written up than nine
half-done.

---

## What to send back

A repository (or a zip) containing your work, plus two short documents. One
page each. Longer is not better.

**`PRIORITIES.md`** — what you did, what you deliberately did not do, and the
number that drove each decision. "I skipped the Dockerfile because the score is
macro-averaged and packaging moves no axis" is a good line. "I ran out of time"
is a fine line too, if it is true.

**`MEASUREMENTS.md`** — your experiment log. Score before, score after, per
change. Include the changes you tried and reverted, and the number that killed
them. This is the document we read first.

Also fill in `SUBMISSION.md` (timing, AI tool usage, honesty clause).

There is no video to record.

**Send it to john.fofe@mincaai.com**, as a link to a Git repository or as a
zip attachment. If the repository is private, grant access to that address. Keep
your commit history — we read it, and a history that shows you measured before
you changed things works in your favour.

---

## Ground rules

- **Python 3.11+.** Use whatever libraries you would use at work.
- **Use AI assistants freely.** We assume you will; everyone does. Log your
  prompts in `SUBMISSION.md`. The test is built on the assumption that writing
  code is cheap, which is why it measures judgment rather than output.
- **Four hours of focused work.** Hard stop at five. If you are past five,
  stop and write down what you would have done next. We track honesty, not
  heroics, and we do check whether your write-up matches your score.
- **Ask.** Email john.fofe@mincaai.com. Clarifying questions are never
  penalised; building something that ignores the brief is.

---

## A note on the corpus

`corpus/dev/` is labelled and yours to study. We grade on a different, larger
corpus you have not seen.

Every kind of damage in the grading corpus also appears in `corpus/dev/`. The
grading corpus is harder because the damage is denser and combines within a
single file, never because it contains a surprise you had no way to anticipate.
If you handle everything in `corpus/dev/` honestly rather than by special-casing
it, you will do well.

Special-casing `corpus/dev/` is detectable and it will not transfer. We check.
