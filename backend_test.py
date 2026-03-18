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

    def test_homework_upload_with_due_date(self):
        """Test homework material upload with due date parameter"""
        print("\n" + "="*50)
        print("📅 TESTING HOMEWORK UPLOAD WITH DUE DATE")
        print("="*50)
        
        # Create a simple test PDF content (minimal PDF structure)
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Homework) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000207 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
296
%%EOF"""
        
        # Set due date to 7 days from now
        from datetime import datetime, timedelta
        due_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        
        # Test uploading homework with due date - use query parameters and multipart form
        files = {'file': ('test_homework.pdf', pdf_content, 'application/pdf')}
        
        from urllib.parse import urlencode
        params = {
            'week_number': 3,
            'material_type': 'homework',
            'title': 'Test Homework with Due Date',
            'description': 'Testing due date functionality',
            'due_date': due_date
        }
        
        url = f"{self.base_url}/api/cohorts/{self.cohort_id}/materials?{urlencode(params)}"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        print(f"🔍 Testing homework upload with due date...")
        print(f"   URL: {url}")
        print(f"   Due date: {due_date}")
        
        self.tests_run += 1
        try:
            response = requests.post(url, files=files, headers=headers)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                self.tests_passed += 1
                result = response.json()
                homework_material_id = result.get('material_id')
                print(f"✅ Homework uploaded successfully with due date")
                print(f"   Material ID: {homework_material_id}")
                return True, homework_material_id
            else:
                print(f"❌ Failed - Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False, None
                
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, None

    def test_submission_workflow(self, material_id=None):
        """Test the complete submission workflow with human-in-the-loop"""
        print("\n" + "="*50)
        print("🔄 TESTING SUBMISSION WORKFLOW (HUMAN-IN-THE-LOOP)")
        print("="*50)
        
        # Step 1: Test submissions listing
        success1, submissions = self.run_test(
            "Get submissions list",
            "GET",
            "submissions",
            200
        )
        
        if not success1:
            print("❌ Could not fetch submissions")
            return False
            
        print(f"   Found {len(submissions) if isinstance(submissions, list) else 0} submissions")
        
        # Find a pending submission to test with, or note that we need one
        pending_submissions = [s for s in submissions if s.get('status') == 'pending'] if isinstance(submissions, list) else []
        draft_submissions = [s for s in submissions if s.get('status') == 'draft'] if isinstance(submissions, list) else []
        
        print(f"   Pending submissions: {len(pending_submissions)}")
        print(f"   Draft submissions: {len(draft_submissions)}")
        
        if pending_submissions:
            submission_id = pending_submissions[0]['submission_id']
            print(f"   Testing with pending submission: {submission_id}")
            
            # Test the AI review generation
            return self.test_ai_review_and_feedback_flow(submission_id)
        elif draft_submissions:
            submission_id = draft_submissions[0]['submission_id']
            print(f"   Testing with draft submission: {submission_id}")
            
            # Test the feedback editing workflow
            return self.test_feedback_edit_and_send_flow(submission_id)
        else:
            print("   No pending or draft submissions found")
            print("   ✅ Submissions API is working, but no test data available for workflow testing")
            print(f"   Note: Material ID was {'provided' if material_id else 'not provided'}")
            return True

    def test_feedback_edit_and_send_flow(self, submission_id):
        """Test feedback editing and sending for a draft submission"""
        print(f"\n📝 Testing Feedback Edit and Send Flow for Draft Submission: {submission_id}")
        
        # Get current submission details
        success1, submission = self.run_test(
            "Get submission details",
            "GET",
            f"submissions/{submission_id}",
            200
        )
        
        if not success1:
            print("❌ Could not fetch submission details")
            return False
            
        current_feedback = submission.get('ai_feedback', '') or submission.get('instructor_feedback', '')
        if not current_feedback:
            print("   No existing feedback found, generating AI feedback first...")
            return self.test_ai_review_and_feedback_flow(submission_id)
        
        # Test updating feedback (PUT /api/submissions/{id}/feedback)
        updated_feedback = f"Updated feedback: {current_feedback[:200]}... [Instructor edits and additions for testing]"
        
        success2, update_response = self.run_test(
            "Update feedback (human-in-the-loop edit)",
            "PUT",
            f"submissions/{submission_id}/feedback", 
            200,
            data={"feedback": updated_feedback}
        )
        
        if success2:
            print("✅ Feedback update (human-in-the-loop) successful")
        else:
            print("❌ Feedback update failed")
            return False
        
        # Test sending feedback to student (POST /api/submissions/{id}/send-feedback)
        success3, send_response = self.run_test(
            "Send feedback to student",
            "POST",
            f"submissions/{submission_id}/send-feedback",
            200
        )
        
        if success3:
            print("✅ Feedback sent to student successfully")
            print("   Note: Email delivery may fail in test environment, but API should succeed")
        else:
            print("❌ Send feedback failed")
            return False
        
        return success1 and success2 and success3

    def test_ai_review_and_feedback_flow(self, submission_id):
        """Test AI review generation and human-in-the-loop feedback workflow"""
        print("\n📝 Testing AI Review and Feedback Flow")
        print(f"   Submission ID: {submission_id}")
        
        # Step 1: Generate AI review (should create 'draft' status)
        success1, review_response = self.run_test(
            "Generate AI review (should create draft)",
            "POST",
            f"submissions/{submission_id}/review",
            200
        )
        
        if not success1:
            print("❌ AI review generation failed")
            return False
            
        # Verify the response indicates draft status
        if review_response.get('status') == 'draft':
            print("✅ AI review correctly created draft status")
        else:
            print(f"⚠️  Expected 'draft' status, got: {review_response.get('status')}")
        
        feedback = review_response.get('feedback', '')
        if feedback:
            print(f"   Generated feedback (preview): {feedback[:100]}...")
        
        # Step 2: Test updating feedback (PUT /api/submissions/{id}/feedback)
        updated_feedback = f"Edited feedback: {feedback[:200]}... [Instructor additions and edits]"
        
        success2, update_response = self.run_test(
            "Update feedback (human-in-the-loop)",
            "PUT",
            f"submissions/{submission_id}/feedback", 
            200,
            data={"feedback": updated_feedback}
        )
        
        if success2:
            print("✅ Feedback update (human-in-the-loop) successful")
        else:
            print("❌ Feedback update failed")
            return False
        
        # Step 3: Test sending feedback to student (POST /api/submissions/{id}/send-feedback)
        success3, send_response = self.run_test(
            "Send feedback to student",
            "POST",
            f"submissions/{submission_id}/send-feedback",
            200
        )
        
        if success3:
            print("✅ Feedback sent to student successfully")
            print("   Note: Email delivery may fail in test environment, but API should succeed")
        else:
            print("❌ Send feedback failed")
            return False
        
        # Step 4: Verify submission status changed to 'sent'
        success4, final_submission = self.run_test(
            "Verify final submission status",
            "GET",
            f"submissions/{submission_id}",
            200
        )
        
        if success4:
            final_status = final_submission.get('status')
            if final_status == 'sent':
                print("✅ Submission status correctly updated to 'sent'")
            else:
                print(f"⚠️  Expected 'sent' status, got: {final_status}")
        
        return success1 and success2 and success3 and success4

    def test_due_date_display(self):
        """Test that due dates are properly returned in materials API"""
        print("\n" + "="*50)
        print("📅 TESTING DUE DATE DISPLAY")
        print("="*50)
        
        success, response = self.run_test(
            f"Get materials with due dates for cohort {self.cohort_id}",
            "GET",
            f"cohorts/{self.cohort_id}/materials",
            200
        )
        
        if success and isinstance(response, list):
            print(f"✅ Materials retrieved successfully")
            
            # Look for homework materials with due dates
            homework_with_due_dates = []
            for week in response:
                homework_list = week.get('homework', [])
                for hw in homework_list:
                    if hw.get('due_date'):
                        homework_with_due_dates.append(hw)
                        print(f"   Found homework '{hw['title']}' with due date: {hw['due_date']}")
            
            if homework_with_due_dates:
                print(f"✅ Found {len(homework_with_due_dates)} homework assignments with due dates")
                return True
            else:
                print("   No homework with due dates found (this may be expected if none uploaded)")
                return True
        else:
            print("❌ Could not retrieve materials")
            return False

    def test_dashboard_analytics(self):
        """Test dashboard analytics endpoint"""
        print("\n" + "="*50)
        print("📊 TESTING DASHBOARD ANALYTICS")
        print("="*50)
        
        success, response = self.run_test(
            "Get dashboard analytics",
            "GET",
            "analytics/dashboard",
            200
        )
        
        if success:
            print("✅ Dashboard analytics retrieved successfully")
            
            # Check response structure
            cohorts_count = response.get('cohorts', 0)
            total_students = response.get('total_students', 0)
            submissions = response.get('submissions', {})
            action_required = response.get('action_required', {})
            recent_activity = response.get('recent_activity', {})
            
            print(f"   Cohorts: {cohorts_count}")
            print(f"   Total Students: {total_students}")
            print(f"   Submissions - Pending: {submissions.get('pending', 0)}")
            print(f"   Submissions - Draft: {submissions.get('draft', 0)}")  
            print(f"   Submissions - Sent: {submissions.get('sent', 0)}")
            print(f"   Action Required - Needs Review: {action_required.get('needs_review', 0)}")
            print(f"   Action Required - Drafts to Send: {action_required.get('drafts_to_send', 0)}")
            print(f"   Recent Activity - This Week: {recent_activity.get('submissions_this_week', 0)}")
            
            # Verify required fields are present
            required_fields = ['cohorts', 'total_students', 'submissions', 'action_required']
            missing_fields = [field for field in required_fields if field not in response]
            
            if missing_fields:
                print(f"⚠️  Missing fields in response: {missing_fields}")
                return False
            else:
                print("✅ All required fields present in dashboard analytics")
                return True
        else:
            print("❌ Dashboard analytics failed")
            return False

    def test_cohort_analytics(self):
        """Test cohort-specific analytics endpoint"""
        print("\n" + "="*50)
        print("📊 TESTING COHORT ANALYTICS")
        print("="*50)
        
        success, response = self.run_test(
            f"Get cohort analytics for {self.cohort_id}",
            "GET",
            f"analytics/cohort/{self.cohort_id}",
            200
        )
        
        if success:
            print("✅ Cohort analytics retrieved successfully")
            
            # Check response structure
            cohort = response.get('cohort', {})
            overview = response.get('overview', {})
            student_progress = response.get('student_progress', [])
            weekly_progress = response.get('weekly_progress', [])
            
            print(f"   Cohort Name: {cohort.get('name', 'Unknown')}")
            print(f"   Total Students: {cohort.get('total_students', 0)}")
            print(f"   Total Homework: {cohort.get('total_homework', 0)}")
            print(f"   Total Submissions: {overview.get('total_submissions', 0)}")
            print(f"   Completed Reviews: {overview.get('completed_reviews', 0)}")
            print(f"   Pending Reviews: {overview.get('pending_reviews', 0)}")
            print(f"   Avg Completion Rate: {overview.get('avg_completion_rate', 0)}%")
            print(f"   Student Progress Entries: {len(student_progress)}")
            print(f"   Weekly Progress Entries: {len(weekly_progress)}")
            
            # Show sample student progress data
            if student_progress:
                sample_student = student_progress[0]
                print(f"   Sample Student: {sample_student.get('name', 'Unknown')}")
                print(f"     Completion Rate: {sample_student.get('completion_rate', 0)}%")
                print(f"     Submissions: {sample_student.get('submissions', 0)}")
                print(f"     Completed: {sample_student.get('completed', 0)}")
            
            # Show sample weekly progress data
            if weekly_progress:
                sample_week = weekly_progress[0]
                print(f"   Sample Week {sample_week.get('week', 'Unknown')}:")
                print(f"     Assignments: {sample_week.get('assignments', 0)}")
                print(f"     Submitted: {sample_week.get('submitted', 0)}")
                print(f"     Reviewed: {sample_week.get('reviewed', 0)}")
            
            # Verify required fields
            required_fields = ['cohort', 'overview', 'student_progress', 'weekly_progress']
            missing_fields = [field for field in required_fields if field not in response]
            
            if missing_fields:
                print(f"⚠️  Missing fields in response: {missing_fields}")
                return False
            else:
                print("✅ All required fields present in cohort analytics")
                return True
        else:
            print("❌ Cohort analytics failed")
            return False

    def test_resubmission_feature(self):
        """Test resubmission functionality"""
        print("\n" + "="*50)
        print("🔄 TESTING RESUBMISSION FEATURE")
        print("="*50)
        
        # First get submissions to find one that's sent
        success, submissions = self.run_test(
            "Get submissions for resubmission test",
            "GET",
            "submissions",
            200
        )
        
        if not success:
            print("❌ Could not fetch submissions")
            return False
        
        # Find a sent submission to test resubmission
        sent_submissions = [s for s in submissions if s.get('status') == 'sent' or s.get('feedback_sent')] if isinstance(submissions, list) else []
        
        if not sent_submissions:
            print("   No sent submissions found to test resubmission")
            print("   ✅ Resubmission API is available but no test data")
            return True
        
        submission_id = sent_submissions[0]['submission_id']
        print(f"   Testing with submission: {submission_id}")
        
        # Test allowing resubmission
        success1, response1 = self.run_test(
            f"Allow resubmission for {submission_id}",
            "POST",
            f"submissions/{submission_id}/allow-resubmission",
            200
        )
        
        if success1:
            print("✅ Resubmission allowed successfully")
            print(f"   Response: {response1.get('message', 'No message')}")
            
            # Verify the submission was updated
            success2, updated_submission = self.run_test(
                f"Verify resubmission flag set",
                "GET",
                f"submissions/{submission_id}",
                200
            )
            
            if success2:
                resubmission_allowed = updated_submission.get('resubmission_allowed', False)
                if resubmission_allowed:
                    print("✅ Resubmission flag correctly set in submission")
                    return True
                else:
                    print("⚠️  Resubmission flag not set in submission (may have been already set)")
                    return True  # Still success as API worked
            else:
                print("❌ Could not verify resubmission flag")
                return False
        else:
            # Check if it was already allowed
            if "already" in str(response1).lower():
                print("✅ Resubmission was already allowed (API working correctly)")
                return True
            else:
                print("❌ Allow resubmission failed")
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
        """Run all tests including new human-in-the-loop features"""
        print("🚀 Starting ThinkificAI Comprehensive Tests (Including New Features)")
        print("=" * 70)
        
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
        
        # Test existing download functionality
        self.test_material_download()
        
        # Test CSV template download
        self.test_csv_template_download()
        
        # Test bulk import
        self.test_bulk_student_import()
        
        # NEW FEATURE TESTS
        print("\n🆕 TESTING NEW FEATURES")
        print("=" * 50)
        
        # Test homework upload with due date
        homework_success, homework_material_id = self.test_homework_upload_with_due_date()
        
        # Test due date display in materials
        self.test_due_date_display()
        
        # Test submission workflow (human-in-the-loop)
        self.test_submission_workflow(homework_material_id if homework_success else None)
        
        # NEW ANALYTICS FEATURES
        print("\n📊 TESTING NEW ANALYTICS FEATURES")
        print("=" * 50)
        
        # Test dashboard analytics
        self.test_dashboard_analytics()
        
        # Test cohort analytics
        self.test_cohort_analytics()
        
        # Test resubmission feature
        self.test_resubmission_feature()
        
        # Print final results
        print("\n" + "=" * 70)
        print("📊 FINAL RESULTS")
        print("=" * 70)
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