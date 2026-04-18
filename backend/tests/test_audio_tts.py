"""
Audio TTS Feature Tests
Tests for:
- POST /api/submissions/{id}/audio - generates MP3 from feedback text, caches result
- POST /api/chat/audio - generates MP3 from arbitrary text
- GET /api/audio/{filename} - serves MP3 file with correct content-type
- Caching - second call returns cached:true
- Validation - empty text returns 400, non-existent submission returns 404
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test session token (created in MongoDB)
TEST_TOKEN = "test-audio"
TEST_SUBMISSION_ID = "sub_7bf4870c7bd8"


@pytest.fixture
def auth_headers():
    """Headers with authentication token"""
    return {
        "Authorization": f"Bearer {TEST_TOKEN}",
        "Content-Type": "application/json"
    }


class TestHealthCheck:
    """Basic health check"""
    
    def test_health_endpoint(self):
        """Verify API is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health check returns 200 with status=healthy")


class TestSubmissionAudioEndpoint:
    """Tests for POST /api/submissions/{id}/audio"""
    
    def test_submission_audio_requires_auth(self):
        """Audio generation requires authentication"""
        response = requests.post(f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/audio")
        assert response.status_code == 401
        print("PASS: POST /api/submissions/{id}/audio returns 401 without auth")
    
    def test_submission_audio_not_found(self, auth_headers):
        """Non-existent submission returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/nonexistent_sub_123/audio",
            headers=auth_headers
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data.get("detail", "").lower()
        print("PASS: POST /api/submissions/nonexistent/audio returns 404")
    
    def test_submission_audio_generates_mp3(self, auth_headers):
        """Valid submission with feedback generates audio"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/audio",
            headers=auth_headers,
            timeout=60  # TTS can take time
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "audio_url" in data
        assert data["audio_url"].startswith("/api/audio/")
        assert data["audio_url"].endswith(".mp3")
        assert "cached" in data
        
        print(f"PASS: POST /api/submissions/{TEST_SUBMISSION_ID}/audio returns 200")
        print(f"  audio_url: {data['audio_url']}")
        print(f"  cached: {data['cached']}")
        
        return data["audio_url"]
    
    def test_submission_audio_caching(self, auth_headers):
        """Second call returns cached:true"""
        # First call (may or may not be cached from previous test)
        response1 = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/audio",
            headers=auth_headers,
            timeout=60
        )
        assert response1.status_code == 200
        data1 = response1.json()
        
        # Second call should be cached
        response2 = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/audio",
            headers=auth_headers,
            timeout=60
        )
        assert response2.status_code == 200
        data2 = response2.json()
        
        # Second call should return cached:true
        assert data2.get("cached") == True
        # URLs should be the same
        assert data1["audio_url"] == data2["audio_url"]
        
        print("PASS: Second call to submission audio returns cached:true")
        print(f"  Same URL returned: {data2['audio_url']}")


class TestChatAudioEndpoint:
    """Tests for POST /api/chat/audio"""
    
    def test_chat_audio_requires_auth(self):
        """Chat audio requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/chat/audio",
            json={"text": "Hello world"}
        )
        assert response.status_code == 401
        print("PASS: POST /api/chat/audio returns 401 without auth")
    
    def test_chat_audio_empty_text_returns_400(self, auth_headers):
        """Empty text returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/chat/audio",
            headers=auth_headers,
            json={"text": ""}
        )
        assert response.status_code == 400
        data = response.json()
        assert "text" in data.get("detail", "").lower() or "required" in data.get("detail", "").lower()
        print("PASS: POST /api/chat/audio with empty text returns 400")
    
    def test_chat_audio_missing_text_returns_400(self, auth_headers):
        """Missing text field returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/chat/audio",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 400
        print("PASS: POST /api/chat/audio with missing text returns 400")
    
    def test_chat_audio_generates_mp3(self, auth_headers):
        """Valid text generates audio"""
        test_text = "Hello, this is a test message from Coach Max."
        response = requests.post(
            f"{BASE_URL}/api/chat/audio",
            headers=auth_headers,
            json={"text": test_text},
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check response structure
        assert "audio_url" in data
        assert data["audio_url"].startswith("/api/audio/")
        assert data["audio_url"].endswith(".mp3")
        
        print("PASS: POST /api/chat/audio generates MP3")
        print(f"  audio_url: {data['audio_url']}")
        
        return data["audio_url"]


class TestServeAudioEndpoint:
    """Tests for GET /api/audio/{filename}"""
    
    def test_serve_audio_not_found(self):
        """Non-existent audio file returns 404"""
        response = requests.get(f"{BASE_URL}/api/audio/nonexistent_file.mp3")
        assert response.status_code == 404
        print("PASS: GET /api/audio/nonexistent returns 404")
    
    def test_serve_audio_returns_mp3(self, auth_headers):
        """Serving audio returns correct content-type"""
        # First generate an audio file
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/audio",
            headers=auth_headers,
            timeout=60
        )
        assert response.status_code == 200
        audio_url = response.json()["audio_url"]
        
        # Now fetch the audio file
        audio_response = requests.get(f"{BASE_URL}{audio_url}")
        assert audio_response.status_code == 200
        
        # Check content-type
        content_type = audio_response.headers.get("Content-Type", "")
        assert "audio/mpeg" in content_type
        
        # Check content-disposition (should be attachment for download)
        content_disposition = audio_response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition
        assert ".mp3" in content_disposition
        
        # Check that we got actual audio data (should be > 1KB for any real audio)
        assert len(audio_response.content) > 1000
        
        print("PASS: GET /api/audio/{filename} returns audio/mpeg")
        print(f"  Content-Type: {content_type}")
        print(f"  Content-Disposition: {content_disposition}")
        print(f"  File size: {len(audio_response.content)} bytes")


class TestSubmissionWithoutFeedback:
    """Test edge case: submission without feedback"""
    
    def test_submission_no_feedback_returns_400(self, auth_headers):
        """Submission without feedback returns 400"""
        # Create a test submission without feedback
        import pymongo
        from datetime import datetime, timezone
        
        client = pymongo.MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        test_sub_id = "sub_test_no_feedback"
        
        # Clean up any existing test submission
        db.submissions.delete_one({"submission_id": test_sub_id})
        
        # Create submission without feedback
        db.submissions.insert_one({
            "submission_id": test_sub_id,
            "material_id": "mat_test",
            "cohort_id": "cohort_test",
            "student_id": "user_test",
            "file_path": "/tmp/test.pdf",
            "file_name": "test.pdf",
            "status": "pending",
            "ai_feedback": None,
            "instructor_feedback": None,
            "submitted_at": datetime.now(timezone.utc).isoformat()
        })
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/submissions/{test_sub_id}/audio",
                headers=auth_headers
            )
            assert response.status_code == 400
            data = response.json()
            assert "feedback" in data.get("detail", "").lower()
            print("PASS: Submission without feedback returns 400")
        finally:
            # Clean up
            db.submissions.delete_one({"submission_id": test_sub_id})
            client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
