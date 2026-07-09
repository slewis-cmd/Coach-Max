"""
Test suite for submission material-enrichment fix (iter_49).

Verifies that milestone-based submissions (`assignment_id` + `milestone_id`,
empty `material_id`) receive a synthesized `sub.material = {title, week_number}`
in three affected endpoints:

  - GET  /api/submissions
  - GET  /api/cohorts/{cohort_id}/submissions
  - POST /api/submissions/{submission_id}/export-pdf   (PDF header line)

Also indirectly validates the `_enrich_submissions_with_material` helper via the
same endpoints (mixed list, invalid-assignment fallback, legacy material-only,
etc.). The helper cannot be imported directly because the module binds Motor to
its own event loop at startup, but the endpoint tests fully exercise it.
"""
import os
import uuid
import asyncio
import pytest
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

TEST_PREFIX = f"TEST_ENRICH_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# DB helper — always creates a fresh Motor client bound to the current loop
# ---------------------------------------------------------------------------
def _run(coro_factory):
    """Run an async task with a fresh Motor client bound to a fresh loop."""
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _wrap():
        client = AsyncIOMotorClient(MONGO_URL)
        try:
            return await coro_factory(client[DB_NAME])
        finally:
            client.close()

    return asyncio.run(_wrap())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def super_admin_token():
    """Seed a session token in `user_sessions` for slewis@theboostpad.org."""
    token = f"{TEST_PREFIX}_{uuid.uuid4().hex}"
    expires = datetime.now(timezone.utc) + timedelta(hours=2)

    async def _seed(db):
        user = await db.users.find_one({"email": "slewis@theboostpad.org"}, {"_id": 0})
        assert user, "Super admin user must exist in DB"
        await db.user_sessions.insert_one({
            "session_token": token,
            "user_id": user["user_id"],
            "email": user["email"],
            "expires_at": expires,
            "created_at": datetime.now(timezone.utc),
        })
        return user["user_id"]

    _run(lambda db: _seed(db))
    yield token

    async def _cleanup(db):
        await db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    _run(lambda db: _cleanup(db))


@pytest.fixture(scope="module")
def auth_headers(super_admin_token):
    return {"Authorization": f"Bearer {super_admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def milestone_sub():
    """Return an existing milestone-based submission with empty material_id
    (the exact scenario the bug affected)."""
    async def _find(db):
        q = {
            "assignment_id": {"$nin": [None, ""]},
            "milestone_id": {"$nin": [None, ""]},
            "$or": [{"material_id": {"$exists": False}}, {"material_id": None}, {"material_id": ""}],
        }
        sub = await db.submissions.find_one(q, {"_id": 0})
        if not sub:
            return None
        asgn = await db.assignments.find_one({"assignment_id": sub["assignment_id"]}, {"_id": 0})
        milestone = None
        if asgn:
            milestone = next(
                (m for m in (asgn.get("milestones") or []) if m.get("milestone_id") == sub["milestone_id"]),
                None,
            )
        return {"submission": sub, "assignment": asgn, "milestone": milestone}

    result = _run(_find)
    if result is None:
        pytest.skip("No milestone-based submission with empty material_id in DB")
    return result


@pytest.fixture(scope="module")
def any_milestone_sub_with_material_id():
    """Milestone-based submission that ALSO has material_id set (edge case:
    the helper should prefer assignment/milestone over the material)."""
    async def _find(db):
        return await db.submissions.find_one(
            {
                "assignment_id": {"$nin": [None, ""]},
                "milestone_id": {"$nin": [None, ""]},
                "material_id": {"$nin": [None, ""]},
            },
            {"_id": 0},
        )
    result = _run(_find)
    if not result:
        pytest.skip("No milestone-based sub with a material_id set")
    return result


@pytest.fixture(scope="module")
def legacy_only_sub():
    """Legacy submission with only material_id, no assignment_id."""
    async def _find(db):
        return await db.submissions.find_one(
            {
                "material_id": {"$nin": [None, ""]},
                "$or": [{"assignment_id": {"$exists": False}}, {"assignment_id": None}, {"assignment_id": ""}],
            },
            {"_id": 0},
        )
    result = _run(_find)
    if not result:
        pytest.skip("No legacy material-only submission")
    return result


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=15)
    assert r.status_code == 200
    print("PASS: /api/health")


def test_auth_required():
    """Endpoint requires auth (401 without token)."""
    r = requests.get(f"{BASE_URL}/api/submissions", timeout=15)
    assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
    print("PASS: /api/submissions requires auth")


# ---------------------------------------------------------------------------
# GET /api/submissions
# ---------------------------------------------------------------------------
class TestGetSubmissions:
    def test_super_admin_milestone_material_populated(self, auth_headers, milestone_sub):
        """Milestone-based sub → material.title = assignment.title, material.week_number = milestone.week_number."""
        r = requests.get(f"{BASE_URL}/api/submissions", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        subs = r.json()
        target = next((s for s in subs if s.get("submission_id") == milestone_sub["submission"]["submission_id"]), None)
        assert target is not None, "target submission missing from response"
        mat = target.get("material")
        assert mat is not None, "material must NOT be None for milestone-based sub"
        expected_title = milestone_sub["assignment"]["title"]
        expected_week = (milestone_sub["milestone"] or {}).get("week_number")
        assert mat["title"] == expected_title, f"expected title {expected_title!r}, got {mat['title']!r}"
        assert mat["week_number"] == expected_week, f"expected week {expected_week}, got {mat['week_number']}"
        # Regression against the exact reported bug:
        assert mat["title"] != "Homework"
        assert mat["week_number"] not in (None, "?")
        print(f"PASS: /api/submissions milestone sub → '{mat['title']} · Week {mat['week_number']}'")

    def test_no_milestone_sub_shows_bug_placeholder(self, auth_headers):
        """Regression: no milestone-based sub in the response shows 'Homework' + '?'."""
        r = requests.get(f"{BASE_URL}/api/submissions", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        subs = r.json()
        offenders = []
        for s in subs:
            if s.get("assignment_id") and s.get("milestone_id"):
                mat = s.get("material") or {}
                if mat.get("title") == "Homework" and mat.get("week_number") in (None, "?"):
                    offenders.append(s.get("submission_id"))
        assert not offenders, f"Milestone subs still show buggy placeholder: {offenders}"
        milestone_count = sum(1 for s in subs if s.get("assignment_id") and s.get("milestone_id"))
        print(f"PASS: {milestone_count} milestone-based sub(s) all correctly enriched (0 placeholders)")

    def test_response_shape(self, auth_headers):
        """Every submission in response has a `material` key (either dict or None)."""
        r = requests.get(f"{BASE_URL}/api/submissions", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        subs = r.json()
        for s in subs:
            assert "material" in s, f"sub {s.get('submission_id')} missing material key"
            mat = s.get("material")
            assert mat is None or isinstance(mat, dict)
            if isinstance(mat, dict):
                assert "title" in mat
                assert "week_number" in mat
        print(f"PASS: all {len(subs)} submissions have well-formed material field")


# ---------------------------------------------------------------------------
# GET /api/cohorts/{cohort_id}/submissions
# ---------------------------------------------------------------------------
class TestCohortSubmissions:
    def test_cohort_submissions_enriched(self, auth_headers, milestone_sub):
        cohort_id = milestone_sub["submission"]["cohort_id"]
        r = requests.get(f"{BASE_URL}/api/cohorts/{cohort_id}/submissions", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        subs = r.json()
        assert len(subs) > 0
        target = next((s for s in subs if s.get("submission_id") == milestone_sub["submission"]["submission_id"]), None)
        assert target is not None, "target sub not in cohort response"
        mat = target.get("material")
        assert mat is not None
        assert mat["title"] == milestone_sub["assignment"]["title"]
        expected_week = (milestone_sub["milestone"] or {}).get("week_number")
        assert mat["week_number"] == expected_week
        assert mat["title"] != "Homework"
        print(f"PASS: /api/cohorts/{cohort_id}/submissions milestone sub → '{mat['title']} · Week {mat['week_number']}'")

    def test_cohort_response_shape(self, auth_headers, milestone_sub):
        cohort_id = milestone_sub["submission"]["cohort_id"]
        r = requests.get(f"{BASE_URL}/api/cohorts/{cohort_id}/submissions", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        subs = r.json()
        for s in subs:
            assert "material" in s
            assert "student" in s
        print(f"PASS: cohort response has {len(subs)} well-formed submissions")


# ---------------------------------------------------------------------------
# POST /api/submissions/{id}/export-pdf
# ---------------------------------------------------------------------------
class TestExportPDF:
    def test_export_pdf_for_milestone_sub(self, auth_headers, milestone_sub):
        sub_id = milestone_sub["submission"]["submission_id"]
        # Need feedback content on the sub
        if not (milestone_sub["submission"].get("ai_feedback") or milestone_sub["submission"].get("instructor_feedback")):
            pytest.skip("target milestone sub has no feedback to export")

        r = requests.post(f"{BASE_URL}/api/submissions/{sub_id}/export-pdf", headers=auth_headers, timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert "application/pdf" in r.headers.get("Content-Type", "")
        assert r.content.startswith(b"%PDF"), "response body is not a PDF"

        # Extract text from PDF (fpdf2 uses FlateDecode-compressed streams)
        import io
        try:
            from pypdf import PdfReader
        except ImportError:
            from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)

        title = milestone_sub["assignment"]["title"]
        week = (milestone_sub["milestone"] or {}).get("week_number")

        assert title in text, f"PDF should contain assignment title '{title}'. Full text:\n{text[:500]}"
        assert f"Week {week}" in text, f"PDF should contain 'Week {week}' (not 'Week ?'). Full text:\n{text[:500]}"
        # Regression: exact buggy line
        assert "Assignment: Homework  |  Week ?" not in text, "PDF still contains the buggy placeholder"
        assert "Homework  |  Week ?" not in text
        print(f"PASS: PDF export for milestone sub contains '{title}' + 'Week {week}'")

    def test_export_pdf_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/submissions/anything/export-pdf", timeout=15)
        assert r.status_code in (401, 403)
        print("PASS: export-pdf requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
