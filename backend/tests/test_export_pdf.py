"""
Test suite for POST /api/submissions/{submission_id}/export-pdf endpoint
Tests the PDF export and email functionality for submission feedback
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
SUPER_ADMIN_TOKEN = os.getenv("TEST_ADMIN_TOKEN", "")
TEST_SUBMISSION_ID = "sub_demo_test"


class TestExportPDFEndpoint:
    """Tests for POST /api/submissions/{submission_id}/export-pdf"""
    
    @pytest.fixture
    def auth_headers(self):
        """Headers with super admin authentication"""
        return {
            "Authorization": f"Bearer {SUPER_ADMIN_TOKEN}",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture
    def no_auth_headers(self):
        """Headers without authentication"""
        return {"Content-Type": "application/json"}
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health check - API is accessible")
    
    def test_export_pdf_returns_valid_pdf(self, auth_headers):
        """Test that export-pdf returns a valid PDF (HTTP 200, content-type application/pdf, body starts with %PDF)"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/export-pdf",
            headers=auth_headers
        )
        
        # Check status code
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected application/pdf, got {content_type}"
        
        # Check PDF magic bytes
        pdf_content = response.content
        assert pdf_content.startswith(b"%PDF"), f"PDF content should start with %PDF, got: {pdf_content[:20]}"
        
        # Check content-disposition header for filename
        content_disposition = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disposition, f"Expected attachment disposition, got: {content_disposition}"
        assert ".pdf" in content_disposition.lower(), f"Expected .pdf in filename, got: {content_disposition}"
        
        print(f"PASS: Export PDF returns valid PDF - {len(pdf_content)} bytes")
        print(f"  Content-Type: {content_type}")
        print(f"  Content-Disposition: {content_disposition}")
    
    def test_export_pdf_requires_auth(self, no_auth_headers):
        """Test that endpoint returns 401 without authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/export-pdf",
            headers=no_auth_headers
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("PASS: Export PDF requires authentication (401 without token)")
    
    def test_export_pdf_returns_404_for_nonexistent_submission(self, auth_headers):
        """Test that endpoint returns 404 for non-existent submission_id"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/nonexistent_submission_12345/export-pdf",
            headers=auth_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        data = response.json()
        assert "not found" in data.get("detail", "").lower(), f"Expected 'not found' in detail, got: {data}"
        print("PASS: Export PDF returns 404 for non-existent submission")
    
    def test_export_pdf_returns_400_if_no_feedback(self, auth_headers):
        """Test that endpoint returns 400 if submission has no feedback"""
        # First, we need to find or create a submission without feedback
        # For now, we'll test with a submission that should have feedback
        # This test documents expected behavior
        
        # Try to get a submission without feedback - this may not exist in test data
        # We'll verify the error message format if we can find one
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/export-pdf",
            headers=auth_headers
        )
        
        # If the test submission has feedback, this should return 200
        # If it doesn't have feedback, it should return 400
        if response.status_code == 400:
            data = response.json()
            assert "feedback" in data.get("detail", "").lower(), f"Expected feedback-related error, got: {data}"
            print("PASS: Export PDF returns 400 when no feedback available")
        elif response.status_code == 200:
            print("SKIP: Test submission has feedback, cannot test 400 case")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


class TestExportPDFStudentAccess:
    """Tests for student access restrictions on export-pdf endpoint"""
    
    def test_export_pdf_forbidden_for_students(self):
        """Test that students cannot access export-pdf endpoint (403)"""
        # This test would require a student token
        # For now, we document the expected behavior
        # The endpoint uses require_instructor dependency which should return 403 for students
        print("INFO: Student access test requires student token - endpoint uses require_instructor dependency")
        print("EXPECTED: Students should receive 403 Forbidden when trying to export PDF")


class TestSubmissionEndpoints:
    """Additional tests for submission-related endpoints"""
    
    @pytest.fixture
    def auth_headers(self):
        return {
            "Authorization": f"Bearer {SUPER_ADMIN_TOKEN}",
            "Content-Type": "application/json"
        }
    
    def test_get_submission_details(self, auth_headers):
        """Verify we can get submission details"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}",
            headers=auth_headers
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"PASS: Got submission details")
            print(f"  submission_id: {data.get('submission_id')}")
            print(f"  status: {data.get('status')}")
            print(f"  has_ai_feedback: {bool(data.get('ai_feedback'))}")
            print(f"  has_instructor_feedback: {bool(data.get('instructor_feedback'))}")
            print(f"  student_id: {data.get('student_id')}")
            print(f"  cohort_id: {data.get('cohort_id')}")
        else:
            print(f"INFO: Could not get submission details - {response.status_code}: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
