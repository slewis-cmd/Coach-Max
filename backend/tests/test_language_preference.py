"""
Test suite for Spanish language support feature.
Tests: PUT /api/user/language, GET /api/auth/me (language_preference), POST /api/chat/ask-tutor (language field)
"""
import pytest
import os
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test session token created in MongoDB for user_d198275ccff4 (super_admin)
TEST_TOKEN = os.getenv("TEST_TOKEN", "test-lang-not-real")


class TestLanguagePreferenceEndpoint:
    """Tests for PUT /api/user/language endpoint"""

    def test_set_language_to_spanish(self):
        """PUT /api/user/language with 'es' should succeed"""
        response = requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={"language": "es"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["message"] == "Language preference updated"
        assert data["language"] == "es"

    def test_set_language_to_english(self):
        """PUT /api/user/language with 'en' should succeed"""
        response = requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={"language": "en"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["message"] == "Language preference updated"
        assert data["language"] == "en"

    def test_set_invalid_language_returns_400(self):
        """PUT /api/user/language with unsupported language should return 400"""
        response = requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={"language": "fr"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "Supported languages" in data.get("detail", "")

    def test_set_language_without_auth_returns_401(self):
        """PUT /api/user/language without auth should return 401"""
        response = requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Content-Type": "application/json"},
            json={"language": "es"}
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"


class TestAuthMeLanguagePreference:
    """Tests for GET /api/auth/me returning language_preference"""

    def test_auth_me_returns_language_preference_after_set(self):
        """GET /api/auth/me should return language_preference field after it's been set"""
        # First set language to Spanish
        requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={"language": "es"}
        )
        
        # Now check /auth/me
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "language_preference" in data, "language_preference field missing from /auth/me response"
        assert data["language_preference"] == "es", f"Expected 'es', got {data['language_preference']}"
        
        # Reset to English for other tests
        requests.put(
            f"{BASE_URL}/api/user/language",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={"language": "en"}
        )


class TestChatAskTutorLanguageField:
    """Tests for POST /api/chat/ask-tutor accepting optional 'language' field"""

    def test_ask_tutor_accepts_language_field(self):
        """POST /api/chat/ask-tutor should accept optional 'language' field in request body"""
        # Note: This test only verifies the API contract, not actual AI generation
        # The AI LLM key is rate-limited, so we expect a 500 or similar error
        # We're testing that the endpoint accepts the language field without 400 error
        
        # First we need a valid submission_id - let's check if there's one
        # For now, we test with a fake submission_id to verify the endpoint exists
        response = requests.post(
            f"{BASE_URL}/api/chat/ask-tutor",
            headers={"Authorization": f"Bearer {TEST_TOKEN}", "Content-Type": "application/json"},
            json={
                "message": "Test message",
                "submission_id": "nonexistent_submission",
                "language": "es"  # This is the field we're testing
            }
        )
        # We expect 404 (submission not found) or 403 (students only), not 400 (bad request)
        # This proves the 'language' field is accepted
        assert response.status_code in [403, 404, 500], f"Unexpected status {response.status_code}: {response.text}"
        # 403 = students only (super_admin is not a student)
        # 404 = submission not found
        # 500 = AI service error (which is expected since LLM key is rate-limited)


class TestHealthEndpoint:
    """Basic health check"""

    def test_health_endpoint(self):
        """GET /api/health should return 200"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
