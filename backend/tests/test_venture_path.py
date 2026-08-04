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
    assert set(data.keys()) >= {"modules", "trend", "unlocked_count", "total_modules", "overall_best_score"}
    assert data["total_modules"] == 6
    assert len(data["modules"]) == 6
    assert data["unlocked_count"] == 0
    assert data["overall_best_score"] == 0
    assert data["trend"] == []
    nums = [m["module"] for m in data["modules"]]
    assert nums == [1, 2, 3, 4, 5, 6]
    for m in data["modules"]:
        for f in ("module", "name", "icon", "tagline", "best_score", "unlocked", "attempted"):
            assert f in m, f"missing {f} in {m}"
        assert m["best_score"] == 0
        assert m["unlocked"] is False
        assert m["attempted"] is False


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
    for n in (1, 3, 4, 5, 6):
        assert mods[n]["unlocked"] is False, f"module {n} should be locked"

    trend = data["trend"]
    assert any(t["week"] == 2 and t["score"] == 85 for t in trend), trend
