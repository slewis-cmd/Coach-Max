"""
Iteration 42 — Refactor regression tests.

Covers the 3 refactored areas:
1. bulk_import_students (server.py:1637) — endpoint decorator was accidentally
   attached to the extracted helper _build_bulk_invite_email_html; fixed in
   this iteration. Verifies the 3 buckets (added / already_enrolled / not_found).
2. _questionnaire_text_from_doc (server.py:185) — read_file_text branch for
   business_questionnaire submissions.
3. _video_transcript_text (server.py:205) — read_file_text branch for video
   materials + inclusion in build_cumulative_context via
   _cumulative_prior_weeks_sections / _cumulative_global_resources_sections.

Uses direct helper invocation (asyncio) for pure-function coverage plus a live
HTTP integration test for the bulk-import endpoint.
"""
import asyncio
import io
import os
import time
import uuid

import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

mongo = MongoClient(MONGO_URL)
db_sync = mongo[DB_NAME]

TEST_PREFIX = "TEST_REF42_"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------
# Module fixture: seed instructor + student + session tokens
# ------------------------------------------------------------------
@pytest.fixture(scope="module")
def seed():
    ts = int(time.time())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    ids = {
        "instructor": f"{TEST_PREFIX}ins_{ts}",
        "student":    f"{TEST_PREFIX}stu_{ts}",
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids}

    db_sync.users.insert_many([
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}ins_{ts}@x.com",
         "name": "Ref42Ins", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["student"], "email": f"{TEST_PREFIX}stu_{ts}@x.com",
         "name": "Ref42Stu", "role": "student", "created_at": now_iso},
    ])
    db_sync.user_sessions.insert_many([
        {"user_id": ids[k], "session_token": toks[k], "expires_at": expires_at, "created_at": now_iso}
        for k in ids
    ])

    yield {"ids": ids, "tokens": toks, "ts": ts}

    # cleanup
    db_sync.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db_sync.users.delete_many({"email": {"$regex": f"^{TEST_PREFIX.lower()}"}})
    db_sync.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db_sync.cohorts.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
    db_sync.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db_sync.assignments.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db_sync.submissions.delete_many({"file_name": {"$regex": f"^{TEST_PREFIX}"}})


# ==================================================================
# 1) BULK IMPORT — regression test for the decorator relocation
# ==================================================================
class TestBulkImport:
    """POST /api/cohorts/{id}/students/bulk — verifies decorator is on the
    correct function (was misplaced on _build_bulk_invite_email_html)."""

    def test_bulk_import_buckets(self, seed):
        # 1) Create cohort
        r = requests.post(
            f"{BASE_URL}/api/cohorts",
            json={"name": f"{TEST_PREFIX}Cbulk_{uuid.uuid4().hex[:6]}"},
            headers=_auth(seed["tokens"]["instructor"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        cid = r.json()["cohort_id"]

        # 2) Pre-create ONE student user and enroll them so we can trigger the
        #    already_enrolled bucket
        enrolled_id = f"{TEST_PREFIX}pre_{uuid.uuid4().hex[:8]}"
        enrolled_email = f"{TEST_PREFIX.lower()}enrolled_{uuid.uuid4().hex[:6]}@x.com"
        db_sync.users.insert_one({
            "user_id": enrolled_id,
            "email": enrolled_email,
            "name": "PreEnrolled",
            "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db_sync.cohorts.update_one(
            {"cohort_id": cid}, {"$push": {"student_ids": enrolled_id}}
        )

        # 3) Prepare CSV: 1 new (added), 1 already-enrolled, 1 not_found (no name)
        new_email = f"{TEST_PREFIX.lower()}new_{uuid.uuid4().hex[:6]}@x.com"
        nf_email = f"{TEST_PREFIX.lower()}nf_{uuid.uuid4().hex[:6]}@x.com"
        csv_text = (
            "email,name\n"
            f"{new_email},NewStudentBulk\n"
            f"{enrolled_email},Ignored\n"
            f"{nf_email},\n"
        )
        files = {"file": ("import.csv", csv_text.encode("utf-8"), "text/csv")}

        # 4) POST bulk import
        r2 = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/students/bulk",
            files=files,
            headers=_auth(seed["tokens"]["instructor"]),
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "results" in body, body
        results = body["results"]

        added_emails = [x.get("email") if isinstance(x, dict) else x for x in results.get("added", [])]
        assert new_email in added_emails, f"expected {new_email} in added, got {results}"
        assert enrolled_email in results.get("already_enrolled", []), results
        assert nf_email in results.get("not_found", []), results

        # 5) Verify DB: new student really was created + enrolled
        cohort = db_sync.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
        new_user = db_sync.users.find_one({"email": new_email}, {"_id": 0})
        assert new_user is not None
        assert new_user["user_id"] in cohort.get("student_ids", [])
        assert new_user["role"] == "student"

    def test_bulk_import_rejects_non_csv(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/cohorts",
            json={"name": f"{TEST_PREFIX}Creject_{uuid.uuid4().hex[:6]}"},
            headers=_auth(seed["tokens"]["instructor"]),
            timeout=15,
        )
        cid = r.json()["cohort_id"]
        files = {"file": ("notcsv.txt", b"just text", "text/plain")}
        r2 = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/students/bulk",
            files=files,
            headers=_auth(seed["tokens"]["instructor"]),
            timeout=15,
        )
        assert r2.status_code == 400, r2.text

    def test_bulk_import_requires_auth(self, seed):
        # Ensure the endpoint still gates on instructor role
        r = requests.post(
            f"{BASE_URL}/api/cohorts/any_cid/students/bulk",
            files={"file": ("a.csv", b"email\nx@y.com\n", "text/csv")},
            timeout=10,
        )
        assert r.status_code == 401, r.text


# ==================================================================
# 2) _questionnaire_text_from_doc — direct helper coverage
# ==================================================================
class TestQuestionnaireTextHelper:
    """Verifies read_file_text branch for questionnaire submissions."""

    def test_questionnaire_text_with_fields(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        mat_id = f"mat_{uuid.uuid4().hex[:10]}"
        db_sync.materials.insert_one({
            "material_id": mat_id,
            "title": f"{TEST_PREFIX}Q",
            "material_type": "homework",
            "questionnaire_fields": [
                {"id": "q1", "label": "What is your business idea?"},
                {"id": "q2", "label": "Who is your customer?"},
            ],
        })
        try:
            sub_doc = {
                "submission_type": "business_questionnaire",
                "material_id": mat_id,
                "questionnaire_answers": {
                    "q1": "AI tutor for entrepreneurs",
                    "q2": "Aspiring founders in college",
                },
            }
            text = asyncio.get_event_loop().run_until_complete(
                server._questionnaire_text_from_doc(sub_doc)
            )
            assert text is not None
            assert "Q: What is your business idea?" in text
            assert "A: AI tutor for entrepreneurs" in text
            assert "Q: Who is your customer?" in text
            assert "A: Aspiring founders in college" in text
        finally:
            db_sync.materials.delete_one({"material_id": mat_id})

    def test_questionnaire_text_missing_answer(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        mat_id = f"mat_{uuid.uuid4().hex[:10]}"
        db_sync.materials.insert_one({
            "material_id": mat_id,
            "title": f"{TEST_PREFIX}Q2",
            "material_type": "homework",
            "questionnaire_fields": [{"id": "q1", "label": "Idea?"}],
        })
        try:
            sub_doc = {
                "submission_type": "business_questionnaire",
                "material_id": mat_id,
                "questionnaire_answers": {},
            }
            text = asyncio.get_event_loop().run_until_complete(
                server._questionnaire_text_from_doc(sub_doc)
            )
            assert text is not None
            assert "(no answer)" in text
        finally:
            db_sync.materials.delete_one({"material_id": mat_id})

    def test_non_questionnaire_returns_none(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        sub_doc = {"submission_type": "file_upload", "file_name": "x.pdf"}
        text = asyncio.get_event_loop().run_until_complete(
            server._questionnaire_text_from_doc(sub_doc)
        )
        assert text is None


# ==================================================================
# 3) _video_transcript_text — direct helper coverage
# ==================================================================
class TestVideoTranscriptHelper:
    def test_video_with_transcript(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        doc = {
            "material_type": "video",
            "video_url": "https://youtube.com/xyz",
            "transcript": "This is the extracted transcript body.",
        }
        text = server._video_transcript_text(doc)
        assert text is not None
        assert "[VIDEO TRANSCRIPT" in text
        assert "https://youtube.com/xyz" in text
        assert "This is the extracted transcript body." in text

    def test_video_without_transcript_returns_empty_string(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        doc = {"material_type": "video", "transcript": "   "}
        text = server._video_transcript_text(doc)
        # Non-None empty string signals "video branch matched but no content"
        assert text == ""

    def test_non_video_returns_none(self):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        doc = {"material_type": "workbook", "transcript": "should be ignored"}
        text = server._video_transcript_text(doc)
        assert text is None


# ==================================================================
# 4) build_cumulative_context — integration across the 3 phase helpers
# ==================================================================
class TestBuildCumulativeContext:
    """Direct invocation of build_cumulative_context to validate phase-helper composition."""

    def test_prior_weeks_includes_video_transcript(self, seed):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        # Create a cohort with a video material (week 1, has transcript)
        cid = f"cohort_{uuid.uuid4().hex[:10]}"
        db_sync.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}Cctx",
            "student_ids": [seed["ids"]["student"]],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Prior-week video with transcript
        vid_id = f"mat_{uuid.uuid4().hex[:10]}"
        db_sync.materials.insert_one({
            "material_id": vid_id,
            "cohort_ids": [cid],
            "week_number": 1,
            "material_type": "video",
            "title": f"{TEST_PREFIX}Vid",
            "video_url": "https://youtube.com/abc123",
            "transcript": "Founders should validate demand before writing code.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Global material with is_global=True
        glob_id = f"mat_{uuid.uuid4().hex[:10]}"
        db_sync.materials.insert_one({
            "material_id": glob_id,
            "cohort_ids": [cid],
            "is_library": True,
            "is_global": True,
            "week_number": 0,
            "material_type": "workbook",
            "title": f"{TEST_PREFIX}Global",
            "file_name": f"{TEST_PREFIX}g.txt",
            "gridfs_id": None,
            "text_content": "COURSE-WIDE glossary content here.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        try:
            ctx = asyncio.get_event_loop().run_until_complete(
                server.build_cumulative_context(
                    student_id=seed["ids"]["student"],
                    cohort_id=cid,
                    current_week=2,
                    max_chars=6000,
                )
            )
            # Video transcript from prior week must appear in context
            assert "VIDEO TRANSCRIPT" in ctx, ctx[:500]
            assert "Founders should validate demand" in ctx, ctx[:500]
            # Week label from _cumulative_prior_weeks_sections
            assert "Week 1" in ctx, ctx[:500]
        finally:
            db_sync.materials.delete_many({"material_id": {"$in": [vid_id, glob_id]}})
            db_sync.cohorts.delete_one({"cohort_id": cid})

    def test_week_1_returns_only_global_or_empty(self, seed):
        import sys
        sys.path.insert(0, "/app/backend")
        import server

        cid = f"cohort_{uuid.uuid4().hex[:10]}"
        db_sync.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}Cw1",
            "student_ids": [seed["ids"]["student"]],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            ctx = asyncio.get_event_loop().run_until_complete(
                server.build_cumulative_context(
                    student_id=seed["ids"]["student"],
                    cohort_id=cid,
                    current_week=1,
                    max_chars=6000,
                )
            )
            # Week 1: no prior-week material, no global -> empty string
            assert ctx == ""
        finally:
            db_sync.cohorts.delete_one({"cohort_id": cid})
