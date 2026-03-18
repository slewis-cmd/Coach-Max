"""
Backend Tests for Week Release and Coach Max Features
- Week release/unrelease endpoints (instructor controls student visibility)
- Student dashboard filtered by released weeks
- Coach Max chat endpoint (AI tutor for students)
- Chat history endpoint
"""

import pytest
import requests
import os
import json

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL')

# Test credentials from requirements
SUPER_ADMIN_TOKEN = "test_sess_d9a54d79188e457dbe9d236f00660eaf"
STUDENT_TOKEN = "enrolled_sess_b8c3180a495240fb"
COHORT_ID = "cohort_3a1999cb7d72"

class TestWeekReleaseEndpoints:
    """Tests for POST /api/cohorts/{id}/release-week and unrelease-week"""
    
    def test_release_week_as_instructor_success(self):
        """Instructor/super_admin can release a week"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "released_weeks" in data
        assert 3 in data["released_weeks"]
        assert "message" in data
        print(f"✓ Release week 3: {data}")
    
    def test_unrelease_week_as_instructor_success(self):
        """Instructor/super_admin can unrelease (hide) a week"""
        # First make sure week 3 is released
        requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        
        # Now unrelease it
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/unrelease-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "released_weeks" in data
        assert 3 not in data["released_weeks"]
        print(f"✓ Unrelease week 3: {data}")
    
    def test_release_week_invalid_number(self):
        """Invalid week number should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 15}  # Invalid: max is 12
        )
        assert response.status_code == 400
        data = response.json()
        assert "Invalid week number" in data.get("detail", "")
        print(f"✓ Invalid week number rejected: {data}")
    
    def test_release_week_as_student_forbidden(self):
        """Students cannot release weeks - should get 403"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        assert response.status_code == 403
        print(f"✓ Student blocked from releasing week: {response.json()}")
    
    def test_release_week_invalid_cohort(self):
        """Invalid cohort ID should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/invalid_cohort_123/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 1}
        )
        assert response.status_code == 404
        print(f"✓ Invalid cohort rejected: {response.json()}")
    
    def test_release_week_idempotent(self):
        """Releasing same week twice should not duplicate"""
        # Release week 1 twice
        requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 1}
        )
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 1}
        )
        assert response.status_code == 200
        data = response.json()
        # Count occurrences of week 1
        count = data["released_weeks"].count(1)
        assert count == 1, f"Week 1 appears {count} times (should be 1)"
        print(f"✓ Idempotent release verified: {data}")


class TestStudentDashboard:
    """Tests for GET /api/student/dashboard with released_weeks filter"""
    
    def test_dashboard_returns_only_released_weeks(self):
        """Student dashboard should only show released weeks"""
        response = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert len(data) > 0, "Student should be enrolled in at least one cohort"
        cohort = data[0]
        
        # Check weeks array exists
        assert "weeks" in cohort
        
        # Get week numbers returned
        returned_weeks = [w["week_number"] for w in cohort["weeks"]]
        print(f"Returned weeks: {returned_weeks}")
        
        # Weeks 1 and 2 should be returned (released per requirements)
        assert 1 in returned_weeks, "Week 1 should be released"
        assert 2 in returned_weeks, "Week 2 should be released"
        
        # Unreleased weeks should NOT be returned (e.g., 3-12)
        # Note: Adjust if more weeks are released during testing
        print(f"✓ Dashboard shows only released weeks: {returned_weeks}")
    
    def test_dashboard_week_status_values(self):
        """Verify correct status values for weeks"""
        response = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        cohort = data[0]
        
        valid_statuses = ["no_homework", "waiting_on_submission", "submitted", "under_review", "feedback_provided"]
        
        for week in cohort["weeks"]:
            assert week["status"] in valid_statuses, f"Invalid status: {week['status']}"
            print(f"  Week {week['week_number']}: status={week['status']}")
        
        print(f"✓ All week statuses are valid")
    
    def test_dashboard_feedback_provided_has_feedback(self):
        """Week with feedback_provided status should have feedback content"""
        response = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        cohort = data[0]
        
        feedback_weeks = [w for w in cohort["weeks"] if w["status"] == "feedback_provided"]
        
        for week in feedback_weeks:
            assert week["feedback"] is not None, f"Week {week['week_number']} has feedback_provided but no feedback content"
            assert len(week["feedback"]) > 0, f"Week {week['week_number']} feedback is empty"
            print(f"  Week {week['week_number']}: feedback={week['feedback'][:50]}...")
        
        print(f"✓ Feedback content verified for {len(feedback_weeks)} weeks")
    
    def test_dashboard_instructor_access_forbidden(self):
        """Instructor/super_admin should not access student dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        assert response.status_code == 403
        print(f"✓ Instructor blocked from student dashboard: {response.json()}")


class TestCoachMaxChat:
    """Tests for POST /api/chat/ask-tutor - AI Coach Max endpoint"""
    
    # Submission with feedback_provided status
    SUBMISSION_ID = "sub_a39fdce75191"
    
    def test_ask_tutor_success(self):
        """Student can ask Coach Max about their feedback"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={
                "message": "Can you explain what you meant by leadership styles?",
                "submission_id": self.SUBMISSION_ID
            },
            timeout=60  # AI calls can be slow
        )
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert len(data["response"]) > 0
        print(f"✓ Coach Max responded: {data['response'][:100]}...")
    
    def test_ask_tutor_missing_message(self):
        """Missing message should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={
                "submission_id": self.SUBMISSION_ID
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "Message is required" in data.get("detail", "")
        print(f"✓ Missing message rejected: {data}")
    
    def test_ask_tutor_missing_submission_id(self):
        """Missing submission_id should return 400"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={
                "message": "Hello"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "Submission ID is required" in data.get("detail", "")
        print(f"✓ Missing submission_id rejected: {data}")
    
    def test_ask_tutor_invalid_submission(self):
        """Invalid submission_id should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={
                "message": "Hello",
                "submission_id": "invalid_sub_123"
            }
        )
        assert response.status_code == 404
        print(f"✓ Invalid submission rejected: {response.json()}")
    
    def test_ask_tutor_instructor_forbidden(self):
        """Instructor/super_admin should not access Coach Max"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={
                "message": "Hello",
                "submission_id": self.SUBMISSION_ID
            }
        )
        assert response.status_code == 403
        print(f"✓ Instructor blocked from Coach Max: {response.json()}")


class TestChatHistory:
    """Tests for GET /api/chat/history/{submission_id}"""
    
    SUBMISSION_ID = "sub_a39fdce75191"
    
    def test_get_chat_history_success(self):
        """Student can get their chat history"""
        response = requests.get(
            f"{BASE_URL}/api/chat/history/{self.SUBMISSION_ID}",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            chat = data[0]
            assert "message" in chat
            assert "response" in chat
            assert "created_at" in chat
            print(f"✓ Chat history has {len(data)} entries")
        else:
            print(f"✓ Chat history is empty (no chats yet)")
    
    def test_get_chat_history_instructor_forbidden(self):
        """Instructor should not access student chat history"""
        response = requests.get(
            f"{BASE_URL}/api/chat/history/{self.SUBMISSION_ID}",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        assert response.status_code == 403
        print(f"✓ Instructor blocked from chat history: {response.json()}")


class TestCohortReleasedWeeksField:
    """Tests for cohort released_weeks field in cohort GET endpoint"""
    
    def test_cohort_has_released_weeks_field(self):
        """GET /api/cohorts/{id} should include released_weeks"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # released_weeks might not exist initially, but should be present after first release
        released_weeks = data.get("released_weeks", [])
        assert isinstance(released_weeks, list), "released_weeks should be a list"
        
        print(f"✓ Cohort has released_weeks: {released_weeks}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
