"""
Iteration 41 - Milestone title generation + regenerate back-fill endpoint.

Covers:
- _default_milestone_title / MILESTONE_TITLE_MAP correctness via new-cohort auto-seed
  (indirect test — creating a cohort exercises _make_milestone / _build_default_milestones)
- POST /api/admin/regenerate-milestone-titles:
    * 401 without auth
    * 403 for non-super-admin (instructor)
    * Renames milestones matching literal 'Week N' or 'Week N — Final Deck'
    * Leaves custom titles alone (e.g., 'Slides 1-2')
    * Idempotent — second run returns milestones_renamed=0

All seeded docs prefixed TEST_MT_.
"""
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

mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

TEST_PREFIX = "TEST_MT_"


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
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids.keys()}

    db.users.insert_many([
        {"user_id": ids["sa"],         "email": f"{TEST_PREFIX}sa_{ts}@x.com",  "name": "Adm", "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i_{ts}@x.com",   "name": "Ins", "role": "instructor",  "created_at": now_iso},
    ])
    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": toks[k], "expires_at": expires_at, "created_at": now_iso}
        for k, uid in ids.items()
    ])

    yield {"ids": ids, "tokens": toks, "ts": ts}

    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
    db.assignments.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})


# ==============================================================
# 1) Curriculum-aware milestone titles via new cohort auto-seed
# ==============================================================
class TestNewCohortMilestoneTitles:
    """Creating a cohort auto-seeds the 4 defaults; each milestone should have
    the curriculum-aware title from MILESTONE_TITLE_MAP."""

    @pytest.fixture(scope="class")
    def cohort_with_defaults(self, seed):
        # Use API to create cohort (triggers _seed_default_assignments_for_cohort)
        name = f"{TEST_PREFIX}C_{uuid.uuid4().hex[:6]}"
        r = requests.post(
            f"{BASE_URL}/api/cohorts",
            json={"name": name, "description": "iter41 titles"},
            headers=_auth(seed["tokens"]["sa"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        cid = r.json()["cohort_id"]

        # Fetch assignments
        r2 = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["sa"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        asgn = r2.json()
        by_key = {a["assignment_key"]: a for a in asgn}
        return {"cohort_id": cid, "by_key": by_key}

    def test_four_defaults_seeded(self, cohort_with_defaults):
        by_key = cohort_with_defaults["by_key"]
        assert set(by_key.keys()) == {
            "60_second_pitch", "10_slide_pitch", "case_activity", "business_questionnaire"
        }

    def test_60_second_pitch_week1_title(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["60_second_pitch"]
        ms = next(m for m in a["milestones"] if m["week_number"] == 1)
        assert ms["title"] == "Week 1 — First Draft: The Hook"

    def test_60_second_pitch_week3_title(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["60_second_pitch"]
        ms = next(m for m in a["milestones"] if m["week_number"] == 3)
        assert ms["title"] == "Week 3 — Nail the Solution"

    def test_10_slide_pitch_week2_title(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["10_slide_pitch"]
        ms = next(m for m in a["milestones"] if m["week_number"] == 2)
        assert ms["title"] == "Week 2 — Slide 2: Problem"

    def test_10_slide_pitch_final_capstone(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["10_slide_pitch"]
        ms14 = next(m for m in a["milestones"] if m["week_number"] == 14)
        assert ms14["is_final_capstone"] is True
        assert ms14["title"] == "Week 14 — Final Consolidated Deck"

    def test_case_activity_week3_title(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["case_activity"]
        ms = next(m for m in a["milestones"] if m["week_number"] == 3)
        assert ms["title"] == "Week 3 — Root Cause Diagnosis"

    def test_business_questionnaire_week1_title(self, cohort_with_defaults):
        a = cohort_with_defaults["by_key"]["business_questionnaire"]
        ms = next(m for m in a["milestones"] if m["week_number"] == 1)
        assert ms["title"] == "Week 1 — Business Foundations"

    def test_all_14_weeks_present_and_non_default(self, cohort_with_defaults):
        """None of the 14 default weeks should still be the literal 'Week N' fallback."""
        import re
        stale_pat = re.compile(r"^Week \d+$")
        for key in ("60_second_pitch", "10_slide_pitch", "case_activity", "business_questionnaire"):
            a = cohort_with_defaults["by_key"][key]
            assert len(a["milestones"]) == 14
            for m in a["milestones"]:
                assert not stale_pat.match(m["title"]), \
                    f"{key} week {m['week_number']} still stale: {m['title']}"


# ==============================================================
# 2) Auth / RBAC on regenerate endpoint
# ==============================================================
class TestRegenerateEndpointAuth:
    def test_no_auth_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/admin/regenerate-milestone-titles", timeout=10)
        assert r.status_code == 401, r.text

    def test_instructor_returns_403(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/admin/regenerate-milestone-titles",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 403, r.text

    def test_super_admin_succeeds(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/admin/regenerate-milestone-titles",
            headers=_auth(seed["tokens"]["sa"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "assignments_scanned" in body
        assert "milestones_renamed" in body
        assert isinstance(body["assignments_scanned"], int)
        assert isinstance(body["milestones_renamed"], int)


# ==============================================================
# 3) Regenerate rename behaviour
# ==============================================================
class TestRegenerateRenameBehavior:
    """Seed an assignment with stale 'Week N' + one custom title, call
    the endpoint, and verify:
      - Stale titles get replaced with curriculum-aware defaults
      - Custom titles are preserved
      - Second call returns milestones_renamed=0 (idempotent)
    """

    @pytest.fixture(scope="class")
    def stale_assignment(self, seed):
        cid = f"{TEST_PREFIX}c_{uuid.uuid4().hex[:8]}"
        aid = f"{TEST_PREFIX}a_{uuid.uuid4().hex[:8]}"
        db.cohorts.insert_one({
            "cohort_id": cid,
            "name": f"{TEST_PREFIX}stale_{uuid.uuid4().hex[:4]}",
            "instructor_id": seed["ids"]["instructor"],
            "instructor_ids": [seed["ids"]["instructor"]],
            "student_ids": [],
            "total_weeks": 14,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        milestones = [
            {
                "milestone_id": f"ms_stale_{i}_{uuid.uuid4().hex[:6]}",
                "week_number": i,
                "title": (
                    "Slides 1-2 (custom)" if i == 5      # custom, preserve
                    else "Week 14 — Final Deck" if i == 14  # legacy capstone label
                    else f"Week {i}"                    # stale
                ),
                "description": "",
                "feedback_template_override": "",
                "drive_folder_url_override": "",
                "is_final_capstone": (i == 14),
                "due_date": None,
            }
            for i in range(1, 15)
        ]
        db.assignments.insert_one({
            "assignment_id": aid,
            "cohort_id": cid,
            "assignment_key": "10_slide_pitch",
            "title": "Kawasaki 10-Slide Pitch Deck",
            "description": "",
            "submission_type": "10_slide_pitch",
            "milestones": milestones,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"cohort_id": cid, "assignment_id": aid}

    def test_first_run_renames_stale_titles(self, seed, stale_assignment):
        aid = stale_assignment["assignment_id"]
        r = requests.post(
            f"{BASE_URL}/api/admin/regenerate-milestone-titles",
            headers=_auth(seed["tokens"]["sa"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # 12 stale ("Week N" weeks 1-4,6-13) + 1 legacy ("Week 14 — Final Deck") = 13
        assert body["milestones_renamed"] >= 13

        # Verify db state
        a = db.assignments.find_one({"assignment_id": aid})
        ms_by_week = {m["week_number"]: m for m in a["milestones"]}
        # Week 1 should now be curriculum-aware
        assert ms_by_week[1]["title"] == "Week 1 — Slide 1: Title & Vision"
        # Week 2
        assert ms_by_week[2]["title"] == "Week 2 — Slide 2: Problem"
        # Custom title preserved
        assert ms_by_week[5]["title"] == "Slides 1-2 (custom)"
        # Legacy 'Week 14 — Final Deck' should have been rewritten
        assert ms_by_week[14]["title"] == "Week 14 — Final Consolidated Deck"

    def test_second_run_is_idempotent(self, seed, stale_assignment):
        # First run already happened in previous test — capture the state, run again,
        # and confirm milestones_renamed for THIS assignment is 0.
        aid = stale_assignment["assignment_id"]
        before = db.assignments.find_one({"assignment_id": aid})
        titles_before = [m["title"] for m in before["milestones"]]

        r = requests.post(
            f"{BASE_URL}/api/admin/regenerate-milestone-titles",
            headers=_auth(seed["tokens"]["sa"]), timeout=30,
        )
        assert r.status_code == 200, r.text

        after = db.assignments.find_one({"assignment_id": aid})
        titles_after = [m["title"] for m in after["milestones"]]
        assert titles_before == titles_after, "Titles must not change on second run"

    def test_custom_title_never_overwritten(self, seed, stale_assignment):
        """Explicit verification that any milestone title not matching the
        stale pattern is left untouched even after multiple runs."""
        aid = stale_assignment["assignment_id"]
        # Set another custom title mid-way
        db.assignments.update_one(
            {"assignment_id": aid, "milestones.week_number": 7},
            {"$set": {"milestones.$.title": "My Custom Week 7 Story"}}
        )
        r = requests.post(
            f"{BASE_URL}/api/admin/regenerate-milestone-titles",
            headers=_auth(seed["tokens"]["sa"]), timeout=30,
        )
        assert r.status_code == 200
        a = db.assignments.find_one({"assignment_id": aid})
        ms7 = next(m for m in a["milestones"] if m["week_number"] == 7)
        assert ms7["title"] == "My Custom Week 7 Story"
