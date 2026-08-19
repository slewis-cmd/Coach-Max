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
        for w in range(1, 15)
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
    assert data["total_modules"] == 14
    assert len(data["modules"]) == 14
    assert data["unlocked_count"] == 0
    assert data["gold_count"] == 0
    assert data["silver_count"] == 0
    assert data["bronze_count"] == 0
    assert data["overall_best_score"] == 0
    assert data["trend"] == []
    nums = [m["module"] for m in data["modules"]]
    assert nums == list(range(1, 15))
    for m in data["modules"]:
        for f in ("module", "name", "icon", "tagline", "best_score", "unlocked",
                  "attempted", "tier", "next_tier", "points_to_next"):
            assert f in m, f"missing {f} in {m}"
        assert m["best_score"] == 0
        assert m["unlocked"] == False
        assert m["attempted"] == False
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
    assert m2["unlocked"] == True
    assert m2["best_score"] == 85
    assert m2["attempted"] == True
    assert m2["tier"] == "gold"
    assert m2["next_tier"] is None
    assert m2["points_to_next"] is None
    assert data["gold_count"] == 1
    assert data["silver_count"] == 0
    assert data["bronze_count"] == 0
    for n in (1, 3, 4, 5, 6):
        assert mods[n]["unlocked"] == False, f"module {n} should be locked"

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


# ==================== INSTRUCTOR ENDPOINT TESTS ====================

def _get_instructor_vp(student_id, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(
        f"{BASE_URL}/api/instructor/students/{student_id}/venture-path",
        headers=headers, timeout=30,
    )


@pytest.fixture(scope="module")
def super_admin_token(mongo):
    """Seed a super_admin session for tests."""
    suffix = uuid.uuid4().hex[:8]
    user_id = f"TEST_sa_{suffix}"
    token = f"TEST_satok_{suffix}"
    mongo.users.insert_one({
        "user_id": user_id,
        "email": f"TEST_sa_{suffix}@example.com",
        "name": "TEST Super Admin",
        "role": "super_admin",
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": user_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    yield token
    mongo.users.delete_many({"user_id": user_id})
    mongo.user_sessions.delete_many({"user_id": user_id})


def _seed_instructor(mongo, cohort_id=None, use_legacy_field=False):
    suffix = uuid.uuid4().hex[:8]
    user_id = f"TEST_inst_{suffix}"
    token = f"TEST_itok_{suffix}"
    mongo.users.insert_one({
        "user_id": user_id, "email": f"TEST_inst_{suffix}@example.com",
        "name": "TEST Instructor", "role": "instructor",
    })
    mongo.user_sessions.insert_one({
        "session_token": token, "user_id": user_id,
        "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
    })
    if cohort_id:
        if use_legacy_field:
            mongo.cohorts.update_one({"cohort_id": cohort_id}, {"$set": {"instructor_id": user_id}})
        else:
            mongo.cohorts.update_one({"cohort_id": cohort_id}, {"$addToSet": {"instructor_ids": user_id}})
    return {"user_id": user_id, "token": token}


def _cleanup_instructor(mongo, ictx):
    mongo.users.delete_many({"user_id": ictx["user_id"]})
    mongo.user_sessions.delete_many({"user_id": ictx["user_id"]})


class TestInstructorVenturePathAuth:
    def test_no_auth_returns_401(self, student_ctx):
        r = _get_instructor_vp(student_ctx["user_id"])
        assert r.status_code == 401, r.text

    def test_student_role_forbidden(self, student_ctx):
        # A student calling the instructor endpoint (even for themselves) → 403
        r = _get_instructor_vp(student_ctx["user_id"], token=student_ctx["token"])
        assert r.status_code == 403, r.text

    def test_instructor_not_managing_cohort_forbidden(self, mongo, student_ctx):
        ictx = _seed_instructor(mongo, cohort_id=None)
        try:
            r = _get_instructor_vp(student_ctx["user_id"], token=ictx["token"])
            assert r.status_code == 403, r.text
        finally:
            _cleanup_instructor(mongo, ictx)

    def test_instructor_managing_cohort_allowed(self, mongo, student_ctx):
        ictx = _seed_instructor(mongo, cohort_id=student_ctx["cohort_id"])
        try:
            r = _get_instructor_vp(student_ctx["user_id"], token=ictx["token"])
            assert r.status_code == 200, r.text
        finally:
            _cleanup_instructor(mongo, ictx)
            mongo.cohorts.update_one(
                {"cohort_id": student_ctx["cohort_id"]},
                {"$pull": {"instructor_ids": ictx["user_id"]}},
            )

    def test_instructor_legacy_instructor_id_field_allowed(self, mongo, student_ctx):
        ictx = _seed_instructor(mongo, cohort_id=student_ctx["cohort_id"], use_legacy_field=True)
        try:
            r = _get_instructor_vp(student_ctx["user_id"], token=ictx["token"])
            assert r.status_code == 200, r.text
        finally:
            _cleanup_instructor(mongo, ictx)
            mongo.cohorts.update_one(
                {"cohort_id": student_ctx["cohort_id"]},
                {"$unset": {"instructor_id": ""}},
            )

    def test_super_admin_bypasses_cohort_check(self, student_ctx, super_admin_token):
        r = _get_instructor_vp(student_ctx["user_id"], token=super_admin_token)
        assert r.status_code == 200, r.text

    def test_student_not_found_returns_404(self, super_admin_token):
        r = _get_instructor_vp("TEST_does_not_exist_xyz", token=super_admin_token)
        assert r.status_code == 404, r.text


class TestInstructorVenturePathShape:
    def test_response_shape_matches_student_plus_student_field(self, student_ctx, super_admin_token):
        r = _get_instructor_vp(student_ctx["user_id"], token=super_admin_token)
        assert r.status_code == 200, r.text
        data = r.json()
        # Same top-level keys as /student/venture-path
        expected_keys = {"modules", "trend", "unlocked_count", "total_modules",
                         "overall_best_score", "gold_count", "silver_count", "bronze_count"}
        assert expected_keys.issubset(set(data.keys()))
        # Plus a student field with name/email/picture
        assert "student" in data
        assert set(data["student"].keys()) >= {"name", "email"}
        assert data["student"]["name"] == "Test Student"
        assert data["student"]["email"].startswith("TEST_")


class TestInstructorVenturePathScoreMath:
    def test_week3_score_72_gives_silver(self, mongo, super_admin_token):
        """Seed a fresh student, insert readiness_score=72 on week-3 milestone,
        call the instructor endpoint as super_admin, verify module_3.tier=silver
        best_score=72, unlocked_count=1, silver_count=1, plus student.name/email."""
        ctx = _seed_student(mongo)
        try:
            _insert_sub(mongo, ctx, week=3, score=72)
            r = _get_instructor_vp(ctx["user_id"], token=super_admin_token)
            assert r.status_code == 200, r.text
            data = r.json()
            m3 = next(m for m in data["modules"] if m["module"] == 3)
            assert m3["tier"] == "silver"
            assert m3["best_score"] == 72
            assert data["unlocked_count"] == 1
            assert data["silver_count"] == 1
            assert data["gold_count"] == 0
            assert data["bronze_count"] == 0
            assert data["student"]["name"] == "Test Student"
            assert data["student"]["email"].startswith("TEST_")
        finally:
            _cleanup_student(mongo, ctx)


# ============================================================
# 14-module ordering + always-visible locked modules
# ============================================================
class TestFourteenModulesInOrder:
    def test_all_14_modules_returned_in_numerical_order(self, student_ctx, mongo):
        """All 14 modules must appear regardless of what the student submitted."""
        token = student_ctx["token"]
        r = requests.get(
            f"{BASE_URL}/api/student/venture-path",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        module_nums = [m["module"] for m in data["modules"]]
        # Bug #1: numerical curriculum order, always
        assert module_nums == list(range(1, 15)), f"Modules must be 1..14 in order, got {module_nums}"
        # Bug #2: all 14 present even for a student with no submissions
        assert data["total_modules"] == 14
        assert len(data["modules"]) == 14

    def test_completed_module_out_of_order_still_renders_in_curriculum_order(self, mongo):
        """If a student completes Week 5 first, then Week 2, both badges should
        show at their curriculum position (not in submission order)."""
        suffix = uuid.uuid4().hex[:8]
        user_id = f"TEST_ord_{suffix}"
        token = f"TEST_tok_{suffix}"
        cohort_id = f"TEST_coh_{suffix}"
        assignment_id = f"TEST_asg_{suffix}"
        milestones = [
            {"milestone_id": f"TEST_ms_{suffix}_w{w}", "week_number": w, "title": f"Week {w}"}
            for w in range(1, 15)
        ]
        mongo.users.insert_one({
            "user_id": user_id, "email": f"TEST_ord_{suffix}@example.com",
            "name": "Order Test", "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mongo.user_sessions.insert_one({
            "session_token": token, "user_id": user_id,
            "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        })
        mongo.cohorts.insert_one({
            "cohort_id": cohort_id, "name": "Ord Cohort",
            "student_ids": [user_id], "instructor_ids": [],
        })
        mongo.assignments.insert_one({
            "assignment_id": assignment_id, "cohort_id": cohort_id,
            "title": "Test Asg", "milestones": milestones, "is_active": True,
        })
        # Submit Week 5 FIRST (chronologically), then Week 2
        subs = [
            {
                "submission_id": f"TEST_sub_{suffix}_wk5",
                "student_id": user_id, "cohort_id": cohort_id,
                "assignment_id": assignment_id,
                "milestone_id": f"TEST_ms_{suffix}_w5",
                "readiness_score": 88,
                "submitted_at": "2026-01-10T00:00:00+00:00",
            },
            {
                "submission_id": f"TEST_sub_{suffix}_wk2",
                "student_id": user_id, "cohort_id": cohort_id,
                "assignment_id": assignment_id,
                "milestone_id": f"TEST_ms_{suffix}_w2",
                "readiness_score": 72,
                "submitted_at": "2026-01-20T00:00:00+00:00",  # later date, earlier week
            },
        ]
        mongo.submissions.insert_many(subs)
        try:
            r = requests.get(
                f"{BASE_URL}/api/student/venture-path",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            # Bug #1: modules array is in curriculum order 1..14, regardless of submission dates
            module_nums = [m["module"] for m in data["modules"]]
            assert module_nums == list(range(1, 15))
            # Trend is ALSO sorted by week (curriculum order), not submission date
            weeks_in_trend = [t["week"] for t in data["trend"]]
            assert weeks_in_trend == [2, 5], f"Trend should be curriculum order, got {weeks_in_trend}"
            # Bug #2: modules NOT submitted are still present, with tier='none'
            m1 = next(m for m in data["modules"] if m["module"] == 1)
            m14 = next(m for m in data["modules"] if m["module"] == 14)
            assert m1["tier"] == "none" and m1["unlocked"] == False
            assert m14["tier"] == "none" and m14["unlocked"] == False
            # Submitted modules unlocked at correct tier
            m2 = next(m for m in data["modules"] if m["module"] == 2)
            m5 = next(m for m in data["modules"] if m["module"] == 5)
            assert m2["tier"] == "silver" and m2["best_score"] == 72
            assert m5["tier"] == "gold" and m5["best_score"] == 88
        finally:
            mongo.users.delete_one({"user_id": user_id})
            mongo.user_sessions.delete_one({"session_token": token})
            mongo.cohorts.delete_one({"cohort_id": cohort_id})
            mongo.assignments.delete_one({"assignment_id": assignment_id})
            mongo.submissions.delete_many({"submission_id": {"$regex": f"^TEST_sub_{suffix}_"}})

    def test_module_name_overridden_from_curriculum_milestone_title(self, mongo):
        """When a cohort's milestone has a distinctive title, it replaces the
        default VENTURE_PATH_MODULES name for that week."""
        suffix = uuid.uuid4().hex[:8]
        user_id = f"TEST_nm_{suffix}"
        token = f"TEST_tok_{suffix}"
        cohort_id = f"TEST_coh_{suffix}"
        assignment_id = f"TEST_asg_{suffix}"
        milestones = [
            {"milestone_id": f"TEST_ms_{suffix}_w1", "week_number": 1, "title": "Custom Week One Title"},
        ]
        mongo.users.insert_one({
            "user_id": user_id, "email": f"TEST_nm_{suffix}@example.com",
            "name": "Name Test", "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mongo.user_sessions.insert_one({
            "session_token": token, "user_id": user_id,
            "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        })
        mongo.cohorts.insert_one({
            "cohort_id": cohort_id, "name": "Name Cohort",
            "student_ids": [user_id], "instructor_ids": [],
        })
        mongo.assignments.insert_one({
            "assignment_id": assignment_id, "cohort_id": cohort_id,
            "title": "Test Asg", "milestones": milestones, "is_active": True,
        })
        try:
            r = requests.get(
                f"{BASE_URL}/api/student/venture-path",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            data = r.json()
            m1 = next(m for m in data["modules"] if m["module"] == 1)
            # Curriculum name overrides default "Problem-Solution Fit"
            assert m1["name"] == "Custom Week One Title"
            # Default names still used for weeks without a curriculum milestone
            m2 = next(m for m in data["modules"] if m["module"] == 2)
            assert m2["name"] == "Market Master"
        finally:
            mongo.users.delete_one({"user_id": user_id})
            mongo.user_sessions.delete_one({"session_token": token})
            mongo.cohorts.delete_one({"cohort_id": cohort_id})
            mongo.assignments.delete_one({"assignment_id": assignment_id})


# ============================================================
# TestModuleNameOverrides — super_admin editable module names
# (GET/PUT /api/admin/venture-path-modules and E2E propagation)
# ============================================================
def _get_admin_modules(token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(f"{BASE_URL}/api/admin/venture-path-modules", headers=headers, timeout=15)


def _put_admin_modules(payload, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.put(f"{BASE_URL}/api/admin/venture-path-modules", json=payload, headers=headers, timeout=15)


@pytest.fixture(scope="module", autouse=False)
def _reset_overrides(mongo):
    """Ensure the platform_settings overrides doc is cleared before/after this suite."""
    mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
    yield
    mongo.platform_settings.delete_many({"_id": "venture_path_modules"})


class TestModuleNameOverrides:
    def test_get_no_auth_401(self, _reset_overrides):
        r = _get_admin_modules()
        assert r.status_code == 401, r.text

    def test_get_student_forbidden(self, student_ctx, _reset_overrides):
        r = _get_admin_modules(student_ctx["token"])
        assert r.status_code == 403, r.text

    def test_get_instructor_forbidden(self, instructor_ctx, _reset_overrides):
        r = _get_admin_modules(instructor_ctx["token"])
        assert r.status_code == 403, r.text

    def test_get_super_admin_200_shape(self, super_admin_token, _reset_overrides):
        r = _get_admin_modules(super_admin_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) >= {"modules", "defaults", "allowed_icons"}
        assert len(data["modules"]) == 14
        assert len(data["defaults"]) == 14
        assert len(data["allowed_icons"]) == 14
        for m in data["modules"]:
            for f in ("module", "name", "tagline", "icon"):
                assert f in m
        # First load: no overrides → merged == defaults
        for merged, default in zip(data["modules"], data["defaults"]):
            assert merged["module"] == default["module"]
            assert merged["name"] == default["name"]
            assert merged["tagline"] == default["tagline"]
            assert merged["icon"] == default["icon"]

    def test_put_no_auth_401(self):
        r = _put_admin_modules({"modules": [{"module": 1, "name": "X"}]})
        assert r.status_code == 401, r.text

    def test_put_student_forbidden(self, student_ctx):
        r = _put_admin_modules({"modules": [{"module": 1, "name": "X"}]}, token=student_ctx["token"])
        assert r.status_code == 403, r.text

    def test_put_instructor_forbidden(self, instructor_ctx):
        r = _put_admin_modules({"modules": [{"module": 1, "name": "X"}]}, token=instructor_ctx["token"])
        assert r.status_code == 403, r.text

    def test_put_super_admin_persists_and_saved_count(self, super_admin_token, mongo):
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
        payload = {
            "modules": [
                {"module": 1, "name": "Custom Name 1", "tagline": "Custom tag", "icon": "rocket"},
                {"module": 2, "name": "Custom Name 2", "tagline": "T2", "icon": "shield"},
            ]
        }
        r = _put_admin_modules(payload, token=super_admin_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["saved_count"] == 2
        mods = {m["module"]: m for m in data["modules"]}
        assert mods[1]["name"] == "Custom Name 1"
        assert mods[1]["tagline"] == "Custom tag"
        assert mods[1]["icon"] == "rocket"
        assert mods[2]["icon"] == "shield"
        # Persistence: subsequent GET returns same overrides
        g = _get_admin_modules(super_admin_token)
        assert g.status_code == 200
        gdata = g.json()
        gmods = {m["module"]: m for m in gdata["modules"]}
        assert gmods[1]["name"] == "Custom Name 1"
        assert gmods[2]["icon"] == "shield"
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})

    def test_partial_override_falls_back_to_defaults(self, super_admin_token, mongo):
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
        # Only override the NAME of module 3 — tagline+icon should fall back
        r = _put_admin_modules({"modules": [{"module": 3, "name": "Only Name Changed"}]}, token=super_admin_token)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["saved_count"] == 1
        mods = {m["module"]: m for m in data["modules"]}
        # Module 3 defaults
        assert mods[3]["name"] == "Only Name Changed"
        assert mods[3]["tagline"] == "Your value proposition holds up."
        assert mods[3]["icon"] == "layers"
        # Other modules unchanged from defaults
        assert mods[1]["name"] == "Problem-Solution Fit"
        assert mods[14]["name"] == "Demo Day Ready"
        assert mods[14]["icon"] == "star"
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})

    def test_validation_invalid_module_number_400(self, super_admin_token):
        r = _put_admin_modules({"modules": [{"module": 99, "name": "X"}]}, token=super_admin_token)
        assert r.status_code == 400, r.text

    def test_validation_invalid_icon_400(self, super_admin_token):
        r = _put_admin_modules({"modules": [{"module": 1, "icon": "nonexistent-icon"}]}, token=super_admin_token)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        # Should mention allowed icons in error
        assert "allowed" in detail.lower() or "rocket" in detail.lower()

    def test_name_truncated_to_80_chars(self, super_admin_token, mongo):
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
        long_name = "A" * 200
        r = _put_admin_modules({"modules": [{"module": 4, "name": long_name}]}, token=super_admin_token)
        assert r.status_code == 200, r.text
        data = r.json()
        mods = {m["module"]: m for m in data["modules"]}
        assert len(mods[4]["name"]) <= 80
        assert mods[4]["name"] == "A" * 80
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})

    def test_e2e_admin_override_propagates_to_student_view(self, super_admin_token, mongo):
        """Set module 5 override and confirm the student endpoint reflects it
        (when no cohort-milestone title for week 5 exists)."""
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
        # Seed a student without any week-5 milestone title
        ctx = _seed_student(mongo, weeks=(1, 2, 3, 4))  # no week 5 milestone
        try:
            r = _put_admin_modules(
                {"modules": [{"module": 5, "name": "Custom Model Builder"}]},
                token=super_admin_token,
            )
            assert r.status_code == 200, r.text
            r2 = _get_vp(ctx["token"])
            assert r2.status_code == 200, r2.text
            m5 = next(m for m in r2.json()["modules"] if m["module"] == 5)
            assert m5["name"] == "Custom Model Builder"
        finally:
            _cleanup_student(mongo, ctx)
            mongo.platform_settings.delete_many({"_id": "venture_path_modules"})

    def test_curriculum_milestone_title_beats_admin_override(self, super_admin_token, mongo):
        """Hierarchy: cohort_milestone_title > admin_override > code_default."""
        mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
        # Set admin override for module 5
        r = _put_admin_modules(
            {"modules": [{"module": 5, "name": "Admin Override Name"}]},
            token=super_admin_token,
        )
        assert r.status_code == 200, r.text
        # Seed student WITH a week-5 milestone that has a distinctive title
        suffix = uuid.uuid4().hex[:8]
        user_id = f"TEST_h_{suffix}"
        token = f"TEST_tok_{suffix}"
        cohort_id = f"TEST_coh_{suffix}"
        assignment_id = f"TEST_asg_{suffix}"
        milestones = [
            {"milestone_id": f"TEST_ms_{suffix}_w5", "week_number": 5, "title": "Curriculum Week 5 Title"},
        ]
        mongo.users.insert_one({
            "user_id": user_id, "email": f"TEST_h_{suffix}@example.com",
            "name": "Hierarchy Test", "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        mongo.user_sessions.insert_one({
            "session_token": token, "user_id": user_id,
            "expires_at": datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
        })
        mongo.cohorts.insert_one({
            "cohort_id": cohort_id, "name": "H Cohort",
            "student_ids": [user_id], "instructor_ids": [],
        })
        mongo.assignments.insert_one({
            "assignment_id": assignment_id, "cohort_id": cohort_id,
            "title": "H Asg", "milestones": milestones, "is_active": True,
        })
        try:
            r2 = _get_vp(token)
            assert r2.status_code == 200, r2.text
            m5 = next(m for m in r2.json()["modules"] if m["module"] == 5)
            # Curriculum milestone title WINS over admin override
            assert m5["name"] == "Curriculum Week 5 Title", f"Expected curriculum title, got {m5['name']}"
        finally:
            mongo.users.delete_one({"user_id": user_id})
            mongo.user_sessions.delete_one({"session_token": token})
            mongo.cohorts.delete_one({"cohort_id": cohort_id})
            mongo.assignments.delete_one({"assignment_id": assignment_id})
            mongo.platform_settings.delete_many({"_id": "venture_path_modules"})
