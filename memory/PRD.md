# ThinkificAI Tutor - Product Requirements Document

## Original Problem Statement
Build an AI tutor for Thinkific LMS Platform for a cohort learning environment. Upload weekly workbooks, case studies and homework assignments. AI Agent reviews homework submissions with qualitative encouraging feedback.

## User Choices
- **AI Model**: OpenAI GPT-5.2 via Emergent LLM Key
- **File Formats**: PDF and Word documents (.docx)
- **Feedback Style**: Qualitative encouraging feedback (no grades/scores)
- **User Roles**: Both instructors and students with cohort/group management
- **Authentication**: Emergent-managed Google Auth

## Architecture
- **Frontend**: React with Tailwind CSS, Shadcn/UI components
- **Backend**: FastAPI with Python
- **Database**: MongoDB
- **AI Integration**: OpenAI GPT-5.2 via emergentintegrations library
- **Authentication**: Emergent OAuth with session-based auth

## User Personas

### Instructor
- Creates and manages cohorts
- Uploads weekly materials (workbooks, case studies, homework)
- Adds students to cohorts by email
- Triggers AI reviews for student submissions
- Views all submissions and feedback

### Student
- Views enrolled cohorts and materials
- Downloads workbooks and case studies
- Submits homework assignments
- Receives AI-generated encouraging feedback

## Core Requirements (Static)
1. Google OAuth authentication with role-based access
2. Cohort/group creation and management
3. Weekly material organization (workbooks, case studies, homework)
4. PDF and Word document upload support
5. Student homework submission system
6. AI-powered qualitative feedback generation

## What's Been Implemented (March 18, 2026)
- [x] Landing page with "Paper & Ink" design theme
- [x] Emergent Google OAuth authentication
- [x] Role selection (instructor/student)
- [x] Instructor dashboard with cohort management
- [x] Student dashboard with course overview
- [x] Cohort creation and student enrollment
- [x] Material upload (workbooks, case studies, homework)
- [x] Weekly content organization
- [x] Student homework submission
- [x] AI review generation using GPT-5.2
- [x] Encouraging feedback display in "letter" style
- [x] Submissions page with pending/reviewed sections

## API Endpoints
- POST /api/auth/session - Exchange session_id for token
- GET /api/auth/me - Get current user
- POST /api/auth/logout - Logout
- POST /api/auth/set-role - Set user role
- GET/POST /api/cohorts - List/Create cohorts
- GET/PUT/DELETE /api/cohorts/{id} - Cohort operations
- POST /api/cohorts/{id}/students - Add student
- DELETE /api/cohorts/{id}/students/{studentId} - Remove student
- GET/POST /api/cohorts/{id}/materials - List/Upload materials
- DELETE /api/materials/{id} - Delete material
- POST /api/materials/{id}/submit - Submit homework
- GET /api/submissions - List submissions
- GET /api/submissions/{id} - Get submission detail
- POST /api/submissions/{id}/review - Generate AI review

## Prioritized Backlog

### P0 (Critical - Completed)
- [x] Authentication flow
- [x] Cohort management
- [x] Material upload
- [x] Homework submission
- [x] AI feedback generation

### P1 (Important - Next Phase)
- [ ] File download functionality for materials
- [ ] Resubmission capability for students
- [ ] Email notifications for new submissions
- [ ] Bulk student import (CSV)
- [ ] Material due dates

### P2 (Nice to Have)
- [ ] Discussion/comments on submissions
- [ ] Progress tracking dashboard
- [ ] Custom feedback templates for instructors
- [ ] Multi-cohort material sharing
- [ ] Export submissions and feedback as PDF

## Next Tasks
1. Implement file download for materials
2. Add resubmission flow for students
3. Set up email notifications with SendGrid
4. Add bulk student import feature
5. Consider analytics dashboard for instructor insights
