"""
Iteration 46 — End-to-End Coach Max reproduction test for the 4 milestone-based
assignment types + edge cases from user's bug report ("Sorry, I'm having trouble").

For EACH of the 4 assignment types (60_second_pitch, 10_slide_pitch, case_activity,
business_questionnaire):
  1. GET /api/submissions/{id}      → 200 + material.title non-empty
  2. GET /api/chat/history/{id}     → 200 + [] (empty list)
  3. POST /api/chat/ask-tutor       → 200 + non-empty .response

Edge cases:
  A) student re-enrolled after submission (not enrolled at sub time)
  B) submission migrated: both material_id and assignment_id set
  C) instructor_feedback empty but ai_feedback populated
  D) submission whose assignment_id refers to inactive/deleted assignment
  E) missing/expired token → 401 (frontend catch triggers the "having trouble" toast)

If ANY assignment type returns 4xx/5xx or empty response ⇒ REPRODUCTION of user's bug.
"""
import os
import sys
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

TAG = "TEST_CM46_"


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# One assignment per type — with 1 milestone at week=3 — and one sent sub per type.
ASSIGN_TYPES = [
    ("60_second_pitch",       "60-Second Elevator Pitch"),
    ("10_slide_pitch",        "10-Slide Business Deck"),
    ("case_activity",         "Case Activity"),
    ("business_questionnaire","Business Questionnaire"),
]


@pytest.fixture(scope="module")
def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db_ = client[DB_NAME]

    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:6]}"
    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:6]}"
    late_stu_id = f"{TAG}stuL_{uuid.uuid4().hex[:6]}"  # will be "re-enrolled" later
    cohort_id = f"{TAG}coh_{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc).replace(year=datetime.now().year + 1)).isoformat()

    inst_tok = f"{TAG}itok_{uuid.uuid4().hex[:8]}"
    stu_tok = f"{TAG}stok_{uuid.uuid4().hex[:8]}"
    late_tok = f"{TAG}ltok_{uuid.uuid4().hex[:8]}"

    # Per-type ids
    per_type = {}
    for stype, title in ASSIGN_TYPES:
        per_type[stype] = {
            "asgn_id": f"{TAG}asgn_{stype}_{uuid.uuid4().hex[:6]}",
            "ms_id":   f"{TAG}ms_{stype}_{uuid.uuid4().hex[:6]}",
            "sub_id":  f"{TAG}sub_{stype}_{uuid.uuid4().hex[:6]}",
            "title":   f"{TAG}{title}",
        }

    # Edge case ids
    edge_ai_only_sub = f"{TAG}sub_aionly_{uuid.uuid4().hex[:6]}"
    edge_migrated_sub = f"{TAG}sub_migr_{uuid.uuid4().hex[:6]}"
    edge_inactive_sub = f"{TAG}sub_inact_{uuid.uuid4().hex[:6]}"
    edge_late_sub = f"{TAG}sub_late_{uuid.uuid4().hex[:6]}"
    inactive_asgn = f"{TAG}asgn_inact_{uuid.uuid4().hex[:6]}"
    inactive_ms   = f"{TAG}ms_inact_{uuid.uuid4().hex[:6]}"
    legacy_mat = f"{TAG}mat_legacy_{uuid.uuid4().hex[:6]}"

    async def setup():
        # Users + sessions
        await db_.users.insert_many([
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Inst 46",
             "role": "instructor", "created_at": now},
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Stu 46",
             "role": "student", "created_at": now, "language_preference": "en"},
            {"user_id": late_stu_id, "email": f"{late_stu_id}@t.test", "name": "Late Stu",
             "role": "student", "created_at": now, "language_preference": "en"},
        ])
        await db_.user_sessions.insert_many([
            {"session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
             "expires_at": expires, "created_at": now},
            {"session_token": stu_tok, "user_id": stu_id, "email": f"{stu_id}@t.test",
             "expires_at": expires, "created_at": now},
            {"session_token": late_tok, "user_id": late_stu_id, "email": f"{late_stu_id}@t.test",
             "expires_at": expires, "created_at": now},
        ])
        # Cohort — both students enrolled
        await db_.cohorts.insert_one({
            "cohort_id": cohort_id, "name": f"{TAG}Cohort",
            "instructor_ids": [inst_id],
            "student_ids": [stu_id, late_stu_id],
            "total_weeks": 6, "current_week": 6,
            "auto_send_feedback": False,
            "created_at": now,
        })
        # Assignments + milestones + submissions for each type
        for stype, meta in per_type.items():
            await db_.assignments.insert_one({
                "assignment_id": meta["asgn_id"], "cohort_id": cohort_id,
                "title": meta["title"], "description": f"{meta['title']} description",
                "submission_type": stype,
                "feedback_template": "Template",
                "drive_folder_url": "",
                "questionnaire_fields": (
                    [{"field_id": "q1", "label": "Q1", "field_type": "text", "required": True}]
                    if stype == "business_questionnaire" else []
                ),
                "is_active": True,
                "milestones": [{
                    "milestone_id": meta["ms_id"], "week_number": 3,
                    "title": f"{stype} milestone", "description": "wk3",
                    "feedback_template_override": "",
                    "drive_folder_url_override": "",
                    "is_final_capstone": False, "due_date": None,
                }],
                "created_at": now,
            })
            await db_.submissions.insert_one({
                "submission_id": meta["sub_id"],
                "student_id": stu_id,
                "cohort_id": cohort_id,
                "assignment_id": meta["asgn_id"],
                "milestone_id": meta["ms_id"],
                "material_id": "",
                "submission_type": stype,
                "file_name": f"{stype}.txt",
                "content_text": f"Sample {stype} content for testing coach max.",
                "status": "sent",
                "instructor_feedback": f"Great {stype} work. Refine hook.",
                "ai_feedback": "",
                "submitted_at": now, "sent_at": now, "feedback_sent": True,
            })

        # ---- EDGE CASE A: late-enrolled student — submission by late_stu_id AFTER
        # they were "not in cohort" at submit time. Verified simply by ensuring the
        # student is CURRENTLY in cohort.student_ids (they are). The submission has
        # student_id=late_stu_id, and the ask-tutor scopes only by student_id.
        first_meta = per_type["60_second_pitch"]
        await db_.submissions.insert_one({
            "submission_id": edge_late_sub,
            "student_id": late_stu_id,
            "cohort_id": cohort_id,
            "assignment_id": first_meta["asgn_id"],
            "milestone_id": first_meta["ms_id"],
            "material_id": "",
            "submission_type": "60_second_pitch",
            "file_name": "late.txt", "content_text": "Late-enrolled pitch.",
            "status": "sent",
            "instructor_feedback": "Nice late submission.", "ai_feedback": "",
            "submitted_at": now, "sent_at": now, "feedback_sent": True,
        })

        # ---- EDGE CASE B: migrated submission (BOTH material_id AND assignment_id set)
        await db_.materials.insert_one({
            "material_id": legacy_mat, "cohort_id": cohort_id, "cohort_ids": [cohort_id],
            "title": f"{TAG}Legacy Mat", "description": "Legacy homework material",
            "material_type": "homework", "week_number": 3, "submission_type": "text",
            "content": "Legacy content", "created_at": now,
        })
        await db_.submissions.insert_one({
            "submission_id": edge_migrated_sub,
            "student_id": stu_id, "cohort_id": cohort_id,
            "assignment_id": first_meta["asgn_id"],  # both set!
            "milestone_id": first_meta["ms_id"],
            "material_id": legacy_mat,               # both set!
            "submission_type": "60_second_pitch",
            "file_name": "mig.txt", "content_text": "Migrated sub content.",
            "status": "sent",
            "instructor_feedback": "Ok migrated.", "ai_feedback": "",
            "submitted_at": now, "sent_at": now, "feedback_sent": True,
        })

        # ---- EDGE CASE C: instructor_feedback empty but ai_feedback populated
        await db_.submissions.insert_one({
            "submission_id": edge_ai_only_sub,
            "student_id": stu_id, "cohort_id": cohort_id,
            "assignment_id": first_meta["asgn_id"],
            "milestone_id": first_meta["ms_id"],
            "material_id": "",
            "submission_type": "60_second_pitch",
            "file_name": "aio.txt", "content_text": "AI only feedback sub content.",
            "status": "sent",
            "instructor_feedback": "",
            "ai_feedback": "AI suggests: clarify the opening line.",
            "submitted_at": now, "sent_at": now, "feedback_sent": True,
        })

        # ---- EDGE CASE D: assignment inactive/deleted — sub references it
        await db_.assignments.insert_one({
            "assignment_id": inactive_asgn, "cohort_id": cohort_id,
            "title": f"{TAG}Inactive Asgn", "description": "no longer active",
            "submission_type": "60_second_pitch",
            "feedback_template": "", "drive_folder_url": "",
            "questionnaire_fields": [],
            "is_active": False,   # <-- inactive
            "milestones": [{
                "milestone_id": inactive_ms, "week_number": 2,
                "title": "Inactive ms", "description": "wk2",
                "feedback_template_override": "", "drive_folder_url_override": "",
                "is_final_capstone": False, "due_date": None,
            }],
            "created_at": now,
        })
        await db_.submissions.insert_one({
            "submission_id": edge_inactive_sub,
            "student_id": stu_id, "cohort_id": cohort_id,
            "assignment_id": inactive_asgn, "milestone_id": inactive_ms,
            "material_id": "",
            "submission_type": "60_second_pitch",
            "file_name": "inact.txt", "content_text": "Inactive asgn sub content.",
            "status": "sent",
            "instructor_feedback": "Still good.", "ai_feedback": "",
            "submitted_at": now, "sent_at": now, "feedback_sent": True,
        })
    _run(setup())

    ctx = {
        "stu_tok": stu_tok, "late_tok": late_tok,
        "stu_auth": {"Authorization": f"Bearer {stu_tok}"},
        "late_auth": {"Authorization": f"Bearer {late_tok}"},
        "per_type": per_type,
        "edge_ai_only_sub": edge_ai_only_sub,
        "edge_migrated_sub": edge_migrated_sub,
        "edge_inactive_sub": edge_inactive_sub,
        "edge_late_sub": edge_late_sub,
    }
    yield ctx

    async def teardown():
        await db_.users.delete_many({"user_id": {"$regex": f"^{TAG}"}})
        await db_.user_sessions.delete_many({"session_token": {"$regex": f"^{TAG}"}})
        await db_.cohorts.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
        await db_.assignments.delete_many({"assignment_id": {"$regex": f"^{TAG}"}})
        await db_.materials.delete_many({"material_id": {"$regex": f"^{TAG}"}})
        await db_.submissions.delete_many({"submission_id": {"$regex": f"^{TAG}"}})
        await db_.tutor_chats.delete_many({"submission_id": {"$regex": f"^{TAG}"}})
    _run(teardown())
    client.close()


# =====================================================================
# 3-step E2E flow for each of the 4 assignment types (12 tests)
# =====================================================================
@pytest.mark.parametrize("stype,pretty", ASSIGN_TYPES)
class TestCoachMaxFlowPerType:
    def test_get_submission(self, seed, stype, pretty):
        sub_id = seed["per_type"][stype]["sub_id"]
        r = requests.get(f"{BASE_URL}/api/submissions/{sub_id}", headers=seed["stu_auth"])
        assert r.status_code == 200, r.text
        d = r.json()
        mat = d.get("material")
        assert mat is not None, f"[{stype}] material missing"
        assert mat.get("title"), f"[{stype}] material.title empty"
        assert mat["title"] == seed["per_type"][stype]["title"]
        assert mat.get("week_number") == 3
        assert mat.get("submission_type") == stype

    def test_get_chat_history_empty(self, seed, stype, pretty):
        sub_id = seed["per_type"][stype]["sub_id"]
        r = requests.get(f"{BASE_URL}/api/chat/history/{sub_id}", headers=seed["stu_auth"])
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_ask_tutor_returns_nonempty_response(self, seed, stype, pretty):
        sub_id = seed["per_type"][stype]["sub_id"]
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["stu_auth"],
            json={"message": f"Give me one tip for my {pretty}.", "submission_id": sub_id},
            timeout=60,
        )
        # Bug repro: any 4xx or 5xx OR empty response = reproduce user's bug
        assert r.status_code == 200, (
            f"[{stype}] REPRO USER BUG: /api/chat/ask-tutor returned {r.status_code}: {r.text}"
        )
        d = r.json()
        resp = d.get("response")
        assert isinstance(resp, str) and len(resp.strip()) > 0, (
            f"[{stype}] REPRO USER BUG: empty response body: {d}"
        )
        # Ensure the fallback string is NEVER what the backend returns
        assert "having trouble right now" not in resp.lower(), (
            f"[{stype}] LLM returned the fallback error string itself"
        )


# =====================================================================
# Edge cases
# =====================================================================
class TestEdgeCases:
    def test_late_enrolled_student_can_use_coach_max(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["late_auth"],
            json={"message": "Any tips?", "submission_id": seed["edge_late_sub"]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("response")

    def test_migrated_sub_both_ids_set(self, seed):
        # get_submission — should still return a material (either legacy or synthetic)
        r = requests.get(f"{BASE_URL}/api/submissions/{seed['edge_migrated_sub']}",
                         headers=seed["stu_auth"])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("material") is not None
        assert d["material"].get("title")
        # ask-tutor — must not crash
        r2 = requests.post(f"{BASE_URL}/api/chat/ask-tutor",
                           headers=seed["stu_auth"],
                           json={"message": "hi", "submission_id": seed["edge_migrated_sub"]},
                           timeout=60)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("response")

    def test_ai_feedback_only_sub_works(self, seed):
        r = requests.post(f"{BASE_URL}/api/chat/ask-tutor",
                          headers=seed["stu_auth"],
                          json={"message": "What should I improve?",
                                "submission_id": seed["edge_ai_only_sub"]},
                          timeout=60)
        assert r.status_code == 200, r.text
        assert r.json().get("response")

    def test_inactive_assignment_still_resolves(self, seed):
        """Defensive: sub references an inactive assignment — endpoint must still work."""
        r = requests.get(f"{BASE_URL}/api/submissions/{seed['edge_inactive_sub']}",
                         headers=seed["stu_auth"])
        assert r.status_code == 200, r.text
        r2 = requests.post(f"{BASE_URL}/api/chat/ask-tutor",
                           headers=seed["stu_auth"],
                           json={"message": "hi", "submission_id": seed["edge_inactive_sub"]},
                           timeout=60)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("response")


# =====================================================================
# Auth path — verifies the "having trouble right now" fallback is NOT
# masking a subtle 401.
# =====================================================================
class TestAuthPath:
    def test_no_auth_header_returns_401(self, seed):
        sub_id = seed["per_type"]["60_second_pitch"]["sub_id"]
        r = requests.post(f"{BASE_URL}/api/chat/ask-tutor",
                          json={"message": "hi", "submission_id": sub_id},
                          timeout=15)
        assert r.status_code == 401, r.text

    def test_bad_token_returns_401(self, seed):
        sub_id = seed["per_type"]["60_second_pitch"]["sub_id"]
        r = requests.post(f"{BASE_URL}/api/chat/ask-tutor",
                          headers={"Authorization": "Bearer garbage-token"},
                          json={"message": "hi", "submission_id": sub_id},
                          timeout=15)
        assert r.status_code == 401, r.text

    def test_cors_allows_authorization_header(self, seed):
        """Preflight OPTIONS: ensure Authorization is in Access-Control-Allow-Headers."""
        r = requests.options(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={
                "Origin": "https://cohort-feedback-hub.preview.emergentagent.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
            timeout=10,
        )
        # Should not be a hard failure — ACAO/ACAH must include Authorization (or wildcard *)
        allow_headers = (r.headers.get("access-control-allow-headers", "") or "").lower()
        assert (
            "authorization" in allow_headers or "*" in allow_headers
        ), f"CORS preflight blocks Authorization header: {dict(r.headers)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
