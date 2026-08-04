"""Tests for the Founder Progress Score display refactor (iteration_57).

Covers:
- Backend: POST /api/submissions/{id}/export-pdf must:
    * include a "Founder Progress Score: NN/100" header + tier label
    * strip any trailing "Progress Score: NN/100" line from the feedback body
    * do the same stripping for legacy "Readiness Score: NN/100" label
- Backend: passing a submission with readiness_score=None should NOT crash,
  and the PDF should NOT contain the "Founder Progress Score" header block.
"""
import io
import os
import re
import sys
import uuid
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

sys.path.insert(0, "/app/backend")

# Prefer pdfplumber (already installed) for reliable text extraction from fpdf2 output.
import pdfplumber  # noqa: E402


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def instructor_ctx(mongo):
    """Seed instructor + session + cohort + assignment used across tests."""
    suffix = uuid.uuid4().hex[:8]
    inst_id = f"TEST_inst_{suffix}"
    inst_token = f"TEST_itok_{suffix}"
    stu_id = f"TEST_stu_{suffix}"
    cohort_id = f"TEST_cohort_{suffix}"
    assignment_id = f"TEST_asgmt_{suffix}"
    milestone_id = f"TEST_ms_{suffix}_w2"

    mongo.users.insert_one({
        "user_id": inst_id, "email": f"TEST_inst_{suffix}@example.com",
        "name": "TEST Instructor", "role": "instructor",
    })
    mongo.user_sessions.insert_one({
        "session_token": inst_token, "user_id": inst_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    mongo.users.insert_one({
        "user_id": stu_id, "email": f"TEST_stu_{suffix}@example.com",
        "name": "TEST Student", "role": "student",
    })
    mongo.cohorts.insert_one({
        "cohort_id": cohort_id, "name": f"TEST Cohort {suffix}",
        "student_ids": [stu_id], "instructor_ids": [inst_id],
        "total_weeks": 14, "is_active": True,
    })
    mongo.assignments.insert_one({
        "assignment_id": assignment_id, "cohort_id": cohort_id,
        "title": "TEST Assignment", "is_active": True, "order": 1,
        "milestones": [{"milestone_id": milestone_id, "week_number": 2, "title": "Week 2"}],
    })

    ctx = {
        "inst_id": inst_id, "inst_token": inst_token,
        "stu_id": stu_id, "cohort_id": cohort_id,
        "assignment_id": assignment_id, "milestone_id": milestone_id,
    }
    yield ctx

    mongo.users.delete_many({"user_id": {"$in": [inst_id, stu_id]}})
    mongo.user_sessions.delete_many({"user_id": inst_id})
    mongo.cohorts.delete_many({"cohort_id": cohort_id})
    mongo.assignments.delete_many({"assignment_id": assignment_id})
    mongo.submissions.delete_many({"cohort_id": cohort_id})


def _seed_submission(mongo, ctx, feedback_text, readiness_score):
    sub_id = f"TEST_sub_{uuid.uuid4().hex[:8]}"
    mongo.submissions.insert_one({
        "submission_id": sub_id,
        "student_id": ctx["stu_id"],
        "cohort_id": ctx["cohort_id"],
        "assignment_id": ctx["assignment_id"],
        "milestone_id": ctx["milestone_id"],
        "ai_feedback": feedback_text,
        "readiness_score": readiness_score,
        "status": "draft",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "file_name": "TEST.pdf",
        "title": "TEST",
    })
    return sub_id


def _extract_pdf_text(pdf_bytes):
    text_pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text_pages.append(page.extract_text() or "")
    return "\n".join(text_pages)


def _export(sub_id, token):
    return requests.post(
        f"{BASE_URL}/api/submissions/{sub_id}/export-pdf",
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )


# -------------------- Progress Score label (new) --------------------
def test_export_pdf_progress_score_label_strips_and_renders_badge(mongo, instructor_ctx):
    feedback = (
        "Great work on your pitch deck!\n"
        "Your value prop is clear.\n\n"
        "Progress Score: 72/100"
    )
    sub_id = _seed_submission(mongo, instructor_ctx, feedback, 72)
    r = _export(sub_id, instructor_ctx["inst_token"])
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")

    text = _extract_pdf_text(r.content)

    # Badge / header block present
    assert "Founder Progress Score: 72/100" in text, text
    assert "Silver" in text and "Traction Mode" in text, text

    # The trailing machine-readable line was stripped from the body
    # (only the badge line should show a Score reference)
    body_area = text.split("Coach Max Feedback", 1)[-1]
    assert "Progress Score: 72/100" not in body_area, body_area
    # But the feedback body itself is preserved
    assert "Great work on your pitch deck" in body_area


# -------------------- Readiness Score legacy label --------------------
def test_export_pdf_legacy_readiness_score_label_strips_cleanly(mongo, instructor_ctx):
    feedback = (
        "Solid traction!\n\n"
        "Readiness Score: 78/100"
    )
    sub_id = _seed_submission(mongo, instructor_ctx, feedback, 78)
    r = _export(sub_id, instructor_ctx["inst_token"])
    assert r.status_code == 200, r.text
    text = _extract_pdf_text(r.content)

    assert "Founder Progress Score: 78/100" in text
    assert "Silver" in text  # 78 -> silver tier
    body_area = text.split("Coach Max Feedback", 1)[-1]
    assert "Readiness Score:" not in body_area
    assert "Progress Score:" not in body_area
    assert "Solid traction" in body_area


# -------------------- Gold tier --------------------
def test_export_pdf_gold_tier(mongo, instructor_ctx):
    feedback = "Investor-ready deck.\n\nProgress Score: 90/100"
    sub_id = _seed_submission(mongo, instructor_ctx, feedback, 90)
    r = _export(sub_id, instructor_ctx["inst_token"])
    assert r.status_code == 200
    text = _extract_pdf_text(r.content)
    assert "Founder Progress Score: 90/100" in text
    assert "Gold" in text and "Investor-Ready" in text


# -------------------- No score --------------------
def test_export_pdf_no_readiness_score_omits_badge(mongo, instructor_ctx):
    feedback = "Great work — keep going."
    sub_id = _seed_submission(mongo, instructor_ctx, feedback, None)
    r = _export(sub_id, instructor_ctx["inst_token"])
    assert r.status_code == 200, r.text
    text = _extract_pdf_text(r.content)
    # Header block should NOT be present
    assert "Founder Progress Score:" not in text
    # But the body is still rendered
    assert "Great work" in text


# -------------------- parse_readiness_score still works both labels --------------------
def test_parse_readiness_score_both_labels():
    from server import parse_readiness_score
    assert parse_readiness_score("Nice.\n\nProgress Score: 72/100") == 72
    assert parse_readiness_score("Nice.\n\nReadiness Score: 72/100") == 72


# -------------------- Bronze tier + trailing whitespace/newlines --------------------
def test_export_pdf_bronze_and_trailing_whitespace(mongo, instructor_ctx):
    feedback = "Building momentum.\n\nProgress Score: 55/100\n\n\n"
    sub_id = _seed_submission(mongo, instructor_ctx, feedback, 55)
    r = _export(sub_id, instructor_ctx["inst_token"])
    assert r.status_code == 200
    text = _extract_pdf_text(r.content)
    assert "Founder Progress Score: 55/100" in text
    assert "Bronze" in text and "Building Momentum" in text
    body_area = text.split("Coach Max Feedback", 1)[-1]
    assert "Progress Score:" not in body_area
