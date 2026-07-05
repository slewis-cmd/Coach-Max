"""
Test Suite for Platform Branding (SaaS white-label layer)

Covers:
- GET  /api/settings/branding (public, defaults on fresh install)
- PUT  /api/settings/branding ACL (401 unauth, 403 instructor, 200 super_admin)
- PUT  merges partial payload + persists (verified via subsequent GET)
- PUT  rejects payload with only unknown fields (400)
- 30s in-process cache -- 5 rapid GETs identical
- Persona injection -- POST /api/chat/ask-tutor still succeeds with override active
- Email sender -- POST /api/submissions/{id}/send-feedback still succeeds with override
- Regression: default persona chat + default sender name email
- AI system_prompt override does not break chat

Teardown restores the DEFAULT_BRANDING document + deletes all TEST_ data.
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

TEST_PREFIX = "TEST_BRAND_"

DEFAULT_BRANDING = {
    "app_name": "The Boost Pad",
    "ai_persona_name": "Coach Max",
    "primary_color": "#22438E",
    "logo_url": "",
    "favicon_url": "",
    "email_sender_name": "The Boost Pad",
    "tagline": "AI-powered learning coach",
    "ai_system_prompt": (
        "You are {persona}, a friendly, supportive AI tutor for a leadership development course."
    ),
}


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def seed():
    """Seed super admin / instructor / student + cohort + material + graded submission."""
    ts = int(datetime.now().timestamp())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()

    ids = {
        "super_admin": f"{TEST_PREFIX}sa_{ts}",
        "instructor":  f"{TEST_PREFIX}inst_{ts}",
        "student":     f"{TEST_PREFIX}stu_{ts}",
        "cohort":      f"{TEST_PREFIX}cohort_{ts}",
        "material":    f"{TEST_PREFIX}mat_{ts}",
        "submission":  f"{TEST_PREFIX}sub_{ts}",
    }
    tokens = {
        "super_admin": f"{TEST_PREFIX}tok_sa_{ts}",
        "instructor":  f"{TEST_PREFIX}tok_inst_{ts}",
        "student":     f"{TEST_PREFIX}tok_stu_{ts}",
    }

    # Users
    db.users.insert_many([
        {"user_id": ids["super_admin"], "email": f"{TEST_PREFIX}sa_{ts}@x.com",
         "name": "Test Admin", "role": "super_admin",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["instructor"], "email": f"{TEST_PREFIX}inst_{ts}@x.com",
         "name": "Test Instructor", "role": "instructor",
         "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["student"], "email": f"{TEST_PREFIX}stu_{ts}@x.com",
         "name": "Test Student", "role": "student", "language_preference": "en",
         "created_at": datetime.now(timezone.utc).isoformat()},
    ])
    # Sessions
    db.user_sessions.insert_many([
        {"user_id": ids["super_admin"], "session_token": tokens["super_admin"],
         "expires_at": expires_at, "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["instructor"], "session_token": tokens["instructor"],
         "expires_at": expires_at, "created_at": datetime.now(timezone.utc).isoformat()},
        {"user_id": ids["student"], "session_token": tokens["student"],
         "expires_at": expires_at, "created_at": datetime.now(timezone.utc).isoformat()},
    ])

    # Cohort with student + instructor
    db.cohorts.insert_one({
        "cohort_id": ids["cohort"],
        "name": f"{TEST_PREFIX}Cohort_{ts}",
        "instructor_id": ids["instructor"],
        "instructor_ids": [ids["instructor"]],
        "student_ids": [ids["student"]],
        "released_weeks": [1],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Homework material (week 1)
    db.materials.insert_one({
        "material_id": ids["material"],
        "cohort_id": ids["cohort"],
        "title": f"{TEST_PREFIX}HW_{ts}",
        "material_type": "homework",
        "week_number": 1,
        "content": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Submission already reviewed + sent (allows both chat + resend-feedback paths)
    db.submissions.insert_one({
        "submission_id": ids["submission"],
        "student_id": ids["student"],
        "cohort_id": ids["cohort"],
        "material_id": ids["material"],
        "status": "sent",
        "content": "Student submission body — testing branding overrides.",
        "instructor_feedback": "Great work — this is instructor edited feedback for the branding test.",
        "ai_feedback": "AI-generated fallback feedback.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    yield {"ids": ids, "tokens": tokens}

    # ---------------- Teardown ----------------
    # 1. Restore defaults via API (also invalidates the in-process cache).
    try:
        requests.put(
            f"{BASE_URL}/api/settings/branding",
            json=DEFAULT_BRANDING,
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
            timeout=10,
        )
    except Exception as e:
        print(f"Teardown restore-branding failed (non-fatal): {e}")
    # 2. Extra safety: remove the branding doc entirely so the module truly falls back to defaults.
    db.platform_settings.delete_one({"_id": "branding"})
    # 3. Delete TEST_ seed data.
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.materials.delete_many({"material_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.submissions.delete_many({"submission_id": {"$regex": f"^{TEST_PREFIX}"}})


@pytest.fixture(autouse=True)
def reset_branding_before_each(seed):
    """Wipe the platform_settings doc + force cache refresh before every test."""
    db.platform_settings.delete_one({"_id": "branding"})
    # First GET after cache TTL (or after any PUT) reloads from DB.
    # We wait a short moment and hit GET to reseed the cache to defaults.
    # But PUT below within tests will explicitly invalidate the cache — so
    # we do nothing more here; some tests want the pure default state.
    yield


# ----------------------------------------------------------------------
# GET /api/settings/branding
# ----------------------------------------------------------------------
class TestGetBranding:
    def test_get_public_no_auth(self):
        """Endpoint is public — no auth header, should be 200."""
        r = requests.get(f"{BASE_URL}/api/settings/branding", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        # Defaults present on fresh state
        for k, v in DEFAULT_BRANDING.items():
            assert k in data, f"missing field {k}"
            assert data[k] == v, f"{k} default mismatch: got {data[k]!r} expected {v!r}"

    def test_get_returns_json_dict(self):
        r = requests.get(f"{BASE_URL}/api/settings/branding", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), dict)


# ----------------------------------------------------------------------
# PUT /api/settings/branding — access control
# ----------------------------------------------------------------------
class TestPutBrandingAccessControl:
    def test_put_no_token_returns_401(self):
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"app_name": "Nope"},
            timeout=10,
        )
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"

    def test_put_as_instructor_returns_403(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"app_name": "InstructorTry"},
            headers={"Authorization": f"Bearer {seed['tokens']['instructor']}"},
            timeout=10,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_put_as_student_returns_403(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"app_name": "StudentTry"},
            headers={"Authorization": f"Bearer {seed['tokens']['student']}"},
            timeout=10,
        )
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"


# ----------------------------------------------------------------------
# PUT — merge / persist / filter
# ----------------------------------------------------------------------
class TestPutBrandingUpdates:
    def test_put_partial_payload_persists_and_merges(self, seed):
        payload = {"app_name": "My Professor", "ai_persona_name": "Prof X"}
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json=payload,
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # Response is merged
        assert body["app_name"] == "My Professor"
        assert body["ai_persona_name"] == "Prof X"
        # Untouched fields keep defaults
        assert body["primary_color"] == DEFAULT_BRANDING["primary_color"]
        assert body["email_sender_name"] == DEFAULT_BRANDING["email_sender_name"]

        # Persisted — subsequent GET reflects the change
        r2 = requests.get(f"{BASE_URL}/api/settings/branding", timeout=10)
        assert r2.status_code == 200
        got = r2.json()
        assert got["app_name"] == "My Professor"
        assert got["ai_persona_name"] == "Prof X"
        assert got["primary_color"] == DEFAULT_BRANDING["primary_color"]

    def test_put_filters_unknown_fields_returns_400(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"some_unknown_field": "x", "another_junk": 1},
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        assert "no valid branding fields" in detail or "branding" in detail

    def test_put_mixed_payload_filters_unknown_but_keeps_valid(self, seed):
        r = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"app_name": "Mixed", "unknown_junk": "y"},
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["app_name"] == "Mixed"
        assert "unknown_junk" not in body


# ----------------------------------------------------------------------
# Cache behaviour
# ----------------------------------------------------------------------
class TestBrandingCache:
    def test_five_rapid_gets_consistent(self):
        """The 30s cache in get_branding() should return identical bodies."""
        bodies = []
        for _ in range(5):
            r = requests.get(f"{BASE_URL}/api/settings/branding", timeout=10)
            assert r.status_code == 200
            bodies.append(r.json())
        first = bodies[0]
        for b in bodies[1:]:
            assert b == first, "branding responses drifted within cache window"


# ----------------------------------------------------------------------
# Persona injection into Coach Max chat
# ----------------------------------------------------------------------
class TestPersonaInjectionChat:
    def _chat(self, token, submission_id, message="Hi coach, quick test."):
        return requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            json={"message": message, "submission_id": submission_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=90,   # LLM latency
        )

    def test_chat_default_persona_regression(self, seed):
        """Regression: default persona should not break chat."""
        r = self._chat(seed["tokens"]["student"], seed["ids"]["submission"],
                       "Give me one bullet of encouragement.")
        if r.status_code == 500 and "unavailable" in r.text.lower():
            pytest.skip("LLM unavailable (Coach Max upstream) — auth+persona path validated separately")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "response" in body and isinstance(body["response"], str) and body["response"]

    def test_chat_with_persona_override_succeeds(self, seed):
        """Override persona -> chat still 200; DB write happens."""
        put = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"ai_persona_name": "Prof X"},
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert put.status_code == 200

        r = self._chat(seed["tokens"]["student"], seed["ids"]["submission"],
                       "Persona test — one sentence.")
        if r.status_code == 500 and "unavailable" in r.text.lower():
            pytest.skip("LLM unavailable")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("response")

        # Verify the chat entry was persisted (uses the same code path that stores it).
        stored = db.tutor_chats.find_one({"submission_id": seed["ids"]["submission"]})
        assert stored is not None
        assert stored.get("student_id") == seed["ids"]["student"]

    def test_chat_with_system_prompt_override_succeeds(self, seed):
        """Set ai_system_prompt override — chat should still 200."""
        put = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={
                "ai_persona_name": "Prof X",
                "ai_system_prompt": "You are {persona}, a strict TA. Answer in one sentence.",
            },
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert put.status_code == 200

        r = self._chat(seed["tokens"]["student"], seed["ids"]["submission"],
                       "System prompt override test.")
        if r.status_code == 500 and "unavailable" in r.text.lower():
            pytest.skip("LLM unavailable")
        assert r.status_code == 200, r.text
        assert r.json().get("response")


# ----------------------------------------------------------------------
# Email sender-name override
# ----------------------------------------------------------------------
class TestEmailSenderOverride:
    def test_send_feedback_with_default_sender_regression(self, seed):
        """Regression: send-feedback works with default sender name."""
        r = requests.post(
            f"{BASE_URL}/api/submissions/{seed['ids']['submission']}/send-feedback",
            headers={"Authorization": f"Bearer {seed['tokens']['instructor']}"},
            timeout=30,
        )
        # Accept 200 (email sent or gracefully skipped when RESEND_API_KEY missing).
        assert r.status_code == 200, f"send-feedback failed: {r.status_code} {r.text}"
        assert "sent" in (r.json().get("message", "").lower())

    def test_send_feedback_with_custom_sender_succeeds(self, seed):
        """Override email_sender_name -> endpoint should still 200."""
        put = requests.put(
            f"{BASE_URL}/api/settings/branding",
            json={"email_sender_name": "My Professor"},
            headers={"Authorization": f"Bearer {seed['tokens']['super_admin']}"},
            timeout=10,
        )
        assert put.status_code == 200
        assert put.json()["email_sender_name"] == "My Professor"

        r = requests.post(
            f"{BASE_URL}/api/submissions/{seed['ids']['submission']}/send-feedback",
            headers={"Authorization": f"Bearer {seed['tokens']['instructor']}"},
            timeout=30,
        )
        assert r.status_code == 200, f"send-feedback with custom sender failed: {r.status_code} {r.text}"
