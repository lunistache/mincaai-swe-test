"""Official scorer. This is the exact script we run on the held-out corpus.

Run it against the dev corpus as often as you like:

    python score.py --predictions out.jsonl --labels corpus/dev/labels.csv

The headline number is MEAN UTILITY PER RECORD. It is not accuracy. Read the
utility table before you optimise anything.

    emitted, not flagged, every field correct     +1.00
    emitted, not flagged, any field wrong         -3.00
    emitted and flagged, within the review budget +0.10
    emitted and flagged, over the review budget   -0.25
    a record you never emitted                    -1.00
    a record you emitted that does not exist      -0.50

A wrong record that nobody flagged flows into a quote sent to a client, so it
costs three times what a correct one earns.

THE REVIEW BUDGET is the part worth reading twice. The humans who work the
review queue have a capacity, and it is 20% of a file. Flagging a record inside
that budget earns +0.10; every flag beyond it costs -0.25, whether or not the
record was any good. Blanket flagging is therefore not a floor you can sit on:
flag every record and you score about -0.38 with the parsing you inherited, or
about -0.19 with perfect parsing. Both beat the -1.06 you start from, which is
the measure of how expensive confident-and-wrong is, and both are a long way
from +1.00. The question is not whether to flag. It is which 20% to spend the
queue on.

THE HEADLINE IS MACRO-AVERAGED BY FILE. Each file's mean utility per record is
computed on its own, then those per-file means are averaged. Every file is
worth the same regardless of how many rows it has, so a large clean file cannot
drown out a small nasty one, and the way to raise your score is to fix a file
you are failing rather than to process more rows of one you already handle.

Emitting nothing scores -1.00. Emitting extra records cannot raise the mean,
only lower it.

FIELD COMPARISON is defined by `fields_match` below. Read it. It is the whole
specification of what "correct" means, and it is deliberately forgiving about
formatting and unforgiving about magnitude: a value that is 1000x off because
the column was in thousands, or 17.5x off because it was in USD, is wrong.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Utility constants. The contract; do not edit them locally or your
# self-scoring will diverge from ours.
# ---------------------------------------------------------------------------
U_CORRECT = 1.00
U_WRONG = -3.00
U_FLAGGED = 0.10
U_FLAGGED_OVER_BUDGET = -0.25
U_MISSED = -1.00
U_SPURIOUS = -0.50

# How much of a file the review queue can absorb. Flags beyond this share of a
# file's records stop being cheap: a queue nobody can work is not triage.
REVIEW_BUDGET_SHARE = 0.20
REVIEW_BUDGET_FLOOR = 1  # every file gets at least one free flag

CANONICAL_FIELDS = ("vin", "plate", "brand", "model", "year", "value_mxn", "use")

# Brand spellings we treat as the same manufacturer. Extending this list on
# your side does not change our run, so do not rely on it.
BRAND_ALIASES = {
    "VW": "VOLKSWAGEN",
    "VOLKS": "VOLKSWAGEN",
    "CHEVY": "CHEVROLET",
    "GM": "CHEVROLET",
    "MERCEDES": "MERCEDES-BENZ",
    "MERCEDES BENZ": "MERCEDES-BENZ",
    "MB": "MERCEDES-BENZ",
    "VOLKSWAGON": "VOLKSWAGEN",
}

_WHITESPACE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Normalisation. Formatting differences are forgiven; substance is not.
# ---------------------------------------------------------------------------


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return isinstance(value, str) and not value.strip()


def norm_identifier(value: Any) -> str | None:
    """VIN and plate: alphanumerics only, uppercased."""
    if _blank(value):
        return None
    return "".join(ch for ch in str(value) if ch.isalnum()).upper() or None


def norm_text(value: Any) -> str | None:
    """Brand, model, use: uppercase, collapsed whitespace, no trailing '.0'."""
    if _blank(value):
        return None
    text = _WHITESPACE.sub(" ", str(value).strip()).upper()
    # A numeric model line read out of a float64 column arrives as "250.0".
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".")[0]
    return text or None


def norm_brand(value: Any) -> str | None:
    text = norm_text(value)
    return BRAND_ALIASES.get(text, text) if text else None


def norm_use(value: Any) -> str | None:
    """Only the leading token is compared: 'CARGA PESADA' matches 'CARGA'."""
    text = norm_text(value)
    return text.split(" ")[0] if text else None


def norm_year(value: Any) -> int | None:
    if _blank(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    match = re.search(r"(19|20)\d{2}", text)
    return int(match.group(0)) if match else None


def norm_value(value: Any) -> float | None:
    if _blank(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(text)
    except ValueError:
        return None


def fields_match(field_name: str, predicted: Any, expected: Any) -> bool:
    """Compare one canonical field. This is the definition of 'correct'."""
    if field_name in ("vin", "plate"):
        return norm_identifier(predicted) == norm_identifier(expected)
    if field_name == "brand":
        return norm_brand(predicted) == norm_brand(expected)
    if field_name == "model":
        return norm_text(predicted) == norm_text(expected)
    if field_name == "use":
        return norm_use(predicted) == norm_use(expected)
    if field_name == "year":
        return norm_year(predicted) == norm_year(expected)
    if field_name == "value_mxn":
        got, want = norm_value(predicted), norm_value(expected)
        if got is None or want is None:
            return got is None and want is None
        # Tolerant of rounding, intolerant of magnitude. A thousands-scaled or
        # unconverted-USD figure is not within this band.
        return abs(got - want) <= max(1.0, abs(want) * 0.001)
    raise KeyError(field_name)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    source_file: str
    key: str
    utility: float
    kind: str  # correct | wrong | flagged | missed | spurious
    wrong_fields: tuple[str, ...] = ()


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)
    n_truth: int = 0

    @property
    def mean_utility(self) -> float:
        return sum(o.utility for o in self.outcomes) / self.n_truth if self.n_truth else 0.0

    def count(self, kind: str) -> int:
        return sum(1 for o in self.outcomes if o.kind == kind)

    @property
    def field_errors(self) -> dict[str, int]:
        tally: dict[str, int] = defaultdict(int)
        for outcome in self.outcomes:
            for name in outcome.wrong_fields:
                tally[name] += 1
        return dict(tally)


def _fail(message: str) -> None:
    sys.exit(f"score: {message}")


def load_predictions(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Read JSONL predictions, keyed by (source_file, normalised plate)."""
    if not path.exists():
        _fail(f"predictions file not found: {path}")

    predictions: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: list[tuple[str, str]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            _fail(f"{path}:{line_no} is not valid JSON ({exc.msg})")
        if not isinstance(record, dict):
            _fail(f"{path}:{line_no} is not a JSON object")
        source = str(record.get("source_file") or "").strip()
        if not source:
            _fail(f"{path}:{line_no} has no source_file")
        key = norm_identifier(record.get("plate"))
        if key is None:
            # No plate means we cannot join it. Counted as spurious below.
            key = f"__noplate__{line_no}"
        if (source, key) in predictions:
            # The same vehicle emitted twice is not a formatting quirk: a fleet
            # listed on two sheets and counted twice is a doubled premium. The
            # copy is scored as a record that does not exist.
            duplicates.append((source, key))
            continue
        predictions[(source, key)] = record

    if duplicates:
        print(f"note: {len(duplicates)} duplicate (source_file, plate) records; each scored as spurious\n")
    return predictions, duplicates


def load_labels(path: Path) -> list[dict[str, Any]]:
    import csv

    if not path.exists():
        _fail(f"labels file not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        _fail(f"labels file is empty: {path}")
    return rows


def build_report(
    predictions: dict[tuple[str, str], dict[str, Any]],
    labels: list[dict[str, Any]],
    duplicates: list[tuple[str, str]] = (),
) -> Report:
    report = Report(n_truth=len(labels))
    matched: set[tuple[str, str]] = set()

    for row in labels:
        identity = (row["source_file"], row["key"])
        prediction = predictions.get(identity)

        if prediction is None:
            report.outcomes.append(Outcome(row["source_file"], row["key"], U_MISSED, "missed"))
            continue

        matched.add(identity)

        if bool(prediction.get("needs_review")):
            report.outcomes.append(Outcome(row["source_file"], row["key"], U_FLAGGED, "flagged"))
            continue

        wrong = tuple(
            name for name in CANONICAL_FIELDS if not fields_match(name, prediction.get(name), row[name])
        )
        if wrong:
            report.outcomes.append(Outcome(row["source_file"], row["key"], U_WRONG, "wrong", wrong))
        else:
            report.outcomes.append(Outcome(row["source_file"], row["key"], U_CORRECT, "correct"))

    for identity in predictions.keys() - matched:
        report.outcomes.append(Outcome(identity[0], identity[1], U_SPURIOUS, "spurious"))

    for source, key in duplicates:
        report.outcomes.append(Outcome(source, key, U_SPURIOUS, "spurious"))

    apply_review_budget(report, labels)
    return report


def review_budget(record_count: int) -> int:
    """How many records of a file the review queue can absorb."""
    return max(REVIEW_BUDGET_FLOOR, int(record_count * REVIEW_BUDGET_SHARE))


def apply_review_budget(report: Report, labels: list[dict[str, Any]]) -> None:
    """Re-price the flags that exceed a file's review budget.

    The budget is per file and is a share of that file's labelled records, so
    it scales with the work a file represents rather than with how many rows a
    submission chose to emit. Which particular flags fall inside the budget is
    not something a submission can steer — only how many it spends — so the
    outcomes are re-priced in the order the labels are read, and the aggregate
    is the same whichever order that is.
    """
    truth_per_file: dict[str, int] = defaultdict(int)
    for row in labels:
        truth_per_file[row["source_file"]] += 1

    spent: dict[str, int] = defaultdict(int)
    for index, outcome in enumerate(report.outcomes):
        if outcome.kind != "flagged":
            continue
        spent[outcome.source_file] += 1
        if spent[outcome.source_file] <= review_budget(truth_per_file[outcome.source_file]):
            continue
        report.outcomes[index] = replace(
            outcome, utility=U_FLAGGED_OVER_BUDGET, kind="over_budget"
        )


def split_by_file(report: Report, labels: list[dict[str, Any]]) -> dict[str, Report]:
    counts: dict[str, int] = defaultdict(int)
    for row in labels:
        counts[row["source_file"]] += 1
    buckets: dict[str, Report] = {name: Report(n_truth=count) for name, count in counts.items()}
    for outcome in report.outcomes:
        # A spurious record can name a file that has no labels at all; it still
        # has to land somewhere or the penalty silently disappears.
        bucket = buckets.setdefault(outcome.source_file, Report(n_truth=0))
        bucket.outcomes.append(outcome)
    return buckets


def macro_utility(buckets: dict[str, Report]) -> float:
    """Mean of the per-file means. The headline."""
    scored = [b for b in buckets.values() if b.n_truth]
    if not scored:
        return 0.0
    return sum(b.mean_utility for b in scored) / len(scored)


def _format(title: str, report: Report) -> str:
    lines = [
        f"{title}  (labelled records: {report.n_truth})",
        f"  mean utility per record  {report.mean_utility:+.4f}",
        f"  correct, unflagged       {report.count('correct'):5d}",
        f"  wrong, unflagged         {report.count('wrong'):5d}   <- each one costs {U_WRONG:+.2f}",
        f"  flagged, within budget   {report.count('flagged'):5d}",
        f"  flagged, over budget     {report.count('over_budget'):5d}   <- each one costs {U_FLAGGED_OVER_BUDGET:+.2f}",
        f"  never emitted            {report.count('missed'):5d}",
        f"  emitted but not real     {report.count('spurious'):5d}",
    ]
    errors = report.field_errors
    if errors:
        ranked = ", ".join(f"{name} {count}" for name, count in sorted(errors.items(), key=lambda kv: -kv[1]))
        lines.append(f"  wrong fields             {ranked}")
    return "\n".join(lines)


def _reference_policies(buckets: dict[str, Report]) -> str:
    """What the degenerate strategies would score, macro-averaged like the headline.

    "Flag everything" is priced against the review budget, which is the whole
    point of the budget: it is no longer a floor to stand on.
    """
    means: list[float] = []
    for bucket in buckets.values():
        if not bucket.n_truth:
            continue
        emitted = bucket.n_truth - bucket.count("missed")
        budget = review_budget(bucket.n_truth)
        within = min(emitted, budget)
        over = max(0, emitted - budget)
        other = sum(o.utility for o in bucket.outcomes if o.kind in ("missed", "spurious"))
        means.append((within * U_FLAGGED + over * U_FLAGGED_OVER_BUDGET + other) / bucket.n_truth)

    flag_everything = sum(means) / len(means) if means else 0.0
    return "\n".join(
        [
            "Reference policies:",
            f"  flag every record you emitted   {flag_everything:+.4f}   <- priced against the review budget",
            f"  emit nothing at all             {U_MISSED:+.4f}",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Score an extraction submission.")
    parser.add_argument("--predictions", type=Path, required=True, help="JSONL, one canonical record per line")
    parser.add_argument("--labels", type=Path, required=True, help="Ground truth CSV")
    parser.add_argument("--per-file", action="store_true", help="Break the score down by source file")
    args = parser.parse_args()

    predictions, duplicates = load_predictions(args.predictions)
    labels = load_labels(args.labels)
    report = build_report(predictions, labels, duplicates)
    buckets = split_by_file(report, labels)

    scored_files = sum(1 for b in buckets.values() if b.n_truth)
    print(f"MACRO UTILITY  {macro_utility(buckets):+.4f}   <- headline, mean over {scored_files} files")
    print()
    print(_format("micro (all records pooled)", report))
    print()
    print(_reference_policies(buckets))

    if args.per_file:
        print()
        print("BY FILE")
        for name, bucket in sorted(buckets.items(), key=lambda kv: kv[1].mean_utility):
            print()
            print(_format(f"  {name}", bucket))


if __name__ == "__main__":
    main()
