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
    # Not a real PDF — extractor should not crash, and MUST NOT dump the raw bytes
    # into the returned string (that would poison the AI review prompt).
    text = extract_text_from_pdf(b"not a pdf at all")
    assert isinstance(text, str)
    assert text == "", "extractor must not return raw bytes for a bogus PDF"


def test_extract_text_from_pdf_empty_bytes():
    text = extract_text_from_pdf(b"")
    assert text == ""


def test_extract_text_from_file_never_returns_raw_pdf_bytes():
    """Regression: when a real PDF has no extractable text AND OCR is unavailable/empty,
    extract_text_from_file must return "" — NOT the raw PDF header/streams. Otherwise
    the AI review prompt gets fed '%PDF-1.4', '/Creator (Google)', '/MediaBox …' and
    the LLM writes feedback about PDF internals instead of the student's work.
    """
    from server import extract_text_from_file  # noqa: WPS433 — test-local import

    # Minimal valid-ish PDF header bytes that PyPDF2 / pdfplumber will reject or
    # return empty for, and that OCR will not recover text from.
    fake_pdf = b"%PDF-1.4\n%garbage stream data here\n/Creator (Google)\n/Title (Title)\n%%EOF\n"
    result = extract_text_from_file(fake_pdf, "deck.pdf")
    assert "%PDF" not in result
    assert "/Creator" not in result
    assert "/Title" not in result
    assert "MediaBox" not in result


def test_extract_text_from_file_never_returns_raw_docx_bytes():
    """Same guarantee for .docx (which is a zip binary — decoding it dumps zip
    headers like 'PK\\x03\\x04' into the prompt)."""
    from server import extract_text_from_file  # noqa: WPS433

    zip_garbage = b"PK\x03\x04" + b"\x00" * 200
    result = extract_text_from_file(zip_garbage, "answer.docx")
    assert "PK" not in result or result == ""
    assert len(result) < 5, f"docx extractor should not leak binary; got: {result!r}"


def _build_image_only_pdf(text_lines):
    """Build an image-only PDF (text rendered into an image, no embedded text layer).

    Used to exercise the Tesseract OCR fallback. If PIL/fpdf2 aren't available
    or Tesseract isn't installed on the host we skip.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        from fpdf import FPDF
    except ImportError:  # pragma: no cover
        pytest.skip("PIL/fpdf2 not available to build an image-only PDF")

    # Render the text lines into a PNG image at OCR-friendly DPI.
    img = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except (OSError, IOError):
        font = ImageFont.load_default()

    y = 60
    for line in text_lines:
        draw.text((60, y), line, fill="black", font=font)
        y += 90

    img_path = "/tmp/_ocr_test_slide.png"
    img.save(img_path, "PNG")

    # Wrap the image in a PDF (no text layer at all).
    pdf = FPDF(unit="pt", format=(1200, 800))
    pdf.add_page()
    pdf.image(img_path, x=0, y=0, w=1200, h=800)
    return bytes(pdf.output(dest="S"))


def test_extract_text_from_pdf_ocr_fallback_for_scanned_decks():
    """Image-only PDFs (scanned decks) should be recovered via Tesseract OCR."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except Exception:
        pytest.skip("Tesseract binary not available on this host — skipping OCR test")

    pdf_bytes = _build_image_only_pdf([
        "KAWASAKI SLIDE DECK",
        "Problem: Nurses lose time",
        "Solution: ShiftSure",
    ])

    # Sanity: PyPDF2 alone should NOT recover this (no text layer).
    from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pypdf_text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    assert len(pypdf_text) < 40, "Test setup invalid — PDF has a text layer"

    # Full extractor should recover the OCR text.
    text = extract_text_from_pdf(pdf_bytes)
    lower = text.lower()
    # OCR is imperfect; accept partial matches on the most distinctive tokens.
    hits = sum(kw in lower for kw in ("kawasaki", "problem", "solution", "shiftsure", "nurses"))
    assert hits >= 2, f"OCR fallback failed to recover recognisable text; got: {text!r}"


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


def test_extract_text_from_pdf_vision_fallback_for_image_only_deck():
    """End-to-end: image-only PDF (Google-Slides-style export) should be recovered
    via the GPT-5.2 vision fallback even when Tesseract is unavailable.

    Skipped if EMERGENT_LLM_KEY is not set. Uses the same helper as the OCR test.
    """
    import os as _os
    if not _os.environ.get("EMERGENT_LLM_KEY"):
        pytest.skip("EMERGENT_LLM_KEY not set — skipping live vision integration test")

    pdf_bytes = _build_image_only_pdf([
        "KAWASAKI SLIDE DECK",
        "Problem: Nurses lose time",
        "Solution: ShiftSure automates it",
    ])

    text = extract_text_from_pdf(pdf_bytes)
    lower = text.lower()
    # At least two of the distinctive tokens must survive round-trip.
    hits = sum(kw in lower for kw in ("kawasaki", "problem", "solution", "shiftsure", "nurses"))
    assert hits >= 2, (
        f"Vision fallback failed to recover recognisable slide text; got: {text!r}"
    )
