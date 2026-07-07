"""
Iteration 39 - Backend test suite for Assignment Template Library.

Covers:
- GET /api/assignment-templates (empty init + can_edit flag)
- POST /api/assignment-templates (validation, milestone normalization)
- POST /api/assignment-templates/from-assignment/{assignment_id} (snapshot)
- PUT /api/assignment-templates/{id} (author + super_admin edit; others 403)
- DELETE /api/assignment-templates/{id} (author-only; others 403)
- POST /api/cohorts/{cohort_id}/assignments/from-template/{template_id}
    * default week_map=null clones original weeks
    * week_map remaps a milestone
    * week_map null value SKIPS a milestone
    * replace_existing_by_type=True overwrites in place (assignment_id preserved)
    * title_override changes title
    * 404 on missing template / cohort; 403 for non-manager instructor

All seeded docs prefixed TEST_TPL_.
"""
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

TEST_PREFIX = "TEST_TPL_"


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
        "other_ins":  f"{TEST_PREFIX}i2_{ts}",
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids.keys()}

    db.users.insert_many([
        {"user_id": ids["sa"],         "email": f"{TEST_PREFIX}sa_{ts}@x.com", "name": "Adm",  "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i_{ts}@x.com",  "name": "Ins1", "role": "instructor",  "created_at": now_iso},
        {"user_id": ids["other_ins"],  "email": f"{TEST_PREFIX}i2_{ts}@x.com", "name": "Ins2", "role": "instructor",  "created_at": now_iso},
    ])
    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": toks[k], "expires_at": expires_at, "created_at": now_iso}
        for k, uid in ids.items()
    ])

    yield {"ids": ids, "tokens": toks, "ts": ts}

    # Cleanup - be thorough
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
    db.assignments.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.assignment_templates.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})


def _create_cohort(token, name_suffix=""):
    name = f"{TEST_PREFIX}C_{name_suffix}_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/cohorts",
        json={"name": name, "description": "iter39 test cohort"},
        headers=_auth(token), timeout=15,
    )
    assert r.status_code == 200, f"create_cohort failed: {r.status_code} {r.text}"
    return r.json()["cohort_id"]


def _sample_milestones(count=3):
    return [
        {"week_number": i + 1, "title": f"M{i+1}", "description": f"desc {i+1}",
         "is_final_capstone": (i == count - 1)}
        for i in range(count)
    ]


def _create_template(token, name_suffix="", submission_type="10_slide_pitch", milestones=None):
    payload = {
        "name": f"{TEST_PREFIX}Tpl_{name_suffix}_{uuid.uuid4().hex[:5]}",
        "description": "test template",
        "submission_type": submission_type,
        "feedback_template": "Give balanced feedback...",
        "drive_folder_url": "",
        "milestones": milestones if milestones is not None else _sample_milestones(3),
    }
    r = requests.post(f"{BASE_URL}/api/assignment-templates", json=payload, headers=_auth(token), timeout=10)
    assert r.status_code == 200, f"create_template failed: {r.status_code} {r.text}"
    return r.json()


# ===================================================================
# 1) GET /api/assignment-templates
# ===================================================================
class TestListTemplates:
    def test_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/assignment-templates", timeout=10)
        assert r.status_code in (401, 403)

    def test_list_returns_array_and_can_edit_flag(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "listflag")
        tid = tpl["template_id"]

        # Author sees can_edit=True
        r1 = requests.get(f"{BASE_URL}/api/assignment-templates", headers=_auth(seed["tokens"]["instructor"]), timeout=10)
        assert r1.status_code == 200
        data1 = r1.json()
        assert isinstance(data1, list)
        mine = next((t for t in data1 if t["template_id"] == tid), None)
        assert mine is not None
        assert mine["can_edit"] is True

        # Other instructor sees can_edit=False
        r2 = requests.get(f"{BASE_URL}/api/assignment-templates", headers=_auth(seed["tokens"]["other_ins"]), timeout=10)
        assert r2.status_code == 200
        other = next((t for t in r2.json() if t["template_id"] == tid), None)
        assert other is not None
        assert other["can_edit"] is False

        # Super admin sees can_edit=True
        r3 = requests.get(f"{BASE_URL}/api/assignment-templates", headers=_auth(seed["tokens"]["sa"]), timeout=10)
        assert r3.status_code == 200
        sa_view = next((t for t in r3.json() if t["template_id"] == tid), None)
        assert sa_view is not None
        assert sa_view["can_edit"] is True


# ===================================================================
# 2) POST /api/assignment-templates
# ===================================================================
class TestCreateTemplate:
    def test_create_happy_path(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "happy", "10_slide_pitch")
        assert tpl["template_id"].startswith("tpl_")
        assert tpl["submission_type"] == "10_slide_pitch"
        assert tpl["created_by"] == seed["ids"]["instructor"]
        assert tpl["can_edit"] is True
        assert len(tpl["milestones"]) == 3
        # milestone_ids should be normalized/generated
        for m in tpl["milestones"]:
            assert m["milestone_id"].startswith("ms_")
            assert "week_number" in m
            assert isinstance(m["is_final_capstone"], bool)
        # last milestone (from _sample_milestones) has is_final_capstone=True
        assert tpl["milestones"][-1]["is_final_capstone"] is True

    def test_create_missing_name_400(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/assignment-templates",
            json={"name": "  ", "submission_type": "10_slide_pitch", "milestones": []},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 400

    def test_create_bad_submission_type_400(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/assignment-templates",
            json={"name": f"{TEST_PREFIX}bad", "submission_type": "not_a_type", "milestones": []},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 400

    def test_create_normalizes_milestone_ids(self, seed):
        # Client sends milestones without milestone_id — server should generate
        payload_ms = [
            {"week_number": 1, "title": "Week 1", "description": ""},
            {"week_number": 2, "title": "Week 2", "description": ""},
        ]
        tpl = _create_template(seed["tokens"]["instructor"], "norm", milestones=payload_ms)
        for m in tpl["milestones"]:
            assert m["milestone_id"].startswith("ms_")


# ===================================================================
# 3) POST /api/assignment-templates/from-assignment/{assignment_id}
# ===================================================================
class TestSaveAssignmentAsTemplate:
    def test_snapshot_assignment(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "fromasgn")
        # Pick the auto-seeded 60_second_pitch assignment
        r = requests.get(f"{BASE_URL}/api/cohorts/{cid}/assignments", headers=_auth(seed["tokens"]["instructor"]), timeout=10)
        assert r.status_code == 200
        asgns = r.json()
        pitch = next((a for a in asgns if a["submission_type"] == "60_second_pitch"), None)
        assert pitch is not None
        original_ms_count = len(pitch.get("milestones") or [])

        r2 = requests.post(
            f"{BASE_URL}/api/assignment-templates/from-assignment/{pitch['assignment_id']}",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r2.status_code == 200, r2.text
        tpl = r2.json()
        assert tpl["name"] == pitch["title"]
        assert tpl["submission_type"] == "60_second_pitch"
        assert len(tpl["milestones"]) == original_ms_count
        # Milestone shape preserved (ids may be preserved by _normalize_milestone_shape;
        # they'll be regenerated when the template is APPLIED to a cohort)
        for m in tpl["milestones"]:
            assert m["milestone_id"].startswith("ms_")
            assert isinstance(m["is_final_capstone"], bool)

    def test_snapshot_403_for_non_manager(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "fromasgn403")
        r = requests.get(f"{BASE_URL}/api/cohorts/{cid}/assignments", headers=_auth(seed["tokens"]["instructor"]), timeout=10)
        pitch = next((a for a in r.json() if a["submission_type"] == "60_second_pitch"), None)
        r2 = requests.post(
            f"{BASE_URL}/api/assignment-templates/from-assignment/{pitch['assignment_id']}",
            headers=_auth(seed["tokens"]["other_ins"]), timeout=10,
        )
        assert r2.status_code == 403

    def test_snapshot_super_admin_ok(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "fromasgn_sa")
        r = requests.get(f"{BASE_URL}/api/cohorts/{cid}/assignments", headers=_auth(seed["tokens"]["instructor"]), timeout=10)
        pitch = next((a for a in r.json() if a["submission_type"] == "60_second_pitch"), None)
        r2 = requests.post(
            f"{BASE_URL}/api/assignment-templates/from-assignment/{pitch['assignment_id']}",
            headers=_auth(seed["tokens"]["sa"]), timeout=10,
        )
        assert r2.status_code == 200

    def test_snapshot_404_missing_assignment(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/assignment-templates/from-assignment/bogus_asgn_id",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 404


# ===================================================================
# 4) PUT /api/assignment-templates/{id}
# ===================================================================
class TestUpdateTemplate:
    def test_update_by_author(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "put1")
        r = requests.put(
            f"{BASE_URL}/api/assignment-templates/{tpl['template_id']}",
            json={"name": tpl["name"] + "_edited", "description": "updated"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["name"].endswith("_edited")
        # Verify in DB
        got = db.assignment_templates.find_one({"template_id": tpl["template_id"]}, {"_id": 0})
        assert got["description"] == "updated"

    def test_update_by_other_instructor_403(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "put2")
        r = requests.put(
            f"{BASE_URL}/api/assignment-templates/{tpl['template_id']}",
            json={"name": "hack"},
            headers=_auth(seed["tokens"]["other_ins"]), timeout=10,
        )
        assert r.status_code == 403

    def test_update_by_super_admin(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "put3")
        r = requests.put(
            f"{BASE_URL}/api/assignment-templates/{tpl['template_id']}",
            json={"description": "sa-edited"},
            headers=_auth(seed["tokens"]["sa"]), timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["description"] == "sa-edited"

    def test_update_404(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/assignment-templates/tpl_missing",
            json={"name": "x"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 404


# ===================================================================
# 5) DELETE /api/assignment-templates/{id}
# ===================================================================
class TestDeleteTemplate:
    def test_delete_by_author(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "del1")
        r = requests.delete(
            f"{BASE_URL}/api/assignment-templates/{tpl['template_id']}",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        assert db.assignment_templates.find_one({"template_id": tpl["template_id"]}) is None

    def test_delete_by_other_instructor_403(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "del2")
        r = requests.delete(
            f"{BASE_URL}/api/assignment-templates/{tpl['template_id']}",
            headers=_auth(seed["tokens"]["other_ins"]), timeout=10,
        )
        assert r.status_code == 403
        assert db.assignment_templates.find_one({"template_id": tpl["template_id"]}) is not None


# ===================================================================
# 6) POST /api/cohorts/{cohort_id}/assignments/from-template/{template_id}
# ===================================================================
class TestApplyTemplate:
    def test_apply_default_week_map_creates_new(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_new")
        # Use a NEW submission type not auto-seeded? All 4 are auto-seeded.
        # So we use business_questionnaire but with replace=False → creates additional
        # BUT default replace=False creates a new custom assignment.
        # Use custom milestones with distinct weeks so we can check ordering
        milestones = [
            {"week_number": 3, "title": "MA"},
            {"week_number": 7, "title": "MB"},
            {"week_number": 12, "title": "MC", "is_final_capstone": True},
        ]
        tpl = _create_template(seed["tokens"]["instructor"], "applynew", "10_slide_pitch", milestones)
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={},  # default: no remap, no replace
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["replaced"] is False
        assert data["milestones_count"] == 3
        assert "assignment_id" in data

        # Verify assignment in DB
        asgn = db.assignments.find_one({"assignment_id": data["assignment_id"]}, {"_id": 0})
        assert asgn is not None
        weeks = sorted([m["week_number"] for m in asgn["milestones"]])
        assert weeks == [3, 7, 12]
        # Verify fresh milestone ids (different from template's)
        tpl_ids = {m["milestone_id"] for m in tpl["milestones"]}
        new_ids = {m["milestone_id"] for m in asgn["milestones"]}
        assert tpl_ids.isdisjoint(new_ids)

    def test_apply_week_map_remaps(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_remap")
        milestones = [
            {"week_number": 1, "title": "M1"},
            {"week_number": 2, "title": "M2"},
            {"week_number": 3, "title": "M3"},
        ]
        tpl = _create_template(seed["tokens"]["instructor"], "remap", "10_slide_pitch", milestones)
        # Remap M2 (template's ms) to week 5
        m2 = tpl["milestones"][1]
        week_map = {m2["milestone_id"]: 5}
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={"week_map": week_map},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["milestones_count"] == 3
        asgn = db.assignments.find_one({"assignment_id": data["assignment_id"]}, {"_id": 0})
        weeks_by_title = {m["title"]: m["week_number"] for m in asgn["milestones"]}
        assert weeks_by_title["M1"] == 1
        assert weeks_by_title["M2"] == 5
        assert weeks_by_title["M3"] == 3

    def test_apply_week_map_null_skips(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_skip")
        milestones = [
            {"week_number": 1, "title": "SkipMe"},
            {"week_number": 2, "title": "KeepMe"},
        ]
        tpl = _create_template(seed["tokens"]["instructor"], "skip", "10_slide_pitch", milestones)
        skip_id = tpl["milestones"][0]["milestone_id"]
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={"week_map": {skip_id: None}},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["milestones_count"] == 1
        asgn = db.assignments.find_one({"assignment_id": data["assignment_id"]}, {"_id": 0})
        titles = [m["title"] for m in asgn["milestones"]]
        assert titles == ["KeepMe"]

    def test_apply_replace_existing_by_type(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_replace")
        # Get auto-seeded 60_second_pitch assignment
        r0 = requests.get(f"{BASE_URL}/api/cohorts/{cid}/assignments", headers=_auth(seed["tokens"]["instructor"]), timeout=10)
        pitch = next((a for a in r0.json() if a["submission_type"] == "60_second_pitch"), None)
        assert pitch is not None
        original_aid = pitch["assignment_id"]
        original_ms_count = len(pitch["milestones"])

        # Seed a fake submission linked to the original assignment to verify linkage preserved
        db.submissions.insert_one({
            "submission_id": f"{TEST_PREFIX}sub_{uuid.uuid4().hex[:8]}",
            "assignment_id": original_aid,
            "cohort_id": cid,
            "student_id": "does_not_matter",
            "file_name": f"{TEST_PREFIX}fake.pdf",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # Build template with matching submission_type but very different milestones
        milestones = [
            {"week_number": 4, "title": "NewA"},
            {"week_number": 8, "title": "NewB", "is_final_capstone": True},
        ]
        tpl = _create_template(seed["tokens"]["instructor"], "replace", "60_second_pitch", milestones)
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={"replace_existing_by_type": True, "title_override": f"{TEST_PREFIX}Renamed Pitch"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["replaced"] is True
        assert data["assignment_id"] == original_aid  # PRESERVED
        assert data["milestones_count"] == 2

        # Reload assignment from DB
        updated = db.assignments.find_one({"assignment_id": original_aid}, {"_id": 0})
        assert updated["title"] == f"{TEST_PREFIX}Renamed Pitch"
        assert len(updated["milestones"]) == 2
        assert original_ms_count != len(updated["milestones"])
        titles = sorted([m["title"] for m in updated["milestones"]])
        assert titles == ["NewA", "NewB"]

        # Submission linkage preserved
        sub = db.submissions.find_one({"assignment_id": original_aid, "file_name": {"$regex": f"^{TEST_PREFIX}"}})
        assert sub is not None

        # Cleanup submission
        db.submissions.delete_many({"file_name": {"$regex": f"^{TEST_PREFIX}"}})

    def test_apply_title_override(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_title")
        tpl = _create_template(seed["tokens"]["instructor"], "titl", "10_slide_pitch")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={"title_override": f"{TEST_PREFIX}Custom Name"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        asgn = db.assignments.find_one({"assignment_id": data["assignment_id"]}, {"_id": 0})
        assert asgn["title"] == f"{TEST_PREFIX}Custom Name"

    def test_apply_404_missing_template(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_404t")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/tpl_missing",
            json={},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 404

    def test_apply_404_missing_cohort(self, seed):
        tpl = _create_template(seed["tokens"]["instructor"], "apply_404c", "10_slide_pitch")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/bogus_cohort_id/assignments/from-template/{tpl['template_id']}",
            json={},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 404

    def test_apply_403_non_manager(self, seed):
        cid = _create_cohort(seed["tokens"]["instructor"], "apply_403")
        tpl = _create_template(seed["tokens"]["other_ins"], "apply_403tpl", "10_slide_pitch")
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments/from-template/{tpl['template_id']}",
            json={},
            headers=_auth(seed["tokens"]["other_ins"]), timeout=10,
        )
        assert r.status_code == 403
