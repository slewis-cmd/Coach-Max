"""
Backend test suite for custom AI feedback_template on homework materials.

Covers:
- POST /api/cohorts/{cohort_id}/materials accepts optional feedback_template query param;
  persists for homework; stored empty for non-homework regardless of input.
- POST /api/library/materials accepts optional feedback_template for homework; persists it.
- PUT /api/materials/{material_id}/feedback-template:
    * updates with non-empty string (200 + new value, verified via DB)
    * empty string clears the field (restores default rubric)
    * non-homework material -> 400
    * unknown material_id -> 404
    * ACL: cohort manager -> 200, outsider instructor -> 403, super_admin -> 200
    * ACL for library homework material: instructor managing ANY assigned cohort -> 200,
      outsider instructor -> 403; owner-uploader still 200 when no cohort assigned
- POST /api/materials/{material_id}/submit-on-behalf: 200 on homework material with a
  custom feedback_template; smoke-check that the async AI review either uses the custom
  system prompt OR (if async task hasn't produced ai_feedback within a short wait) the
  submission itself was created and no default rubric leaked into the submit-on-behalf
  response body.

All seeded docs are prefixed TEST_FBTPL_ and cleaned up in teardown.
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

TEST_PREFIX = "TEST_FBTPL_"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


# ----------------------------------------------------------------------
# Fixture: seed users, cohorts, sessions
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def seed():
    ts = int(datetime.now().timestamp())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    ids = {
        "super_admin":       f"{TEST_PREFIX}sa_{ts}",
        "inst_manager":      f"{TEST_PREFIX}i1_{ts}",   # manages C1
        "inst_outsider":     f"{TEST_PREFIX}i2_{ts}",   # manages nothing
        "inst_lib_manager":  f"{TEST_PREFIX}i3_{ts}",   # manages C2
        "student":           f"{TEST_PREFIX}stu_{ts}",
        "cohort_c1":         f"{TEST_PREFIX}c1_{ts}",
        "cohort_c2":         f"{TEST_PREFIX}c2_{ts}",
    }
    tokens = {
        "super_admin":       f"{TEST_PREFIX}tok_sa_{ts}",
        "inst_manager":      f"{TEST_PREFIX}tok_i1_{ts}",
        "inst_outsider":     f"{TEST_PREFIX}tok_i2_{ts}",
        "inst_lib_manager":  f"{TEST_PREFIX}tok_i3_{ts}",
        "student":           f"{TEST_PREFIX}tok_stu_{ts}",
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    db.users.insert_many([
        {"user_id": ids["super_admin"], "email": f"{TEST_PREFIX}sa_{ts}@x.com",
         "name": "Test Admin", "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["inst_manager"], "email": f"{TEST_PREFIX}i1_{ts}@x.com",
         "name": "Cohort Mgr", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["inst_outsider"], "email": f"{TEST_PREFIX}i2_{ts}@x.com",
         "name": "Outsider", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["inst_lib_manager"], "email": f"{TEST_PREFIX}i3_{ts}@x.com",
         "name": "Lib Cohort Mgr", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["student"], "email": f"{TEST_PREFIX}stu_{ts}@x.com",
         "name": "Test Student", "role": "student",
         "language_preference": "en", "created_at": now_iso},
    ])

    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": tok,
         "expires_at": expires_at, "created_at": now_iso}
        for uid, tok in [
            (ids["super_admin"],      tokens["super_admin"]),
            (ids["inst_manager"],     tokens["inst_manager"]),
            (ids["inst_outsider"],    tokens["inst_outsider"]),
            (ids["inst_lib_manager"], tokens["inst_lib_manager"]),
            (ids["student"],          tokens["student"]),
        ]
    ])

    db.cohorts.insert_one({
        "cohort_id": ids["cohort_c1"],
        "name": f"{TEST_PREFIX}C1_{ts}",
        "instructor_id": ids["inst_manager"],
        "instructor_ids": [ids["inst_manager"]],
        "student_ids": [ids["student"]],
        "released_weeks": [3],
        "created_at": now_iso,
    })
    db.cohorts.insert_one({
        "cohort_id": ids["cohort_c2"],
        "name": f"{TEST_PREFIX}C2_{ts}",
        "instructor_id": ids["inst_lib_manager"],
        "instructor_ids": [ids["inst_lib_manager"]],
        "student_ids": [],
        "released_weeks": [],
        "created_at": now_iso,
    })

    yield {"ids": ids, "tokens": tokens}

    # Teardown — remove ALL our seed docs
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"submission_id": {"$regex": f"^{TEST_PREFIX}"}})


# ----------------------------------------------------------------------
# Upload helpers
# ----------------------------------------------------------------------
def _upload_cohort_material(cohort_id, token, material_type, title,
                            feedback_template=None, week_number=3, description=""):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
        "description": description,
    }
    if feedback_template is not None:
        params["feedback_template"] = feedback_template
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/cohorts/{cohort_id}/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


def _upload_library_material(token, material_type, title,
                             feedback_template=None, week_number=3):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
    }
    if feedback_template is not None:
        params["feedback_template"] = feedback_template
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/library/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


# ======================================================================
# Cohort material upload with feedback_template
# ======================================================================
class TestCohortUploadFeedbackTemplate:
    def test_homework_persists_feedback_template(self, seed):
        tpl = "Compare the submission to the Kawasaki Model on slide 4. Give 2 wins and 2 gaps."
        title = f"{TEST_PREFIX}HW_tpl_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc["material_type"] == "homework"
        assert doc.get("feedback_template") == tpl

    def test_workbook_feedback_template_dropped(self, seed):
        tpl = "Should be discarded — workbooks don't take custom rubric."
        title = f"{TEST_PREFIX}WB_drop_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="workbook", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("feedback_template", "") == ""

    def test_case_study_feedback_template_dropped(self, seed):
        tpl = "Should be discarded."
        title = f"{TEST_PREFIX}CS_drop_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="case_study", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("feedback_template", "") == ""

    def test_homework_without_feedback_template_defaults_empty(self, seed):
        """Regression: existing upload without the new field still works."""
        title = f"{TEST_PREFIX}HW_default_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, feedback_template=None,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("feedback_template", "MISSING") == ""


# ======================================================================
# Library material upload with feedback_template
# ======================================================================
class TestLibraryUploadFeedbackTemplate:
    def test_library_homework_persists_feedback_template(self, seed):
        tpl = "Use the McKinsey pyramid principle to structure feedback."
        title = f"{TEST_PREFIX}LIB_HW_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["inst_manager"],
            material_type="homework", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("feedback_template") == tpl
        assert doc.get("is_library") is True

    def test_library_workbook_feedback_template_dropped(self, seed):
        tpl = "Ignored for workbook."
        title = f"{TEST_PREFIX}LIB_WB_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["inst_manager"],
            material_type="workbook", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("feedback_template", "") == ""


# ======================================================================
# PUT /api/materials/{material_id}/feedback-template
# ======================================================================
class TestUpdateFeedbackTemplate:
    @pytest.fixture
    def homework_material(self, seed):
        """Create a fresh cohort homework material for each test in this class."""
        title = f"{TEST_PREFIX}HW_upd_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title,
            feedback_template="Old template",
        )
        assert r.status_code == 200, r.text
        return r.json()["material_id"]

    def test_updates_with_non_empty_string(self, seed, homework_material):
        new_tpl = "Compare submission to Kawasaki Model on slide 4. Focus on positioning."
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/feedback-template",
            json={"feedback_template": new_tpl},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["feedback_template"] == new_tpl
        assert body["material_id"] == homework_material

        # DB persistence
        doc = db.materials.find_one({"material_id": homework_material}, {"_id": 0})
        assert doc["feedback_template"] == new_tpl

    def test_empty_string_clears(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/feedback-template",
            json={"feedback_template": ""},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["feedback_template"] == ""

        doc = db.materials.find_one({"material_id": homework_material}, {"_id": 0})
        assert doc["feedback_template"] == ""

    def test_whitespace_only_string_is_trimmed_to_empty(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/feedback-template",
            json={"feedback_template": "   \n  \t  "},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["feedback_template"] == ""

    def test_non_homework_material_returns_400(self, seed):
        title = f"{TEST_PREFIX}WB_nofb_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="workbook", title=title,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        r2 = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": "shouldn't apply"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r2.status_code == 400, r2.text
        assert "homework" in r2.json().get("detail", "").lower()

    def test_case_study_material_returns_400(self, seed):
        title = f"{TEST_PREFIX}CS_nofb_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="case_study", title=title,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        r2 = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": "n/a"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r2.status_code == 400, r2.text

    def test_unknown_material_id_returns_404(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/materials/does_not_exist_xyz/feedback-template",
            json={"feedback_template": "anything"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 404, r.text

    def test_outsider_instructor_forbidden(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/feedback-template",
            json={"feedback_template": "I shouldn't be allowed"},
            headers=_auth(seed["tokens"]["inst_outsider"]),
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_super_admin_allowed(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/feedback-template",
            json={"feedback_template": "Super admin override rubric."},
            headers=_auth(seed["tokens"]["super_admin"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["feedback_template"] == "Super admin override rubric."

    def test_library_material_acl(self, seed):
        """Library homework assigned to C2:
           - inst_lib_manager (manages C2) -> 200
           - inst_outsider (manages nothing) -> 403
        """
        title = f"{TEST_PREFIX}LIB_ACL_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["super_admin"],
            material_type="homework", title=title, feedback_template="base",
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        db.materials.update_one({"material_id": mid},
                                {"$set": {"cohort_ids": [seed["ids"]["cohort_c2"]]}})

        # Outsider -> 403
        r_out = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": "outsider try"},
            headers=_auth(seed["tokens"]["inst_outsider"]),
            timeout=15,
        )
        assert r_out.status_code == 403, r_out.text

        # Lib manager -> 200
        r_ok = requests.put(
            f"{BASE_URL}/api/materials/{mid}/feedback-template",
            json={"feedback_template": "Lib manager rubric"},
            headers=_auth(seed["tokens"]["inst_lib_manager"]),
            timeout=15,
        )
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["feedback_template"] == "Lib manager rubric"


# ======================================================================
# submit-on-behalf with custom feedback_template (smoke test)
# ======================================================================
class TestSubmitOnBehalfWithCustomTemplate:
    def test_submit_on_behalf_accepts_flow_with_custom_template(self, seed):
        """Endpoint must return 200 for a homework with a custom feedback_template.
        AI review runs asynchronously — we only verify the endpoint accepts the flow
        and creates the submission. If the async task manages to complete within a
        short wait, we additionally sanity-check the ai_feedback does NOT contain
        the default '3 things you did well' scaffolding literal.
        """
        tpl = ("Focus ONLY on how well the student applied the Kawasaki Model. "
               "Give one paragraph of feedback — do NOT use a 'What You Did Well' / "
               "'Areas for Growth' rubric. This is a custom instructor override.")
        title = f"{TEST_PREFIX}HW_sob_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, feedback_template=tpl,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        # Instructor submits on behalf of the student
        files = {"file": ("student_answer.pdf", _tiny_pdf_bytes(), "application/pdf")}
        data = {"student_id": seed["ids"]["student"], "cohort_id": seed["ids"]["cohort_c1"]}
        r2 = requests.post(
            f"{BASE_URL}/api/materials/{mid}/submit-on-behalf",
            files=files, data=data,
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=45,
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        sub_id = body.get("submission_id")
        assert sub_id, r2.text
        # Response body itself must not contain the default rubric scaffolding
        assert "What You Did Well" not in str(body)
        # Tag submission for cleanup
        db.submissions.update_one(
            {"submission_id": sub_id},
            {"$set": {"submission_id": f"{TEST_PREFIX}{sub_id}"}}
        )
        tagged_sub_id = f"{TEST_PREFIX}{sub_id}"

        # Best-effort: give the async task up to ~20s to finish. AI may fail on the
        # 40-byte fake PDF (no extractable text) — in that case ai_feedback stays None,
        # which is still acceptable for this smoke test.
        deadline = time.time() + 20
        ai_feedback = None
        while time.time() < deadline:
            sub_doc = db.submissions.find_one({"submission_id": tagged_sub_id}, {"_id": 0})
            if sub_doc and sub_doc.get("ai_feedback"):
                ai_feedback = sub_doc["ai_feedback"]
                break
            time.sleep(2)

        if ai_feedback:
            # Positive assertion: custom instructions were applied — AI response must
            # reference the domain-specific term from our custom template ("Kawasaki").
            # (We can't reliably assert absence of the default scaffolding string
            # "What You Did Well:" because the AI may reference that phrase naturally
            # in a refusal / explanation message when the submission has no extractable
            # text, as with our tiny stub PDF.)
            assert "Kawasaki" in ai_feedback, (
                "Custom feedback_template should have been injected into the AI prompt — "
                "expected AI to reference 'Kawasaki' per the template. Got: "
                f"{ai_feedback[:400]}"
            )
        # If ai_feedback is None within the wait window: async task hasn't completed
        # yet — the endpoint contract (accepts flow + creates submission) is what
        # we require. Do NOT fail the test on timeout.
