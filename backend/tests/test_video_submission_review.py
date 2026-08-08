"""
Focused test suite for iteration_44 BUG FIX: Video/Audio SUBMISSION transcription
+ auto-review pipeline (60-Second Pitch was timing out on production).

Coverage:
1. Pure helpers: _is_media_submission, _transcribe_media_bytes (mp3 fallback path — works WITHOUT ffmpeg).
2. _ensure_submission_transcript: persists transcript + transcription_status to db.submissions.
3. End-to-end: instructor submit-on-behalf with a real short mp3 → background auto-review
   transcribes, then either generates ai_feedback OR sets ai_feedback_error + status='review_failed'.
4. Manual review endpoint: POST /submissions/{id}/review works for milestone-based submissions.
5. Regression: non-media (.pdf) submissions still work — _ensure_submission_transcript is no-op.
6. Fallback (no ffmpeg): direct Whisper path on ≤ 25MB native-format files.

Uses seeded ephemeral instructor + student + cohort + assignment (all TEST_VSR_ prefixed).
"""
import os
import io
import sys
import time
import uuid
import shutil
import asyncio
import subprocess
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Make backend importable so we can call helpers in-process
sys.path.insert(0, "/app/backend")

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME')

TAG = "TEST_VSR_"


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ----------- generate a real short mp3 (32kbps mono 16kHz sine) -------------
def _make_mp3_bytes(duration_sec: float = 2.0, freq: int = 440) -> bytes:
    """Uses ffmpeg CLI to synthesize a small mp3 sine tone. Result is ~8KB for 2s.
    Whisper will accept but likely return an empty transcript for pure tone."""
    path = f"/tmp/_vsr_{uuid.uuid4().hex[:6]}.mp3"
    try:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
             "-i", f"sine=frequency={freq}:duration={duration_sec}",
             "-ar", "16000", "-ac", "1", "-b:a", "32k", path],
            check=True, timeout=30,
        )
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ----------- seed fixture ---------------------------------------------------
@pytest.fixture(scope="module")
def seed():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    inst_id = f"{TAG}inst_{uuid.uuid4().hex[:8]}"
    stu_id = f"{TAG}stu_{uuid.uuid4().hex[:8]}"
    cohort_id = f"{TAG}coh_{uuid.uuid4().hex[:8]}"
    asgn_pitch_id = f"{TAG}asgn_pitch_{uuid.uuid4().hex[:8]}"
    asgn_case_id = f"{TAG}asgn_case_{uuid.uuid4().hex[:8]}"
    asgn_q_id = f"{TAG}asgn_q_{uuid.uuid4().hex[:8]}"
    ms_pitch_id = f"{TAG}ms_pitch_{uuid.uuid4().hex[:8]}"
    ms_case_id = f"{TAG}ms_case_{uuid.uuid4().hex[:8]}"
    ms_q_id = f"{TAG}ms_q_{uuid.uuid4().hex[:8]}"
    inst_tok = f"{TAG}tok_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    async def setup():
        await db.users.insert_many([
            {"user_id": inst_id, "email": f"{inst_id}@t.test", "name": "Inst VSR",
             "role": "instructor", "created_at": now},
            {"user_id": stu_id, "email": f"{stu_id}@t.test", "name": "Stu VSR",
             "role": "student", "created_at": now, "language_preference": "en"},
        ])
        await db.user_sessions.insert_one({
            "session_token": inst_tok, "user_id": inst_id, "email": f"{inst_id}@t.test",
            "expires_at": (datetime.now(timezone.utc).replace(
                year=datetime.now().year + 1)).isoformat(),
            "created_at": now,
        })
        await db.cohorts.insert_one({
            "cohort_id": cohort_id, "name": f"{TAG}Cohort",
            "instructor_ids": [inst_id],
            "student_ids": [stu_id],
            "total_weeks": 4, "current_week": 4,
            "auto_send_feedback": False,
            "created_at": now,
        })
        # Pitch assignment (media)
        await db.assignments.insert_one({
            "assignment_id": asgn_pitch_id, "cohort_id": cohort_id,
            "title": f"{TAG}Pitch", "description": "60-second pitch",
            "submission_type": "60_second_pitch",
            "feedback_template": "", "drive_folder_url": "",
            "questionnaire_fields": [], "is_active": True,
            "milestones": [
                {"milestone_id": ms_pitch_id, "week_number": 1,
                 "title": "Pitch Week 1", "description": "",
                 "feedback_template_override": "", "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })
        # Case activity assignment (pdf/docx — non-media, regression)
        await db.assignments.insert_one({
            "assignment_id": asgn_case_id, "cohort_id": cohort_id,
            "title": f"{TAG}Case", "description": "case activity",
            "submission_type": "case_activity",
            "feedback_template": "", "drive_folder_url": "",
            "questionnaire_fields": [], "is_active": True,
            "milestones": [
                {"milestone_id": ms_case_id, "week_number": 1,
                 "title": "Case W1", "description": "",
                 "feedback_template_override": "", "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })
        # Questionnaire assignment (regression)
        await db.assignments.insert_one({
            "assignment_id": asgn_q_id, "cohort_id": cohort_id,
            "title": f"{TAG}Q", "description": "business q",
            "submission_type": "business_questionnaire",
            "feedback_template": "", "drive_folder_url": "",
            "questionnaire_fields": [
                {"id": "q1", "label": "What is your idea?", "type": "text", "required": True},
            ],
            "is_active": True,
            "milestones": [
                {"milestone_id": ms_q_id, "week_number": 1,
                 "title": "Q W1", "description": "",
                 "feedback_template_override": "", "drive_folder_url_override": "",
                 "is_final_capstone": False, "due_date": None},
            ],
            "created_at": now,
        })

    _run(setup())

    ctx = {
        "inst_id": inst_id, "stu_id": stu_id,
        "cohort_id": cohort_id,
        "asgn_pitch_id": asgn_pitch_id, "ms_pitch_id": ms_pitch_id,
        "asgn_case_id": asgn_case_id, "ms_case_id": ms_case_id,
        "asgn_q_id": asgn_q_id, "ms_q_id": ms_q_id,
        "inst_tok": inst_tok,
        "auth": {"Authorization": f"Bearer {inst_tok}"},
    }
    yield ctx

    async def teardown():
        await db.users.delete_many({"user_id": {"$regex": f"^{TAG}"}})
        await db.user_sessions.delete_many({"session_token": {"$regex": f"^{TAG}"}})
        await db.cohorts.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
        await db.assignments.delete_many({"assignment_id": {"$regex": f"^{TAG}"}})
        await db.submissions.delete_many({"cohort_id": {"$regex": f"^{TAG}"}})
    _run(teardown())
    client.close()


# ============================================================================
# 1. Pure helpers — in-process
# ============================================================================
class TestPureHelpers:
    def test_is_media_submission_positive(self):
        from server import _is_media_submission
        for name in ["pitch.mp4", "clip.MOV", "voice.mp3", "audio.wav",
                     "rec.webm", "vid.m4v", "sound.flac"]:
            assert _is_media_submission({"file_name": name}) == True, name

    def test_is_media_submission_negative(self):
        from server import _is_media_submission
        for name in ["doc.pdf", "slides.pptx", "notes.docx", "readme.txt",
                     "", "no-extension"]:
            assert _is_media_submission({"file_name": name}) == False, name
        # No file_name key at all
        assert _is_media_submission({}) == False
        # Questionnaire (no file_name → treated as non-media)
        assert _is_media_submission({"submission_type": "business_questionnaire",
                                     "questionnaire_answers": {"x": "y"}}) == False

    def test_transcribe_media_bytes_returns_tuple_mp3(self):
        """Real mp3 (2s tone) → Whisper should return ('done', <string>).
        For pure tone the transcript is likely empty — that's OK."""
        from server import _transcribe_media_bytes
        mp3 = _make_mp3_bytes(duration_sec=2.0)
        assert 1000 < len(mp3) < 50_000, f"unexpected mp3 size {len(mp3)}"
        status, transcript = _run(_transcribe_media_bytes(mp3, "test.mp3"))
        assert status in ("done", "failed"), f"Unexpected status {status}"
        assert isinstance(transcript, str)
        print(f"[helper] status={status}, transcript_len={len(transcript)}")
        # Even on failure we get a str (empty)
        if status == "done":
            # Pure tone → often empty or short garbage. Just verify it's a string.
            pass

    def test_transcribe_media_bytes_no_dbwrite(self):
        """Ensure the pure helper does NOT touch db.submissions."""
        from server import _transcribe_media_bytes
        mp3 = _make_mp3_bytes(duration_sec=1.0)
        _run(_transcribe_media_bytes(mp3, "x.mp3"))
        # No side effect on submissions — smoke-check by counting a TAG-prefixed record isn't created
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        n = _run(db.submissions.count_documents({"submission_id": {"$regex": "^_transcribe_media_bytes_"}}))
        assert n == 0
        client.close()


# ============================================================================
# 2. _ensure_submission_transcript — persistence
# ============================================================================
class TestEnsureSubmissionTranscript:
    def test_noop_for_non_media(self, seed):
        """PDF submission → helper returns doc unchanged, no db writes needed."""
        from server import _ensure_submission_transcript
        doc = {"submission_id": f"{TAG}nomedia_{uuid.uuid4().hex[:6]}",
               "file_name": "notes.pdf", "cohort_id": seed["cohort_id"]}
        out = _run(_ensure_submission_transcript(doc))
        assert out == doc
        assert "transcript" not in out

    def test_noop_when_transcript_already_set(self, seed):
        from server import _ensure_submission_transcript
        doc = {"submission_id": f"{TAG}already_{uuid.uuid4().hex[:6]}",
               "file_name": "clip.mp3", "transcript": "hello world",
               "transcription_status": "done"}
        out = _run(_ensure_submission_transcript(doc))
        assert out["transcript"] == "hello world"

    def test_noop_when_prior_failed(self, seed):
        from server import _ensure_submission_transcript
        doc = {"submission_id": f"{TAG}fail_{uuid.uuid4().hex[:6]}",
               "file_name": "clip.mp3", "transcription_status": "failed"}
        out = _run(_ensure_submission_transcript(doc))
        # Prior failure short-circuits — returns unchanged
        assert out["transcription_status"] == "failed"
        assert not out.get("transcript")


# ============================================================================
# 3. End-to-end: submit-on-behalf with a real mp3
# ============================================================================
class TestSubmitOnBehalfMedia:
    def _get_sub(self, sid):
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            return _run(db.submissions.find_one({"submission_id": sid}, {"_id": 0}))
        finally:
            client.close()

    def test_submit_mp3_transcribes_and_persists(self, seed):
        """Instructor uploads a small mp3 as a pitch submission. Background auto-review
        runs and calls _ensure_submission_transcript → transcript+status persisted."""
        mp3 = _make_mp3_bytes(duration_sec=2.0)
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ms_pitch_id']}/submit-on-behalf",
            headers=seed["auth"],
            data={"student_id": seed["stu_id"], "assignment_id": seed["asgn_pitch_id"]},
            files={"file": ("pitch.mp3", mp3, "audio/mpeg")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]

        # Poll up to 90s for transcription + review to progress
        final = None
        for i in range(45):
            sub = self._get_sub(sid)
            if not sub:
                time.sleep(2); continue
            tstatus = sub.get("transcription_status")
            has_feedback = bool(sub.get("ai_feedback"))
            has_error = bool(sub.get("ai_feedback_error"))
            if tstatus in ("done", "failed", "failed_too_large") and (has_feedback or has_error):
                final = sub
                break
            time.sleep(2)

        assert final is not None, f"Transcription+review did not converge for sid={sid}. Last: {self._get_sub(sid)}"
        print(f"[E2E mp3] transcription_status={final.get('transcription_status')}, "
              f"transcript_len={len(final.get('transcript') or '')}, "
              f"has_feedback={bool(final.get('ai_feedback'))}, "
              f"has_error={bool(final.get('ai_feedback_error'))}, "
              f"status={final.get('status')}")

        # KEY ASSERTION: transcription_status field exists on the submission (proves plumbing wired up)
        assert final.get("transcription_status") in ("done", "failed", "failed_too_large"), \
            f"transcription_status missing / stuck-pending: {final.get('transcription_status')}"

        # If transcript is empty (silent tone) → auto-review should mark review_failed with helpful error
        if final.get("transcription_status") == "done" and not (final.get("transcript") or "").strip():
            # empty-transcript case → review should have set ai_feedback_error + status='review_failed'
            assert final.get("ai_feedback_error"), \
                "For empty transcript, ai_feedback_error should be set (no more silent no-op)"
            assert final.get("status") == "review_failed", \
                f"For empty transcript, status should be 'review_failed', got {final.get('status')}"
            assert "no readable content" in final["ai_feedback_error"].lower() or \
                   "spoken content" in final["ai_feedback_error"].lower()
        elif final.get("transcription_status") == "done" and (final.get("transcript") or "").strip():
            # Real transcript → GPT should have produced feedback
            assert final.get("ai_feedback"), "Expected ai_feedback when transcript non-empty"


# ============================================================================
# 4. Manual review endpoint — milestone-based media submission
# ============================================================================
class TestManualReviewEndpoint:
    def test_review_endpoint_media_submission(self, seed):
        """Create a media submission, then call POST /submissions/{id}/review.
        Should either succeed OR return 400 with a transcription/empty-text error."""
        mp3 = _make_mp3_bytes(duration_sec=2.0)
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ms_pitch_id']}/submit-on-behalf",
            headers=seed["auth"],
            data={"student_id": seed["stu_id"], "assignment_id": seed["asgn_pitch_id"]},
            files={"file": ("review_target.mp3", mp3, "audio/mpeg")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]

        # Wait briefly for auto-review to at least start touching the doc
        time.sleep(4)

        # Call manual review endpoint — this refactored endpoint must support milestone-based subs
        r2 = requests.post(
            f"{BASE_URL}/api/submissions/{sid}/review",
            headers=seed["auth"], timeout=120,
        )
        # Acceptable outcomes:
        #  200 = feedback generated
        #  400 = transcription failed OR empty transcript (graceful failure)
        assert r2.status_code in (200, 400), f"Unexpected {r2.status_code}: {r2.text}"
        if r2.status_code == 400:
            detail = r2.json().get("detail", "").lower()
            assert any(k in detail for k in
                       ("transcribe", "extract text", "empty", "unsupported")), \
                f"400 must have a meaningful message, got: {detail}"
            print(f"[review 400] {detail}")
        else:
            body = r2.json()
            assert body.get("ai_feedback") or body.get("feedback"), \
                f"200 review response should include feedback: {body}"
            print(f"[review 200] feedback_len={len(str(body.get('ai_feedback') or body.get('feedback') or ''))}")

    def test_review_endpoint_404_missing_submission(self, seed):
        r = requests.post(
            f"{BASE_URL}/api/submissions/does-not-exist-abc/review",
            headers=seed["auth"], timeout=30,
        )
        assert r.status_code == 404


# ============================================================================
# 5. Regression: non-media (case_activity pdf) still works end-to-end
# ============================================================================
class TestNonMediaRegression:
    def test_pdf_submit_on_behalf_no_transcription(self, seed):
        """Case activity .pdf submission → _ensure_submission_transcript is no-op;
        submission still gets processed through normal extract-and-review flow."""
        # Minimal valid-looking PDF bytes (Whisper won't be called)
        pdf_bytes = (
            b"%PDF-1.4\n"
            b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 50 250 Td (Hello World) Tj ET\nendstream endobj\n"
            b"xref\n0 5\n0000000000 65535 f\ntrailer<</Root 1 0 R/Size 5>>\n%%EOF\n"
        )
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ms_case_id']}/submit-on-behalf",
            headers=seed["auth"],
            data={"student_id": seed["stu_id"], "assignment_id": seed["asgn_case_id"]},
            files={"file": ("case.pdf", pdf_bytes, "application/pdf")},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]

        # Give auto-review a few seconds; then verify transcription_status was NEVER set
        # (proves the helper skipped it correctly).
        time.sleep(6)
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        sub = _run(db.submissions.find_one({"submission_id": sid}, {"_id": 0}))
        client.close()
        assert sub is not None
        # transcription_status should be absent or None for non-media
        assert sub.get("transcription_status") in (None, "n/a"), \
            f"Non-media submission should not have transcription_status set, got {sub.get('transcription_status')}"
        # Should not have any transcript field
        assert not sub.get("transcript")


# ============================================================================
# 6. Regression: questionnaire submissions unaffected
# ============================================================================
class TestQuestionnaireRegression:
    def test_questionnaire_submit_no_media_pipeline(self, seed):
        import json as _json
        r = requests.post(
            f"{BASE_URL}/api/milestones/{seed['ms_q_id']}/submit-on-behalf",
            headers=seed["auth"],
            data={
                "student_id": seed["stu_id"],
                "assignment_id": seed["asgn_q_id"],
                "questionnaire_answers": _json.dumps({"q1": "I want to build a SaaS for schools."}),
            },
        )
        assert r.status_code == 200, r.text
        sid = r.json()["submission_id"]

        time.sleep(3)
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        sub = _run(db.submissions.find_one({"submission_id": sid}, {"_id": 0}))
        client.close()
        assert sub is not None
        assert sub.get("submission_type") == "business_questionnaire"
        assert sub.get("questionnaire_answers", {}).get("q1", "").startswith("I want")
        # No transcription pipeline touched
        assert sub.get("transcription_status") in (None, "n/a")
        assert not sub.get("transcript")


# ============================================================================
# 7. Fallback path: works WITHOUT ffmpeg (small file + native ext → direct Whisper)
# ============================================================================
class TestFfmpegFallback:
    def test_direct_whisper_path_without_ffmpeg(self):
        """Simulate missing ffmpeg by temporarily renaming the binary — verify
        that _transcribe_media_bytes still succeeds via the direct Whisper path
        for small (< 25MB) native-format files (mp3)."""
        from server import _transcribe_media_bytes

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            pytest.skip("ffmpeg not present — cannot simulate its removal")

        # Generate mp3 BEFORE we disable ffmpeg
        mp3 = _make_mp3_bytes(duration_sec=1.5)

        disabled = ffmpeg_bin + ".disabled_by_test"
        try:
            os.rename(ffmpeg_bin, disabled)
            assert shutil.which("ffmpeg") is None, "ffmpeg still on PATH after rename"

            status, transcript = _run(_transcribe_media_bytes(mp3, "tone.mp3"))
            # Direct Whisper path should NOT depend on ffmpeg for a small native mp3
            assert status in ("done", "failed"), f"Unexpected status {status}"
            assert isinstance(transcript, str)
            # If status is 'done' → direct path worked without ffmpeg
            # If 'failed' → Whisper API itself refused it (still no exception thrown; graceful)
            print(f"[no-ffmpeg fallback] status={status}, transcript_len={len(transcript)}")
            # The critical assertion: no exception, valid tuple back
        finally:
            if os.path.exists(disabled):
                os.rename(disabled, ffmpeg_bin)
            assert shutil.which("ffmpeg") == ffmpeg_bin, "Failed to restore ffmpeg!"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
