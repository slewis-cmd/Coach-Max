"""
Backend test suite for Rubric Library CRUD.

Covers:
- GET /api/rubrics returns list with can_edit flag.
- POST /api/rubrics validates name and content.
- PUT /api/rubrics/{id}: ACL — creator OK, non-creator instructor 403, super_admin OK.
- DELETE /api/rubrics/{id}: creator OK, non-creator 403, unknown 404.
- Regression: existing feedback_template endpoints (POST materials, PUT feedback-template).

All seeded docs are prefixed TEST_RUB_ and cleaned up in teardown.
"""

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

mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

TEST_PREFIX = "TEST_RUB_"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_pdf() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture(scope="module")
def seed():
    ts = int(datetime.now().timestamp())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    ids = {
        "super_admin":   f"{TEST_PREFIX}sa_{ts}",
        "inst_creator":  f"{TEST_PREFIX}ic_{ts}",
        "inst_other":    f"{TEST_PREFIX}io_{ts}",
        "cohort":        f"{TEST_PREFIX}coh_{ts}",
    }
    tokens = {
        "super_admin":   f"{TEST_PREFIX}tok_sa_{ts}",
        "inst_creator":  f"{TEST_PREFIX}tok_ic_{ts}",
        "inst_other":    f"{TEST_PREFIX}tok_io_{ts}",
    }
    now_iso = datetime.now(timezone.utc).isoformat()

    db.users.insert_many([
        {"user_id": ids["super_admin"], "email": f"{TEST_PREFIX}sa_{ts}@x.com",
         "name": "Test Admin", "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["inst_creator"], "email": f"{TEST_PREFIX}ic_{ts}@x.com",
         "name": "Rubric Creator", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["inst_other"], "email": f"{TEST_PREFIX}io_{ts}@x.com",
         "name": "Other Instructor", "role": "instructor", "created_at": now_iso},
    ])
    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": tok,
         "expires_at": expires_at, "created_at": now_iso}
        for uid, tok in [
            (ids["super_admin"], tokens["super_admin"]),
            (ids["inst_creator"], tokens["inst_creator"]),
            (ids["inst_other"], tokens["inst_other"]),
        ]
    ])
    db.cohorts.insert_one({
        "cohort_id": ids["cohort"],
        "name": f"{TEST_PREFIX}C_{ts}",
        "instructor_id": ids["inst_creator"],
        "instructor_ids": [ids["inst_creator"]],
        "student_ids": [],
        "released_weeks": [3],
        "created_at": now_iso,
    })

    yield {"ids": ids, "tokens": tokens}

    # Teardown
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.rubrics.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})


# ================================================================
# Initial state: authenticated instructor gets empty or list w/ can_edit
# ================================================================
class TestRubricsListInitial:
    def test_list_returns_array_with_can_edit_flag(self, seed):
        # Clean up any leftover rubrics from our test prefix
        db.rubrics.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
        r = requests.get(f"{BASE_URL}/api/rubrics", headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        # All items must include can_edit flag if any exist
        for item in data:
            assert "can_edit" in item
            assert isinstance(item["can_edit"], bool)

    def test_list_unauthorized_no_token(self, seed):
        r = requests.get(f"{BASE_URL}/api/rubrics", timeout=15)
        assert r.status_code in (401, 403)


# ================================================================
# Create
# ================================================================
class TestRubricCreate:
    def test_create_success(self, seed):
        payload = {
            "name": f"{TEST_PREFIX}Kawasaki_{uuid.uuid4().hex[:6]}",
            "content": "Compare submission to the Kawasaki Model on slide 4. 2 wins, 2 gaps.",
            "description": "Kawasaki case week 3",
        }
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload,
                          headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rubric_id" in data
        assert data["name"] == payload["name"]
        assert data["content"] == payload["content"]
        assert data["description"] == payload["description"]
        assert data["can_edit"] is True
        assert data["created_by"] == seed["ids"]["inst_creator"]

        # Verify persistence via GET
        list_r = requests.get(f"{BASE_URL}/api/rubrics",
                              headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert list_r.status_code == 200
        found = [x for x in list_r.json() if x["rubric_id"] == data["rubric_id"]]
        assert len(found) == 1
        assert found[0]["can_edit"] is True

    def test_create_missing_name(self, seed):
        payload = {"name": "", "content": "some content"}
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload,
                          headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 400, r.text

    def test_create_missing_content(self, seed):
        payload = {"name": f"{TEST_PREFIX}NoContent", "content": ""}
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload,
                          headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 400, r.text

    def test_create_missing_name_field(self, seed):
        # Pydantic-level validation (no name key at all)
        r = requests.post(f"{BASE_URL}/api/rubrics", json={"content": "x"},
                          headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code in (400, 422), r.text


# ================================================================
# Update / ACL
# ================================================================
class TestRubricUpdate:
    def _make(self, seed, token, suffix="upd"):
        payload = {
            "name": f"{TEST_PREFIX}{suffix}_{uuid.uuid4().hex[:6]}",
            "content": "orig content",
            "description": "orig desc",
        }
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload, headers=_auth(token), timeout=15)
        assert r.status_code == 200, r.text
        return r.json()

    def test_creator_can_update(self, seed):
        original = self._make(seed, seed["tokens"]["inst_creator"])
        original_updated_at = original["updated_at"]

        # Ensure timestamp actually differs
        time.sleep(1.1)

        new_payload = {
            "name": original["name"] + "_v2",
            "content": "new content",
            "description": "new desc",
        }
        r = requests.put(f"{BASE_URL}/api/rubrics/{original['rubric_id']}",
                         json=new_payload, headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["name"] == new_payload["name"]
        assert updated["content"] == new_payload["content"]
        assert updated["description"] == new_payload["description"]
        assert updated["can_edit"] is True
        # updated_at must move forward
        assert updated["updated_at"] > original_updated_at, \
            f"updated_at did not advance: {original_updated_at} -> {updated['updated_at']}"

    def test_non_creator_instructor_cannot_update(self, seed):
        original = self._make(seed, seed["tokens"]["inst_creator"], suffix="acl403")
        r = requests.put(f"{BASE_URL}/api/rubrics/{original['rubric_id']}",
                         json={"name": "hacked", "content": "hacked"},
                         headers=_auth(seed["tokens"]["inst_other"]), timeout=15)
        assert r.status_code == 403, r.text

    def test_super_admin_can_update_others_rubric(self, seed):
        original = self._make(seed, seed["tokens"]["inst_creator"], suffix="acladmin")
        r = requests.put(f"{BASE_URL}/api/rubrics/{original['rubric_id']}",
                         json={"name": original["name"] + "_admin", "content": "admin edit"},
                         headers=_auth(seed["tokens"]["super_admin"]), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "admin edit"

    def test_update_unknown_returns_404(self, seed):
        r = requests.put(f"{BASE_URL}/api/rubrics/does_not_exist_xyz",
                         json={"name": "x", "content": "y"},
                         headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 404, r.text


# ================================================================
# Delete / ACL
# ================================================================
class TestRubricDelete:
    def _make(self, token, suffix="del"):
        payload = {
            "name": f"{TEST_PREFIX}{suffix}_{uuid.uuid4().hex[:6]}",
            "content": "to be deleted",
        }
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload, headers=_auth(token), timeout=15)
        assert r.status_code == 200
        return r.json()

    def test_creator_can_delete(self, seed):
        rub = self._make(seed["tokens"]["inst_creator"])
        r = requests.delete(f"{BASE_URL}/api/rubrics/{rub['rubric_id']}",
                            headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 200, r.text

        # Verify it no longer appears
        list_r = requests.get(f"{BASE_URL}/api/rubrics",
                              headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        ids = [x["rubric_id"] for x in list_r.json()]
        assert rub["rubric_id"] not in ids

    def test_non_creator_instructor_cannot_delete(self, seed):
        rub = self._make(seed["tokens"]["inst_creator"], suffix="del403")
        r = requests.delete(f"{BASE_URL}/api/rubrics/{rub['rubric_id']}",
                            headers=_auth(seed["tokens"]["inst_other"]), timeout=15)
        assert r.status_code == 403, r.text
        # Still there
        list_r = requests.get(f"{BASE_URL}/api/rubrics",
                              headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert any(x["rubric_id"] == rub["rubric_id"] for x in list_r.json())

    def test_delete_unknown_returns_404(self, seed):
        r = requests.delete(f"{BASE_URL}/api/rubrics/rub_bogus_xyz",
                            headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        assert r.status_code == 404, r.text

    def test_super_admin_can_delete_others_rubric(self, seed):
        rub = self._make(seed["tokens"]["inst_creator"], suffix="delAdmin")
        r = requests.delete(f"{BASE_URL}/api/rubrics/{rub['rubric_id']}",
                            headers=_auth(seed["tokens"]["super_admin"]), timeout=15)
        assert r.status_code == 200, r.text


# ================================================================
# can_edit correctness across users
# ================================================================
class TestRubricCanEditFlag:
    def test_can_edit_true_for_creator_false_for_other(self, seed):
        payload = {
            "name": f"{TEST_PREFIX}canedit_{uuid.uuid4().hex[:6]}",
            "content": "abc",
        }
        r = requests.post(f"{BASE_URL}/api/rubrics", json=payload,
                          headers=_auth(seed["tokens"]["inst_creator"]), timeout=15)
        rub_id = r.json()["rubric_id"]

        # Creator sees can_edit=true
        lst_creator = requests.get(f"{BASE_URL}/api/rubrics",
                                   headers=_auth(seed["tokens"]["inst_creator"]), timeout=15).json()
        item = next(x for x in lst_creator if x["rubric_id"] == rub_id)
        assert item["can_edit"] is True

        # Other instructor sees can_edit=false
        lst_other = requests.get(f"{BASE_URL}/api/rubrics",
                                 headers=_auth(seed["tokens"]["inst_other"]), timeout=15).json()
        item = next(x for x in lst_other if x["rubric_id"] == rub_id)
        assert item["can_edit"] is False

        # Super admin sees can_edit=true
        lst_admin = requests.get(f"{BASE_URL}/api/rubrics",
                                 headers=_auth(seed["tokens"]["super_admin"]), timeout=15).json()
        item = next(x for x in lst_admin if x["rubric_id"] == rub_id)
        assert item["can_edit"] is True


# ================================================================
# Regression: feedback_template feature still works
# ================================================================
class TestFeedbackTemplateRegression:
    def test_cohort_homework_upload_with_feedback_template(self, seed):
        tpl = "Focus on Kawasaki model comparison. 2 wins, 2 gaps."
        title = f"{TEST_PREFIX}HW_reg_{uuid.uuid4().hex[:6]}"
        params = {
            "week_number": 3,
            "material_type": "homework",
            "title": title,
            "description": "",
            "feedback_template": tpl,
        }
        files = {"file": (f"{title}.pdf", _tiny_pdf(), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{seed['ids']['cohort']}/materials",
            params=params, files=files,
            headers=_auth(seed["tokens"]["inst_creator"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc.get("feedback_template") == tpl

        # PUT to update it
        r2 = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": "new instructions"},
            headers=_auth(seed["tokens"]["inst_creator"]), timeout=15,
        )
        assert r2.status_code == 200, r2.text
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc.get("feedback_template") == "new instructions"

        # Clear back to default
        r3 = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": ""},
            headers=_auth(seed["tokens"]["inst_creator"]), timeout=15,
        )
        assert r3.status_code == 200, r3.text
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert (doc.get("feedback_template") or "") == ""
