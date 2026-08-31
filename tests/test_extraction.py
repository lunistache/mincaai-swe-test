"""The test suite you inherited.

Three of these fail. They are not flaky and they are not environment problems:
each one describes a real defect in `pipeline.py`. Read them before you read
the code.

The rest pass. Passing is not the same as being right.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extractor.llm import LLMError
from extractor.pipeline import extract, find_header_row, map_columns_with_llm, parse_value

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "dev"


class ExplodingClient:
    """An LLM that is always down."""

    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        raise LLMError("service unavailable")


class GarbageClient:
    """An LLM that answers, but not with JSON."""

    def complete(self, prompt: str, *, timeout_s: float = 10.0) -> str:
        return "Certainly! The header is probably the first row."


# ---------------------------------------------------------------------------
# Passing
# ---------------------------------------------------------------------------


def test_clean_csv_extracts_every_row():
    result = extract(CORPUS / "dev_01_clean.csv")
    assert len(result.records) == 12
    assert result.records[0].brand
    assert result.records[0].year >= 1980


def test_header_is_found_below_the_preamble():
    rows = [["BROKER: X"], [], ["NIV", "Placa", "Marca", "Modelo", "Año"], ["1", "2", "3", "4", "2020"]]
    assert find_header_row(rows) == 2


def test_llm_failure_falls_back_to_keyword_mapping():
    header = ["NIV", "Placa", "Marca", "Modelo", "Año", "Valor Asegurado MXN", "Uso"]
    mapping, method, confidence = map_columns_with_llm(header, ExplodingClient())
    assert method == "fallback"
    assert confidence < 1.0
    assert set(mapping.values()) >= {"vin", "plate", "brand", "model", "year"}


def test_malformed_llm_response_falls_back():
    header = ["NIV", "Placa", "Marca", "Modelo", "Año"]
    mapping, method, _ = map_columns_with_llm(header, GarbageClient())
    assert method == "fallback"
    assert mapping


def test_empty_file_does_not_raise(tmp_path: Path):
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    result = extract(empty)
    assert result.records == []
    assert "file_is_empty" in result.warnings


def test_subtotal_row_is_not_emitted():
    result = extract(CORPUS / "dev_08_motos.xlsx")
    assert not any((r.brand or "").startswith("TOTAL") for r in result.records)


def test_plain_number_parses():
    assert parse_value("285000") == 285000.0
    assert parse_value("285,000") == 285000.0


# ---------------------------------------------------------------------------
# Failing. Each describes a defect.
# ---------------------------------------------------------------------------


def test_latin1_file_is_readable():
    """Brokers export Latin-1. We must not lose the whole file over an accent."""
    result = extract(CORPUS / "dev_03_multisection.csv")
    assert len(result.records) >= 10


def test_second_section_header_is_detected():
    """dev_03 carries two headers with different column orders. Both count."""
    result = extract(CORPUS / "dev_03_multisection.csv")
    assert len(result.records) == 19


def test_thousands_column_is_scaled():
    """A column labelled '(miles)' is in thousands of pesos, not pesos."""
    result = extract(CORPUS / "dev_05_thousands.csv")
    values = [r.value_mxn for r in result.records if r.value_mxn is not None]
    assert values, "no values extracted"
    assert min(values) > 10_000, f"values look unscaled: min={min(values)}"


# ---------------------------------------------------------------------------
# Passing, and worth a second look.
# ---------------------------------------------------------------------------


def test_usd_row_is_not_flagged():
    result = extract(CORPUS / "dev_04_usd.xlsx")
    assert all(r.needs_review is False for r in result.records)


def test_vin_is_returned_as_written():
    """Every VIN we emit is 17 uppercase alphanumerics, exactly as written."""
    result = extract(CORPUS / "dev_07_vin_errors.csv")
    vins = [r.vin for r in result.records if r.vin]
    assert vins
    assert all(len(v) == 17 and v.isalnum() and v.isupper() for v in vins)


@pytest.mark.parametrize("year", [1979, 2028, 0])
def test_year_outside_the_window_is_rejected(year: int, tmp_path: Path):
    path = tmp_path / "year.csv"
    path.write_text(
        "NIV,Placa,Marca,Modelo,Año,Valor Asegurado MXN,Uso\n"
        f"1HGCM82633A004352,AAA-111-A,Toyota,Corolla,{year},285000,Particular\n",
        encoding="utf-8",
    )
    assert extract(path).records == []
