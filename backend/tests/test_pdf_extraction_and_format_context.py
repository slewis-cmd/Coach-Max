"""Tests for PDF text extraction robustness and the format-aware review helper.

These are pure unit tests — they exercise the helpers directly without hitting
Mongo, GridFS, or the LLM.
"""
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (  # noqa: E402
    _submission_format_context,
    extract_text_from_pdf,
)


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _build_reportlab_pdf(lines):
    """Build a PDF via reportlab (available in the container via fpdf2? we use pypdf's writer).

    We generate a simple PDF using pdfplumber's dependency (pdfminer.six via a
    tiny reportlab fallback). If reportlab isn't installed we build via fpdf2
    which IS in requirements.txt.
    """
    try:
        from fpdf import FPDF
    except ImportError:  # pragma: no cover
        pytest.skip("fpdf2 not available to build a test PDF")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    for line in lines:
        pdf.cell(w=0, h=10, text=line, new_x="LMARGIN", new_y="NEXT")
    # fpdf2 returns bytes via .output(dest='S')
    out = pdf.output(dest="S")
    return bytes(out)


def test_extract_text_from_pdf_reads_content():
    pdf_bytes = _build_reportlab_pdf([
        "Slide 1: Problem",
        "Nurses waste hours on paperwork.",
        "Slide 2: Solution",
        "ShiftSure automates credentialing.",
    ])
    text = extract_text_from_pdf(pdf_bytes)
    assert "Problem" in text
    assert "ShiftSure" in text
    assert "Solution" in text


def test_extract_text_from_pdf_handles_garbage_gracefully():
    # Not a real PDF — extractor should not crash, should just return "" or best-effort.
    text = extract_text_from_pdf(b"not a pdf at all")
    assert isinstance(text, str)
    # Should not raise. Empty or fallback plain-text is acceptable.


def test_extract_text_from_pdf_empty_bytes():
    text = extract_text_from_pdf(b"")
    assert text == ""


# ---------------------------------------------------------------------------
# Format-aware submission context
# ---------------------------------------------------------------------------

def test_format_context_video_recording():
    ctx = _submission_format_context({"file_name": "elevator.mp4"})
    assert ctx["kind"] == "video"
    assert ctx["descriptor"] == "your recording"
    assert "transcript" in ctx["guidance"].lower()
    assert "slide" not in ctx["descriptor"]


def test_format_context_audio_recording():
    ctx = _submission_format_context({"file_name": "pitch.mp3"})
    assert ctx["kind"] == "audio"
    assert ctx["descriptor"] == "your recording"


def test_format_context_slide_deck_via_title_hint():
    ctx = _submission_format_context(
        {"file_name": "mydeck.pdf"},
        assignment_title="Kawasaki 10-Slide Pitch Deck",
    )
    assert ctx["kind"] == "slide_deck"
    assert ctx["descriptor"] == "your slide deck"
    assert "slide" in ctx["guidance"].lower()


def test_format_context_generic_pdf_document():
    ctx = _submission_format_context(
        {"file_name": "writeup.pdf"},
        assignment_title="Business Reflection Essay",
    )
    assert ctx["kind"] == "document"
    assert ctx["descriptor"] == "your document"


def test_format_context_docx_document():
    ctx = _submission_format_context({"file_name": "answer.docx"})
    assert ctx["kind"] == "document"
    assert ctx["descriptor"] == "your document"


def test_format_context_questionnaire():
    ctx = _submission_format_context({
        "file_name": "",
        "submission_type": "business_questionnaire",
    })
    assert ctx["kind"] == "questionnaire"
    assert ctx["descriptor"] == "your questionnaire answers"


def test_format_context_text_writeup():
    ctx = _submission_format_context({"file_name": "notes.txt"})
    assert ctx["kind"] == "writeup"
    assert ctx["descriptor"] == "your writeup"


def test_format_context_unknown_extension_safe_default():
    ctx = _submission_format_context({"file_name": "weird.xyz"})
    # Should not crash; kind is a known label; guidance may be empty.
    assert ctx["kind"] in {"other", "writeup"}
    assert isinstance(ctx["descriptor"], str) and ctx["descriptor"]


def test_format_context_no_filename():
    ctx = _submission_format_context({})
    assert isinstance(ctx["descriptor"], str) and ctx["descriptor"]
    # Empty file_name with no submission_type falls into the writeup branch.
    assert ctx["kind"] in {"writeup", "other"}
