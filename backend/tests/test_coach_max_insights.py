"""
Test Coach Max Insights endpoints:
- GET /api/cohorts/{cohort_id}/coach-max-report - Raw questions grouped by week
- POST /api/cohorts/{cohort_id}/coach-max-report/generate - AI-generated insights
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test session token for instructor access
TEST_TOKEN = "test-insights"
TEST_COHORT_ID = "cohort_3a1999cb7d72"
EMPTY_COHORT_ID = "cohort_nonexistent_12345"


class TestCoachMaxReport:
    """Tests for GET /api/cohorts/{cohort_id}/coach-max-report endpoint"""

    def test_get_report_without_auth(self):
        """Should return 401 without authorization"""
        response = requests.get(f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: GET coach-max-report returns 401 without auth")

    def test_get_report_with_auth(self):
        """Should return report with weeks array and total_questions"""
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report",
            headers=headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "weeks" in data, "Response should contain 'weeks' key"
        assert "total_questions" in data, "Response should contain 'total_questions' key"
        assert isinstance(data["weeks"], list), "'weeks' should be a list"
        assert isinstance(data["total_questions"], int), "'total_questions' should be an integer"
        print(f"PASS: GET coach-max-report returns valid structure with {data['total_questions']} questions")

    def test_get_report_week_structure(self):
        """Each week should have required fields: week_number, material_title, question_count, unique_students, questions"""
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report",
            headers=headers
        )
        assert response.status_code == 200
        
        data = response.json()
        if data["weeks"]:
            week = data["weeks"][0]
            assert "week_number" in week, "Week should have 'week_number'"
            assert "material_title" in week, "Week should have 'material_title'"
            assert "question_count" in week, "Week should have 'question_count'"
            assert "unique_students" in week, "Week should have 'unique_students'"
            assert "questions" in week, "Week should have 'questions'"
            assert isinstance(week["questions"], list), "'questions' should be a list"
            print(f"PASS: Week structure valid - Week {week['week_number']}: {week['question_count']} questions from {week['unique_students']} students")
        else:
            print("PASS: No weeks data (empty cohort)")

    def test_get_report_question_structure(self):
        """Each question should have student_name, question, response, created_at"""
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report",
            headers=headers
        )
        assert response.status_code == 200
        
        data = response.json()
        if data["weeks"] and data["weeks"][0]["questions"]:
            q = data["weeks"][0]["questions"][0]
            assert "student_name" in q, "Question should have 'student_name'"
            assert "question" in q, "Question should have 'question'"
            assert "response" in q, "Question should have 'response'"
            assert "created_at" in q, "Question should have 'created_at'"
            print(f"PASS: Question structure valid - '{q['question'][:50]}...'")
        else:
            print("PASS: No questions to validate structure")

    def test_get_report_nonexistent_cohort(self):
        """Should return 404 for nonexistent cohort"""
        headers = {"Authorization": f"Bearer {TEST_TOKEN}"}
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{EMPTY_COHORT_ID}/coach-max-report",
            headers=headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: GET coach-max-report returns 404 for nonexistent cohort")


class TestCoachMaxInsightsGeneration:
    """Tests for POST /api/cohorts/{cohort_id}/coach-max-report/generate endpoint"""

    def test_generate_insights_without_auth(self):
        """Should return 401 without authorization"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report/generate",
            json={"week_number": 1}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("PASS: POST generate insights returns 401 without auth")

    def test_generate_insights_with_week(self):
        """Should generate AI insights for specific week"""
        headers = {
            "Authorization": f"Bearer {TEST_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report/generate",
            headers=headers,
            json={"week_number": 1},
            timeout=60  # AI generation can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "summary" in data, "Response should contain 'summary'"
        assert "themes" in data, "Response should contain 'themes'"
        assert "recommendations" in data, "Response should contain 'recommendations'"
        assert isinstance(data["themes"], list), "'themes' should be a list"
        assert isinstance(data["recommendations"], list), "'recommendations' should be a list"
        print(f"PASS: AI insights generated - {len(data['themes'])} themes, {len(data['recommendations'])} recommendations")

    def test_generate_insights_theme_structure(self):
        """Each theme should have theme name, count, and examples"""
        headers = {
            "Authorization": f"Bearer {TEST_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report/generate",
            headers=headers,
            json={"week_number": 1},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        if data["themes"]:
            theme = data["themes"][0]
            assert "theme" in theme, "Theme should have 'theme' name"
            assert "count" in theme, "Theme should have 'count'"
            assert "examples" in theme, "Theme should have 'examples'"
            print(f"PASS: Theme structure valid - '{theme['theme']}' ({theme['count']} questions)")
        else:
            print("PASS: No themes generated (may be due to limited data)")

    def test_generate_insights_nonexistent_cohort(self):
        """Should return 404 for nonexistent cohort"""
        headers = {
            "Authorization": f"Bearer {TEST_TOKEN}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{EMPTY_COHORT_ID}/coach-max-report/generate",
            headers=headers,
            json={"week_number": 1}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: POST generate insights returns 404 for nonexistent cohort")

    def test_generate_insights_empty_week(self):
        """Should return graceful response for week with no questions"""
        headers = {
            "Authorization": f"Bearer {TEST_TOKEN}",
            "Content-Type": "application/json"
        }
        # Week 99 should have no data
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TEST_COHORT_ID}/coach-max-report/generate",
            headers=headers,
            json={"week_number": 99},
            timeout=60
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "summary" in data, "Response should contain 'summary'"
        # Should indicate no conversations found
        print(f"PASS: Empty week returns graceful response - '{data['summary'][:50]}...'")


class TestHealthCheck:
    """Basic health check"""

    def test_health_endpoint(self):
        """Health endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Health endpoint returns 200")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
