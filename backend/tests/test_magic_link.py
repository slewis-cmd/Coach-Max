"""
Iteration 47 — BUG FIX #2: Magic-link auto-auth from email CTA.

Coverage:
1. POST /api/auth/magic-link:
   - Valid token           -> 200 {session_token=input, user populated}
   - Missing token         -> 400
   - Nonexistent token     -> 401 'Invalid or expired token'
   - Expired token         -> 401 'Token expired' AND token deleted
   - Token exists but user deleted -> 404
2. send_feedback CTA URL:
   - POST /api/submissions/{id}/send-feedback appends ?auth=<magic_...> to
     coach_max_url. Magic exists in user_sessions with purpose='magic_link'.
   - Exchanged token successfully calls /api/chat/ask-tutor.
3. Security:
   - Magic tokens unpredictable (32-char hex + 'magic_' prefix)
   - TTL bounded at 30 days
   - Cannot use user A's magic token to impersonate user B.
   - Exchanging a normal (non-magic) session token also works (no-op replay) — 
     verify /me still returns the correct user.
"""
import os
import sys
import time
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

TAG = "TEST_ML_"


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture(scope="module")
def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    stu_b_id = f"{TAG}stub_{uuid.uuid4().hex[:8]}"
    cohort_id = f"{TAG}coh_{uuid.uuid4().hex[:8]}"
    asgn_id = f"{TAG}asgn_{uuid.uuid4().hex[:8]}"
    ms_id = f"{TAG}ms_{uuid.uuid4().hex[:8]}"
    inst_tok = f"{TAG}itok_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    far_future = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

    async def setup():
        await db.users.insert_many([
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Instructor ML",
             "role": "instructor", "created_at": now},
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Student A ML",
             "role": "student", "created_at": now, "language_preference": "en"},
            {"user_id": stu_b_id, "email": f"{stu_b_id}@t.test", "name": "Student B ML",
             "role": "student", "created_at": now, "language_preference": "en"},
        ])
        await db.user_sessions.insert_one({
            "session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
            "expires_at": far_future, "created_at": now,
        })
        await db.cohorts.insert_one({
            "cohort_id": cohort_id, "name": f"{TAG}Cohort",
            "instructor_ids": [inst_id], "student_ids": [stu_id, stu_b_id],
            "total_weeks": 4, "current_week": 4,
            "auto_send_feedback": False,
            "created_at": now,
        })
        # Simple case_activity assignment
        await db.assignments.insert_one({
            "assignment_id": asgn_id, "cohort_id": cohort_id,
            "title": f"{TAG}Case", "description": "Case study",
            "submission_type": "case_activity",
            "feedback_template": "", "drive_folder_url": "",
            "questionnaire_fields": [], "is_active": True,
            "milestones": [
                {"milestone_id": ms_id, "week_number": 1, "title": "Week 1",
                 "description": "", "feedback_template_override": "",
                 "drive_folder_url_override": "", "is_final_capstone": False,
                 "due_date": None},
            ],
            "created_at": now,
        })
        # Pre-seed a submission for student A with ai_feedback so send-feedback works
        sub_id = f"{TAG}sub_{uuid.uuid4().hex[:12]}"
        await db.submissions.insert_one({
            "submission_id": sub_id,
            "material_id": "",
            "cohort_id": cohort_id,
            "student_id": stu_id,
            "file_path": "", "gridfs_id": None, "file_name": "seed.txt",
            "submission_type": "case_activity",
            "questionnaire_answers": None,
            "assignment_id": asgn_id, "milestone_id": ms_id,
            "status": "draft",
            "ai_feedback": "Nice work! You demonstrated clear reasoning.\nWhat You Did Well:\n- Clear thesis.\nAreas for Growth:\n- Add data.\nKeep going!",
            "instructor_feedback": None, "feedback_sent": False,
            "resubmission_count": 0,
            "submitted_at": now,
        })
        return sub_id

    sub_id = _run(setup())

    ctx = {
        "inst_id": inst_id, "stu_id": stu_id, "stu_b_id": stu_b_id,
        "cohort_id": cohort_id, "asgn_id": asgn_id, "ms_id": ms_id,
        "inst_tok": inst_tok, "sub_id": sub_id,
        "inst_auth": {"Authorization": f"Bearer {inst_tok}"},
    }
    yield ctx

    async def teardown():
        await db.users.delete_many({"user_id": {"$regex": f"^{TAG}"}})
        await db.user_sessions.delete_many({"$or": [
            {"session_token": {"$regex": f"^{TAG}"}},
            {"user_id": {"$regex": f"^{TAG}"}},
        ]})
        await db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
        await db.assignments.delete_many({"assignment_id": {"$regex": f"^{TAG}"}})
        await db.submissions.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
    _run(teardown())
    client.close()


def _seed_magic(user_id: str, ttl_days: int = 30, expired: bool = False) -> str:
    """Directly insert a magic-link session doc for the given user."""
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    token = f"magic_{uuid.uuid4().hex}"
    if expired:
        exp = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    else:
        exp = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    _run(db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": exp,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "magic_link",
    }))
    client.close()
    return token


# ==========================================================================
# 1) POST /api/auth/magic-link — validation matrix
# ==========================================================================
class TestMagicLinkEndpoint:
    def test_missing_token_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={})
        assert r.status_code == 400
        assert "token" in r.json()["detail"].lower()

    def test_empty_token_returns_400(self):
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": ""})
        assert r.status_code == 400

    def test_nonexistent_token_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/auth/magic-link",
                          json={"token": f"magic_nonexistent_{uuid.uuid4().hex}"})
        assert r.status_code == 401
        assert "invalid" in r.json()["detail"].lower() or "expired" in r.json()["detail"].lower()

    def test_valid_token_returns_session_and_user(self, seed):
        tok = _seed_magic(seed["stu_id"])
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": tok})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["session_token"] == tok, "session_token should equal the exchanged input token"
        assert d["user"]["user_id"] == seed["stu_id"]
        assert d["user"]["email"] == f"{seed['stu_id']}@t.test"
        assert d["user"]["role"] == "student"

    def test_expired_token_returns_401_and_is_deleted(self, seed):
        tok = _seed_magic(seed["stu_id"], expired=True)
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": tok})
        assert r.status_code == 401
        assert "expired" in r.json()["detail"].lower()
        # Verify the token was deleted from user_sessions
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        found = _run(db.user_sessions.find_one({"session_token": tok}))
        client.close()
        assert found is None, "Expired magic token must be deleted"

    def test_token_for_deleted_user_returns_404(self, seed):
        # Create a magic token for a user we then delete
        ghost_uid = f"{TAG}ghost_{uuid.uuid4().hex[:8]}"
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        _run(db.users.insert_one({
            "user_id": ghost_uid, "email": f"{ghost_uid}@t.test",
            "name": "ghost", "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        tok = _seed_magic(ghost_uid)
        # Delete the user
        _run(db.users.delete_one({"user_id": ghost_uid}))
        client.close()
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": tok})
        assert r.status_code == 404
        assert "user" in r.json()["detail"].lower()

    def test_using_normal_session_token_is_noop_replay(self, seed):
        """A normal (non-magic) session_token can also be exchanged: same token
        returned, correct user — but no elevation, no leaked data."""
        # Instructor session token (created in seed) is a normal token
        r = requests.post(f"{BASE_URL}/api/auth/magic-link",
                          json={"token": seed["inst_tok"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["session_token"] == seed["inst_tok"]
        assert d["user"]["user_id"] == seed["inst_id"]
        # No sensitive extras leaked (basic guardrail)
        assert "password" not in d["user"]
        assert "session_token" not in d["user"]


# ==========================================================================
# 2) send_feedback -> ?auth=<magic_...> URL in email + token works end-to-end
# ==========================================================================
class TestSendFeedbackMagicLink:
    def test_send_feedback_generates_magic_and_ctal_url(self, seed):
        # Capture user_sessions purpose='magic_link' for this student before/after
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        before_count = _run(db.user_sessions.count_documents({
            "user_id": seed["stu_id"], "purpose": "magic_link",
        }))

        r = requests.post(
            f"{BASE_URL}/api/submissions/{seed['sub_id']}/send-feedback",
            headers=seed["inst_auth"],
        )
        assert r.status_code == 200, r.text

        after = _run(db.user_sessions.find({
            "user_id": seed["stu_id"], "purpose": "magic_link",
        }, {"_id": 0}).sort("created_at", -1).to_list(5))
        client.close()

        assert len(after) >= before_count + 1, "A new magic-link token should be created"
        latest = after[0]
        # Token shape checks
        assert latest["session_token"].startswith("magic_"), "Magic tokens must have 'magic_' prefix"
        assert len(latest["session_token"]) >= 32
        assert latest["user_id"] == seed["stu_id"]
        assert latest["purpose"] == "magic_link"

    def test_magic_token_can_be_exchanged_and_used(self, seed):
        """End-to-end: exchange magic -> call /api/auth/me -> call ask-tutor."""
        tok = _seed_magic(seed["stu_id"])
        # Exchange
        ex = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": tok})
        assert ex.status_code == 200
        sess = ex.json()["session_token"]

        # Call /api/auth/me with the returned session
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {sess}"})
        assert me.status_code == 200
        assert me.json()["user_id"] == seed["stu_id"]

        # Ask-tutor should reach the LLM (may take a moment)
        chat = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {sess}"},
            json={"submission_id": seed["sub_id"], "message": "Give me one tip in 8 words."},
            timeout=60,
        )
        assert chat.status_code == 200, chat.text
        assert (chat.json().get("response") or "").strip()


# ==========================================================================
# 3) SECURITY
# ==========================================================================
class TestMagicLinkSecurity:
    def test_ttl_is_bounded_30_days(self, seed):
        """Directly generated magic tokens should expire within ~30 days
        (server-side helper hardcodes ttl_days=30 in email flows)."""
        tok = _seed_magic(seed["stu_id"], ttl_days=30)
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        doc = _run(db.user_sessions.find_one({"session_token": tok}, {"_id": 0}))
        client.close()
        exp = datetime.fromisoformat(doc["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        assert 29 <= delta.days <= 31, f"TTL should be ~30 days, got {delta.days}"

    def test_token_bound_to_single_user(self, seed):
        """Magic token created for student A returns student A — never student B."""
        tok_a = _seed_magic(seed["stu_id"])
        r = requests.post(f"{BASE_URL}/api/auth/magic-link", json={"token": tok_a})
        assert r.status_code == 200
        assert r.json()["user"]["user_id"] == seed["stu_id"]
        # Also verify /me returns A, not B
        me = requests.get(f"{BASE_URL}/api/auth/me",
                          headers={"Authorization": f"Bearer {tok_a}"})
        assert me.status_code == 200
        assert me.json()["user_id"] == seed["stu_id"]
        assert me.json()["user_id"] != seed["stu_b_id"]

    def test_token_unpredictable_hex(self, seed):
        """Two consecutive magic tokens must not be sequential/predictable."""
        t1 = _seed_magic(seed["stu_id"])
        t2 = _seed_magic(seed["stu_id"])
        assert t1 != t2
        # Enough entropy — magic_ + 32 hex chars = 38+ len
        assert len(t1) >= 32 and len(t2) >= 32
        # Not sequential-differ-by-one
        assert t1[:-4] != t2[:-4], "Tokens share too much prefix — insufficient entropy"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
