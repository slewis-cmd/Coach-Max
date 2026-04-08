"""
Test DELETE /api/submissions/{submission_id} endpoint
Tests:
- 404 for non-existent submission
- 200 for successful delete with instructor auth
- 403 for unauthorized student access
- Verify tutor_chats are cleaned up on delete
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test tokens - created in MongoDB
INSTRUCTOR_TOKEN = "test-token-delete"
STUDENT_TOKEN = "test-student-token-delete"


class TestDeleteSubmission:
    """Tests for DELETE /api/submissions/{submission_id}"""
    
    def test_health_check(self):
        """Verify API is running"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")
    
    def test_delete_without_auth_returns_401(self):
        """DELETE without auth token should return 401"""
        response = requests.delete(f"{BASE_URL}/api/submissions/sub-test-delete")
        assert response.status_code == 401
        print("✓ DELETE without auth returns 401")
    
    def test_delete_nonexistent_returns_404(self):
        """DELETE non-existent submission should return 404"""
        response = requests.delete(
            f"{BASE_URL}/api/submissions/nonexistent-submission-id",
            headers={"Authorization": f"Bearer {INSTRUCTOR_TOKEN}"}
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data.get("detail", "").lower()
        print("✓ DELETE non-existent submission returns 404")
    
    def test_delete_existing_submission_success(self):
        """DELETE existing submission with instructor auth should return 200"""
        # First verify the submission exists
        get_response = requests.get(
            f"{BASE_URL}/api/submissions/sub-test-delete",
            headers={"Authorization": f"Bearer {INSTRUCTOR_TOKEN}"}
        )
        # If submission doesn't exist, create it first
        if get_response.status_code == 404:
            pytest.skip("Test submission not found - needs to be created first")
        
        # Delete the submission
        response = requests.delete(
            f"{BASE_URL}/api/submissions/sub-test-delete",
            headers={"Authorization": f"Bearer {INSTRUCTOR_TOKEN}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "deleted" in data.get("message", "").lower()
        print("✓ DELETE existing submission returns 200 with 'Submission deleted'")
        
        # Verify submission is actually deleted
        verify_response = requests.get(
            f"{BASE_URL}/api/submissions/sub-test-delete",
            headers={"Authorization": f"Bearer {INSTRUCTOR_TOKEN}"}
        )
        assert verify_response.status_code == 404
        print("✓ Submission verified as deleted (GET returns 404)")


class TestDeleteSubmissionStudentAccess:
    """Tests for student access to delete endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup_student_session(self):
        """Create a student session for testing"""
        import subprocess
        # Create student user and session
        subprocess.run([
            "mongosh", "--quiet", "--eval", """
            use('test_database');
            var student = db.users.findOne({user_id: 'student-for-delete-test'});
            if (!student) {
                db.users.insertOne({
                    user_id: 'student-for-delete-test',
                    email: 'student.delete.test@example.com',
                    name: 'Delete Test Student',
                    role: 'student',
                    created_at: new Date()
                });
            }
            var session = db.user_sessions.findOne({session_token: 'test-student-token-delete'});
            if (!session) {
                db.user_sessions.insertOne({
                    session_token: 'test-student-token-delete',
                    user_id: 'student-for-delete-test',
                    expires_at: new Date(Date.now() + 24*60*60*1000),
                    created_at: new Date()
                });
            }
            // Create a submission for the student to try to delete
            var sub = db.submissions.findOne({submission_id: 'sub-student-cannot-delete'});
            if (!sub) {
                db.submissions.insertOne({
                    submission_id: 'sub-student-cannot-delete',
                    material_id: 'mat_test',
                    student_id: 'student-for-delete-test',
                    cohort_id: 'cohort_3a1999cb7d72',
                    file_path: '',
                    status: 'pending',
                    file_name: 'student_test.pdf',
                    submitted_at: new Date()
                });
            }
            """
        ], capture_output=True)
        yield
    
    def test_student_cannot_delete_submission(self):
        """Student should get 403 when trying to delete a submission"""
        response = requests.delete(
            f"{BASE_URL}/api/submissions/sub-student-cannot-delete",
            headers={"Authorization": f"Bearer {STUDENT_TOKEN}"}
        )
        # Should be 403 Forbidden (instructor access required)
        assert response.status_code == 403
        print("✓ Student gets 403 when trying to delete submission")


class TestTutorChatCleanup:
    """Tests for tutor_chats cleanup on submission delete"""
    
    @pytest.fixture(autouse=True)
    def setup_submission_with_chat(self):
        """Create a submission with associated tutor chat"""
        import subprocess
        subprocess.run([
            "mongosh", "--quiet", "--eval", """
            use('test_database');
            // Create submission
            var sub = db.submissions.findOne({submission_id: 'sub-with-chat-delete'});
            if (!sub) {
                db.submissions.insertOne({
                    submission_id: 'sub-with-chat-delete',
                    material_id: 'mat_test',
                    student_id: 'student-001',
                    cohort_id: 'cohort_3a1999cb7d72',
                    file_path: '',
                    status: 'pending',
                    file_name: 'chat_test.pdf',
                    submitted_at: new Date()
                });
            }
            // Create tutor chat
            var chat = db.tutor_chats.findOne({submission_id: 'sub-with-chat-delete'});
            if (!chat) {
                db.tutor_chats.insertOne({
                    submission_id: 'sub-with-chat-delete',
                    student_id: 'student-001',
                    messages: [{role: 'user', content: 'test chat message'}],
                    created_at: new Date()
                });
            }
            print('Setup complete for chat cleanup test');
            """
        ], capture_output=True)
        yield
    
    def test_tutor_chats_deleted_with_submission(self):
        """Verify tutor_chats are deleted when submission is deleted"""
        import subprocess
        
        # Verify chat exists before delete
        result = subprocess.run([
            "mongosh", "--quiet", "--eval", """
            use('test_database');
            var chat = db.tutor_chats.findOne({submission_id: 'sub-with-chat-delete'});
            print(chat ? 'CHAT_EXISTS' : 'NO_CHAT');
            """
        ], capture_output=True, text=True)
        
        if "CHAT_EXISTS" not in result.stdout:
            pytest.skip("Tutor chat not found - setup may have failed")
        
        print("✓ Tutor chat exists before delete")
        
        # Delete the submission
        response = requests.delete(
            f"{BASE_URL}/api/submissions/sub-with-chat-delete",
            headers={"Authorization": f"Bearer {INSTRUCTOR_TOKEN}"}
        )
        assert response.status_code == 200
        print("✓ Submission deleted successfully")
        
        # Verify chat is also deleted
        result = subprocess.run([
            "mongosh", "--quiet", "--eval", """
            use('test_database');
            var chat = db.tutor_chats.findOne({submission_id: 'sub-with-chat-delete'});
            print(chat ? 'CHAT_EXISTS' : 'NO_CHAT');
            """
        ], capture_output=True, text=True)
        
        assert "NO_CHAT" in result.stdout
        print("✓ Tutor chat was deleted along with submission")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
