PY ?= python3
CORPUS ?= corpus/dev
OUT ?= out.jsonl

.PHONY: install serve extract score test determinism clean

install:
	$(PY) -m pip install -r requirements.txt

serve:
	PYTHONPATH=src $(PY) -m uvicorn extractor.api:app --reload --port 8000

extract:
	PYTHONPATH=src $(PY) -m extractor.cli --corpus $(CORPUS) --out $(OUT)

score: extract
	$(PY) score.py --predictions $(OUT) --labels $(CORPUS)/labels.csv --per-file

test:
	$(PY) -m pytest -q

## Two runs over the same corpus must produce the same records.
determinism:
	PYTHONPATH=src $(PY) -m extractor.cli --corpus $(CORPUS) --out /tmp/run1.jsonl
	PYTHONPATH=src $(PY) -m extractor.cli --corpus $(CORPUS) --out /tmp/run2.jsonl
	@sort /tmp/run1.jsonl > /tmp/run1.sorted; sort /tmp/run2.jsonl > /tmp/run2.sorted; \
	if diff -q /tmp/run1.sorted /tmp/run2.sorted >/dev/null; then \
		echo "deterministic [OK]"; \
	else \
		echo "NOT deterministic [FAIL]"; diff /tmp/run1.sorted /tmp/run2.sorted | head -20; exit 1; \
	fi

clean:
	rm -f $(OUT) /tmp/run1.jsonl /tmp/run2.jsonl /tmp/run1.sorted /tmp/run2.sorted
