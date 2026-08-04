"""Tests for Venture Path gamification: GET /api/student/venture-path.

Verifies:
- 401 without auth
- 403 for instructor
- Shape + 6 modules with correct fields for empty student
- Unlock math after seeding a scored submission at week_number=2
- Trend array includes the seeded week/score
- parse_readiness_score helper (imported directly)
"""
import os
import sys
import uuid
import time
import pytest
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Make server.py importable so we can test parse_readiness_score directly.
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def student_ctx(mongo):
    """Seed a student user + session + cohort + assignment with 6 milestones."""
    suffix = uuid.uuid4().hex[:8]
    user_id = f"TEST_stu_{suffix}"
    token = f"TEST_tok_{suffix}"
    cohort_id = f"TEST_cohort_{suffix}"
    assignment_id = f"TEST_asgmt_{suffix}"
    milestones = [
        {"milestone_id": f"TEST_ms_{suffix}_w{w}", "week_number": w, "title": f"Week {w}"}
        for w in range(1, 7)
    ]

    mongo.users.insert_one({
        "user_id": user_id,
        "email": f"TEST_{suffix}@example.com",
        "name": "Test Student",
        "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    mongo.cohorts.insert_one({
        "cohort_id": cohort_id,
        "name": f"TEST Cohort {suffix}",
        "student_ids": [user_id],
        "instructor_ids": [],
        "total_weeks": 14,
        "is_active": True,
    })
    mongo.assignments.insert_one({
        "assignment_id": assignment_id,
        "cohort_id": cohort_id,
        "title": "TEST Assignment",
        "is_active": True,
        "order": 1,
        "milestones": milestones,
    })

    ctx = {
        "user_id": user_id, "token": token, "cohort_id": cohort_id,
        "assignment_id": assignment_id, "milestones": milestones,
    }
    yield ctx

    # cleanup
    mongo.users.delete_many({"user_id": user_id})
    mongo.user_sessions.delete_many({"user_id": user_id})
    mongo.cohorts.delete_many({"cohort_id": cohort_id})
    mongo.assignments.delete_many({"assignment_id": assignment_id})
    mongo.submissions.delete_many({"student_id": user_id})


@pytest.fixture(scope="module")
def instructor_ctx(mongo):
    suffix = uuid.uuid4().hex[:8]
    user_id = f"TEST_inst_{suffix}"
    token = f"TEST_itok_{suffix}"
    mongo.users.insert_one({
        "user_id": user_id, "email": f"TEST_inst_{suffix}@example.com",
        "name": "Test Instructor", "role": "instructor",
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": user_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    yield {"user_id": user_id, "token": token}
    mongo.users.delete_many({"user_id": user_id})
    mongo.user_sessions.delete_many({"user_id": user_id})


def _get_vp(token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(f"{BASE_URL}/api/student/venture-path", headers=headers, timeout=30)


# -------------------- parse_readiness_score helper --------------------
class TestParseReadinessScore:
    def test_parses_trailing_line(self):
        from server import parse_readiness_score
        assert parse_readiness_score("Great work.\n\nReadiness Score: 92/100") == 92

    def test_returns_none_when_missing(self):
        from server import parse_readiness_score
        assert parse_readiness_score("no score here") is None

    def test_clamps_range(self):
        from server import parse_readiness_score
        assert parse_readiness_score("Readiness Score: 150/100") == 100
        assert parse_readiness_score("Readiness Score: 0/100") == 1

    def test_parses_progress_score_new_label(self):
        from server import parse_readiness_score
        assert parse_readiness_score("Nice work.\n\nProgress Score: 82/100") == 82

    def test_parses_readiness_score_legacy_label(self):
        from server import parse_readiness_score
        assert parse_readiness_score("Readiness Score: 82/100") == 82


# -------------------- INVESTOR_SCORE_INSTRUCTION content --------------------
def test_investor_score_instruction_encouraging_language():
    from server import INVESTOR_SCORE_INSTRUCTION as inst
    assert "first-time" in inst.lower()
    for band in ("Strong Start", "Building Momentum", "Traction Mode", "Investor-Ready"):
        assert band in inst, f"missing band '{band}'"
    # New label used in prompt
    assert "Progress Score" in inst


# -------------------- Badge tier thresholds --------------------
class TestBadgeTierFor:
    def test_thresholds(self):
        from server import badge_tier_for
        assert badge_tier_for(0) == "none"
        assert badge_tier_for(49) == "none"
        assert badge_tier_for(50) == "bronze"
        assert badge_tier_for(69) == "bronze"
        assert badge_tier_for(70) == "silver"
        assert badge_tier_for(84) == "silver"
        assert badge_tier_for(85) == "gold"
        assert badge_tier_for(100) == "gold"


# -------------------- Auth --------------------
def test_unauthenticated_returns_401():
    r = _get_vp()
    assert r.status_code == 401, r.text


def test_instructor_forbidden(instructor_ctx):
    r = _get_vp(instructor_ctx["token"])
    assert r.status_code == 403, r.text


# -------------------- Empty student --------------------
def test_empty_student_shape(student_ctx):
    r = _get_vp(student_ctx["token"])
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data.keys()) >= {"modules", "trend", "unlocked_count", "total_modules",
                                 "overall_best_score", "gold_count", "silver_count", "bronze_count"}
    assert data["total_modules"] == 6
    assert len(data["modules"]) == 6
    assert data["unlocked_count"] == 0
    assert data["gold_count"] == 0
    assert data["silver_count"] == 0
    assert data["bronze_count"] == 0
    assert data["overall_best_score"] == 0
    assert data["trend"] == []
    nums = [m["module"] for m in data["modules"]]
    assert nums == [1, 2, 3, 4, 5, 6]
    for m in data["modules"]:
        for f in ("module", "name", "icon", "tagline", "best_score", "unlocked",
                  "attempted", "tier", "next_tier", "points_to_next"):
            assert f in m, f"missing {f} in {m}"
        assert m["best_score"] == 0
        assert m["unlocked"] is False
        assert m["attempted"] is False
        assert m["tier"] == "none"
        assert m["next_tier"] == "bronze"
        assert m["points_to_next"] == 50


# -------------------- Unlock math --------------------
def test_unlock_module_2_after_seeded_submission(mongo, student_ctx):
    ms_w2 = next(m for m in student_ctx["milestones"] if m["week_number"] == 2)
    sub_id = f"TEST_sub_{uuid.uuid4().hex[:8]}"
    mongo.submissions.insert_one({
        "submission_id": sub_id,
        "student_id": student_ctx["user_id"],
        "cohort_id": student_ctx["cohort_id"],
        "assignment_id": student_ctx["assignment_id"],
        "milestone_id": ms_w2["milestone_id"],
        "readiness_score": 85,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "reviewed",
        "title": "Week 2 pitch",
    })

    r = _get_vp(student_ctx["token"])
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["unlocked_count"] == 1
    assert data["overall_best_score"] == 85

    mods = {m["module"]: m for m in data["modules"]}
    m2 = mods[2]
    assert m2["unlocked"] is True
    assert m2["best_score"] == 85
    assert m2["attempted"] is True
    assert m2["tier"] == "gold"
    assert m2["next_tier"] is None
    assert m2["points_to_next"] is None
    assert data["gold_count"] == 1
    assert data["silver_count"] == 0
    assert data["bronze_count"] == 0
    for n in (1, 3, 4, 5, 6):
        assert mods[n]["unlocked"] is False, f"module {n} should be locked"

    trend = data["trend"]
    assert any(t["week"] == 2 and t["score"] == 85 for t in trend), trend


# -------------------- Fresh-student helpers for tier tests --------------------
def _seed_student(mongo, weeks=(1, 2, 3, 4, 5, 6)):
    suffix = uuid.uuid4().hex[:8]
    user_id = f"TEST_stu_{suffix}"
    token = f"TEST_tok_{suffix}"
    cohort_id = f"TEST_cohort_{suffix}"
    assignment_id = f"TEST_asgmt_{suffix}"
    milestones = [
        {"milestone_id": f"TEST_ms_{suffix}_w{w}", "week_number": w, "title": f"Week {w}"}
        for w in weeks
    ]
    mongo.users.insert_one({
        "user_id": user_id, "email": f"TEST_{suffix}@example.com",
        "name": "Test Student", "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": user_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    mongo.cohorts.insert_one({
        "cohort_id": cohort_id, "name": f"TEST Cohort {suffix}",
        "student_ids": [user_id], "instructor_ids": [],
        "total_weeks": 14, "is_active": True,
    })
    mongo.assignments.insert_one({
        "assignment_id": assignment_id, "cohort_id": cohort_id,
        "title": "TEST Assignment", "is_active": True, "order": 1,
        "milestones": milestones,
    })
    return {
        "user_id": user_id, "token": token, "cohort_id": cohort_id,
        "assignment_id": assignment_id, "milestones": milestones,
    }


def _cleanup_student(mongo, ctx):
    mongo.users.delete_many({"user_id": ctx["user_id"]})
    mongo.user_sessions.delete_many({"user_id": ctx["user_id"]})
    mongo.cohorts.delete_many({"cohort_id": ctx["cohort_id"]})
    mongo.assignments.delete_many({"assignment_id": ctx["assignment_id"]})
    mongo.submissions.delete_many({"student_id": ctx["user_id"]})


def _insert_sub(mongo, ctx, week, score):
    ms = next(m for m in ctx["milestones"] if m["week_number"] == week)
    mongo.submissions.insert_one({
        "submission_id": f"TEST_sub_{uuid.uuid4().hex[:8]}",
        "student_id": ctx["user_id"],
        "cohort_id": ctx["cohort_id"],
        "assignment_id": ctx["assignment_id"],
        "milestone_id": ms["milestone_id"],
        "readiness_score": score,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "reviewed",
        "title": f"Week {week} attempt",
    })


# -------------------- Tier threshold correctness --------------------
@pytest.mark.parametrize("score,exp_tier,exp_next,exp_points", [
    (49, "none",   "bronze", 1),
    (50, "bronze", "silver", 20),
    (69, "bronze", "silver", 1),
    (70, "silver", "gold",   15),
    (84, "silver", "gold",   1),
    (85, "gold",   None,     None),
    (100, "gold",  None,     None),
])
def test_tier_thresholds(mongo, score, exp_tier, exp_next, exp_points):
    ctx = _seed_student(mongo)
    try:
        _insert_sub(mongo, ctx, week=3, score=score)
        r = _get_vp(ctx["token"])
        assert r.status_code == 200, r.text
        data = r.json()
        m3 = next(m for m in data["modules"] if m["module"] == 3)
        assert m3["best_score"] == score
        assert m3["tier"] == exp_tier
        assert m3["next_tier"] == exp_next
        assert m3["points_to_next"] == exp_points
        # unlocked_count should equal sum of gold+silver+bronze counts
        assert data["unlocked_count"] == data["gold_count"] + data["silver_count"] + data["bronze_count"]
    finally:
        _cleanup_student(mongo, ctx)


# -------------------- Best-of-many-attempts --------------------
def test_best_attempt_wins_when_multiple_submissions(mongo):
    ctx = _seed_student(mongo)
    try:
        # First attempt low, second attempt higher — best (72) should win => silver.
        _insert_sub(mongo, ctx, week=4, score=45)
        _insert_sub(mongo, ctx, week=4, score=72)
        r = _get_vp(ctx["token"])
        assert r.status_code == 200, r.text
        data = r.json()
        m4 = next(m for m in data["modules"] if m["module"] == 4)
        assert m4["best_score"] == 72
        assert m4["tier"] == "silver"
        assert m4["next_tier"] == "gold"
        assert m4["points_to_next"] == 13
        assert data["silver_count"] == 1
        assert data["overall_best_score"] == 72
    finally:
        _cleanup_student(mongo, ctx)
