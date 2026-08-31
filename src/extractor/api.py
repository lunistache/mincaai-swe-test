"""HTTP surface.

    POST /extract   multipart/form-data: file=<csv|xlsx>  ->  ExtractionResult

The contract is the same one the CLI writes. Keep it: the harness reads both.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

from .pipeline import extract
from .schema import ExtractionResult

app = FastAPI(title="Broker fleet extractor", version="1.0.0")

SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract", response_model=ExtractionResult)
async def extract_endpoint(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return JSONResponse(
            status_code=415,
            content={"detail": f"unsupported file type {suffix!r}", "supported": sorted(SUPPORTED_SUFFIXES)},
        )

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(await file.read())
        temporary = Path(handle.name)

    try:
        return extract(temporary)
    finally:
        temporary.unlink(missing_ok=True)
