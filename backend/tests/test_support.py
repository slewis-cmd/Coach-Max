"""
Iteration 51 — Platform Support Bot + Escalation feature.

Covers:
  BACKEND POST /api/support/chat: auth-required, GPT-5.2 real call, history bounded,
    platform-only boundary (redirect to Coach Max for coaching questions),
    platform navigation Q answered correctly.
  BACKEND POST /api/support/escalate: auth-required, creates ticket row,
    truncates conversation, 400 on empty, subject fallback.
  BACKEND GET /api/admin/support/tickets: super_admin only, status filter,
    DESC sort.
  BACKEND PATCH /api/admin/support/tickets/{id}: super_admin only, status/notes,
    resolved_at set/cleared, 400 invalid, 404 missing.

GPT-5.2 budget: 3 real LLM calls (chat basic, coaching boundary, platform nav).
"""

import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

TAG = "TEST_SUPPORT_"


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
    db_ = client[DB_NAME]

    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    admin_id = f"{TAG}adm_{uuid.uuid4().hex[:8]}"
    stu_tok = f"{TAG}stok_{uuid.uuid4().hex[:10]}"
    inst_tok = f"{TAG}itok_{uuid.uuid4().hex[:10]}"
    adm_tok = f"{TAG}atok_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    expires = (datetime.now(timezone.utc).replace(year=datetime.now().year + 1)).isoformat()

    async def setup():
        await db_.users.insert_many([
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Sam Student",
             "role": "student", "created_at": now},
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Ivy Instructor",
             "role": "instructor", "created_at": now},
            {"user_id": admin_id, "email": f"{admin_id}@t.test", "name": "Sara Admin",
             "role": "super_admin", "created_at": now},
        ])
        await db_.user_sessions.insert_many([
            {"session_token": stu_tok, "user_id": stu_id, "email": f"{stu_id}@t.test",
             "expires_at": expires, "created_at": now},
            {"session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
             "expires_at": expires, "created_at": now},
            {"session_token": adm_tok, "user_id": admin_id, "email": f"{admin_id}@t.test",
             "expires_at": expires, "created_at": now},
        ])

    _run(setup())

    yield {
        "stu_id": stu_id, "inst_id": inst_id, "admin_id": admin_id,
        "stu_tok": stu_tok, "inst_tok": inst_tok, "adm_tok": adm_tok,
    }

    async def teardown():
        await db_.users.delete_many({"user_id": {"$in": [stu_id, inst_id, admin_id]}})
        await db_.user_sessions.delete_many({"session_token": {"$in": [stu_tok, inst_tok, adm_tok]}})
        await db_.support_tickets.delete_many({"user_id": {"$in": [stu_id, inst_id, admin_id]}})

    _run(teardown())
    client.close()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ==================== /api/support/chat ====================

class TestSupportChat:
    def test_chat_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/support/chat",
                          json={"message": "hi", "history": []}, timeout=10)
        assert r.status_code == 401, r.text

    def test_chat_empty_message_400(self, seed):
        r = requests.post(f"{BASE_URL}/api/support/chat",
                          headers=_hdr(seed["stu_tok"]),
                          json={"message": "", "history": []}, timeout=10)
        assert r.status_code == 400, r.text

    def test_chat_platform_navigation_answer(self, seed):
        """Bot should answer HOW-TO navigation questions (real GPT-5.2 call)."""
        r = requests.post(f"{BASE_URL}/api/support/chat",
                          headers=_hdr(seed["stu_tok"]),
                          json={"message": "How do I submit my 60-second pitch?",
                                "history": []}, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "response" in body
        text = body["response"].lower()
        # Should contain navigation hints (assignments, submit, upload...).
        assert any(k in text for k in [
            "assignment", "milestone", "submit", "upload", "click", "thinkific", "my assignments"
        ]), f"Response lacks navigation guidance: {body['response'][:400]}"
        assert len(body["response"]) > 20

    def test_chat_boundary_redirects_to_coach_max(self, seed):
        """Bot must REFUSE content coaching and redirect to Coach Max (real GPT-5.2 call)."""
        r = requests.post(f"{BASE_URL}/api/support/chat",
                          headers=_hdr(seed["stu_tok"]),
                          json={"message": "How should I improve my pitch's value proposition?",
                                "history": []}, timeout=60)
        assert r.status_code == 200, r.text
        text = r.json()["response"].lower()
        assert "coach max" in text, f"Should redirect to Coach Max, got: {text[:400]}"

    def test_chat_history_bounded_to_last_6(self, seed):
        """Send 10 prior turns; endpoint should not fail (bounded to last 6). Uses real GPT-5.2 call."""
        history = [{"role": "user" if i % 2 == 0 else "assistant",
                    "text": f"turn {i}"} for i in range(10)]
        r = requests.post(f"{BASE_URL}/api/support/chat",
                          headers=_hdr(seed["stu_tok"]),
                          json={"message": "Where do I set my language preference?",
                                "history": history}, timeout=60)
        assert r.status_code == 200, r.text
        assert "response" in r.json()

    def test_chat_source_has_timeout_guard(self):
        """Source-level assertion: 45s asyncio.wait_for + 504 error path present."""
        src = open("/app/backend/server.py").read()
        assert "async def support_chat" in src
        assert "asyncio.wait_for" in src
        assert "timeout=45" in src
        assert "504" in src


# ==================== /api/support/escalate ====================

class TestSupportEscalate:
    def test_escalate_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/support/escalate",
                          json={"conversation": [{"role": "user", "text": "help"}]},
                          timeout=10)
        assert r.status_code == 401

    def test_escalate_empty_conversation_400(self, seed):
        r = requests.post(f"{BASE_URL}/api/support/escalate",
                          headers=_hdr(seed["stu_tok"]),
                          json={"conversation": []}, timeout=10)
        assert r.status_code == 400

    def test_escalate_creates_ticket_and_returns_id(self, seed):
        convo = [
            {"role": "user", "text": "I can't find my feedback anywhere in the app.",
             "ts": datetime.now(timezone.utc).isoformat()},
            {"role": "assistant", "text": "Check Submissions tab or email inbox.",
             "ts": datetime.now(timezone.utc).isoformat()},
            {"role": "user", "text": "It's not there. Please escalate.",
             "ts": datetime.now(timezone.utc).isoformat()},
        ]
        r = requests.post(f"{BASE_URL}/api/support/escalate",
                          headers=_hdr(seed["stu_tok"]),
                          json={"conversation": convo}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "ticket_id" in data
        assert data["ticket_id"].startswith("tkt_")
        assert "message" in data

        # Verify persistence in DB
        client = AsyncIOMotorClient(MONGO_URL)
        db_ = client[DB_NAME]
        ticket = _run(db_.support_tickets.find_one({"ticket_id": data["ticket_id"]}, {"_id": 0}))
        client.close()
        assert ticket is not None
        assert ticket["user_id"] == seed["stu_id"]
        assert ticket["user_role"] == "student"
        assert ticket["status"] == "open"
        assert ticket["resolved_at"] is None
        assert ticket["admin_notes"] == ""
        assert len(ticket["conversation"]) == 3
        # Subject falls back to first user message
        assert "feedback" in ticket["subject"].lower()

    def test_escalate_custom_subject_used(self, seed):
        r = requests.post(f"{BASE_URL}/api/support/escalate",
                          headers=_hdr(seed["stu_tok"]),
                          json={"subject": "Login issue",
                                "conversation": [{"role": "user", "text": "Cannot log in."}]},
                          timeout=15)
        assert r.status_code == 200
        tid = r.json()["ticket_id"]
        client = AsyncIOMotorClient(MONGO_URL)
        db_ = client[DB_NAME]
        ticket = _run(db_.support_tickets.find_one({"ticket_id": tid}, {"_id": 0}))
        client.close()
        assert ticket["subject"] == "Login issue"

    def test_escalate_bounds_conversation_size(self, seed):
        """>40 turns should be truncated to last 40; each text bounded to 2000 chars."""
        big = [{"role": "user" if i % 2 == 0 else "assistant",
                "text": ("X" * 3000) + f" turn{i}"}
               for i in range(60)]
        r = requests.post(f"{BASE_URL}/api/support/escalate",
                          headers=_hdr(seed["stu_tok"]),
                          json={"subject": "bulk test", "conversation": big}, timeout=20)
        assert r.status_code == 200
        tid = r.json()["ticket_id"]
        client = AsyncIOMotorClient(MONGO_URL)
        db_ = client[DB_NAME]
        ticket = _run(db_.support_tickets.find_one({"ticket_id": tid}, {"_id": 0}))
        client.close()
        assert len(ticket["conversation"]) == 40, f"got {len(ticket['conversation'])}"
        for c in ticket["conversation"]:
            assert len(c["text"]) <= 2000


# ==================== /api/admin/support/tickets (list) ====================

class TestListTickets:
    def test_list_requires_super_admin_student_403(self, seed):
        r = requests.get(f"{BASE_URL}/api/admin/support/tickets",
                         headers=_hdr(seed["stu_tok"]), timeout=10)
        assert r.status_code == 403

    def test_list_requires_super_admin_instructor_403(self, seed):
        r = requests.get(f"{BASE_URL}/api/admin/support/tickets",
                         headers=_hdr(seed["inst_tok"]), timeout=10)
        assert r.status_code == 403

    def test_list_super_admin_returns_list_desc(self, seed):
        # Create two tickets with distinct timestamps
        client = AsyncIOMotorClient(MONGO_URL)
        db_ = client[DB_NAME]
        t1_id = f"tkt_{uuid.uuid4().hex[:12]}"
        t2_id = f"tkt_{uuid.uuid4().hex[:12]}"
        older = "2024-01-01T00:00:00+00:00"
        newer = "2025-06-01T00:00:00+00:00"
        _run(db_.support_tickets.insert_many([
            {"ticket_id": t1_id, "user_id": seed["stu_id"], "user_name": "A",
             "user_email": "a@t.test", "user_role": "student", "subject": "Older",
             "conversation": [{"role": "user", "text": "old"}], "status": "open",
             "created_at": older, "resolved_at": None, "admin_notes": ""},
            {"ticket_id": t2_id, "user_id": seed["stu_id"], "user_name": "A",
             "user_email": "a@t.test", "user_role": "student", "subject": "Newer",
             "conversation": [{"role": "user", "text": "new"}], "status": "resolved",
             "created_at": newer, "resolved_at": newer, "admin_notes": ""},
        ]))
        client.close()

        r = requests.get(f"{BASE_URL}/api/admin/support/tickets",
                         headers=_hdr(seed["adm_tok"]), timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Ensure our two are present and DESC ordered wrt each other
        ids_in_order = [t["ticket_id"] for t in data if t["ticket_id"] in (t1_id, t2_id)]
        assert ids_in_order == [t2_id, t1_id]

    def test_list_status_filter(self, seed):
        r = requests.get(f"{BASE_URL}/api/admin/support/tickets?status=resolved",
                         headers=_hdr(seed["adm_tok"]), timeout=10)
        assert r.status_code == 200
        for t in r.json():
            assert t["status"] == "resolved"


# ==================== PATCH /api/admin/support/tickets/{id} ====================

class TestPatchTicket:
    @pytest.fixture
    def open_ticket(self, seed):
        client = AsyncIOMotorClient(MONGO_URL)
        db_ = client[DB_NAME]
        tid = f"tkt_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        _run(db_.support_tickets.insert_one({
            "ticket_id": tid, "user_id": seed["stu_id"], "user_name": "S",
            "user_email": "s@t.test", "user_role": "student", "subject": "Patch test",
            "conversation": [{"role": "user", "text": "hello"}], "status": "open",
            "created_at": now, "resolved_at": None, "admin_notes": "",
        }))
        client.close()
        return tid

    def test_patch_requires_super_admin(self, seed, open_ticket):
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/{open_ticket}",
                           headers=_hdr(seed["stu_tok"]),
                           json={"status": "resolved"}, timeout=10)
        assert r.status_code == 403

    def test_patch_invalid_status_400(self, seed, open_ticket):
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/{open_ticket}",
                           headers=_hdr(seed["adm_tok"]),
                           json={"status": "closed"}, timeout=10)
        assert r.status_code == 400

    def test_patch_missing_ticket_404(self, seed):
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/tkt_missing_xxx",
                           headers=_hdr(seed["adm_tok"]),
                           json={"status": "resolved"}, timeout=10)
        assert r.status_code == 404

    def test_patch_resolve_then_reopen_and_notes(self, seed, open_ticket):
        # Resolve → sets resolved_at
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/{open_ticket}",
                           headers=_hdr(seed["adm_tok"]),
                           json={"status": "resolved",
                                 "admin_notes": "Handled via email."}, timeout=10)
        assert r.status_code == 200, r.text
        t = r.json()
        assert t["status"] == "resolved"
        assert t["resolved_at"] is not None
        assert t["admin_notes"] == "Handled via email."

        # Reopen → clears resolved_at
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/{open_ticket}",
                           headers=_hdr(seed["adm_tok"]),
                           json={"status": "open"}, timeout=10)
        assert r.status_code == 200
        t = r.json()
        assert t["status"] == "open"
        assert t["resolved_at"] is None
        # admin_notes remains from previous patch
        assert t["admin_notes"] == "Handled via email."

    def test_patch_no_fields_400(self, seed, open_ticket):
        r = requests.patch(f"{BASE_URL}/api/admin/support/tickets/{open_ticket}",
                           headers=_hdr(seed["adm_tok"]),
                           json={}, timeout=10)
        assert r.status_code == 400
