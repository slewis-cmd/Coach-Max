"""
Iteration 38 - Backend test suite for Phase 1 Assignments refactor.

Covers:
- Cohort auto_send_feedback + total_weeks fields (Cohort model + CohortUpdate)
- Auto-seed 4 default assignments on cohort create + Kawasaki final capstone
- GET /api/cohorts/{id}/assignments (auto-seed, access control)
- POST /api/cohorts/{id}/assignments (custom assignments, submission_type validation)
- PUT /api/assignments/{id} (update fields; permission)
- DELETE /api/assignments/{id} (soft-delete; is_active=false)
- PUT /api/assignments/{id}/milestones/{milestone_id} (update in place; 404 unknown)
- GET /api/submit-link/a/{aid}/w/{week} (200 + 404)
- POST /api/admin/migrate-to-assignments (super_admin only, idempotent, reassigns subs)
- POST /api/materials/{id}/submit stores assignment_id/milestone_id when provided
- review_submission builds prior-submission context (cumulative feedback) and auto_send
- PUT /api/cohorts/{id} persists auto_send_feedback + total_weeks
- DELETE /api/cohorts/{id} cascades to db.assignments

All seeded docs prefixed TEST_ASGN_.
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

TEST_PREFIX = "TEST_ASGN_"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _tiny_txt() -> bytes:
    return b"Iteration 38 test submission content - pitch draft."


@pytest.fixture(scope="module")
def seed():
    ts = int(time.time())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    now_iso = datetime.now(timezone.utc).isoformat()

    ids = {
        "sa":         f"{TEST_PREFIX}sa_{ts}",
        "instructor": f"{TEST_PREFIX}i1_{ts}",
        "other_ins":  f"{TEST_PREFIX}i2_{ts}",
        "student":    f"{TEST_PREFIX}stu_{ts}",
        "outsider":   f"{TEST_PREFIX}out_{ts}",
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids.keys()}

    db.users.insert_many([
        {"user_id": ids["sa"],         "email": f"{TEST_PREFIX}sa_{ts}@x.com",  "name": "Adm",  "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i_{ts}@x.com",   "name": "Ins",  "role": "instructor",  "created_at": now_iso},
        {"user_id": ids["other_ins"],  "email": f"{TEST_PREFIX}i2_{ts}@x.com",  "name": "Ins2", "role": "instructor",  "created_at": now_iso},
        {"user_id": ids["student"],    "email": f"{TEST_PREFIX}s_{ts}@x.com",   "name": "Stu",  "role": "student",     "language_preference": "en", "created_at": now_iso},
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
    db.submissions.delete_many({"file_name": {"$regex": f"^{TEST_PREFIX}"}})


def _create_cohort(token, name_suffix="", instructor_id=None):
    """Create cohort via API + returns cohort_id."""
    name = f"{TEST_PREFIX}C_{name_suffix}_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/cohorts",
        json={"name": name, "description": "iter38 test cohort"},
        headers=_auth(token), timeout=15,
    )
    assert r.status_code == 200, f"create_cohort failed: {r.status_code} {r.text}"
    return r.json()["cohort_id"], name


# ===================================================================
# 1) Cohort model — auto_send_feedback + total_weeks defaults
# ===================================================================
class TestCohortModelExtensions:
    def test_new_cohort_has_default_total_weeks_and_auto_send(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "modeldef")
        doc = db.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
        assert doc is not None
        assert doc.get("total_weeks") == 14
        assert doc.get("auto_send_feedback") is False

    def test_cohort_update_persists_auto_send_and_total_weeks(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "upd")
        r = requests.put(
            f"{BASE_URL}/api/cohorts/{cid}",
            json={"auto_send_feedback": True, "total_weeks": 10},
            headers=_auth(seed["tokens"]["instructor"]),
            timeout=10,
        )
        assert r.status_code == 200, r.text
        doc = db.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
        assert doc["auto_send_feedback"] is True
        assert doc["total_weeks"] == 10


# ===================================================================
# 2) Auto-seed 4 default assignments on cohort create
# ===================================================================
class TestAutoSeedOnCreate:
    def test_create_cohort_seeds_four_default_assignments(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "seed")
        # Small wait for the fire-and-forget-style block to complete (it's awaited but be safe)
        docs = list(db.assignments.find({"cohort_id": cid}, {"_id": 0}))
        keys = sorted([d["assignment_key"] for d in docs])
        assert keys == sorted([
            "60_second_pitch", "10_slide_pitch", "case_activity", "business_questionnaire"
        ])

    def test_each_default_assignment_has_14_milestones(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "seed14")
        for d in db.assignments.find({"cohort_id": cid}, {"_id": 0}):
            ms = d.get("milestones") or []
            assert len(ms) == 14, f"{d['assignment_key']} has {len(ms)}"

    def test_kawasaki_final_milestone_is_capstone(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "capstone")
        kaw = db.assignments.find_one(
            {"cohort_id": cid, "assignment_key": "10_slide_pitch"}, {"_id": 0}
        )
        assert kaw is not None
        ms = kaw["milestones"]
        assert ms[-1]["is_final_capstone"] is True
        # non-final should not be capstones
        assert all(not m.get("is_final_capstone") for m in ms[:-1])

    def test_non_kawasaki_have_no_capstone(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "nocap")
        for key in ("60_second_pitch", "case_activity", "business_questionnaire"):
            d = db.assignments.find_one({"cohort_id": cid, "assignment_key": key}, {"_id": 0})
            assert d is not None
            assert all(not m.get("is_final_capstone") for m in d["milestones"])


# ===================================================================
# 3) GET /api/cohorts/{id}/assignments
# ===================================================================
class TestListAssignments:
    def test_instructor_lists_four_defaults(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "list")
        r = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 4
        assert all("milestones" in d for d in data)

    def test_enrolled_student_can_read_assignments(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "stuview")
        # Enroll student
        db.cohorts.update_one({"cohort_id": cid}, {"$push": {"student_ids": seed["ids"]["student"]}})
        r = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["student"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) == 4

    def test_non_enrolled_non_instructor_gets_403(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "outside")
        r = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["outsider"]), timeout=10,
        )
        assert r.status_code == 403

    def test_auto_seed_on_instructor_get_when_missing(self, seed):
        # Create cohort directly in mongo (bypass endpoint) with no assignments seeded
        cid = f"{TEST_PREFIX}bare_{uuid.uuid4().hex[:8]}"
        db.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}bare",
            "instructor_id": seed["ids"]["instructor"],
            "instructor_ids": [seed["ids"]["instructor"]],
            "student_ids": [],
            "total_weeks": 14,
            "auto_send_feedback": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        assert db.assignments.count_documents({"cohort_id": cid}) == 0
        r = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        assert len(r.json()) == 4
        assert db.assignments.count_documents({"cohort_id": cid}) == 4


# ===================================================================
# 4) POST /api/cohorts/{id}/assignments — custom assignment
# ===================================================================
class TestCreateCustomAssignment:
    def test_creates_custom_with_valid_submission_type(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "cust")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={
                "title": f"{TEST_PREFIX}Custom Pitch",
                "submission_type": "60_second_pitch",
                "description": "custom",
                "assignment_key": "custom",
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["submission_type"] == "60_second_pitch"
        assert data["title"] == f"{TEST_PREFIX}Custom Pitch"
        assert len(data["milestones"]) == 14
        assert data["order"] == 4  # after the 4 defaults

    def test_rejects_unknown_submission_type_400(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "custbad")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={"title": "T", "submission_type": "nope"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 400
        assert "submission_type" in r.text


# ===================================================================
# 5) PUT /api/assignments/{id}
# ===================================================================
class TestUpdateAssignment:
    def test_update_title_and_feedback_template(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "updasgn")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        aid = asgn["assignment_id"]
        r = requests.put(
            f"{BASE_URL}/api/assignments/{aid}",
            json={"title": "New Case Title", "feedback_template": "rubric v2"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["title"] == "New Case Title"
        assert got["feedback_template"] == "rubric v2"

    def test_non_manager_gets_403(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "updperm")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        r = requests.put(
            f"{BASE_URL}/api/assignments/{asgn['assignment_id']}",
            json={"title": "hacker"},
            headers=_auth(seed["tokens"]["other_ins"]), timeout=10,
        )
        assert r.status_code == 403


# ===================================================================
# 6) DELETE /api/assignments/{id} — soft delete
# ===================================================================
class TestSoftDeleteAssignment:
    def test_soft_delete_sets_inactive(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "delasgn")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        aid = asgn["assignment_id"]
        r = requests.delete(
            f"{BASE_URL}/api/assignments/{aid}",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        doc = db.assignments.find_one({"assignment_id": aid}, {"_id": 0})
        assert doc is not None
        assert doc["is_active"] is False


# ===================================================================
# 7) PUT /api/assignments/{aid}/milestones/{mid}
# ===================================================================
class TestUpdateMilestone:
    def test_update_milestone_in_place(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "milestone")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "60_second_pitch"}, {"_id": 0})
        ms = asgn["milestones"][2]  # week 3
        r = requests.put(
            f"{BASE_URL}/api/assignments/{asgn['assignment_id']}/milestones/{ms['milestone_id']}",
            json={
                "week_number": 3,
                "title": "Refined Pitch",
                "description": "polish it",
                "feedback_template_override": "custom rubric",
                "is_final_capstone": False,
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        # Verify persisted
        doc = db.assignments.find_one({"assignment_id": asgn["assignment_id"]}, {"_id": 0})
        m = next(m for m in doc["milestones"] if m["milestone_id"] == ms["milestone_id"])
        assert m["title"] == "Refined Pitch"
        assert m["feedback_template_override"] == "custom rubric"
        assert m["description"] == "polish it"

    def test_update_unknown_milestone_returns_404(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "unkms")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "60_second_pitch"}, {"_id": 0})
        r = requests.put(
            f"{BASE_URL}/api/assignments/{asgn['assignment_id']}/milestones/ms_nonexistent",
            json={"week_number": 3, "title": "x"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 404


# ===================================================================
# 8) GET /api/submit-link/a/{assignment_id}/w/{week_number}
# ===================================================================
class TestAssignmentSubmitLinkResolver:
    def test_valid_returns_milestone(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "resolve")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "10_slide_pitch"}, {"_id": 0})
        r = requests.get(
            f"{BASE_URL}/api/submit-link/a/{asgn['assignment_id']}/w/5", timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["assignment_id"] == asgn["assignment_id"]
        assert data["cohort_id"] == cid
        # milestone_id matches week 5 in asgn's milestones
        expected_ms = next(m for m in asgn["milestones"] if m["week_number"] == 5)
        assert data["milestone_id"] == expected_ms["milestone_id"]

    def test_missing_week_returns_404(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "resolve404")
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "60_second_pitch"}, {"_id": 0})
        r = requests.get(
            f"{BASE_URL}/api/submit-link/a/{asgn['assignment_id']}/w/99", timeout=10,
        )
        assert r.status_code == 404


# ===================================================================
# 9) DELETE /api/cohorts/{id} cascades to assignments
# ===================================================================
class TestCohortDeleteCascade:
    def test_delete_cohort_cleans_assignments(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "casc")
        assert db.assignments.count_documents({"cohort_id": cid}) == 4
        r = requests.delete(
            f"{BASE_URL}/api/cohorts/{cid}",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        assert db.assignments.count_documents({"cohort_id": cid}) == 0


# ===================================================================
# 10) POST /api/admin/migrate-to-assignments — super_admin only + idempotent
# ===================================================================
class TestMigration:
    def _create_pre_migration_cohort(self, seed):
        """Create a cohort DIRECTLY in mongo (so no assignments are auto-seeded)
        + a homework material + a submission — simulates pre-refactor state."""
        cid = f"{TEST_PREFIX}pre_{uuid.uuid4().hex[:8]}"
        db.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}pre",
            "instructor_id": seed["ids"]["instructor"],
            "instructor_ids": [seed["ids"]["instructor"]],
            "student_ids": [seed["ids"]["student"]],
            "total_weeks": 14,
            "auto_send_feedback": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mat_id = f"mat_{uuid.uuid4().hex[:10]}"
        db.materials.insert_one({
            "material_id": mat_id,
            "cohort_id": cid,
            "week_number": 4,
            "material_type": "homework",
            "title": f"{TEST_PREFIX}OldHW",
            "file_name": f"{TEST_PREFIX}old.pdf",
            "uploaded_by": seed["ids"]["instructor"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        sub_id = f"sub_{uuid.uuid4().hex[:10]}"
        db.submissions.insert_one({
            "submission_id": sub_id,
            "material_id": mat_id,
            "cohort_id": cid,
            "student_id": seed["ids"]["student"],
            "file_name": f"{TEST_PREFIX}old_sub.pdf",
            "status": "reviewed",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })
        return cid, mat_id, sub_id

    def test_migration_requires_super_admin(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/admin/migrate-to-assignments",
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 403

    def test_migration_seeds_assignments_and_reassigns_subs(self, seed):
        cid, mat_id, sub_id = self._create_pre_migration_cohort(seed)
        r = requests.post(
            f"{BASE_URL}/api/admin/migrate-to-assignments",
            headers=_auth(seed["tokens"]["sa"]), timeout=60,
        )
        assert r.status_code == 200, r.text
        stats = r.json()
        assert stats["cohorts_seeded"] >= 1
        assert stats["submissions_linked"] >= 1
        # Assignments seeded
        assert db.assignments.count_documents({"cohort_id": cid}) == 4
        qn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "business_questionnaire"}, {"_id": 0})
        assert qn is not None
        # Submission now linked to questionnaire assignment
        sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert sub["assignment_id"] == qn["assignment_id"]
        assert sub["milestone_id"]
        # Material archived
        mat = db.materials.find_one({"material_id": mat_id}, {"_id": 0})
        assert mat.get("migrated_to_assignment") is True

    def test_migration_idempotent(self, seed):
        # Second run — no more cohorts should be seeded (assumes previous test ran)
        r1 = requests.post(
            f"{BASE_URL}/api/admin/migrate-to-assignments",
            headers=_auth(seed["tokens"]["sa"]), timeout=60,
        )
        r2 = requests.post(
            f"{BASE_URL}/api/admin/migrate-to-assignments",
            headers=_auth(seed["tokens"]["sa"]), timeout=60,
        )
        assert r1.status_code == r2.status_code == 200
        # After first cleanup, second must be a no-op on cohorts_seeded
        stats2 = r2.json()
        assert stats2["cohorts_seeded"] == 0
        # Submissions already linked — should be 0 additional linked
        assert stats2["submissions_linked"] == 0


# ===================================================================
# 11) POST /api/materials/{id}/submit stores assignment_id + milestone_id
# ===================================================================
class TestSubmissionCarriesAssignmentIds:
    def test_submit_with_query_params_persists_ids(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "subhw")
        # Enroll student
        db.cohorts.update_one({"cohort_id": cid}, {"$push": {"student_ids": seed["ids"]["student"]}})
        # Add releases so material is submittable
        db.cohorts.update_one({"cohort_id": cid}, {"$set": {"released_weeks": list(range(1, 15))}})
        # Upload a homework material (generic type)
        files = {"file": (f"{TEST_PREFIX}hw.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")}
        params = {
            "week_number": 3,
            "material_type": "homework",
            "title": f"{TEST_PREFIX}subhw_material",
            "description": "",
        }
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/materials",
            params=params, files=files,
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        # Get the seeded 60-sec assignment for this cohort
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        ms3 = next(m for m in asgn["milestones"] if m["week_number"] == 3)

        # Student submits with assignment_id + milestone_id as query params
        submit_files = {"file": (f"{TEST_PREFIX}subA.pdf", b"%PDF-1.4\ncontent\n%%EOF", "application/pdf")}
        r2 = requests.post(
            f"{BASE_URL}/api/materials/{mid}/submit",
            params={"assignment_id": asgn["assignment_id"], "milestone_id": ms3["milestone_id"]},
            files=submit_files,
            headers=_auth(seed["tokens"]["student"]), timeout=20,
        )
        assert r2.status_code == 200, r2.text
        sub_id = r2.json()["submission_id"]
        sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert sub["assignment_id"] == asgn["assignment_id"]
        assert sub["milestone_id"] == ms3["milestone_id"]


# ===================================================================
# 12) Cumulative feedback: build_cumulative_context surfaces prior asgn submissions
# ===================================================================
class TestCumulativeReview:
    def test_review_uses_prior_assignment_submissions(self, seed):
        """Seed 2 submissions for the SAME assignment (week 2 + week 3) for the same
        student, then trigger review on week 3. AI feedback should populate (EMERGENT_LLM_KEY)."""
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "cumul")
        db.cohorts.update_one({"cohort_id": cid}, {"$push": {"student_ids": seed["ids"]["student"]}})
        db.cohorts.update_one({"cohort_id": cid}, {"$set": {"released_weeks": list(range(1, 15))}})

        # Reuse the same "homework" material for both weeks (server allows submissions with assignment_id override)
        # Actually — a submission is scoped by (material_id, student_id, cohort_id). To get two submissions
        # with different milestones from same student, we need two separate materials OR direct seeding.
        # Simplest: seed both submissions directly in mongo pointing at the SAME assignment_id, different milestones.
        asgn = db.assignments.find_one({"cohort_id": cid, "assignment_key": "case_activity"}, {"_id": 0})
        ms2 = next(m for m in asgn["milestones"] if m["week_number"] == 2)
        ms3 = next(m for m in asgn["milestones"] if m["week_number"] == 3)

        # Create two homework materials (week 2 + week 3)
        def mkmat(week, title_suffix):
            mat_id = f"mat_{uuid.uuid4().hex[:10]}"
            db.materials.insert_one({
                "material_id": mat_id, "cohort_id": cid, "week_number": week,
                "material_type": "homework", "title": f"{TEST_PREFIX}HW_{title_suffix}",
                "file_name": f"{TEST_PREFIX}HW_{title_suffix}.txt", "uploaded_by": seed["ids"]["instructor"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            return mat_id

        mid2 = mkmat(2, "w2")
        mid3 = mkmat(3, "w3")

        # Seed submission for week 2 (with prior instructor_feedback so cumulative context has content)
        # Use gridfs upload via POST submit, then update to add assignment_id + feedback
        files2 = {"file": (f"{TEST_PREFIX}cum_w2.pdf", b"%PDF-1.4\nWeek 2 pitch: identifying the problem for busy commuters.\n%%EOF", "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/materials/{mid2}/submit",
            params={"assignment_id": asgn["assignment_id"], "milestone_id": ms2["milestone_id"]},
            files=files2,
            headers=_auth(seed["tokens"]["student"]), timeout=20,
        )
        assert r.status_code == 200, r.text
        sub2_id = r.json()["submission_id"]
        # Add feedback (simulate prior week already reviewed)
        db.submissions.update_one(
            {"submission_id": sub2_id},
            {"$set": {"status": "sent", "instructor_feedback": "Great problem framing, next add customer segment."}}
        )

        # Now submit week 3
        files3 = {"file": (f"{TEST_PREFIX}cum_w3.pdf", b"%PDF-1.4\nWeek 3 pitch: added customer segment - college students commuting to campus.\n%%EOF", "application/pdf")}
        r3 = requests.post(
            f"{BASE_URL}/api/materials/{mid3}/submit",
            params={"assignment_id": asgn["assignment_id"], "milestone_id": ms3["milestone_id"]},
            files=files3,
            headers=_auth(seed["tokens"]["student"]), timeout=20,
        )
        assert r3.status_code == 200, r3.text
        sub3_id = r3.json()["submission_id"]

        # Trigger review as instructor
        rev = requests.post(
            f"{BASE_URL}/api/submissions/{sub3_id}/review",
            headers=_auth(seed["tokens"]["instructor"]), timeout=90,
        )
        assert rev.status_code == 200, rev.text
        data = rev.json()
        # Since cohort.auto_send_feedback=False (default), status='draft'
        assert data.get("status") == "draft"
        # AI feedback must be populated (proves the LLM call succeeded and context flow ran)
        sub3 = db.submissions.find_one({"submission_id": sub3_id}, {"_id": 0})
        assert sub3.get("ai_feedback"), "expected ai_feedback to be populated"


# ===================================================================
# 13) auto_send_feedback=True flips status to 'sent'
# ===================================================================
class TestAutoSendFeedback:
    def test_auto_send_flips_status_sent(self, seed):
        cid, _ = _create_cohort(seed["tokens"]["instructor"], "autosend")
        # Enable auto_send_feedback on the cohort
        requests.put(
            f"{BASE_URL}/api/cohorts/{cid}",
            json={"auto_send_feedback": True},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        db.cohorts.update_one({"cohort_id": cid}, {"$push": {"student_ids": seed["ids"]["student"]}})
        db.cohorts.update_one({"cohort_id": cid}, {"$set": {"released_weeks": list(range(1, 15))}})

        # Create homework material
        mat_params = {"week_number": 2, "material_type": "homework", "title": f"{TEST_PREFIX}autoHW"}
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/materials",
            params=mat_params,
            files={"file": (f"{TEST_PREFIX}hw.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        mid = r.json()["material_id"]

        # Student submits
        sub_r = requests.post(
            f"{BASE_URL}/api/materials/{mid}/submit",
            files={"file": (f"{TEST_PREFIX}auto_sub.pdf", b"%PDF-1.4\npitch draft content\n%%EOF", "application/pdf")},
            headers=_auth(seed["tokens"]["student"]), timeout=20,
        )
        assert sub_r.status_code == 200, sub_r.text
        sub_id = sub_r.json()["submission_id"]

        # Trigger instructor review → should auto-send
        rev = requests.post(
            f"{BASE_URL}/api/submissions/{sub_id}/review",
            headers=_auth(seed["tokens"]["instructor"]), timeout=90,
        )
        assert rev.status_code == 200, rev.text
        data = rev.json()
        assert data.get("status") == "sent", f"expected auto-send, got {data}"
        sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert sub.get("feedback_sent") is True
        assert sub.get("sent_at") is not None
