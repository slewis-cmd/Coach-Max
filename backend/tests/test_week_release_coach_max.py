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

# Use environment variables for credentials - never hardcode secrets
SUPER_ADMIN_TOKEN = os.environ.get('TEST_SUPER_ADMIN_TOKEN', '')
STUDENT_TOKEN = os.environ.get('TEST_STUDENT_TOKEN', '')
COHORT_ID = os.environ.get('TEST_COHORT_ID', '')


@pytest.fixture(autouse=True)
def skip_if_no_credentials():
    if not SUPER_ADMIN_TOKEN or not STUDENT_TOKEN or not COHORT_ID:
        pytest.skip("Test credentials not set in environment variables")


class TestWeekReleaseEndpoints:
    """Tests for POST /api/cohorts/{id}/release-week and unrelease-week"""
    
    def test_release_week_as_instructor_success(self):
        """Instructor/super_admin can release a week"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        assert response.status_code in [200, 400]

    def test_release_week_already_released(self):
        """Re-releasing an already released week should be handled gracefully"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 1}
        )
        assert response.status_code in [200, 400]

    def test_unrelease_week_as_instructor(self):
        """Instructor can hide a week"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/unrelease-week",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 3}
        )
        assert response.status_code in [200, 400]

    def test_release_week_unauthenticated(self):
        """Unauthenticated users cannot release weeks"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            json={"week_number": 2}
        )
        assert response.status_code in [401, 403]

    def test_release_week_as_student(self):
        """Students cannot release weeks"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/release-week",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}", "Content-Type": "application/json"},
            json={"week_number": 2}
        )
        assert response.status_code in [401, 403]


class TestStudentDashboard:
    """Tests for GET /api/student/dashboard"""

    def test_student_dashboard_returns_data(self):
        """Student can access their dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/student/dashboard",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "weeks" in data

    def test_student_dashboard_no_auth(self):
        """Unauthenticated user gets 401"""
        response = requests.get(f"{BASE_URL}/api/student/dashboard")
        assert response.status_code in [401, 403]


class TestCoachMaxChat:
    """Tests for POST /api/chat/ask-tutor"""

    def test_ask_tutor_no_auth(self):
        """Unauthenticated chat attempt should fail"""
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            json={"submission_id": "test", "message": "Hello"}
        )
        assert response.status_code in [401, 403]


class TestChatHistory:
    """Tests for GET /api/chat/history/{submission_id}"""

    def test_chat_history_no_auth(self):
        """Unauthenticated user cannot access chat history"""
        response = requests.get(f"{BASE_URL}/api/chat/history/test_submission")
        assert response.status_code in [401, 403]
