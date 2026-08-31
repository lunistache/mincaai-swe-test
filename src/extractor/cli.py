"""Batch CLI: run the extractor over a corpus directory and write JSONL.

    python -m extractor.cli --corpus corpus/dev --out out.jsonl

The output is what `score.py` reads: one canonical record per line. The run
report on stderr carries the numbers the throughput axis is measured from.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .pipeline import extract

SUPPORTED = {".csv", ".xlsx"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a corpus to JSONL.")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    paths = [p for p in sorted(args.corpus.iterdir()) if p.suffix.lower() in SUPPORTED and p.name != "labels.csv"]

    started = time.perf_counter()
    total_records = 0
    total_calls = 0
    failures: list[str] = []

    with args.out.open("w", encoding="utf-8") as handle:
        for path in paths:
            try:
                result = extract(path)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
                continue
            total_calls += result.llm_calls
            for record in result.records:
                handle.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")
                total_records += 1

    elapsed = time.perf_counter() - started
    report = {
        "files": len(paths),
        "records": total_records,
        "llm_calls": total_calls,
        "seconds": round(elapsed, 2),
        "failed_files": failures,
    }
    print(json.dumps(report, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
