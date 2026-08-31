# Backlog

Nine items, in no particular order. They are not equally valuable and they are
not sorted by value.

You cannot do all of them in four hours. Choose, and say why in
`PRIORITIES.md`. You have `score.py` and a labelled corpus; the cost of finding
out which of these matters is one command.

**This is what the team wrote down. It is not a list of everything that is
wrong with the service.** Nobody audited the extractor before filing these;
they are the things that happened to get reported. `score.py --per-file` knows
more than this document does.

---

**B1. Latin-1 and CP1252 files fail to load.**
`read_rows` decodes as UTF-8 and raises on anything else. The CLI catches it, so
the file is skipped silently and every record in it is lost.

**B2. Only the first header row is found.**
Several brokers paginate: a second table appears further down, often with the
columns in a different order, sometimes with English labels where the first
table had Spanish ones. Everything after the first section is currently parsed
against the wrong column mapping or dropped.

**B3. An LLM call per row.**
`normalise_use` calls the model once for every data row. On a 40,000-row file
that is 40,000 calls.

**B4. Values in thousands are read literally.**
Some brokers label the column "Suma Asegurada (miles)" and write 420 for
420,000 pesos.

**B5. USD cells are read as pesos.**
A minority of cells are written `USD 24,000.00` in an otherwise peso column. The
brief rate is 17.5 MXN/USD. Note that one file's metadata block names a
different rate; decide what you do about that and write it down.

**B6. No VIN validation.**
A VIN carries a check digit at position 9 (ISO 3779). Some VINs in these files
were retyped by hand and fail it. We currently pass them downstream as
identifiers.

**B7. The same vehicle can be emitted twice.**
Brokers repeat a fleet across sheets, or append a "consolidated" section that
restates earlier rows with the plate formatted differently.

**B8. `needs_review` is always False.**
Nothing is ever routed to a human, however unsure the parse was.

**B9. Files are read entirely into memory.**
`read_rows` builds a list of every row before anything is parsed.

---

## Also mentioned by the team, unprioritised

- A `Dockerfile`, so this runs the same way on every machine.
- Structured logging with a correlation ID per upload.
- Retry with exponential backoff around the LLM call.
- Richer OpenAPI documentation on `POST /extract`.
- Support for `.ods` files. One broker has asked twice.
