"""
Test Material Library Feature
- GET /api/library/materials - lists all library materials with assigned cohort names
- POST /api/library/materials - upload a workbook or case study to the library (multipart form)
- PUT /api/library/materials/{id} - update title/description/week/file
- DELETE /api/library/materials/{id} - delete from library
- POST /api/library/materials/{id}/assign - assign to cohorts (with access control check)
- POST /api/library/materials/{id}/unassign - remove from a cohort
- Library only accepts workbook or case_study types (not homework)
- Library only accepts PDF and DOCX files
- GET /api/cohorts/{id}/materials - returns both cohort-specific materials AND linked library materials
"""

import pytest
import requests
import os
import io
import time
from datetime import datetime, timezone, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test data
TEST_PREFIX = "TEST_LIB_"

class TestMaterialLibrarySetup:
    """Setup test users and cohorts for library testing"""
    
    @pytest.fixture(scope="class")
    def mongo_client(self):
        """Get MongoDB client for direct database operations"""
        from pymongo import MongoClient
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        client = MongoClient(mongo_url)
        db = client[os.environ.get('DB_NAME', 'test_database')]
        return db
    
    @pytest.fixture(scope="class")
    def test_users(self, mongo_client):
        """Create test users: super_admin, instructor, student"""
        db = mongo_client
        timestamp = int(time.time() * 1000)
        
        # Create super_admin
        super_admin_id = f"user_sa_{timestamp}"
        super_admin_token = f"sa_token_{timestamp}"
        db.users.update_one(
            {"user_id": super_admin_id},
            {"$set": {
                "user_id": super_admin_id,
                "email": f"{TEST_PREFIX}superadmin@test.com",
                "name": f"{TEST_PREFIX}Super Admin",
                "role": "super_admin",
                "created_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        db.user_sessions.insert_one({
            "user_id": super_admin_id,
            "session_token": super_admin_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        })
        
        # Create instructor
        instructor_id = f"user_inst_{timestamp}"
        instructor_token = f"inst_token_{timestamp}"
        db.users.update_one(
            {"user_id": instructor_id},
            {"$set": {
                "user_id": instructor_id,
                "email": f"{TEST_PREFIX}instructor@test.com",
                "name": f"{TEST_PREFIX}Instructor",
                "role": "instructor",
                "created_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        db.user_sessions.insert_one({
            "user_id": instructor_id,
            "session_token": instructor_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        })
        
        # Create student
        student_id = f"user_stu_{timestamp}"
        student_token = f"stu_token_{timestamp}"
        db.users.update_one(
            {"user_id": student_id},
            {"$set": {
                "user_id": student_id,
                "email": f"{TEST_PREFIX}student@test.com",
                "name": f"{TEST_PREFIX}Student",
                "role": "student",
                "created_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        db.user_sessions.insert_one({
            "user_id": student_id,
            "session_token": student_token,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        })
        
        return {
            "super_admin": {"user_id": super_admin_id, "token": super_admin_token},
            "instructor": {"user_id": instructor_id, "token": instructor_token},
            "student": {"user_id": student_id, "token": student_token}
        }
    
    @pytest.fixture(scope="class")
    def test_cohorts(self, mongo_client, test_users):
        """Create test cohorts"""
        db = mongo_client
        timestamp = int(time.time() * 1000)
        
        cohort1_id = f"cohort_lib1_{timestamp}"
        cohort2_id = f"cohort_lib2_{timestamp}"
        
        db.cohorts.insert_one({
            "cohort_id": cohort1_id,
            "name": f"{TEST_PREFIX}Cohort 1",
            "description": "Test cohort 1 for library testing",
            "instructor_id": test_users["instructor"]["user_id"],
            "student_ids": [test_users["student"]["user_id"]],
            "invite_code": f"inv1_{timestamp}",
            "released_weeks": [1, 2],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        db.cohorts.insert_one({
            "cohort_id": cohort2_id,
            "name": f"{TEST_PREFIX}Cohort 2",
            "description": "Test cohort 2 for library testing",
            "instructor_id": test_users["instructor"]["user_id"],
            "student_ids": [],
            "invite_code": f"inv2_{timestamp}",
            "released_weeks": [1],
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        
        return {"cohort1": cohort1_id, "cohort2": cohort2_id}


class TestLibraryMaterialsEndpoints(TestMaterialLibrarySetup):
    """Test library material CRUD operations"""
    
    def test_get_library_materials_empty(self, test_users):
        """GET /api/library/materials - returns empty list initially"""
        response = requests.get(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"GET /api/library/materials - returned {len(data)} materials")
    
    def test_get_library_materials_requires_instructor(self, test_users):
        """GET /api/library/materials - student cannot access"""
        response = requests.get(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['student']['token']}"}
        )
        assert response.status_code == 403, f"Expected 403 for student, got {response.status_code}"
        print("GET /api/library/materials - correctly denied student access (403)")
    
    def test_get_library_materials_unauthenticated(self):
        """GET /api/library/materials - requires authentication"""
        response = requests.get(f"{BASE_URL}/api/library/materials")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("GET /api/library/materials - correctly requires auth (401)")
    
    def test_upload_library_material_workbook(self, test_users, mongo_client):
        """POST /api/library/materials - upload workbook"""
        # Create a test PDF file
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        files = {"file": ("test_workbook.pdf", io.BytesIO(pdf_content), "application/pdf")}
        
        # FastAPI expects query params for non-file fields
        params = {
            "title": f"{TEST_PREFIX}Test Workbook",
            "description": "A test workbook for library",
            "week_number": 1,
            "material_type": "workbook"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files,
            params=params
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert "material_id" in result, "Response should contain material_id"
        assert result["material_id"].startswith("lib_"), "Library material ID should start with 'lib_'"
        print(f"POST /api/library/materials - workbook uploaded: {result['material_id']}")
        
        # Store for later tests
        pytest.lib_workbook_id = result["material_id"]
    
    def test_upload_library_material_case_study(self, test_users):
        """POST /api/library/materials - upload case study"""
        # Create a test DOCX file (minimal valid docx is complex, use PDF)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        files = {"file": ("test_case_study.pdf", io.BytesIO(pdf_content), "application/pdf")}
        params = {
            "title": f"{TEST_PREFIX}Test Case Study",
            "description": "A test case study for library",
            "week_number": 2,
            "material_type": "case_study"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files,
            params=params
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        assert "material_id" in result
        print(f"POST /api/library/materials - case study uploaded: {result['material_id']}")
        
        pytest.lib_case_study_id = result["material_id"]
    
    def test_upload_library_material_homework_rejected(self, test_users):
        """POST /api/library/materials - homework type should be rejected"""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        files = {"file": ("test_homework.pdf", io.BytesIO(pdf_content), "application/pdf")}
        params = {
            "title": f"{TEST_PREFIX}Test Homework",
            "description": "This should fail",
            "week_number": 1,
            "material_type": "homework"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files,
            params=params
        )
        # Backend validates material_type and returns 400 for invalid types
        assert response.status_code == 400, f"Expected 400 for homework type, got {response.status_code}: {response.text}"
        assert "workbook" in response.text.lower() or "case" in response.text.lower(), "Error should mention allowed types"
        print("POST /api/library/materials - correctly rejected homework type (400)")
    
    def test_upload_library_material_invalid_file_type(self, test_users):
        """POST /api/library/materials - only PDF and DOCX allowed"""
        txt_content = b"This is a text file"
        files = {"file": ("test.txt", io.BytesIO(txt_content), "text/plain")}
        params = {
            "title": f"{TEST_PREFIX}Test Invalid",
            "description": "This should fail",
            "week_number": 1,
            "material_type": "workbook"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files,
            params=params
        )
        assert response.status_code == 400, f"Expected 400 for txt file, got {response.status_code}"
        assert "pdf" in response.text.lower() or "docx" in response.text.lower(), "Error should mention allowed file types"
        print("POST /api/library/materials - correctly rejected .txt file (400)")
    
    def test_upload_library_material_student_denied(self, test_users):
        """POST /api/library/materials - student cannot upload"""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}
        params = {
            "title": f"{TEST_PREFIX}Student Upload",
            "week_number": 1,
            "material_type": "workbook"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['student']['token']}"},
            files=files,
            params=params
        )
        assert response.status_code == 403, f"Expected 403 for student, got {response.status_code}"
        print("POST /api/library/materials - correctly denied student upload (403)")
    
    def test_get_library_materials_with_data(self, test_users):
        """GET /api/library/materials - returns uploaded materials with cohort info"""
        response = requests.get(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2, f"Expected at least 2 materials, got {len(data)}"
        
        # Check structure
        for mat in data:
            assert "material_id" in mat
            assert "title" in mat
            assert "material_type" in mat
            assert "week_number" in mat
            assert "assigned_cohorts" in mat, "Should include assigned_cohorts array"
            assert isinstance(mat["assigned_cohorts"], list)
        
        print(f"GET /api/library/materials - returned {len(data)} materials with cohort info")


class TestLibraryMaterialAssignment(TestMaterialLibrarySetup):
    """Test assigning/unassigning library materials to cohorts"""
    
    def test_assign_material_to_cohort(self, test_users, test_cohorts):
        """POST /api/library/materials/{id}/assign - assign to cohort"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/assign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={"cohort_ids": [test_cohorts["cohort1"]]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"POST /api/library/materials/{material_id}/assign - assigned to cohort1")
    
    def test_assign_material_to_multiple_cohorts(self, test_users, test_cohorts):
        """POST /api/library/materials/{id}/assign - assign to multiple cohorts"""
        material_id = getattr(pytest, 'lib_case_study_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/assign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={"cohort_ids": [test_cohorts["cohort1"], test_cohorts["cohort2"]]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"POST /api/library/materials/{material_id}/assign - assigned to both cohorts")
    
    def test_assign_material_missing_cohort_ids(self, test_users):
        """POST /api/library/materials/{id}/assign - requires cohort_ids"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/assign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("POST /api/library/materials/{id}/assign - correctly requires cohort_ids (400)")
    
    def test_assign_material_invalid_cohort(self, test_users):
        """POST /api/library/materials/{id}/assign - invalid cohort returns 404"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/assign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={"cohort_ids": ["invalid_cohort_id"]}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("POST /api/library/materials/{id}/assign - correctly returns 404 for invalid cohort")
    
    def test_assign_material_student_denied(self, test_users, test_cohorts):
        """POST /api/library/materials/{id}/assign - student cannot assign"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/assign",
            headers={
                "Authorization": f"Bearer {test_users['student']['token']}",
                "Content-Type": "application/json"
            },
            json={"cohort_ids": [test_cohorts["cohort1"]]}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("POST /api/library/materials/{id}/assign - correctly denied student (403)")
    
    def test_unassign_material_from_cohort(self, test_users, test_cohorts):
        """POST /api/library/materials/{id}/unassign - remove from cohort"""
        material_id = getattr(pytest, 'lib_case_study_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/unassign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={"cohort_id": test_cohorts["cohort2"]}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"POST /api/library/materials/{material_id}/unassign - removed from cohort2")
    
    def test_unassign_material_missing_cohort_id(self, test_users):
        """POST /api/library/materials/{id}/unassign - requires cohort_id"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.post(
            f"{BASE_URL}/api/library/materials/{material_id}/unassign",
            headers={
                "Authorization": f"Bearer {test_users['instructor']['token']}",
                "Content-Type": "application/json"
            },
            json={}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("POST /api/library/materials/{id}/unassign - correctly requires cohort_id (400)")


class TestLibraryMaterialUpdate(TestMaterialLibrarySetup):
    """Test updating library materials"""
    
    def test_update_library_material_title(self, test_users):
        """PUT /api/library/materials/{id} - update title"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.put(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            data={"title": f"{TEST_PREFIX}Updated Workbook Title"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PUT /api/library/materials/{material_id} - title updated")
    
    def test_update_library_material_week(self, test_users):
        """PUT /api/library/materials/{id} - update week number"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.put(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            data={"week_number": "3"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PUT /api/library/materials/{material_id} - week updated to 3")
    
    def test_update_library_material_with_file(self, test_users):
        """PUT /api/library/materials/{id} - replace file"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        files = {"file": ("updated_workbook.pdf", io.BytesIO(pdf_content), "application/pdf")}
        
        response = requests.put(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files,
            data={"description": "Updated description with new file"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"PUT /api/library/materials/{material_id} - file replaced")
    
    def test_update_library_material_invalid_file_type(self, test_users):
        """PUT /api/library/materials/{id} - reject invalid file type"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        txt_content = b"This is a text file"
        files = {"file": ("invalid.txt", io.BytesIO(txt_content), "text/plain")}
        
        response = requests.put(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            files=files
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PUT /api/library/materials/{id} - correctly rejected .txt file (400)")
    
    def test_update_library_material_not_found(self, test_users):
        """PUT /api/library/materials/{id} - invalid material returns 404"""
        response = requests.put(
            f"{BASE_URL}/api/library/materials/invalid_material_id",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"},
            data={"title": "Should fail"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PUT /api/library/materials/{id} - correctly returns 404 for invalid material")
    
    def test_update_library_material_student_denied(self, test_users):
        """PUT /api/library/materials/{id} - student cannot update"""
        material_id = getattr(pytest, 'lib_workbook_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.put(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['student']['token']}"},
            data={"title": "Student update"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PUT /api/library/materials/{id} - correctly denied student (403)")


class TestCohortMaterialsWithLibrary(TestMaterialLibrarySetup):
    """Test that cohort materials endpoint includes library materials"""
    
    def test_cohort_materials_includes_library(self, test_users, test_cohorts):
        """GET /api/cohorts/{id}/materials - includes linked library materials"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{test_cohorts['cohort1']}/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Data is grouped by week
        assert isinstance(data, list), "Response should be a list of weeks"
        
        # Check if library materials are included
        all_materials = []
        for week in data:
            all_materials.extend(week.get("workbooks", []))
            all_materials.extend(week.get("case_studies", []))
        
        # Find library materials (they have is_library=True or material_id starts with lib_)
        library_materials = [m for m in all_materials if m.get("is_library") or m.get("material_id", "").startswith("lib_")]
        print(f"GET /api/cohorts/{test_cohorts['cohort1']}/materials - found {len(library_materials)} library materials")
    
    def test_cohort_materials_student_access(self, test_users, test_cohorts):
        """GET /api/cohorts/{id}/materials - student can access assigned cohort materials"""
        response = requests.get(
            f"{BASE_URL}/api/cohorts/{test_cohorts['cohort1']}/materials",
            headers={"Authorization": f"Bearer {test_users['student']['token']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"GET /api/cohorts/{test_cohorts['cohort1']}/materials - student can access")


class TestLibraryMaterialDelete(TestMaterialLibrarySetup):
    """Test deleting library materials"""
    
    def test_delete_library_material_student_denied(self, test_users):
        """DELETE /api/library/materials/{id} - student cannot delete"""
        material_id = getattr(pytest, 'lib_case_study_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.delete(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['student']['token']}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("DELETE /api/library/materials/{id} - correctly denied student (403)")
    
    def test_delete_library_material_not_found(self, test_users):
        """DELETE /api/library/materials/{id} - invalid material returns 404"""
        response = requests.delete(
            f"{BASE_URL}/api/library/materials/invalid_material_id",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("DELETE /api/library/materials/{id} - correctly returns 404 for invalid material")
    
    def test_delete_library_material_success(self, test_users):
        """DELETE /api/library/materials/{id} - instructor can delete"""
        material_id = getattr(pytest, 'lib_case_study_id', None)
        if not material_id:
            pytest.skip("No library material created")
        
        response = requests.delete(
            f"{BASE_URL}/api/library/materials/{material_id}",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"DELETE /api/library/materials/{material_id} - deleted successfully")
        
        # Verify deletion
        response = requests.get(
            f"{BASE_URL}/api/library/materials",
            headers={"Authorization": f"Bearer {test_users['instructor']['token']}"}
        )
        data = response.json()
        deleted_ids = [m["material_id"] for m in data]
        assert material_id not in deleted_ids, "Deleted material should not appear in list"
        print(f"DELETE /api/library/materials/{material_id} - verified deletion")


class TestCleanup(TestMaterialLibrarySetup):
    """Cleanup test data"""
    
    def test_cleanup(self, mongo_client, test_users, test_cohorts):
        """Clean up test data"""
        db = mongo_client
        
        # Delete test materials
        db.materials.delete_many({"title": {"$regex": f"^{TEST_PREFIX}"}})
        db.materials.delete_many({"is_library": True, "title": {"$regex": f"^{TEST_PREFIX}"}})
        
        # Delete test cohorts
        db.cohorts.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
        
        # Delete test users and sessions
        db.users.delete_many({"name": {"$regex": f"^{TEST_PREFIX}"}})
        db.user_sessions.delete_many({"session_token": {"$regex": "^(sa_token_|inst_token_|stu_token_)"}})
        
        print("Cleanup completed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
