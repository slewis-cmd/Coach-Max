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
- **GET /api/submit-link/{material_id}** (public — returns material info for direct submit page)
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

### Instructor Access to Submissions & Progress (Verified - March 25, 2026)
- [x] Sidebar navigation shows Dashboard, Submissions (with badge), and Progress links for all instructors
- [x] Backend `GET /api/submissions` scopes data to instructor's assigned cohorts only
- [x] Backend `GET /api/analytics/dashboard` scopes stats to instructor's cohorts only
- [x] Backend `GET /api/analytics/cohort/{id}` verifies instructor ownership via `is_cohort_manager`
- [x] Super admins see all cohorts/submissions; instructors see only their assigned cohorts
- [x] Verified end-to-end: instructor sees only their cohort's data on both pages

### Assign Instructor to Cohort (Completed - March 25, 2026)
- [x] POST /api/cohorts/{id}/assign-instructor — super admin can reassign a cohort to a different instructor
- [x] GET /api/instructors — super admin can list all instructors/admins
- [x] CohortDetail page shows "Assign Instructor" button for super admins
- [x] Dialog lists all instructors with "Current" and "Admin" badges
- [x] After assignment, instructor can see cohort submissions, progress, and analytics
- [x] Cohort detail API returns instructor_name and instructor_email
- [x] Tested: 18/18 backend + all frontend UI tests passed

### Notification Badge (March 21, 2026)
- [x] Bell icon with red badge count in instructor dashboard header (desktop + mobile)
- [x] Per-cohort pending submission count on cohort cards
- [x] Clicking bell navigates to submissions page

### Delete Submission (Completed - April 8, 2026)
- [x] DELETE /api/submissions/{submission_id} — instructor/admin only
- [x] Deletes file from disk, tutor_chats, and submission record
- [x] Trash icon button in FeedbackTab.js rows with confirmation dialog
- [x] Trash icon button in SubmissionDetail.js header for instructors
- [x] Dashboard analytics datetime parsing bug fixed (handled both string and datetime objects)
- [x] Tested: 6/6 backend tests passed, frontend code + UI verified

### Cumulative Training Context (April 9, 2026)
- [x] build_cumulative_context() helper — fetches prior weeks' materials + student's submissions/feedback
- [x] Coach Max chat now has full prior-weeks context in system prompt
- [x] AI feedback review (manual + auto) references earlier weeks and student growth
- [x] Prompts updated to instruct AI to connect current topics to prior learning
- [x] Tested: AI review references Week 1 in Week 2 feedback, Coach Max answers growth questions

### Weekly Coach Max Digest Email (April 9, 2026)
- [x] Automated weekly email to info@theboostpad.org every Monday 9 AM UTC
- [x] Includes AI-generated summary of student questions per cohort
- [x] Grouped by week with example questions and question counts
- [x] "Send Weekly Digest" manual trigger button on Instructor Dashboard
- [x] POST /api/admin/send-weekly-digest endpoint for manual trigger
- [x] Background scheduler starts on app startup
- [x] Tested: Email delivered successfully (Resend ID verified)

### Coach Max Insights Report (April 9, 2026)
- [x] GET /api/cohorts/{id}/coach-max-report — raw questions grouped by week with counts
- [x] POST /api/cohorts/{id}/coach-max-report/generate — AI-generated themes, counts, examples, recommendations
- [x] New "Coach Max Insights" tab in CohortDetail (alongside Materials, Students, Feedback)
- [x] Standalone /coach-max-insights/:cohortId page accessible from Instructor Dashboard
- [x] Per-week breakdown with "Generate Insights" button and expandable raw questions
- [x] Tested: 11/11 backend, 100% frontend (iteration_20)

### Audio TTS Feedback (April 9, 2026)
- [x] POST /api/submissions/{id}/audio — generates MP3 from feedback, caches result
- [x] POST /api/chat/audio — generates MP3 from Coach Max chat response
- [x] GET /api/audio/{filename} — serves audio files
- [x] "Listen to Feedback" button on SubmissionDetail with inline player + MP3 download
- [x] "Listen" button on each Coach Max chat response (plays via browser Audio API)
- [x] Uses OpenAI TTS (tts-1, voice: nova) via Emergent integrations
- [x] Audio caching to avoid regeneration for same feedback
- [x] Tested: 12/12 backend, 100% frontend (iteration_19)

### Spanish Language Support (April 9, 2026)
- [x] Students can set language preference (EN/ES) in sidebar of Student Dashboard
- [x] Coach Max chat page has per-chat language toggle in header
- [x] AI feedback generation uses student's language preference
- [x] Auto-review on submission uses student's language preference
- [x] Feedback emails and PDF export emails are localized for Spanish
- [x] Welcome messages, placeholders, and UI text switch dynamically
- [x] Tested: 7/7 backend, 100% frontend via Playwright (iteration_18)

### Code Quality Pass 3 (February 2026)
- [x] Extracted nested ternary in StudentDashboard.js into `getWeekNumberClass(status)` helper
- [x] Extracted nested ternary in SubmissionDetail.js into `<ReviewStatusBadge>` component
- [x] Lint clean on both files

### Persistent File Storage (February 2026)
- [x] **BUG FIX**: Student submissions no longer lost on redeploy — migrated all uploads from ephemeral `/app/backend/uploads/` disk to MongoDB GridFS
- [x] New helpers: `save_bytes_to_gridfs`, `read_bytes_from_doc`, `delete_file_from_doc`
- [x] Library materials, cohort materials, student submissions, submit-on-behalf, and TTS audio cache all use GridFS
- [x] Legacy records (file_path only) gracefully return HTTP 410 with clear resubmit message
- [x] 8/8 backend tests pass (iteration_21.json)

### Google Drive Homework Links (February 2026)
- [x] `drive_folder_url` optional field on `Material` (homework only)
- [x] `POST /api/cohorts/{id}/materials` + `POST /api/library/materials` accept `drive_folder_url` (dropped silently for non-homework types)
- [x] New `PUT /api/materials/{id}/drive-link` — super admin or cohort manager only; validates via `_validate_drive_url()` (urlparse-based, rejects `javascript:`, `ftp://`, bare hosts, etc.)
- [x] `/api/submit-link/{id}` returns the drive URL; student dashboard `homeworks[].drive_folder_url` populated
- [x] Frontend: **Cohort Materials tab** — new "Add/Change Drive Folder" button per homework (`window.prompt` for MVP UX, PUT to /drive-link)
- [x] **Public /submit/{id} page** — when Drive folder is set, prominent "Step 1: Upload to Google Drive" hint with "Open Drive Folder" button above the file upload
- [x] **Student Dashboard homework rows** — "Drive" button opens the folder in a new tab, sitting next to Submit
- [x] Renamed "Copy Submission Link for Thinkific" → "Copy Submission Link"
- [x] 15/15 backend tests pass (iteration_33.json); URL validation hardened per review

### Platform Branding / White-Label Prep (February 2026)
- [x] `GET /api/settings/branding` (public) + `PUT /api/settings/branding` (super admin) — persisted in `platform_settings` collection
- [x] Fields: app_name, ai_persona_name, primary_color, logo_url, favicon_url, email_sender_name, tagline, ai_system_prompt
- [x] Backend: `get_branding()` helper with 30s in-process cache; wired into Coach Max chat persona + email sender name; `ai_system_prompt` override supported
- [x] Frontend: `BrandingContext` fetches on mount, applies to browser tab title, favicon, CSS `--brand-primary`, Landing page nav/footer, Coach Max chat UI
- [x] New `/admin/branding` page for Super Admin — form for all fields incl. color picker; reload after save
- [x] 14/14 backend tests pass (iteration_32.json)
- [x] Foundation for licensing "My Professor" — rebrand a deployment via config, no code changes

### Multi-Homework per Week (February 2026)
- [x] `/api/student/dashboard` now returns `weeks[i].homeworks[]` — full array of homework tracks per week
- [x] Each homework entry has its own `status`, `submission`, `feedback`, `due_date`
- [x] Overall week status = least-complete across all homeworks (via `status_rank`)
- [x] Legacy `homework` / `submission` / `feedback` top-level fields preserved (point to first homework)
- [x] Frontend Student Dashboard renders one row per homework in the week card, with "Exercise 1" / "Exercise 2" labels when 2+
- [x] Each homework has its own Submit/Resubmit button, feedback expand, and Ask Coach Max button
- [x] Extracted `<HomeworkTrackRow>` and `<StatusBadge>` into `/components/student/`
- [x] Library homework materials assigned to a cohort also appear as tracks (via the existing library_materials.extend flow)
- [x] Submissions, AI reviews, and feedback emails all remain per-material-id (no changes needed)
- [x] 16/16 backend tests pass (iteration_31.json)

### Video Library Materials (February 2026)
- [x] New `material_type: "video"` — supports both **MP4/MOV/WEBM/M4A/WAV uploads** and **YouTube/Vimeo/Loom URLs**
- [x] Uploaded videos → **auto-transcribed via OpenAI Whisper** (background task using ffmpeg to extract mono 16kHz 32kbps audio, then `emergentintegrations.OpenAISpeechToText` with `whisper-1`)
- [x] Transcript stored on the material doc; automatically included in AI feedback context (`read_file_text` returns transcript for video materials)
- [x] `POST /api/library/materials/{id}/transcribe` — manually re-trigger transcription
- [x] `transcription_status` field: pending / done / failed / failed_too_large / n/a
- [x] Frontend: new "Videos" filter tab, Video option in upload dialog with mutually-exclusive File/URL inputs, HTML5 `<video>` preview for uploads, YouTube/Vimeo iframe for URL videos, transcription-status badges on rows
- [x] Student Dashboard "Course Resources" chips open URL videos in new tab (Play icon), download files otherwise
- [x] `duplicate_library_material` is now video-aware (URL preserved for URL videos; new GridFS + background re-transcription for uploaded videos)
- [x] 18/18 backend tests pass (iteration_30.json)

### Course-Wide (Global) Library Materials (February 2026)
- [x] Materials can be marked `is_global=True` — spans all weeks (week_number=0)
- [x] `POST /api/library/materials` accepts `is_global` query param; upload dialog has a Course-Wide checkbox
- [x] `GET /api/student/dashboard` returns `course_resources: [...]` at each cohort level with the assigned global materials
- [x] `build_cumulative_context()` and `review_submission` always prepend global materials to AI context, regardless of week
- [x] `submit_on_behalf` auto-review also prepends globals
- [x] `duplicate_library_material` now preserves `is_global` flag
- [x] Frontend: Material Library filter tab (All | Weekly | Course-Wide), badge on each row, Student Dashboard "Course Resources" section at top
- [x] 12/12 backend tests pass (iteration_28.json)

### Code Quality Pass 4 — Nested Ternaries (February 2026)
- [x] Extracted `PreviewToggleContent` component in SubmissionDetail.js (was 3-state ternary for button label)
- [x] Extracted `EmptyStateCard` component in StudentDashboard.js (was nested ternary for no-cohort / no-weeks / weeks states)
- [x] Extracted `getCompletionColorClass()` helper in ProgressTracking.js (was nested ternary for completion-rate text color)
- [x] Lint clean across frontend; smoke test passed
- [x] **Refused (incorrect):** PEP 8 `is None` → `== None` reversal — PEP 8 mandates `is None`
- [x] **Deferred:** httpOnly cookies migration (proxy reliability), backend function refactors (need scoped sessions)

### Component Refactor — SubmissionDetail (February 2026)
- [x] Split SubmissionDetail.js (670 → 566 lines) into 4 focused sub-components:
  - `/components/submission/SubmissionPreviewPane.js` (PDF iframe + DOCX text panel, 36 lines)
  - `/components/submission/FeedbackEditor.js` (edit-mode textarea + save controls, 54 lines)
  - `/components/submission/FeedbackDisplay.js` (read-only feedback + audio player, 67 lines)
  - `/components/submission/ReviewWorkflow.js` (3-step instructor workflow checklist, 27 lines)
- [x] All data-testid contracts preserved; 10/10 frontend regression flows pass (iteration_26.json)

### Library Material View / Inline Preview (February 2026)
- [x] `GET /api/materials/{id}/download?inline=1` — streams material inline (PDF iframe-renders directly)
- [x] `GET /api/materials/{id}/preview-text` — returns extracted text for DOCX (or PDF) with full ACL
- [x] Frontend View button on each MaterialLibrary row → opens a centered modal with PDF iframe or DOCX text; includes inline Download button
- [x] 15/15 backend tests pass (iteration_25.json)

### Duplicate / Save as Template (February 2026)
- [x] `POST /api/library/materials/{id}/duplicate` — clones a library material as an unassigned template (new GridFS file, title suffixed with " (Copy)")
- [x] `POST /api/cohorts/{id}/duplicate` — clones a cohort: new instructor=current user, empty students, carries `released_weeks` over, re-links library materials, clones non-library materials' GridFS files; does NOT copy submissions
- [x] Copy icon button on each row of MaterialLibrary
- [x] Copy icon button (visible on card hover) for each cohort card on InstructorDashboard
- [x] 8/8 backend tests pass (iteration_24.json)

### Inline Submission Preview (February 2026)
- [x] `GET /api/submissions/{id}/download?inline=1` — streams PDF inline with `application/pdf` media type (browser renders in iframe)
- [x] `GET /api/submissions/{id}/preview-text` — returns extracted text for DOCX (or PDF) with full ACL
- [x] Frontend "View preview" toggle on SubmissionDetail page (PDF iframe, DOCX as pre-formatted text)
- [x] **Side-by-side layout** — when preview is open, desktop switches to 2-column grid (preview left, feedback editor right); preview column is sticky; widens container to 1600px
- [x] **Cloudflare 520 fix** — replaced StreamingResponse(io.BytesIO(...)) with `binary_file_response()` helper (Response + explicit Content-Length + Accept-Ranges: none + X-Frame-Options: SAMEORIGIN). Fixes 520 'Web server is returning an unknown error' on iframe-loaded PDFs in production.
- [x] 15/15 new + 8/8 regression tests pass (iteration_22.json, iteration_23.json)

### Test Data Added (April 9, 2026)
- [x] Expanded system from 12 weeks to 14 weeks (backend validation + student dashboard loop)
- [x] Added "Test 1" (Week 13) and "Test 2" (Week 14) to Material Library
- [x] Each week has: Workbook, Case Study, Homework Assignment (6 materials total)
- [x] All materials downloadable and ready to assign to any cohort
- [x] Assigned to "Fall 2024 Leadership" cohort and released for students

### Named Submission Types + Thinkific-Stable Links (Completed - July 6, 2026)
- [x] 4 named homework submission types: `60_second_pitch`, `10_slide_pitch`, `case_activity`, `business_questionnaire` — coexist alongside generic homework (opt-in per material)
- [x] Per-type file-extension enforcement on `POST /api/materials/{id}/submit`:
  - 60 Second Pitch: mp4/mov/m4v/mp3/m4a/wav
  - 10 Slide Pitch Deck: pdf/ppt/pptx
  - Case Activity: pdf/doc/docx/txt
  - Business Questionnaire: no file — structured form
- [x] Business Questionnaire builder — instructor defines up to 20 questions (text / longtext / required flag); students see the form on the direct-submit page; answers stored on submission doc as `questionnaire_answers: {id: value}`
- [x] AI review synthesizes Q&A text for questionnaire submissions (via updated `read_file_text` — used by manual review + on-behalf auto-review). BUG FIX by testing agent: `review_submission` was still calling `read_bytes_from_doc`; now uses `read_file_text` which handles questionnaire fallback.
- [x] Download + preview-text endpoints serve questionnaire submissions as JSON payload / synthesized text (no file blob 404)
- [x] NEW `GET /api/submit-link/w/{week}/{submission_type}?cohort_id=...` resolver — 400 on bad type, 404 on no-match, 200 with `{material_id}` — enables **Thinkific-stable links** that never need updating
- [x] Frontend `/submit/w/:week/:submissionType` route → resolves + redirects to `/submit/{material_id}` (or 'Not published yet' card if unresolved)
- [x] "Copy Thinkific Link" button on every homework card that has a submission_type set (`data-testid=copy-stable-link-{material_id}`)
- [x] Shared `<SubmissionTypeFields/>` component embedded in both Upload Material dialogs; dynamic questionnaire builder appears when type = business_questionnaire
- [x] Direct-submit page real-time button disable when required questionnaire fields are empty
- [x] Testing: 24/24 new backend tests + 67/67 regression + 100% of 22 Playwright items PASS (iteration_37.json)

### Rubric Library (Completed - July 6, 2026)
- [x] MongoDB `rubrics` collection: `{rubric_id, name, content, description, created_by, created_by_name, created_at, updated_at}`
- [x] CRUD REST endpoints (`GET/POST/PUT/DELETE /api/rubrics[/{id}]`) — instructor-scoped list, shared visibility across org; edit/delete restricted to author + super_admin (403 otherwise, 404 for unknown IDs)
- [x] Input validation: name ≤ 200 chars, content ≤ 8000 chars, description ≤ 500 chars (400 on overflow)
- [x] Response includes `can_edit` flag per rubric (true for creator + super_admin)
- [x] `/rubrics` management page — create, edit (own), delete (own), see all
- [x] New sidebar link (data-testid `rubrics-link`)
- [x] Shared `<FeedbackTemplateField/>` component: rubric picker dropdown + textarea + "Save as…" button — embedded in both Upload Material dialogs (cohort + library) when material_type = homework
- [x] `<EditFeedbackTemplateDialog/>` — replaces `window.prompt` in both MaterialsTab and MaterialLibrary edit flows (fixes Safari 15+ compat issue from iteration_34)
- [x] Rubric fetch failure surfaces inline retry hint (no silent failure)
- [x] 32/32 pytest (16 new rubric + 16 feedback_template regression) PASS. 100% frontend Playwright review-item coverage (iteration_36.json)

### Code Quality — Safe Refactor Pass (Completed - July 6, 2026)
- [x] Empty error handlers replaced with `console.warn`/`console.error` (AuthContext logout/setRole/checkAuth, BrandingContext, CoachMaxPage chat + TTS, CoachMaxChat) — 404-silent branch preserved for expected empty-history cases
- [x] `useCallback` normalized across fetchers + reordered before their `useEffect` (InstructorDashboard, MaterialLibrary, SubmissionDetail, ProgressTracking) — no more stale closures
- [x] `useMemo` added: `filteredMaterials` in MaterialLibrary, `sortedWeeklyProgress` in ProgressTracking (also fixed state-mutating `.sort()` via `[...arr].sort()`)
- [x] `eslint-disable react-hooks/exhaustive-deps` comment removed from SubmissionDetail (deps now correct)
- [x] pytest antipattern: `is True` / `is False` → `== True` / `== False` across 12 assertions in 6 test files
- [x] Regression tested: 51/51 in-scope pytest + 10/10 frontend Playwright PASS (iteration_35.json). Custom AI Feedback Instructions feature still works E2E.
- **Skipped (explicit user decision):** localStorage → httpOnly cookies migration (preview-proxy risk), oversized-component splits (`MaterialLibrary`/`SubmissionDetail`/`CohortDetail`/`StudentDashboard`), Python function complexity refactor (`build_cumulative_context`, `upload_library_material`, `transcribe_video_material`, `bulk_import_students`).

### Custom AI Feedback Instructions (Completed - July 6, 2026)
- [x] `feedback_template` field on Material (homework only) — overrides the default "3 done well / 3 to improve" rubric
- [x] `POST /api/cohorts/{id}/materials` and `POST /api/library/materials` accept optional `feedback_template` query param (persisted only for homework)
- [x] `PUT /api/materials/{material_id}/feedback-template` — update/clear per-material AI rubric (homework only; ACL-checked)
- [x] Manual AI review (submit-on-behalf) and auto-review both inject the custom template into the OpenAI prompt when set
- [x] UI: "AI Feedback Instructions" textarea in Upload Material dialogs (cohort + library), homework-only
- [x] UI: "Add/Edit AI Instructions" button + Sparkles icon on homework cards (MaterialsTab + MaterialLibrary)
- [x] UI: "Custom AI Rubric" badge (data-testid `custom-rubric-badge-{material_id}`) visible on any homework with a customized template
- [x] 16/16 backend pytest + 11/11 frontend Playwright assertions PASS (iteration_34.json)

## Prioritized Backlog
### P1 (Next Up)
- [ ] Discussion/comments on submissions
- [ ] Replace Thinkific roster sync with a native alternative

### P2 (Future)
- [ ] Split `server.py` (>4700 lines) into routers/controllers/models
- [ ] Refactor complex functions (`build_cumulative_context`, `bulk_import_students`, `get_student_dashboard`)
- [ ] Split large components (`MaterialLibrary.js`, `StudentDashboard.js`, `CohortDetail.js`)
- [ ] Migrate auth tokens from `localStorage` to `httpOnly` cookies (deferred — proxy reliability)
- [ ] Shared `<FeedbackTemplateField/>` component to dedupe textarea between cohort + library dialogs
- [ ] Replace `window.prompt` edit flow with inline Dialog+Textarea (better UX, Safari 15+ compat)
- [ ] Add Pydantic model for `PUT /materials/{id}/feedback-template` (malformed JSON → 400 instead of 500)

### P2 (Future)
- [x] Export submissions and feedback as PDF (Completed - April 6, 2026)
- [x] Coach Max standalone page + email CTA fix (Completed - April 6, 2026)

### Completed (March 26 - April 3, 2026)
- [x] Material Library — Central library for workbooks/case studies/homework, linked across cohorts
- [x] Assign Instructor to Cohort — Super admin can reassign cohorts to different instructors
- [x] Multiple Instructors per Cohort — instructor_ids array, multi-select in dialog
- [x] Email routing — All system emails sent from and to info@theboostpad.org
- [x] Delete Cohorts — Admin dashboard cohort management with delete
- [x] Library Homework — Students can submit homework against library materials
- [x] Boost Pad Branding — Full rebrand with #22438E/#7CBAE6/#1A75BA/#E1F0FF palette, Montserrat/Lato fonts
- [x] Thinkific Integration — API sync for courses, students, progress; webhook receiver for real-time updates
- [x] Direct Submission Link — Instructors can copy a link per homework for students to submit via /submit/:materialId (April 3, 2026)
- [x] Code Quality Refactor — Component splitting, backend helper extraction, hardcoded secret removal, empty catch fix (April 3, 2026)
- [x] Email Delivery Fix — Emails now sent to actual recipients (not just admin), added student submission confirmation email, fixed instructor_ids lookup (April 4, 2026)
- [x] Code Quality Pass 2 — Removed console statements, simplified nested ternaries, extracted SubmissionStatusBadge component, verified `is None` comparisons correct (April 4, 2026)
- [x] Download Fix — Cleaned up seed data with fake file paths, centralized download utility with specific error messages, removed code duplication (April 4, 2026)

### Code Architecture After Refactoring
```
/app/frontend/src/
├── components/
│   ├── admin/AdminDialogs.js
│   ├── cohort/MaterialsTab.js, StudentsTab.js, CohortDialogs.js
│   ├── instructor/Sidebar.js, CreateCohortDialog.js
│   ├── student/CoachMaxChat.js
│   └── ui/ (Shadcn)
├── utils/download.js
├── pages/ (CohortDetail, InstructorDashboard, StudentDashboard, AdminManagement, etc.)
└── context/AuthContext.js
```
