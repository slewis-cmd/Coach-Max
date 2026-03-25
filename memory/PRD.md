# ThinkificAI Tutor - Product Requirements Document

## Original Problem Statement
Build an AI tutor for Thinkific LMS Platform for a cohort learning environment. Upload weekly workbooks, case studies and homework assignments. AI Agent reviews homework submissions with qualitative encouraging feedback.

## User Choices
- **AI Model**: OpenAI GPT-5.2 via Emergent LLM Key
- **File Formats**: PDF and Word documents (.docx)
- **Feedback Style**: 3 bullet points on what was done well + 3 bullet points on areas for improvement
- **User Roles**: Super Admin > Instructor > Student
- **Authentication**: Emergent-managed Google Auth
- **Super Admin Email**: slewis@theboostpad.org
- **AI Tutor Name**: Coach Max

## Architecture
- **Frontend**: React with Tailwind CSS, Shadcn/UI components
- **Backend**: FastAPI with Python
- **Database**: MongoDB
- **AI Integration**: OpenAI GPT-5.2 via emergentintegrations library
- **Authentication**: Emergent OAuth with session-based auth (localStorage + Bearer token)
- **Email**: Resend API for notifications

## What's Been Implemented

### Core Platform (Completed)
- [x] Landing page with "Paper & Ink" design theme
- [x] Emergent Google OAuth authentication
- [x] Session-based auth with localStorage + Bearer token (cookies unreliable through proxy)
- [x] Landing page auto-redirects authenticated users to dashboard

### Super Admin Feature (Completed - March 18, 2026)
- [x] `super_admin` role with full instructor capabilities
- [x] Auto-promotion via SUPER_ADMIN_EMAIL env variable
- [x] Admin Management page (/admin) for super admins only
- [x] Invite/promote users to instructor role
- [x] Revoke instructor access (demote to student)
- [x] Super admin can manage ALL cohorts, submissions, and analytics

### Manual Week Release (Completed - March 18, 2026)
- [x] `released_weeks` array field on cohorts
- [x] POST /api/cohorts/{id}/release-week — instructor/admin releases a week
- [x] POST /api/cohorts/{id}/unrelease-week — instructor/admin hides a week
- [x] Student dashboard only shows released weeks
- [x] Eye/EyeOff toggle buttons on instructor CohortDetail page
- [x] "No weeks released yet" message for students when no weeks visible

### Coach Max AI Tutor Chat (Completed - March 18, 2026)
- [x] "Ask Coach Max" button appears on expanded feedback in student dashboard
- [x] Full chat interface with message history
- [x] Multi-turn conversation with GPT-5.2 (context includes feedback, submission, and course materials)
- [x] Chat history persisted in `tutor_chats` MongoDB collection
- [x] GET /api/chat/history/{submission_id} — retrieve past conversations
- [x] Only available after instructor sends feedback (status: "sent")

### Cohort & Content Management (Completed)
- [x] Cohort creation and student enrollment
- [x] Material upload (workbooks, case studies, homework) - PDF/DOCX
- [x] Weekly content organization (12 weeks)
- [x] File download functionality
- [x] Bulk student import via CSV
- [x] Material due dates for homework

### Student Dashboard (Redesigned - March 18, 2026)
- [x] 12-week progress view (filtered by released weeks)
- [x] Status tracking per week: Waiting on Submission, Submitted, Under Review, Feedback Provided
- [x] Inline feedback display with expand/collapse
- [x] Submit homework button with file upload
- [x] Coach Max chat accessible from feedback section

### AI Feedback & HITL (Completed)
- [x] Student homework submission with file upload (fixed label-based dialog upload)
- [x] AI review generation with structured 3+3 bullet format
- [x] Human-in-the-loop feedback workflow (draft → review → send)
- [x] Feedback posted to student dashboard after instructor approval

### Resubmission & Progress (Completed)
- [x] Resubmission capability for students
- [x] Progress Tracking Dashboard with cohort analytics
- [x] Email notifications for new submissions (Resend)

## API Endpoints
- POST /api/auth/session, GET /api/auth/me, POST /api/auth/logout, POST /api/auth/set-role
- GET/POST /api/admin/users, POST /api/admin/invite-instructor, POST /api/admin/revoke-instructor, GET /api/admin/stats
- GET/POST /api/cohorts, GET/PUT/DELETE /api/cohorts/{id}
- POST /api/cohorts/{id}/students, DELETE /api/cohorts/{id}/students/{studentId}
- POST /api/cohorts/{id}/students/bulk, GET /api/cohorts/{id}/students/template
- **POST /api/cohorts/{id}/release-week, POST /api/cohorts/{id}/unrelease-week**
- GET/POST /api/cohorts/{id}/materials, DELETE /api/materials/{id}, GET /api/materials/{id}/download
- POST /api/materials/{id}/submit
- **GET /api/student/dashboard** (weekly progress with released_weeks filter)
- GET /api/submissions, GET /api/submissions/{id}
- POST /api/submissions/{id}/review, PUT /api/submissions/{id}/feedback
- POST /api/submissions/{id}/send-feedback, POST /api/submissions/{id}/allow-resubmission
- **POST /api/chat/ask-tutor, GET /api/chat/history/{submission_id}**
- GET /api/analytics/dashboard, GET /api/analytics/cohort/{id}

## DB Schema
- **users**: {user_id, email, name, picture, role: [student|instructor|super_admin], created_at}
- **cohorts**: {cohort_id, name, description, instructor_id, student_ids[], **released_weeks[]**, created_at}
- **materials**: {material_id, cohort_id, week_number, material_type, title, description, file_path, file_name, uploaded_by, due_date, created_at}
- **submissions**: {submission_id, material_id, cohort_id, student_id, file_path, file_name, status, ai_feedback, instructor_feedback, feedback_sent, submitted_at, reviewed_at, sent_at, resubmission_allowed, resubmission_count}
- **user_sessions**: {user_id, session_token, expires_at, created_at}
- **tutor_chats**: {chat_id, submission_id, student_id, message, response, created_at}

## Bug Fixes
### File Download Bug Fix (March 21, 2026)
- [x] Root cause: Frontend used axios blob downloads which failed silently for end users
- [x] Fix: Backend `get_current_user` now accepts auth token via query parameter (`?token=xxx`)
- [x] Fix: Frontend download functions use `window.open(url + '?token=xxx')` for native browser downloads
- [x] All 3 download endpoints verified: materials, submissions, CSV template
- [x] Affected files: `server.py`, `StudentDashboard.js`, `InstructorDashboard.js`, `CohortDetail.js`

### CORS Fix for Downloads (March 22, 2026)
- [x] Root cause: `withCredentials:true` in axios + proxy's `Access-Control-Allow-Origin:*` = CORS violation
- [x] Removed `withCredentials:true` from ALL frontend code (interceptor + every individual call)
- [x] Removed `allow_credentials=True` from backend CORS (not needed with token-based auth)
- [x] Download functions now use native `fetch()` + blob (bypasses axios entirely)
- [x] Students can now download materials (workbooks, case studies) from expanded week view

### Student Submission Visibility & AI Feedback Display (March 22, 2026)
- [x] Cohort Detail page now shows AI feedback inline below each student submission
- [x] Student Dashboard prominently shows submitted homework file with download link
- [x] Students can see "Your submission: filename.pdf" with download icon for each week

### Progress Tracking Enhancement (March 25, 2026)
- [x] Student Progress section now has expandable rows per student
- [x] Each student shows week-by-week details: homework title, submission file (with download), AI/instructor feedback
- [x] Instructors can submit/resubmit homework on behalf of students from the progress view
- [x] Backend analytics endpoint returns per-student week_details with submission data and feedback

### Notification Badge (March 21, 2026)
- [x] Bell icon with red badge count in instructor dashboard header (desktop + mobile)
- [x] Per-cohort pending submission count on cohort cards
- [x] Clicking bell navigates to submissions page

## Prioritized Backlog
### P2 (Nice to Have - Future)
- [ ] Discussion/comments on submissions
- [ ] Custom feedback templates for instructors
- [ ] Multi-cohort material sharing
- [ ] Export submissions and feedback as PDF
