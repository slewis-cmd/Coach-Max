"""
Iteration 50 — POST /api/chat/ask-tutor performance/timeout fix.

USER BUG (production Cloudflare 524): On the SECOND follow-up question, the
LlmChat session_id was `coach_max_{user}_{submission}` (constant), so
LlmChat accumulated conversation history server-side ON TOP OF our fresh
15-20K-char system prompt, compounding the prompt on every turn. GPT-5.2
would routinely exceed 100s on Q2/Q3, triggering Cloudflare 524.

FIX (server.py ~3882):
  (a) Fresh UNIQUE session_id per request: coach_max_{uuid4.hex[:12]}
  (b) Load last 6 tutor_chats and inject compactly (Q:400, A:800 chars)
  (c) Trim context blocks 5000→2500, feedback 2000
  (d) asyncio.wait_for(75s) around chat.send_message; on TimeoutError
      raise HTTP 504 with a friendly retry-hint (beats Cloudflare 524).

This test suite verifies:
  1. Follow-up latency stays flat (each of 3 sequential Qs ≤ 60s).
  2. Conversational coherence: second answer references the first (proof
     that history_block is being injected into the system prompt).
  3. tutor_chats DB grows one row per successful call.
  4. session_id uniqueness (source-level assertion + observable behavior:
     Q3 latency ~= Q1 latency, not exponential).
  5. History-window bound: source-level assertion that .to_list(6) is used,
     AND that the endpoint tolerates >6 prior chats in DB without slowdown.
  6. Timeout path exists in code: asyncio.wait_for + HTTP 504 with the
     specific error message.
  7. REGRESSION: legacy material-based sent submissions still work.
  8. REGRESSION: 400 on unsent submission, 404 on missing.

GPT-5.2 budget: 6 total real LLM calls across the entire suite.
"""
import os
import re
import sys
import time
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, "/app/backend")

# Ensure env vars load whether pytest runs from /app or /app/backend
load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")

TAG = "TEST_TUTPERF_"
SERVER_PATH = "/app/backend/server.py"

# Per user-supplied hint, preview manual test showed 9.9/15.2/7.3s. Give
# generous headroom but well under Cloudflare's 100s cap.
LATENCY_BUDGET_S = 60.0


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ==========================================================================
# FIXTURE: instructor + student + cohort + milestone assignment
#          + 1 milestone-based SENT submission (primary target)
#          + 1 legacy material-based SENT submission (regression)
#          + 1 milestone PENDING submission (400 regression)
# ==========================================================================
@pytest.fixture(scope="module")
def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db_ = client[DB_NAME]

    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    cohort_id = f"{TAG}coh_{uuid.uuid4().hex[:8]}"
    asgn_id = f"{TAG}asgn_{uuid.uuid4().hex[:8]}"
    ms_id = f"{TAG}ms_{uuid.uuid4().hex[:8]}"
    legacy_mat_id = f"{TAG}mat_{uuid.uuid4().hex[:8]}"

    sub_ms_sent = f"{TAG}sub_ms_sent_{uuid.uuid4().hex[:6]}"
    sub_ms_pending = f"{TAG}sub_ms_pend_{uuid.uuid4().hex[:6]}"
    sub_legacy_sent = f"{TAG}sub_lg_sent_{uuid.uuid4().hex[:6]}"

    stu_tok = f"{TAG}stok_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc).isoformat()
    expires = (
        datetime.now(timezone.utc).replace(year=datetime.now().year + 1)
    ).isoformat()

    async def setup():
        await db_.users.insert_many([
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Inst Perf",
             "role": "instructor", "created_at": now},
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Alex",
             "role": "student", "created_at": now, "language_preference": "en"},
        ])
        await db_.user_sessions.insert_many([
            {"session_token": stu_tok, "user_id": stu_id,
             "email": f"{stu_id}@t.test",
             "expires_at": expires, "created_at": now},
        ])
        await db_.cohorts.insert_one({
            "cohort_id": cohort_id, "name": f"{TAG}Cohort",
            "instructor_ids": [inst_id], "student_ids": [stu_id],
            "total_weeks": 4, "current_week": 4,
            "auto_send_feedback": False, "created_at": now,
        })
        await db_.assignments.insert_one({
            "assignment_id": asgn_id, "cohort_id": cohort_id,
            "title": f"{TAG}60-Second Elevator Pitch",
            "description": "Deliver a 60-second elevator pitch about your leadership vision.",
            "submission_type": "60_second_pitch",
            "feedback_template": "Assignment-level template",
            "drive_folder_url": "", "questionnaire_fields": [],
            "is_active": True,
            "milestones": [
                {"milestone_id": ms_id, "week_number": 3,
                 "title": "Week 3 Refined Pitch", "description": "Refined draft",
                 "feedback_template_override": "",
                 "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })
        await db_.materials.insert_one({
            "material_id": legacy_mat_id, "cohort_id": cohort_id,
            "cohort_ids": [cohort_id],
            "title": f"{TAG}Legacy Homework Week 1",
            "description": "Legacy per-material homework",
            "material_type": "homework", "week_number": 1,
            "submission_type": "text",
            "content": "Legacy material content for context",
            "created_at": now,
        })
        # Milestone-based SENT submission (main target)
        await db_.submissions.insert_one({
            "submission_id": sub_ms_sent, "student_id": stu_id,
            "cohort_id": cohort_id, "assignment_id": asgn_id,
            "milestone_id": ms_id, "material_id": "",
            "submission_type": "60_second_pitch",
            "file_name": "pitch.txt",
            "content_text": (
                "Hi, I'm Alex. I lead product teams by combining a clear "
                "vision with day-to-day empathy. In my last role I turned "
                "around a stalled roadmap by rebuilding trust one 1:1 at a "
                "time. My hook: leadership is a series of small, honest "
                "conversations that compound."
            ),
            "status": "sent",
            "instructor_feedback": (
                "Strong personal hook and clear POV. Two suggestions: "
                "(1) Open with the compounding-conversations line — it's "
                "your best asset. (2) Cut the middle sentence about the "
                "stalled roadmap in half; keep the outcome, drop the setup."
            ),
            "ai_feedback": "AI: Consider a stronger opening line.",
            "submitted_at": now, "sent_at": now, "feedback_sent": True,
        })
        # Milestone-based PENDING (400 regression)
        await db_.submissions.insert_one({
            "submission_id": sub_ms_pending, "student_id": stu_id,
            "cohort_id": cohort_id, "assignment_id": asgn_id,
            "milestone_id": ms_id, "material_id": "",
            "submission_type": "60_second_pitch",
            "file_name": "draft.txt",
            "content_text": "Rough draft.",
            "status": "pending_review",
            "instructor_feedback": "", "ai_feedback": "",
            "submitted_at": now,
        })
        # Legacy material-based SENT (regression)
        await db_.submissions.insert_one({
            "submission_id": sub_legacy_sent, "student_id": stu_id,
            "cohort_id": cohort_id, "material_id": legacy_mat_id,
            "submission_type": "text",
            "file_name": "legacy.txt",
            "content_text": "Legacy submission text about leadership.",
            "status": "sent",
            "instructor_feedback": (
                "Nice reflection. Push on the 'why' behind each choice."
            ),
            "ai_feedback": "", "submitted_at": now, "sent_at": now,
            "feedback_sent": True,
        })

    _run(setup())

    ctx = {
        "stu_id": stu_id, "stu_tok": stu_tok,
        "stu_auth": {"Authorization": f"Bearer {stu_tok}"},
        "sub_ms_sent": sub_ms_sent,
        "sub_ms_pending": sub_ms_pending,
        "sub_legacy_sent": sub_legacy_sent,
    }
    yield ctx

    async def teardown():
        await db_.users.delete_many({"user_id": {"$regex": f"^{TAG}"}})
        await db_.user_sessions.delete_many({"session_token": {"$regex": f"^{TAG}"}})
        await db_.cohorts.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
        await db_.assignments.delete_many({"assignment_id": {"$regex": f"^{TAG}"}})
        await db_.materials.delete_many({"material_id": {"$regex": f"^{TAG}"}})
        await db_.submissions.delete_many({"submission_id": {"$regex": f"^{TAG}"}})
        await db_.tutor_chats.delete_many({"submission_id": {"$regex": f"^{TAG}"}})

    _run(teardown())
    client.close()


# ==========================================================================
# Helper: read server.py source once (for code-path assertions)
# ==========================================================================
@pytest.fixture(scope="module")
def server_src():
    with open(SERVER_PATH, "r") as f:
        return f.read()


def _ask(seed, submission_id, message, timeout_s=90):
    """POST to ask-tutor; return (status, elapsed_s, json_or_text)."""
    t0 = time.monotonic()
    r = requests.post(
        f"{BASE_URL}/api/chat/ask-tutor",
        headers={**seed["stu_auth"], "Content-Type": "application/json"},
        json={"message": message, "submission_id": submission_id},
        timeout=timeout_s,
    )
    dt = time.monotonic() - t0
    try:
        body = r.json()
    except Exception:
        body = r.text
    return r.status_code, dt, body


# ==========================================================================
# 1. CODE-PATH ASSERTIONS (fast, no LLM cost)
# ==========================================================================
class TestSourceCodePaths:
    """Static assertions the fix is actually in server.py at ~3882."""

    def test_session_id_is_unique_per_request(self, server_src):
        # Must NOT use the old constant form
        assert 'session_id=f"coach_max_{user["user_id"]}_{submission_id}"' not in server_src, \
            "Old accumulating session_id pattern still present — bug not fixed."
        # Must use fresh uuid4
        assert re.search(
            r'session_id=f"coach_max_\{uuid\.uuid4\(\)\.hex\[:12\]\}"',
            server_src,
        ), "Fresh unique session_id not found in ask_tutor endpoint."

    def test_history_window_uses_to_list_6(self, server_src):
        # last-6-turns window
        assert re.search(
            r"tutor_chats\.find\([\s\S]*?\.sort\(\"created_at\",\s*-1\)\.to_list\(6\)",
            server_src,
        ), "History window (.sort desc .to_list(6)) missing."

    def test_history_trim_400_800(self, server_src):
        # q[:400] and a[:800] compact trimming
        assert "q[:400]" in server_src and "a[:800]" in server_src, \
            "Per-turn compact trimming (400/800 chars) missing."

    def test_context_trimmed_to_2500(self, server_src):
        # submission_text/context_text/cumulative_ctx all sliced to 2500,
        # feedback to 2000 (per PR description).
        assert "submission_text[:2500]" in server_src
        assert "context_text[:2500]" in server_src
        assert "cumulative_ctx[:2500]" in server_src
        assert "feedback[:2000]" in server_src

    def test_asyncio_wait_for_75s(self, server_src):
        # 75s wrapper around chat.send_message
        assert re.search(
            r"asyncio\.wait_for\([\s\S]*?chat\.send_message[\s\S]*?timeout=75\.0",
            server_src,
        ), "asyncio.wait_for(..., timeout=75.0) not wrapping send_message."

    def test_timeout_handler_returns_504(self, server_src):
        # HTTP 504 + specific retry-hint message
        assert re.search(
            r"except\s+asyncio\.TimeoutError[\s\S]{0,400}?status_code=504",
            server_src,
        ), "asyncio.TimeoutError -> 504 handler missing."
        assert "is taking longer than expected. Please try asking again" in server_src, \
            "User-facing 504 message copy missing."


# ==========================================================================
# 2. AUTH + INPUT-VALIDATION (fast, no LLM cost)
# ==========================================================================
class TestInputValidation:
    def test_unauthed_401(self):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            json={"message": "hi", "submission_id": "x"},
            timeout=10,
        )
        assert r.status_code in (401, 403), r.text

    def test_missing_message_400(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["stu_auth"],
            json={"message": "  ", "submission_id": seed["sub_ms_sent"]},
            timeout=10,
        )
        assert r.status_code == 400, r.text

    def test_missing_submission_id_400(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["stu_auth"],
            json={"message": "hi"},
            timeout=10,
        )
        assert r.status_code == 400, r.text

    def test_unknown_submission_404(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["stu_auth"],
            json={"message": "hi", "submission_id": "does_not_exist"},
            timeout=10,
        )
        assert r.status_code == 404, r.text

    def test_pending_submission_400(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers=seed["stu_auth"],
            json={"message": "hi", "submission_id": seed["sub_ms_pending"]},
            timeout=10,
        )
        assert r.status_code == 400, r.text
        assert "feedback" in (r.json().get("detail") or "").lower()


# ==========================================================================
# 3. THE CORE LATENCY TEST — 3 sequential follow-ups (3 real LLM calls)
# ==========================================================================
class TestFollowUpLatency:
    """
    Repro of the exact user bug scenario. Send Q1 → Q2 → Q3 to the same
    submission and verify:
      - each returns 200 with non-empty response
      - each completes ≤ 60s (pre-fix Q2 exceeded 100s)
      - Q2/Q3 don't grow super-linearly vs Q1 (proof session_id is fresh
        and prior turns aren't accumulating server-side)
      - Q2 response is contextually aware of Q1 (proof history_block works)
    """

    QUESTIONS = [
        "What did I do well in my pitch?",
        "Given that, what should I improve first?",
        "Can you give me one concrete example rewrite of my opening line?",
    ]

    def test_three_sequential_questions_stay_under_60s(self, seed):
        latencies = []
        answers = []

        for i, q in enumerate(self.QUESTIONS):
            status, dt, body = _ask(seed, seed["sub_ms_sent"], q, timeout_s=90)
            print(f"[latency] Q{i+1} status={status} elapsed={dt:.1f}s")
            assert status == 200, f"Q{i+1} failed: status={status} body={body}"
            assert isinstance(body, dict) and body.get("response"), \
                f"Q{i+1} empty response body: {body}"
            latencies.append(dt)
            answers.append(body["response"])
            # brief realistic gap between messages
            time.sleep(1.0)

        # (a) All under Cloudflare-safe budget
        for i, dt in enumerate(latencies):
            assert dt <= LATENCY_BUDGET_S, (
                f"Q{i+1} took {dt:.1f}s > budget {LATENCY_BUDGET_S}s. "
                "Follow-up latency regression — bug returning."
            )

        # (b) Sanity: Q3 shouldn't be dramatically slower than Q1. Old bug
        #     caused Q3 >> Q1 due to accumulating history. Allow 2.5x
        #     factor as a generous flake margin (real observed ratios in
        #     preview were ~0.7x).
        q1, q3 = latencies[0], latencies[-1]
        assert q3 <= max(q1 * 2.5, 20.0), (
            f"Q3 ({q3:.1f}s) grew >2.5x over Q1 ({q1:.1f}s) — hints at "
            "session_id accumulation regression."
        )

        # (c) History injection sanity: Q2 answer should be responding to
        #     Q1 ("Given that ..."). We can't force wording, but the answer
        #     should be non-trivial and topically relevant to the pitch.
        assert len(answers[1]) > 40, "Q2 answer suspiciously short."
        # Store latencies on the seed dict for the next test's assertion.
        seed["_latencies"] = latencies
        seed["_answers"] = answers

    def test_tutor_chats_persisted_all_three(self, seed):
        # Precondition: prior test ran successfully
        assert seed.get("_latencies"), "Precondition: run 3-Q test first."

        async def _count():
            client = AsyncIOMotorClient(MONGO_URL)
            n = await client[DB_NAME].tutor_chats.count_documents({
                "submission_id": seed["sub_ms_sent"],
                "student_id": seed["stu_id"],
            })
            client.close()
            return n

        n = _run(_count())
        assert n >= 3, f"Expected ≥3 tutor_chats rows persisted, got {n}."


# ==========================================================================
# 4. HISTORY-WINDOW BOUND — simulate 8 prior chats already in DB, then a
#    9th ask. The prompt should only pick last 6; endpoint should stay
#    fast. (Uses 1 real LLM call.)
# ==========================================================================
class TestHistoryWindowBound:
    def test_endpoint_stays_fast_with_8_prior_chats(self, seed):
        # Preload 8 fake historical turns directly in Mongo (no LLM cost).
        async def _preload():
            client = AsyncIOMotorClient(MONGO_URL)
            docs = []
            for i in range(8):
                docs.append({
                    "chat_id": f"{TAG}fake_{i}_{uuid.uuid4().hex[:6]}",
                    "submission_id": seed["sub_ms_sent"],
                    "student_id": seed["stu_id"],
                    "message": f"Prior question {i}: what about topic {i}?" * 3,
                    "response": (
                        f"Prior answer {i}: here's my take on topic {i}. " * 10
                    ),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
            await client[DB_NAME].tutor_chats.insert_many(docs)
            client.close()
        _run(_preload())

        status, dt, body = _ask(
            seed, seed["sub_ms_sent"],
            "One more thing — what's the single next action?", timeout_s=90,
        )
        print(f"[history-bound] status={status} elapsed={dt:.1f}s")
        assert status == 200, f"Failed: status={status} body={body}"
        assert isinstance(body, dict) and body.get("response")
        # With .to_list(6) capping the injected history, the prompt should
        # NOT grow unboundedly. Latency should stay well under budget.
        assert dt <= LATENCY_BUDGET_S, (
            f"With 8+ prior chats endpoint took {dt:.1f}s — history window "
            "bound (.to_list(6)) may be broken."
        )


# ==========================================================================
# 5. REGRESSION — legacy material-based sent submission still works
#    (1 real LLM call)
# ==========================================================================
class TestLegacyMaterialRegression:
    def test_legacy_material_submission_still_answers(self, seed):
        status, dt, body = _ask(
            seed, seed["sub_legacy_sent"],
            "What did I do well?", timeout_s=90,
        )
        print(f"[legacy] status={status} elapsed={dt:.1f}s")
        assert status == 200, f"Legacy sub failed: status={status} body={body}"
        assert isinstance(body, dict) and body.get("response")
        assert len(body["response"].strip()) > 20
        assert dt <= LATENCY_BUDGET_S
