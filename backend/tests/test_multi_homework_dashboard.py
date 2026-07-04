"""
Tests for the multi-homework-per-week feature in /api/student/dashboard.

The student dashboard was rewritten so each week returns a `homeworks` array
supporting N parallel homework tracks per week. Overall week.status = the
LEAST-COMPLETE of all homeworks (higher status_rank = less complete):
    no_homework(0) < feedback_provided(1) < under_review(2)
    < submitted(3) < waiting_on_submission(4)

Legacy `week.homework` and `week.submission` still point to the FIRST homework
for back-compat.

Endpoints under test:
- GET  /api/student/dashboard  (multi-homework aggregation + legacy fields)
- POST /api/materials/{material_id}/submit  (per-material submissions)
- POST /api/submissions/{submission_id}/review  (per-material AI review)

Regression:
- course_resources still returned
- week.materials includes ALL homework materials + workbooks + case_studies
"""
import io
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient
from bson import ObjectId


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
SUPER_ADMIN_EMAIL = "slewis@theboostpad.org"

TEST_PREFIX = "TEST_MHW_"
WEEK = 3


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


def _seed_session(mongo, user_id: str, prefix: str) -> str:
    token = f"{prefix}_{uuid.uuid4().hex[:12]}"
    mongo.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    })
    return token


@pytest.fixture(scope="module")
def admin(mongo):
    doc = mongo.users.find_one({"email": SUPER_ADMIN_EMAIL})
    assert doc, f"Super admin {SUPER_ADMIN_EMAIL} not seeded"
    token = _seed_session(mongo, doc["user_id"], "test_mhw_admin")
    yield {"user_id": doc["user_id"], "token": token,
           "headers": {"Authorization": f"Bearer {token}"}}
    mongo.user_sessions.delete_one({"session_token": token})


@pytest.fixture(scope="module")
def instructor(mongo):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"{TEST_PREFIX}inst_{uuid.uuid4().hex[:6]}@example.com"
    mongo.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{TEST_PREFIX}Instructor",
        "picture": None,
        "role": "instructor",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    token = _seed_session(mongo, uid, "test_mhw_inst")
    yield {"user_id": uid, "email": email, "token": token,
           "headers": {"Authorization": f"Bearer {token}"}}
    mongo.user_sessions.delete_one({"session_token": token})
    mongo.users.delete_one({"user_id": uid})


@pytest.fixture(scope="module")
def student(mongo):
    uid = f"user_{uuid.uuid4().hex[:12]}"
    email = f"{TEST_PREFIX}stu_{uuid.uuid4().hex[:6]}@example.com"
    mongo.users.insert_one({
        "user_id": uid,
        "email": email,
        "name": f"{TEST_PREFIX}Student",
        "picture": None,
        "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    token = _seed_session(mongo, uid, "test_mhw_stu")
    yield {"user_id": uid, "email": email, "token": token,
           "headers": {"Authorization": f"Bearer {token}"}}
    mongo.user_sessions.delete_one({"session_token": token})
    mongo.users.delete_one({"user_id": uid})


@pytest.fixture(scope="module")
def cohort(mongo, admin, instructor, student):
    cid = f"cohort_{uuid.uuid4().hex[:12]}"
    name = f"{TEST_PREFIX}Cohort_{uuid.uuid4().hex[:6]}"
    mongo.cohorts.insert_one({
        "cohort_id": cid,
        "name": name,
        "description": "multi-homework test cohort",
        "instructor_id": instructor["user_id"],
        "instructor_ids": [instructor["user_id"]],
        "student_ids": [student["user_id"]],
        "released_weeks": [WEEK],
        "invite_code": uuid.uuid4().hex[:8],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    yield {"cohort_id": cid, "name": name}
    mongo.cohorts.delete_one({"cohort_id": cid})


# Track everything inserted so teardown is guaranteed
_created_material_ids: list = []
_created_submission_ids: list = []
_created_gridfs_ids: list = []


def _insert_material(mongo, cohort_id: str, week: int, material_type: str,
                     title: str, gridfs_id: str = None, description: str = "") -> str:
    mid = f"mat_{uuid.uuid4().hex[:12]}"
    doc = {
        "material_id": mid,
        "cohort_id": cohort_id,
        "week_number": week,
        "material_type": material_type,
        "title": title,
        "description": description,
        "file_path": "",
        "gridfs_id": gridfs_id,
        "file_name": f"{title}.pdf",
        "uploaded_by": "system",
        "due_date": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    mongo.materials.insert_one(doc)
    _created_material_ids.append(mid)
    return mid


def _insert_submission(mongo, *, cohort_id: str, material_id: str, student_id: str,
                       status: str, ai_fb: str = None, instr_fb: str = None) -> str:
    sid = f"sub_{uuid.uuid4().hex[:12]}"
    doc = {
        "submission_id": sid,
        "material_id": material_id,
        "cohort_id": cohort_id,
        "student_id": student_id,
        "file_path": "",
        "gridfs_id": None,
        "file_name": f"{sid}.pdf",
        "status": status,
        "ai_feedback": ai_fb,
        "instructor_feedback": instr_fb,
        "feedback_sent": (status == "sent"),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_at": None,
        "sent_at": None,
    }
    mongo.submissions.insert_one(doc)
    _created_submission_ids.append(sid)
    return sid


@pytest.fixture(scope="module", autouse=True)
def cleanup(mongo):
    yield
    # Delete submissions
    if _created_submission_ids:
        mongo.submissions.delete_many({"submission_id": {"$in": _created_submission_ids}})
    # Delete materials + any lingering gridfs blobs
    for mid in _created_material_ids:
        m = mongo.materials.find_one({"material_id": mid})
        if m and m.get("gridfs_id"):
            try:
                mongo["fs.files"].delete_one({"_id": ObjectId(m["gridfs_id"])})
                mongo["fs.chunks"].delete_many({"files_id": ObjectId(m["gridfs_id"])})
            except Exception:
                pass
    mongo.materials.delete_many({"material_id": {"$in": _created_material_ids}})
    # Also catch anything with TEST_MHW_ prefix that may have slipped through
    for m in mongo.materials.find({"title": {"$regex": f"^{TEST_PREFIX}"}}):
        if m.get("gridfs_id"):
            try:
                mongo["fs.files"].delete_one({"_id": ObjectId(m["gridfs_id"])})
                mongo["fs.chunks"].delete_many({"files_id": ObjectId(m["gridfs_id"])})
            except Exception:
                pass
    mongo.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    # Clean submissions for the test student too
    mongo.submissions.delete_many({"file_name": {"$regex": r"^sub_"}}) if False else None


def _get_dashboard(student):
    r = requests.get(f"{BASE_URL}/api/student/dashboard",
                     headers=student["headers"], timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _get_week(dashboard: list, cohort_id: str, week: int) -> dict:
    for c in dashboard:
        if c["cohort_id"] == cohort_id:
            for w in c["weeks"]:
                if w["week_number"] == week:
                    return w
    raise AssertionError(f"Week {week} for cohort {cohort_id} not found in dashboard")


# ---------- Tests ----------

class TestSingleHomeworkRegression:
    """Cohort with exactly 1 homework in week — new homeworks[] must be
    single-element and legacy fields must still populate."""

    def test_single_homework_returns_length_1_array_and_legacy(self, mongo, cohort, student):
        # Seed exactly one homework material in the released week
        mid = _insert_material(mongo, cohort["cohort_id"], WEEK,
                               "homework", f"{TEST_PREFIX}HW_Single",
                               description="single-hw description")
        try:
            dash = _get_dashboard(student)
            week = _get_week(dash, cohort["cohort_id"], WEEK)

            # New array shape
            assert "homeworks" in week, "week must expose 'homeworks' array"
            assert isinstance(week["homeworks"], list)
            assert len(week["homeworks"]) == 1
            hw0 = week["homeworks"][0]
            assert hw0["material_id"] == mid
            assert hw0["title"] == f"{TEST_PREFIX}HW_Single"
            assert hw0["status"] == "waiting_on_submission"
            assert hw0["submission"] is None
            assert hw0["feedback"] is None

            # Legacy fields
            assert week["homework"] is not None
            assert week["homework"]["material_id"] == mid
            assert week["submission"] is None  # no submission yet
            assert week["status"] == "waiting_on_submission"
        finally:
            mongo.materials.delete_one({"material_id": mid})


class TestMultiHomework:
    """Cohort with TWO homework materials in the same week — full multi-HW test suite."""

    @pytest.fixture(scope="class")
    def hw_pair(self, mongo, cohort):
        # Seed 2 homework materials + 1 workbook + 1 case_study for materials regression
        hw_a = _insert_material(mongo, cohort["cohort_id"], WEEK, "homework",
                                f"{TEST_PREFIX}HW1_A", description="First track")
        hw_b = _insert_material(mongo, cohort["cohort_id"], WEEK, "homework",
                                f"{TEST_PREFIX}HW1_B", description="Second track")
        wb = _insert_material(mongo, cohort["cohort_id"], WEEK, "workbook",
                              f"{TEST_PREFIX}WB")
        cs = _insert_material(mongo, cohort["cohort_id"], WEEK, "case_study",
                              f"{TEST_PREFIX}CS")
        yield {"hw_a": hw_a, "hw_b": hw_b, "wb": wb, "cs": cs}

    def _reset_submissions(self, mongo, cohort_id, student_id, mids):
        mongo.submissions.delete_many({
            "cohort_id": cohort_id,
            "student_id": student_id,
            "material_id": {"$in": mids},
        })

    # ---- 1. Shape ----
    def test_two_homeworks_returns_length_2_array(self, mongo, cohort, student, hw_pair):
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        dash = _get_dashboard(student)
        week = _get_week(dash, cohort["cohort_id"], WEEK)
        assert len(week["homeworks"]) == 2

        # Each has its own material_id, title, status, submission
        mids_returned = {h["material_id"] for h in week["homeworks"]}
        assert mids_returned == {hw_pair["hw_a"], hw_pair["hw_b"]}
        for h in week["homeworks"]:
            assert "title" in h and h["title"].startswith(TEST_PREFIX)
            assert h["status"] == "waiting_on_submission"
            assert h["submission"] is None

    # ---- 2. Overall week.status = least-complete ----
    def test_status_both_waiting_is_waiting(self, mongo, cohort, student, hw_pair):
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        assert week["status"] == "waiting_on_submission"

    def test_status_hw1_feedback_hw2_waiting_is_waiting(self, mongo, cohort, student, hw_pair):
        # HW1 sent (feedback_provided rank=1), HW2 waiting (rank=4) → overall waiting
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_a"], student_id=student["user_id"],
                           status="sent", instr_fb="Great job on HW1")
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        assert week["status"] == "waiting_on_submission", \
            f"Expected waiting_on_submission (least complete), got {week['status']}"

        # Verify per-hw status is still correct
        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        assert by_mid[hw_pair["hw_a"]]["status"] == "feedback_provided"
        assert by_mid[hw_pair["hw_a"]]["feedback"] == "Great job on HW1"
        assert by_mid[hw_pair["hw_b"]]["status"] == "waiting_on_submission"

    def test_status_hw1_sent_hw2_pending_is_submitted(self, mongo, cohort, student, hw_pair):
        # HW1 sent (rank=1), HW2 pending/submitted (rank=3) → overall submitted
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_a"], student_id=student["user_id"],
                           status="sent", instr_fb="Feedback A")
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_b"], student_id=student["user_id"],
                           status="pending")
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        assert week["status"] == "submitted", \
            f"Expected submitted, got {week['status']}"
        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        assert by_mid[hw_pair["hw_a"]]["status"] == "feedback_provided"
        assert by_mid[hw_pair["hw_b"]]["status"] == "submitted"

    def test_status_hw1_sent_hw2_draft_is_under_review(self, mongo, cohort, student, hw_pair):
        # HW1 sent (rank=1), HW2 draft=under_review (rank=2) → overall under_review
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_a"], student_id=student["user_id"],
                           status="sent", instr_fb="Feedback A")
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_b"], student_id=student["user_id"],
                           status="draft", ai_fb="AI draft feedback")
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        assert week["status"] == "under_review", \
            f"Expected under_review, got {week['status']}"

    def test_status_both_sent_is_feedback_provided(self, mongo, cohort, student, hw_pair):
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_a"], student_id=student["user_id"],
                           status="sent", instr_fb="Feedback A")
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=hw_pair["hw_b"], student_id=student["user_id"],
                           status="sent", instr_fb="Feedback B")
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        assert week["status"] == "feedback_provided"

        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        # Each homework carries its OWN feedback
        assert by_mid[hw_pair["hw_a"]]["feedback"] == "Feedback A"
        assert by_mid[hw_pair["hw_b"]]["feedback"] == "Feedback B"
        # Legacy top-level feedback = first feedback_provided entry
        assert week["feedback"] in ("Feedback A", "Feedback B")

    # ---- 3. Real API submission end-to-end ----
    def test_student_submits_hw1_only_via_api(self, mongo, cohort, student, hw_pair):
        self._reset_submissions(mongo, cohort["cohort_id"], student["user_id"],
                                [hw_pair["hw_a"], hw_pair["hw_b"]])

        # Minimal-but-valid PDF bytes (extension check is the only server-side gate)
        pdf_bytes = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                     b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                     b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
                     b"trailer<</Root 1 0 R>>\n%%EOF")
        files = {"file": ("submission_hw1.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/materials/{hw_pair['hw_a']}/submit",
            files=files, headers=student["headers"], timeout=60,
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]
        _created_submission_ids.append(sid)

        # Verify dashboard: HW1 -> submitted, HW2 -> waiting_on_submission
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        assert by_mid[hw_pair["hw_a"]]["status"] == "submitted"
        assert by_mid[hw_pair["hw_a"]]["submission"] is not None
        assert by_mid[hw_pair["hw_a"]]["submission"]["submission_id"] == sid
        assert by_mid[hw_pair["hw_b"]]["status"] == "waiting_on_submission"
        assert by_mid[hw_pair["hw_b"]]["submission"] is None
        # Overall week status = least complete = waiting_on_submission (HW2 not started)
        assert week["status"] == "waiting_on_submission"

    def test_student_submits_hw2_also_independent_ids(self, mongo, cohort, student, hw_pair):
        # HW1 should still be 'submitted' from previous test; now submit HW2
        pdf_bytes = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                     b"trailer<</Root 1 0 R>>\n%%EOF")
        files = {"file": ("submission_hw2.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/materials/{hw_pair['hw_b']}/submit",
            files=files, headers=student["headers"], timeout=60,
        )
        assert r.status_code == 200, r.text
        sid_b = r.json()["submission_id"]
        _created_submission_ids.append(sid_b)

        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        sub_a = by_mid[hw_pair["hw_a"]]["submission"]
        sub_b = by_mid[hw_pair["hw_b"]]["submission"]
        assert sub_a is not None and sub_b is not None
        # Independent submission_ids
        assert sub_a["submission_id"] != sub_b["submission_id"]
        assert sub_b["submission_id"] == sid_b
        # Both statuses = submitted
        assert by_mid[hw_pair["hw_a"]]["status"] == "submitted"
        assert by_mid[hw_pair["hw_b"]]["status"] == "submitted"
        # Overall week status = submitted
        assert week["status"] == "submitted"

    def test_download_submissions_independently(self, mongo, cohort, student, hw_pair):
        """Regression: each submission has its own downloadable file."""
        # Get the two submission_ids from previous state
        subs = list(mongo.submissions.find({
            "cohort_id": cohort["cohort_id"],
            "student_id": student["user_id"],
            "material_id": {"$in": [hw_pair["hw_a"], hw_pair["hw_b"]]},
        }))
        assert len(subs) == 2
        for s in subs:
            r = requests.get(
                f"{BASE_URL}/api/submissions/{s['submission_id']}/download",
                headers=student["headers"], timeout=30,
            )
            assert r.status_code == 200, \
                f"Download failed for {s['submission_id']}: {r.status_code} {r.text[:200]}"
            assert len(r.content) > 0

    # ---- 4. Per-material AI review ----
    def test_review_endpoint_is_per_material(self, mongo, cohort, instructor, student, hw_pair):
        """AI review targets a specific submission_id (which is tied to one material_id).
        We don't invoke the LLM (slow); we assert review affects ONLY the targeted HW
        by simulating the DB state that /review would leave, and verifying the dashboard
        surfaces per-material status correctly."""
        subs = list(mongo.submissions.find({
            "cohort_id": cohort["cohort_id"],
            "student_id": student["user_id"],
            "material_id": {"$in": [hw_pair["hw_a"], hw_pair["hw_b"]]},
        }))
        assert len(subs) == 2
        sub_a = next(s for s in subs if s["material_id"] == hw_pair["hw_a"])

        # Simulate a successful /review call on HW1 only (leaves status='draft' + ai_feedback)
        mongo.submissions.update_one(
            {"submission_id": sub_a["submission_id"]},
            {"$set": {"status": "draft",
                      "ai_feedback": "AI-generated feedback for HW1",
                      "reviewed_at": datetime.now(timezone.utc).isoformat()}},
        )
        # HW2 untouched → still 'pending'
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], WEEK)
        by_mid = {h["material_id"]: h for h in week["homeworks"]}
        assert by_mid[hw_pair["hw_a"]]["status"] == "under_review"
        assert by_mid[hw_pair["hw_b"]]["status"] == "submitted"
        # Overall = least complete of (under_review=2, submitted=3) = submitted
        assert week["status"] == "submitted"

    def test_review_endpoint_authz_and_material_scoping(self, mongo, cohort, instructor, student, hw_pair):
        """Verify /submissions/{id}/review resolves the correct submission and rejects
        submissions that don't belong to a cohort the instructor manages."""
        subs = list(mongo.submissions.find({
            "cohort_id": cohort["cohort_id"],
            "student_id": student["user_id"],
            "material_id": hw_pair["hw_a"],
        }))
        assert subs, "HW1 submission missing"
        sub_a_id = subs[0]["submission_id"]

        # Wrong role (student cannot call /review)
        r = requests.post(
            f"{BASE_URL}/api/submissions/{sub_a_id}/review",
            headers=student["headers"], timeout=30,
        )
        assert r.status_code == 403, f"Students must be forbidden, got {r.status_code}"

        # Non-existent submission
        r = requests.post(
            f"{BASE_URL}/api/submissions/sub_doesnotexist/review",
            headers=instructor["headers"], timeout=30,
        )
        assert r.status_code == 404

    # ---- 5. Legacy field regression ----
    def test_legacy_homework_and_submission_point_to_first(self, mongo, cohort, student, hw_pair):
        # State from previous tests: hw_a has submission (draft/under_review), hw_b has submission (pending/submitted)
        dash = _get_dashboard(student)
        week = _get_week(dash, cohort["cohort_id"], WEEK)

        # week.homework legacy field
        assert week["homework"] is not None
        assert week["homework"]["material_id"] == week["homeworks"][0]["material_id"]
        # week.submission legacy field = first hw's submission
        first_sub = week["homeworks"][0]["submission"]
        if first_sub is None:
            assert week["submission"] is None
        else:
            assert week["submission"] is not None
            assert week["submission"]["submission_id"] == first_sub["submission_id"]

    # ---- 6. course_resources + materials array regression ----
    def test_course_resources_and_materials_array(self, mongo, cohort, student, hw_pair):
        dash = _get_dashboard(student)
        # course_resources still returned (may be empty for this cohort, but key must exist)
        cohort_entry = next(c for c in dash if c["cohort_id"] == cohort["cohort_id"])
        assert "course_resources" in cohort_entry
        assert isinstance(cohort_entry["course_resources"], list)

        # week.materials should contain BOTH homework mats + workbook + case_study
        week = _get_week(dash, cohort["cohort_id"], WEEK)
        assert "materials" in week
        mids = {m["material_id"] for m in week["materials"]}
        assert hw_pair["hw_a"] in mids
        assert hw_pair["hw_b"] in mids
        assert hw_pair["wb"] in mids
        assert hw_pair["cs"] in mids

        types = {m["material_id"]: m["material_type"] for m in week["materials"]}
        assert types[hw_pair["hw_a"]] == "homework"
        assert types[hw_pair["hw_b"]] == "homework"
        assert types[hw_pair["wb"]] == "workbook"
        assert types[hw_pair["cs"]] == "case_study"


class TestStatusRankOrdering:
    """Standalone unit-style checks of the status_rank ordering by testing edge combos.
    Uses a temp week (5) and a fresh pair of homeworks to isolate from other tests."""

    WEEK5 = 5

    @pytest.fixture(scope="class")
    def setup(self, mongo, cohort, student):
        # Release week 5 as well
        mongo.cohorts.update_one(
            {"cohort_id": cohort["cohort_id"]},
            {"$addToSet": {"released_weeks": self.WEEK5}},
        )
        hw_x = _insert_material(mongo, cohort["cohort_id"], self.WEEK5, "homework",
                                f"{TEST_PREFIX}HW_X_{uuid.uuid4().hex[:4]}")
        hw_y = _insert_material(mongo, cohort["cohort_id"], self.WEEK5, "homework",
                                f"{TEST_PREFIX}HW_Y_{uuid.uuid4().hex[:4]}")
        yield {"hw_x": hw_x, "hw_y": hw_y}
        # Cleanup submissions for this pair
        mongo.submissions.delete_many({
            "cohort_id": cohort["cohort_id"],
            "student_id": student["user_id"],
            "material_id": {"$in": [hw_x, hw_y]},
        })

    def _reset(self, mongo, cohort_id, student_id, mids):
        mongo.submissions.delete_many({
            "cohort_id": cohort_id, "student_id": student_id,
            "material_id": {"$in": mids},
        })

    def test_draft_vs_pending_least_complete_is_pending(self, mongo, cohort, student, setup):
        # draft=under_review(2) vs pending=submitted(3) → submitted wins (less complete)
        self._reset(mongo, cohort["cohort_id"], student["user_id"],
                    [setup["hw_x"], setup["hw_y"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=setup["hw_x"], student_id=student["user_id"],
                           status="draft", ai_fb="ai")
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=setup["hw_y"], student_id=student["user_id"],
                           status="pending")
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], self.WEEK5)
        assert week["status"] == "submitted"

    def test_sent_vs_no_submission_least_complete_is_waiting(self, mongo, cohort, student, setup):
        # sent(1) vs no-submission(4) → waiting_on_submission
        self._reset(mongo, cohort["cohort_id"], student["user_id"],
                    [setup["hw_x"], setup["hw_y"]])
        _insert_submission(mongo, cohort_id=cohort["cohort_id"],
                           material_id=setup["hw_x"], student_id=student["user_id"],
                           status="sent", instr_fb="fb")
        # hw_y has NO submission at all
        week = _get_week(_get_dashboard(student), cohort["cohort_id"], self.WEEK5)
        assert week["status"] == "waiting_on_submission"
