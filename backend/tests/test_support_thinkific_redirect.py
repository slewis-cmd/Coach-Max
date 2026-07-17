"""
Iteration 52 — Support Bot Thinkific Redirect for Student Submissions.

Verifies the SUPPORT_SYSTEM_PROMPT update:
  1) STUDENT asks how to submit ANY homework type → response must include "thinkific"
     and must NOT direct them to the in-app "My Assignments" upload flow.
  2) STUDENT platform navigation questions (non-submission) → answered normally
     without being force-redirected to Thinkific.
  3) INSTRUCTOR asks "how to submit on behalf" → response explains the in-app flow
     (Assignments tab / Submit for student). Instructor NOT redirected to Thinkific.
  4) INSTRUCTOR platform questions unaffected.
  5) Coach Max boundary unchanged (business coaching → redirected to Coach Max, not Thinkific).

Budget: 8 real GPT-5.2 calls (short canonical questions).
"""

import os
import re
import sys
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

TAG = "TEST_SUPPORT_THINKIFIC_"


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db_ = client[DB_NAME]

    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    stu_tok = f"{TAG}stok_{uuid.uuid4().hex[:10]}"
    inst_tok = f"{TAG}itok_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    expires = (
        datetime.now(timezone.utc).replace(year=datetime.now().year + 1)
    ).isoformat()

    async def setup():
        await db_.users.insert_many([
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Sam Student",
             "role": "student", "created_at": now},
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Ivy Instructor",
             "role": "instructor", "created_at": now},
        ])
        await db_.user_sessions.insert_many([
            {"session_token": stu_tok, "user_id": stu_id, "email": f"{stu_id}@t.test",
             "expires_at": expires, "created_at": now},
            {"session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
             "expires_at": expires, "created_at": now},
        ])

    _run(setup())

    yield {
        "stu_id": stu_id, "inst_id": inst_id,
        "stu_tok": stu_tok, "inst_tok": inst_tok,
    }

    async def teardown():
        await db_.users.delete_many({"user_id": {"$in": [stu_id, inst_id]}})
        await db_.user_sessions.delete_many({"session_token": {"$in": [stu_tok, inst_tok]}})

    _run(teardown())
    client.close()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _chat(tok, message, history=None):
    """Send a support/chat request and return (status, response text)."""
    r = requests.post(
        f"{BASE_URL}/api/support/chat",
        headers=_hdr(tok),
        json={"message": message, "history": history or []},
        timeout=90,
    )
    return r


def _assert_not_directed_to_in_app_upload(text_lower: str):
    """Response must NOT tell students to upload via My Assignments / in-app flow."""
    # Phrases that would indicate the bot is telling the student to submit in-app.
    bad_patterns = [
        r"upload (it |your |the |).{0,20}(to |in |on |via |through |).{0,20}my assignments",
        r"submit (it |your |).{0,20}(to |in |on |via |through |).{0,20}my assignments",
        r"go to (the |your |).{0,10}my assignments (page |tab |).{0,20}(to |and )(submit|upload)",
        r"use (the |your |).{0,10}my assignments (page |tab )(to |and )(submit|upload)",
        r"submit .{0,40}in.?app upload",
    ]
    for p in bad_patterns:
        m = re.search(p, text_lower)
        assert m is None, (
            f"Response directs student to in-app upload ('{m.group(0) if m else ''}'). "
            f"Should redirect to Thinkific instead."
        )


# ==================== STUDENT: Homework Submission → Thinkific ====================

class TestStudentSubmissionRedirect:
    """Every homework-submission question from a student must redirect to Thinkific."""

    @pytest.mark.parametrize("question,label", [
        ("How do I submit my 60-second pitch?", "60-sec-pitch"),
        ("Where do I upload the 10-slide deck?", "10-slide-deck"),
        ("Can I submit my case study here?", "case-study"),
        ("How do I fill out the business questionnaire?", "questionnaire"),
    ])
    def test_student_submission_redirects_to_thinkific(self, seed, question, label):
        r = _chat(seed["stu_tok"], question)
        assert r.status_code == 200, f"[{label}] {r.status_code} {r.text}"
        body = r.json()
        assert "response" in body, f"[{label}] no response field: {body}"
        text = body["response"]
        text_lower = text.lower()

        # (1) Must mention Thinkific
        assert "thinkific" in text_lower, (
            f"[{label}] Response must mention Thinkific. Got: {text[:500]}"
        )

        # (2) Must NOT tell them to use My Assignments as a submission portal / in-app upload
        _assert_not_directed_to_in_app_upload(text_lower)

        # (3) Response is helpful (non-trivial length; some contextual explanation)
        assert len(text.strip()) > 40, (
            f"[{label}] Response too short/robotic: {text!r}"
        )


# ==================== STUDENT: Non-submission questions unaffected ====================

class TestStudentNonSubmissionUnaffected:
    """Non-submission platform questions from a student should get platform-nav answers,
    NOT be force-redirected to Thinkific."""

    def test_student_coach_max_question(self, seed):
        r = _chat(seed["stu_tok"], "How do I use Coach Max?")
        assert r.status_code == 200, r.text
        text = r.json()["response"].lower()
        # Should discuss Coach Max somehow.
        assert "coach max" in text, f"Missing Coach Max guidance: {text[:400]}"
        # Should not be a submission redirect ("submit your assignment through your Thinkific").
        assert not re.search(
            r"submit .{0,40}through .{0,20}thinkific",
            text,
        ), f"Non-submission question got submission-redirect answer: {text[:400]}"

    def test_student_language_preference_question(self, seed):
        r = _chat(seed["stu_tok"], "Where do I change my language preference?")
        assert r.status_code == 200, r.text
        text = r.json()["response"].lower()
        # Must reference profile / language setting.
        assert any(k in text for k in ["profile", "language", "settings"]), (
            f"Missing profile/language nav: {text[:400]}"
        )
        assert not re.search(
            r"submit .{0,40}through .{0,20}thinkific", text
        ), f"Non-submission question got submission-redirect answer: {text[:400]}"


# ==================== INSTRUCTOR: Submit on Behalf explained ====================

class TestInstructorSubmitOnBehalf:
    """Instructor asks how to submit on behalf → in-app flow must be explained,
    NOT redirected to Thinkific."""

    def test_instructor_submit_on_behalf_explained(self, seed):
        r = _chat(
            seed["inst_tok"],
            "How do I submit an assignment on behalf of a student?",
        )
        assert r.status_code == 200, r.text
        text = r.json()["response"]
        text_lower = text.lower()

        # Must reference the in-app flow.
        assert "submit for student" in text_lower or "submit on behalf" in text_lower, (
            f"Missing 'Submit for student' guidance: {text[:500]}"
        )
        # Should mention Assignments tab and/or milestone context.
        assert "assignment" in text_lower, (
            f"Missing Assignments tab reference: {text[:500]}"
        )
        # Instructor should NOT be told to use Thinkific for this instructor-only flow.
        assert not re.search(
            r"(please |)submit .{0,60}(via |through |on ).{0,20}thinkific",
            text_lower,
        ), f"Instructor incorrectly redirected to Thinkific: {text[:500]}"


# ==================== INSTRUCTOR: Platform navigation unaffected ====================

class TestInstructorPlatformQuestions:
    def test_instructor_create_assignment(self, seed):
        r = _chat(seed["inst_tok"], "How do I create an assignment?")
        assert r.status_code == 200, r.text
        text = r.json()["response"].lower()
        # Should reference Assignments tab / New Assignment flow.
        assert "assignment" in text, f"Missing assignment nav: {text[:400]}"
        assert any(k in text for k in ["new assignment", "create", "milestone", "tab"]), (
            f"Missing creation/nav hints: {text[:400]}"
        )


# ==================== COACH MAX BOUNDARY UNCHANGED ====================

class TestCoachMaxBoundaryUnchanged:
    def test_coaching_question_redirects_to_coach_max_not_thinkific(self, seed):
        r = _chat(
            seed["stu_tok"],
            "How should I improve my pitch's value proposition?",
        )
        assert r.status_code == 200, r.text
        text = r.json()["response"].lower()
        # Must redirect to Coach Max (primary answer).
        assert "coach max" in text, f"Should redirect to Coach Max: {text[:500]}"
        # Bot must NOT provide actual business coaching content
        # (e.g. concrete value-prop tactics like "use the problem-solution framework").
        coaching_content_signals = [
            "problem-solution framework",
            "unique selling proposition",
            "features and benefits",
            "target customer segment",
            "here are some tips to improve",
            "to improve your value proposition, try",
        ]
        for signal in coaching_content_signals:
            assert signal not in text, (
                f"Bot provided actual coaching content ('{signal}'): {text[:500]}"
            )
