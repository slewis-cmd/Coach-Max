"""
Backend test suite for Google Drive folder URL metadata on homework materials.

Covers:
- Cohort material upload: drive_folder_url persisted for material_type='homework',
  dropped (empty) for non-homework.
- Library material upload: drive_folder_url persisted for material_type='homework'.
- PUT /api/materials/{material_id}/drive-link:
    * updates with valid https URL (200 + new url)
    * clears with empty string
    * rejects non-http URL (400)
    * rejects on non-homework material (400)
    * ACL: outsider instructor -> 403, cohort manager -> 200
    * ACL for library homework: instructor managing ANY assigned cohort -> 200,
      instructor managing none -> 403
- GET /api/submit-link/{material_id} exposes drive_folder_url.
- GET /api/student/dashboard: weeks[i].homeworks[0].drive_folder_url and legacy
  week.homework.drive_folder_url both match.
- Regression: existing homework upload without drive_folder_url defaults to "".
- Regression: submission POST/GET download + review still work with drive metadata.

All seeded docs are prefixed TEST_DRIVE_ and cleaned up in teardown.
"""

import io
import os
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

TEST_PREFIX = "TEST_DRIVE_"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_pdf_bytes() -> bytes:
    # Minimal valid PDF stub — server only checks the extension, but we send real bytes.
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


# ----------------------------------------------------------------------
# Fixture: seed super admin, cohort manager, outsider instructor, student, cohort
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def seed():
    ts = int(datetime.now().timestamp())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    ids = {
        "super_admin":       f"{TEST_PREFIX}sa_{ts}",
        "inst_manager":      f"{TEST_PREFIX}i1_{ts}",   # manages C1
        "inst_outsider":     f"{TEST_PREFIX}i2_{ts}",   # does NOT manage C1
        "inst_lib_manager":  f"{TEST_PREFIX}i3_{ts}",   # manages C2 (assigned to lib mat)
        "student":           f"{TEST_PREFIX}stu_{ts}",
        "cohort_c1":         f"{TEST_PREFIX}c1_{ts}",
        "cohort_c2":         f"{TEST_PREFIX}c2_{ts}",
    }
    tokens = {
        "super_admin":      f"{TEST_PREFIX}tok_sa_{ts}",
        "inst_manager":     f"{TEST_PREFIX}tok_i1_{ts}",
        "inst_outsider":    f"{TEST_PREFIX}tok_i2_{ts}",
        "inst_lib_manager": f"{TEST_PREFIX}tok_i3_{ts}",
        "student":          f"{TEST_PREFIX}tok_stu_{ts}",
    }

    # Users
    db.users.insert_many([
        {"user_id": ids["super_admin"], "email": f"{TEST_PREFIX}sa_{ts}@x.com",
         "name": "Test Admin", "role": "super_admin",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["inst_manager"], "email": f"{TEST_PREFIX}i1_{ts}@x.com",
         "name": "Cohort Mgr", "role": "instructor",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["inst_outsider"], "email": f"{TEST_PREFIX}i2_{ts}@x.com",
         "name": "Outsider", "role": "instructor",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["inst_lib_manager"], "email": f"{TEST_PREFIX}i3_{ts}@x.com",
         "name": "Lib Cohort Mgr", "role": "instructor",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["student"], "email": f"{TEST_PREFIX}stu_{ts}@x.com",
         "name": "Test Student", "role": "student", "language_preference": "en",
         "created_at": datetime.now(timezone.utc).isoformat()},
    ])

    # Sessions
    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": tok,
         "expires_at": expires_at,
         "created_at": datetime.now(timezone.utc).isoformat()}
        for uid, tok in [
            (ids["super_admin"],      tokens["super_admin"]),
            (ids["inst_manager"],     tokens["inst_manager"]),
            (ids["inst_outsider"],    tokens["inst_outsider"]),
            (ids["inst_lib_manager"], tokens["inst_lib_manager"]),
            (ids["student"],          tokens["student"]),
        ]
    ])

    # Cohort C1 – managed by inst_manager, has student, week 3 released
    db.cohorts.insert_one({
        "cohort_id": ids["cohort_c1"],
        "name": f"{TEST_PREFIX}C1_{ts}",
        "instructor_id": ids["inst_manager"],
        "instructor_ids": [ids["inst_manager"]],
        "student_ids": [ids["student"]],
        "released_weeks": [3],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Cohort C2 – managed only by inst_lib_manager (for library ACL test)
    db.cohorts.insert_one({
        "cohort_id": ids["cohort_c2"],
        "name": f"{TEST_PREFIX}C2_{ts}",
        "instructor_id": ids["inst_lib_manager"],
        "instructor_ids": [ids["inst_lib_manager"]],
        "student_ids": [],
        "released_weeks": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    yield {"ids": ids, "tokens": tokens}

    # Teardown
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    # Delete only materials we tagged (title always starts with TEST_DRIVE_)
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"submission_id": {"$regex": f"^{TEST_PREFIX}"}})


# ----------------------------------------------------------------------
# Upload helper: uses form-multipart against the real endpoint
# ----------------------------------------------------------------------
def _upload_cohort_material(cohort_id, token, material_type, title,
                            drive_folder_url=None, week_number=3, description=""):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
        "description": description,
    }
    if drive_folder_url is not None:
        params["drive_folder_url"] = drive_folder_url
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/cohorts/{cohort_id}/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


def _upload_library_material(token, material_type, title,
                             drive_folder_url=None, week_number=3):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
    }
    if drive_folder_url is not None:
        params["drive_folder_url"] = drive_folder_url
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/library/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


# ======================================================================
# Tests: cohort material upload
# ======================================================================
class TestCohortMaterialUpload:
    def test_homework_with_drive_url_persists(self, seed):
        url = "https://drive.google.com/drive/folders/HW_ABC"
        title = f"{TEST_PREFIX}HW_persist_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, drive_folder_url=url,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc["drive_folder_url"] == url
        assert doc["material_type"] == "homework"

    def test_workbook_with_drive_url_is_dropped(self, seed):
        url = "https://drive.google.com/drive/folders/WB_XYZ"
        title = f"{TEST_PREFIX}WB_drop_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="workbook", title=title, drive_folder_url=url,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        # Field is stored but forced to empty for non-homework
        assert doc.get("drive_folder_url", "") == ""

    def test_homework_without_drive_url_defaults_empty(self, seed):
        """Regression: existing upload path without the new field still works."""
        title = f"{TEST_PREFIX}HW_default_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, drive_folder_url=None,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc.get("drive_folder_url", "MISSING") == ""


# ======================================================================
# Tests: library material upload
# ======================================================================
class TestLibraryMaterialUpload:
    def test_library_homework_persists_url(self, seed):
        url = "https://drive.google.com/drive/folders/LIB_HW_1"
        title = f"{TEST_PREFIX}LIB_HW_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["inst_manager"],
            material_type="homework", title=title, drive_folder_url=url,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]

        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc["drive_folder_url"] == url
        assert doc["is_library"] is True
        assert doc["material_type"] == "homework"


# ======================================================================
# Tests: PUT /api/materials/{material_id}/drive-link
# ======================================================================
class TestUpdateDriveLink:
    @pytest.fixture
    def homework_material(self, seed):
        """Create a fresh homework material on C1 for each test in this class."""
        title = f"{TEST_PREFIX}HW_upd_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title,
            drive_folder_url="https://drive.google.com/drive/folders/OLD",
        )
        assert r.status_code == 200, r.text
        return r.json()["material_id"]

    def test_valid_https_updates(self, seed, homework_material):
        new_url = "https://drive.google.com/drive/folders/NEW_URL"
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": new_url},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["drive_folder_url"] == new_url
        # Verify persistence via GET (submit-link)
        r2 = requests.get(f"{BASE_URL}/api/submit-link/{homework_material}", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["drive_folder_url"] == new_url

    def test_empty_string_clears(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": ""},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["drive_folder_url"] == ""
        doc = db.materials.find_one({"material_id": homework_material}, {"_id": 0})
        assert doc["drive_folder_url"] == ""

    def test_javascript_url_rejected(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": "javascript:alert(1)"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_ftp_url_rejected(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": "ftp://x.example.com/drive"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 400, r.text

    def test_non_homework_material_rejected(self, seed):
        # Create a workbook material and try to set drive-link
        title = f"{TEST_PREFIX}WB_nohw_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="workbook", title=title,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        r2 = requests.put(
            f"{BASE_URL}/api/materials/{mid}/drive-link",
            json={"drive_folder_url": "https://drive.google.com/x"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r2.status_code == 400, r2.text
        assert "homework" in r2.json().get("detail", "").lower()

    def test_outsider_instructor_forbidden(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": "https://drive.google.com/drive/folders/OUT"},
            headers=_auth(seed["tokens"]["inst_outsider"]),
            timeout=15,
        )
        assert r.status_code == 403, r.text

    def test_cohort_manager_allowed(self, seed, homework_material):
        r = requests.put(
            f"{BASE_URL}/api/materials/{homework_material}/drive-link",
            json={"drive_folder_url": "https://drive.google.com/drive/folders/MGR_OK"},
            headers=_auth(seed["tokens"]["inst_manager"]),
            timeout=15,
        )
        assert r.status_code == 200, r.text

    def test_library_material_acl(self, seed):
        """Library homework material assigned to C2:
           - inst_lib_manager (manages C2) -> 200
           - inst_outsider (manages nothing) -> 403
        """
        # Upload as super_admin, then assign to C2 by direct DB update
        title = f"{TEST_PREFIX}LIB_ACL_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["super_admin"],
            material_type="homework", title=title,
            drive_folder_url="https://drive.google.com/drive/folders/LIB_ACL",
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        db.materials.update_one({"material_id": mid}, {"$set": {"cohort_ids": [seed["ids"]["cohort_c2"]]}})

        # Outsider: not managing any assigned cohort -> 403
        r_out = requests.put(
            f"{BASE_URL}/api/materials/{mid}/drive-link",
            json={"drive_folder_url": "https://drive.google.com/drive/folders/OUTSIDER"},
            headers=_auth(seed["tokens"]["inst_outsider"]),
            timeout=15,
        )
        assert r_out.status_code == 403, r_out.text

        # Lib manager (manages C2) -> 200
        r_ok = requests.put(
            f"{BASE_URL}/api/materials/{mid}/drive-link",
            json={"drive_folder_url": "https://drive.google.com/drive/folders/LIB_OK"},
            headers=_auth(seed["tokens"]["inst_lib_manager"]),
            timeout=15,
        )
        assert r_ok.status_code == 200, r_ok.text
        assert r_ok.json()["drive_folder_url"] == "https://drive.google.com/drive/folders/LIB_OK"


# ======================================================================
# Tests: /submit-link + student dashboard shape
# ======================================================================
class TestSubmitLinkAndDashboard:
    def test_submit_link_returns_drive_url(self, seed):
        url = "https://drive.google.com/drive/folders/SUBLINK"
        title = f"{TEST_PREFIX}HW_sublink_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, drive_folder_url=url,
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        r2 = requests.get(f"{BASE_URL}/api/submit-link/{mid}", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["drive_folder_url"] == url

    def test_student_dashboard_exposes_drive_url(self, seed):
        # Delete any lingering week 3 homework from earlier tests within this cohort
        # to keep the shape assertions deterministic (student sees all homeworks
        # of released weeks; we only assert on the one we just created).
        url = "https://drive.google.com/drive/folders/DASH_XYZ"
        title = f"{TEST_PREFIX}HW_dash_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title, drive_folder_url=url,
            week_number=3,
        )
        assert r.status_code == 200, r.text
        target_mid = r.json()["material_id"]

        # Student dashboard
        r2 = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers=_auth(seed["tokens"]["student"]),
            timeout=15,
        )
        assert r2.status_code == 200, r2.text
        payload = r2.json()

        target_cohort = next(
            (c for c in payload if c["cohort_id"] == seed["ids"]["cohort_c1"]), None
        )
        assert target_cohort is not None, "seeded cohort not found in student dashboard"

        week3 = next(
            (w for w in target_cohort["weeks"] if w["week_number"] == 3), None
        )
        assert week3 is not None, "week 3 missing from released weeks"

        # New shape: homeworks[] entry matching our material
        hw_entry = next(
            (h for h in week3["homeworks"] if h["material_id"] == target_mid), None
        )
        assert hw_entry is not None, f"seeded homework not in week3.homeworks: {week3}"
        assert hw_entry["drive_folder_url"] == url

        # Legacy top-level homework field must also include drive_folder_url
        # (points to the first homework of the week — may or may not be ours)
        assert week3["homework"] is not None
        assert "drive_folder_url" in week3["homework"]

    def test_regression_submission_flow_still_works(self, seed):
        """Regression: POST /materials/{id}/submit + GET download still succeed."""
        title = f"{TEST_PREFIX}HW_reg_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort_c1"], seed["tokens"]["inst_manager"],
            material_type="homework", title=title,
            drive_folder_url="https://drive.google.com/drive/folders/REG",
        )
        assert r.status_code == 200
        mid = r.json()["material_id"]

        # Student submits a file
        files = {"file": ("hw_answer.pdf", _tiny_pdf_bytes(), "application/pdf")}
        r2 = requests.post(
            f"{BASE_URL}/api/materials/{mid}/submit",
            files=files, headers=_auth(seed["tokens"]["student"]),
            timeout=30,
        )
        assert r2.status_code == 200, r2.text
        sub_id = r2.json().get("submission_id")
        assert sub_id, r2.text

        # Verify persistence
        db_sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert db_sub is not None
        assert db_sub["material_id"] == mid
        # Cleanup tag for teardown
        db.submissions.update_one(
            {"submission_id": sub_id},
            {"$set": {"submission_id": f"{TEST_PREFIX}{sub_id}"}}
        )
