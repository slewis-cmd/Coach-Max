"""
Test Download Endpoints with Token Query Parameter
Tests the P0 bug fix: file downloads now accept auth token as query parameter (?token=xxx)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from the review request
SUPER_ADMIN_TOKEN = "62BSlTaC4MP-CCoAg-y1pUhBvqris4jL7iv1SNYaa6c"
STUDENT_TOKEN = "kYAqjcbme9Hago6smk_zzn-MkMWMesnJt0v1-HZxUpc"
SUPER_ADMIN_USER_ID = "user_d198275ccff4"
STUDENT_USER_ID = "user_a22492fa9973"

# Known material IDs
MATERIAL_ID_1 = "mat_ad6d2da5e1cd"  # week2_homework.pdf
MATERIAL_ID_2 = "mat_ab936a2cb162"  # week1_workbook.pdf
MATERIAL_ID_3 = "mat_66b6d55ebe08"  # Module-2-Workbook.pdf

# Known submission IDs
SUBMISSION_ID_1 = "sub_b041c9168836"  # my_submission.pdf
SUBMISSION_ID_2 = "sub_88670613c572"  # ShiftSure Case Activity.pdf

# Known cohort ID
COHORT_ID = "cohort_3a1999cb7d72"


class TestMaterialDownloadWithTokenParam:
    """Test GET /api/materials/{material_id}/download?token=xxx"""
    
    def test_download_material_with_token_query_param(self):
        """Material download should work with token as query parameter"""
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download",
            params={"token": SUPER_ADMIN_TOKEN},
            allow_redirects=True
        )
        print(f"Material download with token param: {response.status_code}")
        # Should return 200 or file content
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Verify it's a file response (has content)
        assert len(response.content) > 0, "Response should have file content"
        print(f"SUCCESS: Material download returned {len(response.content)} bytes")
    
    def test_download_material_with_bearer_header(self):
        """Material download should still work with Authorization Bearer header"""
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        print(f"Material download with Bearer header: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert len(response.content) > 0, "Response should have file content"
        print(f"SUCCESS: Material download with Bearer header returned {len(response.content)} bytes")
    
    def test_download_material_without_token_returns_401(self):
        """Material download without any token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download"
        )
        print(f"Material download without token: {response.status_code}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("SUCCESS: Material download without token returns 401")
    
    def test_download_material_with_invalid_token_returns_401(self):
        """Material download with invalid token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download",
            params={"token": "invalid_token_12345"}
        )
        print(f"Material download with invalid token: {response.status_code}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("SUCCESS: Material download with invalid token returns 401")
    
    def test_download_material_student_token(self):
        """Student should be able to download materials from their cohort"""
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download",
            params={"token": STUDENT_TOKEN}
        )
        print(f"Material download with student token: {response.status_code}")
        # Student should have access if enrolled in the cohort
        assert response.status_code in [200, 403], f"Expected 200 or 403, got {response.status_code}"
        if response.status_code == 200:
            print(f"SUCCESS: Student can download material ({len(response.content)} bytes)")
        else:
            print("INFO: Student doesn't have access to this material (403)")


class TestSubmissionDownloadWithTokenParam:
    """Test GET /api/submissions/{submission_id}/download?token=xxx"""
    
    def test_download_submission_with_token_query_param(self):
        """Submission download should work with token as query parameter"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download",
            params={"token": SUPER_ADMIN_TOKEN}
        )
        print(f"Submission download with token param: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert len(response.content) > 0, "Response should have file content"
        print(f"SUCCESS: Submission download returned {len(response.content)} bytes")
    
    def test_download_submission_with_bearer_header(self):
        """Submission download should still work with Authorization Bearer header"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        print(f"Submission download with Bearer header: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        assert len(response.content) > 0, "Response should have file content"
        print(f"SUCCESS: Submission download with Bearer header returned {len(response.content)} bytes")
    
    def test_download_submission_without_token_returns_401(self):
        """Submission download without any token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download"
        )
        print(f"Submission download without token: {response.status_code}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("SUCCESS: Submission download without token returns 401")
    
    def test_download_submission_with_invalid_token_returns_401(self):
        """Submission download with invalid token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download",
            params={"token": "invalid_token_12345"}
        )
        print(f"Submission download with invalid token: {response.status_code}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("SUCCESS: Submission download with invalid token returns 401")
    
    def test_download_submission_second_file(self):
        """Test downloading second submission file"""
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_2}/download",
            params={"token": SUPER_ADMIN_TOKEN}
        )
        print(f"Second submission download: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"SUCCESS: Second submission download returned {len(response.content)} bytes")


class TestStudentTemplateDownloadWithTokenParam:
    """Test GET /api/cohorts/{cohort_id}/students/template?token=xxx"""
    
    def test_download_template_with_token_query_param(self):
        """Student template download should work with token as query parameter"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/students/template",
            params={"token": SUPER_ADMIN_TOKEN}
        )
        print(f"Template download with token param: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        # Verify it's a CSV file
        content = response.text
        assert "email" in content.lower(), "Template should contain 'email' column"
        assert "name" in content.lower(), "Template should contain 'name' column"
        print(f"SUCCESS: Template download returned CSV content:\n{content[:200]}")
    
    def test_download_template_with_bearer_header(self):
        """Student template download should still work with Authorization Bearer header"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/students/template",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        print(f"Template download with Bearer header: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: Template download with Bearer header works")
    
    def test_download_template_without_token_returns_401(self):
        """Student template download without any token should return 401"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/students/template"
        )
        print(f"Template download without token: {response.status_code}")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("SUCCESS: Template download without token returns 401")
    
    def test_download_template_student_forbidden(self):
        """Student should not be able to download template (instructor only)"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/students/template",
            params={"token": STUDENT_TOKEN}
        )
        print(f"Template download with student token: {response.status_code}")
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("SUCCESS: Student cannot download template (403)")


class TestAuthMeEndpoint:
    """Verify auth/me works to confirm tokens are valid"""
    
    def test_auth_me_super_admin(self):
        """Verify super admin token is valid"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {SUPER_ADMIN_TOKEN}"}
        )
        print(f"Auth/me super admin: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("user_id") == SUPER_ADMIN_USER_ID, f"User ID mismatch: {data.get('user_id')}"
        assert data.get("role") == "super_admin", f"Role should be super_admin: {data.get('role')}"
        print(f"SUCCESS: Super admin token valid - {data.get('name')} ({data.get('email')})")
    
    def test_auth_me_student(self):
        """Verify student token is valid"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        print(f"Auth/me student: {response.status_code}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("user_id") == STUDENT_USER_ID, f"User ID mismatch: {data.get('user_id')}"
        assert data.get("role") == "student", f"Role should be student: {data.get('role')}"
        print(f"SUCCESS: Student token valid - {data.get('name')} ({data.get('email')})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
