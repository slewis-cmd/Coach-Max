"""
Iteration 53 — Per-assignment allowed_extensions override feature.

Covers:
- _normalize_extensions helper: string/list/None/dedupe/dotstrip/lowercase
- _effective_allowed_extensions helper: override > type default > DEFAULT
- POST /api/cohorts/{cid}/assignments — persists normalized extensions
- PUT /api/assignments/{aid} — set / explicit-clear (empty list) / omit
- POST /api/milestones/{mid}/submit — override respected (accept + reject)
- Legacy POST /api/materials/{mid}/submit — falls back to type defaults
- POST /api/milestones/{mid}/submit-on-behalf — override respected
- GET /api/submit-link/a/{aid}/w/{wk} — returns effective list

All seeded docs prefixed TEST_AEXT_.
"""
import io
import os
import sys
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

TEST_PREFIX = "TEST_AEXT_"

# Import helpers directly for unit tests (avoid HTTP round-trip)
sys.path.insert(0, "/app/backend")
from server import (  # noqa: E402
    _normalize_extensions,
    _effective_allowed_extensions,
    SUBMISSION_TYPE_CONFIG,
    DEFAULT_HOMEWORK_EXTENSIONS,
)


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
    }
    toks = {k: f"{TEST_PREFIX}tok_{k}_{ts}_{uuid.uuid4().hex[:6]}" for k in ids.keys()}

    db.users.insert_many([
        {"user_id": ids["sa"],         "email": f"{TEST_PREFIX}sa_{ts}@x.com",  "name": "Adm",  "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i_{ts}@x.com",   "name": "Ins",  "role": "instructor",  "created_at": now_iso},
        {"user_id": ids["student"],    "email": f"{TEST_PREFIX}s_{ts}@x.com",   "name": "Stu",  "role": "student",     "language_preference": "en", "created_at": now_iso},
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
    db.assignments.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"student_id": {"$regex": f"^{TEST_PREFIX}"}})


def _create_cohort_with_student(instructor_token, student_id, name_suffix=""):
    name = f"{TEST_PREFIX}C_{name_suffix}_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{BASE_URL}/api/cohorts",
        json={"name": name, "description": "iter53 aext test"},
        headers=_auth(instructor_token), timeout=15,
    )
    assert r.status_code == 200, r.text
    cid = r.json()["cohort_id"]
    db.cohorts.update_one({"cohort_id": cid}, {"$addToSet": {"student_ids": student_id}})
    return cid


# ===================================================================
# 1) Unit tests — _normalize_extensions
# ===================================================================
class TestNormalizeExtensions:
    def test_string_mixed_case_dots_spaces(self):
        assert _normalize_extensions("MP4, .MOV, mp3") == ["mp4", "mov", "mp3"]

    def test_string_space_separated_dedupe(self):
        assert _normalize_extensions("pdf pdf docx") == ["pdf", "docx"]

    def test_empty_string_returns_none(self):
        assert _normalize_extensions("") is None

    def test_empty_list_returns_none(self):
        assert _normalize_extensions([]) is None

    def test_none_returns_none(self):
        assert _normalize_extensions(None) is None

    def test_list_of_strings_dedupes_and_lowercases(self):
        assert _normalize_extensions([".PDF", "pdf", "DOCX"]) == ["pdf", "docx"]

    def test_semicolon_separated(self):
        assert _normalize_extensions("mp4;mov;mp3") == ["mp4", "mov", "mp3"]


# ===================================================================
# 2) Unit tests — _effective_allowed_extensions
# ===================================================================
class TestEffectiveExtensions:
    def test_override_wins(self):
        asgn = {"allowed_extensions": ["mp4", "pdf"]}
        assert _effective_allowed_extensions(asgn, "60_second_pitch") == ["mp4", "pdf"]

    def test_falls_back_to_type_default(self):
        asgn = {"allowed_extensions": None}
        assert _effective_allowed_extensions(asgn, "10_slide_pitch") == SUBMISSION_TYPE_CONFIG["10_slide_pitch"]["extensions"]

    def test_falls_back_to_type_default_when_missing(self):
        # Empty dict should fall back
        assert _effective_allowed_extensions({}, "60_second_pitch") == SUBMISSION_TYPE_CONFIG["60_second_pitch"]["extensions"]

    def test_falls_back_to_default_homework_for_unknown_type(self):
        assert _effective_allowed_extensions({}, "some_unknown_type") == DEFAULT_HOMEWORK_EXTENSIONS

    def test_empty_list_override_treated_as_no_override(self):
        # Empty list is falsy → falls back to type default
        assert _effective_allowed_extensions({"allowed_extensions": []}, "60_second_pitch") == SUBMISSION_TYPE_CONFIG["60_second_pitch"]["extensions"]


# ===================================================================
# 3) POST /api/cohorts/{cid}/assignments — creates with override
# ===================================================================
class TestCreateAssignmentWithOverride:
    def test_create_persists_normalized_extensions(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "create1")
        payload = {
            "title": f"{TEST_PREFIX}Elevator Pitch Mixed",
            "submission_type": "60_second_pitch",
            "description": "Video OR written",
            "allowed_extensions": ["MP4", ".MOV", "PDF", "pdf"],  # mixed → normalized
        }
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json=payload, headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["allowed_extensions"] == ["mp4", "mov", "pdf"]
        # Verify persistence via GET
        r2 = requests.get(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r2.status_code == 200
        created = next(a for a in r2.json() if a["assignment_id"] == data["assignment_id"])
        assert created["allowed_extensions"] == ["mp4", "mov", "pdf"]

    def test_create_without_override_stores_null(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "create2")
        payload = {
            "title": f"{TEST_PREFIX}No Override",
            "submission_type": "10_slide_pitch",
        }
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json=payload, headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed_extensions"] is None


# ===================================================================
# 4) PUT /api/assignments/{aid} — set / clear / omit
# ===================================================================
class TestUpdateAssignmentOverride:
    def _create(self, seed, cid, initial=None):
        payload = {
            "title": f"{TEST_PREFIX}Upd_{uuid.uuid4().hex[:5]}",
            "submission_type": "60_second_pitch",
        }
        if initial is not None:
            payload["allowed_extensions"] = initial
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json=payload, headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_set_override_via_put(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "upd_set")
        asgn = self._create(seed, cid)
        aid = asgn["assignment_id"]
        r = requests.put(
            f"{BASE_URL}/api/assignments/{aid}",
            json={"allowed_extensions": ["mp4", "pdf"]},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed_extensions"] == ["mp4", "pdf"]

    def test_clear_override_via_empty_list(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "upd_clear")
        asgn = self._create(seed, cid, initial=["mp4", "pdf"])
        aid = asgn["assignment_id"]
        assert asgn["allowed_extensions"] == ["mp4", "pdf"]
        # Explicit clear via empty list → stored as None
        r = requests.put(
            f"{BASE_URL}/api/assignments/{aid}",
            json={"allowed_extensions": []},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed_extensions"] is None

    def test_omit_field_leaves_alone(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "upd_omit")
        asgn = self._create(seed, cid, initial=["mp4", "pdf"])
        aid = asgn["assignment_id"]
        r = requests.put(
            f"{BASE_URL}/api/assignments/{aid}",
            json={"description": "changed desc only"},
            headers=_auth(seed["tokens"]["instructor"]), timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["allowed_extensions"] == ["mp4", "pdf"]
        assert r.json()["description"] == "changed desc only"


# ===================================================================
# 5) Student milestone submit — override enforced
# ===================================================================
class TestMilestoneSubmitOverride:
    def _create_asgn(self, seed, cid, submission_type, extensions=None):
        payload = {
            "title": f"{TEST_PREFIX}A_{uuid.uuid4().hex[:5]}",
            "submission_type": submission_type,
        }
        if extensions is not None:
            payload["allowed_extensions"] = extensions
        r = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json=payload, headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()

    def test_override_accepts_pdf_on_60sec_pitch(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "over_pdf")
        asgn = self._create_asgn(seed, cid, "60_second_pitch", extensions=["mp4", "pdf"])
        mid = asgn["milestones"][0]["milestone_id"]
        # .pdf should be accepted because of override (default 60sec rejects pdf)
        files = {"file": ("pitch.pdf", io.BytesIO(b"%PDF-1.4 test content"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        sub = db.submissions.find_one({"submission_id": r.json()["submission_id"]}, {"_id": 0})
        assert sub is not None
        assert sub["file_name"] == "pitch.pdf"

    def test_override_accepts_mp4(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "over_mp4")
        asgn = self._create_asgn(seed, cid, "60_second_pitch", extensions=["mp4", "pdf"])
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("pitch.mp4", io.BytesIO(b"\x00\x00\x00\x18ftypmp42"), "video/mp4")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=30,
        )
        assert r.status_code == 200, r.text

    def test_override_rejects_txt_with_override_in_error(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "over_txt")
        asgn = self._create_asgn(seed, cid, "60_second_pitch", extensions=["mp4", "pdf"])
        mid = asgn["milestones"][0]["milestone_id"]
        files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        # Error must reflect the OVERRIDE list, not the type default
        assert ".mp4" in r.text and ".pdf" in r.text
        assert ".mov" not in r.text  # mov is 60sec default, but overridden away

    def test_no_override_uses_type_default(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "no_over")
        asgn = self._create_asgn(seed, cid, "60_second_pitch", extensions=None)
        mid = asgn["milestones"][0]["milestone_id"]
        # 60_second_pitch defaults were widened Jul 20 2026 to include written
        # alternatives (pdf/doc/docx/txt), so .pdf is now ACCEPTED by default.
        # A truly-unsupported extension like .zip must still be rejected.
        files = {"file": ("pitch.zip", io.BytesIO(b"zipbytes"), "application/zip")}
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit",
            params={"cohort_id": cid, "assignment_id": asgn["assignment_id"]},
            files=files,
            headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        # Error reflects the TYPE DEFAULT (has .mov/.mp4)
        assert ".mov" in r.text or ".mp4" in r.text


# ===================================================================
# 6) Submit-on-behalf enforces the override
# ===================================================================
class TestSubmitOnBehalfOverride:
    def test_sob_respects_override(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "sob_over")
        # Create 60sec assignment with override that allows pdf
        r_create = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={
                "title": f"{TEST_PREFIX}SoBOver",
                "submission_type": "60_second_pitch",
                "allowed_extensions": ["mp4", "pdf"],
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r_create.status_code == 200, r_create.text
        asgn = r_create.json()
        mid = asgn["milestones"][0]["milestone_id"]
        # Instructor submits .pdf on behalf (default 60sec rejects .pdf; override allows it)
        files = {"file": ("onbehalf.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")}
        data = {
            "student_id": seed["ids"]["student"],
            "assignment_id": asgn["assignment_id"],
            "cohort_id": cid,
        }
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit-on-behalf",
            data=data, files=files,
            headers=_auth(seed["tokens"]["instructor"]), timeout=30,
        )
        assert r.status_code == 200, r.text
        sub = db.submissions.find_one({"submission_id": r.json()["submission_id"]}, {"_id": 0})
        assert sub is not None
        assert sub["file_name"] == "onbehalf.pdf"

    def test_sob_rejects_when_override_excludes(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "sob_rej")
        r_create = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={
                "title": f"{TEST_PREFIX}SoBRej",
                "submission_type": "60_second_pitch",
                "allowed_extensions": ["mp4", "pdf"],
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        asgn = r_create.json()
        mid = asgn["milestones"][0]["milestone_id"]
        # .txt should be rejected (not in override list)
        files = {"file": ("notes.txt", io.BytesIO(b"hi"), "text/plain")}
        data = {
            "student_id": seed["ids"]["student"],
            "assignment_id": asgn["assignment_id"],
            "cohort_id": cid,
        }
        r = requests.post(
            f"{BASE_URL}/api/milestones/{mid}/submit-on-behalf",
            data=data, files=files,
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert r.status_code == 400
        assert ".pdf" in r.text and ".mp4" in r.text


# ===================================================================
# 7) Legacy /api/materials/{id}/submit still uses SUBMISSION_TYPE_CONFIG
# ===================================================================
class TestLegacyMaterialSubmitFallback:
    def test_legacy_material_rejects_unsupported_when_type_is_60sec(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "legacy")
        mat_id = f"mat_{uuid.uuid4().hex[:10]}"
        db.materials.insert_one({
            "material_id": mat_id,
            "cohort_id": cid,
            "title": f"{TEST_PREFIX}legacy 60sec",
            "week_number": 1,
            "material_type": "homework",
            "submission_type": "60_second_pitch",
            "file_name": "hw.pdf",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        db.cohorts.update_one({"cohort_id": cid}, {"$addToSet": {"released_weeks": 1}})
        # 60_second_pitch defaults now include pdf/doc/docx/txt after Jul 20
        # widening, so .pdf is accepted. A truly-unsupported extension (.zip)
        # must still be rejected by the legacy material endpoint.
        files = {"file": ("try.zip", io.BytesIO(b"zipbytes"), "application/zip")}
        r = requests.post(
            f"{BASE_URL}/api/materials/{mat_id}/submit",
            files=files, headers=_auth(seed["tokens"]["student"]), timeout=15,
        )
        assert r.status_code == 400
        assert ".mp4" in r.text or ".mov" in r.text


# ===================================================================
# 8) Submit-link resolver returns effective allowed_extensions
# ===================================================================
class TestSubmitLinkResolverEffectiveExtensions:
    def test_resolver_uses_override(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "resolv_o")
        r_create = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={
                "title": f"{TEST_PREFIX}Resolv",
                "submission_type": "60_second_pitch",
                "allowed_extensions": ["mp4", "pdf"],
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        aid = r_create.json()["assignment_id"]
        wk = r_create.json()["milestones"][0]["week_number"]
        r = requests.get(
            f"{BASE_URL}/api/submit-link/a/{aid}/w/{wk}", timeout=10,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["assignment"]["allowed_extensions"] == ["mp4", "pdf"]

    def test_resolver_uses_type_default_when_no_override(self, seed):
        cid = _create_cohort_with_student(seed["tokens"]["instructor"], seed["ids"]["student"], "resolv_d")
        r_create = requests.post(
            f"{BASE_URL}/api/cohorts/{cid}/assignments",
            json={
                "title": f"{TEST_PREFIX}ResolvD",
                "submission_type": "10_slide_pitch",
            },
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        aid = r_create.json()["assignment_id"]
        wk = r_create.json()["milestones"][0]["week_number"]
        r = requests.get(
            f"{BASE_URL}/api/submit-link/a/{aid}/w/{wk}", timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json()["assignment"]["allowed_extensions"] == SUBMISSION_TYPE_CONFIG["10_slide_pitch"]["extensions"]
