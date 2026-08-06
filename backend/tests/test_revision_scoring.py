"""Tests for the iteration_59 revision-scoring changes.

Covers:
1. INVESTOR_SCORE_INSTRUCTION prompt contains the new calibration + revision bonus phrases.
2. _prior_attempts_on_same_milestone_section() helper behaviour (empty cases,
   header/format, score line, exclude, feedback inclusion).
3. build_cumulative_context() end-to-end includes prior scores + feedback and
   excludes the current attempt.
4. Backwards compatibility: build_cumulative_context() works without
   milestone_id / exclude_submission_id (legacy signature).
"""
import asyncio
import os
import sys
import uuid
import pytest
from datetime import datetime, timezone
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

sys.path.insert(0, "/app/backend")

# Import server module (loads env, db handle etc.)
import server  # noqa: E402


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture()
def event_loop():
    """Fresh event loop per test; rebind server.db/client to this loop so
    motor's cached io_loop matches (avoids 'attached to a different loop')."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Rebind motor to this loop
    original_client = server.client
    original_db = server.db
    new_client = AsyncIOMotorClient(MONGO_URL, io_loop=loop)
    server.client = new_client
    server.db = new_client[DB_NAME]
    try:
        yield loop
    finally:
        new_client.close()
        server.client = original_client
        server.db = original_db
        loop.close()


# ------------------------------------------------------------------ #
# 1) Prompt content sanity                                           #
# ------------------------------------------------------------------ #
class TestInvestorScoreInstructionContent:
    """The prompt must ship the new calibration wording."""

    def test_contains_required_phrases(self):
        inst = server.INVESTOR_SCORE_INSTRUCTION
        required = [
            "SCORING CALIBRATION",
            "65-79",
            "Traction Mode",
            "REVISION BONUS",
            "+10 to +15",
            "PRIOR ATTEMPTS ON THIS EXACT MILESTONE",
        ]
        missing = [p for p in required if p not in inst]
        assert not missing, f"Prompt missing required phrases: {missing}"


# ------------------------------------------------------------------ #
# 2) _prior_attempts_on_same_milestone_section()                     #
# ------------------------------------------------------------------ #
@pytest.fixture()
def milestone_ctx(mongo):
    """Seed a student + milestone id for the helper tests. Cleans up after."""
    suffix = uuid.uuid4().hex[:8]
    ctx = {
        "student_id": f"TEST_stu_{suffix}",
        "milestone_id": f"TEST_ms_{suffix}",
        "cohort_id": f"TEST_cohort_{suffix}",
        "assignment_id": f"TEST_asgmt_{suffix}",
        "suffix": suffix,
    }
    yield ctx
    mongo.submissions.delete_many({"student_id": ctx["student_id"]})


def _run(coro, loop):
    return loop.run_until_complete(coro)


def _seed_sub(mongo, ctx, *, submission_id, feedback, score, submitted_at=None, milestone_id=None):
    mongo.submissions.insert_one({
        "submission_id": submission_id,
        "student_id": ctx["student_id"],
        "cohort_id": ctx["cohort_id"],
        "assignment_id": ctx["assignment_id"],
        "milestone_id": milestone_id or ctx["milestone_id"],
        "ai_feedback": feedback,
        "readiness_score": score,
        "status": "reviewed",
        "submitted_at": submitted_at or datetime.now(timezone.utc).isoformat(),
        "title": f"attempt {submission_id}",
    })


class TestPriorAttemptsHelper:
    def test_empty_when_no_prior_submissions(self, milestone_ctx, event_loop):
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], milestone_ctx["milestone_id"]
            ),
            event_loop,
        )
        assert out == ""

    def test_empty_when_milestone_id_none(self, milestone_ctx, event_loop):
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], None
            ),
            event_loop,
        )
        assert out == ""

    def test_empty_when_milestone_id_empty_string(self, milestone_ctx, event_loop):
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], ""
            ),
            event_loop,
        )
        assert out == ""

    def test_returns_header_and_scores_when_prior_exists(self, mongo, milestone_ctx, event_loop):
        # Two prior attempts, chronological
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_a_{milestone_ctx['suffix']}",
            feedback="Great start - deepen the market sizing next time",
            score=62,
            submitted_at="2025-01-01T10:00:00+00:00",
        )
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_b_{milestone_ctx['suffix']}",
            feedback="Better; add unit economics",
            score=71,
            submitted_at="2025-01-02T10:00:00+00:00",
        )
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], milestone_ctx["milestone_id"]
            ),
            event_loop,
        )
        assert out.lstrip().startswith("--- PRIOR ATTEMPTS ON THIS EXACT MILESTONE ---"), out[:200]
        # Score lines
        assert "Founder Progress Score awarded: 62/100" in out
        assert "Founder Progress Score awarded: 71/100" in out
        # Feedback snippets included
        assert "deepen the market sizing" in out
        assert "add unit economics" in out
        # Ordering: 62 comes before 71 (chronological)
        assert out.index("62/100") < out.index("71/100")

    def test_excludes_current_submission_id(self, mongo, milestone_ctx, event_loop):
        cur_id = f"TEST_sub_cur_{milestone_ctx['suffix']}"
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_prev_{milestone_ctx['suffix']}",
            feedback="prior feedback text",
            score=62,
            submitted_at="2025-01-01T10:00:00+00:00",
        )
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=cur_id,
            feedback="THIS_IS_THE_CURRENT_ATTEMPT_FEEDBACK",
            score=None,
            submitted_at="2025-01-05T10:00:00+00:00",
        )
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"],
                milestone_ctx["milestone_id"],
                exclude_submission_id=cur_id,
            ),
            event_loop,
        )
        assert "prior feedback text" in out
        assert "THIS_IS_THE_CURRENT_ATTEMPT_FEEDBACK" not in out
        assert "62/100" in out

    def test_no_score_line_when_readiness_score_missing(self, mongo, milestone_ctx, event_loop):
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_noscore_{milestone_ctx['suffix']}",
            feedback="ungraded feedback here",
            score=None,
            submitted_at="2025-01-01T10:00:00+00:00",
        )
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], milestone_ctx["milestone_id"]
            ),
            event_loop,
        )
        assert "ungraded feedback here" in out
        assert "Founder Progress Score awarded:" not in out

    def test_prefers_instructor_feedback_over_ai_feedback(self, mongo, milestone_ctx, event_loop):
        mongo.submissions.insert_one({
            "submission_id": f"TEST_sub_inst_{milestone_ctx['suffix']}",
            "student_id": milestone_ctx["student_id"],
            "cohort_id": milestone_ctx["cohort_id"],
            "assignment_id": milestone_ctx["assignment_id"],
            "milestone_id": milestone_ctx["milestone_id"],
            "ai_feedback": "AI_FEEDBACK_TEXT",
            "instructor_feedback": "INSTRUCTOR_FEEDBACK_TEXT",
            "readiness_score": 70,
            "status": "reviewed",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "title": "attempt inst",
        })
        out = _run(
            server._prior_attempts_on_same_milestone_section(
                milestone_ctx["student_id"], milestone_ctx["milestone_id"]
            ),
            event_loop,
        )
        assert "INSTRUCTOR_FEEDBACK_TEXT" in out
        assert "AI_FEEDBACK_TEXT" not in out


# ------------------------------------------------------------------ #
# 3) build_cumulative_context() integration                          #
# ------------------------------------------------------------------ #
class TestBuildCumulativeContextRevision:
    def test_includes_two_prior_attempts_and_excludes_current(self, mongo, milestone_ctx, event_loop):
        cur_id = f"TEST_sub_cur_{milestone_ctx['suffix']}"
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_a_{milestone_ctx['suffix']}",
            feedback="Great start - deepen the market sizing next time",
            score=62,
            submitted_at="2025-01-01T10:00:00+00:00",
        )
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_b_{milestone_ctx['suffix']}",
            feedback="Better; add unit economics",
            score=71,
            submitted_at="2025-01-02T10:00:00+00:00",
        )
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=cur_id,
            feedback="CURRENT_ATTEMPT_MUST_NOT_APPEAR",
            score=None,
            submitted_at="2025-01-05T10:00:00+00:00",
        )
        out = _run(
            server.build_cumulative_context(
                student_id=milestone_ctx["student_id"],
                cohort_id=milestone_ctx["cohort_id"],
                current_week=3,
                milestone_id=milestone_ctx["milestone_id"],
                exclude_submission_id=cur_id,
            ),
            event_loop,
        )
        assert "62/100" in out
        assert "71/100" in out
        assert "deepen the market sizing" in out
        assert "add unit economics" in out
        assert "CURRENT_ATTEMPT_MUST_NOT_APPEAR" not in out
        assert "PRIOR ATTEMPTS ON THIS EXACT MILESTONE" in out

    def test_legacy_signature_without_milestone_id_still_works(self, mongo, milestone_ctx, event_loop):
        """Old callers that don't pass milestone_id must still get a valid string
        (either empty or containing course-wide / prior-week sections), and MUST
        NOT include the 'PRIOR ATTEMPTS' section."""
        # Seed a prior attempt to make sure it does NOT leak into legacy output.
        _seed_sub(
            mongo, milestone_ctx,
            submission_id=f"TEST_sub_leak_{milestone_ctx['suffix']}",
            feedback="SHOULD_NOT_APPEAR_IN_LEGACY_CALL",
            score=62,
        )
        out = _run(
            server.build_cumulative_context(
                milestone_ctx["student_id"],
                milestone_ctx["cohort_id"],
                1,  # week 1 => only global resources considered
            ),
            event_loop,
        )
        # Legacy result may be empty string when no global resources / prior weeks.
        assert isinstance(out, str)
        assert "PRIOR ATTEMPTS ON THIS EXACT MILESTONE" not in out
        assert "SHOULD_NOT_APPEAR_IN_LEGACY_CALL" not in out

    def test_no_prior_attempts_returns_no_prior_header(self, mongo, milestone_ctx, event_loop):
        """milestone_id passed but no prior submissions -> no PRIOR ATTEMPTS header."""
        out = _run(
            server.build_cumulative_context(
                student_id=milestone_ctx["student_id"],
                cohort_id=milestone_ctx["cohort_id"],
                current_week=1,
                milestone_id=milestone_ctx["milestone_id"],
                exclude_submission_id="TEST_nonexistent",
            ),
            event_loop,
        )
        assert isinstance(out, str)
        assert "PRIOR ATTEMPTS ON THIS EXACT MILESTONE" not in out
