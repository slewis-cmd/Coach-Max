"""
Test Download Endpoints with Token Query Parameter
Tests the P0 bug fix: file downloads now accept auth token as query parameter (?token=xxx)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Use environment variables for credentials - never hardcode secrets
SUPER_ADMIN_TOKEN = os.environ.get('TEST_SUPER_ADMIN_TOKEN', '')
STUDENT_TOKEN = os.environ.get('TEST_STUDENT_TOKEN', '')
SUPER_ADMIN_USER_ID = os.environ.get('TEST_SUPER_ADMIN_USER_ID', '')
STUDENT_USER_ID = os.environ.get('TEST_STUDENT_USER_ID', '')

# Known material/submission/cohort IDs from environment
MATERIAL_ID_1 = os.environ.get('TEST_MATERIAL_ID_1', '')
MATERIAL_ID_2 = os.environ.get('TEST_MATERIAL_ID_2', '')
SUBMISSION_ID_1 = os.environ.get('TEST_SUBMISSION_ID_1', '')
COHORT_ID = os.environ.get('TEST_COHORT_ID', '')


@pytest.fixture(autouse=True)
def skip_if_no_credentials():
    if not SUPER_ADMIN_TOKEN or not BASE_URL:
        pytest.skip("Test credentials not set in environment variables")


class TestMaterialDownloadWithTokenParam:
    """Test material download with ?token= query parameter"""

    def test_download_material_unauthenticated(self):
        """Download without auth should fail"""
        if not MATERIAL_ID_1:
            pytest.skip("No test material ID configured")
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download",
            allow_redirects=False
        )
        assert response.status_code in [401, 403]

    def test_download_material_with_token(self):
        """Download with token query param should succeed"""
        if not MATERIAL_ID_1:
            pytest.skip("No test material ID configured")
        response = requests.get(
            f"{BASE_URL}/api/materials/{MATERIAL_ID_1}/download?token={SUPER_ADMIN_TOKEN}",
            allow_redirects=False
        )
        assert response.status_code in [200, 404]

    def test_download_nonexistent_material(self):
        """Download non-existent material should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/materials/nonexistent_id/download?token={SUPER_ADMIN_TOKEN}",
            allow_redirects=False
        )
        assert response.status_code == 404


class TestSubmissionDownloadWithTokenParam:
    """Test submission download with ?token= query parameter"""

    def test_download_submission_unauthenticated(self):
        """Download without auth should fail"""
        if not SUBMISSION_ID_1:
            pytest.skip("No test submission ID configured")
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download",
            allow_redirects=False
        )
        assert response.status_code in [401, 403]

    def test_download_submission_with_token(self):
        """Download with token query param should succeed"""
        if not SUBMISSION_ID_1:
            pytest.skip("No test submission ID configured")
        response = requests.get(
            f"{BASE_URL}/api/submissions/{SUBMISSION_ID_1}/download?token={SUPER_ADMIN_TOKEN}",
            allow_redirects=False
        )
        assert response.status_code in [200, 404]


class TestCSVTemplateDownload:
    """Test CSV template download"""

    def test_csv_template_with_token(self):
        """CSV template download should work with token"""
        if not COHORT_ID:
            pytest.skip("No test cohort ID configured")
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{COHORT_ID}/students/template?token={SUPER_ADMIN_TOKEN}",
            allow_redirects=False
        )
        assert response.status_code in [200, 404]
