# Test Credentials

## Super Admin (Google-authenticated)
- **Email:** slewis@theboostpad.org
- **Password:** Teach2026
- **Role:** super_admin
- **Access:** Full platform access (manage all cohorts, materials, submissions, invite instructors, view all analytics)

## Notes for Testing Agents
- Auth is Emergent-managed Google OAuth. For API-level tests, seed a session token directly into the `user_sessions` Mongo collection and pass it as `Authorization: Bearer <token>` or `?token=<token>` query param (`get_current_user` in `/app/backend/server.py` supports both).
- The super admin is auto-promoted at startup via `SUPER_ADMIN_EMAIL` env variable — no manual seeding needed.
- For student-facing tests, insert a user doc directly into the `users` collection (role: "student"), add the `user_id` to a cohort's `student_ids` array, then seed a session token. Clean up in fixture teardown.
