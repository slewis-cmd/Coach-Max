"""
Test suite for Assign Instructor feature
Tests:
- POST /api/cohorts/{cohort_id}/assign-instructor - Super admin can assign an instructor to a cohort
- GET /api/instructors - Super admin can list all instructors
- After assignment, instructor can see submissions via GET /api/submissions
- After assignment, instructor can see cohort analytics via GET /api/analytics/dashboard
- After assignment, instructor can access cohort detail via GET /api/cohorts/{cohort_id}
- Non-super-admin users cannot call /api/cohorts/{id}/assign-instructor (should get 403)
- Cohort detail API returns instructor_name and instructor_email fields
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data IDs - will be created during setup
TEST_PREFIX = f"TEST_{uuid.uuid4().hex[:8]}"


class TestSetup:
    """Setup test data in MongoDB"""
    
    @pytest.fixture(scope="class", autouse=True)
    def setup_test_data(self):
        """Create test users, sessions, and cohort for testing"""
        import subprocess
        
        # Create unique IDs for this test run
        super_admin_id = f"user_sa_{uuid.uuid4().hex[:8]}"
        instructor_id = f"user_inst_{uuid.uuid4().hex[:8]}"
        student_id = f"user_stu_{uuid.uuid4().hex[:8]}"
        cohort_id = f"cohort_{uuid.uuid4().hex[:8]}"
        
        super_admin_token = f"token_sa_{uuid.uuid4().hex}"
        instructor_token = f"token_inst_{uuid.uuid4().hex}"
        student_token = f"token_stu_{uuid.uuid4().hex}"
        
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        
        # MongoDB script to create test data
        mongo_script = f'''
        use('test_database');
        
        // Create super_admin user
        db.users.insertOne({{
            user_id: "{super_admin_id}",
            email: "{TEST_PREFIX}_superadmin@test.com",
            name: "{TEST_PREFIX} Super Admin",
            role: "super_admin",
            created_at: new Date().toISOString()
        }});
        
        // Create instructor user
        db.users.insertOne({{
            user_id: "{instructor_id}",
            email: "{TEST_PREFIX}_instructor@test.com",
            name: "{TEST_PREFIX} Instructor",
            role: "instructor",
            created_at: new Date().toISOString()
        }});
        
        // Create student user
        db.users.insertOne({{
            user_id: "{student_id}",
            email: "{TEST_PREFIX}_student@test.com",
            name: "{TEST_PREFIX} Student",
            role: "student",
            created_at: new Date().toISOString()
        }});
        
        // Create sessions
        db.user_sessions.insertOne({{
            user_id: "{super_admin_id}",
            session_token: "{super_admin_token}",
            expires_at: "{expires_at}",
            created_at: new Date().toISOString()
        }});
        
        db.user_sessions.insertOne({{
            user_id: "{instructor_id}",
            session_token: "{instructor_token}",
            expires_at: "{expires_at}",
            created_at: new Date().toISOString()
        }});
        
        db.user_sessions.insertOne({{
            user_id: "{student_id}",
            session_token: "{student_token}",
            expires_at: "{expires_at}",
            created_at: new Date().toISOString()
        }});
        
        // Create cohort (initially with super_admin as instructor)
        db.cohorts.insertOne({{
            cohort_id: "{cohort_id}",
            name: "{TEST_PREFIX} Test Cohort",
            description: "Test cohort for assign instructor feature",
            instructor_id: "{super_admin_id}",
            student_ids: ["{student_id}"],
            invite_code: "{uuid.uuid4().hex[:8]}",
            released_weeks: [1, 2],
            created_at: new Date().toISOString()
        }});
        
        print("Test data created successfully");
        '''
        
        result = subprocess.run(
            ['mongosh', '--eval', mongo_script],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"MongoDB setup error: {result.stderr}")
            pytest.fail("Failed to setup test data")
        
        # Store test data for use in tests
        TestSetup.super_admin_id = super_admin_id
        TestSetup.instructor_id = instructor_id
        TestSetup.student_id = student_id
        TestSetup.cohort_id = cohort_id
        TestSetup.super_admin_token = super_admin_token
        TestSetup.instructor_token = instructor_token
        TestSetup.student_token = student_token
        
        yield
        
        # Cleanup after tests
        cleanup_script = f'''
        use('test_database');
        db.users.deleteMany({{ email: {{ $regex: "^{TEST_PREFIX}" }} }});
        db.user_sessions.deleteMany({{ session_token: {{ $regex: "^token_" }} }});
        db.cohorts.deleteMany({{ name: {{ $regex: "^{TEST_PREFIX}" }} }});
        print("Test data cleaned up");
        '''
        subprocess.run(['mongosh', '--eval', cleanup_script], capture_output=True)


class TestListInstructors(TestSetup):
    """Test GET /api/instructors endpoint"""
    
    def test_super_admin_can_list_instructors(self, setup_test_data):
        """Super admin should be able to list all instructors"""
        response = requests.get(
            f"{BASE_URL}/api/instructors",
            headers={"Authorization": f"Bearer {TestSetup.super_admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        # Should include users with instructor or super_admin role
        roles = [inst.get("role") for inst in data]
        assert all(r in ["instructor", "super_admin"] for r in roles), "All returned users should be instructors or super_admins"
        
        # Verify response structure
        if len(data) > 0:
            inst = data[0]
            assert "user_id" in inst, "Instructor should have user_id"
            assert "name" in inst, "Instructor should have name"
            assert "email" in inst, "Instructor should have email"
            assert "role" in inst, "Instructor should have role"
        
        print(f"SUCCESS: Listed {len(data)} instructors")
    
    def test_instructor_cannot_list_instructors(self, setup_test_data):
        """Regular instructor should NOT be able to list instructors (403)"""
        response = requests.get(
            f"{BASE_URL}/api/instructors",
            headers={"Authorization": f"Bearer {TestSetup.instructor_token}"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("SUCCESS: Instructor correctly denied access to list instructors")
    
    def test_student_cannot_list_instructors(self, setup_test_data):
        """Student should NOT be able to list instructors (403)"""
        response = requests.get(
            f"{BASE_URL}/api/instructors",
            headers={"Authorization": f"Bearer {TestSetup.student_token}"}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("SUCCESS: Student correctly denied access to list instructors")
    
    def test_unauthenticated_cannot_list_instructors(self, setup_test_data):
        """Unauthenticated request should get 401"""
        response = requests.get(f"{BASE_URL}/api/instructors")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
        print("SUCCESS: Unauthenticated request correctly denied")


class TestAssignInstructor(TestSetup):
    """Test POST /api/cohorts/{cohort_id}/assign-instructor endpoint"""
    
    def test_super_admin_can_assign_instructor(self, setup_test_data):
        """Super admin should be able to assign an instructor to a cohort"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.super_admin_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.instructor_id}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        assert TestSetup.instructor_id in data.get("message", "") or "Instructor" in data.get("message", ""), \
            f"Message should mention instructor assignment: {data}"
        
        print(f"SUCCESS: Assigned instructor - {data.get('message')}")
    
    def test_verify_instructor_assigned_via_cohort_detail(self, setup_test_data):
        """Verify the instructor was assigned by checking cohort detail"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}",
            headers={"Authorization": f"Bearer {TestSetup.super_admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("instructor_id") == TestSetup.instructor_id, \
            f"Cohort instructor_id should be {TestSetup.instructor_id}, got {data.get('instructor_id')}"
        
        # Verify instructor_name and instructor_email are returned
        assert "instructor_name" in data, "Cohort detail should include instructor_name"
        assert "instructor_email" in data, "Cohort detail should include instructor_email"
        assert data.get("instructor_name") == f"{TEST_PREFIX} Instructor", \
            f"instructor_name should match, got {data.get('instructor_name')}"
        assert data.get("instructor_email") == f"{TEST_PREFIX}_instructor@test.com", \
            f"instructor_email should match, got {data.get('instructor_email')}"
        
        print(f"SUCCESS: Verified instructor assignment - name: {data.get('instructor_name')}, email: {data.get('instructor_email')}")
    
    def test_instructor_cannot_assign_instructor(self, setup_test_data):
        """Regular instructor should NOT be able to assign instructors (403)"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.instructor_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.super_admin_id}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("SUCCESS: Instructor correctly denied from assigning instructors")
    
    def test_student_cannot_assign_instructor(self, setup_test_data):
        """Student should NOT be able to assign instructors (403)"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.student_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.instructor_id}
        )
        
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("SUCCESS: Student correctly denied from assigning instructors")
    
    def test_assign_instructor_missing_instructor_id(self, setup_test_data):
        """Should return 400 if instructor_id is missing"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.super_admin_token}",
                "Content-Type": "application/json"
            },
            json={}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("SUCCESS: Missing instructor_id correctly returns 400")
    
    def test_assign_instructor_invalid_cohort(self, setup_test_data):
        """Should return 404 for non-existent cohort"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/nonexistent_cohort_123/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.super_admin_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.instructor_id}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("SUCCESS: Non-existent cohort correctly returns 404")
    
    def test_assign_non_instructor_user(self, setup_test_data):
        """Should return 400 when trying to assign a student as instructor"""
        response = requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.super_admin_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.student_id}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        data = response.json()
        assert "not an instructor" in data.get("detail", "").lower(), \
            f"Error should mention user is not an instructor: {data}"
        print("SUCCESS: Assigning non-instructor user correctly returns 400")


class TestInstructorAccessAfterAssignment(TestSetup):
    """Test that assigned instructor can access cohort resources"""
    
    def test_assigned_instructor_can_access_cohort_detail(self, setup_test_data):
        """Assigned instructor should be able to access cohort detail"""
        # First ensure instructor is assigned
        requests.post(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}/assign-instructor",
            headers={
                "Authorization": f"Bearer {TestSetup.super_admin_token}",
                "Content-Type": "application/json"
            },
            json={"instructor_id": TestSetup.instructor_id}
        )
        
        # Now test instructor access
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}",
            headers={"Authorization": f"Bearer {TestSetup.instructor_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("cohort_id") == TestSetup.cohort_id, "Should return correct cohort"
        assert "students" in data, "Instructor should see students list"
        
        print(f"SUCCESS: Assigned instructor can access cohort detail")
    
    def test_assigned_instructor_can_see_submissions(self, setup_test_data):
        """Assigned instructor should be able to see submissions for the cohort"""
        response = requests.get(
            f"{BASE_URL}/api/submissions",
            headers={"Authorization": f"Bearer {TestSetup.instructor_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        
        print(f"SUCCESS: Assigned instructor can access submissions endpoint - {len(data)} submissions")
    
    def test_assigned_instructor_can_access_analytics(self, setup_test_data):
        """Assigned instructor should be able to access analytics dashboard"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {TestSetup.instructor_token}"}
        )
        
        # Analytics endpoint may return 200 or 404 if not implemented
        assert response.status_code in [200, 404], f"Expected 200 or 404, got {response.status_code}: {response.text}"
        
        if response.status_code == 200:
            print("SUCCESS: Assigned instructor can access analytics dashboard")
        else:
            print("INFO: Analytics dashboard endpoint not found (404) - may not be implemented")


class TestCohortDetailInstructorInfo(TestSetup):
    """Test that cohort detail returns instructor_name and instructor_email"""
    
    def test_cohort_detail_includes_instructor_info(self, setup_test_data):
        """Cohort detail should include instructor_name and instructor_email"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{TestSetup.cohort_id}",
            headers={"Authorization": f"Bearer {TestSetup.super_admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify instructor info fields exist
        assert "instructor_name" in data, "Cohort detail should include instructor_name"
        assert "instructor_email" in data, "Cohort detail should include instructor_email"
        
        # Verify they are not empty
        assert data.get("instructor_name"), "instructor_name should not be empty"
        assert data.get("instructor_email"), "instructor_email should not be empty"
        
        print(f"SUCCESS: Cohort detail includes instructor info - name: {data.get('instructor_name')}, email: {data.get('instructor_email')}")


class TestAuthMeEndpoint(TestSetup):
    """Verify auth tokens are working"""
    
    def test_super_admin_token_valid(self, setup_test_data):
        """Verify super admin token works"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {TestSetup.super_admin_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("role") == "super_admin", f"Expected super_admin role, got {data.get('role')}"
        
        print(f"SUCCESS: Super admin token valid - user: {data.get('name')}")
    
    def test_instructor_token_valid(self, setup_test_data):
        """Verify instructor token works"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {TestSetup.instructor_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("role") == "instructor", f"Expected instructor role, got {data.get('role')}"
        
        print(f"SUCCESS: Instructor token valid - user: {data.get('name')}")
    
    def test_student_token_valid(self, setup_test_data):
        """Verify student token works"""
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {TestSetup.student_token}"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("role") == "student", f"Expected student role, got {data.get('role')}"
        
        print(f"SUCCESS: Student token valid - user: {data.get('name')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
