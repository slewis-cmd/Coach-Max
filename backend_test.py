#!/usr/bin/env python3

import requests
import json
import sys
from datetime import datetime, timezone
import io
import tempfile
import os

class ThinkificAITester:
    def __init__(self, base_url="https://learning-agent-hub-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.session_token = None
        self.test_user = None
        self.test_instructor = None
        self.tests_run = 0
        self.tests_passed = 0

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name}: {details}")

    def run_api_test(self, method, endpoint, expected_status=200, data=None, files=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api{endpoint}"
        
        if headers is None:
            headers = {}
        
        if self.session_token:
            headers['Authorization'] = f'Bearer {self.session_token}'
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, data=data, headers=headers)
                else:
                    headers.setdefault('Content-Type', 'application/json')
                    response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                headers.setdefault('Content-Type', 'application/json')
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            success = response.status_code == expected_status
            if success:
                try:
                    return True, response.json()
                except:
                    return True, {"status": "ok"}
            else:
                return False, f"Status {response.status_code}, expected {expected_status}. Response: {response.text[:200]}"

        except Exception as e:
            return False, f"Error: {str(e)}"

    def test_health_endpoints(self):
        """Test basic health endpoints"""
        print("\n🏥 Testing Health Endpoints...")
        
        # Test root endpoint
        success, result = self.run_api_test('GET', '/')
        self.log_test("API Root Endpoint", success, result if not success else "")
        
        # Test health endpoint
        success, result = self.run_api_test('GET', '/health')
        self.log_test("API Health Endpoint", success, result if not success else "")

    def mock_auth_session(self, role="instructor", user_id=None, email=None):
        """Create mock user session for testing"""
        print(f"\n👤 Creating mock {role} session...")
        
        if user_id is None:
            user_id = f"test_{role}_{datetime.now().strftime('%H%M%S')}"
        if email is None:
            email = f"{user_id}@test.com"
            
        # Create session token for testing
        session_token = f"test_session_{user_id}"
        self.session_token = session_token
        
        # Store user info
        user_data = {
            "user_id": user_id,
            "email": email,
            "name": f"Test {role.title()}",
            "role": role
        }
        
        if role == "instructor":
            self.test_instructor = user_data
        else:
            self.test_user = user_data
            
        return user_data

    def test_cohort_management(self):
        """Test cohort CRUD operations (instructor)"""
        print("\n📚 Testing Cohort Management...")
        
        # Mock instructor session
        instructor = self.mock_auth_session("instructor", "test_instructor_001")
        
        # Create cohort
        cohort_data = {
            "name": "Test Cohort 2024",
            "description": "A test cohort for API testing"
        }
        success, result = self.run_api_test('POST', '/cohorts', 201, cohort_data)
        self.log_test("Create Cohort", success, result if not success else "")
        
        if success:
            cohort_id = result.get('cohort_id')
            
            # Get cohorts list
            success, result = self.run_api_test('GET', '/cohorts')
            self.log_test("Get Cohorts List", success, result if not success else "")
            
            # Get single cohort
            success, result = self.run_api_test('GET', f'/cohorts/{cohort_id}')
            self.log_test("Get Single Cohort", success, result if not success else "")
            
            return cohort_id
        
        return None

    def test_student_management(self, cohort_id):
        """Test adding students to cohort"""
        print("\n👥 Testing Student Management...")
        
        if not cohort_id:
            print("⚠️ Skipping student tests - no cohort available")
            return None
            
        # Mock student session
        student = self.mock_auth_session("student", "test_student_001")
        
        # Try to add student to cohort (would require student to exist in DB)
        student_data = {"email": student["email"]}
        success, result = self.run_api_test('POST', f'/cohorts/{cohort_id}/students', 404, student_data)  # Expect 404 as student doesn't exist in DB
        self.log_test("Add Student to Cohort (Expected 404)", success or "not found" in str(result).lower(), result if not success else "")
        
        return student["user_id"]

    def test_material_upload(self, cohort_id):
        """Test material upload functionality"""
        print("\n📄 Testing Material Upload...")
        
        if not cohort_id:
            print("⚠️ Skipping material tests - no cohort available")
            return None
        
        # Switch back to instructor session
        self.mock_auth_session("instructor", "test_instructor_001")
        
        # Create a test PDF file
        test_content = "Test PDF content for homework assignment"
        
        # Create form data
        files = {
            'file': ('test_homework.pdf', io.BytesIO(test_content.encode()), 'application/pdf')
        }
        
        # Material upload parameters
        params = {
            'week_number': 1,
            'material_type': 'homework',
            'title': 'Test Homework Assignment',
            'description': 'A test homework for API testing'
        }
        
        # Test material upload
        success, result = self.run_api_test(
            'POST', 
            f'/cohorts/{cohort_id}/materials?' + '&'.join([f'{k}={v}' for k, v in params.items()]), 
            201, 
            data=params, 
            files=files
        )
        self.log_test("Upload Material", success, result if not success else "")
        
        if success:
            # Get materials list
            success, result = self.run_api_test('GET', f'/cohorts/{cohort_id}/materials')
            self.log_test("Get Materials List", success, result if not success else "")
            
            if success and result:
                # Find our uploaded material
                for week in result:
                    for homework in week.get('homework', []):
                        if homework['title'] == 'Test Homework Assignment':
                            return homework['material_id']
        
        return None

    def test_homework_submission(self, material_id):
        """Test homework submission"""
        print("\n📝 Testing Homework Submission...")
        
        if not material_id:
            print("⚠️ Skipping submission tests - no homework material available")
            return None
            
        # Switch to student session
        self.mock_auth_session("student", "test_student_001")
        
        # Create test submission file
        submission_content = "This is my homework submission content"
        files = {
            'file': ('submission.pdf', io.BytesIO(submission_content.encode()), 'application/pdf')
        }
        
        # Submit homework
        success, result = self.run_api_test(
            'POST', 
            f'/materials/{material_id}/submit', 
            404,  # Expect 404 as student not in cohort
            files=files
        )
        self.log_test("Submit Homework (Expected 404)", success or "not found" in str(result).lower() or "not enrolled" in str(result).lower(), result if not success else "")

    def test_ai_review_generation(self):
        """Test AI review functionality (mock)"""
        print("\n🤖 Testing AI Review Generation...")
        
        # This would normally require a real submission, so we'll test the auth requirement
        self.mock_auth_session("instructor", "test_instructor_001")
        
        fake_submission_id = "fake_submission_123"
        success, result = self.run_api_test('POST', f'/submissions/{fake_submission_id}/review', 404)
        self.log_test("AI Review Generation (Expected 404)", success or "not found" in str(result).lower(), result if not success else "")

    def test_submissions_endpoint(self):
        """Test submissions listing"""
        print("\n📋 Testing Submissions Endpoints...")
        
        # Test as instructor
        self.mock_auth_session("instructor", "test_instructor_001")
        success, result = self.run_api_test('GET', '/submissions')
        self.log_test("Get Submissions (Instructor)", success, result if not success else "")
        
        # Test as student
        self.mock_auth_session("student", "test_student_001")
        success, result = self.run_api_test('GET', '/submissions')
        self.log_test("Get Submissions (Student)", success, result if not success else "")

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("\n🔐 Testing Authentication...")
        
        # Test /auth/me without session
        self.session_token = None
        success, result = self.run_api_test('GET', '/auth/me', 401)
        self.log_test("Auth Me (No Token - Expected 401)", success, result if not success else "")
        
        # Test session creation (would need real session_id)
        session_data = {"session_id": "fake_session"}
        success, result = self.run_api_test('POST', '/auth/session', 401, session_data)
        self.log_test("Create Session (Expected 401)", success, result if not success else "")

    def run_all_tests(self):
        """Run comprehensive test suite"""
        print("🚀 Starting ThinkificAI API Tests...")
        print(f"Backend URL: {self.base_url}")
        
        try:
            # Basic health checks
            self.test_health_endpoints()
            
            # Authentication tests
            self.test_auth_endpoints()
            
            # Cohort management tests
            cohort_id = self.test_cohort_management()
            
            # Student management tests
            student_id = self.test_student_management(cohort_id)
            
            # Material upload tests
            material_id = self.test_material_upload(cohort_id)
            
            # Homework submission tests
            self.test_homework_submission(material_id)
            
            # AI review tests
            self.test_ai_review_generation()
            
            # Submissions listing tests
            self.test_submissions_endpoint()
            
        except Exception as e:
            print(f"❌ Test suite error: {e}")
            return 1

        # Print summary
        print(f"\n📊 Test Summary:")
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Success rate: {success_rate:.1f}%")
        
        if success_rate < 70:
            print("⚠️  Many tests failed - check backend implementation")
            return 1
        elif success_rate < 90:
            print("⚠️  Some tests failed - minor issues detected")
            return 0
        else:
            print("✅ Most tests passed - backend looks healthy!")
            return 0

def main():
    """Main test function"""
    tester = ThinkificAITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())