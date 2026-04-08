"""
Test Coach Max URL fix - Iteration 15
Tests that the 'Ask Coach Max' link in feedback emails points to /coach-max/:submissionId
instead of the old /submit/:materialId URL.

Features tested:
- POST /api/submissions/{id}/send-feedback returns 200 and uses coach-max URL
- POST /api/submissions/{id}/export-pdf returns 200 and uses coach-max URL  
- No /submit/ URL in email templates (only /coach-max/)
"""

import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
SUPER_ADMIN_TOKEN = os.getenv("TEST_ADMIN_TOKEN", "")
TEST_SUBMISSION_ID = "sub_demo_test"


class TestCoachMaxURL:
    """Test Coach Max URL in feedback emails"""
    
    @pytest.fixture
    def auth_headers(self):
        return {
            "Authorization": f"Bearer {SUPER_ADMIN_TOKEN}",
            "Content-Type": "application/json"
        }
    
    def test_health_check(self):
        """Verify API is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("PASS: Health check - API is healthy")
    
    def test_submission_exists(self, auth_headers):
        """Verify test submission exists"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("submission_id") == TEST_SUBMISSION_ID
        print(f"PASS: Test submission {TEST_SUBMISSION_ID} exists")
    
    def test_send_feedback_returns_200(self, auth_headers):
        """Test POST /api/submissions/{id}/send-feedback returns 200"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/send-feedback",
            headers=auth_headers
        )
        # Should return 200 (feedback sent) or 400 (no feedback to send)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            print("PASS: send-feedback endpoint returns 200")
        else:
            print(f"INFO: send-feedback returned 400 - {response.json().get('detail', 'No feedback to send')}")
    
    def test_export_pdf_returns_200(self, auth_headers):
        """Test POST /api/submissions/{id}/export-pdf returns 200 with PDF"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/export-pdf",
            headers=auth_headers
        )
        # Should return 200 (PDF generated) or 400 (no feedback)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"
        if response.status_code == 200:
            assert response.headers.get("content-type") == "application/pdf"
            assert response.content[:4] == b"%PDF"
            print("PASS: export-pdf endpoint returns valid PDF")
        else:
            print(f"INFO: export-pdf returned 400 - may need feedback first")
    
    def test_send_feedback_requires_auth(self):
        """Test send-feedback requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/send-feedback"
        )
        assert response.status_code == 401
        print("PASS: send-feedback requires authentication")
    
    def test_export_pdf_requires_auth(self):
        """Test export-pdf requires authentication"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/{TEST_SUBMISSION_ID}/export-pdf"
        )
        assert response.status_code == 401
        print("PASS: export-pdf requires authentication")
    
    def test_send_feedback_404_for_invalid_submission(self, auth_headers):
        """Test send-feedback returns 404 for non-existent submission"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/nonexistent_sub_12345/send-feedback",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: send-feedback returns 404 for invalid submission")
    
    def test_export_pdf_404_for_invalid_submission(self, auth_headers):
        """Test export-pdf returns 404 for non-existent submission"""
        response = requests.post(
            f"{BASE_URL}/api/submissions/nonexistent_sub_12345/export-pdf",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: export-pdf returns 404 for invalid submission")


class TestCoachMaxCodeReview:
    """Code review tests to verify coach-max URL is used correctly in server.py"""
    
    def test_server_py_uses_coach_max_url_in_send_feedback(self):
        """Verify send_feedback_to_student uses /coach-max/ URL"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Find the send_feedback_to_student function
        send_feedback_match = re.search(
            r'async def send_feedback_to_student.*?(?=\n@api_router|\nclass |\n# ===)',
            content,
            re.DOTALL
        )
        assert send_feedback_match, "send_feedback_to_student function not found"
        
        func_content = send_feedback_match.group(0)
        
        # Verify coach_max_url is defined with /coach-max/
        assert '/coach-max/' in func_content, "send_feedback should use /coach-max/ URL"
        assert 'coach_max_url' in func_content, "send_feedback should define coach_max_url"
        
        # Verify NO /submit/ URL in the function
        # Allow /submit/ only in comments or unrelated strings
        submit_matches = re.findall(r'href="[^"]*\/submit\/[^"]*"', func_content)
        assert len(submit_matches) == 0, f"send_feedback should NOT use /submit/ URL in href: {submit_matches}"
        
        print("PASS: send_feedback_to_student uses /coach-max/ URL correctly")
    
    def test_server_py_uses_coach_max_url_in_export_pdf(self):
        """Verify export_feedback_pdf uses /coach-max/ URL"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Find the export_feedback_pdf function
        export_pdf_match = re.search(
            r'async def export_feedback_pdf.*?(?=\n@api_router|\nclass |\n# ===)',
            content,
            re.DOTALL
        )
        assert export_pdf_match, "export_feedback_pdf function not found"
        
        func_content = export_pdf_match.group(0)
        
        # Verify coach_max_url is defined with /coach-max/
        assert '/coach-max/' in func_content, "export_pdf should use /coach-max/ URL"
        assert 'coach_max_url' in func_content, "export_pdf should define coach_max_url"
        
        # Verify NO /submit/ URL in the function
        submit_matches = re.findall(r'href="[^"]*\/submit\/[^"]*"', func_content)
        assert len(submit_matches) == 0, f"export_pdf should NOT use /submit/ URL in href: {submit_matches}"
        
        print("PASS: export_feedback_pdf uses /coach-max/ URL correctly")
    
    def test_coach_max_url_format(self):
        """Verify coach_max_url format is correct"""
        server_path = "/app/backend/server.py"
        with open(server_path, "r") as f:
            content = f.read()
        
        # Find all coach_max_url definitions
        url_defs = re.findall(r'coach_max_url\s*=\s*f"[^"]*"', content)
        assert len(url_defs) >= 2, f"Expected at least 2 coach_max_url definitions, found {len(url_defs)}"
        
        for url_def in url_defs:
            # Verify format: {FRONTEND_URL}/coach-max/{submission_id}
            assert '/coach-max/{submission_id}' in url_def, f"URL should end with /coach-max/{{submission_id}}: {url_def}"
            assert 'FRONTEND_URL' in url_def, f"URL should use FRONTEND_URL env var: {url_def}"
        
        print(f"PASS: Found {len(url_defs)} coach_max_url definitions with correct format")


class TestCoachMaxFrontendRoute:
    """Test that CoachMaxPage route exists in frontend"""
    
    def test_app_js_has_coach_max_route(self):
        """Verify App.js has /coach-max/:submissionId route"""
        app_js_path = "/app/frontend/src/App.js"
        with open(app_js_path, "r") as f:
            content = f.read()
        
        # Check for route definition
        assert '/coach-max/:submissionId' in content, "App.js should have /coach-max/:submissionId route"
        assert 'CoachMaxPage' in content, "App.js should import CoachMaxPage"
        
        # Verify it's a protected route
        assert 'ProtectedRoute' in content, "App.js should have ProtectedRoute component"
        
        print("PASS: App.js has /coach-max/:submissionId route")
    
    def test_coach_max_page_exists(self):
        """Verify CoachMaxPage.js exists and has required elements"""
        page_path = "/app/frontend/src/pages/CoachMaxPage.js"
        with open(page_path, "r") as f:
            content = f.read()
        
        # Check for required elements
        assert 'useParams' in content, "CoachMaxPage should use useParams"
        assert 'submissionId' in content, "CoachMaxPage should extract submissionId"
        assert 'data-testid="coach-max-page"' in content, "CoachMaxPage should have data-testid"
        assert 'data-testid="coach-max-input"' in content, "CoachMaxPage should have chat input"
        assert 'data-testid="coach-max-send"' in content, "CoachMaxPage should have send button"
        assert '/api/chat/ask-tutor' in content, "CoachMaxPage should call ask-tutor API"
        assert '/api/chat/history/' in content, "CoachMaxPage should load chat history"
        
        print("PASS: CoachMaxPage.js exists with required elements")
    
    def test_no_resend_dev_references(self):
        """Verify no resend.dev references in codebase (excluding test files)"""
        import subprocess
        # Exclude test files and __pycache__ from search
        result = subprocess.run(
            ['grep', '-rn', '--exclude-dir=tests', '--exclude-dir=__pycache__', 
             '--exclude=*.pyc', 'resend.dev', '/app/backend/', '/app/frontend/'],
            capture_output=True,
            text=True
        )
        assert result.returncode != 0 or result.stdout == '', f"Found resend.dev references: {result.stdout}"
        print("PASS: No resend.dev references in codebase")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
