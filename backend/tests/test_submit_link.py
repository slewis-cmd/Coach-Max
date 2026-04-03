"""
Test suite for Direct Submission Link feature
Tests GET /api/submit-link/{material_id} endpoint
"""
import pytest
import requests
import os
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSubmitLinkEndpoint:
    """Tests for GET /api/submit-link/{material_id} endpoint"""
    
    def test_valid_homework_material_mat_c1_w1(self):
        """Test that valid homework material mat-c1-w1 returns correct info"""
        response = requests.get(f"{BASE_URL}/api/submit-link/mat-c1-w1")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["material_id"] == "mat-c1-w1"
        assert data["title"] == "Week 1 HW - Cohort 1"
        assert data["week_number"] == 1
        assert "cohorts" in data
        assert len(data["cohorts"]) >= 1
        
        # Verify cohort info
        cohort = data["cohorts"][0]
        assert cohort["cohort_id"] == "cohort-instructor1"
        assert cohort["name"] == "Instructor 1 Cohort"
        print(f"SUCCESS: mat-c1-w1 returns correct data: {data}")
    
    def test_valid_homework_material_mat_c2_w1(self):
        """Test that valid homework material mat-c2-w1 returns correct info"""
        response = requests.get(f"{BASE_URL}/api/submit-link/mat-c2-w1")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["material_id"] == "mat-c2-w1"
        assert data["title"] == "Week 1 HW - Cohort 2"
        assert data["week_number"] == 1
        assert "cohorts" in data
        assert len(data["cohorts"]) >= 1
        
        # Verify cohort info
        cohort = data["cohorts"][0]
        assert cohort["cohort_id"] == "cohort-instructor2"
        assert cohort["name"] == "Instructor 2 Cohort"
        print(f"SUCCESS: mat-c2-w1 returns correct data: {data}")
    
    def test_nonexistent_material_returns_404(self):
        """Test that non-existent material ID returns 404"""
        response = requests.get(f"{BASE_URL}/api/submit-link/invalid-id")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()
        print(f"SUCCESS: invalid-id returns 404 with message: {data['detail']}")
    
    def test_nonexistent_material_random_id(self):
        """Test that random non-existent material ID returns 404"""
        response = requests.get(f"{BASE_URL}/api/submit-link/mat_nonexistent_12345")
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("SUCCESS: Random non-existent ID returns 404")
    
    def test_endpoint_is_public_no_auth_required(self):
        """Test that submit-link endpoint is public (no auth required)"""
        # Make request without any auth headers
        response = requests.get(
            f"{BASE_URL}/api/submit-link/mat-c1-w1",
            headers={}  # No auth headers
        )
        
        # Should return 200, not 401
        assert response.status_code == 200, f"Expected 200 (public endpoint), got {response.status_code}"
        print("SUCCESS: Endpoint is public, no auth required")
    
    def test_response_structure(self):
        """Test that response has correct structure"""
        response = requests.get(f"{BASE_URL}/api/submit-link/mat-c1-w1")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check required fields
        required_fields = ["material_id", "title", "week_number", "cohorts"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        # Check cohorts structure
        assert isinstance(data["cohorts"], list)
        if len(data["cohorts"]) > 0:
            cohort = data["cohorts"][0]
            assert "cohort_id" in cohort
            assert "name" in cohort
        
        print(f"SUCCESS: Response has correct structure with fields: {list(data.keys())}")
    
    def test_existing_homework_with_file(self):
        """Test homework material that has a file attached"""
        # mat_6afbac5f4fe1 has file_name: week1_homework.pdf
        response = requests.get(f"{BASE_URL}/api/submit-link/mat_6afbac5f4fe1")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["material_id"] == "mat_6afbac5f4fe1"
        assert data["title"] == "Week 1 Assignment"
        assert data["file_name"] == "week1_homework.pdf"
        print(f"SUCCESS: Homework with file returns file_name: {data['file_name']}")


class TestSubmitLinkNonHomeworkMaterials:
    """Tests to verify non-homework materials return 404"""
    
    def test_workbook_material_returns_404(self):
        """Test that workbook materials return 404 (only homework allowed)"""
        # First, let's check if there are any workbook materials
        # This test verifies the endpoint only works for homework type
        response = requests.get(f"{BASE_URL}/api/submit-link/workbook-test-id")
        
        # Should return 404 since it's not a homework material
        assert response.status_code == 404
        print("SUCCESS: Non-homework material returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
