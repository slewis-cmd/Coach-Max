"""Tests for spreadsheet extraction + spreadsheet format-context classification."""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    _submission_format_context,
    extract_text_from_file,
    extract_text_from_spreadsheet,
)


def _build_xlsx(sheets: dict) -> bytes:
    """Build a minimal .xlsx workbook with the given {sheet_name: [rows]} data."""
    from openpyxl import Workbook
    wb = Workbook()
    # Remove the default empty sheet
    default = wb.active
    wb.remove(default)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_from_xlsx_preserves_sheet_and_cells():
    data = _build_xlsx({
        "Assumptions": [
            ["Metric", "Value", "Notes"],
            ["ARPU",   "$45",  "monthly"],
            ["Churn",  "5%",   "annualized"],
        ],
        "Customers": [
            ["Segment", "Count"],
            ["Nurses",  120],
            ["Doctors", 34],
        ],
    })
    text = extract_text_from_spreadsheet(data, "xlsx")
    assert "Sheet: Assumptions" in text
    assert "Sheet: Customers" in text
    assert "ARPU" in text
    assert "$45" in text
    assert "Nurses" in text
    assert "120" in text
    # Confirmed pipe-separated row rendering
    assert "|" in text


def test_extract_from_xlsx_via_file_dispatcher():
    """extract_text_from_file must route .xlsx to the spreadsheet extractor."""
    data = _build_xlsx({"Sheet1": [["A", "B"], [1, 2]]})
    text = extract_text_from_file(data, "template.xlsx")
    assert "Sheet: Sheet1" in text
    assert "A" in text and "B" in text


def test_extract_from_csv():
    data = b"name,role\nSarah,PM\nEd,Eng\n"
    text = extract_text_from_file(data, "roster.csv")
    assert "Sarah" in text
    assert "PM" in text


def test_spreadsheet_extraction_returns_empty_for_garbage_not_raw_bytes():
    """Regression: garbage input MUST NOT leak raw bytes into the AI prompt."""
    text = extract_text_from_spreadsheet(b"not a real xlsx", "xlsx")
    assert text == ""
    text2 = extract_text_from_file(b"not a real xlsx", "junk.xlsx")
    # Only accept empty here — never PK-header binary leakage.
    assert text2 == "" or ("PK" not in text2 and len(text2) < 5)


def test_format_context_xlsx():
    ctx = _submission_format_context({"file_name": "financials.xlsx"})
    assert ctx["kind"] == "spreadsheet"
    assert ctx["descriptor"] == "your spreadsheet"
    assert "spreadsheet" in ctx["guidance"].lower()
    assert "tab" in ctx["guidance"].lower() or "sheet" in ctx["guidance"].lower()


def test_format_context_csv():
    ctx = _submission_format_context({"file_name": "roster.csv"})
    assert ctx["kind"] == "spreadsheet"
    assert ctx["descriptor"] == "your spreadsheet"


def test_format_context_xls_legacy():
    ctx = _submission_format_context({"file_name": "older.xls"})
    assert ctx["kind"] == "spreadsheet"
