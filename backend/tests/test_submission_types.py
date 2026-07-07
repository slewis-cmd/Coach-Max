"""
Backend test suite for named homework submission types feature (iteration 37).

Covers:
- Material model accepts submission_type + questionnaire_fields on cohort + library uploads
- Invalid submission_type returns 400
- Non-homework materials strip submission_type
- Questionnaire fields: JSON parsing / list validation / cap of 20 / required label / type whitelist
- NEW /api/submit-link/w/{week}/{type} resolver: 400 unknown type, 404 no match, 200 with material_id
- GET /api/submit-link/{material_id} returns submission_type + questionnaire_fields
- POST /api/materials/{id}/submit: per-type extension enforcement (pitch/deck/case)
- Questionnaire submissions: file optional, questionnaire_answers required-field / >5000 char validation, persists
- GET /api/submissions/{id}/download -> JSON payload for questionnaire submissions
- GET /api/submissions/{id}/preview-text -> synthesized Q&A text
- Manual /api/submissions/{id}/review on a questionnaire submission uses synthesized text (populates ai_feedback)

All seeded docs are prefixed TEST_SUBTYPE_ and cleaned in teardown.
"""

import io
import os
import json
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

TEST_PREFIX = "TEST_SUBTYPE_"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tiny_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _tiny_pptx_bytes() -> bytes:
    # Minimal (fake) zip container — good enough for extension check
    return b"PK\x03\x04" + b"\x00" * 64


def _tiny_mp4_bytes() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200


def _tiny_docx_bytes() -> bytes:
    return b"PK\x03\x04" + b"\x00" * 64


def _tiny_txt_bytes() -> bytes:
    return b"hello case activity submission"


@pytest.fixture(scope="module")
def seed():
    ts = int(datetime.now().timestamp())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    ids = {
        "super_admin":       f"{TEST_PREFIX}sa_{ts}",
        "instructor":        f"{TEST_PREFIX}i1_{ts}",
        "student":           f"{TEST_PREFIX}stu_{ts}",
        "cohort":            f"{TEST_PREFIX}c1_{ts}",
    }
    tokens = {
        "super_admin":       f"{TEST_PREFIX}tok_sa_{ts}",
        "instructor":        f"{TEST_PREFIX}tok_i1_{ts}",
        "student":           f"{TEST_PREFIX}tok_stu_{ts}",
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    db.users.insert_many([
        {"user_id": ids["super_admin"], "email": f"{TEST_PREFIX}sa_{ts}@x.com",
         "name": "Test Admin", "role": "super_admin", "created_at": now_iso},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}i1_{ts}@x.com",
         "name": "Cohort Mgr", "role": "instructor", "created_at": now_iso},
        {"user_id": ids["student"], "email": f"{TEST_PREFIX}stu_{ts}@x.com",
         "name": "Test Student", "role": "student",
         "language_preference": "en", "created_at": now_iso},
    ])

    db.user_sessions.insert_many([
        {"user_id": uid, "session_token": tok,
         "expires_at": expires_at, "created_at": now_iso}
        for uid, tok in [
            (ids["super_admin"], tokens["super_admin"]),
            (ids["instructor"], tokens["instructor"]),
            (ids["student"], tokens["student"]),
        ]
    ])

    db.cohorts.insert_one({
        "cohort_id": ids["cohort"],
        "name": f"{TEST_PREFIX}C1_{ts}",
        "instructor_id": ids["instructor"],
        "instructor_ids": [ids["instructor"]],
        "student_ids": [ids["student"]],
        "released_weeks": list(range(1, 15)),
        "created_at": now_iso,
    })

    yield {"ids": ids, "tokens": tokens}

    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"file_name": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"submission_id": {"$regex": f"^{TEST_PREFIX}"}})


def _upload_cohort_material(cohort_id, token, material_type, title,
                            submission_type=None, questionnaire_fields=None,
                            week_number=3, description=""):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
        "description": description,
    }
    if submission_type is not None:
        params["submission_type"] = submission_type
    if questionnaire_fields is not None:
        params["questionnaire_fields"] = questionnaire_fields
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/cohorts/{cohort_id}/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


def _upload_library_material(token, material_type, title,
                             submission_type=None, questionnaire_fields=None,
                             week_number=3):
    params = {
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
    }
    if submission_type is not None:
        params["submission_type"] = submission_type
    if questionnaire_fields is not None:
        params["questionnaire_fields"] = questionnaire_fields
    files = {"file": (f"{title}.pdf", _tiny_pdf_bytes(), "application/pdf")}
    return requests.post(
        f"{BASE_URL}/api/library/materials",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


# ======================================================================
# Cohort material upload with submission_type
# ======================================================================
class TestCohortSubmissionTypeUpload:
    def test_homework_persists_submission_type(self, seed):
        title = f"{TEST_PREFIX}HW_pitch_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            submission_type="60_second_pitch",
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc is not None
        assert doc["submission_type"] == "60_second_pitch"

    def test_invalid_submission_type_returns_400(self, seed):
        r = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}HW_invalid_{uuid.uuid4().hex[:6]}",
            submission_type="not_a_real_type",
        )
        assert r.status_code == 400
        assert "submission_type must be one of" in r.text

    def test_empty_submission_type_treated_as_generic(self, seed):
        r = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}HW_generic_{uuid.uuid4().hex[:6]}",
            submission_type="",
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc.get("submission_type") in (None, "")

    def test_workbook_strips_submission_type(self, seed):
        r = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="workbook",
            title=f"{TEST_PREFIX}WB_pitch_{uuid.uuid4().hex[:6]}",
            submission_type="60_second_pitch",
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        # Should NOT persist submission_type on non-homework
        assert doc.get("submission_type") in (None, "")

    def test_materials_list_includes_submission_type(self, seed):
        title = f"{TEST_PREFIX}HW_list_{uuid.uuid4().hex[:6]}"
        r = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            submission_type="60_second_pitch",
        )
        assert r.status_code == 200
        mid = r.json()["material_id"]
        list_r = requests.get(
            f"{BASE_URL}/api/cohorts/{seed['ids']['cohort']}/materials",
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert list_r.status_code == 200
        weeks = list_r.json()
        # Response is grouped by week: [{week_number, workbooks, case_studies, homework}, ...]
        homework = []
        for w in weeks:
            homework.extend(w.get("homework", []))
        found = next((m for m in homework if m.get("material_id") == mid), None)
        assert found is not None
        assert found.get("submission_type") == "60_second_pitch"


# ======================================================================
# Library upload with questionnaire fields
# ======================================================================
class TestLibraryQuestionnaireUpload:
    def test_valid_questionnaire_fields_persist(self, seed):
        fields = [
            {"id": "q1", "label": "Problem you solve?", "type": "text", "required": True},
            {"id": "q2", "label": "Target market?", "type": "longtext", "required": False},
        ]
        title = f"{TEST_PREFIX}LIB_Q_{uuid.uuid4().hex[:6]}"
        r = _upload_library_material(
            seed["tokens"]["instructor"],
            material_type="homework", title=title,
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert r.status_code == 200, r.text
        mid = r.json()["material_id"]
        doc = db.materials.find_one({"material_id": mid}, {"_id": 0})
        assert doc["submission_type"] == "business_questionnaire"
        got = doc.get("questionnaire_fields") or []
        assert len(got) == 2
        assert got[0]["label"] == "Problem you solve?"
        assert got[0]["required"]
        assert got[1]["type"] == "longtext"

    def test_invalid_json_returns_400(self, seed):
        r = _upload_library_material(
            seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}LIB_bad_{uuid.uuid4().hex[:6]}",
            submission_type="business_questionnaire",
            questionnaire_fields="{not valid json",
        )
        assert r.status_code == 400
        assert "valid JSON" in r.text

    def test_more_than_20_fields_returns_400(self, seed):
        fields = [{"id": f"q{i}", "label": f"Q{i}", "type": "text", "required": False} for i in range(21)]
        r = _upload_library_material(
            seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}LIB_cap_{uuid.uuid4().hex[:6]}",
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert r.status_code == 400
        assert "20" in r.text

    def test_missing_label_returns_400(self, seed):
        fields = [{"id": "q1", "label": "", "type": "text", "required": True}]
        r = _upload_library_material(
            seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}LIB_nolabel_{uuid.uuid4().hex[:6]}",
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert r.status_code == 400
        assert "label" in r.text.lower()

    def test_wrong_type_returns_400(self, seed):
        fields = [{"id": "q1", "label": "Pick one", "type": "select", "required": False}]
        r = _upload_library_material(
            seed["tokens"]["instructor"],
            material_type="homework",
            title=f"{TEST_PREFIX}LIB_wrongtype_{uuid.uuid4().hex[:6]}",
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert r.status_code == 400
        assert "type" in r.text.lower()


# ======================================================================
# /api/submit-link/w/{week}/{type} resolver
# ======================================================================
class TestStableSubmitLinkResolver:
    def test_unknown_type_returns_400(self, seed):
        r = requests.get(
            f"{BASE_URL}/api/submit-link/w/3/definitely_bad_type",
            timeout=15,
        )
        assert r.status_code == 400
        assert "submission_type must be one of" in r.text

    def test_no_material_returns_404(self, seed):
        # Use a very high week that has no material
        r = requests.get(
            f"{BASE_URL}/api/submit-link/w/13/case_activity",
            params={"cohort_id": seed["ids"]["cohort"]},
            timeout=15,
        )
        assert r.status_code == 404
        assert "No assignment matches" in r.text

    def test_match_returns_material_id(self, seed):
        # Create a homework material with the target type for week 5
        title = f"{TEST_PREFIX}HW_stable_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=5,
            submission_type="case_activity",
        )
        assert cr.status_code == 200, cr.text
        mid = cr.json()["material_id"]
        r = requests.get(
            f"{BASE_URL}/api/submit-link/w/5/case_activity",
            params={"cohort_id": seed["ids"]["cohort"]},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("material_id") == mid


# ======================================================================
# GET /api/submit-link/{material_id} returns submission_type + fields
# ======================================================================
class TestGetSubmitLinkInfo:
    def test_returns_submission_type_and_fields(self, seed):
        fields = [
            {"id": "q1", "label": "Startup name?", "type": "text", "required": True}
        ]
        title = f"{TEST_PREFIX}HW_infoQ_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=4,
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert cr.status_code == 200
        mid = cr.json()["material_id"]
        r = requests.get(f"{BASE_URL}/api/submit-link/{mid}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["submission_type"] == "business_questionnaire"
        assert isinstance(data["questionnaire_fields"], list)
        assert len(data["questionnaire_fields"]) == 1
        assert data["questionnaire_fields"][0]["label"] == "Startup name?"


# ======================================================================
# POST /api/materials/{id}/submit — per-type extension validation
# ======================================================================
def _submit_file(material_id, token, filename, content, cohort_id, content_type="application/octet-stream"):
    files = {"file": (filename, content, content_type)}
    params = {"cohort_id": cohort_id}
    return requests.post(
        f"{BASE_URL}/api/materials/{material_id}/submit",
        params=params, files=files, headers=_auth(token), timeout=30,
    )


class TestSubmissionExtensionValidation:
    def test_pitch_rejects_pdf(self, seed):
        title = f"{TEST_PREFIX}HW_pitch_reject_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=6, submission_type="60_second_pitch",
        )
        mid = cr.json()["material_id"]
        r = _submit_file(mid, seed["tokens"]["student"], f"{TEST_PREFIX}bad.pdf",
                         _tiny_pdf_bytes(), seed["ids"]["cohort"], "application/pdf")
        assert r.status_code == 400
        # Detail should list allowed extensions
        assert "mp4" in r.text.lower() or "wav" in r.text.lower()

    def test_pitch_accepts_mp4(self, seed):
        title = f"{TEST_PREFIX}HW_pitch_accept_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=6, submission_type="60_second_pitch",
        )
        mid = cr.json()["material_id"]
        r = _submit_file(mid, seed["tokens"]["student"], f"{TEST_PREFIX}pitch.mp4",
                         _tiny_mp4_bytes(), seed["ids"]["cohort"], "video/mp4")
        assert r.status_code == 200, r.text

    def test_slide_deck_accepts_pdf_and_pptx_rejects_mp4(self, seed):
        title = f"{TEST_PREFIX}HW_deck_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=7, submission_type="10_slide_pitch",
        )
        mid = cr.json()["material_id"]
        r_pdf = _submit_file(mid, seed["tokens"]["student"], f"{TEST_PREFIX}deck.pdf",
                             _tiny_pdf_bytes(), seed["ids"]["cohort"], "application/pdf")
        assert r_pdf.status_code == 200, r_pdf.text
        r_pptx = _submit_file(mid, seed["tokens"]["student"], f"{TEST_PREFIX}deck.pptx",
                              _tiny_pptx_bytes(), seed["ids"]["cohort"],
                              "application/vnd.openxmlformats-officedocument.presentationml.presentation")
        assert r_pptx.status_code == 200, r_pptx.text
        r_mp4 = _submit_file(mid, seed["tokens"]["student"], f"{TEST_PREFIX}bad.mp4",
                             _tiny_mp4_bytes(), seed["ids"]["cohort"], "video/mp4")
        assert r_mp4.status_code == 400

    def test_case_activity_accepts_pdf_docx_txt(self, seed):
        title = f"{TEST_PREFIX}HW_case_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=8, submission_type="case_activity",
        )
        mid = cr.json()["material_id"]
        for ext, mime, content in [
            ("pdf", "application/pdf", _tiny_pdf_bytes()),
            ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", _tiny_docx_bytes()),
            ("txt", "text/plain", _tiny_txt_bytes()),
        ]:
            r = _submit_file(mid, seed["tokens"]["student"],
                             f"{TEST_PREFIX}case.{ext}", content,
                             seed["ids"]["cohort"], mime)
            assert r.status_code == 200, f"{ext}: {r.text}"


# ======================================================================
# Questionnaire submission: no file, answers required-field, size cap
# ======================================================================
def _submit_questionnaire(material_id, token, answers_dict, cohort_id):
    data = {"questionnaire_answers": json.dumps(answers_dict)}
    params = {"cohort_id": cohort_id}
    # Note: no file argument
    return requests.post(
        f"{BASE_URL}/api/materials/{material_id}/submit",
        params=params, data=data, headers=_auth(token), timeout=30,
    )


class TestQuestionnaireSubmission:
    @pytest.fixture(scope="class")
    def q_material(self, seed):
        fields = [
            {"id": "q1", "label": "Startup name?", "type": "text", "required": True},
            {"id": "q2", "label": "Elevator pitch", "type": "longtext", "required": False},
        ]
        title = f"{TEST_PREFIX}HW_Qsub_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=9,
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        assert cr.status_code == 200, cr.text
        return cr.json()["material_id"]

    def test_missing_required_returns_400(self, seed, q_material):
        r = _submit_questionnaire(
            q_material, seed["tokens"]["student"],
            {"q2": "some pitch text"},  # q1 is required, missing
            seed["ids"]["cohort"],
        )
        assert r.status_code == 400
        assert "Startup name?" in r.text

    def test_over_5000_chars_returns_400(self, seed, q_material):
        r = _submit_questionnaire(
            q_material, seed["tokens"]["student"],
            {"q1": "x" * 5001, "q2": ""},
            seed["ids"]["cohort"],
        )
        assert r.status_code == 400
        assert "5000" in r.text

    def test_successful_submit_persists_answers(self, seed, q_material):
        r = _submit_questionnaire(
            q_material, seed["tokens"]["student"],
            {"q1": "Acme Startup", "q2": "We do X for Y."},
            seed["ids"]["cohort"],
        )
        assert r.status_code == 200, r.text
        sub_id = r.json().get("submission_id")
        assert sub_id
        sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert sub is not None
        assert sub["submission_type"] == "business_questionnaire"
        assert sub["questionnaire_answers"]["q1"] == "Acme Startup"
        assert sub["questionnaire_answers"]["q2"] == "We do X for Y."

    def test_download_returns_json_payload(self, seed, q_material):
        # Ensure a submission exists
        r = _submit_questionnaire(
            q_material, seed["tokens"]["student"],
            {"q1": "Acme2", "q2": "Elevator2"},
            seed["ids"]["cohort"],
        )
        assert r.status_code == 200
        sub_id = r.json()["submission_id"]
        dr = requests.get(
            f"{BASE_URL}/api/submissions/{sub_id}/download",
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert dr.status_code == 200, dr.text
        assert "application/json" in dr.headers.get("Content-Type", "")
        payload = dr.json()
        # Should contain Q/A structure
        payload_text = json.dumps(payload)
        assert "Startup name?" in payload_text or "q1" in payload_text
        assert "Acme2" in payload_text

    def test_preview_text_synthesizes_qa(self, seed, q_material):
        r = _submit_questionnaire(
            q_material, seed["tokens"]["student"],
            {"q1": "Acme3", "q2": "Pitch3"},
            seed["ids"]["cohort"],
        )
        assert r.status_code == 200
        sub_id = r.json()["submission_id"]
        pr = requests.get(
            f"{BASE_URL}/api/submissions/{sub_id}/preview-text",
            headers=_auth(seed["tokens"]["instructor"]), timeout=15,
        )
        assert pr.status_code == 200, pr.text
        data = pr.json()
        txt = data.get("text", "")
        assert "Q:" in txt and "A:" in txt
        assert "Startup name?" in txt
        assert "Acme3" in txt


# ======================================================================
# Manual /submissions/{id}/review on questionnaire submission
# ======================================================================
class TestManualReviewOnQuestionnaire:
    def test_manual_review_uses_synthesized_text(self, seed):
        # Setup a questionnaire homework + successful student submission
        fields = [
            {"id": "q1", "label": "What problem?", "type": "text", "required": True},
            {"id": "q2", "label": "Who is your customer?", "type": "longtext", "required": True},
        ]
        title = f"{TEST_PREFIX}HW_review_{uuid.uuid4().hex[:6]}"
        cr = _upload_cohort_material(
            seed["ids"]["cohort"], seed["tokens"]["instructor"],
            material_type="homework", title=title,
            week_number=10,
            submission_type="business_questionnaire",
            questionnaire_fields=json.dumps(fields),
        )
        mid = cr.json()["material_id"]
        sr = _submit_questionnaire(
            mid, seed["tokens"]["student"],
            {"q1": "Small business owners struggle to file taxes efficiently.",
             "q2": "SMB owners in the US with revenue between $50K-500K annually."},
            seed["ids"]["cohort"],
        )
        assert sr.status_code == 200, sr.text
        sub_id = sr.json()["submission_id"]

        # Trigger manual review
        rev = requests.post(
            f"{BASE_URL}/api/submissions/{sub_id}/review",
            headers=_auth(seed["tokens"]["instructor"]), timeout=90,
        )
        # If the manual review path doesn't handle questionnaires, we'll see a 4xx/5xx here
        assert rev.status_code == 200, f"Manual review failed on questionnaire submission: {rev.status_code} {rev.text}"

        # Confirm ai_feedback populated (or at least non-empty via DB)
        sub = db.submissions.find_one({"submission_id": sub_id}, {"_id": 0})
        assert sub is not None
        ai_fb = (sub.get("ai_feedback") or "").strip()
        assert ai_fb, f"ai_feedback empty after manual review; sub={sub}"
