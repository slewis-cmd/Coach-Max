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
from typing import List, Optional
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


async def read_file_text(doc_or_path, file_name: str = None) -> str:
    """Read file and extract text. Accepts either a doc dict (preferred) or a legacy (file_path, file_name) pair.
    For video materials, returns the stored Whisper transcript."""
    try:
        if isinstance(doc_or_path, dict):
            doc = doc_or_path
            # Video materials: return stored transcript
            if doc.get("material_type") == "video":
                transcript = (doc.get("transcript") or "").strip()
                if transcript:
                    label = "VIDEO TRANSCRIPT"
                    if doc.get("video_url"):
                        label += f" ({doc.get('video_url')})"
                    return f"[{label}]\n{transcript}"
                return ""
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


async def transcribe_video_material(material_id: str) -> None:
    """Background task: pull video bytes from GridFS, extract mono 32kbps mp3 audio via ffmpeg, transcribe via Whisper, save transcript.
    Runs OUT-OF-BAND (fire-and-forget)."""
    import tempfile
    import subprocess
    try:
        material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
        if not material or not material.get("gridfs_id"):
            return
        
        file_bytes = await read_bytes_from_doc(material)
        file_ext = (material.get("file_name") or "video.mp4").split(".")[-1].lower()

        with tempfile.NamedTemporaryFile(suffix=f".{file_ext}", delete=False) as vid_tmp:
            vid_tmp.write(file_bytes)
            vid_path = vid_tmp.name

        audio_path = vid_path + ".mp3"
        try:
            # Extract audio: mono, 16 kHz, 32 kbps mp3 — Whisper-friendly, keeps ~60 min under 25 MB
            proc = await asyncio.to_thread(
                subprocess.run,
                ["ffmpeg", "-y", "-i", vid_path, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", audio_path],
                capture_output=True,
                timeout=600
            )
            if proc.returncode != 0:
                logger.error(f"ffmpeg failed for material {material_id}: {proc.stderr[:500].decode(errors='ignore')}")
                await db.materials.update_one(
                    {"material_id": material_id},
                    {"$set": {"transcription_status": "failed"}}
                )
                return

            # Whisper 25 MB limit
            audio_size = os.path.getsize(audio_path)
            if audio_size > 25 * 1024 * 1024:
                logger.error(f"Audio too large for Whisper ({audio_size} bytes) — material {material_id}")
                await db.materials.update_one(
                    {"material_id": material_id},
                    {"$set": {"transcription_status": "failed_too_large"}}
                )
                return

            api_key = os.environ.get("EMERGENT_LLM_KEY")
            if not api_key:
                logger.error("Whisper: EMERGENT_LLM_KEY not set")
                await db.materials.update_one(
                    {"material_id": material_id},
                    {"$set": {"transcription_status": "failed"}}
                )
                return

            from emergentintegrations.llm.openai import OpenAISpeechToText
            stt = OpenAISpeechToText(api_key=api_key)
            with open(audio_path, "rb") as audio_file:
                response = await stt.transcribe(
                    file=audio_file,
                    model="whisper-1",
                    response_format="text"
                )
            transcript_text = response if isinstance(response, str) else getattr(response, "text", "")
            await db.materials.update_one(
                {"material_id": material_id},
                {"$set": {
                    "transcript": (transcript_text or "").strip(),
                    "transcription_status": "done"
                }}
            )
            logger.info(f"Transcribed material {material_id}: {len(transcript_text or '')} chars")
        finally:
            for p in (vid_path, audio_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
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


async def build_coach_max_context(submission: dict, material: dict) -> tuple:
    """Build context strings for Coach Max AI tutor. Returns (submission_text, context_text)."""
    submission_text = await read_file_text(submission)
    
    context_text = ""
    if material:
        context_materials = await db.materials.find({
            "cohort_id": submission["cohort_id"],
            "week_number": material.get("week_number"),
            "material_type": {"$in": ["workbook", "case_study", "video"]}
        }, {"_id": 0}).to_list(10)
        
        for mat in context_materials:
            mat_text = await read_file_text(mat)
            if mat_text:
                context_text += f"\n--- {mat['title']} ---\n{mat_text[:3000]}"
    
    return submission_text, context_text


async def build_cumulative_context(student_id: str, cohort_id: str, current_week: int, max_chars: int = 6000) -> str:
    """Build cumulative context from all prior weeks: materials + student submissions + feedback.
    Always includes Course-Wide Resources (is_global=True) regardless of week."""
    parts = []
    total_chars = 0

    # Course-Wide Resources: always included, regardless of current week
    global_materials = await db.materials.find({
        "is_library": True,
        "is_global": True,
        "cohort_ids": cohort_id
    }, {"_id": 0}).to_list(20)

    for mat in global_materials:
        mat_text = await read_file_text(mat)
        excerpt = mat_text[:1200] if mat_text else ""
        if not excerpt:
            continue
        section = f"\n--- COURSE-WIDE RESOURCE: {mat.get('title', '')} ---\n{excerpt}"
        if total_chars + len(section) > max_chars:
            break
        parts.append(section)
        total_chars += len(section)

    # If it's Week 1, only global resources apply (no prior weeks)
    if not current_week or current_week <= 1:
        return "\n".join(parts) if parts else ""

    # Get all prior materials (weeks 1 to current_week-1)
    prior_materials = await db.materials.find({
        "cohort_ids": cohort_id,
        "week_number": {"$lt": current_week, "$gt": 0},
        "material_type": {"$in": ["workbook", "case_study", "video"]}
    }, {"_id": 0}).sort("week_number", 1).to_list(100)

    # Also check single cohort_id field for backwards compat
    if not prior_materials:
        prior_materials = await db.materials.find({
            "cohort_id": cohort_id,
            "week_number": {"$lt": current_week},
            "material_type": {"$in": ["workbook", "case_study", "video"]}
        }, {"_id": 0}).sort("week_number", 1).to_list(100)

    # Get all prior homework materials to find submissions
    prior_hw = await db.materials.find({
        "$or": [{"cohort_ids": cohort_id}, {"cohort_id": cohort_id}],
        "week_number": {"$lt": current_week},
        "material_type": "homework"
    }, {"_id": 0, "material_id": 1, "title": 1, "week_number": 1}).sort("week_number", 1).to_list(50)

    hw_ids = [m["material_id"] for m in prior_hw]
    hw_map = {m["material_id"]: m for m in prior_hw}

    # Get student's prior submissions + feedback
    prior_submissions = await db.submissions.find({
        "student_id": student_id,
        "material_id": {"$in": hw_ids}
    }, {"_id": 0, "material_id": 1, "ai_feedback": 1, "instructor_feedback": 1}).to_list(50)

    sub_by_mat = {s["material_id"]: s for s in prior_submissions}

    # Build summary per prior week (most recent weeks get more detail)
    weeks_seen = set()
    for mat in prior_materials:
        wk = mat.get("week_number")
        if wk in weeks_seen:
            continue
        weeks_seen.add(wk)

        # Summarize material topics (brief excerpt)
        mat_text = await read_file_text(mat)
        excerpt = mat_text[:800] if mat_text else ""

        section = f"\n--- Week {wk}: {mat.get('title', '')} ---\nTopics: {excerpt}"

        # Add student's feedback from that week if available
        hw_for_week = [h for h in prior_hw if h.get("week_number") == wk]
        for hw in hw_for_week:
            sub = sub_by_mat.get(hw["material_id"])
            if sub:
                fb = sub.get("instructor_feedback") or sub.get("ai_feedback") or ""
                if fb:
                    section += f"\nFeedback received: {fb[:600]}"

        if total_chars + len(section) > max_chars:
            break
        parts.append(section)
        total_chars += len(section)

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CohortCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CohortUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class Material(BaseModel):
    material_id: str = Field(default_factory=lambda: f"mat_{uuid.uuid4().hex[:12]}")
    cohort_id: str
    week_number: int
    material_type: str  # "workbook", "case_study", "homework"
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = ""
    gridfs_id: Optional[str] = None
    file_name: str
    uploaded_by: str
    due_date: Optional[str] = None  # ISO date string for homework assignments
    drive_folder_url: Optional[str] = ""  # Google Drive folder URL for homework submissions
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Submission(BaseModel):
    submission_id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    material_id: str
    cohort_id: str
    student_id: str
    file_path: Optional[str] = ""
    gridfs_id: Optional[str] = None
    file_name: str
    status: str = "pending"  # "pending", "draft", "reviewed", "sent"
    ai_feedback: Optional[str] = None
    instructor_feedback: Optional[str] = None  # Human-in-the-loop: instructor's edited/added feedback
    feedback_sent: bool = False  # Whether feedback has been sent to student
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None  # When feedback was sent to student

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
    
    # Validate file type
    filename = file.filename or "unnamed"
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")
    
    # Read and parse CSV
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except Exception:
        text = content.decode('latin-1')
    
    reader = csv.DictReader(io.StringIO(text))
    
    results = {
        "added": [],
        "already_enrolled": [],
        "not_found": [],
        "errors": []
    }
    
    for row in reader:
        email = row.get("email", "").strip().lower()
        if not email:
            continue
        
        try:
            # Find student by email
            student = await db.users.find_one({"email": email}, {"_id": 0})
            
            if not student:
                # Check if name provided for creating placeholder
                name = row.get("name", "").strip()
                if name:
                    # Create placeholder user (they'll complete profile on first login)
                    student_id = f"user_{uuid.uuid4().hex[:12]}"
                    await db.users.insert_one({
                        "user_id": student_id,
                        "email": email,
                        "name": name,
                        "picture": None,
                        "role": "student",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                    student = {"user_id": student_id, "name": name, "email": email}
                else:
                    results["not_found"].append(email)
                    continue
            
            # Check if already enrolled
            if student["user_id"] in cohort.get("student_ids", []):
                results["already_enrolled"].append(email)
                continue
            
            # Add to cohort
            await db.cohorts.update_one(
                {"cohort_id": cohort_id},
                {"$push": {"student_ids": student["user_id"]}}
            )
            
            # Refresh cohort data
            cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
            
            results["added"].append({
                "email": email,
                "name": student.get("name", "Unknown")
            })
            
            # Send invitation email
            origin = request.headers.get("origin", "") if request else ""
            app_url = origin or "https://cohort-feedback-hub.preview.emergentagent.com"
            await send_email_notification(
                to_email=email,
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
                        Use your Google account ({email}) to sign in.
                    </p>
                </div>
                """
            )
            
        except Exception as e:
            logger.error(f"Error importing student {email}: {e}")
            results["errors"].append(email)
    
    return {
        "message": f"Import complete: {len(results['added'])} added, {len(results['already_enrolled'])} already enrolled, {len(results['not_found'])} not found",
        "results": results
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
        drive_folder_url=_validate_drive_url(drive_folder_url) if material_type == "homework" else ""
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
        "cohorts": cohorts
    }



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
    
    # Get material info
    material = await db.materials.find_one(
        {"material_id": submission["material_id"]},
        {"_id": 0}
    )
    
    # Build context using helper
    submission_text, context_text = await build_coach_max_context(submission, material)
    
    # Build cumulative context from prior weeks
    current_week = material.get("week_number", 1) if material else 1
    cumulative_ctx = await build_cumulative_context(
        user["user_id"], submission.get("cohort_id", ""), current_week
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

CURRENT ASSIGNMENT: {material['title'] if material else 'Unknown'}
CURRENT WEEK: {material.get('week_number', '?') if material else '?'}

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
    file: UploadFile = File(...),
    cohort_id: str = None,
    user: dict = Depends(get_current_user)
):
    """Submit homework for review"""
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
    
    # Validate file
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    
    # Save file to GridFS (persistent across redeploys)
    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    content = await file.read()
    gridfs_id = await save_bytes_to_gridfs(content, f"{submission_id}_{filename}")
    
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
            submission_id=submission_id,
            material_id=material_id,
            cohort_id=submission_cohort_id,
            student_id=user["user_id"],
            file_path="",
            gridfs_id=gridfs_id,
            file_name=filename
        )
        
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
            
            # Extract text from submission (read from GridFS — in-memory content is also available)
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
                logger.error(f"Auto review: EMERGENT_LLM_KEY not set")
                return
            
            # Look up student's language preference
            stu = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
            auto_lang = stu.get("language_preference", "en") if stu else "en"
            auto_lang_instr = get_language_instruction(auto_lang)
            
            # Build cumulative context from prior weeks
            auto_cumulative = await build_cumulative_context(
                student_id, submission_cohort_id, material.get("week_number", 1)
            )
            
            chat = LlmChat(
                api_key=api_key,
                session_id=f"review_{submission_id}",
                system_message=f"""You are a supportive and encouraging AI tutor helping students learn.
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
    """Get single submission details"""
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
    
    # Add related info
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    submission["material"] = material
    
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
    """Generate AI review for a submission"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    submission = await db.submissions.find_one({"submission_id": submission_id}, {"_id": 0})
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": submission["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get material info (for context)
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Get related workbooks and case studies for context
    context_materials = await db.materials.find({
        "cohort_id": submission["cohort_id"],
        "week_number": material["week_number"],
        "material_type": {"$in": ["workbook", "case_study", "video"]}
    }, {"_id": 0}).to_list(10)
    
    # Always include Course-Wide Resources (is_global=True library materials linked to this cohort)
    global_materials = await db.materials.find({
        "is_library": True,
        "is_global": True,
        "cohort_ids": submission["cohort_id"]
    }, {"_id": 0}).to_list(20)
    context_materials = list(global_materials) + list(context_materials)
    
    # Extract text from submission
    try:
        file_bytes = await read_bytes_from_doc(submission)
        submission_text = extract_text_from_file(file_bytes, submission["file_name"])
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
    
    # Build cumulative context from prior weeks
    cumulative_ctx = await build_cumulative_context(
        submission["student_id"], submission.get("cohort_id", ""), material.get("week_number", 1)
    )
    
    feedback = ""
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_{submission_id}",
            system_message=f"""You are a supportive and encouraging AI tutor helping students learn.
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
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Please review this student's homework submission and provide structured feedback.

ASSIGNMENT: {material['title']}
{f"DESCRIPTION: {material['description']}" if material.get('description') else ""}

CURRENT WEEK CONTEXT (Week {material['week_number']} materials):
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
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    instructor = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
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
                {t['body']} <strong>{material['title'] if material else 'Homework'}</strong> 
                ({t['week']} {material['week_number'] if material else '?'}).
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
        f"Feedback on {material['title'] if material else 'Your Homework'} - {cohort['name']}",
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
