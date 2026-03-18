#!/usr/bin/env python3
import requests
import sys
import json
import io
import csv
import os
from datetime import datetime

class ThinkificAITester:
    def __init__(self, base_url="https://learning-agent-hub-1.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = "test_sess_1773829867648"  # Provided instructor token
        self.cohort_id = "cohort_3a1999cb7d72"  # Provided cohort ID
        self.material_id = "mat_ab936a2cb162"  # Provided material ID
        self.tests_run = 0
        self.tests_passed = 0
        print(f"🔧 Testing ThinkificAI platform at: {base_url}")
        print(f"🎯 Using instructor token: {self.token}")
        print(f"📚 Testing cohort: {self.cohort_id}")
        print(f"📄 Testing material: {self.material_id}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers_override=None, response_type='json'):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {self.token}'}
        if headers_override:
            headers.update(headers_override)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        print(f"   Method: {method}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                if isinstance(data, dict) and 'Content-Type' in headers and headers['Content-Type'] == 'application/json':
                    response = requests.post(url, json=data, headers=headers)
                else:
                    response = requests.post(url, data=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            print(f"   Status: {response.status_code}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                if response_type == 'json' and response.content:
                    try:
                        resp_json = response.json()
                        print(f"   Response: {json.dumps(resp_json, indent=2)[:200]}...")
                        return success, resp_json
                    except:
                        return success, response.text
                else:
                    return success, response.content
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                print(f"   Response: {response.text[:300]}...")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_auth_access(self):
        """Test authentication and access"""
        print("\n" + "="*50)
        print("🔐 TESTING AUTHENTICATION")
        print("="*50)
        
        success, response = self.run_test(
            "Get current user",
            "GET", 
            "auth/me",
            200
        )
        
        if success:
            print(f"✅ Authenticated as: {response.get('name', 'Unknown')} ({response.get('role', 'Unknown')})")
            return True
        else:
            print("❌ Authentication failed - cannot proceed with tests")
            return False

    def test_cohort_access(self):
        """Test cohort access"""
        print("\n" + "="*50)
        print("📚 TESTING COHORT ACCESS")
        print("="*50)
        
        success, response = self.run_test(
            f"Get cohort {self.cohort_id}",
            "GET",
            f"cohorts/{self.cohort_id}",
            200
        )
        
        if success:
            print(f"✅ Cohort found: {response.get('name', 'Unknown')}")
            student_count = len(response.get('student_ids', []))
            print(f"   Students: {student_count}")
            return True, response
        return False, {}

    def test_material_download(self):
        """Test material download functionality"""
        print("\n" + "="*50)
        print("📄 TESTING MATERIAL DOWNLOAD")
        print("="*50)
        
        # First check if material exists
        success, response = self.run_test(
            f"Download material {self.material_id}",
            "GET",
            f"materials/{self.material_id}/download",
            200,
            response_type='binary'
        )
        
        if success:
            content_length = len(response) if response else 0
            print(f"✅ Material downloaded successfully - Size: {content_length} bytes")
            return True
        else:
            print("❌ Material download failed")
            return False

    def test_csv_template_download(self):
        """Test CSV template download"""
        print("\n" + "="*50)
        print("📋 TESTING CSV TEMPLATE DOWNLOAD") 
        print("="*50)
        
        success, response = self.run_test(
            f"Download student CSV template for cohort {self.cohort_id}",
            "GET",
            f"cohorts/{self.cohort_id}/students/template",
            200,
            response_type='csv'
        )
        
        if success:
            # Parse CSV to validate format
            try:
                csv_content = response.decode('utf-8') if isinstance(response, bytes) else str(response)
                print(f"✅ CSV template downloaded")
                print(f"   Content preview: {csv_content[:100]}...")
                
                # Validate CSV structure
                reader = csv.DictReader(io.StringIO(csv_content))
                headers = reader.fieldnames
                print(f"   CSV headers: {headers}")
                
                if 'email' in headers:
                    print("✅ CSV has required 'email' column")
                    return True
                else:
                    print("❌ CSV missing 'email' column")
                    return False
                    
            except Exception as e:
                print(f"❌ Error parsing CSV: {e}")
                return False
        return False

    def test_bulk_student_import(self):
        """Test bulk student import functionality"""
        print("\n" + "="*50) 
        print("👥 TESTING BULK STUDENT IMPORT")
        print("="*50)
        
        # Create a test CSV
        test_csv_content = """email,name
test.student1@example.com,Test Student 1
test.student2@example.com,Test Student 2
invalid-email,Invalid Entry
"""
        
        # Test with multipart form data
        files = {'file': ('test_students.csv', test_csv_content, 'text/csv')}
        
        url = f"{self.base_url}/api/cohorts/{self.cohort_id}/students/bulk"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        print(f"🔍 Testing bulk import...")
        print(f"   URL: {url}")
        print(f"   CSV content: {test_csv_content.strip()}")
        
        self.tests_run += 1
        try:
            response = requests.post(url, files=files, headers=headers)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                self.tests_passed += 1
                print(f"✅ Bulk import successful")
                
                try:
                    result = response.json()
                    print(f"   Response: {json.dumps(result, indent=2)}")
                    
                    # Check results structure
                    results = result.get('results', {})
                    added = results.get('added', [])
                    not_found = results.get('not_found', [])
                    already_enrolled = results.get('already_enrolled', [])
                    errors = results.get('errors', [])
                    
                    print(f"   Added: {len(added)}")
                    print(f"   Not found: {len(not_found)}")  
                    print(f"   Already enrolled: {len(already_enrolled)}")
                    print(f"   Errors: {len(errors)}")
                    
                    return True
                    
                except Exception as e:
                    print(f"   Error parsing response: {e}")
                    print(f"   Raw response: {response.text}")
                    return True  # Still count as success if status was 200
            else:
                print(f"❌ Failed - Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False

    def test_materials_list(self):
        """Test materials listing to verify context"""
        print("\n" + "="*50)
        print("📚 TESTING MATERIALS LIST")
        print("="*50)
        
        success, response = self.run_test(
            f"Get materials for cohort {self.cohort_id}",
            "GET",
            f"cohorts/{self.cohort_id}/materials",
            200
        )
        
        if success:
            print(f"✅ Materials list retrieved")
            if isinstance(response, list):
                print(f"   Found {len(response)} weeks with materials")
                for week in response:
                    week_num = week.get('week_number', 'Unknown')
                    workbooks = len(week.get('workbooks', []))
                    case_studies = len(week.get('case_studies', []))
                    homework = len(week.get('homework', []))
                    print(f"   Week {week_num}: {workbooks} workbooks, {case_studies} case studies, {homework} homework")
            return True
        return False

    def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting ThinkificAI Download & Import Tests")
        print("=" * 60)
        
        # Test authentication first
        if not self.test_auth_access():
            return 1
        
        # Test cohort access
        cohort_success, cohort_data = self.test_cohort_access()
        if not cohort_success:
            print("❌ Cannot access cohort - stopping tests")
            return 1
        
        # Test materials list for context
        self.test_materials_list()
        
        # Test new download functionality
        self.test_material_download()
        
        # Test CSV template download
        self.test_csv_template_download()
        
        # Test bulk import
        self.test_bulk_student_import()
        
        # Print final results
        print("\n" + "=" * 60)
        print("📊 FINAL RESULTS")
        print("=" * 60)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run)*100:.1f}%" if self.tests_run > 0 else "0%")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print(f"⚠️  {self.tests_run - self.tests_passed} test(s) failed")
            return 1

def main():
    """Main test runner"""
    tester = ThinkificAITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())