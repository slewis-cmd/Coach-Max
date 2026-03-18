# ThinkificAI Tutor - Product Requirements Document

## Original Problem Statement
Build an AI tutor for Thinkific LMS Platform for a cohort learning environment. Upload weekly workbooks, case studies and homework assignments. AI Agent reviews homework submissions with qualitative encouraging feedback.

## User Choices
- **AI Model**: OpenAI GPT-5.2 via Emergent LLM Key
- **File Formats**: PDF and Word documents (.docx)
- **Feedback Style**: Qualitative encouraging feedback (no grades/scores)
- **User Roles**: Super Admin > Instructor > Student
- **Authentication**: Emergent-managed Google Auth
- **Super Admin Email**: slewis@theboostpad.org

## Architecture
- **Frontend**: React with Tailwind CSS, Shadcn/UI components
- **Backend**: FastAPI with Python
- **Database**: MongoDB
- **AI Integration**: OpenAI GPT-5.2 via emergentintegrations library
- **Authentication**: Emergent OAuth with session-based auth
- **Email**: Resend API for notifications

## User Personas

### Super Admin (slewis@theboostpad.org)
- Has all instructor capabilities
- Can promote/demote users to instructor
- Can view all cohorts, submissions, and analytics across the platform
- Manages platform users via Admin Management page
- Auto-promoted on login via SUPER_ADMIN_EMAIL env

### Instructor (promoted by Super Admin)
- Creates and manages their own cohorts
- Uploads weekly materials (workbooks, case studies, homework)
- Adds students to cohorts by email
- Triggers AI reviews for student submissions
- Reviews, edits, and sends feedback (Human-in-the-Loop)

### Student (default role for all new users)
- Views enrolled cohorts and materials
- Downloads workbooks and case studies
- Submits homework assignments
- Receives AI-generated encouraging feedback via email

## What's Been Implemented

### Core Platform (Completed)
- [x] Landing page with "Paper & Ink" design theme
- [x] Emergent Google OAuth authentication
- [x] Session-based auth with cookies

### Super Admin Feature (Completed - March 18, 2026)
- [x] `super_admin` role with full instructor capabilities
- [x] Auto-promotion via SUPER_ADMIN_EMAIL env variable
- [x] Admin Management page (/admin) for super admins only
- [x] Invite/promote users to instructor role
- [x] Revoke instructor access (demote to student)
- [x] Platform stats (total users, roles, cohorts, submissions)
- [x] Only super admins can promote to instructor
- [x] RoleSelection page only offers student role
- [x] Admin link in sidebar visible only to super admins
- [x] Super admin can manage ALL cohorts, submissions, and analytics

### Cohort & Content Management (Completed)
- [x] Cohort creation and student enrollment
- [x] Material upload (workbooks, case studies, homework) - PDF/DOCX
- [x] Weekly content organization
- [x] File download functionality for all materials
- [x] Bulk student import via CSV
- [x] CSV template download for bulk import
- [x] Material due dates for homework assignments

### AI Feedback & HITL (Completed)
- [x] Student homework submission
- [x] AI review generation using GPT-5.2
- [x] Human-in-the-loop feedback workflow (draft → review → send)
- [x] Instructor can edit AI-generated feedback
- [x] Feedback sent to student via email (Resend)
- [x] Encouraging feedback display in "letter" style

### Resubmission & Progress (Completed)
- [x] Resubmission capability for students (instructor can allow)
- [x] Student notified via email for resubmission
- [x] Resubmission count tracked
- [x] Progress Tracking Dashboard with cohort analytics
- [x] Weekly progress with completion rates
- [x] Individual student progress rankings

### Dashboard & Notifications (Completed)
- [x] Color-coded stat cards (needs review, drafts to send, feedback sent)
- [x] Action required alert banner
- [x] This week activity summary
- [x] Email notifications for new submissions (Resend)

## API Endpoints
- POST /api/auth/session - Exchange session_id for token
- GET /api/auth/me - Get current user
- POST /api/auth/logout - Logout
- POST /api/auth/set-role - Set user role (restricted)
- GET /api/admin/users - List all users (super_admin only)
- POST /api/admin/invite-instructor - Promote user (super_admin only)
- POST /api/admin/revoke-instructor - Demote user (super_admin only)
- GET /api/admin/stats - Platform stats (super_admin only)
- GET/POST /api/cohorts - List/Create cohorts
- GET/PUT/DELETE /api/cohorts/{id} - Cohort operations
- POST /api/cohorts/{id}/students - Add student
- DELETE /api/cohorts/{id}/students/{studentId} - Remove student
- POST /api/cohorts/{id}/students/bulk - Bulk import students (CSV)
- GET /api/cohorts/{id}/students/template - Download CSV template
- GET/POST /api/cohorts/{id}/materials - List/Upload materials
- DELETE /api/materials/{id} - Delete material
- GET /api/materials/{id}/download - Download material file
- POST /api/materials/{id}/submit - Submit homework
- GET /api/submissions - List submissions
- GET /api/submissions/{id} - Get submission detail
- POST /api/submissions/{id}/review - Generate AI draft feedback
- PUT /api/submissions/{id}/feedback - Edit feedback (HITL)
- POST /api/submissions/{id}/send-feedback - Send feedback to student
- POST /api/submissions/{id}/allow-resubmission - Allow resubmission
- GET /api/analytics/dashboard - Dashboard analytics
- GET /api/analytics/cohort/{id} - Cohort analytics

## Prioritized Backlog

### P0 (Critical - All Completed)
- [x] Authentication flow
- [x] Cohort management
- [x] Material upload
- [x] Homework submission
- [x] AI feedback generation
- [x] Super Admin role

### P1 (Important - All Completed)
- [x] File download functionality
- [x] Bulk student import (CSV)
- [x] Email notifications
- [x] Material due dates
- [x] Human-in-the-loop feedback
- [x] Resubmission capability
- [x] Progress tracking dashboard
- [x] Dashboard widgets

### P2 (Nice to Have - Future)
- [ ] Discussion/comments on submissions
- [ ] Custom feedback templates for instructors
- [ ] Multi-cohort material sharing
- [ ] Export submissions and feedback as PDF

## DB Schema
- **users**: {user_id, email, name, picture, role: [student|instructor|super_admin], created_at}
- **cohorts**: {cohort_id, name, description, instructor_id, student_ids[], created_at}
- **materials**: {material_id, cohort_id, week_number, material_type, title, description, file_path, file_name, uploaded_by, due_date, created_at}
- **submissions**: {submission_id, material_id, cohort_id, student_id, file_path, file_name, status, ai_feedback, instructor_feedback, feedback_sent, submitted_at, reviewed_at, sent_at, resubmission_allowed, resubmission_count}
- **user_sessions**: {user_id, session_token, expires_at, created_at}
