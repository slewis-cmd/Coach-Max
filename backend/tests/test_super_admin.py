"""
Test Suite for Super Admin Features - ThinkificAI
Tests:
- Admin endpoints (GET /api/admin/users, POST /api/admin/invite-instructor, POST /api/admin/revoke-instructor, GET /api/admin/stats)
- Role-based access control (super_admin, instructor, student)
- Auto-promotion of SUPER_ADMIN_EMAIL
- Cohort management permissions for super_admin
- Submissions access for super_admin
"""

import pytest
import requests
import os
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
import uuid

# Configuration
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
SUPER_ADMIN_EMAIL = "slewis@theboostpad.org"

# MongoDB connection
mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

# Test data prefixes for cleanup
TEST_PREFIX = "TEST_SUPERADMIN_"

@pytest.fixture(scope="module")
def setup_test_data():
    """Create test users and sessions for testing"""
    timestamp = int(datetime.now().timestamp())
    
    # Create super_admin user
    super_admin_user_id = f"{TEST_PREFIX}super_admin_{timestamp}"
    super_admin_session = f"{TEST_PREFIX}session_super_{timestamp}"
    
    # Create instructor user
    instructor_user_id = f"{TEST_PREFIX}instructor_{timestamp}"
    instructor_session = f"{TEST_PREFIX}session_instructor_{timestamp}"
    
    # Create student user
    student_user_id = f"{TEST_PREFIX}student_{timestamp}"
    student_session = f"{TEST_PREFIX}session_student_{timestamp}"
    
    # Create another student to test promotion
    promotable_student_id = f"{TEST_PREFIX}promotable_{timestamp}"
    promotable_email = f"test_promotable_{timestamp}@example.com"
    
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    
    # Insert users
    db.users.insert_one({
        "user_id": super_admin_user_id,
        "email": f"test_super_admin_{timestamp}@example.com",
        "name": "Test Super Admin",
        "picture": None,
        "role": "super_admin",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    db.users.insert_one({
        "user_id": instructor_user_id,
        "email": f"test_instructor_{timestamp}@example.com",
        "name": "Test Instructor",
        "picture": None,
        "role": "instructor",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    db.users.insert_one({
        "user_id": student_user_id,
        "email": f"test_student_{timestamp}@example.com",
        "name": "Test Student",
        "picture": None,
        "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    db.users.insert_one({
        "user_id": promotable_student_id,
        "email": promotable_email,
        "name": "Promotable Student",
        "picture": None,
        "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Insert sessions
    db.user_sessions.insert_one({
        "user_id": super_admin_user_id,
        "session_token": super_admin_session,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    db.user_sessions.insert_one({
        "user_id": instructor_user_id,
        "session_token": instructor_session,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    db.user_sessions.insert_one({
        "user_id": student_user_id,
        "session_token": student_session,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    test_data = {
        "super_admin": {
            "user_id": super_admin_user_id,
            "session": super_admin_session
        },
        "instructor": {
            "user_id": instructor_user_id,
            "session": instructor_session
        },
        "student": {
            "user_id": student_user_id,
            "session": student_session
        },
        "promotable": {
            "user_id": promotable_student_id,
            "email": promotable_email
        }
    }
    
    yield test_data
    
    # Cleanup
    db.users.delete_many({"user_id": {"$regex": f"^{TEST_PREFIX}"}})
    db.user_sessions.delete_many({"session_token": {"$regex": f"^{TEST_PREFIX}"}})
    db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TEST_PREFIX}"}})


class TestAdminEndpoints:
    """Test admin-only endpoints require super_admin role"""
    
    def test_get_admin_users_as_super_admin(self, setup_test_data):
        """GET /api/admin/users - should return all users for super_admin"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list of users"
        print(f"✅ GET /api/admin/users returned {len(data)} users")
    
    def test_get_admin_users_as_instructor_denied(self, setup_test_data):
        """GET /api/admin/users - should return 403 for instructor"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {setup_test_data['instructor']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ GET /api/admin/users correctly denied for instructor")
    
    def test_get_admin_users_as_student_denied(self, setup_test_data):
        """GET /api/admin/users - should return 403 for student"""
        response = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {setup_test_data['student']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ GET /api/admin/users correctly denied for student")
    
    def test_get_admin_stats_as_super_admin(self, setup_test_data):
        """GET /api/admin/stats - should return platform stats for super_admin"""
        response = requests.get(
            f"{BASE_URL}/api/admin/stats",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "users" in data, "Response should have 'users' key"
        assert "total" in data["users"], "Users should have 'total' count"
        assert "super_admins" in data["users"], "Users should have 'super_admins' count"
        assert "instructors" in data["users"], "Users should have 'instructors' count"
        assert "students" in data["users"], "Users should have 'students' count"
        assert "cohorts" in data, "Response should have 'cohorts' count"
        assert "submissions" in data, "Response should have 'submissions' count"
        print(f"✅ GET /api/admin/stats: {data['users']['total']} users, {data['cohorts']} cohorts")
    
    def test_get_admin_stats_as_instructor_denied(self, setup_test_data):
        """GET /api/admin/stats - should return 403 for instructor"""
        response = requests.get(
            f"{BASE_URL}/api/admin/stats",
            headers={"Authorization": f"Bearer {setup_test_data['instructor']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ GET /api/admin/stats correctly denied for instructor")


class TestInviteInstructor:
    """Test invite/promote instructor functionality"""
    
    def test_invite_instructor_as_super_admin(self, setup_test_data):
        """POST /api/admin/invite-instructor - super_admin can promote student to instructor"""
        response = requests.post(
            f"{BASE_URL}/api/admin/invite-instructor",
            json={"email": setup_test_data['promotable']['email']},
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        assert "instructor" in data["message"].lower() or "promoted" in data["message"].lower(), \
            f"Message should mention instructor/promoted: {data['message']}"
        
        # Verify user role changed in DB
        user = db.users.find_one({"user_id": setup_test_data['promotable']['user_id']})
        assert user["role"] == "instructor", "User role should be instructor now"
        print(f"✅ POST /api/admin/invite-instructor: {data['message']}")
    
    def test_invite_instructor_as_instructor_denied(self, setup_test_data):
        """POST /api/admin/invite-instructor - should return 403 for instructor"""
        response = requests.post(
            f"{BASE_URL}/api/admin/invite-instructor",
            json={"email": "anyemail@example.com"},
            headers={"Authorization": f"Bearer {setup_test_data['instructor']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ POST /api/admin/invite-instructor correctly denied for instructor")
    
    def test_invite_instructor_nonexistent_user(self, setup_test_data):
        """POST /api/admin/invite-instructor - should return 404 for non-existent user"""
        response = requests.post(
            f"{BASE_URL}/api/admin/invite-instructor",
            json={"email": "nonexistent_user_12345@example.com"},
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
        print("✅ POST /api/admin/invite-instructor returns 404 for non-existent user")


class TestRevokeInstructor:
    """Test revoke instructor functionality"""
    
    def test_revoke_instructor_as_super_admin(self, setup_test_data):
        """POST /api/admin/revoke-instructor - super_admin can demote instructor to student"""
        # First ensure the promotable user is an instructor
        db.users.update_one(
            {"user_id": setup_test_data['promotable']['user_id']},
            {"$set": {"role": "instructor"}}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/admin/revoke-instructor",
            json={"user_id": setup_test_data['promotable']['user_id']},
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        
        # Verify user role changed in DB
        user = db.users.find_one({"user_id": setup_test_data['promotable']['user_id']})
        assert user["role"] == "student", "User role should be student now"
        print(f"✅ POST /api/admin/revoke-instructor: {data['message']}")
    
    def test_revoke_instructor_as_instructor_denied(self, setup_test_data):
        """POST /api/admin/revoke-instructor - should return 403 for instructor"""
        response = requests.post(
            f"{BASE_URL}/api/admin/revoke-instructor",
            json={"user_id": "any_user_id"},
            headers={"Authorization": f"Bearer {setup_test_data['instructor']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ POST /api/admin/revoke-instructor correctly denied for instructor")


class TestSetRole:
    """Test role setting with permission checks"""
    
    def test_student_can_set_own_role_to_student(self, setup_test_data):
        """POST /api/auth/set-role - student can set their own role to student"""
        response = requests.post(
            f"{BASE_URL}/api/auth/set-role",
            json={"role": "student"},
            headers={"Authorization": f"Bearer {setup_test_data['student']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✅ POST /api/auth/set-role: student can set own role to student")
    
    def test_student_cannot_set_own_role_to_instructor(self, setup_test_data):
        """POST /api/auth/set-role - student cannot set their own role to instructor"""
        response = requests.post(
            f"{BASE_URL}/api/auth/set-role",
            json={"role": "instructor"},
            headers={"Authorization": f"Bearer {setup_test_data['student']['session']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✅ POST /api/auth/set-role: student cannot promote self to instructor")
    
    def test_super_admin_can_set_other_user_to_instructor(self, setup_test_data):
        """POST /api/auth/set-role - super_admin can promote another user to instructor"""
        # Reset promotable user to student
        db.users.update_one(
            {"user_id": setup_test_data['promotable']['user_id']},
            {"$set": {"role": "student"}}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/auth/set-role",
            json={"role": "instructor", "user_id": setup_test_data['promotable']['user_id']},
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify role changed
        user = db.users.find_one({"user_id": setup_test_data['promotable']['user_id']})
        assert user["role"] == "instructor", "User should be instructor now"
        print("✅ POST /api/auth/set-role: super_admin can promote user to instructor")


class TestSuperAdminCohortAccess:
    """Test super_admin can access and manage all cohorts"""
    
    def test_super_admin_sees_all_cohorts(self, setup_test_data):
        """GET /api/cohorts - super_admin should see all cohorts"""
        timestamp = int(datetime.now().timestamp())
        
        # Create a cohort owned by instructor
        cohort_id = f"{TEST_PREFIX}cohort_{timestamp}"
        db.cohorts.insert_one({
            "cohort_id": cohort_id,
            "name": f"Test Cohort {timestamp}",
            "description": "Test cohort for super admin access",
            "instructor_id": setup_test_data['instructor']['user_id'],
            "student_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Super admin gets cohorts
        response = requests.get(
            f"{BASE_URL}/api/cohorts",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        cohort_ids = [c['cohort_id'] for c in data]
        assert cohort_id in cohort_ids, "Super admin should see the instructor's cohort"
        print(f"✅ GET /api/cohorts: super_admin sees {len(data)} cohorts including others' cohorts")
        
        # Cleanup
        db.cohorts.delete_one({"cohort_id": cohort_id})
    
    def test_super_admin_can_access_cohort_detail(self, setup_test_data):
        """GET /api/cohorts/{id} - super_admin can access any cohort"""
        timestamp = int(datetime.now().timestamp())
        
        # Create a cohort owned by instructor
        cohort_id = f"{TEST_PREFIX}cohort_detail_{timestamp}"
        db.cohorts.insert_one({
            "cohort_id": cohort_id,
            "name": f"Test Cohort Detail {timestamp}",
            "description": "Test cohort detail access",
            "instructor_id": setup_test_data['instructor']['user_id'],
            "student_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Super admin accesses cohort detail
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{cohort_id}",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data['cohort_id'] == cohort_id, "Should return the correct cohort"
        print(f"✅ GET /api/cohorts/{cohort_id}: super_admin can access any cohort")
        
        # Cleanup
        db.cohorts.delete_one({"cohort_id": cohort_id})
    
    def test_super_admin_can_update_cohort(self, setup_test_data):
        """PUT /api/cohorts/{id} - super_admin can update any cohort"""
        timestamp = int(datetime.now().timestamp())
        
        # Create a cohort owned by instructor
        cohort_id = f"{TEST_PREFIX}cohort_update_{timestamp}"
        db.cohorts.insert_one({
            "cohort_id": cohort_id,
            "name": f"Test Cohort Update {timestamp}",
            "description": "Original description",
            "instructor_id": setup_test_data['instructor']['user_id'],
            "student_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Super admin updates cohort
        response = requests.put(
            f"{BASE_URL}/api/cohorts/{cohort_id}",
            json={"description": "Updated by super admin"},
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        cohort = db.cohorts.find_one({"cohort_id": cohort_id})
        assert cohort['description'] == "Updated by super admin", "Description should be updated"
        print(f"✅ PUT /api/cohorts/{cohort_id}: super_admin can update any cohort")
        
        # Cleanup
        db.cohorts.delete_one({"cohort_id": cohort_id})
    
    def test_super_admin_can_delete_cohort(self, setup_test_data):
        """DELETE /api/cohorts/{id} - super_admin can delete any cohort"""
        timestamp = int(datetime.now().timestamp())
        
        # Create a cohort owned by instructor
        cohort_id = f"{TEST_PREFIX}cohort_delete_{timestamp}"
        db.cohorts.insert_one({
            "cohort_id": cohort_id,
            "name": f"Test Cohort Delete {timestamp}",
            "description": "To be deleted",
            "instructor_id": setup_test_data['instructor']['user_id'],
            "student_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        # Super admin deletes cohort
        response = requests.delete(
            f"{BASE_URL}/api/cohorts/{cohort_id}",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify deletion
        cohort = db.cohorts.find_one({"cohort_id": cohort_id})
        assert cohort is None, "Cohort should be deleted"
        print(f"✅ DELETE /api/cohorts/{cohort_id}: super_admin can delete any cohort")


class TestSuperAdminSubmissionsAccess:
    """Test super_admin can see all submissions"""
    
    def test_super_admin_sees_all_submissions(self, setup_test_data):
        """GET /api/submissions - super_admin should see all submissions"""
        response = requests.get(
            f"{BASE_URL}/api/submissions",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"✅ GET /api/submissions: super_admin sees {len(data)} submissions")


class TestSuperAdminDashboardAnalytics:
    """Test super_admin gets analytics for all cohorts"""
    
    def test_super_admin_dashboard_analytics(self, setup_test_data):
        """GET /api/analytics/dashboard - super_admin gets analytics for all cohorts"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "cohorts" in data, "Response should have 'cohorts' count"
        assert "total_students" in data, "Response should have 'total_students'"
        assert "submissions" in data, "Response should have 'submissions'"
        print(f"✅ GET /api/analytics/dashboard: super_admin sees {data['cohorts']} cohorts, {data['total_students']} students")


class TestRequireInstructorAllowsSuperAdmin:
    """Test that require_instructor decorator allows super_admin"""
    
    def test_super_admin_can_create_cohort(self, setup_test_data):
        """POST /api/cohorts - super_admin should be able to create cohorts (requires instructor)"""
        timestamp = int(datetime.now().timestamp())
        
        response = requests.post(
            f"{BASE_URL}/api/cohorts",
            json={
                "name": f"Super Admin Cohort {timestamp}",
                "description": "Created by super admin"
            },
            headers={"Authorization": f"Bearer {setup_test_data['super_admin']['session']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "cohort_id" in data, "Response should have cohort_id"
        print(f"✅ POST /api/cohorts: super_admin can create cohorts (cohort_id: {data['cohort_id']})")
        
        # Cleanup
        db.cohorts.delete_one({"cohort_id": data['cohort_id']})


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
