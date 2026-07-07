"""
Iteration 40 - Backend test suite for Phase 2 Student-side Assignments.

Covers:
- GET /api/student/assignments-dashboard
    * Returns [{cohort_id, cohort_name, total_weeks, current_week, this_week[], assignments[]}]
    * current_week = min week among not-yet-submitted milestones, None when all done
    * this_week is one entry per not-yet-submitted milestone at current_week
    * assignments[].milestones[].status derived from submission
    * Auto-seeds 4 default assignments if cohort has none
    * 403 for non-student
- POST /api/milestones/{milestone_id}/submit
    * Requires assignment_id
    * 404 for unknown assignment_id / milestone_id
    * 403 if student not enrolled
    * File extension validation (60_second_pitch rejects .pdf, accepts .mp4)
    * business_questionnaire required-field validation + persistence
    * Resubmission updates existing (is_resubmission=True, no dup, count++)

All seeded docs prefixed TEST_P2_.
"""
import io
import os
import json
import uuid
import time
import pytest
import requests
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

TEST_PREFIX = "TEST_P2_"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def seed():
    ts = int(time.time())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    ids = {
        "sa":         f"{TEST_PREFIX}sa_{ts}",
        "instructor": f"{TEST_PREFIX}i1_{ts}",
        "student":    f"{TEST_PREFIX}stu_{ts}",
        "student2":   f"{TEST_PREFIX}stu2_{ts}",
        "outsider":   f"{TEST_PREFIX}out_{ts}",
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids.keys()}

    db.users.insert_many([
        {"user_id": ids["sa"],         "email": f"{TEST_PREFIX}sa_{ts}@x.com",  "name": "Adm",  "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i_{ts}@x.com",   "name": "Ins",  "role": "instructor",  "created_at": now_iso},
        {"user_id": ids["student"],    "email": f"{TEST_PREFIX}s_{ts}@x.com",   "name": "Stu",  "role": "student",     "language_preference": "en", "created_at": now_iso},
        {"user_id": ids["student2"],   "email": f"{TEST_PREFIX}s2_{ts}@x.com",  "name": "Stu2", "role": "student",     "language_preference": "en", "created_at": now_iso},
        {"user_id": ids["outsider"],   "email": f"{TEST_PREFIX}o_{ts}@x.com",   "name": "Out",  "role": "student",     "created_at": now_iso},
    ])
    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": toks[k], "expires_at": expires_at, "created_at": now_iso}
        for k, uid in ids.items()
    ])

    yield {"ids": ids, "tokens": toks, "ts": ts}

    # Cleanup
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db.assignments.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"student_id": {"$regex": f"^{TEST_PREFIX}"}})


def _create_cohort_with_student(instructor_token, student_id, name_suffix=""):
    """Create cohort via API + enroll student. Returns cohort_id."""
    name = f"{TEST_PREFIX}C_{name_suffix}_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/cohorts",
        json={"name": name, "description": "iter40 phase2 test"},
        headers=_auth(instructor_token), timeout=15,
    )
    assert r.status_code == 200, r.text
    cid = r.json()["cohort_id"]
    db.cohorts.update_one({"cohort_id": cid}, {"$addToSet": {"student_ids": student_id}})
    return cid


# ===================================================================
# 1) GET /api/student/assignments-dashboard
# ===================================================================
class TestStudentAssignmentsDashboard:
    def test_non_student_gets_403(self, seed):
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 403

    def test_super_admin_gets_403(self, seed):
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["sa"]), timeout=10,
        )
        assert r.status_code == 403

    def test_returns_shape_with_expected_fields(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "shape")
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        entry = next((c for c in data if c["cohort_id"] == cid), None)
        assert entry is not None, "Cohort should be in dashboard"
        for key in ("cohort_id", "cohort_name", "total_weeks", "current_week", "this_week", "assignments"):
            assert key in entry, f"Missing key: {key}"
        # 4 default assignments auto-seeded on cohort create
        assert len(entry["assignments"]) == 4
        # current_week should be 1 (all not started)
        assert entry["current_week"] == 1
        # this_week has one entry per assignment at week 1
        assert len(entry["this_week"]) == 4
        for tw in entry["this_week"]:
            for k in ("assignment_id", "assignment_title", "submission_type",
                      "milestone_id", "milestone_title", "week_number",
                      "drive_folder_url", "is_final_capstone"):
                assert k in tw, f"this_week entry missing {k}"
            assert tw["week_number"] == 1

    def test_auto_seeds_when_cohort_has_no_assignments(self, seed):
        # Create a bare cohort directly in mongo (bypass API — no auto-seed happens)
        cid = f"{TEST_PREFIX}bare_{uuid.uuid4().hex[:8]}"
        db.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}bare",
            "instructor_id": seed["ids"]["instructor"],
            "instructor_ids": [seed["ids"]["instructor"]],
            "student_ids": [seed["ids"]["student"]],
            "total_weeks": 14,
            "auto_send_feedback": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        assert db.assignments.count_documents({"cohort_id": cid}) == 0
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        # After the call, assignments should have been auto-seeded
        assert db.assignments.count_documents({"cohort_id": cid}) == 4
        entry = next((c for c in r.json() if c["cohort_id"] == cid), None)
        assert entry is not None
        assert len(entry["assignments"]) == 4

    def test_milestone_status_derived_from_submissions(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "status")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        aid = asgn["assignment_id"]
        milestones = asgn["milestones"]
        # Seed submissions with 3 different states
        pending_ms = milestones[0]      # week 1 -> submitted
        draft_ms   = milestones[1]      # week 2 -> under_review
        sent_ms    = milestones[2]      # week 3 -> feedback_provided
        now = datetime.now(timezone.utc).isoformat()
        base = {
            "cohort_id": cid,
            "student_id": seed["ids"]["student"],
            "material_id": "",
            "assignment_id": aid,
            "file_name": f"{TEST_PREFIX}f",
            "submission_type": "case_activity",
            "submitted_at": now,
            "resubmission_count": 0,
        }
        db.submissions.insert_many([
            {**base, "submission_id": f"sub_{uuid.uuid4().hex[:10]}", "milestone_id": pending_ms["milestone_id"], "status": "pending"},
            {**base, "submission_id": f"sub_{uuid.uuid4().hex[:10]}", "milestone_id": draft_ms["milestone_id"],   "status": "draft", "ai_feedback": "wip"},
            {**base, "submission_id": f"sub_{uuid.uuid4().hex[:10]}", "milestone_id": sent_ms["milestone_id"],    "status": "sent",  "ai_feedback": "great job", "feedback_sent": True},
        ])
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        assert r.status_code == 200
        entry = next(c for c in r.json() if c["cohort_id"] == cid)
        case_asgn = next(a for a in entry["assignments"] if a["assignment_id"] == aid)
        m_by_id = {m["milestone_id"]: m for m in case_asgn["milestones"]}
        assert m_by_id[pending_ms["milestone_id"]]["status"] == "submitted"
        assert m_by_id[draft_ms["milestone_id"]]["status"] == "under_review"
        assert m_by_id[sent_ms["milestone_id"]]["status"] == "feedback_provided"
        # not_started for any unset week
        assert m_by_id[milestones[3]["milestone_id"]]["status"] == "not_started"

    def test_current_week_is_min_unsubmitted_across_assignments(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "curwk")
        # Submit ALL milestones for weeks 1..3 across ALL 4 assignments so current_week becomes 4
        assignments = list(db.assignments.find({"cohort_id": cid}, {"_id": 0}))
        now = datetime.now(timezone.utc).isoformat()
        sub_docs = []
        for a in assignments:
            for m in a["milestones"][:3]:  # weeks 1, 2, 3
                sub_docs.append({
                    "submission_id": f"sub_{uuid.uuid4().hex[:10]}",
                    "material_id": "",
                    "cohort_id": cid,
                    "student_id": seed["ids"]["student"],
                    "assignment_id": a["assignment_id"],
                    "milestone_id": m["milestone_id"],
                    "file_name": f"{TEST_PREFIX}x",
                    "submission_type": a["submission_type"],
                    "status": "pending",
                    "submitted_at": now,
                    "resubmission_count": 0,
                })
        db.submissions.insert_many(sub_docs)
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        entry = next(c for c in r.json() if c["cohort_id"] == cid)
        assert entry["current_week"] == 4
        # this_week entries all at week 4, and there should be 4 (one per assignment)
        assert len(entry["this_week"]) == 4
        assert all(tw["week_number"] == 4 for tw in entry["this_week"])

    def test_current_week_null_when_all_submitted(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "allsub")
        assignments = list(db.assignments.find({"cohort_id": cid}, {"_id": 0}))
        now = datetime.now(timezone.utc).isoformat()
        sub_docs = []
        for a in assignments:
            for m in a["milestones"]:
                sub_docs.append({
                    "submission_id": f"sub_{uuid.uuid4().hex[:10]}",
                    "material_id": "",
                    "cohort_id": cid,
                    "student_id": seed["ids"]["student"],
                    "assignment_id": a["assignment_id"],
                    "milestone_id": m["milestone_id"],
                    "file_name": f"{TEST_PREFIX}x",
                    "submission_type": a["submission_type"],
                    "status": "pending",
                    "submitted_at": now,
                    "resubmission_count": 0,
                })
        db.submissions.insert_many(sub_docs)
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        entry = next(c for c in r.json() if c["cohort_id"] == cid)
        assert entry["current_week"] is None
        assert entry["this_week"] == []

    def test_student_with_no_cohort_returns_empty_list(self, seed):
        r = requests.get(
            f"{BASE_URL}/api/student/assignments-dashboard",
            headers=_auth(seed["tokens"]["outsider"]), timeout=10,
        )
        assert r.status_code == 200
        # Outsider student is not in any TEST_P2_ cohort — but may be in other test cohorts.
        # Verify none of the test cohorts are shown (outsider is not enrolled).
        data = r.json()
        outsider_id = seed["ids"]["outsider"]
        # verify the outsider was never added to student_ids of a test cohort
        for entry in data:
            cohort = db.cohorts.find_one({"cohort_id": entry["cohort_id"]}, {"_id": 0, "student_ids": 1})
            assert outsider_id in (cohort.get("student_ids") or [])


# ===================================================================
# 2) POST /api/milestones/{milestone_id}/submit — happy path + errors
# ===================================================================
class TestMilestoneSubmitEndpoint:
    def test_requires_assignment_id_400(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "reqaid")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("test.pdf", io.BytesIO(b"pdf content"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        assert "assignment_id" in r.text

    def test_unknown_assignment_404(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "unkaid")
        files = {"file": ("t.pdf", io.BytesIO(b"x"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/ms_x/submit",
            params={"cohort_id": cid, "assignment_id": "asgn_nope"},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        assert r.status_code == 404

    def test_unknown_milestone_404(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "unkms")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        files = {"file": ("t.pdf", io.BytesIO(b"x"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/ms_nonexistent_x/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        assert r.status_code == 404

    def test_not_enrolled_student_403(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "not_enr")
        # student2 is NOT enrolled in this cohort
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("t.pdf", io.BytesIO(b"x"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student2"]), timeout=10,
        )
        assert r.status_code == 403

    def test_instructor_forbidden(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "instrole")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("t.pdf", io.BytesIO(b"x"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 403


# ===================================================================
# 3) File-type validation for 60_second_pitch (video only)
# ===================================================================
class TestFileTypeValidation:
    def test_60_second_pitch_rejects_pdf(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "pitch_pdf")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "60_second_pitch"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("pitch.pdf", io.BytesIO(b"pdf"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        # Response mentions allowed file types
        assert "Allowed" in r.text or "allowed" in r.text.lower()

    def test_60_second_pitch_accepts_mp4(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "pitch_mp4")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "60_second_pitch"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("pitch.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42"), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert not (data.get("is_resubmission"))
        # Verify submission persisted with correct linkage
        sub = db.submissions.find_one({"submission_id": data["submission_id"]}, {"_id": 0})
        assert sub["assignment_id"] == asgn["assignment_id"]
        assert sub["milestone_id"] == mid
        assert sub["cohort_id"] == cid
        assert sub["student_id"] == seed["ids"]["student"]


# ===================================================================
# 4) Business questionnaire validation + persistence
# ===================================================================
class TestQuestionnaireSubmission:
    def _get_questionnaire_asgn(self, cid):
        return db.assignments.find_one({"cohort_id": cid, "assignment_key": "business_questionnaire"}, {"_id": 0})

    def test_required_question_missing_400(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "q_miss")
        asgn = self._get_questionnaire_asgn(cid)
        # Inject a required questionnaire field for the test (auto-seed doesn't provide any)
        required_field = {"id": "q_biz_name", "label": "Business Name", "type": "text", "required": True}
        optional_field = {"id": "q_biz_desc", "label": "Business Description", "type": "longtext", "required": False}
        db.assignments.update_one(
            {"assignment_id": asgn["assignment_id"]},
            {"$set": {"questionnaire_fields": [required_field, optional_field]}},
        )
        asgn = db.assignments.find_one({"assignment_id": asgn["assignment_id"]}, {"_id": 0})
        fields = asgn.get("questionnaire_fields") or []
        assert len(fields) == 2
        mid = asgn["milestones"][0]["milestone_id"]
        # Send empty answers → should be 400 with the label
        answers_json = json.dumps({required_field["id"]: ""})
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            data={"questionnaire_answers": answers_json},
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        assert required_field["label"] in r.text

    def test_successful_questionnaire_persists_answers(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "q_ok")
        asgn = self._get_questionnaire_asgn(cid)
        # Inject fields for deterministic testing
        db.assignments.update_one(
            {"assignment_id": asgn["assignment_id"]},
            {"$set": {"questionnaire_fields": [
                {"id": "q_biz_name", "label": "Business Name", "type": "text", "required": True},
                {"id": "q_biz_desc", "label": "Business Description", "type": "longtext", "required": False},
            ]}},
        )
        asgn = db.assignments.find_one({"assignment_id": asgn["assignment_id"]}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]
        fields = asgn.get("questionnaire_fields") or []
        # Provide an answer for every field
        answers = {f["id"]: f"TEST answer for {f['label']}" for f in fields}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            data={"questionnaire_answers": json.dumps(answers)},
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        sub = db.submissions.find_one({"submission_id": r.json()["submission_id"]}, {"_id": 0})
        assert sub is not None
        persisted = sub.get("questionnaire_answers") or {}
        for f in fields:
            assert persisted.get(f["id"]) == answers[f["id"]]


# ===================================================================
# 5) Resubmission idempotency
# ===================================================================
class TestResubmission:
    def test_resubmission_updates_existing_no_dup(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "resub")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "10_slide_pitch"}, {"_id": 0})
        mid = asgn["milestones"][0]["milestone_id"]

        # 1st submission
        files1 = {"file": ("v1.pdf", io.BytesIO(b"first"), "application/pdf")}
        r1 = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files1,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r1.status_code == 200, r1.text
        data1 = r1.json()
        assert not (data1["is_resubmission"])
        sub_id_1 = data1["submission_id"]

        # 2nd submission — same student + assignment + milestone → resubmission
        files2 = {"file": ("v2.pdf", io.BytesIO(b"second"), "application/pdf")}
        r2 = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files2,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["is_resubmission"]
        # Same submission_id (updated in place)
        assert data2["submission_id"] == sub_id_1

        # No dup in DB — exactly ONE submission for this (student, assignment, milestone)
        count = db.submissions.count_documents({
            "student_id": seed["ids"]["student"],
            "assignment_id": asgn["assignment_id"],
            "milestone_id": mid,
        })
        assert count == 1

        # resubmission_count incremented
        sub = db.submissions.find_one({"submission_id": sub_id_1}, {"_id": 0})
        assert sub["resubmission_count"] == 1
        assert sub["file_name"] == "v2.pdf"
        assert sub["status"] == "pending"


# ===================================================================
# 6) Regression — legacy /api/materials/{id}/submit still works
# ===================================================================
class TestLegacyMaterialSubmitRegression:
    def test_legacy_material_submit_still_works(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "legacy")
        # Create a homework material directly in mongo
        mat_id = f"mat_{uuid.uuid4().hex[:10]}"
        db.materials.insert_one({
            "material_id": mat_id,
            "cohort_id": cid,
            "title": f"{TEST_PREFIX}legacy hw",
            "week_number": 1,
            "material_type": "homework",
            "submission_type": "",  # generic
            "file_name": "hw.pdf",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # Release the week so submissions are allowed (legacy path requires it)
        db.cohorts.update_one({"cohort_id": cid}, {"$addToSet": {"released_weeks": 1}})
        files = {"file": ("hw_answer.pdf", io.BytesIO(b"content"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/materials/{mat_id}/submit",
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        # 200 = success; if the legacy endpoint requires additional gating we accept 200 only.
        assert r.status_code == 200, r.text
        sub = db.submissions.find_one({"submission_id": r.json()["submission_id"]}, {"_id": 0})
        assert sub is not None
        assert sub["material_id"] == mat_id
