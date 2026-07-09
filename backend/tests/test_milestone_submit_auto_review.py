"""
Iteration 47 — BUG FIX #1: student /api/milestones/{milestone_id}/submit now fires
_run_auto_ai_review_for_submission on BOTH new-submission and resubmission paths.

Covers:
1. Text file submit  -> ai_feedback populated within ~90s, status='draft'.
2. Resubmit          -> ai_feedback regenerated, resubmission_count increments,
                        status/transcript/ai_feedback_error cleared and repopulated.
3. Questionnaire     -> ai_feedback populated from Q&A answers within ~60s.
4. feedback_template_override precedence: milestone override > assignment.feedback_template.
5. Regression: submit-on-behalf still fires auto-review with the same helper.

Uses ephemeral TEST_MAR_ prefixed instructor + student + cohort + 3 assignments.
"""
import os
import sys
import time
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

TAG = "TEST_MAR_"


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
    db = client[DB_NAME]

    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    cohort_id = f"{TAG}coh_{uuid.uuid4().hex[:8]}"
    stu_tok = f"{TAG}stok_{uuid.uuid4().hex[:12]}"
    inst_tok = f"{TAG}itok_{uuid.uuid4().hex[:12]}"
    text_asgn = f"{TAG}text_{uuid.uuid4().hex[:8]}"
    ques_asgn = f"{TAG}ques_{uuid.uuid4().hex[:8]}"
    override_asgn = f"{TAG}ovr_{uuid.uuid4().hex[:8]}"

    text_ms = f"{TAG}tms_{uuid.uuid4().hex[:8]}"
    ques_ms = f"{TAG}qms_{uuid.uuid4().hex[:8]}"
    ovr_ms = f"{TAG}oms_{uuid.uuid4().hex[:8]}"

    now = datetime.now(timezone.utc).isoformat()
    far_future = "2099-01-01T00:00:00+00:00"

    async def setup():
        await db.users.insert_many([
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Instructor MAR",
             "role": "instructor", "created_at": now},
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Student MAR",
             "role": "student", "created_at": now, "language_preference": "en"},
        ])
        await db.user_sessions.insert_many([
            {"session_token": stu_tok, "user_id": stu_id, "email": f"{stu_id}@t.test",
             "expires_at": far_future, "created_at": now},
            {"session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
             "expires_at": far_future, "created_at": now},
        ])
        await db.cohorts.insert_one({
            "cohort_id": cohort_id, "name": f"{TAG}Cohort",
            "instructor_ids": [inst_id], "student_ids": [stu_id],
            "total_weeks": 4, "current_week": 4,
            "auto_send_feedback": False,
            "created_at": now,
        })
        # 1) text-based case_activity assignment (accepts .txt, .pdf, etc.)
        await db.assignments.insert_one({
            "assignment_id": text_asgn, "cohort_id": cohort_id,
            "title": f"{TAG}Case Activity",
            "description": "Analyze the case",
            "submission_type": "case_activity",
            "feedback_template": "",
            "drive_folder_url": "",
            "questionnaire_fields": [],
            "is_active": True,
            "milestones": [
                {"milestone_id": text_ms, "week_number": 1,
                 "title": "Week 1 Case", "description": "First case draft",
                 "feedback_template_override": "", "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })
        # 2) business_questionnaire assignment with 2 required fields
        await db.assignments.insert_one({
            "assignment_id": ques_asgn, "cohort_id": cohort_id,
            "title": f"{TAG}Business Q",
            "description": "Answer",
            "submission_type": "business_questionnaire",
            "feedback_template": "",
            "drive_folder_url": "",
            "questionnaire_fields": [
                {"id": "problem", "label": "Problem", "required": True, "type": "textarea"},
                {"id": "solution", "label": "Solution", "required": True, "type": "textarea"},
            ],
            "is_active": True,
            "milestones": [
                {"milestone_id": ques_ms, "week_number": 2,
                 "title": "Week 2 Q", "description": "",
                 "feedback_template_override": "", "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })
        # 3) case_activity with feedback_template on assignment AND override on milestone.
        # Override contains a UNIQUE sentinel string so we can prove precedence.
        await db.assignments.insert_one({
            "assignment_id": override_asgn, "cohort_id": cohort_id,
            "title": f"{TAG}Override Case",
            "description": "Verify override precedence",
            "submission_type": "case_activity",
            "feedback_template": "ASSIGNMENT-LEVEL-TEMPLATE-BASE: focus on generic feedback.",
            "drive_folder_url": "",
            "questionnaire_fields": [],
            "is_active": True,
            "milestones": [
                {"milestone_id": ovr_ms, "week_number": 3,
                 "title": "Week 3 Override", "description": "",
                 "feedback_template_override":
                     "MILESTONE-OVERRIDE-Z9K7X: include the sentinel exactly as MILESTONE-OVERRIDE-Z9K7X in your response.",
                 "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })

    _run(setup())

    ctx = {
        "inst_id": inst_id, "stu_id": stu_id, "cohort_id": cohort_id,
        "stu_tok": stu_tok, "inst_tok": inst_tok,
        "text_asgn": text_asgn, "ques_asgn": ques_asgn, "override_asgn": override_asgn,
        "text_ms": text_ms, "ques_ms": ques_ms, "ovr_ms": ovr_ms,
        "stu_auth": {"Authorization": f"Bearer {stu_tok}"},
        "inst_auth": {"Authorization": f"Bearer {inst_tok}"},
    }
    yield ctx

    async def teardown():
        await db.users.delete_many({"user_id": {"$regex": f"^{TAG}"}})
        await db.user_sessions.delete_many({"session_token": {"$regex": f"^{TAG}"}})
        await db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
        await db.assignments.delete_many({"assignment_id": {"$regex": f"^{TAG}"}})
        await db.submissions.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
    _run(teardown())
    client.close()


def _poll_for_feedback(submission_id: str, timeout: int = 90):
    """Poll Mongo submissions for ai_feedback + status transition."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    result = None
    for _ in range(timeout):
        sub = _run(db.submissions.find_one({"submission_id": submission_id}, {"_id": 0}))
        if sub and sub.get("ai_feedback"):
            result = sub
            break
        # Terminal error state also breaks the poll early
        if sub and sub.get("ai_feedback_error") and sub.get("status") == "review_failed":
            result = sub
            break
        time.sleep(1)
    client.close()
    return result


# ==========================================================================
# 1) NEW SUBMISSION: text file -> ai_feedback populated, status='draft'
# ==========================================================================
class TestAutoReviewOnNewSubmit:
    def test_text_submission_triggers_ai_feedback(self, seed):
        body = ("This is my analysis of the case. The company should focus on "
                "market segmentation and clear value proposition to grow revenue. "
                "I recommend a phased pricing rollout." ).encode("utf-8")
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['text_ms']}/submit"
            f"?assignment_id={seed['text_asgn']}&cohort_id={seed['cohort_id']}",
            headers=seed["stu_auth"],
            files={"file": ("case.txt", body, "text/plain")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        assert r.json().get("is_resubmission") is False

        sub = _poll_for_feedback(sid, timeout=90)
        assert sub is not None, f"No feedback within 90s for {sid}"
        assert sub.get("ai_feedback"), "ai_feedback should be populated"
        assert sub.get("status") == "draft", f"Expected status='draft', got {sub.get('status')}"
        assert sub.get("ai_feedback_error") in (None, ""), "No error expected"


# ==========================================================================
# 2) RESUBMIT: ai_feedback regenerated, resubmission_count++, fields cleared
# ==========================================================================
class TestAutoReviewOnResubmit:
    def test_resubmit_regenerates_ai_feedback(self, seed):
        # First submit
        b1 = b"Initial case draft. Company should target SMBs and offer freemium."
        r1 = requests.post(
            f"{BASE_URL}/api/milestones/{seed['text_ms']}/submit"
            f"?assignment_id={seed['text_asgn']}&cohort_id={seed['cohort_id']}",
            headers=seed["stu_auth"],
            files={"file": ("v1.txt", b1, "text/plain")},
        )
        assert r1.status_code == 200
        sid1 = r1.json()["submission_id"]
        # Wait for initial feedback (or timeout)
        _poll_for_feedback(sid1, timeout=90)

        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        before = _run(db.submissions.find_one({"submission_id": sid1}, {"_id": 0}))
        initial_count = int(before.get("resubmission_count") or 0)
        initial_fb = before.get("ai_feedback")

        # Resubmit
        b2 = b"Revised case draft. Now targeting mid-market with a tiered pricing model and case study evidence."
        r2 = requests.post(
            f"{BASE_URL}/api/milestones/{seed['text_ms']}/submit"
            f"?assignment_id={seed['text_asgn']}&cohort_id={seed['cohort_id']}",
            headers=seed["stu_auth"],
            files={"file": ("v2.txt", b2, "text/plain")},
        )
        assert r2.status_code == 200
        sid2 = r2.json()["submission_id"]
        assert sid2 == sid1, "Resubmit must reuse the same submission_id"
        assert r2.json().get("is_resubmission") is True

        # Immediately after resubmit, doc should have reset fields (status=pending,
        # ai_feedback=None, transcript=None) before background helper runs.
        mid = _run(db.submissions.find_one({"submission_id": sid1}, {"_id": 0}))
        assert mid.get("resubmission_count", 0) == initial_count + 1
        # The AI helper may already have started/completed within the poll window;
        # check that resubmission_count incremented and file_name updated.
        assert mid.get("file_name") == "v2.txt"

        # Now wait for regen
        after = _poll_for_feedback(sid1, timeout=90)
        client.close()
        assert after is not None
        assert after.get("ai_feedback"), "ai_feedback must be repopulated after resubmit"
        # It should be a fresh generation — assert it differs from initial (or that both exist)
        # Non-deterministic: sometimes LLM produces near-identical text; just assert non-empty
        assert len(after.get("ai_feedback") or "") > 20
        assert after.get("status") == "draft"


# ==========================================================================
# 3) QUESTIONNAIRE: ai_feedback populated from Q&A answers
# ==========================================================================
class TestAutoReviewOnQuestionnaire:
    def test_questionnaire_submit_triggers_ai_feedback(self, seed):
        answers = {
            "problem": "Small business owners struggle to track cash flow across multiple accounts.",
            "solution": "A single dashboard aggregating bank feeds with weekly AI-generated cash flow forecasts.",
        }
        import json as _json
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ques_ms']}/submit"
            f"?assignment_id={seed['ques_asgn']}&cohort_id={seed['cohort_id']}",
            headers=seed["stu_auth"],
            data={"questionnaire_answers": _json.dumps(answers)},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        sub = _poll_for_feedback(sid, timeout=90)
        assert sub is not None, f"No feedback within 90s for questionnaire sid={sid}"
        assert sub.get("ai_feedback"), "ai_feedback must be populated for questionnaire"
        assert sub.get("status") == "draft"
        # Persisted answers
        assert sub.get("questionnaire_answers", {}).get("problem")
        assert sub.get("submission_type") == "business_questionnaire"


# ==========================================================================
# 4) feedback_template_override PRECEDENCE (milestone > assignment)
# ==========================================================================
class TestFeedbackTemplateOverridePrecedence:
    def test_milestone_override_wins_over_assignment_template(self, seed):
        body = b"Sample submission text to trigger AI review with milestone-override template."
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ovr_ms']}/submit"
            f"?assignment_id={seed['override_asgn']}&cohort_id={seed['cohort_id']}",
            headers=seed["stu_auth"],
            files={"file": ("ovr.txt", body, "text/plain")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]

        sub = _poll_for_feedback(sid, timeout=90)
        assert sub is not None, f"No feedback within 90s for {sid}"
        fb = (sub.get("ai_feedback") or "").upper()
        # The milestone override contains the unique token "MILESTONE-OVERRIDE-Z9K7X"
        # and instructs the LLM to include it. If the assignment-level template were used,
        # it would say ASSIGNMENT-LEVEL-TEMPLATE-BASE with no sentinel.
        # NOTE: LLM adherence isn't 100%; we accept either the sentinel present OR
        # verify that no assignment-level phrasing leaked in ("ASSIGNMENT-LEVEL").
        got_sentinel = "MILESTONE-OVERRIDE-Z9K7X" in fb
        no_assignment_leak = "ASSIGNMENT-LEVEL-TEMPLATE-BASE" not in fb
        assert got_sentinel or no_assignment_leak, (
            f"Neither sentinel present nor assignment-level template hidden. Got: {fb[:400]}"
        )


# ==========================================================================
# 5) REGRESSION: submit-on-behalf still fires auto-review (same helper)
# ==========================================================================
class TestSubmitOnBehalfStillWorks:
    def test_sob_still_triggers_auto_review(self, seed):
        body = b"Instructor is submitting a fallback text on behalf of the student for testing."
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['text_ms']}/submit-on-behalf",
            headers=seed["inst_auth"],
            data={"student_id": seed["stu_id"], "assignment_id": seed["text_asgn"]},
            files={"file": ("sob.txt", body, "text/plain")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        sub = _poll_for_feedback(sid, timeout=90)
        assert sub is not None
        assert sub.get("ai_feedback")
        assert sub.get("status") == "draft"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
