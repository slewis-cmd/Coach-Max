from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Form, Depends, Response, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from bson import ObjectId
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Tuple
import json
import uuid
from datetime import datetime, timezone, timedelta
import aiofiles
import httpx
from PyPDF2 import PdfReader
from docx import Document
import io
import csv
import asyncio
import resend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# GridFS bucket for persistent file storage (survives pod redeploys)
fs_bucket = AsyncIOMotorGridFSBucket(db)

# Create the main app
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Upload directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure Resend
resend.api_key = os.environ.get("RESEND_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL") or "info@theboostpad.org"

# ==================== PLATFORM BRANDING ====================
# Defaults are used when the platform_settings collection is empty (fresh install).
# White-label buyers override these via GET/PUT /api/settings/branding.
DEFAULT_BRANDING = {
    "app_name": "The Boost Pad",
    "ai_persona_name": "Coach Max",
    "primary_color": "#22438E",
    "logo_url": "",
    "favicon_url": "",
    "email_sender_name": "The Boost Pad",
    "tagline": "AI-powered learning coach",
    "ai_system_prompt": "You are {persona}, a friendly, supportive AI tutor for a leadership development course.",
}

_branding_cache = None
_branding_cache_ts = 0

async def get_branding() -> dict:
    """Return the current platform branding config (cached 30s)."""
    global _branding_cache, _branding_cache_ts
    import time
    now = time.time()
    if _branding_cache and (now - _branding_cache_ts) < 30:
        return _branding_cache
    doc = await db.platform_settings.find_one({"_id": "branding"}, {"_id": 0})
    merged = {**DEFAULT_BRANDING, **(doc or {})}
    _branding_cache = merged
    _branding_cache_ts = now
    return merged

def invalidate_branding_cache():
    global _branding_cache, _branding_cache_ts
    _branding_cache = None
    _branding_cache_ts = 0
# Force override if stale resend.dev value is still in env
if "resend.dev" in SENDER_EMAIL:
    SENDER_EMAIL = "info@theboostpad.org"
    logger.warning("Overrode stale resend.dev SENDER_EMAIL with info@theboostpad.org")
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "").lower().strip()
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "").lower().strip()
THINKIFIC_API_KEY = os.environ.get("THINKIFIC_API_KEY", "")
THINKIFIC_SUBDOMAIN = os.environ.get("THINKIFIC_SUBDOMAIN", "")

# Read the external app URL from the frontend .env (Emergent configures this correctly for both preview and production)
APP_BASE_URL = ""
try:
    with open("/app/frontend/.env") as _f:
        for _line in _f:
            if _line.startswith("REACT_APP_BACKEND_URL="):
                APP_BASE_URL = _line.strip().split("=", 1)[1].strip('"').rstrip("/")
                break
except Exception:
    pass
if not APP_BASE_URL:
    APP_BASE_URL = "https://cohort-feedback-hub.preview.emergentagent.com"
logger.info(f"App base URL: {APP_BASE_URL}")

# ==================== EMAIL HELPER ====================

async def send_email_notification(to_email: str, subject: str, html_content: str):
    """Send email notification using Resend"""
    if not resend.api_key:
        logger.warning("Resend API key not configured, skipping email")
        return None
    
    try:
        branding = await get_branding()
        sender_name = branding.get("email_sender_name") or "The Boost Pad"
        params = {
            "from": f"{sender_name} <{SENDER_EMAIL}>",
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }
        # CC admin on all emails for visibility
        if NOTIFICATION_EMAIL and NOTIFICATION_EMAIL.lower() != to_email.lower():
            params["cc"] = [NOTIFICATION_EMAIL]
        
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to_email}: {result.get('id')}")
        return result
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return None


# ==================== TEXT EXTRACTION HELPERS ====================

async def save_bytes_to_gridfs(content: bytes, filename: str) -> str:
    """Persist file bytes to MongoDB GridFS. Returns the gridfs_id as a string."""
    gridfs_id = await fs_bucket.upload_from_stream(filename, content)
    return str(gridfs_id)


async def read_bytes_from_doc(doc: dict) -> bytes:
    """Read file bytes from a doc. Prefers gridfs_id (persistent), falls back to disk file_path (legacy)."""
    gridfs_id = doc.get("gridfs_id")
    if gridfs_id:
        grid_out = await fs_bucket.open_download_stream(ObjectId(gridfs_id))
        return await grid_out.read()
    fp = doc.get("file_path")
    if fp:
        try:
            async with aiofiles.open(fp, "rb") as f:
                return await f.read()
        except FileNotFoundError:
            raise HTTPException(
                status_code=410,
                detail="This file was uploaded before persistent storage was enabled and is no longer available. Please ask the student to resubmit."
            )
    raise HTTPException(status_code=404, detail="File reference missing")


async def delete_file_from_doc(doc: dict) -> None:
    """Delete a file referenced by a doc (GridFS or legacy disk). Silent on failure."""
    gridfs_id = doc.get("gridfs_id")
    if gridfs_id:
        try:
            await fs_bucket.delete(ObjectId(gridfs_id))
        except Exception:
            pass
    fp = doc.get("file_path")
    if fp:
        try:
            os.remove(fp)
        except Exception:
            pass


async def _questionnaire_text_from_doc(doc: dict) -> Optional[str]:
    """Synthesize Q&A text from a questionnaire submission doc, or return None if not applicable."""
    if doc.get("submission_type") != "business_questionnaire" or doc.get("questionnaire_answers") is None:
        return None
    mat = None
    if doc.get("material_id"):
        mat = await db.materials.find_one(
            {"material_id": doc.get("material_id")},
            {"_id": 0, "questionnaire_fields": 1},
        )
    fields = (mat or {}).get("questionnaire_fields") or []
    answers = doc.get("questionnaire_answers") or {}
    if fields:
        return "\n\n".join(
            f"Q: {f.get('label')}\nA: {answers.get(f.get('id'), '') or '(no answer)'}"
            for f in fields
        )
    return "\n\n".join(f"Q: {k}\nA: {v}" for k, v in answers.items())


def _video_transcript_text(doc: dict) -> Optional[str]:
    """Return labeled transcript text for a video material OR a media-file submission, or None if not applicable."""
    # Library video material path
    if doc.get("material_type") == "video":
        transcript = (doc.get("transcript") or "").strip()
        if not transcript:
            return ""
        label = "VIDEO TRANSCRIPT"
        if doc.get("video_url"):
            label += f" ({doc.get('video_url')})"
        return f"[{label}]\n{transcript}"
    # Video/audio submission path (60-second pitch etc.) — transcript is persisted on the submission doc
    if doc.get("submission_id") and _is_media_submission(doc):
        transcript = (doc.get("transcript") or "").strip()
        if not transcript:
            return ""
        return f"[VIDEO/AUDIO TRANSCRIPT]\n{transcript}"
    return None


async def read_file_text(doc_or_path, file_name: str = None) -> str:
    """Read file and extract text. Accepts either a doc dict (preferred) or a legacy (file_path, file_name) pair.
    For video materials, returns the stored Whisper transcript."""
    try:
        if isinstance(doc_or_path, dict):
            doc = doc_or_path
            q_text = await _questionnaire_text_from_doc(doc)
            if q_text is not None:
                return q_text
            v_text = _video_transcript_text(doc)
            if v_text is not None:
                return v_text
            file_bytes = await read_bytes_from_doc(doc)
            return extract_text_from_file(file_bytes, doc.get("file_name", ""))
        # Legacy signature: (file_path, file_name)
        async with aiofiles.open(doc_or_path, "rb") as f:
            file_bytes = await f.read()
        return extract_text_from_file(file_bytes, file_name or "")
    except HTTPException:
        return ""
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        return ""


async def save_uploaded_file(file: UploadFile, prefix: str) -> tuple:
    """Save uploaded file to GridFS. Returns (gridfs_id, filename)."""
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    content = await file.read()
    gridfs_id = await save_bytes_to_gridfs(content, f"{prefix}_{filename}")
    return gridfs_id, filename


WHISPER_MAX_BYTES = 25 * 1024 * 1024  # OpenAI Whisper 25 MB hard limit
WHISPER_NATIVE_EXTS = {"mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"}  # Formats Whisper accepts natively


async def _run_ffmpeg_extract_audio(input_path: str, output_path: str) -> Tuple[bool, str]:
    """Run ffmpeg to extract mono/16kHz/32kbps mp3 audio. Returns (ok, stderr_snippet)."""
    import subprocess
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", input_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", output_path],
            capture_output=True,
            timeout=600,
        )
        if proc.returncode != 0:
            return False, proc.stderr[:500].decode(errors="ignore")
        return True, ""
    except FileNotFoundError:
        return False, "ffmpeg not installed"
    except Exception as e:
        return False, str(e)[:500]


async def _whisper_transcribe_file(path: str) -> str:
    """Send a file path to Whisper. Raises on any error."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise RuntimeError("EMERGENT_LLM_KEY not set")
    from emergentintegrations.llm.openai import OpenAISpeechToText
    stt = OpenAISpeechToText(api_key=api_key)
    with open(path, "rb") as audio_file:
        response = await stt.transcribe(
            file=audio_file,
            model="whisper-1",
            response_format="text",
        )
    return response if isinstance(response, str) else getattr(response, "text", "")


async def _transcribe_media_bytes(file_bytes: bytes, filename: str) -> Tuple[str, str]:
    """Pure helper: transcribe a video/audio blob via ffmpeg (audio extract) + Whisper.
    Falls back to sending the raw file to Whisper when the file is already ≤ 25 MB in a
    Whisper-native format (works even if ffmpeg is missing).
    Returns (status, transcript_text) where status is one of 'done' | 'failed' | 'failed_too_large'.
    No DB writes."""
    import tempfile
    file_ext = (filename or "video.mp4").rsplit(".", 1)[-1].lower()

    # Path 1: Small file + Whisper-native extension → skip ffmpeg entirely (works without ffmpeg)
    if len(file_bytes) <= WHISPER_MAX_BYTES and file_ext in WHISPER_NATIVE_EXTS:
        raw_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as tmp:
                tmp.write(file_bytes)
                raw_path = tmp.name
            transcript_text = await _whisper_transcribe_file(raw_path)
            return "done", (transcript_text or "").strip()
        except Exception as e:
            logger.warning(f"Direct Whisper transcribe failed ({e}); falling through to ffmpeg pipeline")
        finally:
            if raw_path:
                try:
                    os.remove(raw_path)
                except OSError:
                    pass

    # Path 2: ffmpeg pipeline (large file or non-native format)
    with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as vid_tmp:
        vid_tmp.write(file_bytes)
        vid_path = vid_tmp.name
    audio_path = vid_path + ".mp3"
    try:
        ok, err = await _run_ffmpeg_extract_audio(vid_path, audio_path)
        if not ok:
            logger.error(f"ffmpeg pipeline failed: {err}")
            # Last-ditch: try Whisper directly if file is small enough
            if len(file_bytes) <= WHISPER_MAX_BYTES:
                try:
                    transcript_text = await _whisper_transcribe_file(vid_path)
                    return "done", (transcript_text or "").strip()
                except Exception as e:
                    logger.error(f"Fallback direct Whisper also failed: {e}")
            return "failed", ""
        audio_size = os.path.getsize(audio_path)
        if audio_size > WHISPER_MAX_BYTES:
            logger.error(f"Audio too large for Whisper ({audio_size} bytes)")
            return "failed_too_large", ""
        try:
            transcript_text = await _whisper_transcribe_file(audio_path)
        except Exception as e:
            logger.error(f"Whisper API error: {e}")
            return "failed", ""
        return "done", (transcript_text or "").strip()
    except Exception as e:
        logger.exception(f"Transcription pipeline error: {e}")
        return "failed", ""
    finally:
        for p in (vid_path, audio_path):
            try:
                os.remove(p)
            except OSError:
                pass


# Extensions we treat as video/audio submissions eligible for Whisper transcription.
MEDIA_EXTS_FOR_TRANSCRIPTION = {"mp4", "mov", "m4v", "avi", "mkv", "webm", "mp3", "m4a", "wav", "aac", "ogg", "flac"}


def _is_media_submission(doc: dict) -> bool:
    """Return True if the submission file is a video/audio file we can transcribe."""
    fname = (doc.get("file_name") or "").lower()
    ext = fname.rsplit(".", 1)[-1] if "." in fname else ""
    return ext in MEDIA_EXTS_FOR_TRANSCRIPTION


async def _ensure_submission_transcript(doc: dict) -> dict:
    """If the submission is video/audio and lacks a stored transcript, transcribe it now
    (blocking, but only run within background tasks). Persists to db.submissions and returns
    the refreshed doc. If transcription fails, returns the doc unchanged with a
    `transcription_status` field so the caller can decide what to do."""
    if not _is_media_submission(doc):
        return doc
    if (doc.get("transcript") or "").strip():
        return doc
    if doc.get("transcription_status") in ("failed", "failed_too_large"):
        return doc
    try:
        # Mark in-flight so concurrent tasks don't double-transcribe
        await db.submissions.update_one(
            {"submission_id": doc["submission_id"]},
            {"$set": {"transcription_status": "pending"}},
        )
        file_bytes = await read_bytes_from_doc(doc)
        status, transcript_text = await _transcribe_media_bytes(file_bytes, doc.get("file_name") or "")
        update = {"transcription_status": status}
        if status == "done":
            update["transcript"] = transcript_text
        await db.submissions.update_one(
            {"submission_id": doc["submission_id"]},
            {"$set": update},
        )
        doc = {**doc, **update}
        logger.info(f"Submission {doc['submission_id']} transcription: {status}, {len(transcript_text)} chars")
    except Exception as e:
        logger.exception(f"Submission transcription error for {doc.get('submission_id')}: {e}")
        try:
            await db.submissions.update_one(
                {"submission_id": doc["submission_id"]},
                {"$set": {"transcription_status": "failed"}},
            )
        except Exception:
            pass
    return doc


async def transcribe_video_material(material_id: str) -> None:
    """Background task: pull video bytes from GridFS, transcribe via Whisper, save transcript.
    Runs OUT-OF-BAND (fire-and-forget)."""
    try:
        material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
        if not material or not material.get("gridfs_id"):
            return
        file_bytes = await read_bytes_from_doc(material)
        status, transcript_text = await _transcribe_media_bytes(file_bytes, material.get("file_name") or "video.mp4")
        update = {"transcription_status": status}
        if status == "done":
            update["transcript"] = transcript_text
            logger.info(f"Transcribed material {material_id}: {len(transcript_text)} chars")
        await db.materials.update_one({"material_id": material_id}, {"$set": update})
    except Exception as e:
        logger.exception(f"Transcription pipeline error for {material_id}: {e}")
        try:
            await db.materials.update_one(
                {"material_id": material_id},
                {"$set": {"transcription_status": "failed"}}
            )
        except Exception:
            pass


def binary_file_response(file_bytes: bytes, filename: str, inline: bool = False, force_pdf: bool = False) -> Response:
    """Return a Response for binary file downloads with explicit Content-Length.
    Avoids StreamingResponse so Cloudflare/proxies don't see chunked-encoding without a length
    (which can surface as a 520 'unknown response' error in the iframe-preview path)."""
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if force_pdf or ext == "pdf":
        media_type = "application/pdf"
    else:
        media_type = "application/octet-stream"
    disposition = "inline" if inline else "attachment"
    safe_name = (filename or "file").replace('"', '')
    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_name}"',
            "Content-Length": str(len(file_bytes)),
            "Cache-Control": "private, max-age=0, must-revalidate",
            "Accept-Ranges": "none",
            "X-Frame-Options": "SAMEORIGIN",
        }
    )


async def resolve_submission_cohort(material: dict, user: dict, cohort_id: str = None) -> str:
    """Determine which cohort a submission belongs to. Returns cohort_id."""
    if material.get("is_library"):
        if cohort_id:
            cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
        else:
            cohort = await db.cohorts.find_one({
                "student_ids": user["user_id"],
                "cohort_id": {"$in": material.get("cohort_ids", [])}
            }, {"_id": 0})
        if not cohort or user["user_id"] not in cohort.get("student_ids", []):
            raise HTTPException(status_code=403, detail="Not enrolled in this cohort")
        return cohort["cohort_id"], cohort
    else:
        submission_cohort_id = material["cohort_id"]
        cohort = await db.cohorts.find_one({"cohort_id": submission_cohort_id}, {"_id": 0})
        if not cohort or user["user_id"] not in cohort.get("student_ids", []):
            raise HTTPException(status_code=403, detail="Not enrolled in this cohort")
        return submission_cohort_id, cohort


def build_submission_email_html(user_name: str, material: dict, cohort_name: str, is_resubmission: bool) -> str:
    """Build HTML email for submission notification"""
    subject_prefix = "Resubmission" if is_resubmission else "New Submission"
    return f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: {'#E0F2FE' if is_resubmission else '#FDE047'}; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #1A1A1A; margin: 0; font-size: 24px;">{subject_prefix}: Homework</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
            <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                <strong>{user_name}</strong> has {'resubmitted' if is_resubmission else 'submitted'} homework for review.
            </p>
            <div style="background-color: white; border: 1px solid #E5E5E5; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <p style="margin: 0 0 8px 0; color: #5A5A5A; font-size: 14px;">Assignment</p>
                <p style="margin: 0; color: #1A1A1A; font-weight: 500;">{material['title']}</p>
                <p style="margin: 8px 0 0 0; color: #888; font-size: 14px;">Week {material['week_number']} &middot; {cohort_name}</p>
            </div>
            <p style="color: #5A5A5A; font-size: 14px;">
                Log in to The Boost Pad to review this submission and provide AI-powered feedback.
            </p>
        </div>
    </div>
    """


async def build_coach_max_context(submission: dict, material: dict, week_number: Optional[int] = None) -> tuple:
    """Build context strings for Coach Max AI tutor. Returns (submission_text, context_text).
    Works for both legacy material-based and new milestone-based submissions.
    Pass `week_number` explicitly when there is no `material` doc (milestone-based submissions)."""
    submission_text = await read_file_text(submission)
    # Ensure video/audio submission transcripts are resolved (mirrors auto-review path)
    if _is_media_submission(submission) and not (submission_text or "").strip():
        submission = await _ensure_submission_transcript(submission)
        submission_text = await read_file_text(submission)
    
    wk = (material or {}).get("week_number") if material else week_number
    context_text = ""
    if wk is not None:
        context_materials = await db.materials.find({
            "$or": [{"cohort_ids": submission["cohort_id"]}, {"cohort_id": submission["cohort_id"]}],
            "week_number": wk,
            "material_type": {"$in": ["workbook", "case_study", "video"]}
        }, {"_id": 0}).to_list(10)
        # Always include Course-Wide Resources (global library materials linked to this cohort)
        global_materials = await db.materials.find({
            "is_library": True, "is_global": True, "cohort_ids": submission["cohort_id"],
        }, {"_id": 0}).to_list(20)
        for mat in (list(global_materials) + list(context_materials)):
            mat_text = await read_file_text(mat)
            if mat_text:
                context_text += f"\n--- {mat.get('title', '')} ---\n{mat_text[:3000]}"
    
    return submission_text, context_text


async def _cumulative_same_assignment_section(student_id: str, assignment_id: str, current_week: int) -> str:
    """Return the 'PRIOR SUBMISSIONS FOR THIS ASSIGNMENT' section text, or '' if none."""
    if not assignment_id or not current_week or current_week <= 1:
        return ""
    asgn = await db.assignments.find_one(
        {"assignment_id": assignment_id},
        {"_id": 0, "title": 1, "milestones": 1},
    )
    if not asgn:
        return ""
    milestones = asgn.get("milestones") or []
    prior_ms_ids = [
        m.get("milestone_id") for m in milestones
        if m.get("week_number") and m["week_number"] < current_week
    ]
    if not prior_ms_ids:
        return ""
    prior_asgn_subs = await db.submissions.find({
        "student_id": student_id,
        "assignment_id": assignment_id,
        "milestone_id": {"$in": prior_ms_ids},
    }, {"_id": 0}).sort("submitted_at", 1).to_list(50)
    if not prior_asgn_subs:
        return ""
    body = ""
    for s in prior_asgn_subs:
        ms = next((m for m in milestones if m.get("milestone_id") == s.get("milestone_id")), None)
        wk = (ms or {}).get("week_number", "?")
        try:
            sub_text = await read_file_text(s)
            excerpt = (sub_text or "")[:600]
        except Exception:
            excerpt = ""
        fb = (s.get("instructor_feedback") or s.get("ai_feedback") or "")[:400]
        body += f"\nWeek {wk} submission:\n{excerpt}\nFeedback given: {fb}\n"
    header = f"\n--- PRIOR SUBMISSIONS FOR THIS ASSIGNMENT ({asgn.get('title', '')}) ---\n"
    return header + body


async def _cumulative_global_resources_sections(cohort_id: str) -> List[str]:
    """Return one section string per course-wide (is_global=True) material with non-empty text."""
    global_materials = await db.materials.find({
        "is_library": True,
        "is_global": True,
        "cohort_ids": cohort_id,
    }, {"_id": 0}).to_list(20)
    sections: List[str] = []
    for mat in global_materials:
        mat_text = await read_file_text(mat)
        excerpt = mat_text[:1200] if mat_text else ""
        if not excerpt:
            continue
        sections.append(f"\n--- COURSE-WIDE RESOURCE: {mat.get('title', '')} ---\n{excerpt}")
    return sections


async def _cumulative_prior_weeks_sections(student_id: str, cohort_id: str, current_week: int) -> List[str]:
    """Return one section per prior week: material excerpt + student's feedback from that week."""
    prior_materials = await db.materials.find({
        "cohort_ids": cohort_id,
        "week_number": {"$lt": current_week, "$gt": 0},
        "material_type": {"$in": ["workbook", "case_study", "video"]},
    }, {"_id": 0}).sort("week_number", 1).to_list(100)
    # Backwards compat: single cohort_id field
    if not prior_materials:
        prior_materials = await db.materials.find({
            "cohort_id": cohort_id,
            "week_number": {"$lt": current_week},
            "material_type": {"$in": ["workbook", "case_study", "video"]},
        }, {"_id": 0}).sort("week_number", 1).to_list(100)

    prior_hw = await db.materials.find({
        "$or": [{"cohort_ids": cohort_id}, {"cohort_id": cohort_id}],
        "week_number": {"$lt": current_week},
        "material_type": "homework",
    }, {"_id": 0, "material_id": 1, "title": 1, "week_number": 1}).sort("week_number", 1).to_list(50)

    hw_ids = [m["material_id"] for m in prior_hw]
    prior_submissions = await db.submissions.find({
        "student_id": student_id,
        "material_id": {"$in": hw_ids},
    }, {"_id": 0, "material_id": 1, "ai_feedback": 1, "instructor_feedback": 1}).to_list(50)
    sub_by_mat = {s["material_id"]: s for s in prior_submissions}

    sections: List[str] = []
    weeks_seen = set()
    for mat in prior_materials:
        wk = mat.get("week_number")
        if wk in weeks_seen:
            continue
        weeks_seen.add(wk)
        mat_text = await read_file_text(mat)
        excerpt = mat_text[:800] if mat_text else ""
        section = f"\n--- Week {wk}: {mat.get('title', '')} ---\nTopics: {excerpt}"
        for hw in (h for h in prior_hw if h.get("week_number") == wk):
            sub = sub_by_mat.get(hw["material_id"])
            fb = (sub or {}).get("instructor_feedback") or (sub or {}).get("ai_feedback") or ""
            if fb:
                section += f"\nFeedback received: {fb[:600]}"
        sections.append(section)
    return sections


async def build_cumulative_context(student_id: str, cohort_id: str, current_week: int, max_chars: int = 6000, assignment_id: Optional[str] = None) -> str:
    """Build cumulative context from all prior weeks: materials + student submissions + feedback.
    Always includes Course-Wide Resources (is_global=True) regardless of week.
    If assignment_id is given, ALSO includes the student's prior submissions to the SAME assignment
    (used for cumulative feedback on the Kawasaki Deck / iterative 60-Sec Pitch etc.)."""
    parts: List[str] = []
    total_chars = 0

    def _try_append(section: str) -> bool:
        nonlocal total_chars
        if not section:
            return True
        if total_chars + len(section) > max_chars:
            return False
        parts.append(section)
        total_chars += len(section)
        return True

    # 1) Same-assignment progression (highest priority)
    _try_append(await _cumulative_same_assignment_section(student_id, assignment_id, current_week))

    # 2) Course-Wide Resources: always included
    for section in await _cumulative_global_resources_sections(cohort_id):
        if not _try_append(section):
            break

    # 3) If it's Week 1, only global resources apply
    if not current_week or current_week <= 1:
        return "\n".join(parts) if parts else ""

    # 4) Prior weeks: materials + received feedback
    for section in await _cumulative_prior_weeks_sections(student_id, cohort_id, current_week):
        if not _try_append(section):
            break

    return "\n".join(parts) if parts else ""


def get_language_instruction(lang: str) -> str:
    """Return AI prompt instruction for the given language code."""
    if lang == "es":
        return "\n\nIMPORTANT: You MUST respond entirely in Spanish. All feedback, headings, bullet points, and closing remarks must be written in Spanish."
    return ""


def get_feedback_email_strings(lang: str) -> dict:
    """Return localised UI strings for the feedback email."""
    if lang == "es":
        return {
            "heading": "Tu retroalimentacion esta lista!",
            "greeting": "Hola",
            "body": "Tu instructor ha revisado tu envio de",
            "week": "Semana",
            "cta": "Preguntale al Coach Max",
            "cta_sub": "Tienes preguntas sobre tu retroalimentacion? Chatea con Coach Max para orientacion personalizada.",
            "closing": "Sigue con el excelente trabajo!",
        }
    return {
        "heading": "Your Feedback is Ready!",
        "greeting": "Hi",
        "body": "Your instructor has reviewed your submission for",
        "week": "Week",
        "cta": "Ask Coach Max a Question",
        "cta_sub": "Have questions about your feedback? Chat with Coach Max for personalized guidance.",
        "closing": "Keep up the great work!",
    }


def parse_csv_students(content: bytes) -> list:
    """Parse CSV content and return list of {email, name} dicts"""
    try:
        text = content.decode('utf-8')
    except Exception:
        text = content.decode('latin-1')
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        email = row.get("email", "").strip().lower()
        if email:
            rows.append({"email": email, "name": row.get("name", "").strip()})
    return rows

# ==================== MODELS ====================

class User(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "student"  # "instructor" or "student"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str

class Cohort(BaseModel):
    cohort_id: str = Field(default_factory=lambda: f"cohort_{uuid.uuid4().hex[:12]}")
    name: str
    description: Optional[str] = None
    instructor_id: Optional[str] = None
    instructor_ids: List[str] = []
    student_ids: List[str] = []
    invite_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    total_weeks: int = 14
    auto_send_feedback: bool = False  # Self-paced mode: AI feedback goes straight to student, bypassing instructor review
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CohortCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CohortUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    auto_send_feedback: Optional[bool] = None
    total_weeks: Optional[int] = None


# ==================== ASSIGNMENTS (Student-Submittable) ====================
# Assignments are the 4 fixed submittable exercises per cohort (60-Sec Pitch,
# Kawasaki Deck, ShiftSure Case, Business Questionnaire) plus any custom ones.
# Each Assignment has weekly Milestones — one submission slot per week.

class Assignment(BaseModel):
    assignment_id: str = Field(default_factory=lambda: f"asgn_{uuid.uuid4().hex[:12]}")
    cohort_id: str
    # Well-known keys: "60_second_pitch", "10_slide_pitch", "case_activity", "business_questionnaire", "custom"
    assignment_key: str
    title: str
    description: Optional[str] = ""
    submission_type: str  # Same 4 IDs as SUBMISSION_TYPE_CONFIG (file-format profile)
    order: int = 0  # display sort order
    is_active: bool = True
    feedback_template: Optional[str] = ""  # Default rubric across all milestones (milestone override wins)
    drive_folder_url: Optional[str] = ""  # Default drive folder (milestone override wins)
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None  # for submission_type == 'business_questionnaire'
    milestones: List[Dict[str, Any]] = []  # Embedded — see AssignmentMilestone shape below
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Embedded milestone shape (kept as dict for flexibility):
# {
#   "milestone_id": "ms_<hex>",
#   "week_number": 3,
#   "title": "Week 3 - Problem Statement",
#   "description": "",
#   "feedback_template_override": "",     # if set, replaces assignment.feedback_template for this milestone
#   "drive_folder_url_override": "",       # if set, replaces assignment.drive_folder_url for this milestone
#   "is_final_capstone": False,           # True for the "combined deck at end" milestone
#   "due_date": None,
# }


class AssignmentCreate(BaseModel):
    title: str
    submission_type: str
    description: Optional[str] = ""
    assignment_key: Optional[str] = "custom"
    feedback_template: Optional[str] = ""
    drive_folder_url: Optional[str] = ""
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    feedback_template: Optional[str] = None
    drive_folder_url: Optional[str] = None
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None
    order: Optional[int] = None


class MilestonePayload(BaseModel):
    week_number: int
    title: Optional[str] = ""
    description: Optional[str] = ""
    feedback_template_override: Optional[str] = ""
    drive_folder_url_override: Optional[str] = ""
    is_final_capstone: Optional[bool] = False
    due_date: Optional[str] = None


# ==================== END ASSIGNMENTS ====================

class Material(BaseModel):
    material_id: str = Field(default_factory=lambda: f"mat_{uuid.uuid4().hex[:12]}")
    cohort_id: str
    week_number: int
    material_type: str  # "workbook", "case_study", "homework", "video"
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = ""
    gridfs_id: Optional[str] = None
    file_name: str
    uploaded_by: str
    due_date: Optional[str] = None  # ISO date string for homework assignments
    drive_folder_url: Optional[str] = ""  # Google Drive folder URL for homework submissions
    feedback_template: Optional[str] = ""  # Custom AI feedback instructions — overrides the default structure
    submission_type: Optional[str] = None  # One of SUBMISSION_TYPE_IDS or None for generic homework
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None  # For submission_type == 'business_questionnaire'
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# --- Named homework submission types (mirror /app/frontend/src/config/submissionTypes.js) ---
SUBMISSION_TYPE_CONFIG: Dict[str, Dict[str, Any]] = {
    "60_second_pitch":         {"label": "60 Second Pitch",        "extensions": ["mp4", "mov", "m4v", "mp3", "m4a", "wav"], "input_kind": "file"},
    "10_slide_pitch":          {"label": "10 Slide Pitch Deck",    "extensions": ["pdf", "ppt", "pptx"],                    "input_kind": "file"},
    "case_activity":           {"label": "The Case Activity",      "extensions": ["pdf", "doc", "docx", "txt"],             "input_kind": "file"},
    "business_questionnaire":  {"label": "Business Questionnaire", "extensions": [],                                        "input_kind": "form"},
}
SUBMISSION_TYPE_IDS = list(SUBMISSION_TYPE_CONFIG.keys())
DEFAULT_HOMEWORK_EXTENSIONS = ["pdf", "docx", "doc"]


def _parse_questionnaire_fields(raw: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Parse and lightly validate a JSON string of questionnaire fields.
    Accepted per field: {id, label, type in ('text','longtext'), required?}"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="questionnaire_fields must be valid JSON")
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="questionnaire_fields must be a list")
    if len(parsed) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 questionnaire fields allowed")
    cleaned: List[Dict[str, Any]] = []
    seen_ids: set = set()
    for i, f in enumerate(parsed):
        if not isinstance(f, dict):
            raise HTTPException(status_code=400, detail=f"Field {i} must be an object")
        fid = str(f.get("id") or f"q_{i+1}").strip()
        label = str(f.get("label") or "").strip()
        ftype = str(f.get("type") or "text").strip().lower()
        required = bool(f.get("required"))
        if not label:
            raise HTTPException(status_code=400, detail=f"Field {i+1} label is required")
        if len(label) > 300:
            raise HTTPException(status_code=400, detail=f"Field {i+1} label must be 300 characters or less")
        if ftype not in ("text", "longtext"):
            raise HTTPException(status_code=400, detail=f"Field {i+1} type must be 'text' or 'longtext'")
        if fid in seen_ids:
            fid = f"{fid}_{i+1}"
        seen_ids.add(fid)
        cleaned.append({"id": fid, "label": label, "type": ftype, "required": required})
    return cleaned


def _validate_submission_type(submission_type: Optional[str]) -> Optional[str]:
    """Normalize + validate a submission_type value; returns None if empty."""
    if not submission_type:
        return None
    st = submission_type.strip()
    if st == "":
        return None
    if st not in SUBMISSION_TYPE_IDS:
        raise HTTPException(status_code=400, detail=f"submission_type must be one of {SUBMISSION_TYPE_IDS}")
    return st

class Submission(BaseModel):
    submission_id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    material_id: str
    cohort_id: str
    student_id: str
    file_path: Optional[str] = ""
    gridfs_id: Optional[str] = None
    file_name: str
    submission_type: Optional[str] = None  # snapshot of material.submission_type at submit time
    questionnaire_answers: Optional[Dict[str, str]] = None  # For business_questionnaire submissions
    assignment_id: Optional[str] = None  # New model: link to assignment
    milestone_id: Optional[str] = None  # New model: link to specific milestone (week)
    status: str = "pending"  # "pending", "draft", "reviewed", "sent"
    ai_feedback: Optional[str] = None
    instructor_feedback: Optional[str] = None  # Human-in-the-loop: instructor's edited/added feedback
    feedback_sent: bool = False  # Whether feedback has been sent to student
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None  # When feedback was sent to student


class Rubric(BaseModel):
    """A saved AI feedback rubric template that can be reused across homework assignments."""
    rubric_id: str = Field(default_factory=lambda: f"rub_{uuid.uuid4().hex[:12]}")
    name: str
    content: str  # The custom AI feedback instructions
    description: Optional[str] = ""  # Optional short summary
    created_by: str  # user_id of author
    created_by_name: Optional[str] = ""  # display name for UI
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RubricPayload(BaseModel):
    name: str
    content: str
    description: Optional[str] = ""

# ==================== AUTH HELPERS ====================

async def get_current_user(request: Request) -> dict:
    """Extract and validate user from session token"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    if not session_token:
        session_token = request.query_params.get("token")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session = await db.user_sessions.find_one(
        {"session_token": session_token},
        {"_id": 0}
    )
    
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    expires_at = session.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired")
    
    user = await db.users.find_one(
        {"user_id": session["user_id"]},
        {"_id": 0}
    )
    
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    return user

async def require_instructor(request: Request) -> dict:
    """Require instructor or super_admin role"""
    user = await get_current_user(request)
    if user.get("role") not in ["instructor", "super_admin"]:
        raise HTTPException(status_code=403, detail="Instructor access required")
    return user

async def require_super_admin(request: Request) -> dict:
    """Require super_admin role"""
    user = await get_current_user(request)
    if user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user

def is_cohort_manager(user: dict, cohort: dict) -> bool:
    """Check if user can manage a cohort (super_admin or cohort instructor)"""
    if user.get("role") == "super_admin":
        return True
    uid = user.get("user_id")
    return uid in cohort.get("instructor_ids", []) or cohort.get("instructor_id") == uid

# ==================== BRANDING ENDPOINTS ====================

@api_router.get("/settings/branding")
async def get_branding_endpoint():
    """Return current platform branding (public — used by every page on load)."""
    return await get_branding()


@api_router.put("/settings/branding")
async def update_branding(request: Request, user: dict = Depends(require_super_admin)):
    """Update platform branding (super admin only)."""
    payload = await request.json()
    allowed = set(DEFAULT_BRANDING.keys())
    updates = {k: v for k, v in payload.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid branding fields supplied")
    await db.platform_settings.update_one(
        {"_id": "branding"},
        {"$set": updates},
        upsert=True
    )
    invalidate_branding_cache()
    return await get_branding()

# ==================== AUTH ENDPOINTS ====================

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Exchange session_id for session_token"""
    data = await request.json()
    session_id = data.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    
    # Get user data from Emergent Auth
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            if resp.status_code != 200:
                logger.error(f"Auth failed with status {resp.status_code}: {resp.text}")
                raise HTTPException(status_code=401, detail="Invalid session_id")
            user_data = resp.json()
            logger.info(f"Auth successful for: {user_data.get('email')}")
        except httpx.HTTPError as e:
            logger.error(f"Auth HTTP error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")
        except Exception as e:
            logger.error(f"Auth error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Check if this is the first user (make them super_admin)
    user_count = await db.users.count_documents({})
    
    # Check if user exists
    existing_user = await db.users.find_one(
        {"email": user_data["email"]},
        {"_id": 0}
    )
    
    is_new_user = False
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info
        update_fields = {
            "name": user_data["name"],
            "picture": user_data.get("picture")
        }
        # Auto-promote to super_admin if email matches SUPER_ADMIN_EMAIL
        if SUPER_ADMIN_EMAIL and user_data["email"].lower().strip() == SUPER_ADMIN_EMAIL and existing_user.get("role") != "super_admin":
            update_fields["role"] = "super_admin"
            logger.info(f"Auto-promoting {user_data['email']} to super_admin")
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": update_fields}
        )
    else:
        # Create new user
        is_new_user = True
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        
        # First user or matching SUPER_ADMIN_EMAIL becomes super_admin, all others become students
        if user_count == 0 or (SUPER_ADMIN_EMAIL and user_data["email"].lower().strip() == SUPER_ADMIN_EMAIL):
            role = "super_admin"
            logger.info(f"Assigning super_admin role to: {user_data['email']}")
        else:
            role = "student"
            logger.info(f"New user - assigning student role to: {user_data['email']}")
        new_user = {
            "user_id": user_id,
            "email": user_data["email"],
            "name": user_data["name"],
            "picture": user_data.get("picture"),
            "role": role,  # super_admin for first user, student for others
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)
        logger.info(f"Created new user: {user_id} with role: {role}")
    
    # Create session
    session_token = user_data.get("session_token", f"sess_{uuid.uuid4().hex}")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    await db.user_sessions.insert_one({
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    # Get user with role
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    return {"user": user, "session_token": session_token, "is_new_user": is_new_user}

@api_router.get("/auth/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info"""
    return user

@api_router.put("/user/language")
async def set_language_preference(request: Request, user: dict = Depends(get_current_user)):
    """Set user's language preference (en or es)"""
    data = await request.json()
    lang = data.get("language", "en")
    if lang not in ("en", "es"):
        raise HTTPException(status_code=400, detail="Supported languages: en, es")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"language_preference": lang}}
    )
    return {"message": "Language preference updated", "language": lang}

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """Logout user"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header.split(" ")[1]
    if not session_token:
        session_token = request.query_params.get("token")
    
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out"}

@api_router.post("/auth/set-role")
async def set_user_role(request: Request, user: dict = Depends(get_current_user)):
    """Set user role - only super_admin can promote to instructor"""
    data = await request.json()
    role = data.get("role")
    target_user_id = data.get("user_id")  # Optional: for super_admin to set other users' roles
    
    if role not in ["instructor", "student"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    # If trying to set instructor role, must be super_admin
    if role == "instructor":
        if user.get("role") != "super_admin":
            raise HTTPException(status_code=403, detail="Only super admin can promote users to instructor")
    
    # Determine which user to update
    if target_user_id and user.get("role") == "super_admin":
        # Super admin setting another user's role
        update_user_id = target_user_id
    else:
        # User setting their own role (only allowed for student)
        if role == "instructor":
            raise HTTPException(status_code=403, detail="Only super admin can promote users to instructor")
        update_user_id = user["user_id"]
    
    await db.users.update_one(
        {"user_id": update_user_id},
        {"$set": {"role": role}}
    )
    
    return {"message": "Role updated", "role": role}

# ==================== ADMIN MANAGEMENT ENDPOINTS ====================

@api_router.get("/admin/users")
async def get_all_users(user: dict = Depends(require_super_admin)):
    """Get all users (super admin only)"""
    users = await db.users.find({}, {"_id": 0}).to_list(500)
    return users

@api_router.post("/admin/invite-instructor")
async def invite_instructor(request: Request, user: dict = Depends(require_super_admin)):
    """Invite/promote a user to instructor role (super admin only)"""
    data = await request.json()
    email = data.get("email")
    
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    
    # Find user by email
    target_user = await db.users.find_one({"email": email.lower().strip()}, {"_id": 0})
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found. They must sign up first.")
    
    if target_user.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot change super admin role")
    
    if target_user.get("role") == "instructor":
        raise HTTPException(status_code=400, detail="User is already an instructor")
    
    # Promote to instructor
    await db.users.update_one(
        {"user_id": target_user["user_id"]},
        {"$set": {"role": "instructor"}}
    )
    
    # Send notification email
    email_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #E0F2FE; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #075985; margin: 0; font-size: 24px;">You're Now an Instructor!</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
            <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                Hi <strong>{target_user['name'].split()[0]}</strong>,
            </p>
            <p style="color: #5A5A5A; font-size: 14px; margin-bottom: 16px;">
                Great news! <strong>{user['name']}</strong> has promoted you to an instructor on The Boost Pad.
            </p>
            <p style="color: #5A5A5A; font-size: 14px;">
                You can now create cohorts, upload course materials, and review student submissions with AI-powered feedback.
            </p>
            <p style="color: #5A5A5A; font-size: 14px; margin-top: 16px;">
                Log in to get started!
            </p>
        </div>
    </div>
    """
    await send_email_notification(
        target_user["email"],
        "You've Been Promoted to Instructor - The Boost Pad",
        email_html
    )
    
    return {
        "message": f"{target_user['name']} has been promoted to instructor",
        "user": {
            "user_id": target_user["user_id"],
            "name": target_user["name"],
            "email": target_user["email"],
            "role": "instructor"
        }
    }

@api_router.post("/admin/revoke-instructor")
async def revoke_instructor(request: Request, user: dict = Depends(require_super_admin)):
    """Revoke instructor role (super admin only)"""
    data = await request.json()
    user_id = data.get("user_id")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")
    
    target_user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if target_user.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot change super admin role")
    
    if target_user.get("role") != "instructor":
        raise HTTPException(status_code=400, detail="User is not an instructor")
    
    # Demote to student
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"role": "student"}}
    )
    
    return {"message": f"{target_user['name']} has been changed to student"}

@api_router.get("/admin/stats")
async def get_admin_stats(user: dict = Depends(require_super_admin)):
    """Get platform stats (super admin only)"""
    total_users = await db.users.count_documents({})
    instructors = await db.users.count_documents({"role": "instructor"})
    students = await db.users.count_documents({"role": "student"})
    super_admins = await db.users.count_documents({"role": "super_admin"})
    total_cohorts = await db.cohorts.count_documents({})
    total_submissions = await db.submissions.count_documents({})
    
    return {
        "users": {
            "total": total_users,
            "super_admins": super_admins,
            "instructors": instructors,
            "students": students
        },
        "cohorts": total_cohorts,
        "submissions": total_submissions
    }

@api_router.delete("/admin/clear-submissions")
async def clear_all_submissions(user: dict = Depends(require_super_admin)):
    """Clear all homework submissions, files, and tutor chats (super admin only)"""
    # Get all submissions so we can clean up attached files (GridFS + legacy disk)
    submissions = await db.submissions.find({}, {"_id": 0, "file_path": 1, "gridfs_id": 1}).to_list(1000)
    
    deleted_files = 0
    for sub in submissions:
        if sub.get("gridfs_id") or sub.get("file_path"):
            await delete_file_from_doc(sub)
            deleted_files += 1
    
    # Delete from database
    sub_result = await db.submissions.delete_many({})
    chat_result = await db.tutor_chats.delete_many({})
    
    return {
        "message": f"Cleared {sub_result.deleted_count} submissions, {deleted_files} files, and {chat_result.deleted_count} chat sessions",
        "submissions_deleted": sub_result.deleted_count,
        "files_deleted": deleted_files,
        "chats_deleted": chat_result.deleted_count
    }

# ==================== PUBLIC INVITE ENDPOINTS ====================

@api_router.get("/invite/{invite_code}")
async def get_invite_info(invite_code: str):
    """Public endpoint - get cohort info for an invite link"""
    cohort = await db.cohorts.find_one({"invite_code": invite_code}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Invalid invite link")
    
    student_count = len(cohort.get("student_ids", []))
    instructor = await db.users.find_one(
        {"user_id": cohort["instructor_id"]},
        {"_id": 0, "name": 1}
    )
    
    return {
        "cohort_id": cohort["cohort_id"],
        "name": cohort["name"],
        "description": cohort.get("description"),
        "instructor_name": instructor.get("name", "Instructor") if instructor else "Instructor",
        "student_count": student_count
    }

@api_router.post("/invite/{invite_code}/join")
async def join_via_invite(invite_code: str, user: dict = Depends(get_current_user)):
    """Join a cohort using an invite code (authenticated students)"""
    cohort = await db.cohorts.find_one({"invite_code": invite_code}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Invalid invite link")
    
    if user["user_id"] in cohort.get("student_ids", []):
        return {"message": "You're already enrolled in this cohort", "already_enrolled": True, "cohort_id": cohort["cohort_id"]}
    
    # Set role to student if not set
    if not user.get("role"):
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"role": "student"}}
        )
    
    await db.cohorts.update_one(
        {"cohort_id": cohort["cohort_id"]},
        {"$push": {"student_ids": user["user_id"]}}
    )
    
    return {
        "message": f"Welcome to {cohort['name']}!",
        "already_enrolled": False,
        "cohort_id": cohort["cohort_id"]
    }

# ==================== COHORT ENDPOINTS ====================

@api_router.post("/cohorts")
async def create_cohort(cohort_data: CohortCreate, user: dict = Depends(require_instructor)):
    """Create a new cohort (instructor only)"""
    cohort = Cohort(
        name=cohort_data.name,
        description=cohort_data.description,
        instructor_id=user["user_id"],
        instructor_ids=[user["user_id"]]
    )
    
    doc = cohort.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.cohorts.insert_one(doc)

    # Auto-seed the 4 default assignments for the new cohort
    try:
        await _seed_default_assignments_for_cohort(cohort.cohort_id, cohort.total_weeks)
    except Exception as seed_err:
        logger.warning(f"Auto-seed assignments failed for {cohort.cohort_id}: {seed_err}")

    return {"cohort_id": cohort.cohort_id, "message": "Cohort created"}

@api_router.get("/cohorts")
async def get_cohorts(user: dict = Depends(get_current_user)):
    """Get cohorts for current user"""
    if user["role"] in ["instructor", "super_admin"]:
        if user["role"] == "super_admin":
            # Super admin sees all cohorts
            cohorts = await db.cohorts.find({}, {"_id": 0}).to_list(100)
        else:
            cohorts = await db.cohorts.find(
                {"$or": [
                    {"instructor_ids": user["user_id"]},
                    {"instructor_id": user["user_id"]}
                ]},
                {"_id": 0}
            ).to_list(100)
    else:
        cohorts = await db.cohorts.find(
            {"student_ids": user["user_id"]},
            {"_id": 0}
        ).to_list(100)
    
    return cohorts

@api_router.get("/cohorts/{cohort_id}")
async def get_cohort(cohort_id: str, user: dict = Depends(get_current_user)):
    """Get single cohort details"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check access
    if user["role"] in ["instructor", "super_admin"]:
        if user["role"] == "instructor" and not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")
    elif user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get student details if instructor/super_admin
    if user["role"] in ["instructor", "super_admin"]:
        students = await db.users.find(
            {"user_id": {"$in": cohort.get("student_ids", [])}},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1, "picture": 1}
        ).to_list(100)
        cohort["students"] = students
    
    # Add instructor names
    all_instructor_ids = cohort.get("instructor_ids", [])
    if cohort.get("instructor_id") and cohort["instructor_id"] not in all_instructor_ids:
        all_instructor_ids.append(cohort["instructor_id"])
    
    instructors = await db.users.find(
        {"user_id": {"$in": all_instructor_ids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1}
    ).to_list(20)
    cohort["instructors"] = instructors
    cohort["instructor_name"] = ", ".join([i["name"] for i in instructors]) if instructors else None
    cohort["instructor_email"] = instructors[0]["email"] if instructors else None
    
    return cohort

@api_router.put("/cohorts/{cohort_id}")
async def update_cohort(cohort_id: str, update: CohortUpdate, user: dict = Depends(require_instructor)):
    """Update cohort details"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data:
        await db.cohorts.update_one({"cohort_id": cohort_id}, {"$set": update_data})
    
    return {"message": "Cohort updated"}

@api_router.delete("/cohorts/{cohort_id}")
async def delete_cohort(cohort_id: str, user: dict = Depends(require_instructor)):
    """Delete a cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    await db.cohorts.delete_one({"cohort_id": cohort_id})
    await db.materials.delete_many({"cohort_id": cohort_id, "is_library": {"$ne": True}})
    await db.submissions.delete_many({"cohort_id": cohort_id})
    await db.assignments.delete_many({"cohort_id": cohort_id})
    # Unlink library materials from this cohort
    await db.materials.update_many(
        {"is_library": True, "cohort_ids": cohort_id},
        {"$pull": {"cohort_ids": cohort_id}}
    )
    
    return {"message": "Cohort deleted"}

@api_router.post("/cohorts/{cohort_id}/assign-instructor")
async def assign_instructor_to_cohort(cohort_id: str, request: Request, user: dict = Depends(require_super_admin)):
    """Add or remove an instructor from a cohort (super admin only)"""
    data = await request.json()
    instructor_id = data.get("instructor_id")
    action = data.get("action", "add")  # "add" or "remove"
    
    if not instructor_id:
        raise HTTPException(status_code=400, detail="instructor_id required")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    instructor = await db.users.find_one({"user_id": instructor_id}, {"_id": 0})
    if not instructor or instructor.get("role") not in ["instructor", "super_admin"]:
        raise HTTPException(status_code=400, detail="User is not an instructor")
    
    if action == "remove":
        await db.cohorts.update_one(
            {"cohort_id": cohort_id},
            {"$pull": {"instructor_ids": instructor_id}}
        )
        # Update instructor_id if it matches the removed one
        if cohort.get("instructor_id") == instructor_id:
            remaining = [i for i in cohort.get("instructor_ids", []) if i != instructor_id]
            new_primary = remaining[0] if remaining else None
            await db.cohorts.update_one(
                {"cohort_id": cohort_id},
                {"$set": {"instructor_id": new_primary}}
            )
        return {"message": f"{instructor['name']} removed from {cohort['name']}"}
    else:
        await db.cohorts.update_one(
            {"cohort_id": cohort_id},
            {"$addToSet": {"instructor_ids": instructor_id}}
        )
        # Set as primary if first instructor
        if not cohort.get("instructor_id"):
            await db.cohorts.update_one(
                {"cohort_id": cohort_id},
                {"$set": {"instructor_id": instructor_id}}
            )
        return {"message": f"{instructor['name']} assigned to {cohort['name']}"}

@api_router.get("/instructors")
async def list_instructors(user: dict = Depends(require_super_admin)):
    """List all users with instructor or super_admin role"""
    instructors = await db.users.find(
        {"role": {"$in": ["instructor", "super_admin"]}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "role": 1, "picture": 1}
    ).to_list(100)
    return instructors



@api_router.post("/cohorts/{cohort_id}/students")
async def add_student_to_cohort(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Add student to cohort by email. Creates placeholder if not signed up yet, sends invitation email."""
    data = await request.json()
    student_email = data.get("email", "").strip().lower()
    student_name = data.get("name", "").strip()
    
    if not student_email:
        raise HTTPException(status_code=400, detail="Student email required")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Find or create student
    student = await db.users.find_one({"email": student_email}, {"_id": 0})
    is_new = False
    
    if not student:
        # Create placeholder user
        student_id = f"user_{uuid.uuid4().hex[:12]}"
        await db.users.insert_one({
            "user_id": student_id,
            "email": student_email,
            "name": student_name or student_email.split("@")[0],
            "picture": None,
            "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        student = {"user_id": student_id, "name": student_name or student_email.split("@")[0], "email": student_email}
        is_new = True
    
    if student["user_id"] in cohort.get("student_ids", []):
        raise HTTPException(status_code=400, detail="Student already in cohort")
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$push": {"student_ids": student["user_id"]}}
    )
    
    # Send invitation email
    origin = request.headers.get("origin", "")
    app_url = origin or "https://cohort-feedback-hub.preview.emergentagent.com"
    await send_email_notification(
        to_email=student_email,
        subject=f"You've been invited to {cohort['name']}",
        html_content=f"""
        <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
            <h2 style="color: #1A1A1A; font-weight: normal;">Welcome to {cohort['name']}</h2>
            <p style="color: #5A5A5A; line-height: 1.6;">
                Hi {student['name']},
            </p>
            <p style="color: #5A5A5A; line-height: 1.6;">
                You've been invited to join <strong>{cohort['name']}</strong> on The Boost Pad. 
                Sign in to access your course materials, submit homework, and receive personalized feedback.
            </p>
            <p style="text-align: center; margin: 32px 0;">
                <a href="{app_url}" style="background: #1A1A1A; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; font-size: 14px;">
                    Sign In to Get Started
                </a>
            </p>
            <p style="color: #888; font-size: 13px; line-height: 1.6;">
                Use your Google account ({student_email}) to sign in. Your instructor has already enrolled you in the course.
            </p>
        </div>
        """
    )
    
    return {
        "message": f"Student {'invited' if is_new else 'added'} successfully",
        "student": {"user_id": student["user_id"], "name": student["name"], "email": student["email"]},
        "invitation_sent": True
    }

@api_router.delete("/cohorts/{cohort_id}/students/{student_id}")
async def remove_student_from_cohort(cohort_id: str, student_id: str, user: dict = Depends(require_instructor)):
    """Remove student from cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$pull": {"student_ids": student_id}}
    )
    
    return {"message": "Student removed"}

def _build_bulk_invite_email_html(cohort_name: str, student_name: str, email: str, app_url: str) -> str:
    """Compose the HTML body used for bulk-import invitation emails."""
    return f"""
                <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                    <h2 style="color: #1A1A1A; font-weight: normal;">Welcome to {cohort_name}</h2>
                    <p style="color: #5A5A5A; line-height: 1.6;">
                        Hi {student_name},
                    </p>
                    <p style="color: #5A5A5A; line-height: 1.6;">
                        You've been invited to join <strong>{cohort_name}</strong> on The Boost Pad.
                        Sign in to access your course materials, submit homework, and receive personalized feedback.
                    </p>
                    <p style="text-align: center; margin: 32px 0;">
                        <a href="{app_url}" style="background: #1A1A1A; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; font-size: 14px;">
                            Sign In to Get Started
                        </a>
                    </p>
                    <p style="color: #888; font-size: 13px; line-height: 1.6;">
                        Use your Google account ({email}) to sign in.
                    </p>
                </div>
                """


async def _resolve_or_create_bulk_student(email: str, row_name: str) -> Optional[dict]:
    """Return an existing student user, or create a placeholder if a name is provided.
    Returns None when the student does not exist and no name is provided."""
    student = await db.users.find_one({"email": email}, {"_id": 0})
    if student:
        return student
    if not row_name:
        return None
    student_id = f"user_{uuid.uuid4().hex[:12]}"
    await db.users.insert_one({
        "user_id": student_id,
        "email": email,
        "name": row_name,
        "picture": None,
        "role": "student",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"user_id": student_id, "name": row_name, "email": email}


async def _process_bulk_import_row(row: dict, cohort_id: str, cohort: dict, app_url: str) -> Tuple[str, dict, Optional[dict]]:
    """Process one CSV row. Returns (bucket, payload, updated_cohort_or_None) where bucket is one of
    'added' | 'already_enrolled' | 'not_found' | 'errors' | 'skip'."""
    email = row.get("email", "").strip().lower()
    if not email:
        return "skip", {}, None

    try:
        student = await _resolve_or_create_bulk_student(email, row.get("name", "").strip())
        if not student:
            return "not_found", {"email": email}, None

        if student["user_id"] in cohort.get("student_ids", []):
            return "already_enrolled", {"email": email}, None

        await db.cohorts.update_one(
            {"cohort_id": cohort_id},
            {"$push": {"student_ids": student["user_id"]}},
        )
        refreshed = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})

        await send_email_notification(
            to_email=email,
            subject=f"You've been invited to {cohort['name']}",
            html_content=_build_bulk_invite_email_html(
                cohort_name=cohort["name"],
                student_name=student.get("name", "there"),
                email=email,
                app_url=app_url,
            ),
        )
        return "added", {"email": email, "name": student.get("name", "Unknown")}, refreshed
    except Exception as e:
        logger.error(f"Error importing student {email}: {e}")
        return "errors", {"email": email}, None


@api_router.post("/cohorts/{cohort_id}/students/bulk")
async def bulk_import_students(
    cohort_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(require_instructor),
    request: Request = None
):
    """Bulk import students from CSV file and send invitation emails.
    CSV should have columns: email (required), name (optional)
    """
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")

    filename = file.filename or "unnamed"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")

    content = await file.read()
    try:
        text = content.decode('utf-8')
    except Exception:
        text = content.decode('latin-1')

    reader = csv.DictReader(io.StringIO(text))
    results = {"added": [], "already_enrolled": [], "not_found": [], "errors": []}
    origin = request.headers.get("origin", "") if request else ""
    app_url = origin or "https://cohort-feedback-hub.preview.emergentagent.com"

    for row in reader:
        bucket, payload, refreshed_cohort = await _process_bulk_import_row(row, cohort_id, cohort, app_url)
        if bucket == "skip":
            continue
        if bucket in results:
            # 'added' stores dicts, others store just email strings
            results[bucket].append(payload if bucket == "added" else payload["email"])
        if refreshed_cohort:
            cohort = refreshed_cohort

    return {
        "message": f"Import complete: {len(results['added'])} added, {len(results['already_enrolled'])} already enrolled, {len(results['not_found'])} not found",
        "results": results,
    }

@api_router.get("/cohorts/{cohort_id}/students/template")
async def download_student_template(cohort_id: str, user: dict = Depends(require_instructor)):
    """Download CSV template for bulk student import"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    template = "email,name\nstudent1@example.com,John Doe\nstudent2@example.com,Jane Smith\n"
    
    return Response(
        content=template,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_import_template.csv"}
    )

@api_router.post("/cohorts/{cohort_id}/students/invite-all")
async def invite_all_students(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Send invitation emails to all students in a cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    student_ids = cohort.get("student_ids", [])
    if not student_ids:
        raise HTTPException(status_code=400, detail="No students enrolled in this cohort")
    
    students = await db.users.find(
        {"user_id": {"$in": student_ids}},
        {"_id": 0, "email": 1, "name": 1}
    ).to_list(200)
    
    origin = request.headers.get("origin", "")
    app_url = origin or "https://cohort-feedback-hub.preview.emergentagent.com"
    sent_count = 0
    
    for student in students:
        result = await send_email_notification(
            to_email=student["email"],
            subject=f"You've been invited to {cohort['name']}",
            html_content=f"""
            <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <h2 style="color: #1A1A1A; font-weight: normal;">Welcome to {cohort['name']}</h2>
                <p style="color: #5A5A5A; line-height: 1.6;">
                    Hi {student.get('name', 'there')},
                </p>
                <p style="color: #5A5A5A; line-height: 1.6;">
                    You've been invited to join <strong>{cohort['name']}</strong> on The Boost Pad.
                    Sign in to access your course materials, submit homework, and receive personalized feedback.
                </p>
                <p style="text-align: center; margin: 32px 0;">
                    <a href="{app_url}" style="background: #1A1A1A; color: white; padding: 12px 32px; text-decoration: none; border-radius: 8px; font-size: 14px;">
                        Sign In to Get Started
                    </a>
                </p>
                <p style="color: #888; font-size: 13px; line-height: 1.6;">
                    Use your Google account ({student['email']}) to sign in.
                </p>
            </div>
            """
        )
        if result:
            sent_count += 1
    
    return {"message": f"Invitations sent to {sent_count} of {len(students)} students", "sent": sent_count, "total": len(students)}

# ==================== WEEK RELEASE ENDPOINTS ====================

@api_router.post("/cohorts/{cohort_id}/release-week")
async def release_week(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Release a week to make it visible to students"""
    data = await request.json()
    week_number = data.get("week_number")
    if not week_number or not isinstance(week_number, int) or week_number < 1 or week_number > 14:
        raise HTTPException(status_code=400, detail="Invalid week number (1-14)")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    released = cohort.get("released_weeks", [])
    if week_number not in released:
        released.append(week_number)
        released.sort()
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$set": {"released_weeks": released}}
    )
    
    return {"released_weeks": released, "message": f"Week {week_number} released"}

@api_router.post("/cohorts/{cohort_id}/unrelease-week")
async def unrelease_week(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Hide a week from students"""
    data = await request.json()
    week_number = data.get("week_number")
    if not week_number or not isinstance(week_number, int):
        raise HTTPException(status_code=400, detail="Invalid week number")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    released = cohort.get("released_weeks", [])
    if week_number in released:
        released.remove(week_number)
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$set": {"released_weeks": released}}
    )
    
    return {"released_weeks": released, "message": f"Week {week_number} hidden"}

# ==================== MATERIAL ENDPOINTS ====================

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF file"""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        # Try as plain text if PDF parsing fails
        try:
            return file_bytes.decode('utf-8', errors='ignore').strip()
        except Exception:
            return ""

def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from Word document"""
    try:
        doc = Document(io.BytesIO(file_bytes))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        # Try as plain text if DOCX parsing fails
        try:
            return file_bytes.decode('utf-8', errors='ignore').strip()
        except Exception:
            return ""

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract text from file based on extension"""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    text = ""
    
    if ext == "pdf":
        text = extract_text_from_pdf(file_bytes)
    elif ext in ["docx", "doc"]:
        text = extract_text_from_docx(file_bytes)
    else:
        try:
            text = file_bytes.decode('utf-8', errors='ignore').strip()
        except (UnicodeDecodeError, AttributeError):
            text = ""
    
    # If still empty, try plain text as fallback
    if not text:
        try:
            text = file_bytes.decode('utf-8', errors='ignore').strip()
        except (UnicodeDecodeError, AttributeError):
            text = ""
    
    return text

@api_router.post("/cohorts/{cohort_id}/materials")
async def upload_material(
    cohort_id: str,
    week_number: int,
    material_type: str,
    title: str,
    file: UploadFile = File(...),
    description: str = "",
    due_date: str = "",
    drive_folder_url: str = "",
    feedback_template: str = "",
    submission_type: str = "",
    questionnaire_fields: str = "",
    user: dict = Depends(require_instructor)
):
    """Upload course material (workbook, case study, or homework assignment)"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if material_type not in ["workbook", "case_study", "homework"]:
        raise HTTPException(status_code=400, detail="Invalid material type")
    
    # Validate file type
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    
    # Save file to GridFS (persistent across redeploys)
    material_id = f"mat_{uuid.uuid4().hex[:12]}"
    content = await file.read()
    gridfs_id = await save_bytes_to_gridfs(content, f"{material_id}_{filename}")
    
    # Create material record
    material = Material(
        material_id=material_id,
        cohort_id=cohort_id,
        week_number=week_number,
        material_type=material_type,
        title=title,
        description=description,
        file_path="",
        gridfs_id=gridfs_id,
        file_name=filename,
        uploaded_by=user["user_id"],
        due_date=due_date if due_date else None,
        drive_folder_url=_validate_drive_url(drive_folder_url) if material_type == "homework" else "",
        feedback_template=(feedback_template or "").strip() if material_type == "homework" else "",
        submission_type=_validate_submission_type(submission_type) if material_type == "homework" else None,
        questionnaire_fields=_parse_questionnaire_fields(questionnaire_fields) if (material_type == "homework" and _validate_submission_type(submission_type) == "business_questionnaire") else None,
    )
    
    doc = material.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.materials.insert_one(doc)
    
    return {"material_id": material_id, "message": "Material uploaded"}


def _validate_drive_url(raw: str) -> str:
    """Validate + normalize a Drive-folder-style URL. Empty string is allowed (clears the link).
    Rejects non-http(s) schemes and clearly invalid URLs (e.g. bare 'https://')."""
    if not raw:
        return ""
    raw = raw.strip()
    if not raw:
        return ""
    from urllib.parse import urlparse
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="drive_folder_url must be a valid http(s) URL")
    return raw


@api_router.put("/materials/{material_id}/drive-link")
async def update_material_drive_link(material_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Attach or clear a Google Drive folder URL for a homework material."""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    if material.get("material_type") != "homework":
        raise HTTPException(status_code=400, detail="Drive folder URLs are only supported on homework materials")
    
    # Access control: cohort managers OR super admin
    if user.get("role") != "super_admin":
        cohort_id = material.get("cohort_id")
        if material.get("is_library"):
            # library material: any instructor who manages ANY assigned cohort may edit
            allowed = False
            for cid in material.get("cohort_ids", []):
                c = await db.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
                if c and is_cohort_manager(user, c):
                    allowed = True
                    break
            if not allowed:
                raise HTTPException(status_code=403, detail="Access denied")
        elif cohort_id:
            cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
            if not cohort or not is_cohort_manager(user, cohort):
                raise HTTPException(status_code=403, detail="Access denied")
    
    data = await request.json()
    raw = _validate_drive_url(data.get("drive_folder_url") or "")
    
    await db.materials.update_one(
        {"material_id": material_id},
        {"$set": {"drive_folder_url": raw}}
    )
    return {"material_id": material_id, "drive_folder_url": raw, "message": "Drive link updated"}


@api_router.put("/materials/{material_id}/feedback-template")
async def update_material_feedback_template(material_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Attach or clear custom AI feedback instructions for a homework material.
    An empty string restores the default rubric ("3 things you did well / 3 areas to improve")."""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    if material.get("material_type") != "homework":
        raise HTTPException(status_code=400, detail="Custom AI feedback instructions are only supported on homework materials")

    # Access control: cohort managers OR super admin (same rules as drive-link)
    if user.get("role") != "super_admin":
        cohort_id = material.get("cohort_id")
        if material.get("is_library"):
            allowed = False
            for cid in material.get("cohort_ids", []):
                c = await db.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
                if c and is_cohort_manager(user, c):
                    allowed = True
                    break
            # Library material not yet assigned — allow any instructor who owns it OR admin
            if not allowed and material.get("uploaded_by") != user["user_id"]:
                raise HTTPException(status_code=403, detail="Access denied")
        elif cohort_id:
            cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
            if not cohort or not is_cohort_manager(user, cohort):
                raise HTTPException(status_code=403, detail="Access denied")

    data = await request.json()
    tpl = (data.get("feedback_template") or "").strip()

    await db.materials.update_one(
        {"material_id": material_id},
        {"$set": {"feedback_template": tpl}}
    )
    return {"material_id": material_id, "feedback_template": tpl, "message": "AI feedback instructions updated"}


# ==================== RUBRIC LIBRARY ====================

@api_router.get("/rubrics")
async def list_rubrics(user: dict = Depends(require_instructor)):
    """Every instructor + super_admin sees every rubric (org-shared library)."""
    docs = await db.rubrics.find({}, {"_id": 0}).sort("updated_at", -1).to_list(length=1000)
    for d in docs:
        d["can_edit"] = (user.get("role") == "super_admin") or (d.get("created_by") == user["user_id"])
    return docs


RUBRIC_NAME_MAX = 200
RUBRIC_CONTENT_MAX = 8000
RUBRIC_DESC_MAX = 500


def _validate_rubric_payload(payload: "RubricPayload") -> tuple[str, str, str]:
    name = (payload.name or "").strip()
    content = (payload.content or "").strip()
    desc = (payload.description or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not content:
        raise HTTPException(status_code=400, detail="Rubric content is required")
    if len(name) > RUBRIC_NAME_MAX:
        raise HTTPException(status_code=400, detail=f"Name must be {RUBRIC_NAME_MAX} characters or less")
    if len(content) > RUBRIC_CONTENT_MAX:
        raise HTTPException(status_code=400, detail=f"Content must be {RUBRIC_CONTENT_MAX} characters or less")
    if len(desc) > RUBRIC_DESC_MAX:
        raise HTTPException(status_code=400, detail=f"Description must be {RUBRIC_DESC_MAX} characters or less")
    return name, content, desc


@api_router.post("/rubrics")
async def create_rubric(payload: RubricPayload, user: dict = Depends(require_instructor)):
    name, content, desc = _validate_rubric_payload(payload)
    rubric = Rubric(
        name=name,
        content=content,
        description=desc,
        created_by=user["user_id"],
        created_by_name=user.get("name") or user.get("email") or "",
    )
    await db.rubrics.insert_one(rubric.dict())
    out = rubric.dict()
    out["can_edit"] = True
    return out


@api_router.put("/rubrics/{rubric_id}")
async def update_rubric(rubric_id: str, payload: RubricPayload, user: dict = Depends(require_instructor)):
    doc = await db.rubrics.find_one({"rubric_id": rubric_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Rubric not found")
    if user.get("role") != "super_admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the author or a super admin can edit this rubric")

    name, content, desc = _validate_rubric_payload(payload)

    await db.rubrics.update_one(
        {"rubric_id": rubric_id},
        {"$set": {
            "name": name,
            "content": content,
            "description": desc,
            "updated_at": datetime.now(timezone.utc),
        }}
    )
    updated = await db.rubrics.find_one({"rubric_id": rubric_id}, {"_id": 0})
    updated["can_edit"] = True
    return updated


@api_router.delete("/rubrics/{rubric_id}")
async def delete_rubric(rubric_id: str, user: dict = Depends(require_instructor)):
    doc = await db.rubrics.find_one({"rubric_id": rubric_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Rubric not found")
    if user.get("role") != "super_admin" and doc.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the author or a super admin can delete this rubric")
    await db.rubrics.delete_one({"rubric_id": rubric_id})
    return {"rubric_id": rubric_id, "message": "Rubric deleted"}


# ==================== ASSIGNMENTS (Per-Cohort Submittable Exercises) ====================

DEFAULT_ASSIGNMENT_SEEDS: List[Dict[str, Any]] = [
    {
        "assignment_key": "60_second_pitch",
        "title": "60-Second Elevator Pitch",
        "submission_type": "60_second_pitch",
        "description": "Weekly refinement of your elevator pitch. Upload a short (30-90s) video or audio clip.",
        "order": 0,
    },
    {
        "assignment_key": "10_slide_pitch",
        "title": "Kawasaki 10-Slide Pitch Deck",
        "submission_type": "10_slide_pitch",
        "description": "1-2 slides per week following the Kawasaki 10-slide framework, with a final consolidated deck at the end.",
        "order": 1,
    },
    {
        "assignment_key": "case_activity",
        "title": "The ShiftSure Case Activity",
        "submission_type": "case_activity",
        "description": "Weekly written response applying the ShiftSure case framework.",
        "order": 2,
    },
    {
        "assignment_key": "business_questionnaire",
        "title": "Your Business Questionnaire",
        "submission_type": "business_questionnaire",
        "description": "Weekly structured questions about your business.",
        "order": 3,
    },
]


# Meaningful, curriculum-aware milestone titles for the 4 default assignments.
# Indexed by 1-based week number; weeks beyond the mapped range fall back to "Week N".
MILESTONE_TITLE_MAP: Dict[str, Dict[int, str]] = {
    "60_second_pitch": {
        1:  "Week 1 — First Draft: The Hook",
        2:  "Week 2 — Sharpen the Problem",
        3:  "Week 3 — Nail the Solution",
        4:  "Week 4 — Who is it for? (Target Audience)",
        5:  "Week 5 — Why now? (Timing & Urgency)",
        6:  "Week 6 — Traction & Proof",
        7:  "Week 7 — The Ask",
        8:  "Week 8 — Delivery & Confidence",
        9:  "Week 9 — Live Practice",
        10: "Week 10 — Investor-Ready Pitch",
        11: "Week 11 — Refinement",
        12: "Week 12 — Peer Feedback Round",
        13: "Week 13 — Polish Pass",
        14: "Week 14 — Final Pitch",
    },
    "10_slide_pitch": {
        1:  "Week 1 — Slide 1: Title & Vision",
        2:  "Week 2 — Slide 2: Problem",
        3:  "Week 3 — Slide 3: Value Proposition",
        4:  "Week 4 — Slide 4: Underlying Magic",
        5:  "Week 5 — Slide 5: Business Model",
        6:  "Week 6 — Slide 6: Go-to-Market",
        7:  "Week 7 — Slide 7: Competitive Analysis",
        8:  "Week 8 — Slide 8: Team",
        9:  "Week 9 — Slide 9: Financial Projections",
        10: "Week 10 — Slide 10: Status & Timeline",
        11: "Week 11 — Iterate on Slides 1-5",
        12: "Week 12 — Iterate on Slides 6-10",
        13: "Week 13 — Design & Polish Pass",
        14: "Week 14 — Final Consolidated Deck",
    },
    "case_activity": {
        1:  "Week 1 — Case Introduction",
        2:  "Week 2 — Situation Analysis",
        3:  "Week 3 — Root Cause Diagnosis",
        4:  "Week 4 — Stakeholder Map",
        5:  "Week 5 — Options & Trade-offs",
        6:  "Week 6 — Recommendation",
        7:  "Week 7 — Implementation Plan",
        8:  "Week 8 — Risks & Mitigations",
        9:  "Week 9 — Success Metrics",
        10: "Week 10 — Communication Plan",
        11: "Week 11 — Peer Case Review",
        12: "Week 12 — Refinement",
        13: "Week 13 — Executive Summary",
        14: "Week 14 — Final Case Write-up",
    },
    "business_questionnaire": {
        1:  "Week 1 — Business Foundations",
        2:  "Week 2 — Market & Customer",
        3:  "Week 3 — Value Proposition",
        4:  "Week 4 — Revenue Model",
        5:  "Week 5 — Cost Structure",
        6:  "Week 6 — Sales & Distribution",
        7:  "Week 7 — Operations & Delivery",
        8:  "Week 8 — Team & Roles",
        9:  "Week 9 — Financial Projections",
        10: "Week 10 — Metrics & KPIs",
        11: "Week 11 — Risks & Assumptions",
        12: "Week 12 — Growth Strategy",
        13: "Week 13 — Reflection & Iteration",
        14: "Week 14 — Investor-Ready Summary",
    },
}


def _default_milestone_title(assignment_key: str, week_number: int, is_capstone: bool = False) -> str:
    if is_capstone:
        capstone_titles = {
            "10_slide_pitch": f"Week {week_number} — Final Consolidated Deck",
            "60_second_pitch": f"Week {week_number} — Final Pitch",
            "case_activity": f"Week {week_number} — Final Case Write-up",
            "business_questionnaire": f"Week {week_number} — Investor-Ready Summary",
        }
        if assignment_key in capstone_titles:
            return capstone_titles[assignment_key]
    mapping = MILESTONE_TITLE_MAP.get(assignment_key, {})
    return mapping.get(week_number) or f"Week {week_number}"


def _make_milestone(week_number: int, assignment_key: str = "", is_capstone: bool = False) -> Dict[str, Any]:
    title = _default_milestone_title(assignment_key, week_number, is_capstone)
    return {
        "milestone_id": f"ms_{uuid.uuid4().hex[:12]}",
        "week_number": week_number,
        "title": title,
        "description": "",
        "feedback_template_override": "",
        "drive_folder_url_override": "",
        "is_final_capstone": bool(is_capstone),
        "due_date": None,
    }


def _build_default_milestones(assignment_key: str, total_weeks: int) -> List[Dict[str, Any]]:
    weeks = max(1, min(52, total_weeks or 14))
    milestones = [_make_milestone(w, assignment_key=assignment_key) for w in range(1, weeks + 1)]
    if assignment_key == "10_slide_pitch":
        milestones[-1] = _make_milestone(weeks, assignment_key=assignment_key, is_capstone=True)
    return milestones


async def _seed_default_assignments_for_cohort(cohort_id: str, total_weeks: int = 14) -> int:
    """Idempotent: seed the 4 default assignments if this cohort has none yet."""
    existing = await db.assignments.count_documents({"cohort_id": cohort_id})
    if existing > 0:
        return 0
    docs = []
    for seed in DEFAULT_ASSIGNMENT_SEEDS:
        asgn = Assignment(
            cohort_id=cohort_id,
            assignment_key=seed["assignment_key"],
            title=seed["title"],
            description=seed["description"],
            submission_type=seed["submission_type"],
            order=seed["order"],
            milestones=_build_default_milestones(seed["assignment_key"], total_weeks),
        )
        docs.append(asgn.dict())
    if docs:
        await db.assignments.insert_many(docs)
    return len(docs)


@api_router.get("/cohorts/{cohort_id}/assignments")
async def list_assignments(cohort_id: str, user: dict = Depends(get_current_user)):
    """List assignments for a cohort. Auto-seeds the 4 defaults if none exist yet."""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    # Access control: super_admin, cohort manager, or enrolled student
    if user.get("role") != "super_admin":
        is_manager = is_cohort_manager(user, cohort)
        is_enrolled = user["user_id"] in (cohort.get("student_ids") or [])
        if not (is_manager or is_enrolled):
            raise HTTPException(status_code=403, detail="Access denied")

    if user.get("role") in ("super_admin", "instructor"):
        await _seed_default_assignments_for_cohort(cohort_id, cohort.get("total_weeks", 14))

    docs = await db.assignments.find({"cohort_id": cohort_id}, {"_id": 0}).sort("order", 1).to_list(length=100)
    return docs


@api_router.post("/cohorts/{cohort_id}/assignments")
async def create_custom_assignment(cohort_id: str, payload: AssignmentCreate, user: dict = Depends(require_instructor)):
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    if payload.submission_type not in SUBMISSION_TYPE_IDS:
        raise HTTPException(status_code=400, detail=f"submission_type must be one of {SUBMISSION_TYPE_IDS}")

    max_order = await db.assignments.count_documents({"cohort_id": cohort_id})
    asgn = Assignment(
        cohort_id=cohort_id,
        assignment_key=payload.assignment_key or "custom",
        title=payload.title.strip(),
        description=(payload.description or "").strip(),
        submission_type=payload.submission_type,
        order=max_order,
        feedback_template=(payload.feedback_template or "").strip(),
        drive_folder_url=_validate_drive_url(payload.drive_folder_url or ""),
        questionnaire_fields=payload.questionnaire_fields if payload.submission_type == "business_questionnaire" else None,
        milestones=_build_default_milestones(payload.assignment_key or "custom", cohort.get("total_weeks", 14)),
    )
    await db.assignments.insert_one(asgn.dict())
    return asgn.dict()


@api_router.put("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, payload: AssignmentUpdate, user: dict = Depends(require_instructor)):
    asgn = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found")
    cohort = await db.cohorts.find_one({"cohort_id": asgn["cohort_id"]}, {"_id": 0})
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    updates: Dict[str, Any] = {}
    for field in ("title", "description", "is_active", "feedback_template", "questionnaire_fields", "order"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = val
    if payload.drive_folder_url is not None:
        updates["drive_folder_url"] = _validate_drive_url(payload.drive_folder_url)
    if updates:
        updates["updated_at"] = datetime.now(timezone.utc)
        await db.assignments.update_one({"assignment_id": assignment_id}, {"$set": updates})
    updated = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    return updated


@api_router.delete("/assignments/{assignment_id}")
async def delete_assignment(assignment_id: str, user: dict = Depends(require_instructor)):
    asgn = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found")
    cohort = await db.cohorts.find_one({"cohort_id": asgn["cohort_id"]}, {"_id": 0})
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    # Soft-delete: mark inactive rather than destroy submission history
    await db.assignments.update_one(
        {"assignment_id": assignment_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"assignment_id": assignment_id, "message": "Assignment deactivated"}


@api_router.put("/assignments/{assignment_id}/milestones/{milestone_id}")
async def update_milestone(assignment_id: str, milestone_id: str, payload: MilestonePayload, user: dict = Depends(require_instructor)):
    asgn = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found")
    cohort = await db.cohorts.find_one({"cohort_id": asgn["cohort_id"]}, {"_id": 0})
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    milestones = list(asgn.get("milestones") or [])
    idx = next((i for i, m in enumerate(milestones) if m.get("milestone_id") == milestone_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Milestone not found")

    milestones[idx] = {
        **milestones[idx],
        "week_number": payload.week_number,
        "title": (payload.title or milestones[idx].get("title", "")).strip(),
        "description": (payload.description or "").strip(),
        "feedback_template_override": (payload.feedback_template_override or "").strip(),
        "drive_folder_url_override": _validate_drive_url(payload.drive_folder_url_override or ""),
        "is_final_capstone": bool(payload.is_final_capstone),
        "due_date": payload.due_date,
    }
    await db.assignments.update_one(
        {"assignment_id": assignment_id},
        {"$set": {"milestones": milestones, "updated_at": datetime.now(timezone.utc)}}
    )
    return {"assignment_id": assignment_id, "milestone_id": milestone_id, "message": "Milestone updated"}


@api_router.get("/submit-link/a/{assignment_id}/w/{week_number}")
async def resolve_assignment_submit_link(assignment_id: str, week_number: int, cohort_id: str = None):
    """Stable Thinkific link resolver — returns the milestone + assignment metadata for a given
    assignment + week. Public (no auth) so Thinkific-embedded links show the submit page to
    anyone who arrives; auth + enrollment is still enforced on the actual submit POST."""
    asgn = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    if not asgn or not asgn.get("is_active", True):
        raise HTTPException(status_code=404, detail="Assignment not found")
    milestone = next((m for m in (asgn.get("milestones") or []) if m.get("week_number") == week_number), None)
    if not milestone:
        raise HTTPException(status_code=404, detail=f"No milestone for week {week_number} on this assignment")
    return {
        "assignment_id": assignment_id,
        "milestone_id": milestone["milestone_id"],
        "cohort_id": asgn["cohort_id"],
        "assignment": {
            "assignment_id": asgn["assignment_id"],
            "title": asgn.get("title"),
            "description": asgn.get("description"),
            "submission_type": asgn.get("submission_type"),
            "feedback_template": asgn.get("feedback_template"),
            "drive_folder_url": asgn.get("drive_folder_url"),
            "questionnaire_fields": asgn.get("questionnaire_fields") or [],
        },
        "milestone": milestone,
    }


@api_router.post("/admin/migrate-to-assignments")
async def migrate_to_assignments(user: dict = Depends(require_super_admin)):
    """One-time migration: seed 4 default assignments in every cohort, move existing
    homework materials + submissions under 'Your Business Questionnaire'. Idempotent."""
    stats = {"cohorts_seeded": 0, "milestones_created": 0, "submissions_linked": 0, "materials_archived": 0}

    cohorts = await db.cohorts.find({}, {"_id": 0}).to_list(length=1000)
    for c in cohorts:
        seeded = await _seed_default_assignments_for_cohort(c["cohort_id"], c.get("total_weeks", 14))
        if seeded:
            stats["cohorts_seeded"] += 1

        # Move existing homework materials → questionnaire assignment milestones
        qn = await db.assignments.find_one({"cohort_id": c["cohort_id"], "assignment_key": "business_questionnaire"}, {"_id": 0})
        if not qn:
            continue

        existing_homework = await db.materials.find({
            "cohort_id": c["cohort_id"],
            "material_type": "homework",
            "$or": [{"migrated_to_assignment": {"$exists": False}}, {"migrated_to_assignment": False}],
        }, {"_id": 0}).to_list(length=500)

        milestones = list(qn.get("milestones") or [])
        for mat in existing_homework:
            wk = mat.get("week_number") or 1
            # Ensure a milestone exists for this week; if it does, reuse; else append
            ms = next((m for m in milestones if m.get("week_number") == wk), None)
            if not ms:
                ms = _make_milestone(wk, assignment_key="business_questionnaire")
                ms["title"] = mat.get("title") or ms["title"]
                milestones.append(ms)
                stats["milestones_created"] += 1
            elif mat.get("title") and (not ms.get("title") or ms.get("title", "").startswith("Week ")):
                ms["title"] = mat["title"]
            # Reassign submissions to this milestone
            reassigned = await db.submissions.update_many(
                {"material_id": mat["material_id"]},
                {"$set": {
                    "assignment_id": qn["assignment_id"],
                    "milestone_id": ms["milestone_id"],
                    "submission_type": "business_questionnaire",
                }}
            )
            stats["submissions_linked"] += reassigned.modified_count
            # Archive the material
            await db.materials.update_one(
                {"material_id": mat["material_id"]},
                {"$set": {"migrated_to_assignment": True, "migrated_at": datetime.now(timezone.utc)}}
            )
            stats["materials_archived"] += 1

        # Persist updated milestones (sorted by week)
        milestones.sort(key=lambda m: (m.get("week_number") or 0, 1 if m.get("is_final_capstone") else 0))
        await db.assignments.update_one(
            {"assignment_id": qn["assignment_id"]},
            {"$set": {"milestones": milestones, "updated_at": datetime.now(timezone.utc)}}
        )

    return {"message": "Migration complete", **stats}


@api_router.post("/admin/regenerate-milestone-titles")
async def regenerate_milestone_titles(user: dict = Depends(require_super_admin)):
    """Idempotent back-fill: replace milestone titles that match the literal pattern
    'Week N' or 'Week N — Final Deck' with the curriculum-aware default title for that
    assignment_key + week. Titles that have been customized by an instructor are left alone."""
    import re
    week_re = re.compile(r"^\s*Week\s+\d+(?:\s+—\s+Final Deck)?\s*$")
    stats = {"assignments_scanned": 0, "milestones_renamed": 0}
    assignments = await db.assignments.find({}, {"_id": 0}).to_list(length=5000)
    for a in assignments:
        stats["assignments_scanned"] += 1
        milestones = list(a.get("milestones") or [])
        changed = False
        for m in milestones:
            current = (m.get("title") or "").strip()
            if not current or week_re.match(current):
                new_title = _default_milestone_title(
                    a.get("assignment_key", ""),
                    m.get("week_number") or 1,
                    bool(m.get("is_final_capstone")),
                )
                if new_title != current:
                    m["title"] = new_title
                    changed = True
                    stats["milestones_renamed"] += 1
        if changed:
            await db.assignments.update_one(
                {"assignment_id": a["assignment_id"]},
                {"$set": {"milestones": milestones, "updated_at": datetime.now(timezone.utc)}}
            )
    return {"message": "Milestone titles regenerated", **stats}


# ==================== END ASSIGNMENTS ====================


# ==================== ASSIGNMENT TEMPLATES ====================
# Reusable snapshots of an assignment (title, description, rubric, drive link,
# questionnaire, and all milestones with their overrides) that instructors can
# hydrate into new cohorts. Milestone weeks can be REMAPPED at apply time so a
# 14-week template can be reshaped into an 8-week cohort etc.

class AssignmentTemplate(BaseModel):
    template_id: str = Field(default_factory=lambda: f"tpl_{uuid.uuid4().hex[:12]}")
    name: str
    description: Optional[str] = ""
    submission_type: str
    feedback_template: Optional[str] = ""
    drive_folder_url: Optional[str] = ""
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None
    milestones: List[Dict[str, Any]] = []
    created_by: str
    created_by_name: Optional[str] = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssignmentTemplatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    submission_type: Optional[str] = None
    feedback_template: Optional[str] = None
    drive_folder_url: Optional[str] = None
    questionnaire_fields: Optional[List[Dict[str, Any]]] = None
    milestones: Optional[List[Dict[str, Any]]] = None


class ApplyTemplatePayload(BaseModel):
    week_map: Optional[Dict[str, Optional[int]]] = None  # {template_milestone_id: target_week | null (skip)}
    replace_existing_by_type: Optional[bool] = False
    title_override: Optional[str] = None


def _normalize_milestone_shape(m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "milestone_id": m.get("milestone_id") or f"ms_{uuid.uuid4().hex[:12]}",
        "week_number": int(m.get("week_number", 1)),
        "title": m.get("title", "") or "",
        "description": m.get("description", "") or "",
        "feedback_template_override": m.get("feedback_template_override", "") or "",
        "drive_folder_url_override": m.get("drive_folder_url_override", "") or "",
        "is_final_capstone": bool(m.get("is_final_capstone")),
        "due_date": m.get("due_date"),
    }


def _clone_milestones_from_template(
    tpl_milestones: List[Dict[str, Any]],
    week_map: Optional[Dict[str, Optional[int]]] = None,
) -> List[Dict[str, Any]]:
    """Clone milestones; apply week remap; generate fresh milestone_ids."""
    week_map = week_map or {}
    out: List[Dict[str, Any]] = []
    for m in (tpl_milestones or []):
        tpl_ms_id = m.get("milestone_id")
        if tpl_ms_id in week_map:
            target_week = week_map[tpl_ms_id]
        else:
            target_week = m.get("week_number")
        if target_week is None:
            continue
        try:
            wk = int(target_week)
        except Exception:
            continue
        cloned = _normalize_milestone_shape({**m, "week_number": wk})
        cloned["milestone_id"] = f"ms_{uuid.uuid4().hex[:12]}"
        out.append(cloned)
    out.sort(key=lambda x: (x.get("week_number") or 0, 1 if x.get("is_final_capstone") else 0))
    return out


@api_router.get("/assignment-templates")
async def list_assignment_templates(user: dict = Depends(require_instructor)):
    docs = await db.assignment_templates.find({}, {"_id": 0}).sort("updated_at", -1).to_list(length=500)
    for d in docs:
        d["can_edit"] = (user.get("role") == "super_admin") or (d.get("created_by") == user["user_id"])
    return docs


@api_router.post("/assignment-templates")
async def create_assignment_template(payload: AssignmentTemplatePayload, user: dict = Depends(require_instructor)):
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if not payload.submission_type or payload.submission_type not in SUBMISSION_TYPE_IDS:
        raise HTTPException(status_code=400, detail=f"submission_type must be one of {SUBMISSION_TYPE_IDS}")
    tpl = AssignmentTemplate(
        name=name,
        description=(payload.description or "").strip(),
        submission_type=payload.submission_type,
        feedback_template=(payload.feedback_template or "").strip(),
        drive_folder_url=_validate_drive_url(payload.drive_folder_url or ""),
        questionnaire_fields=payload.questionnaire_fields if payload.submission_type == "business_questionnaire" else None,
        milestones=[_normalize_milestone_shape(m) for m in (payload.milestones or [])],
        created_by=user["user_id"],
        created_by_name=user.get("name") or user.get("email") or "",
    )
    await db.assignment_templates.insert_one(tpl.dict())
    out = tpl.dict()
    out["can_edit"] = True
    return out


@api_router.post("/assignment-templates/from-assignment/{assignment_id}")
async def save_assignment_as_template(assignment_id: str, user: dict = Depends(require_instructor)):
    """Snapshot the given assignment into a new template."""
    asgn = await db.assignments.find_one({"assignment_id": assignment_id}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found")
    cohort = await db.cohorts.find_one({"cohort_id": asgn["cohort_id"]}, {"_id": 0})
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    tpl = AssignmentTemplate(
        name=asgn.get("title", "Untitled Template"),
        description=asgn.get("description", ""),
        submission_type=asgn["submission_type"],
        feedback_template=asgn.get("feedback_template", ""),
        drive_folder_url=asgn.get("drive_folder_url", ""),
        questionnaire_fields=asgn.get("questionnaire_fields"),
        milestones=[_normalize_milestone_shape(m) for m in (asgn.get("milestones") or [])],
        created_by=user["user_id"],
        created_by_name=user.get("name") or user.get("email") or "",
    )
    await db.assignment_templates.insert_one(tpl.dict())
    out = tpl.dict()
    out["can_edit"] = True
    return out


@api_router.put("/assignment-templates/{template_id}")
async def update_assignment_template(template_id: str, payload: AssignmentTemplatePayload, user: dict = Depends(require_instructor)):
    tpl = await db.assignment_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if user.get("role") != "super_admin" and tpl.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the author or a super admin can edit this template")

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.description is not None:
        updates["description"] = (payload.description or "").strip()
    if payload.feedback_template is not None:
        updates["feedback_template"] = (payload.feedback_template or "").strip()
    if payload.drive_folder_url is not None:
        updates["drive_folder_url"] = _validate_drive_url(payload.drive_folder_url or "")
    if payload.questionnaire_fields is not None:
        updates["questionnaire_fields"] = payload.questionnaire_fields
    if payload.milestones is not None:
        updates["milestones"] = [_normalize_milestone_shape(m) for m in payload.milestones]

    await db.assignment_templates.update_one({"template_id": template_id}, {"$set": updates})
    updated = await db.assignment_templates.find_one({"template_id": template_id}, {"_id": 0})
    updated["can_edit"] = True
    return updated


@api_router.delete("/assignment-templates/{template_id}")
async def delete_assignment_template(template_id: str, user: dict = Depends(require_instructor)):
    tpl = await db.assignment_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if user.get("role") != "super_admin" and tpl.get("created_by") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Only the author or a super admin can delete this template")
    await db.assignment_templates.delete_one({"template_id": template_id})
    return {"template_id": template_id, "message": "Template deleted"}


@api_router.post("/cohorts/{cohort_id}/assignments/from-template/{template_id}")
async def apply_template_to_cohort(
    cohort_id: str,
    template_id: str,
    payload: ApplyTemplatePayload,
    user: dict = Depends(require_instructor)
):
    """Hydrate a template into a cohort. `week_map` remaps individual milestone weeks
    (send `null` to skip a milestone). If `replace_existing_by_type=True` and the cohort
    has an assignment with the same submission_type, its milestones + rubric are
    OVERWRITTEN in place (preserving assignment_id + submission history)."""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if user.get("role") != "super_admin" and not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    tpl = await db.assignment_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    milestones = _clone_milestones_from_template(tpl.get("milestones") or [], payload.week_map)
    title = (payload.title_override or "").strip() or tpl["name"]

    if payload.replace_existing_by_type:
        existing = await db.assignments.find_one({
            "cohort_id": cohort_id,
            "submission_type": tpl["submission_type"],
            "is_active": True,
        }, {"_id": 0})
        if existing:
            await db.assignments.update_one(
                {"assignment_id": existing["assignment_id"]},
                {"$set": {
                    "title": title,
                    "description": tpl.get("description", ""),
                    "feedback_template": tpl.get("feedback_template", ""),
                    "drive_folder_url": tpl.get("drive_folder_url", ""),
                    "questionnaire_fields": tpl.get("questionnaire_fields"),
                    "milestones": milestones,
                    "updated_at": datetime.now(timezone.utc),
                }}
            )
            return {
                "assignment_id": existing["assignment_id"],
                "message": f"Template applied — {len(milestones)} milestones (existing assignment updated)",
                "milestones_count": len(milestones),
                "replaced": True,
            }

    max_order = await db.assignments.count_documents({"cohort_id": cohort_id})
    asgn = Assignment(
        cohort_id=cohort_id,
        assignment_key="custom",
        title=title,
        description=tpl.get("description", ""),
        submission_type=tpl["submission_type"],
        order=max_order,
        feedback_template=tpl.get("feedback_template", ""),
        drive_folder_url=tpl.get("drive_folder_url", ""),
        questionnaire_fields=tpl.get("questionnaire_fields"),
        milestones=milestones,
    )
    await db.assignments.insert_one(asgn.dict())
    return {
        "assignment_id": asgn.assignment_id,
        "message": f"Template applied — {len(milestones)} milestones (new assignment created)",
        "milestones_count": len(milestones),
        "replaced": False,
    }


# ==================== END ASSIGNMENT TEMPLATES ====================


@api_router.post("/milestones/{milestone_id}/submit")
async def submit_milestone(
    milestone_id: str,
    file: UploadFile = File(None),
    cohort_id: str = None,
    assignment_id: str = None,
    questionnaire_answers: str = Form(default=""),
    user: dict = Depends(get_current_user)
):
    """Submit a student's work against an assignment milestone (Phase 2 flow)."""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can submit")
    if not assignment_id:
        raise HTTPException(status_code=400, detail="assignment_id is required")

    asgn = await db.assignments.find_one({"assignment_id": assignment_id, "is_active": True}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found or inactive")
    milestone = next((m for m in (asgn.get("milestones") or []) if m.get("milestone_id") == milestone_id), None)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    resolved_cohort_id = cohort_id or asgn["cohort_id"]
    cohort = await db.cohorts.find_one({"cohort_id": resolved_cohort_id}, {"_id": 0})
    if not cohort or user["user_id"] not in (cohort.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="Not enrolled in this cohort")

    # Idempotency: one submission per (student, milestone, cohort). Resubmit replaces the old file.
    existing = await db.submissions.find_one({
        "student_id": user["user_id"],
        "assignment_id": assignment_id,
        "milestone_id": milestone_id,
        "cohort_id": resolved_cohort_id,
    }, {"_id": 0})
    if existing:
        await delete_file_from_doc(existing)

    submission_type = asgn.get("submission_type")
    is_questionnaire = submission_type == "business_questionnaire"

    if is_questionnaire:
        try:
            answers_raw = json.loads(questionnaire_answers or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="questionnaire_answers must be valid JSON")
        if not isinstance(answers_raw, dict):
            raise HTTPException(status_code=400, detail="questionnaire_answers must be an object")
        fields = asgn.get("questionnaire_fields") or []
        answers: Dict[str, str] = {}
        for f in fields:
            fid = f.get("id")
            ans = str(answers_raw.get(fid, "") or "").strip()
            if f.get("required") and not ans:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' is required")
            if len(ans) > 5000:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' must be 5000 characters or less")
            answers[fid] = ans
        filename = f"questionnaire_a_{assignment_id}_m_{milestone_id}.json"
        gridfs_id = None
    else:
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="A file is required for this assignment")
        filename = file.filename or "unnamed"
        ext = filename.lower().split(".")[-1]
        allowed_exts = (
            SUBMISSION_TYPE_CONFIG[submission_type]["extensions"]
            if submission_type in SUBMISSION_TYPE_CONFIG and SUBMISSION_TYPE_CONFIG[submission_type]["input_kind"] == "file"
            else DEFAULT_HOMEWORK_EXTENSIONS
        )
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Allowed file types for this assignment: {', '.join('.' + e for e in allowed_exts)}"
            )
        content = await file.read()
        placeholder = f"sub_{uuid.uuid4().hex[:12]}"
        gridfs_id = await save_bytes_to_gridfs(content, f"{placeholder}_{filename}")
        answers = None

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.submissions.update_one(
            {"submission_id": existing["submission_id"]},
            {"$set": {
                "file_path": "",
                "gridfs_id": gridfs_id,
                "file_name": filename,
                "submission_type": submission_type,
                "questionnaire_answers": answers,
                "status": "pending",
                "ai_feedback": None,
                "instructor_feedback": None,
                "feedback_sent": False,
                "resubmission_allowed": False,
                "submitted_at": now,
                "reviewed_at": None,
                "sent_at": None,
                "resubmission_count": existing.get("resubmission_count", 0) + 1,
            }}
        )
        return {"submission_id": existing["submission_id"], "message": "Milestone resubmitted", "is_resubmission": True}

    sub = Submission(
        material_id=asgn.get("material_id") or "",  # optional legacy reference
        cohort_id=resolved_cohort_id,
        student_id=user["user_id"],
        file_path="",
        gridfs_id=gridfs_id,
        file_name=filename,
        submission_type=submission_type,
        questionnaire_answers=answers,
        assignment_id=assignment_id,
        milestone_id=milestone_id,
    )
    doc = sub.model_dump()
    doc["submitted_at"] = doc["submitted_at"].isoformat()
    doc["resubmission_count"] = 0
    await db.submissions.insert_one(doc)
    return {"submission_id": sub.submission_id, "message": "Milestone submitted", "is_resubmission": False}


@api_router.get("/cohorts/{cohort_id}/materials")
async def get_materials(cohort_id: str, week: int = None, user: dict = Depends(get_current_user)):
    """Get materials for a cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Check access
    if user["role"] in ["instructor", "super_admin"]:
        if user["role"] == "instructor" and not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")
    elif user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"cohort_id": cohort_id}
    if week:
        query["week_number"] = week
    
    materials = await db.materials.find(query, {"_id": 0}).to_list(100)
    
    # Also include library materials assigned to this cohort
    library_query = {"is_library": True, "cohort_ids": cohort_id}
    if week:
        library_query["week_number"] = week
    library_materials = await db.materials.find(library_query, {"_id": 0}).to_list(100)
    materials.extend(library_materials)
    
    # Group by week
    weeks = {}
    for mat in materials:
        w = mat["week_number"]
        if w not in weeks:
            weeks[w] = {"week_number": w, "workbooks": [], "case_studies": [], "homework": []}
        
        if mat["material_type"] == "workbook":
            weeks[w]["workbooks"].append(mat)
        elif mat["material_type"] == "case_study":
            weeks[w]["case_studies"].append(mat)
        else:
            weeks[w]["homework"].append(mat)
    
    return list(weeks.values())

@api_router.get("/submit-link/{material_id}")
async def get_submit_link_info(material_id: str):
    """Public endpoint: Get material info for direct submission link"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material or material.get("material_type") != "homework":
        raise HTTPException(status_code=404, detail="Homework assignment not found")
    
    # Get cohort info
    cohort_ids = []
    if material.get("is_library"):
        cohort_ids = material.get("cohort_ids", [])
    elif material.get("cohort_id"):
        cohort_ids = [material["cohort_id"]]
    
    cohorts = await db.cohorts.find(
        {"cohort_id": {"$in": cohort_ids}},
        {"_id": 0, "cohort_id": 1, "name": 1}
    ).to_list(20)
    
    return {
        "material_id": material_id,
        "title": material.get("title", ""),
        "week_number": material.get("week_number"),
        "file_name": material.get("file_name"),
        "description": material.get("description", ""),
        "drive_folder_url": material.get("drive_folder_url", ""),
        "submission_type": material.get("submission_type"),
        "questionnaire_fields": material.get("questionnaire_fields") or [],
        "cohorts": cohorts
    }


@api_router.get("/submit-link/w/{week_number}/{submission_type}")
async def resolve_stable_submit_link(week_number: int, submission_type: str, cohort_id: str = None):
    """Public endpoint: resolve a stable per-week-per-type link (Thinkific-embeddable) to a material.
    URL pattern: /submit/w/{week}/{submission_type}?cohort={cohort_id}"""
    if submission_type not in SUBMISSION_TYPE_IDS:
        raise HTTPException(status_code=400, detail=f"submission_type must be one of {SUBMISSION_TYPE_IDS}")

    query: Dict[str, Any] = {
        "material_type": "homework",
        "week_number": week_number,
        "submission_type": submission_type,
    }
    if cohort_id:
        # Match either the cohort's directly-uploaded material or a library material linked to it
        query = {
            "material_type": "homework",
            "week_number": week_number,
            "submission_type": submission_type,
            "$or": [
                {"cohort_id": cohort_id},
                {"is_library": True, "cohort_ids": cohort_id},
            ],
        }

    material = await db.materials.find_one(query, {"_id": 0}, sort=[("created_at", -1)])
    if not material:
        raise HTTPException(status_code=404, detail="No assignment matches this week + submission type yet")
    return {"material_id": material["material_id"]}



@api_router.put("/materials/{material_id}/week")
async def update_material_week(material_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Update a material's week number"""
    data = await request.json()
    week_number = data.get("week_number")
    if not week_number or not isinstance(week_number, int) or week_number < 1 or week_number > 14:
        raise HTTPException(status_code=400, detail="week_number must be 1-14")
    
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    await db.materials.update_one(
        {"material_id": material_id},
        {"$set": {"week_number": week_number}}
    )
    return {"message": f"Material week updated to {week_number}", "material_id": material_id}

@api_router.delete("/materials/{material_id}")
async def delete_material(material_id: str, user: dict = Depends(require_instructor)):
    """Delete a material"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete file (GridFS + legacy disk)
    await delete_file_from_doc(material)
    
    await db.materials.delete_one({"material_id": material_id})
    return {"message": "Material deleted"}


# ==================== MATERIAL LIBRARY ====================

@api_router.get("/library/materials")
async def get_library_materials(user: dict = Depends(require_instructor)):
    """Get all library materials"""
    materials = await db.materials.find(
        {"is_library": True},
        {"_id": 0}
    ).to_list(200)
    
    # Add cohort names for display
    all_cohort_ids = set()
    for mat in materials:
        all_cohort_ids.update(mat.get("cohort_ids", []))
    
    cohorts_map = {}
    if all_cohort_ids:
        cohorts = await db.cohorts.find(
            {"cohort_id": {"$in": list(all_cohort_ids)}},
            {"_id": 0, "cohort_id": 1, "name": 1}
        ).to_list(100)
        cohorts_map = {c["cohort_id"]: c["name"] for c in cohorts}
    
    for mat in materials:
        mat["assigned_cohorts"] = [
            {"cohort_id": cid, "name": cohorts_map.get(cid, "Unknown")}
            for cid in mat.get("cohort_ids", [])
        ]
    
    return materials

@api_router.post("/library/materials")
async def upload_library_material(
    week_number: int,
    material_type: str,
    title: str,
    file: UploadFile = File(None),
    description: str = "",
    is_global: bool = False,
    video_url: str = "",
    drive_folder_url: str = "",
    feedback_template: str = "",
    submission_type: str = "",
    questionnaire_fields: str = "",
    user: dict = Depends(require_instructor)
):
    """Upload a material to the central library (workbooks, case studies, homework, and videos).
    is_global=True marks the material as a Course-Wide Resource (spans all weeks; auto-included in every AI review).
    For material_type=video, either upload a file (MP4/MOV/WEBM/M4A/MP3) OR pass video_url (YouTube/Vimeo/Loom)."""
    if material_type not in ["workbook", "case_study", "homework", "video"]:
        raise HTTPException(status_code=400, detail="Library supports workbooks, case studies, homework, and videos")
    
    material_id = f"lib_{uuid.uuid4().hex[:12]}"
    gridfs_id = ""
    filename = ""
    is_url_video = False

    if material_type == "video":
        video_url = (video_url or "").strip()
        if video_url:
            # External URL (YouTube / Vimeo / Loom / etc.)
            if not (video_url.startswith("http://") or video_url.startswith("https://")):
                raise HTTPException(status_code=400, detail="video_url must be a valid http(s) URL")
            filename = video_url
            is_url_video = True
        else:
            if file is None or not file.filename:
                raise HTTPException(status_code=400, detail="Provide either a video file or video_url")
            filename = file.filename
            ext = filename.lower().split(".")[-1]
            if ext not in ["mp4", "mov", "webm", "m4v", "mp3", "m4a", "wav"]:
                raise HTTPException(status_code=400, detail="Video must be MP4, MOV, WEBM, M4V, MP3, M4A, or WAV")
            content = await file.read()
            gridfs_id = await save_bytes_to_gridfs(content, f"{material_id}_{filename}")
    else:
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="File is required for non-video materials")
        filename = file.filename
        ext = filename.lower().split(".")[-1]
        if ext not in ["pdf", "docx"]:
            raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
        content = await file.read()
        gridfs_id = await save_bytes_to_gridfs(content, f"{material_id}_{filename}")
    
    doc = {
        "material_id": material_id,
        "is_library": True,
        "is_global": bool(is_global),
        "cohort_id": None,
        "cohort_ids": [],
        "week_number": 0 if is_global else week_number,
        "material_type": material_type,
        "title": title,
        "description": description,
        "file_path": "",
        "gridfs_id": gridfs_id,
        "file_name": filename,
        "video_url": video_url if material_type == "video" and is_url_video else "",
        "transcript": "",
        "transcription_status": "pending" if material_type == "video" and not is_url_video else "n/a",
        "drive_folder_url": _validate_drive_url(drive_folder_url) if material_type == "homework" else "",
        "feedback_template": (feedback_template or "").strip() if material_type == "homework" else "",
        "submission_type": _validate_submission_type(submission_type) if material_type == "homework" else None,
        "questionnaire_fields": _parse_questionnaire_fields(questionnaire_fields) if (material_type == "homework" and _validate_submission_type(submission_type) == "business_questionnaire") else None,
        "uploaded_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.materials.insert_one(doc)
    
    # For uploaded video files, kick off transcription in the background
    if material_type == "video" and not is_url_video and gridfs_id:
        asyncio.create_task(transcribe_video_material(material_id))
    
    return {"material_id": material_id, "message": "Material added to library"}


@api_router.post("/library/materials/{material_id}/transcribe")
async def trigger_transcription(material_id: str, user: dict = Depends(require_instructor)):
    """Manually (re-)trigger transcription of a video material."""
    material = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Library material not found")
    if material.get("material_type") != "video":
        raise HTTPException(status_code=400, detail="Only video materials can be transcribed")
    if not material.get("gridfs_id"):
        raise HTTPException(status_code=400, detail="Cannot transcribe external URL videos (only uploaded files)")
    
    await db.materials.update_one(
        {"material_id": material_id},
        {"$set": {"transcription_status": "pending", "transcript": ""}}
    )
    asyncio.create_task(transcribe_video_material(material_id))
    return {"message": "Transcription started"}

@api_router.put("/library/materials/{material_id}")
async def update_library_material(
    material_id: str,
    title: str = None,
    description: str = None,
    week_number: int = None,
    file: UploadFile = File(None),
    user: dict = Depends(require_instructor)
):
    """Update a library material (title, description, week, or replace file)"""
    material = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Library material not found")
    
    update_data = {}
    if title is not None:
        update_data["title"] = title
    if description is not None:
        update_data["description"] = description
    if week_number is not None:
        update_data["week_number"] = week_number
    
    if file and file.filename:
        filename = file.filename
        ext = filename.lower().split(".")[-1]
        if ext not in ["pdf", "docx"]:
            raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
        
        # Remove old file (GridFS + legacy disk)
        await delete_file_from_doc(material)
        
        content = await file.read()
        gridfs_id = await save_bytes_to_gridfs(content, f"{material_id}_{filename}")
        update_data["gridfs_id"] = gridfs_id
        update_data["file_path"] = ""
        update_data["file_name"] = filename
    
    if update_data:
        await db.materials.update_one({"material_id": material_id}, {"$set": update_data})
    
    return {"message": "Library material updated"}

@api_router.delete("/library/materials/{material_id}")
async def delete_library_material(material_id: str, user: dict = Depends(require_instructor)):
    """Delete a library material"""
    material = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Library material not found")
    
    await delete_file_from_doc(material)
    
    await db.materials.delete_one({"material_id": material_id})
    return {"message": "Library material deleted"}

@api_router.post("/library/materials/{material_id}/duplicate")
async def duplicate_library_material(material_id: str, user: dict = Depends(require_instructor)):
    """Duplicate a library material as an unassigned template.
    - PDF/DOCX/uploaded video: copies GridFS bytes into a new entry.
    - URL-based video: copies the video_url reference only (no GridFS)."""
    src = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Library material not found")
    
    is_video = src.get("material_type") == "video"
    is_url_video = is_video and bool(src.get("video_url"))
    
    new_material_id = f"lib_{uuid.uuid4().hex[:12]}"
    new_gridfs_id = ""
    
    if not is_url_video:
        # Copy file bytes to a new GridFS entry
        try:
            file_bytes = await read_bytes_from_doc(src)
        except HTTPException as e:
            if e.status_code == 410:
                raise HTTPException(status_code=410, detail="Original file is no longer available; cannot duplicate.")
            raise
        new_gridfs_id = await save_bytes_to_gridfs(file_bytes, f"{new_material_id}_{src['file_name']}")
    
    # transcription_status: URL videos → 'n/a'; uploaded videos → 'pending' (re-transcribe copy); others → 'n/a'
    if is_url_video:
        new_transcription_status = "n/a"
    elif is_video:
        new_transcription_status = "pending"
    else:
        new_transcription_status = "n/a"
    
    doc = {
        "material_id": new_material_id,
        "is_library": True,
        "is_global": bool(src.get("is_global", False)),
        "cohort_id": None,
        "cohort_ids": [],  # template — unassigned
        "week_number": src.get("week_number", 0 if src.get("is_global") else 1),
        "material_type": src.get("material_type"),
        "title": f"{src.get('title', 'Untitled')} (Copy)",
        "description": src.get("description"),
        "file_path": "",
        "gridfs_id": new_gridfs_id,
        "file_name": src.get("file_name", ""),
        "video_url": src.get("video_url", "") if is_url_video else "",
        "transcript": "",
        "transcription_status": new_transcription_status,
        "uploaded_by": user["user_id"],
        "duplicated_from": material_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.materials.insert_one(doc)
    
    # Fire background transcription for the copied uploaded video
    if is_video and not is_url_video and new_gridfs_id:
        asyncio.create_task(transcribe_video_material(new_material_id))
    
    return {"material_id": new_material_id, "message": "Material duplicated as template"}


@api_router.post("/cohorts/{cohort_id}/duplicate")
async def duplicate_cohort(cohort_id: str, user: dict = Depends(require_instructor)):
    """Duplicate a cohort as a template: copies materials assignments + release config; does NOT copy students or submissions."""
    src = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if not is_cohort_manager(user, src):
        raise HTTPException(status_code=403, detail="Access denied")
    
    new_cohort = Cohort(
        name=f"{src.get('name', 'Untitled')} (Copy)",
        description=src.get("description"),
        instructor_id=user["user_id"],
        instructor_ids=[user["user_id"]],
        student_ids=[]  # template — start with no students
    )
    doc = new_cohort.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    # Carry over released_weeks config (keeps the same week-release pattern)
    doc["released_weeks"] = list(src.get("released_weeks", []))
    doc["duplicated_from"] = cohort_id
    await db.cohorts.insert_one(doc)
    
    # Re-assign all library materials that were linked to the source cohort
    src_lib_assignments = await db.materials.find(
        {"is_library": True, "cohort_ids": cohort_id},
        {"_id": 0, "material_id": 1}
    ).to_list(500)
    
    for mat in src_lib_assignments:
        await db.materials.update_one(
            {"material_id": mat["material_id"]},
            {"$addToSet": {"cohort_ids": new_cohort.cohort_id}}
        )
    
    # Also duplicate cohort-specific (non-library) materials by cloning file + record
    src_inline_mats = await db.materials.find(
        {"cohort_id": cohort_id, "is_library": {"$ne": True}},
        {"_id": 0}
    ).to_list(500)
    
    inline_copied = 0
    for mat in src_inline_mats:
        try:
            mat_bytes = await read_bytes_from_doc(mat)
        except HTTPException:
            continue  # skip mats whose files are gone (legacy disk-only records)
        new_mat_id = f"mat_{uuid.uuid4().hex[:12]}"
        new_gridfs_id = await save_bytes_to_gridfs(mat_bytes, f"{new_mat_id}_{mat['file_name']}")
        new_mat = {
            "material_id": new_mat_id,
            "cohort_id": new_cohort.cohort_id,
            "week_number": mat.get("week_number", 1),
            "material_type": mat.get("material_type"),
            "title": mat.get("title", "Untitled"),
            "description": mat.get("description"),
            "file_path": "",
            "gridfs_id": new_gridfs_id,
            "file_name": mat["file_name"],
            "uploaded_by": user["user_id"],
            "due_date": mat.get("due_date"),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.materials.insert_one(new_mat)
        inline_copied += 1
    
    return {
        "cohort_id": new_cohort.cohort_id,
        "library_materials_linked": len(src_lib_assignments),
        "cohort_materials_copied": inline_copied,
        "message": "Cohort duplicated as template"
    }


@api_router.post("/library/materials/{material_id}/assign")
async def assign_library_material(material_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Assign a library material to one or more cohorts"""
    data = await request.json()
    cohort_ids = data.get("cohort_ids", [])
    
    if not cohort_ids:
        raise HTTPException(status_code=400, detail="cohort_ids required")
    
    material = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Library material not found")
    
    # Verify cohorts exist and user has access
    for cid in cohort_ids:
        cohort = await db.cohorts.find_one({"cohort_id": cid}, {"_id": 0})
        if not cohort:
            raise HTTPException(status_code=404, detail=f"Cohort {cid} not found")
        if not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail=f"No access to cohort {cohort['name']}")
    
    await db.materials.update_one(
        {"material_id": material_id},
        {"$addToSet": {"cohort_ids": {"$each": cohort_ids}}}
    )
    
    return {"message": f"Material assigned to {len(cohort_ids)} cohort(s)"}

@api_router.post("/library/materials/{material_id}/unassign")
async def unassign_library_material(material_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Remove a library material from a cohort"""
    data = await request.json()
    cohort_id = data.get("cohort_id")
    
    if not cohort_id:
        raise HTTPException(status_code=400, detail="cohort_id required")
    
    material = await db.materials.find_one({"material_id": material_id, "is_library": True}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Library material not found")
    
    await db.materials.update_one(
        {"material_id": material_id},
        {"$pull": {"cohort_ids": cohort_id}}
    )
    
    return {"message": "Material removed from cohort"}


@api_router.get("/materials/{material_id}/download")
async def download_material(material_id: str, inline: int = 0, user: dict = Depends(get_current_user)):
    """Download (or inline-preview with ?inline=1) a material file"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    # Library materials: any instructor or student in an assigned cohort can download
    if material.get("is_library"):
        if user["role"] in ["instructor", "super_admin"]:
            pass  # instructors/admins can download any library material
        else:
            # Student must be in at least one assigned cohort
            assigned_cohorts = material.get("cohort_ids", [])
            student_cohorts = await db.cohorts.find(
                {"cohort_id": {"$in": assigned_cohorts}, "student_ids": user["user_id"]},
                {"_id": 0, "cohort_id": 1}
            ).to_list(1)
            if not student_cohorts:
                raise HTTPException(status_code=403, detail="Access denied")
    else:
        # Check access via cohort
        cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
        if not cohort:
            raise HTTPException(status_code=404, detail="Cohort not found")
        
        if user["role"] in ["instructor", "super_admin"]:
            if user["role"] == "instructor" and not is_cohort_manager(user, cohort):
                raise HTTPException(status_code=403, detail="Access denied")
        elif user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
            raise HTTPException(status_code=403, detail="Access denied")
    
    file_bytes = await read_bytes_from_doc(material)
    return binary_file_response(file_bytes, material["file_name"], inline=bool(inline))


@api_router.get("/materials/{material_id}/preview-text")
async def preview_material_text(material_id: str, user: dict = Depends(get_current_user)):
    """Return the extracted text content of a material (for DOCX inline preview)."""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    # Same ACL as download
    if material.get("is_library"):
        if user["role"] not in ["instructor", "super_admin"]:
            assigned_cohorts = material.get("cohort_ids", [])
            student_cohorts = await db.cohorts.find(
                {"cohort_id": {"$in": assigned_cohorts}, "student_ids": user["user_id"]},
                {"_id": 0, "cohort_id": 1}
            ).to_list(1)
            if not student_cohorts:
                raise HTTPException(status_code=403, detail="Access denied")
    else:
        cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
        if not cohort:
            raise HTTPException(status_code=404, detail="Cohort not found")
        if user["role"] in ["instructor", "super_admin"]:
            if user["role"] == "instructor" and not is_cohort_manager(user, cohort):
                raise HTTPException(status_code=403, detail="Access denied")
        elif user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
            raise HTTPException(status_code=403, detail="Access denied")
    
    file_bytes = await read_bytes_from_doc(material)
    text = extract_text_from_file(file_bytes, material.get("file_name", ""))
    return {"text": text, "file_name": material.get("file_name", "")}


# ==================== STUDENT DASHBOARD ENDPOINT ====================

@api_router.get("/student/assignments-dashboard")
async def get_student_assignments_dashboard(user: dict = Depends(get_current_user)):
    """Assignment-first student dashboard (Phase 2 model). Returns per-cohort data with
    'This Week' summary + 4 (or more) assignment sections showing milestone progress."""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Students only")

    cohorts = await db.cohorts.find({"student_ids": user["user_id"]}, {"_id": 0}).to_list(10)
    result = []
    for cohort in cohorts:
        # Auto-seed if needed (idempotent — same helper used by the instructor GET)
        try:
            await _seed_default_assignments_for_cohort(cohort["cohort_id"], cohort.get("total_weeks", 14))
        except Exception:
            pass

        assignments = await db.assignments.find(
            {"cohort_id": cohort["cohort_id"], "is_active": True},
            {"_id": 0}
        ).sort("order", 1).to_list(50)

        subs = await db.submissions.find(
            {"student_id": user["user_id"], "cohort_id": cohort["cohort_id"]},
            {"_id": 0}
        ).to_list(500)
        subs_by_ms = {s.get("milestone_id"): s for s in subs if s.get("milestone_id")}

        assignments_out = []
        earliest_unsubmitted_week = None
        for a in assignments:
            ms_out = []
            for m in (a.get("milestones") or []):
                ms_id = m.get("milestone_id")
                sub = subs_by_ms.get(ms_id)
                if sub:
                    raw = sub.get("status") or "pending"
                    status = {"pending": "submitted", "draft": "under_review", "sent": "feedback_provided", "reviewed": "under_review"}.get(raw, raw)
                    submission_summary = {
                        "submission_id": sub["submission_id"],
                        "status": status,
                        "submitted_at": sub.get("submitted_at", ""),
                        "feedback_sent": sub.get("feedback_sent", False),
                        "ai_feedback": sub.get("instructor_feedback") or sub.get("ai_feedback") if status == "feedback_provided" else None,
                    }
                else:
                    status = "not_started"
                    submission_summary = None
                    wk = m.get("week_number")
                    if wk is not None and (earliest_unsubmitted_week is None or wk < earliest_unsubmitted_week):
                        earliest_unsubmitted_week = wk

                ms_out.append({
                    "milestone_id": ms_id,
                    "week_number": m.get("week_number"),
                    "title": m.get("title", ""),
                    "description": m.get("description", ""),
                    "drive_folder_url": m.get("drive_folder_url_override") or a.get("drive_folder_url") or "",
                    "is_final_capstone": bool(m.get("is_final_capstone")),
                    "due_date": m.get("due_date"),
                    "status": status,
                    "submission": submission_summary,
                })

            assignments_out.append({
                "assignment_id": a["assignment_id"],
                "assignment_key": a.get("assignment_key", "custom"),
                "title": a.get("title", ""),
                "description": a.get("description", ""),
                "submission_type": a.get("submission_type"),
                "drive_folder_url": a.get("drive_folder_url", ""),
                "questionnaire_fields": a.get("questionnaire_fields"),
                "milestones": sorted(ms_out, key=lambda x: (x.get("week_number") or 0, 1 if x.get("is_final_capstone") else 0)),
            })

        # "This Week" = milestones at earliest_unsubmitted_week across all assignments
        this_week = []
        if earliest_unsubmitted_week is not None:
            for a in assignments_out:
                for m in a["milestones"]:
                    if m["week_number"] == earliest_unsubmitted_week and m["status"] == "not_started":
                        this_week.append({
                            "assignment_id": a["assignment_id"],
                            "assignment_title": a["title"],
                            "submission_type": a["submission_type"],
                            "milestone_id": m["milestone_id"],
                            "milestone_title": m["title"],
                            "week_number": m["week_number"],
                            "drive_folder_url": m["drive_folder_url"],
                            "is_final_capstone": m["is_final_capstone"],
                        })

        result.append({
            "cohort_id": cohort["cohort_id"],
            "cohort_name": cohort.get("name", ""),
            "total_weeks": cohort.get("total_weeks", 14),
            "current_week": earliest_unsubmitted_week,  # None if everything is done
            "this_week": this_week,
            "assignments": assignments_out,
        })

    return result


@api_router.get("/student/dashboard")
async def get_student_dashboard(user: dict = Depends(get_current_user)):
    """Get structured weekly dashboard data for student"""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Students only")
    
    cohorts = await db.cohorts.find(
        {"student_ids": user["user_id"]},
        {"_id": 0}
    ).to_list(10)
    
    result = []
    for cohort in cohorts:
        released_weeks = cohort.get("released_weeks", [])
        
        materials = await db.materials.find(
            {"cohort_id": cohort["cohort_id"]},
            {"_id": 0}
        ).to_list(100)
        
        # Also include library materials assigned to this cohort
        library_materials = await db.materials.find(
            {"is_library": True, "cohort_ids": cohort["cohort_id"]},
            {"_id": 0}
        ).to_list(100)
        materials.extend(library_materials)
        
        # Course-Wide Resources: global materials that this cohort has been given access to
        global_mats = [m for m in library_materials if m.get("is_global")]
        course_resources = [
            {
                "material_id": m["material_id"],
                "title": m.get("title", ""),
                "material_type": m.get("material_type", ""),
                "file_name": m.get("file_name", ""),
                "video_url": m.get("video_url", ""),
                "description": m.get("description", "")
            }
            for m in global_mats
        ]
        
        submissions = await db.submissions.find(
            {"student_id": user["user_id"], "cohort_id": cohort["cohort_id"]},
            {"_id": 0}
        ).to_list(100)
        
        weeks = []
        for week_num in range(1, 15):
            # Only include released weeks
            if week_num not in released_weeks:
                continue
            
            week_materials = [m for m in materials if m.get("week_number") == week_num]
            homework_list = [m for m in week_materials if m.get("material_type") == "homework"]
            
            week_data = {
                "week_number": week_num,
                "homework": None,          # kept for back-compat = first homework
                "submission": None,        # kept for back-compat = first submission
                "homeworks": [],           # NEW: full array (supports N tracks per week)
                "status": "no_homework",
                "feedback": None,
                "materials": []
            }
            
            # Include all materials for download
            for mat in week_materials:
                week_data["materials"].append({
                    "material_id": mat["material_id"],
                    "title": mat.get("title", ""),
                    "material_type": mat.get("material_type", ""),
                    "file_name": mat.get("file_name", "")
                })
            
            # Rank statuses so the top-level status = least-complete across all homeworks
            status_rank = {
                "no_homework": 0,
                "feedback_provided": 1,
                "under_review": 2,
                "submitted": 3,
                "waiting_on_submission": 4,
            }
            worst_status = "no_homework"
            
            for hw in homework_list:
                hw_entry = {
                    "material_id": hw["material_id"],
                    "title": hw.get("title", ""),
                    "description": hw.get("description", ""),
                    "due_date": hw.get("due_date"),
                    "file_name": hw.get("file_name", ""),
                    "drive_folder_url": hw.get("drive_folder_url", ""),
                    "submission": None,
                    "status": "waiting_on_submission",
                    "feedback": None,
                }
                sub = next((s for s in submissions if s.get("material_id") == hw["material_id"]), None)
                if sub:
                    hw_entry["submission"] = {
                        "submission_id": sub["submission_id"],
                        "file_name": sub.get("file_name", ""),
                        "submitted_at": sub.get("submitted_at", ""),
                        "resubmission_allowed": sub.get("resubmission_allowed", False),
                        "resubmission_count": sub.get("resubmission_count", 0)
                    }
                    if sub.get("status") == "pending":
                        hw_entry["status"] = "submitted"
                    elif sub.get("status") == "draft":
                        hw_entry["status"] = "under_review"
                    elif sub.get("status") == "sent":
                        hw_entry["status"] = "feedback_provided"
                        hw_entry["feedback"] = sub.get("instructor_feedback") or sub.get("ai_feedback")
                
                week_data["homeworks"].append(hw_entry)
                if status_rank.get(hw_entry["status"], 0) > status_rank.get(worst_status, 0):
                    worst_status = hw_entry["status"]
            
            if homework_list:
                first = week_data["homeworks"][0]
                # Legacy fields (single-homework consumers)
                week_data["homework"] = {
                    "material_id": first["material_id"],
                    "title": first["title"],
                    "description": first["description"],
                    "due_date": first["due_date"],
                    "file_name": first["file_name"],
                    "drive_folder_url": first.get("drive_folder_url", ""),
                }
                week_data["submission"] = first["submission"]
                week_data["status"] = worst_status
                # Legacy top-level feedback: prefer any feedback_provided entry
                fb_entry = next((h for h in week_data["homeworks"] if h["status"] == "feedback_provided"), None)
                if fb_entry:
                    week_data["feedback"] = fb_entry["feedback"]
            
            weeks.append(week_data)
        
        result.append({
            "cohort_id": cohort["cohort_id"],
            "cohort_name": cohort.get("name", ""),
            "description": cohort.get("description", ""),
            "course_resources": course_resources,
            "weeks": weeks
        })
    
    return result


# ==================== COACH MAX CHAT ENDPOINT ====================

@api_router.post("/chat/ask-tutor")
async def ask_tutor(request: Request, user: dict = Depends(get_current_user)):
    """Ask Coach Max a follow-up question about feedback"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Students only")
    
    data = await request.json()
    message = data.get("message", "").strip()
    submission_id = data.get("submission_id")
    lang_override = data.get("language")  # per-chat override
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if not submission_id:
        raise HTTPException(status_code=400, detail="Submission ID is required")
    
    # Determine language: per-chat override > profile default > en
    lang = lang_override or user.get("language_preference", "en")
    
    # Get submission
    submission = await db.submissions.find_one(
        {"submission_id": submission_id, "student_id": user["user_id"]},
        {"_id": 0}
    )
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    if submission.get("status") != "sent":
        raise HTTPException(status_code=400, detail="Feedback has not been provided yet")
    
    feedback = submission.get("instructor_feedback") or submission.get("ai_feedback", "")
    
    # Resolve source: prefer milestone-based (new model), fall back to legacy material.
    material = None
    asgn_title = None
    week_number = None
    if submission.get("assignment_id") and submission.get("milestone_id"):
        asgn = await db.assignments.find_one({"assignment_id": submission["assignment_id"]}, {"_id": 0})
        if asgn:
            ms = next((m for m in (asgn.get("milestones") or []) if m.get("milestone_id") == submission["milestone_id"]), None)
            asgn_title = asgn.get("title") or "Assignment"
            week_number = (ms or {}).get("week_number")
    if submission.get("material_id"):
        material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    if asgn_title is None:
        asgn_title = (material or {}).get("title") or "Unknown"
    if week_number is None:
        week_number = (material or {}).get("week_number") or 1
    
    # Build context (works for both material-based and milestone-based; queries cohort materials by week)
    submission_text, context_text = await build_coach_max_context(submission, material, week_number=week_number)
    
    # Build cumulative context from prior weeks + prior submissions in the same assignment
    cumulative_ctx = await build_cumulative_context(
        user["user_id"], submission.get("cohort_id", ""), week_number,
        assignment_id=submission.get("assignment_id"),
    )
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    response = ""
    branding = await get_branding()
    persona = branding.get("ai_persona_name", "Coach Max")
    persona_override = (branding.get("ai_system_prompt") or "").strip()
    try:
        default_prompt = f"""You are {persona}, a friendly, supportive AI tutor for a leadership development course.
A student has received feedback on their homework and wants to discuss it with you.

Your personality:
- Warm, encouraging, and conversational
- Use the student's name when possible
- Answer questions clearly and specifically
- Reference the course materials and their submission when relevant
- When relevant, connect current topics back to concepts from earlier weeks
- Help them understand how to improve
- Keep responses concise (2-4 paragraphs max)
- Never give grades or scores

CURRENT ASSIGNMENT: {asgn_title}
CURRENT WEEK: {week_number}

THE STUDENT'S SUBMISSION:
{submission_text[:5000] if submission_text else 'Not available'}

FEEDBACK THE STUDENT RECEIVED:
{feedback}

CURRENT WEEK MATERIALS:
{context_text[:5000] if context_text else 'Not available'}

PRIOR WEEKS CONTEXT (materials covered + student's previous feedback):
{cumulative_ctx[:5000] if cumulative_ctx else 'This is the first week — no prior context.'}{get_language_instruction(lang)}"""

        system_prompt = (persona_override.replace("{persona}", persona)
                         if persona_override else default_prompt)

        chat = LlmChat(
            api_key=api_key,
            session_id=f"coach_max_{user['user_id']}_{submission_id}",
            system_message=system_prompt
        ).with_model("openai", "gpt-5.2")
        
        response = await chat.send_message(UserMessage(text=message))
        
    except Exception as e:
        logger.error(f"Coach Max error: {e}")
        raise HTTPException(status_code=500, detail=f"{persona} is unavailable right now")
    
    # Store chat in DB
    chat_entry = {
        "chat_id": f"chat_{uuid.uuid4().hex[:12]}",
        "submission_id": submission_id,
        "student_id": user["user_id"],
        "message": message,
        "response": response,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.tutor_chats.insert_one(chat_entry)
    
    return {"response": response}

@api_router.get("/chat/history/{submission_id}")
async def get_chat_history(submission_id: str, user: dict = Depends(get_current_user)):
    """Get chat history for a submission"""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Students only")
    
    chats = await db.tutor_chats.find(
        {"submission_id": submission_id, "student_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", 1).to_list(100)
    
    return chats


# ==================== SUBMISSION ENDPOINTS ====================

@api_router.post("/materials/{material_id}/submit")
async def submit_homework(
    material_id: str,
    file: UploadFile = File(None),
    cohort_id: str = None,
    assignment_id: str = None,
    milestone_id: str = None,
    questionnaire_answers: str = Form(default=""),
    user: dict = Depends(get_current_user)
):
    """Submit homework for review. Accepts either a file OR (for questionnaire types) JSON answers."""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can submit homework")
    
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material or material.get("material_type") != "homework":
        raise HTTPException(status_code=404, detail="Homework assignment not found")
    
    # Resolve cohort using extracted helper
    submission_cohort_id, cohort = await resolve_submission_cohort(material, user, cohort_id)
    
    # Check for existing submission (scoped to this student + material + cohort)
    existing = await db.submissions.find_one({
        "material_id": material_id,
        "student_id": user["user_id"],
        "cohort_id": submission_cohort_id
    }, {"_id": 0})
    
    if existing:
        # Delete old file (GridFS + legacy disk)
        await delete_file_from_doc(existing)

    submission_type = material.get("submission_type")
    is_questionnaire = submission_type == "business_questionnaire"

    if is_questionnaire:
        # Parse + validate answers against material's questionnaire_fields
        try:
            answers_raw = json.loads(questionnaire_answers or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="questionnaire_answers must be valid JSON")
        if not isinstance(answers_raw, dict):
            raise HTTPException(status_code=400, detail="questionnaire_answers must be an object")

        fields = material.get("questionnaire_fields") or []
        answers: Dict[str, str] = {}
        for f in fields:
            fid = f.get("id")
            ans = answers_raw.get(fid, "")
            if not isinstance(ans, str):
                ans = str(ans)
            ans = ans.strip()
            if f.get("required") and not ans:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' is required")
            if len(ans) > 5000:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' must be 5000 characters or less")
            answers[fid] = ans

        filename = f"questionnaire_{material_id}.json"
        gridfs_id = None  # No binary file for questionnaire
        content = b""  # Placeholder for closure captured by auto_review
    else:
        # File-based submission (existing behavior, with per-type extension validation)
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="A file is required for this assignment")
        filename = file.filename or "unnamed"
        ext = filename.lower().split(".")[-1]
        allowed_exts = (
            SUBMISSION_TYPE_CONFIG[submission_type]["extensions"]
            if submission_type in SUBMISSION_TYPE_CONFIG and SUBMISSION_TYPE_CONFIG[submission_type]["input_kind"] == "file"
            else DEFAULT_HOMEWORK_EXTENSIONS
        )
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Allowed file types for this assignment: {', '.join('.' + e for e in allowed_exts)}"
            )

        # Save file to GridFS (persistent across redeploys)
        submission_id_placeholder = f"sub_{uuid.uuid4().hex[:12]}"
        content = await file.read()
        gridfs_id = await save_bytes_to_gridfs(content, f"{submission_id_placeholder}_{filename}")
        answers = None
    
    # Create or update submission
    if existing:
        # Update existing submission (resubmission)
        submission_id = existing["submission_id"]
        await db.submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "file_path": "",
                "gridfs_id": gridfs_id,
                "file_name": filename,
                "submission_type": submission_type,
                "questionnaire_answers": answers,
                "assignment_id": assignment_id or existing.get("assignment_id"),
                "milestone_id": milestone_id or existing.get("milestone_id"),
                "status": "pending",
                "ai_feedback": None,
                "instructor_feedback": None,
                "feedback_sent": False,
                "resubmission_allowed": False,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "reviewed_at": None,
                "sent_at": None,
                "resubmission_count": existing.get("resubmission_count", 0) + 1
            }}
        )
        is_resubmission = True
    else:
        # Create new submission
        submission = Submission(
            material_id=material_id,
            cohort_id=submission_cohort_id,
            student_id=user["user_id"],
            file_path="",
            gridfs_id=gridfs_id,
            file_name=filename,
            submission_type=submission_type,
            questionnaire_answers=answers,
            assignment_id=assignment_id,
            milestone_id=milestone_id,
        )
        submission_id = submission.submission_id
        
        doc = submission.model_dump()
        doc["submitted_at"] = doc["submitted_at"].isoformat()
        doc["resubmission_count"] = 0
        await db.submissions.insert_one(doc)
        is_resubmission = False
    
    # Send email notification to instructors
    instructor_ids = cohort.get("instructor_ids", [])
    if not instructor_ids and cohort.get("instructor_id"):
        instructor_ids = [cohort["instructor_id"]]
    for inst_id in instructor_ids:
        instructor = await db.users.find_one({"user_id": inst_id}, {"_id": 0})
        if instructor:
            subject_prefix = "Resubmission" if is_resubmission else "New Submission"
            email_html = build_submission_email_html(user['name'], material, cohort['name'], is_resubmission)
            await send_email_notification(
                instructor["email"],
                f"{subject_prefix}: {material['title']} from {user['name']}",
                email_html
            )
    
    # Send confirmation email to student
    action_word = "Resubmission" if is_resubmission else "Submission"
    action_lower = "resubmission" if is_resubmission else "submission"
    student_confirm_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">{action_word} Received!</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
            <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                Hi <strong>{user['name'].split()[0]}</strong>,
            </p>
            <p style="color: #5A5A5A; font-size: 14px; margin-bottom: 16px;">
                We've received your {action_lower} for <strong>{material['title']}</strong> (Week {material['week_number']}).
            </p>
            <div style="background-color: #E1F0FF; border: 1px solid #B8D4E8; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <p style="margin: 0 0 4px 0; color: #22438E; font-weight: 600; font-size: 14px;">What happens next?</p>
                <p style="margin: 0; color: #333333; font-size: 14px;">
                    Coach Max will review your work and your instructor will send you personalized feedback. You'll receive an email when it's ready.
                </p>
            </div>
            <p style="color: #888; font-size: 13px;">
                {cohort['name']} &middot; The Boost Pad
            </p>
        </div>
    </div>
    """
    subject_word = "Resubmission" if is_resubmission else "Submission"
    await send_email_notification(
        user["email"],
        f"{subject_word} Received: {material['title']}",
        student_confirm_html
    )
    
    return {"submission_id": submission_id, "message": f"Homework {'resubmitted' if is_resubmission else 'submitted'}"}

async def _run_auto_ai_review_for_submission(
    submission_id: str,
    *,
    week_number: int,
    title: str,
    description: Optional[str],
    feedback_template: Optional[str],
    cohort_id: str,
    student_id: str,
    assignment_id: Optional[str] = None,
) -> None:
    """Background task: run AI review on a stored submission and persist feedback as a draft.
    Reads the submission fresh from DB (so it works whether the submission is file-based
    or questionnaire-based). Used by both `/materials/.../submit-on-behalf` (legacy) and
    `/milestones/.../submit-on-behalf` (new)."""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
        if not submission:
            logger.error(f"Auto review: submission {submission_id} not found")
            return

        # For video/audio submissions (e.g. 60-Second Pitch): transcribe first if not already done
        submission = await _ensure_submission_transcript(submission)
        if _is_media_submission(submission):
            status = submission.get("transcription_status")
            if status == "failed_too_large":
                logger.error(f"Auto review: audio too large for Whisper, submission {submission_id}")
                await db.submissions.update_one(
                    {"submission_id": submission_id},
                    {"$set": {"ai_feedback_error": "Audio/video file is too large to transcribe (25 MB Whisper limit). Please upload a shorter clip.", "status": "review_failed"}},
                )
                return
            if status == "failed":
                logger.error(f"Auto review: transcription failed for submission {submission_id}")
                await db.submissions.update_one(
                    {"submission_id": submission_id},
                    {"$set": {"ai_feedback_error": "Could not transcribe the audio/video file. Please try again or upload a different format.", "status": "review_failed"}},
                )
                return

        # Extract submission text (handles file, questionnaire, video transcript)
        submission_text = await read_file_text(submission)
        if not (submission_text or "").strip():
            logger.error(f"Auto review: empty submission text for {submission_id}")
            await db.submissions.update_one(
                {"submission_id": submission_id},
                {"$set": {"ai_feedback_error": "No readable content found in the submission. If you uploaded a video or audio file, please ensure it contains clear spoken content.", "status": "review_failed"}},
            )
            return

        # Context: current-week workbook/case_study/video materials + course-wide globals
        context_materials = await db.materials.find({
            "week_number": week_number,
            "material_type": {"$in": ["workbook", "case_study", "video"]},
            "$or": [{"cohort_ids": cohort_id}, {"cohort_id": cohort_id}],
        }, {"_id": 0}).to_list(10)
        global_materials = await db.materials.find({
            "is_library": True, "is_global": True, "cohort_ids": cohort_id,
        }, {"_id": 0}).to_list(20)
        context_materials = list(global_materials) + list(context_materials)

        context_text = ""
        for mat in context_materials:
            try:
                mat_text = await read_file_text(mat)
                context_text += f"\n\n--- {mat.get('material_type', '').upper()}: {mat.get('title', '')} ---\n{(mat_text or '')[:5000]}"
            except Exception:
                pass

        # Cumulative context from prior weeks + prior same-assignment submissions
        cumulative_ctx = await build_cumulative_context(
            student_id, cohort_id, week_number, assignment_id=assignment_id
        )

        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            logger.error("Auto review: EMERGENT_LLM_KEY not set")
            return

        # Language preference from the STUDENT (not the instructor triggering the submit)
        stu = await db.users.find_one({"user_id": student_id}, {"_id": 0})
        lang = (stu or {}).get("language_preference", "en")
        lang_instr = get_language_instruction(lang)

        custom_tpl = (feedback_template or "").strip()
        if custom_tpl:
            try:
                _rendered = custom_tpl.format(week_number=week_number, title=title, persona="")
            except (KeyError, IndexError, ValueError):
                _rendered = custom_tpl
            system_msg = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on this specific homework submission.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from the student's work
- Reference prior weeks' concepts when relevant
- Do NOT give grades or scores
- Write in a mentoring tone

For THIS assignment, follow these custom instructions from the instructor:

{_rendered}
{lang_instr}"""
        else:
            system_msg = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on homework submissions.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from their work to support each point
- When relevant, reference concepts from earlier weeks to show how the student is building on prior learning
- Note any improvements or growth patterns compared to prior feedback
- Do NOT give grades or scores
- Write in a mentoring, supportive tone
- Keep each bullet point concise (1-2 sentences)

You MUST structure your feedback EXACTLY as follows:

A brief encouraging opening sentence acknowledging their effort.

{"Lo que hiciste bien:" if lang == "es" else "What You Did Well:"}
- [specific strength with example from their work]
- [specific strength with example from their work]
- [specific strength with example from their work]

{"Areas de crecimiento:" if lang == "es" else "Areas for Growth:"}
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]

A brief closing sentence with encouragement and motivation to keep going.{lang_instr}"""

        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_{submission_id}",
            system_message=system_msg,
        ).with_model("openai", "gpt-5.2")

        prompt = f"""Please review this student's homework submission and provide structured feedback.

ASSIGNMENT: {title}
{f"DESCRIPTION: {description}" if description else ""}

CURRENT WEEK CONTEXT (Week {week_number} materials):
{context_text[:6000] if context_text else "No additional context available."}

PRIOR WEEKS CONTEXT (earlier course materials + student's previous feedback):
{cumulative_ctx[:5000] if cumulative_ctx else "This is the student's first submission — no prior context."}

STUDENT SUBMISSION:
{submission_text[:10000]}

Provide feedback with exactly 3 bullet points under "What You Did Well:" and exactly 3 bullet points under "Areas for Growth:". Use specific examples from their submission. When possible, reference how this builds on earlier weeks."""

        feedback = await chat.send_message(UserMessage(text=prompt))
        await db.submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "ai_feedback": feedback,
                "status": "draft",
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"Auto AI review completed for {submission_id}")

        # Self-paced mode: auto-send if the cohort is configured that way
        cohort_doc = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
        if cohort_doc and cohort_doc.get("auto_send_feedback"):
            try:
                # Reuse the existing send helper. Pass a synthetic 'user' dict — the helper
                # only uses it to know who's sending; auto-send is system-initiated.
                await send_feedback_to_student(submission_id, {"user_id": "system", "role": "super_admin", "name": "Auto-Send"})
            except Exception as e:
                logger.error(f"auto_send after auto-review failed for {submission_id}: {e}")
    except Exception as e:
        logger.error(f"Auto AI review failed for {submission_id}: {e}")


@api_router.post("/milestones/{milestone_id}/submit-on-behalf")
async def submit_milestone_on_behalf(
    milestone_id: str,
    file: UploadFile = File(None),
    student_id: str = Form(...),
    assignment_id: str = Form(...),
    cohort_id: str = Form(None),
    questionnaire_answers: str = Form(default=""),
    user: dict = Depends(require_instructor),
):
    """Instructor submits homework on behalf of a student against an assignment milestone.
    Auto-triggers AI review after saving."""
    # 1. Resolve + validate assignment
    asgn = await db.assignments.find_one({"assignment_id": assignment_id, "is_active": True}, {"_id": 0})
    if not asgn:
        raise HTTPException(status_code=404, detail="Assignment not found or inactive")
    milestone = next((m for m in (asgn.get("milestones") or []) if m.get("milestone_id") == milestone_id), None)
    if not milestone:
        raise HTTPException(status_code=404, detail="Milestone not found")

    # 2. Verify instructor manages this cohort
    resolved_cohort_id = cohort_id or asgn["cohort_id"]
    cohort = await db.cohorts.find_one({"cohort_id": resolved_cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Verify student is enrolled
    student = await db.users.find_one({"user_id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student_id not in (cohort.get("student_ids") or []):
        raise HTTPException(status_code=400, detail="Student is not enrolled in this cohort")

    submission_type = asgn.get("submission_type")
    is_questionnaire = submission_type == "business_questionnaire"

    # 4. Delete any prior submission for this student+milestone
    existing = await db.submissions.find_one({
        "student_id": student_id,
        "assignment_id": assignment_id,
        "milestone_id": milestone_id,
        "cohort_id": resolved_cohort_id,
    }, {"_id": 0})
    if existing:
        await delete_file_from_doc(existing)

    # 5. Save new submission (file OR questionnaire)
    if is_questionnaire:
        try:
            answers_raw = json.loads(questionnaire_answers or "{}")
        except Exception:
            raise HTTPException(status_code=400, detail="questionnaire_answers must be valid JSON")
        if not isinstance(answers_raw, dict):
            raise HTTPException(status_code=400, detail="questionnaire_answers must be an object")
        fields = asgn.get("questionnaire_fields") or []
        answers: Dict[str, str] = {}
        for f in fields:
            fid = f.get("id")
            ans = str(answers_raw.get(fid, "") or "").strip()
            if f.get("required") and not ans:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' is required")
            if len(ans) > 5000:
                raise HTTPException(status_code=400, detail=f"'{f.get('label')}' must be 5000 characters or less")
            answers[fid] = ans
        filename = f"questionnaire_a_{assignment_id}_m_{milestone_id}.json"
        gridfs_id = None
    else:
        if file is None or not file.filename:
            raise HTTPException(status_code=400, detail="A file is required for this assignment")
        filename = file.filename or "unnamed"
        ext = filename.lower().split(".")[-1]
        allowed_exts = (
            SUBMISSION_TYPE_CONFIG[submission_type]["extensions"]
            if submission_type in SUBMISSION_TYPE_CONFIG and SUBMISSION_TYPE_CONFIG[submission_type]["input_kind"] == "file"
            else DEFAULT_HOMEWORK_EXTENSIONS
        )
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Allowed file types for this assignment: {', '.join('.' + e for e in allowed_exts)}",
            )
        content = await file.read()
        placeholder = f"sub_{uuid.uuid4().hex[:12]}"
        gridfs_id = await save_bytes_to_gridfs(content, f"{placeholder}_{filename}")
        answers = None

    now = datetime.now(timezone.utc).isoformat()
    if existing:
        submission_id = existing["submission_id"]
        await db.submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "file_path": "",
                "gridfs_id": gridfs_id,
                "file_name": filename,
                "submission_type": submission_type,
                "questionnaire_answers": answers,
                "status": "pending",
                "ai_feedback": None,
                "instructor_feedback": None,
                "feedback_sent": False,
                "resubmission_allowed": False,
                "submitted_at": now,
                "reviewed_at": None,
                "sent_at": None,
                "submitted_by": user["user_id"],
                "resubmission_count": existing.get("resubmission_count", 0) + 1,
            }},
        )
    else:
        sub = Submission(
            material_id="",  # milestone-based; no legacy material
            cohort_id=resolved_cohort_id,
            student_id=student_id,
            file_path="",
            gridfs_id=gridfs_id,
            file_name=filename,
            submission_type=submission_type,
            questionnaire_answers=answers,
            assignment_id=assignment_id,
            milestone_id=milestone_id,
        )
        doc = sub.model_dump()
        doc["submitted_at"] = now
        doc["resubmission_count"] = 0
        doc["submitted_by"] = user["user_id"]
        submission_id = sub.submission_id
        await db.submissions.insert_one(doc)

    # 6. Fire auto AI review
    week_number = int(milestone.get("week_number") or 1)
    # Milestone-level feedback_template overrides the assignment's
    effective_template = (milestone.get("feedback_template_override") or "").strip() or (asgn.get("feedback_template") or "").strip() or None
    asyncio.create_task(_run_auto_ai_review_for_submission(
        submission_id,
        week_number=week_number,
        title=asgn.get("title") or "Assignment",
        description=asgn.get("description"),
        feedback_template=effective_template,
        cohort_id=resolved_cohort_id,
        student_id=student_id,
        assignment_id=assignment_id,
    ))

    # 7. Confirmation email to student
    try:
        student_first_name = (student.get("name") or "there").split()[0]
        confirm_html = f"""
        <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
                <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">Submission Received!</h1>
            </div>
            <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
                <p style="color: #1A1A1A; font-size: 16px;">Hi <strong>{student_first_name}</strong>,</p>
                <p style="color: #5A5A5A; font-size: 14px;">
                    Your instructor has submitted <strong>{asgn.get("title", "your assignment")}</strong>
                    (Week {week_number}: {milestone.get("title") or ""}) on your behalf.
                    Coach Max is reviewing your work and your instructor will send you personalized feedback.
                </p>
                <p style="color: #888; font-size: 13px;">{cohort.get('name', '')} &middot; The Boost Pad</p>
            </div>
        </div>
        """
        await send_email_notification(
            student["email"],
            f"Submission Received: {asgn.get('title', 'Assignment')}",
            confirm_html,
        )
    except Exception as e:
        logger.error(f"Confirmation email failed for {submission_id}: {e}")

    return {
        "submission_id": submission_id,
        "message": f"Submitted on behalf of {student.get('name', 'the student')}. AI review in progress.",
    }



@api_router.post("/materials/{material_id}/submit-on-behalf")
async def submit_on_behalf(
    material_id: str,
    file: UploadFile = File(...),
    student_id: str = Form(...),
    cohort_id: str = Form(None),
    user: dict = Depends(require_instructor)
):
    """Instructor submits homework on behalf of a student, then auto-triggers AI review"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material or material.get("material_type") != "homework":
        raise HTTPException(status_code=404, detail="Homework assignment not found")
    
    # Verify instructor manages this cohort
    if cohort_id:
        cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    else:
        cohort_ids = material.get("cohort_ids") or ([material["cohort_id"]] if material.get("cohort_id") else [])
        cohort = await db.cohorts.find_one({"cohort_id": {"$in": cohort_ids}}, {"_id": 0}) if cohort_ids else None
    
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    submission_cohort_id = cohort["cohort_id"]
    
    # Verify student exists and is in the cohort
    student = await db.users.find_one({"user_id": student_id}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if student_id not in (cohort.get("student_ids") or []):
        raise HTTPException(status_code=400, detail="Student is not in this cohort")
    
    # Check for existing submission
    existing = await db.submissions.find_one({
        "material_id": material_id,
        "student_id": student_id,
        "cohort_id": submission_cohort_id
    }, {"_id": 0})
    
    if existing:
        await delete_file_from_doc(existing)
    
    # Validate file
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    
    # Save file to GridFS (persistent across redeploys)
    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    content = await file.read()
    gridfs_id = await save_bytes_to_gridfs(content, f"{submission_id}_{filename}")
    
    if existing:
        submission_id = existing["submission_id"]
        await db.submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "file_path": "",
                "gridfs_id": gridfs_id,
                "file_name": filename,
                "status": "pending",
                "ai_feedback": None,
                "instructor_feedback": None,
                "feedback_sent": False,
                "resubmission_allowed": False,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "submitted_by": user["user_id"],
                "resubmission_count": existing.get("resubmission_count", 0) + 1
            }}
        )
    else:
        submission = Submission(
            submission_id=submission_id,
            material_id=material_id,
            cohort_id=submission_cohort_id,
            student_id=student_id,
            file_path="",
            gridfs_id=gridfs_id,
            file_name=filename
        )
        doc = submission.model_dump()
        doc["submitted_at"] = doc["submitted_at"].isoformat()
        doc["resubmission_count"] = 0
        doc["submitted_by"] = user["user_id"]
        await db.submissions.insert_one(doc)
    
    # Auto-trigger AI review in the background
    async def auto_review():
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            # Get context materials for this week
            context_materials = await db.materials.find({
                "week_number": material.get("week_number"),
                "material_type": {"$in": ["workbook", "case_study", "video"]},
                "$or": [
                    {"cohort_ids": submission_cohort_id},
                    {"cohort_id": submission_cohort_id}
                ]
            }, {"_id": 0}).to_list(10)
            
            # Always include Course-Wide Resources
            global_materials = await db.materials.find({
                "is_library": True,
                "is_global": True,
                "cohort_ids": submission_cohort_id
            }, {"_id": 0}).to_list(20)
            context_materials = list(global_materials) + list(context_materials)
            
            # Extract text from submission — file bytes OR questionnaire answers.
            # submit_on_behalf writes/edits a file, so is_questionnaire defaults False;
            # if the material IS a questionnaire, fall back to reading stored answers.
            sub_is_questionnaire = material.get("submission_type") == "business_questionnaire"
            if sub_is_questionnaire:
                stored = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0, "questionnaire_answers": 1})
                stored_answers = (stored or {}).get("questionnaire_answers") or {}
                submission_text = "\n\n".join(
                    f"Q: {f.get('label')}\nA: {stored_answers.get(f.get('id'), '') or '(no answer)'}"
                    for f in (material.get("questionnaire_fields") or [])
                )
            else:
                submission_text = extract_text_from_file(content, filename)
            
            if not submission_text.strip():
                logger.error(f"Auto review: empty submission text for {submission_id}")
                return
            
            # Build context from course materials
            context_text = ""
            for mat in context_materials:
                try:
                    mat_bytes = await read_bytes_from_doc(mat)
                    mat_text = extract_text_from_file(mat_bytes, mat["file_name"])
                    context_text += f"\n\n--- {mat['material_type'].upper()}: {mat['title']} ---\n{mat_text[:5000]}"
                except Exception:
                    pass
            
            api_key = os.environ.get("EMERGENT_LLM_KEY")
            if not api_key:
                logger.error("Auto review: EMERGENT_LLM_KEY not set")
                return
            
            # Look up student's language preference
            stu = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
            auto_lang = stu.get("language_preference", "en") if stu else "en"
            auto_lang_instr = get_language_instruction(auto_lang)
            
            # Build cumulative context from prior weeks
            auto_cumulative = await build_cumulative_context(
                student_id, submission_cohort_id, material.get("week_number", 1)
            )
            
            auto_custom_tpl = (material.get("feedback_template") or "").strip()
            if auto_custom_tpl:
                try:
                    _auto_rendered = auto_custom_tpl.format(
                        week_number=material.get("week_number", "?"),
                        title=material.get("title", ""),
                        persona="",
                    )
                except (KeyError, IndexError, ValueError):
                    _auto_rendered = auto_custom_tpl
                _auto_system = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on this specific homework submission.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from the student's work
- Reference prior weeks' concepts when relevant
- Do NOT give grades or scores
- Write in a mentoring tone

For THIS assignment, follow these custom instructions from the instructor:

{_auto_rendered}
{auto_lang_instr}"""
            else:
                _auto_system = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on homework submissions.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from their work to support each point
- When relevant, reference concepts from earlier weeks to show how the student is building on prior learning
- Note any improvements or growth patterns compared to prior feedback
- Do NOT give grades or scores
- Write in a mentoring, supportive tone
- Keep each bullet point concise (1-2 sentences)

You MUST structure your feedback EXACTLY as follows:

A brief encouraging opening sentence acknowledging their effort.

{"Lo que hiciste bien:" if auto_lang == "es" else "What You Did Well:"}
- [specific strength with example from their work]
- [specific strength with example from their work]
- [specific strength with example from their work]

{"Areas de crecimiento:" if auto_lang == "es" else "Areas for Growth:"}
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]

A brief closing sentence with encouragement and motivation to keep going.{auto_lang_instr}"""
            chat = LlmChat(
                api_key=api_key,
                session_id=f"review_{submission_id}",
                system_message=_auto_system
            ).with_model("openai", "gpt-5.2")
            
            prompt = f"""Please review this student's homework submission and provide structured feedback.

ASSIGNMENT: {material['title']}
{f"DESCRIPTION: {material['description']}" if material.get('description') else ""}

CURRENT WEEK CONTEXT (Week {material.get('week_number', '?')} materials):
{context_text[:6000] if context_text else "No additional context available."}

PRIOR WEEKS CONTEXT (earlier course materials + student's previous feedback):
{auto_cumulative[:5000] if auto_cumulative else "This is the student's first submission — no prior context."}

STUDENT SUBMISSION:
{submission_text[:10000]}

Provide feedback with exactly 3 bullet points under "What You Did Well:" and exactly 3 bullet points under "Areas for Growth:". Use specific examples from their submission. When possible, reference how this builds on earlier weeks."""

            feedback = await chat.send_message(UserMessage(text=prompt))
            
            await db.submissions.update_one(
                {"submission_id": submission_id},
                {"$set": {
                    "ai_feedback": feedback,
                    "status": "draft",
                    "reviewed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            logger.info(f"Auto AI review completed for {submission_id}")
        except Exception as e:
            logger.error(f"Auto AI review failed for {submission_id}: {e}")
    
    asyncio.create_task(auto_review())
    
    # Send confirmation email to student
    student_confirm_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">Submission Received!</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
            <p style="color: #1A1A1A; font-size: 16px;">Hi <strong>{student['name'].split()[0]}</strong>,</p>
            <p style="color: #5A5A5A; font-size: 14px;">
                Your instructor has submitted <strong>{material['title']}</strong> (Week {material.get('week_number', '?')}) on your behalf.
                Coach Max will review your work and your instructor will send you personalized feedback.
            </p>
            <p style="color: #888; font-size: 13px;">{cohort['name']} &middot; The Boost Pad</p>
        </div>
    </div>
    """
    await send_email_notification(
        student["email"],
        f"Submission Received: {material['title']}",
        student_confirm_html
    )
    
    return {"submission_id": submission_id, "message": f"Homework submitted on behalf of {student['name']}. AI review in progress."}


@api_router.get("/submissions")
async def get_submissions(user: dict = Depends(get_current_user)):
    """Get submissions for current user"""
    submissions = []
    if user["role"] == "student":
        submissions = await db.submissions.find(
            {"student_id": user["user_id"]},
            {"_id": 0}
        ).to_list(100)
    elif user["role"] == "super_admin":
        # Super admin sees all submissions
        submissions = await db.submissions.find({}, {"_id": 0}).to_list(500)
        # Add student info
        for sub in submissions:
            student = await db.users.find_one(
                {"user_id": sub["student_id"]},
                {"_id": 0, "name": 1, "email": 1}
            )
            sub["student"] = student
    else:
        # Instructor: get all submissions for their cohorts
        cohorts = await db.cohorts.find(
            {"$or": [
                {"instructor_ids": user["user_id"]},
                {"instructor_id": user["user_id"]}
            ]},
            {"_id": 0, "cohort_id": 1}
        ).to_list(100)
        cohort_ids = [c["cohort_id"] for c in cohorts]
        
        submissions = await db.submissions.find(
            {"cohort_id": {"$in": cohort_ids}},
            {"_id": 0}
        ).to_list(500)
        
        # Add student info
        for sub in submissions:
            student = await db.users.find_one(
                {"user_id": sub["student_id"]},
                {"_id": 0, "name": 1, "email": 1}
            )
            sub["student"] = student
    
    # Add material info
    for sub in submissions:
        material = await db.materials.find_one(
            {"material_id": sub["material_id"]},
            {"_id": 0, "title": 1, "week_number": 1}
        )
        sub["material"] = material
    
    return submissions

@api_router.post("/submissions/{submission_id}/allow-resubmission")
async def allow_resubmission(submission_id: str, user: dict = Depends(require_instructor)):
    """Allow student to resubmit homework"""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update to allow resubmission
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {"resubmission_allowed": True}}
    )
    
    # Send email to student
    student = await db.users.find_one({"user_id": submission["student_id"]}, {"_id": 0})
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    
    if student:
        email_html = f"""
        <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #E0F2FE; padding: 20px; border-radius: 12px 12px 0 0;">
                <h1 style="color: #075985; margin: 0; font-size: 24px;">Resubmission Allowed</h1>
            </div>
            <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
                <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                    Hi <strong>{student['name'].split()[0]}</strong>,
                </p>
                <p style="color: #5A5A5A; font-size: 14px; margin-bottom: 16px;">
                    Your instructor has allowed you to resubmit your homework for <strong>{material['title'] if material else 'the assignment'}</strong>.
                </p>
                <p style="color: #5A5A5A; font-size: 14px;">
                    Log in to The Boost Pad to submit your updated work.
                </p>
            </div>
        </div>
        """
        await send_email_notification(
            student["email"],
            f"Resubmission Allowed: {material['title'] if material else 'Homework'}",
            email_html
        )
    
    return {"message": "Resubmission allowed. Student has been notified."}

# ==================== PROGRESS TRACKING ====================

@api_router.get("/analytics/dashboard")
async def get_dashboard_analytics(user: dict = Depends(require_instructor)):
    """Get dashboard analytics for instructor"""
    # Get cohorts (super_admin sees all, instructor sees their own)
    if user["role"] == "super_admin":
        cohorts = await db.cohorts.find({}, {"_id": 0}).to_list(100)
    else:
        cohorts = await db.cohorts.find(
            {"$or": [
                {"instructor_ids": user["user_id"]},
                {"instructor_id": user["user_id"]}
            ]},
            {"_id": 0}
        ).to_list(100)
    
    cohort_ids = [c["cohort_id"] for c in cohorts]
    
    # Get all submissions for these cohorts
    submissions = await db.submissions.find(
        {"cohort_id": {"$in": cohort_ids}},
        {"_id": 0}
    ).to_list(1000)
    
    # Calculate stats
    pending_count = len([s for s in submissions if s.get("status") == "pending"])
    draft_count = len([s for s in submissions if s.get("status") == "draft"])
    sent_count = len([s for s in submissions if s.get("status") == "sent" or s.get("feedback_sent")])
    total_submissions = len(submissions)
    
    # Get total students
    total_students = sum(len(c.get("student_ids", [])) for c in cohorts)
    
    # Get recent submissions (last 7 days)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_submissions = []
    for s in submissions:
        sa = s.get("submitted_at")
        if not sa:
            continue
        try:
            if isinstance(sa, str):
                sa = datetime.fromisoformat(sa.replace("Z", "+00:00"))
            if sa.tzinfo is None:
                sa = sa.replace(tzinfo=timezone.utc)
            if sa > week_ago:
                recent_submissions.append(s)
        except (ValueError, AttributeError):
            pass
    
    return {
        "cohorts": len(cohorts),
        "total_students": total_students,
        "submissions": {
            "pending": pending_count,
            "draft": draft_count,
            "sent": sent_count,
            "total": total_submissions
        },
        "recent_activity": {
            "submissions_this_week": len(recent_submissions)
        },
        "action_required": {
            "needs_review": pending_count,
            "drafts_to_send": draft_count
        }
    }

@api_router.get("/analytics/cohort/{cohort_id}")
async def get_cohort_analytics(cohort_id: str, user: dict = Depends(require_instructor)):
    """Get detailed analytics for a specific cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Get all materials for this cohort
    materials = await db.materials.find(
        {"cohort_id": cohort_id},
        {"_id": 0}
    ).to_list(100)
    
    homework_materials = [m for m in materials if m.get("material_type") == "homework"]
    
    # Get all submissions for this cohort
    submissions = await db.submissions.find(
        {"cohort_id": cohort_id},
        {"_id": 0}
    ).to_list(500)
    
    # Get student details
    students = await db.users.find(
        {"user_id": {"$in": cohort.get("student_ids", [])}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "picture": 1}
    ).to_list(100)
    
    # Calculate per-student progress
    student_progress = []
    for student in students:
        student_subs = [s for s in submissions if s.get("student_id") == student["user_id"]]
        completed = len([s for s in student_subs if s.get("status") == "sent" or s.get("feedback_sent")])
        pending = len([s for s in student_subs if s.get("status") in ["pending", "draft"]])
        
        # Build per-week details for this student
        week_details = []
        for mat in homework_materials:
            sub = next((s for s in student_subs if s.get("material_id") == mat["material_id"]), None)
            week_details.append({
                "week_number": mat["week_number"],
                "material_id": mat["material_id"],
                "homework_title": mat.get("title", ""),
                "submission_id": sub["submission_id"] if sub else None,
                "file_name": sub.get("file_name") if sub else None,
                "status": sub.get("status") if sub else "not_submitted",
                "submitted_at": sub.get("submitted_at") if sub else None,
                "ai_feedback": sub.get("ai_feedback") if sub else None,
                "instructor_feedback": sub.get("instructor_feedback") if sub else None,
            })
        week_details.sort(key=lambda x: x["week_number"])
        
        student_progress.append({
            "user_id": student["user_id"],
            "name": student["name"],
            "email": student["email"],
            "picture": student.get("picture"),
            "submissions": len(student_subs),
            "completed": completed,
            "pending": pending,
            "completion_rate": round((completed / len(homework_materials) * 100) if homework_materials else 0, 1),
            "week_details": week_details
        })
    
    # Sort by completion rate
    student_progress.sort(key=lambda x: x["completion_rate"], reverse=True)
    
    # Calculate per-week progress
    weeks = {}
    for mat in homework_materials:
        week = mat["week_number"]
        if week not in weeks:
            weeks[week] = {"week": week, "assignments": 0, "submitted": 0, "reviewed": 0}
        weeks[week]["assignments"] += 1
        
        mat_subs = [s for s in submissions if s.get("material_id") == mat["material_id"]]
        weeks[week]["submitted"] += len(mat_subs)
        weeks[week]["reviewed"] += len([s for s in mat_subs if s.get("status") == "sent" or s.get("feedback_sent")])
    
    return {
        "cohort": {
            "name": cohort["name"],
            "description": cohort.get("description"),
            "total_students": len(students),
            "total_homework": len(homework_materials)
        },
        "overview": {
            "total_submissions": len(submissions),
            "completed_reviews": len([s for s in submissions if s.get("status") == "sent" or s.get("feedback_sent")]),
            "pending_reviews": len([s for s in submissions if s.get("status") in ["pending", "draft"]]),
            "avg_completion_rate": round(sum(s["completion_rate"] for s in student_progress) / len(student_progress) if student_progress else 0, 1)
        },
        "student_progress": student_progress,
        "weekly_progress": list(weeks.values())
    }

@api_router.get("/submissions/{submission_id}")
async def get_submission(submission_id: str, user: dict = Depends(get_current_user)):
    """Get single submission details. Works for both legacy material-based and new milestone-based."""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Check access
    if user["role"] == "student" and submission["student_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if user["role"] == "instructor":
        cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
        if not cohort or not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Related info: prefer milestone-based (new) with a synthetic `material` shape for frontend compat;
    # fall back to legacy material record when material_id is set.
    material = None
    assignment = None
    milestone = None
    if submission.get("assignment_id") and submission.get("milestone_id"):
        assignment = await db.assignments.find_one(
            {"assignment_id": submission["assignment_id"]}, {"_id": 0}
        )
        if assignment:
            milestone = next(
                (m for m in (assignment.get("milestones") or []) if m.get("milestone_id") == submission["milestone_id"]),
                None,
            )
            # Synthetic material-like shape so the CoachMaxPage + other UIs work without changes
            material = {
                "title": assignment.get("title") or "Assignment",
                "week_number": (milestone or {}).get("week_number"),
                "description": assignment.get("description"),
                "material_type": "assignment",
                "assignment_id": assignment.get("assignment_id"),
                "milestone_id": (milestone or {}).get("milestone_id"),
                "milestone_title": (milestone or {}).get("title"),
                "submission_type": assignment.get("submission_type"),
                "feedback_template": (milestone or {}).get("feedback_template_override") or assignment.get("feedback_template"),
            }
    if material is None and submission.get("material_id"):
        material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    submission["material"] = material
    submission["assignment"] = assignment
    submission["milestone"] = milestone
    
    if user["role"] in ["instructor", "super_admin"]:
        student = await db.users.find_one({"user_id": submission["student_id"]}, {"_id": 0, "name": 1, "email": 1})
        submission["student"] = student
    
    return submission

@api_router.get("/submissions/{submission_id}/download")
async def download_submission(submission_id: str, inline: int = 0, user: dict = Depends(get_current_user)):
    """Download (or inline-preview) a student's submitted homework file"""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Students can only download their own submissions
    if user["role"] == "student" and submission["student_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Instructors can only download from their cohorts
    if user["role"] == "instructor":
        cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
        if not cohort or not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")
    # super_admin can download any submission

    # Questionnaire submissions have no binary file; serve the Q&A as JSON
    if submission.get("submission_type") == "business_questionnaire":
        mat = await db.materials.find_one({"material_id": submission.get("material_id")}, {"_id": 0, "questionnaire_fields": 1, "title": 1})
        fields = (mat or {}).get("questionnaire_fields") or []
        answers = submission.get("questionnaire_answers") or {}
        payload = {
            "title": (mat or {}).get("title", ""),
            "answers": [
                {"id": f.get("id"), "label": f.get("label"), "answer": answers.get(f.get("id"), "")}
                for f in fields
            ],
        }
        body = json.dumps(payload, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'{"inline" if inline else "attachment"}; filename="questionnaire.json"'
            }
        )

    file_bytes = await read_bytes_from_doc(submission)
    filename = submission.get("file_name", "submission")
    return binary_file_response(file_bytes, filename, inline=bool(inline))


@api_router.get("/submissions/{submission_id}/preview-text")
async def preview_submission_text(submission_id: str, user: dict = Depends(get_current_user)):
    """Return the extracted text content of a submission (for DOCX inline preview)."""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    if user["role"] == "student" and submission["student_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] == "instructor":
        cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
        if not cohort or not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")

    # Questionnaire submissions: return Q&A as text
    if submission.get("submission_type") == "business_questionnaire":
        mat = await db.materials.find_one({"material_id": submission.get("material_id")}, {"_id": 0, "questionnaire_fields": 1})
        fields = (mat or {}).get("questionnaire_fields") or []
        answers = submission.get("questionnaire_answers") or {}
        text = "\n\n".join(
            f"Q: {f.get('label')}\nA: {answers.get(f.get('id'), '') or '(no answer)'}"
            for f in fields
        ) or "(no answers submitted)"
        return {"text": text, "file_name": "questionnaire"}

    file_bytes = await read_bytes_from_doc(submission)
    text = extract_text_from_file(file_bytes, submission.get("file_name", ""))
    return {"text": text, "file_name": submission.get("file_name", "")}


@api_router.delete("/submissions/{submission_id}")
async def delete_submission(submission_id: str, user: dict = Depends(require_instructor)):
    """Delete a single submission — instructor/admin only"""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Verify access
    if submission.get("cohort_id"):
        cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
        if cohort and not is_cohort_manager(user, cohort):
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete the file (GridFS + legacy disk)
    await delete_file_from_doc(submission)
    
    # Delete related chat history
    await db.tutor_chats.delete_many({"submission_id": submission_id})
    
    # Delete the submission
    await db.submissions.delete_one({"submission_id": submission_id})
    
    return {"message": "Submission deleted"}

@api_router.get("/cohorts/{cohort_id}/submissions")
async def get_cohort_submissions(cohort_id: str, user: dict = Depends(require_instructor)):
    """Get all submissions for a cohort, grouped by week, with student info"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    submissions = await db.submissions.find(
        {"cohort_id": cohort_id},
        {"_id": 0}
    ).to_list(500)
    
    for sub in submissions:
        student = await db.users.find_one(
            {"user_id": sub["student_id"]},
            {"_id": 0, "name": 1, "email": 1, "picture": 1}
        )
        sub["student"] = student
        material = await db.materials.find_one(
            {"material_id": sub["material_id"]},
            {"_id": 0, "title": 1, "week_number": 1}
        )
        sub["material"] = material
    
    return submissions

# ==================== AI REVIEW ENDPOINT ====================

@api_router.post("/submissions/{submission_id}/review")
async def review_submission(submission_id: str, user: dict = Depends(require_instructor)):
    """Generate AI review for a submission (works for both legacy material-based and new milestone-based submissions)."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Resolve source: prefer milestone-based (new model), fall back to material-based (legacy).
    material = None
    assignment = None
    milestone = None
    week_number = None
    title = None
    description = ""
    feedback_template = None
    if submission.get("assignment_id") and submission.get("milestone_id"):
        assignment = await db.assignments.find_one({"assignment_id": submission["assignment_id"]}, {"_id": 0})
        if assignment:
            milestone = next(
                (m for m in (assignment.get("milestones") or []) if m.get("milestone_id") == submission["milestone_id"]),
                None,
            )
            title = assignment.get("title") or "Assignment"
            description = assignment.get("description") or ""
            week_number = (milestone or {}).get("week_number") or 1
            feedback_template = ((milestone or {}).get("feedback_template_override") or "").strip() or (assignment.get("feedback_template") or "").strip() or None
    if material is None and submission.get("material_id"):
        material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
        if material and title is None:
            title = material.get("title") or "Homework"
            description = material.get("description") or ""
            week_number = material.get("week_number") or 1
            feedback_template = (material.get("feedback_template") or "").strip() or None
    if title is None:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # For video/audio submissions (e.g. 60-Second Pitch): transcribe first if not already done.
    submission = await _ensure_submission_transcript(submission)
    if _is_media_submission(submission):
        status = submission.get("transcription_status")
        if status == "failed_too_large":
            raise HTTPException(status_code=400, detail="Audio/video file is too large to transcribe (25 MB Whisper limit). Please upload a shorter clip.")
        if status == "failed":
            raise HTTPException(status_code=400, detail="Could not transcribe the audio/video file. Please try again or upload a different format.")

    # Get related workbooks and case studies for context
    context_materials = await db.materials.find({
        "cohort_id": submission["cohort_id"],
        "week_number": week_number,
        "material_type": {"$in": ["workbook", "case_study", "video"]}
    }, {"_id": 0}).to_list(10)
    # Always include Course-Wide Resources (is_global=True library materials linked to this cohort)
    global_materials = await db.materials.find({
        "is_library": True,
        "is_global": True,
        "cohort_ids": submission["cohort_id"]
    }, {"_id": 0}).to_list(20)
    context_materials = list(global_materials) + list(context_materials)
    
    # Extract text from submission (read_file_text handles questionnaire fallback + video transcripts)
    try:
        submission_text = await read_file_text(submission)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading submission {submission['submission_id']}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading submission file: {type(e).__name__}")
    
    if not submission_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from submission. The file may be empty or in an unsupported format.")
    
    # Build context from course materials
    context_text = ""
    for mat in context_materials:
        try:
            mat_bytes = await read_bytes_from_doc(mat)
            mat_text = extract_text_from_file(mat_bytes, mat["file_name"])
            context_text += f"\n\n--- {mat['material_type'].upper()}: {mat['title']} ---\n{mat_text[:5000]}"
        except Exception:
            pass
    
    # Call GPT-5.2 for review
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    # Look up student's language preference
    student = await db.users.find_one({"user_id": submission["student_id"]}, {"_id": 0})
    lang = student.get("language_preference", "en") if student else "en"
    lang_instr = get_language_instruction(lang)
    
    # Build cumulative context from prior weeks + prior submissions for the SAME assignment
    cumulative_ctx = await build_cumulative_context(
        submission["student_id"], submission.get("cohort_id", ""), week_number,
        assignment_id=submission.get("assignment_id"),
    )
    
    feedback = ""
    custom_template = (feedback_template or "").strip() if feedback_template else ""
    if custom_template:
        # Substitute placeholders
        try:
            _rendered = custom_template.format(
                week_number=week_number,
                title=title,
                persona="",
            )
        except (KeyError, IndexError, ValueError):
            _rendered = custom_template  # ignore bad placeholders; use raw
        system_msg = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on this specific homework submission.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from the student's work
- Reference prior weeks' concepts when relevant
- Do NOT give grades or scores
- Write in a mentoring tone

For THIS assignment, follow these custom instructions from the instructor:

{_rendered}
{lang_instr}"""
    else:
        system_msg = f"""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on homework submissions.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from their work to support each point
- When relevant, reference concepts from earlier weeks to show how the student is building on prior learning
- Note any improvements or growth patterns you see compared to prior feedback
- Do NOT give grades or scores
- Write in a mentoring, supportive tone
- Keep each bullet point concise (1-2 sentences)

You MUST structure your feedback EXACTLY as follows:

A brief encouraging opening sentence acknowledging their effort.

{"Lo que hiciste bien:" if lang == "es" else "What You Did Well:"}
- [specific strength with example from their work]
- [specific strength with example from their work]
- [specific strength with example from their work]

{"Areas de crecimiento:" if lang == "es" else "Areas for Growth:"}
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]

A brief closing sentence with encouragement and motivation to keep going.{lang_instr}"""
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_{submission_id}",
            system_message=system_msg
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Please review this student's homework submission and provide structured feedback.

ASSIGNMENT: {title}
{f"DESCRIPTION: {description}" if description else ""}

CURRENT WEEK CONTEXT (Week {week_number} materials):
{context_text[:6000] if context_text else "No additional context available."}

PRIOR WEEKS CONTEXT (earlier course materials + student's previous feedback):
{cumulative_ctx[:5000] if cumulative_ctx else "This is the student's first submission — no prior context."}

STUDENT SUBMISSION:
{submission_text[:10000]}

Provide feedback with exactly 3 bullet points under "What You Did Well:" and exactly 3 bullet points under "Areas for Growth:". Use specific examples from their submission. When possible, reference how this builds on earlier weeks."""

        message = UserMessage(text=prompt)
        feedback = await chat.send_message(message)
        
    except Exception as e:
        logger.error(f"AI review error: {e}")
        raise HTTPException(status_code=500, detail=f"AI review failed: {str(e)}")
    
    # Save feedback as DRAFT (Human-in-the-loop: instructor must review before sending)
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {
            "ai_feedback": feedback,
            "status": "draft",  # Changed from "reviewed" to "draft"
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # Self-paced mode: if the cohort has auto_send_feedback enabled, skip the review
    # step and deliver the AI feedback directly to the student.
    cohort_for_autosend = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if cohort_for_autosend and cohort_for_autosend.get("auto_send_feedback"):
        try:
            await send_feedback_to_student(submission_id, user)
            return {"feedback": feedback, "message": "AI feedback generated and auto-sent to student (self-paced mode).", "status": "sent"}
        except Exception as e:
            logger.error(f"auto_send after review failed for {submission_id}: {e}")
            # Fall through — feedback saved as draft, instructor can manually send

    return {"feedback": feedback, "message": "AI feedback generated. Review and edit before sending to student.", "status": "draft"}

@api_router.put("/submissions/{submission_id}/feedback")
async def update_feedback(submission_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Update/edit feedback before sending to student (Human-in-the-loop)"""
    data = await request.json()
    feedback = data.get("feedback")
    
    if not feedback:
        raise HTTPException(status_code=400, detail="Feedback is required")
    
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update with instructor's edited feedback
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {
            "instructor_feedback": feedback,
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Feedback updated"}

@api_router.post("/submissions/{submission_id}/send-feedback")
async def send_feedback_to_student(submission_id: str, user: dict = Depends(require_instructor)):
    """Send feedback to student via email (Human-in-the-loop final step)"""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Use instructor's edited feedback if available, otherwise use AI feedback
    feedback = submission.get("instructor_feedback") or submission.get("ai_feedback")
    if not feedback:
        raise HTTPException(status_code=400, detail="No feedback to send. Generate AI feedback first.")
    
    # Get student and material info
    student = await db.users.find_one({"user_id": submission["student_id"]}, {"_id": 0})
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0}) if submission.get("material_id") else None
    instructor = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Resolve human-readable title + week for the email. Prefer milestone-based (new model).
    assignment_title = None
    week_num_display: Any = "?"
    if submission.get("assignment_id") and submission.get("milestone_id"):
        asgn = await db.assignments.find_one({"assignment_id": submission["assignment_id"]}, {"_id": 0, "title": 1, "milestones": 1})
        if asgn:
            assignment_title = asgn.get("title") or "Assignment"
            ms = next((m for m in (asgn.get("milestones") or []) if m.get("milestone_id") == submission["milestone_id"]), None)
            if ms and ms.get("week_number"):
                week_num_display = ms["week_number"]
    if assignment_title is None:
        assignment_title = (material or {}).get("title") or "Homework"
        if (material or {}).get("week_number"):
            week_num_display = material["week_number"]
    
    # Get student's language preference for email
    lang = student.get("language_preference", "en")
    t = get_feedback_email_strings(lang)
    
    # Send email to student
    feedback_html = feedback.replace("\n", "<br>")
    coach_max_url = f"{APP_BASE_URL}/coach-max/{submission_id}"
    email_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">{t['heading']}</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px;">
            <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                {t['greeting']} <strong>{student['name'].split()[0]}</strong>,
            </p>
            <p style="color: #5A5A5A; font-size: 14px; margin-bottom: 16px;">
                {t['body']} <strong>{assignment_title}</strong> 
                ({t['week']} {week_num_display}).
            </p>
            <div style="background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="color: #166534; font-size: 15px; line-height: 1.7; margin: 0;">
                    {feedback_html}
                </p>
            </div>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{coach_max_url}" style="display: inline-block; background-color: #22438E; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600;">
                    {t['cta']}
                </a>
                <p style="color: #888; font-size: 12px; margin-top: 8px;">{t['cta_sub']}</p>
            </div>
            <p style="color: #5A5A5A; font-size: 14px; margin-top: 20px;">
                {t['closing']}<br>
                — {instructor['name'] if instructor else 'Your Instructor'}
            </p>
        </div>
        <div style="background-color: #E5E5E5; padding: 16px; border-radius: 0 0 12px 12px; text-align: center;">
            <p style="color: #888; font-size: 12px; margin: 0;">
                The Boost Pad &middot; {cohort['name']}
            </p>
        </div>
    </div>
    """
    
    await send_email_notification(
        student["email"],
        f"Feedback on {assignment_title} - {cohort['name']}",
        email_html
    )
    
    # Update submission status
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {
            "status": "sent",
            "feedback_sent": True,
            "sent_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Feedback sent to student"}

# ==================== PDF EXPORT ====================

@api_router.post("/submissions/{submission_id}/export-pdf")
async def export_feedback_pdf(submission_id: str, user: dict = Depends(require_instructor)):
    """Generate a branded PDF with AI feedback and email it to the student. Returns the PDF for instructor download."""
    from fpdf import FPDF
    import base64
    import tempfile
    
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    feedback = submission.get("instructor_feedback") or submission.get("ai_feedback")
    if not feedback:
        raise HTTPException(status_code=400, detail="No feedback available. Generate AI feedback first.")
    
    student = await db.users.find_one({"user_id": submission["student_id"]}, {"_id": 0})
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    instructor = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    student_name = student.get("name", "Student")
    material_title = material.get("title", "Homework") if material else "Homework"
    week_num = material.get("week_number", "?") if material else "?"
    cohort_name = cohort.get("name", "")
    instructor_name = instructor.get("name", "Your Instructor") if instructor else "Your Instructor"
    coach_max_url = f"{APP_BASE_URL}/coach-max/{submission_id}"
    logger.info(f"Coach Max URL generated: {coach_max_url}")
    pdf_lang = student.get("language_preference", "en")
    pdf_t = get_feedback_email_strings(pdf_lang)
    
    # Sanitize text for PDF - replace unicode chars then encode to latin-1
    def safe_text(text):
        text = text.replace("\u2022", "-")   # bullet
        text = text.replace("\u2013", "-")   # en-dash
        text = text.replace("\u2014", "-")   # em-dash
        text = text.replace("\u2018", "'")   # left single quote
        text = text.replace("\u2019", "'")   # right single quote
        text = text.replace("\u201c", '"')   # left double quote
        text = text.replace("\u201d", '"')   # right double quote
        text = text.replace("\u2026", "...")  # ellipsis
        return text.encode("latin-1", "replace").decode("latin-1")
    
    # fpdf2 v2.8.7: multi_cell(w=0) doesn't reset x to left margin, causing
    # "Not enough horizontal space" on subsequent calls.  Use explicit width.
    CW = 190  # content width = 210mm page - 10mm left - 10mm right margin
    
    # Build PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)
    
    # Header bar
    pdf.set_fill_color(34, 67, 142)
    pdf.rect(0, 0, 210, 35, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_y(10)
    pdf.cell(CW, 10, "The Boost Pad", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(CW, 6, "Feedback Report", align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(15)
    
    # Student info section
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(CW, 8, safe_text(f"Student: {student_name}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(CW, 6, safe_text(f"Assignment: {material_title}  |  Week {week_num}  |  {cohort_name}"), new_x="LMARGIN", new_y="NEXT")
    if submission.get("submitted_at"):
        pdf.cell(CW, 6, f"Submitted: {submission['submitted_at'][:10]}", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(5)
    
    # Divider
    pdf.set_draw_color(184, 212, 232)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)
    
    # Feedback section
    pdf.set_text_color(34, 67, 142)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(CW, 8, "Coach Max Feedback", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    
    # Feedback body
    pdf.set_text_color(30, 30, 30)
    pdf.set_font("Helvetica", "", 11)
    
    for line in feedback.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue
        line_safe = safe_text(line).replace("**", "")
        if line_safe.endswith(":") and len(line_safe) < 40:
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(w=CW, h=6, text=line_safe, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
        else:
            pdf.multi_cell(w=CW, h=6, text=line_safe, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)
    
    # Coach Max CTA
    pdf.set_fill_color(225, 240, 255)
    pdf.set_draw_color(184, 212, 232)
    y_before = pdf.get_y()
    pdf.rect(10, y_before, 190, 28, "DF")
    pdf.set_y(y_before + 4)
    pdf.set_text_color(34, 67, 142)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(CW, 7, "Have questions about this feedback?", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(26, 117, 186)
    url_display = coach_max_url if len(coach_max_url) < 80 else coach_max_url[:77] + "..."
    pdf.cell(CW, 7, safe_text("Chat with Coach Max: " + url_display), align="C", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)
    
    # Footer
    pdf.set_text_color(150, 150, 150)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(CW, 6, safe_text(f"Reviewed by {instructor_name}  |  The Boost Pad  |  {cohort_name}"), align="C", new_x="LMARGIN", new_y="NEXT")
    
    # Save PDF to temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        pdf.output(tmp.name)
        tmp_path = tmp.name
    
    # Read PDF bytes for email attachment
    with open(tmp_path, "rb") as f:
        pdf_bytes = f.read()
    
    pdf_filename = f"Feedback_{student_name.replace(' ', '_')}_Week{week_num}.pdf"
    
    # Send email with PDF attachment to student
    if resend.api_key:
        try:
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            _branding = await get_branding()
            _sender_name = _branding.get("email_sender_name") or "The Boost Pad"
            email_params = {
                "from": f"{_sender_name} <{SENDER_EMAIL}>",
                "to": [student["email"]],
                "subject": f"{'Tu Reporte de Retroalimentacion' if pdf_lang == 'es' else 'Your Feedback Report'}: {material_title} - {pdf_t['week']} {week_num}",
                "html": f"""
                <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
                        <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">{"Tu Reporte de Retroalimentacion" if pdf_lang == "es" else "Your Feedback Report"}</h1>
                    </div>
                    <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
                        <p style="color: #1A1A1A; font-size: 16px;">
                            {pdf_t['greeting']} <strong>{student_name.split()[0]}</strong>,
                        </p>
                        <p style="color: #5A5A5A; font-size: 14px;">
                            {"Tu retroalimentacion para" if pdf_lang == "es" else "Your feedback for"} <strong>{material_title}</strong> ({pdf_t['week']} {week_num}) {"esta adjunta como PDF." if pdf_lang == "es" else "is attached as a PDF."}
                        </p>
                        <div style="text-align: center; margin: 24px 0;">
                            <a href="{coach_max_url}" style="display: inline-block; background-color: #22438E; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600;">
                                {pdf_t['cta']}
                            </a>
                            <p style="color: #888; font-size: 12px; margin-top: 8px;">{pdf_t['cta_sub']}</p>
                        </div>
                        <p style="color: #888; font-size: 13px;">{cohort_name} &middot; The Boost Pad</p>
                    </div>
                </div>
                """,
                "attachments": [{"filename": pdf_filename, "content": pdf_b64}]
            }
            if NOTIFICATION_EMAIL and NOTIFICATION_EMAIL.lower() != student["email"].lower():
                email_params["cc"] = [NOTIFICATION_EMAIL]
            
            await asyncio.to_thread(resend.Emails.send, email_params)
            logger.info(f"Feedback PDF emailed to {student['email']}")
        except Exception as e:
            error_msg = str(e)
            if hasattr(e, 'status_code'):
                error_msg = f"Status {e.status_code}: {error_msg}"
            if hasattr(e, 'message'):
                error_msg = f"{error_msg} | {e.message}"
            logger.error(f"Failed to email PDF to {student['email']}: {error_msg}")
            logger.error(f"Email params - from: {email_params.get('from')}, to: {email_params.get('to')}, cc: {email_params.get('cc')}")
    
    # Clean up temp file
    os.unlink(tmp_path)
    
    # Mark submission as sent (consolidates the old send-feedback flow)
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {
            "status": "sent",
            "feedback_sent": True,
            "sent_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Return PDF as download for instructor
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'}
    )

# ==================== AUDIO TTS ENDPOINTS ====================

AUDIO_DIR = ROOT_DIR / "uploads" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

@api_router.post("/submissions/{submission_id}/audio")
async def generate_feedback_audio(submission_id: str, user: dict = Depends(get_current_user)):
    """Generate audio of feedback using OpenAI TTS. Caches the result."""
    from emergentintegrations.llm.openai import OpenAITextToSpeech

    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    feedback = submission.get("instructor_feedback") or submission.get("ai_feedback")
    if not feedback:
        raise HTTPException(status_code=400, detail="No feedback available")

    # Check cache (must have gridfs_id OR disk file still present)
    audio_key = f"feedback_{submission_id}"
    existing = await db.audio_cache.find_one({"audio_key": audio_key}, {"_id": 0})
    if existing:
        if existing.get("gridfs_id") or (AUDIO_DIR / existing["filename"]).exists():
            return {"audio_url": f"/api/audio/{existing['filename']}", "cached": True}
        # Stale cache — file is gone after redeploy. Drop the stale record and regenerate below.
        await db.audio_cache.delete_one({"audio_key": audio_key})

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")

    # Trim to 4096 char limit
    text = feedback[:4096]

    try:
        tts = OpenAITextToSpeech(api_key=api_key)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1",
            voice="echo",
            response_format="mp3"
        )
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {str(e)}")

    filename = f"{audio_key}_{uuid.uuid4().hex[:8]}.mp3"
    gridfs_id = await save_bytes_to_gridfs(audio_bytes, filename)

    await db.audio_cache.insert_one({
        "audio_key": audio_key,
        "filename": filename,
        "gridfs_id": gridfs_id,
        "submission_id": submission_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {"audio_url": f"/api/audio/{filename}", "cached": False}


@api_router.post("/chat/audio")
async def generate_chat_audio(request: Request, user: dict = Depends(get_current_user)):
    """Generate audio for a Coach Max chat response."""
    from emergentintegrations.llm.openai import OpenAITextToSpeech

    data = await request.json()
    text = data.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")

    text = text[:4096]

    try:
        tts = OpenAITextToSpeech(api_key=api_key)
        audio_bytes = await tts.generate_speech(
            text=text,
            model="tts-1",
            voice="echo",
            response_format="mp3"
        )
    except Exception as e:
        logger.error(f"Chat TTS error: {e}")
        raise HTTPException(status_code=500, detail=f"Audio generation failed: {str(e)}")

    filename = f"chat_{uuid.uuid4().hex[:12]}.mp3"
    gridfs_id = await save_bytes_to_gridfs(audio_bytes, filename)
    await db.audio_cache.insert_one({
        "audio_key": f"chat_{filename}",
        "filename": filename,
        "gridfs_id": gridfs_id,
        "submission_id": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return {"audio_url": f"/api/audio/{filename}"}


@api_router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve a generated audio file (from GridFS, falls back to legacy disk cache)."""
    cache = await db.audio_cache.find_one({"filename": filename}, {"_id": 0})
    if cache and cache.get("gridfs_id"):
        audio_bytes = await read_bytes_from_doc(cache)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(audio_bytes)),
                "Cache-Control": "private, max-age=3600",
                "Accept-Ranges": "none",
            }
        )
    # Legacy disk fallback
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        str(filepath),
        media_type="audio/mpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )

# ==================== COACH MAX INSIGHTS ENDPOINTS ====================

@api_router.get("/cohorts/{cohort_id}/coach-max-report")
async def get_coach_max_report(cohort_id: str, user: dict = Depends(require_instructor)):
    """Get raw Coach Max chat data grouped by week for a cohort."""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    # Get all submissions for this cohort
    submissions = await db.submissions.find(
        {"cohort_id": cohort_id},
        {"_id": 0, "submission_id": 1, "material_id": 1, "student_id": 1}
    ).to_list(1000)

    if not submissions:
        return {"weeks": [], "total_questions": 0}

    sub_map = {s["submission_id"]: s for s in submissions}
    sub_ids = list(sub_map.keys())

    # Get all chats for these submissions
    chats = await db.tutor_chats.find(
        {"submission_id": {"$in": sub_ids}},
        {"_id": 0}
    ).sort("created_at", 1).to_list(5000)

    if not chats:
        return {"weeks": [], "total_questions": 0}

    # Get material info for week numbers
    material_ids = list(set(s.get("material_id") for s in submissions if s.get("material_id")))
    materials = await db.materials.find(
        {"material_id": {"$in": material_ids}},
        {"_id": 0, "material_id": 1, "week_number": 1, "title": 1}
    ).to_list(100)
    mat_map = {m["material_id"]: m for m in materials}

    # Get student names
    student_ids = list(set(s.get("student_id") for s in submissions if s.get("student_id")))
    students = await db.users.find(
        {"user_id": {"$in": student_ids}},
        {"_id": 0, "user_id": 1, "name": 1}
    ).to_list(500)
    stu_map = {s["user_id"]: s.get("name", "Unknown") for s in students}

    # Group chats by week
    weeks_data = {}
    for chat in chats:
        sub = sub_map.get(chat.get("submission_id"), {})
        mat = mat_map.get(sub.get("material_id"), {})
        week_num = mat.get("week_number", 0)
        if week_num not in weeks_data:
            weeks_data[week_num] = {
                "week_number": week_num,
                "material_title": mat.get("title", "Unknown"),
                "questions": [],
                "student_count": set()
            }
        weeks_data[week_num]["questions"].append({
            "student_name": stu_map.get(chat.get("student_id"), "Unknown"),
            "question": chat.get("message", ""),
            "response": chat.get("response", ""),
            "created_at": chat.get("created_at", "")
        })
        weeks_data[week_num]["student_count"].add(chat.get("student_id"))

    # Convert sets to counts and sort
    weeks = []
    total_q = 0
    for wk in sorted(weeks_data.keys()):
        d = weeks_data[wk]
        total_q += len(d["questions"])
        weeks.append({
            "week_number": d["week_number"],
            "material_title": d["material_title"],
            "question_count": len(d["questions"]),
            "unique_students": len(d["student_count"]),
            "questions": d["questions"]
        })

    return {"weeks": weeks, "total_questions": total_q}


@api_router.post("/cohorts/{cohort_id}/coach-max-report/generate")
async def generate_coach_max_insights(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Use AI to analyze Coach Max questions and generate insights per week."""
    data = await request.json()
    week_number = data.get("week_number")

    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")

    # Get submissions for this cohort (optionally filtered by week)
    sub_query = {"cohort_id": cohort_id}
    submissions = await db.submissions.find(sub_query, {"_id": 0, "submission_id": 1, "material_id": 1}).to_list(1000)
    sub_map = {s["submission_id"]: s for s in submissions}

    if week_number:
        # Filter to specific week
        material_ids = list(set(s.get("material_id") for s in submissions))
        materials = await db.materials.find(
            {"material_id": {"$in": material_ids}, "week_number": week_number},
            {"_id": 0, "material_id": 1}
        ).to_list(100)
        valid_mat_ids = set(m["material_id"] for m in materials)
        valid_sub_ids = [sid for sid, s in sub_map.items() if s.get("material_id") in valid_mat_ids]
    else:
        valid_sub_ids = list(sub_map.keys())

    chats = await db.tutor_chats.find(
        {"submission_id": {"$in": valid_sub_ids}},
        {"_id": 0, "message": 1}
    ).to_list(5000)

    if not chats:
        return {"summary": "No Coach Max conversations found for this period.", "themes": [], "recommendations": []}

    questions_text = "\n".join([f"- {c['message']}" for c in chats])

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")

    try:
        import json as json_mod
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat_ai = LlmChat(
            api_key=api_key,
            session_id=f"insights_{cohort_id}_{week_number or 'all'}_{uuid.uuid4().hex[:6]}",
            system_message="""You are an analytics assistant for an educational platform. 
Analyze student questions asked to an AI tutor after receiving homework feedback.
Your goal is to help instructors understand what students are struggling with and what they're curious about.

You MUST respond in valid JSON with this exact structure:
{
  "summary": "A 2-3 sentence overview of what students are asking about",
  "themes": [
    {"theme": "Theme name", "count": <number of questions about this>, "examples": ["example question 1", "example question 2"]},
  ],
  "recommendations": ["Actionable recommendation 1 for the instructor", "Recommendation 2"]
}

Keep themes to 3-5 max. Be specific and actionable in recommendations."""
        ).with_model("openai", "gpt-5.2")

        week_label = f"Week {week_number}" if week_number else "all weeks"
        prompt = f"""Analyze these {len(chats)} student questions from {week_label} in the "{cohort['name']}" cohort:

{questions_text[:8000]}

Identify the main themes, count how many questions relate to each theme, provide example questions, and give actionable recommendations for the instructor."""

        result = await chat_ai.send_message(UserMessage(text=prompt))

        # Parse JSON from response
        # Strip markdown code fences if present
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()

        parsed = json_mod.loads(cleaned)
        return parsed

    except json_mod.JSONDecodeError:
        return {"summary": result, "themes": [], "recommendations": []}
    except Exception as e:
        logger.error(f"Insights generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate insights: {str(e)}")


# ==================== WEEKLY DIGEST ====================

DIGEST_RECIPIENT = "info@theboostpad.org"

async def generate_weekly_digest():
    """Generate and email a weekly Coach Max insights digest for all active cohorts."""
    logger.info("Starting weekly Coach Max digest generation...")
    
    cohorts = await db.cohorts.find({}, {"_id": 0}).to_list(100)
    if not cohorts:
        logger.info("No cohorts found, skipping digest.")
        return

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    cohort_sections = []
    total_questions_all = 0

    for cohort in cohorts:
        cid = cohort["cohort_id"]
        
        # Get submissions for this cohort
        submissions = await db.submissions.find(
            {"cohort_id": cid}, {"_id": 0, "submission_id": 1, "material_id": 1}
        ).to_list(1000)
        if not submissions:
            continue
        
        sub_ids = [s["submission_id"] for s in submissions]
        
        # Get chats from the last 7 days
        recent_chats = await db.tutor_chats.find(
            {"submission_id": {"$in": sub_ids}, "created_at": {"$gte": week_ago.isoformat()}},
            {"_id": 0, "message": 1, "submission_id": 1}
        ).to_list(5000)
        
        if not recent_chats:
            continue
        
        total_questions_all += len(recent_chats)
        
        # Get material info for week numbers
        sub_map = {s["submission_id"]: s for s in submissions}
        mat_ids = list(set(s.get("material_id") for s in submissions if s.get("material_id")))
        materials = await db.materials.find(
            {"material_id": {"$in": mat_ids}}, {"_id": 0, "material_id": 1, "week_number": 1, "title": 1}
        ).to_list(100)
        mat_map = {m["material_id"]: m for m in materials}

        # Group by week
        week_questions = {}
        for chat in recent_chats:
            sub = sub_map.get(chat.get("submission_id"), {})
            mat = mat_map.get(sub.get("material_id"), {})
            wk = mat.get("week_number", 0)
            title = mat.get("title", "Unknown")
            if wk not in week_questions:
                week_questions[wk] = {"title": title, "questions": []}
            week_questions[wk]["questions"].append(chat["message"])

        # Generate AI summary if we have an API key
        ai_summary = ""
        if api_key and len(recent_chats) > 0:
            try:
                from emergentintegrations.llm.chat import LlmChat, UserMessage
                questions_text = "\n".join([f"- {c['message']}" for c in recent_chats])
                chat_ai = LlmChat(
                    api_key=api_key,
                    session_id=f"digest_{cid}_{uuid.uuid4().hex[:6]}",
                    system_message="""You are an analytics assistant. Summarize student questions to their AI tutor in 2-3 concise sentences. Highlight the main themes and any areas where students seem confused. Keep it brief and actionable for instructors."""
                ).with_model("openai", "gpt-5.2")
                ai_summary = await chat_ai.send_message(
                    UserMessage(text=f"Summarize these {len(recent_chats)} student questions:\n{questions_text[:6000]}")
                )
            except Exception as e:
                logger.error(f"Digest AI summary failed for {cid}: {e}")
                ai_summary = f"{len(recent_chats)} questions received this week."

        # Build HTML section for this cohort
        weeks_html = ""
        for wk in sorted(week_questions.keys()):
            wd = week_questions[wk]
            q_list = "".join([f"<li style='color:#333;font-size:13px;margin-bottom:4px;'>\"{q}\"</li>" for q in wd["questions"][:5]])
            extra = f"<li style='color:#999;font-size:12px;'>...and {len(wd['questions'])-5} more</li>" if len(wd["questions"]) > 5 else ""
            weeks_html += f"""
            <div style="margin-bottom:16px;">
                <p style="font-weight:600;color:#22438E;font-size:14px;margin:0 0 6px 0;">Week {wk}: {wd['title']} ({len(wd['questions'])} questions)</p>
                <ul style="margin:0;padding-left:20px;">{q_list}{extra}</ul>
            </div>"""

        section = f"""
        <div style="background:#fff;border:1px solid #D0E6F9;border-radius:12px;padding:20px;margin-bottom:20px;">
            <h2 style="color:#000;font-size:18px;margin:0 0 4px 0;">{cohort['name']}</h2>
            <p style="color:#666;font-size:13px;margin:0 0 16px 0;">{len(recent_chats)} questions this week</p>
            {f'<div style="background:#F0F9FF;border:1px solid #BAE6FD;border-radius:8px;padding:14px;margin-bottom:16px;"><p style="color:#22438E;font-weight:600;font-size:12px;margin:0 0 6px 0;">AI SUMMARY</p><p style="color:#333;font-size:14px;line-height:1.6;margin:0;">{ai_summary}</p></div>' if ai_summary else ''}
            {weeks_html}
        </div>"""
        cohort_sections.append(section)

    if not cohort_sections:
        logger.info("No Coach Max activity this week, skipping digest email.")
        return

    # Build full email
    today = datetime.now(timezone.utc)
    week_start = (today - timedelta(days=7)).strftime("%b %d")
    week_end = today.strftime("%b %d, %Y")
    
    email_html = f"""
    <div style="font-family:'Inter',Arial,sans-serif;max-width:640px;margin:0 auto;padding:20px;">
        <div style="background:#22438E;padding:24px;border-radius:12px 12px 0 0;">
            <h1 style="color:#fff;margin:0;font-size:22px;">Coach Max Weekly Digest</h1>
            <p style="color:#94B8D9;font-size:13px;margin:6px 0 0 0;">{week_start} — {week_end}</p>
        </div>
        <div style="background:#EDF5FA;padding:24px;border-radius:0 0 12px 12px;">
            <p style="color:#333;font-size:15px;margin:0 0 20px 0;">
                Here's what your students asked Coach Max this week across all cohorts.
                <strong>{total_questions_all} total questions</strong> were asked.
            </p>
            {''.join(cohort_sections)}
            <div style="text-align:center;margin-top:24px;">
                <a href="{APP_BASE_URL}/dashboard" style="display:inline-block;background:#22438E;color:#fff;text-decoration:none;padding:12px 28px;border-radius:8px;font-size:14px;font-weight:600;">
                    View Full Insights
                </a>
            </div>
            <p style="color:#999;font-size:12px;text-align:center;margin-top:20px;">
                The Boost Pad &middot; Weekly Coach Max Digest
            </p>
        </div>
    </div>"""

    await send_email_notification(
        DIGEST_RECIPIENT,
        f"Coach Max Weekly Digest — {week_start} to {week_end}",
        email_html
    )
    logger.info(f"Weekly digest sent to {DIGEST_RECIPIENT} with {total_questions_all} questions across {len(cohort_sections)} cohorts")


async def weekly_digest_scheduler():
    """Background task that sends weekly digest every Monday at 9 AM UTC."""
    while True:
        now = datetime.now(timezone.utc)
        # Calculate next Monday 9 AM UTC
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= 9:
            days_until_monday = 7
        next_monday = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=days_until_monday)
        wait_seconds = (next_monday - now).total_seconds()
        logger.info(f"Next weekly digest scheduled for {next_monday.isoformat()} ({wait_seconds/3600:.1f}h from now)")
        await asyncio.sleep(wait_seconds)
        try:
            await generate_weekly_digest()
        except Exception as e:
            logger.error(f"Weekly digest failed: {e}")


@api_router.post("/admin/send-weekly-digest")
async def trigger_weekly_digest(user: dict = Depends(require_instructor)):
    """Manually trigger the weekly Coach Max digest email."""
    asyncio.create_task(generate_weekly_digest())
    return {"message": f"Weekly digest is being generated and will be sent to {DIGEST_RECIPIENT}"}


# ==================== UTILITY ENDPOINTS ====================

@api_router.get("/")
async def root():
    return {"message": "The Boost Pad API"}

@api_router.get("/health")
async def health():
    has_key = bool(resend.api_key)
    return {
        "status": "healthy",
        "email_sender": SENDER_EMAIL,
        "resend_key_prefix": (resend.api_key[:8] + "...") if resend.api_key else "NOT SET",
        "email_ready": has_key and bool(SENDER_EMAIL)
    }

@api_router.get("/debug/submission/{submission_id}")
async def debug_submission(submission_id: str):
    """Public diagnostic: shows submission -> material -> week chain"""
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        return {"error": "Submission not found"}
    material = await db.materials.find_one({"material_id": submission.get("material_id")}, {"_id": 0})
    return {
        "submission_id": submission_id,
        "material_id": submission.get("material_id"),
        "material_title": material.get("title") if material else None,
        "material_week_number": material.get("week_number") if material else None,
        "cohort_id": submission.get("cohort_id"),
        "status": submission.get("status")
    }

@api_router.get("/email-diagnostic")
async def email_diagnostic(user: dict = Depends(require_instructor)):
    """Check email configuration — instructor/admin only"""
    has_key = bool(resend.api_key)
    key_prefix = resend.api_key[:8] + "..." if resend.api_key else "NOT SET"
    return {
        "sender_email": SENDER_EMAIL,
        "notification_email": NOTIFICATION_EMAIL,
        "resend_api_key_set": has_key,
        "resend_api_key_prefix": key_prefix,
        "status": "ok" if has_key and SENDER_EMAIL else "misconfigured"
    }

# Include the router (AFTER all route definitions)
# app.include_router moved to end of file

# ==================== THINKIFIC INTEGRATION ====================

THINKIFIC_BASE_URL = "https://api.thinkific.com/api/public/v1"
THINKIFIC_HEADERS = {
    "X-Auth-API-Key": THINKIFIC_API_KEY,
    "X-Auth-Subdomain": THINKIFIC_SUBDOMAIN,
    "Content-Type": "application/json"
}

async def thinkific_get(path: str, params: dict = None) -> dict:
    """Make GET request to Thinkific API"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{THINKIFIC_BASE_URL}{path}",
            headers=THINKIFIC_HEADERS,
            params=params,
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

@api_router.get("/thinkific/courses")
async def get_thinkific_courses(user: dict = Depends(require_instructor)):
    """List all courses from Thinkific"""
    if not THINKIFIC_API_KEY:
        raise HTTPException(status_code=400, detail="Thinkific API not configured")
    data = await thinkific_get("/courses", {"limit": 50})
    courses = []
    for c in data.get("items", []):
        courses.append({
            "id": c["id"],
            "name": c["name"],
            "slug": c.get("slug"),
            "description": c.get("description", ""),
            "chapter_ids": c.get("chapter_ids", []),
            "image_url": c.get("course_card_image_url", "")
        })
    return courses

@api_router.get("/thinkific/courses/{course_id}/chapters")
async def get_thinkific_chapters(course_id: int, user: dict = Depends(require_instructor)):
    """List chapters (weeks) for a Thinkific course"""
    if not THINKIFIC_API_KEY:
        raise HTTPException(status_code=400, detail="Thinkific API not configured")
    data = await thinkific_get(f"/courses/{course_id}/chapters")
    chapters = []
    for ch in data.get("items", []):
        chapters.append({
            "id": ch["id"],
            "name": ch["name"],
            "position": ch.get("position"),
            "content_ids": ch.get("content_ids", [])
        })
    return chapters

@api_router.get("/thinkific/enrollments")
async def get_thinkific_enrollments(course_id: int = None, user: dict = Depends(require_instructor)):
    """List enrollments from Thinkific, optionally filtered by course"""
    if not THINKIFIC_API_KEY:
        raise HTTPException(status_code=400, detail="Thinkific API not configured")
    params = {"limit": 100}
    if course_id:
        params["course_id"] = course_id
    data = await thinkific_get("/enrollments", params)
    enrollments = []
    for e in data.get("items", []):
        enrollments.append({
            "id": e["id"],
            "user_id": e.get("user_id"),
            "user_name": e.get("user_name"),
            "user_email": e.get("user_email"),
            "course_id": e.get("course_id"),
            "course_name": e.get("course_name"),
            "percentage_completed": e.get("percentage_completed", 0),
            "completed": e.get("completed", False),
            "started_at": e.get("started_at"),
            "completed_at": e.get("completed_at")
        })
    return enrollments

@api_router.post("/thinkific/sync-students/{cohort_id}")
async def sync_thinkific_students(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Sync Thinkific course enrollments to a Coach Max cohort"""
    if not THINKIFIC_API_KEY:
        raise HTTPException(status_code=400, detail="Thinkific API not configured")
    
    data = await request.json()
    course_id = data.get("course_id")
    if not course_id:
        raise HTTPException(status_code=400, detail="course_id required")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Save the Thinkific course mapping
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$set": {"thinkific_course_id": course_id}}
    )
    
    # Get all enrollments for this course
    all_enrollments = []
    page = 1
    while True:
        enroll_data = await thinkific_get("/enrollments", {"course_id": course_id, "limit": 100, "page": page})
        items = enroll_data.get("items", [])
        all_enrollments.extend(items)
        if len(items) < 100:
            break
        page += 1
    
    synced = 0
    created = 0
    
    for enrollment in all_enrollments:
        email = enrollment.get("user_email", "").lower().strip()
        if not email:
            continue
        
        # Find or create user in Coach Max
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        if existing_user:
            user_id = existing_user["user_id"]
        else:
            user_id = f"user_{uuid.uuid4().hex[:12]}"
            new_user = {
                "user_id": user_id,
                "email": email,
                "name": enrollment.get("user_name", email.split("@")[0]),
                "role": "student",
                "picture": "",
                "thinkific_user_id": enrollment.get("user_id")
            }
            await db.users.insert_one(new_user)
            created += 1
        
        # Store Thinkific user ID mapping
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"thinkific_user_id": enrollment.get("user_id")}}
        )
        
        # Add to cohort if not already a member
        if user_id not in cohort.get("student_ids", []):
            await db.cohorts.update_one(
                {"cohort_id": cohort_id},
                {"$addToSet": {"student_ids": user_id}}
            )
            synced += 1
        
        # Store enrollment progress
        await db.thinkific_progress.update_one(
            {"cohort_id": cohort_id, "user_id": user_id, "thinkific_course_id": course_id},
            {"$set": {
                "thinkific_enrollment_id": enrollment.get("id"),
                "percentage_completed": enrollment.get("percentage_completed", 0),
                "completed": enrollment.get("completed", False),
                "started_at": enrollment.get("started_at"),
                "completed_at": enrollment.get("completed_at"),
                "synced_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
    
    return {
        "message": f"Synced {synced} new students, created {created} new accounts. {len(all_enrollments)} total enrollments found.",
        "total_enrollments": len(all_enrollments),
        "new_students_added": synced,
        "new_accounts_created": created
    }

@api_router.get("/thinkific/progress/{cohort_id}")
async def get_thinkific_progress(cohort_id: str, user: dict = Depends(require_instructor)):
    """Get Thinkific progress for students in a cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    progress = await db.thinkific_progress.find(
        {"cohort_id": cohort_id},
        {"_id": 0}
    ).to_list(500)
    
    # Enrich with user names
    user_ids = list(set(p["user_id"] for p in progress))
    users = await db.users.find(
        {"user_id": {"$in": user_ids}},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1}
    ).to_list(500)
    user_map = {u["user_id"]: u for u in users}
    
    for p in progress:
        u = user_map.get(p["user_id"], {})
        p["student_name"] = u.get("name", "Unknown")
        p["student_email"] = u.get("email", "")
    
    return progress

@api_router.post("/thinkific/refresh-progress/{cohort_id}")
async def refresh_thinkific_progress(cohort_id: str, user: dict = Depends(require_instructor)):
    """Refresh Thinkific progress for a cohort by re-fetching enrollments"""
    if not THINKIFIC_API_KEY:
        raise HTTPException(status_code=400, detail="Thinkific API not configured")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    if not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    course_id = cohort.get("thinkific_course_id")
    if not course_id:
        raise HTTPException(status_code=400, detail="No Thinkific course linked to this cohort")
    
    # Get all enrollments for the linked course
    all_enrollments = []
    page = 1
    while True:
        enroll_data = await thinkific_get("/enrollments", {"course_id": course_id, "limit": 100, "page": page})
        items = enroll_data.get("items", [])
        all_enrollments.extend(items)
        if len(items) < 100:
            break
        page += 1
    
    updated = 0
    for enrollment in all_enrollments:
        email = enrollment.get("user_email", "").lower().strip()
        existing_user = await db.users.find_one({"email": email}, {"_id": 0})
        if not existing_user:
            continue
        
        await db.thinkific_progress.update_one(
            {"cohort_id": cohort_id, "user_id": existing_user["user_id"], "thinkific_course_id": course_id},
            {"$set": {
                "percentage_completed": enrollment.get("percentage_completed", 0),
                "completed": enrollment.get("completed", False),
                "started_at": enrollment.get("started_at"),
                "completed_at": enrollment.get("completed_at"),
                "synced_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=True
        )
        updated += 1
    
    return {"message": f"Refreshed progress for {updated} students", "updated": updated}

@api_router.post("/webhooks/thinkific")
async def thinkific_webhook(request: Request):
    """Receive webhooks from Thinkific (lesson completed, enrollment progress)"""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")
    
    resource = payload.get("resource")
    action = payload.get("action")
    data = payload.get("payload", {})
    
    logger.info(f"Thinkific webhook: {resource}.{action}")
    
    if resource == "enrollment" and action == "progress":
        course_id = data.get("course_id")
        user_email = data.get("user_email", "").lower().strip()
        percentage = data.get("percentage_completed", 0)
        
        if course_id and user_email:
            existing_user = await db.users.find_one({"email": user_email}, {"_id": 0})
            if existing_user:
                cohort = await db.cohorts.find_one(
                    {"thinkific_course_id": course_id, "student_ids": existing_user["user_id"]},
                    {"_id": 0}
                )
                if cohort:
                    await db.thinkific_progress.update_one(
                        {"cohort_id": cohort["cohort_id"], "user_id": existing_user["user_id"], "thinkific_course_id": course_id},
                        {"$set": {
                            "percentage_completed": percentage,
                            "completed": data.get("completed", False),
                            "synced_at": datetime.now(timezone.utc).isoformat()
                        }},
                        upsert=True
                    )
    
    elif resource == "lesson" and action == "completed":
        user_email = data.get("user_email", "").lower().strip()
        course_id = data.get("course_id")
        lesson_name = data.get("lesson_name", "")
        chapter_name = data.get("chapter_name", "")
        
        if user_email and course_id:
            existing_user = await db.users.find_one({"email": user_email}, {"_id": 0})
            if existing_user:
                await db.thinkific_events.insert_one({
                    "event_type": "lesson_completed",
                    "user_id": existing_user["user_id"],
                    "user_email": user_email,
                    "course_id": course_id,
                    "lesson_name": lesson_name,
                    "chapter_name": chapter_name,
                    "received_at": datetime.now(timezone.utc).isoformat()
                })
    
    return {"status": "ok"}

# Include the router AFTER all routes are defined
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def migrate_instructor_ids():
    """Migrate cohorts from instructor_id to instructor_ids array"""
    cohorts_to_migrate = await db.cohorts.find(
        {"instructor_ids": {"$exists": False}},
        {"_id": 0, "cohort_id": 1, "instructor_id": 1}
    ).to_list(100)
    for c in cohorts_to_migrate:
        iid = c.get("instructor_id")
        await db.cohorts.update_one(
            {"cohort_id": c["cohort_id"]},
            {"$set": {"instructor_ids": [iid] if iid else []}}
        )
    if cohorts_to_migrate:
        logger.info(f"Migrated {len(cohorts_to_migrate)} cohorts to instructor_ids")
    # Start weekly digest scheduler
    asyncio.create_task(weekly_digest_scheduler())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
