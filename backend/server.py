from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Depends, Response, Request
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
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
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
if not SENDER_EMAIL:
    logger.error("SENDER_EMAIL not set in .env — emails will fail")
    SENDER_EMAIL = "info@theboostpad.org"
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "").lower().strip()
NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "").lower().strip()
THINKIFIC_API_KEY = os.environ.get("THINKIFIC_API_KEY", "")
THINKIFIC_SUBDOMAIN = os.environ.get("THINKIFIC_SUBDOMAIN", "")

# ==================== EMAIL HELPER ====================

async def send_email_notification(to_email: str, subject: str, html_content: str):
    """Send email notification using Resend"""
    if not resend.api_key:
        logger.warning("Resend API key not configured, skipping email")
        return None
    
    try:
        params = {
            "from": f"The Boost Pad <{SENDER_EMAIL}>",
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

async def read_file_text(file_path: str, file_name: str) -> str:
    """Read file from disk and extract text"""
    try:
        async with aiofiles.open(file_path, "rb") as f:
            file_bytes = await f.read()
        return extract_text_from_file(file_bytes, file_name)
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return ""


async def save_uploaded_file(file: UploadFile, prefix: str) -> tuple:
    """Save an uploaded file and return (file_path, filename)"""
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    file_path = UPLOAD_DIR / f"{prefix}_{filename}"
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    return str(file_path), filename


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
    submission_text = await read_file_text(submission["file_path"], submission["file_name"])
    
    context_text = ""
    if material:
        context_materials = await db.materials.find({
            "cohort_id": submission["cohort_id"],
            "week_number": material.get("week_number"),
            "material_type": {"$in": ["workbook", "case_study"]}
        }, {"_id": 0}).to_list(10)
        
        for mat in context_materials:
            mat_text = await read_file_text(mat["file_path"], mat["file_name"])
            if mat_text:
                context_text += f"\n--- {mat['title']} ---\n{mat_text[:3000]}"
    
    return submission_text, context_text


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
    file_path: str
    file_name: str
    uploaded_by: str
    due_date: Optional[str] = None  # ISO date string for homework assignments
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Submission(BaseModel):
    submission_id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    material_id: str
    cohort_id: str
    student_id: str
    file_path: str
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
    import shutil
    
    # Get all submission file paths before deleting
    submissions = await db.submissions.find({}, {"_id": 0, "file_path": 1}).to_list(1000)
    
    # Delete files from disk
    deleted_files = 0
    for sub in submissions:
        fp = sub.get("file_path", "")
        if fp and os.path.exists(fp):
            os.remove(fp)
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
    if not week_number or not isinstance(week_number, int) or week_number < 1 or week_number > 12:
        raise HTTPException(status_code=400, detail="Invalid week number (1-12)")
    
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
    
    # Save file
    material_id = f"mat_{uuid.uuid4().hex[:12]}"
    file_path = UPLOAD_DIR / f"{material_id}_{filename}"
    
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    # Create material record
    material = Material(
        material_id=material_id,
        cohort_id=cohort_id,
        week_number=week_number,
        material_type=material_type,
        title=title,
        description=description,
        file_path=str(file_path),
        file_name=filename,
        uploaded_by=user["user_id"],
        due_date=due_date if due_date else None
    )
    
    doc = material.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.materials.insert_one(doc)
    
    return {"material_id": material_id, "message": "Material uploaded"}

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
        "cohorts": cohorts
    }



@api_router.delete("/materials/{material_id}")
async def delete_material(material_id: str, user: dict = Depends(require_instructor)):
    """Delete a material"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete file
    try:
        os.remove(material["file_path"])
    except Exception:
        pass
    
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
    file: UploadFile = File(...),
    description: str = "",
    user: dict = Depends(require_instructor)
):
    """Upload a material to the central library (workbooks and case studies only)"""
    if material_type not in ["workbook", "case_study", "homework"]:
        raise HTTPException(status_code=400, detail="Library supports workbooks, case studies, and homework")
    
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    
    material_id = f"lib_{uuid.uuid4().hex[:12]}"
    file_path = UPLOAD_DIR / f"{material_id}_{filename}"
    
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    doc = {
        "material_id": material_id,
        "is_library": True,
        "cohort_id": None,
        "cohort_ids": [],
        "week_number": week_number,
        "material_type": material_type,
        "title": title,
        "description": description,
        "file_path": str(file_path),
        "file_name": filename,
        "uploaded_by": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.materials.insert_one(doc)
    
    return {"material_id": material_id, "message": "Material added to library"}

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
        
        # Remove old file
        try:
            os.remove(material["file_path"])
        except Exception:
            pass
        
        file_path = UPLOAD_DIR / f"{material_id}_{filename}"
        async with aiofiles.open(file_path, "wb") as f:
            content = await file.read()
            await f.write(content)
        update_data["file_path"] = str(file_path)
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
    
    try:
        os.remove(material["file_path"])
    except Exception:
        pass
    
    await db.materials.delete_one({"material_id": material_id})
    return {"message": "Library material deleted"}

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
async def download_material(material_id: str, user: dict = Depends(get_current_user)):
    """Download a material file"""
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
    
    file_path = Path(material["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        filename=material["file_name"],
        media_type="application/octet-stream"
    )


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
        
        submissions = await db.submissions.find(
            {"student_id": user["user_id"], "cohort_id": cohort["cohort_id"]},
            {"_id": 0}
        ).to_list(100)
        
        weeks = []
        for week_num in range(1, 13):
            # Only include released weeks
            if week_num not in released_weeks:
                continue
            
            week_materials = [m for m in materials if m.get("week_number") == week_num]
            homework_list = [m for m in week_materials if m.get("material_type") == "homework"]
            
            week_data = {
                "week_number": week_num,
                "homework": None,
                "submission": None,
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
            
            if homework_list:
                hw = homework_list[0]
                week_data["homework"] = {
                    "material_id": hw["material_id"],
                    "title": hw.get("title", ""),
                    "description": hw.get("description", ""),
                    "due_date": hw.get("due_date"),
                    "file_name": hw.get("file_name", "")
                }
                week_data["status"] = "waiting_on_submission"
                
                sub = next((s for s in submissions if s.get("material_id") == hw["material_id"]), None)
                if sub:
                    week_data["submission"] = {
                        "submission_id": sub["submission_id"],
                        "file_name": sub.get("file_name", ""),
                        "submitted_at": sub.get("submitted_at", ""),
                        "resubmission_allowed": sub.get("resubmission_allowed", False),
                        "resubmission_count": sub.get("resubmission_count", 0)
                    }
                    if sub.get("status") == "pending":
                        week_data["status"] = "submitted"
                    elif sub.get("status") == "draft":
                        week_data["status"] = "under_review"
                    elif sub.get("status") == "sent":
                        week_data["status"] = "feedback_provided"
                        week_data["feedback"] = sub.get("instructor_feedback") or sub.get("ai_feedback")
            
            weeks.append(week_data)
        
        result.append({
            "cohort_id": cohort["cohort_id"],
            "cohort_name": cohort.get("name", ""),
            "description": cohort.get("description", ""),
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
    
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if not submission_id:
        raise HTTPException(status_code=400, detail="Submission ID is required")
    
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
    
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    response = ""
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"coach_max_{user['user_id']}_{submission_id}",
            system_message=f"""You are Coach Max, a friendly, supportive AI tutor for a leadership development course.
A student has received feedback on their homework and wants to discuss it with you.

Your personality:
- Warm, encouraging, and conversational
- Use the student's name when possible
- Answer questions clearly and specifically
- Reference the course materials and their submission when relevant
- Help them understand how to improve
- Keep responses concise (2-4 paragraphs max)
- Never give grades or scores

ASSIGNMENT: {material['title'] if material else 'Unknown'}
WEEK: {material.get('week_number', '?') if material else '?'}

THE STUDENT'S SUBMISSION:
{submission_text[:5000] if submission_text else 'Not available'}

FEEDBACK THE STUDENT RECEIVED:
{feedback}

COURSE MATERIALS:
{context_text[:5000] if context_text else 'Not available'}"""
        ).with_model("openai", "gpt-5.2")
        
        response = await chat.send_message(UserMessage(text=message))
        
    except Exception as e:
        logger.error(f"Coach Max error: {e}")
        raise HTTPException(status_code=500, detail="Coach Max is unavailable right now")
    
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
        # Delete old file
        try:
            os.remove(existing["file_path"])
        except Exception:
            pass
    
    # Validate file
    filename = file.filename or "unnamed"
    ext = filename.lower().split(".")[-1]
    if ext not in ["pdf", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files allowed")
    
    # Save file
    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    file_path = UPLOAD_DIR / f"{submission_id}_{filename}"
    
    async with aiofiles.open(file_path, "wb") as f:
        content = await file.read()
        await f.write(content)
    
    # Create or update submission
    if existing:
        # Update existing submission (resubmission)
        submission_id = existing["submission_id"]
        await db.submissions.update_one(
            {"submission_id": submission_id},
            {"$set": {
                "file_path": str(file_path),
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
            file_path=str(file_path),
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
    recent_submissions = [s for s in submissions if s.get("submitted_at") and 
                         datetime.fromisoformat(s["submitted_at"].replace("Z", "+00:00")) > week_ago]
    
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
async def download_submission(submission_id: str, user: dict = Depends(get_current_user)):
    """Download a student's submitted homework file"""
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
    
    file_path = Path(submission["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(file_path),
        filename=submission.get("file_name", "submission"),
        media_type="application/octet-stream"
    )

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
        "material_type": {"$in": ["workbook", "case_study"]}
    }, {"_id": 0}).to_list(10)
    
    # Extract text from submission
    try:
        async with aiofiles.open(submission["file_path"], "rb") as f:
            file_bytes = await f.read()
        
        submission_text = extract_text_from_file(file_bytes, submission["file_name"])
    except FileNotFoundError:
        logger.error(f"Submission file not found: {submission['file_path']}")
        raise HTTPException(status_code=404, detail="Submission file not found on server. Please ask the student to resubmit.")
    except Exception as e:
        logger.error(f"Error reading submission {submission['submission_id']}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Error reading submission file: {type(e).__name__}")
    
    if not submission_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from submission. The file may be empty or in an unsupported format.")
    
    # Build context from course materials
    context_text = ""
    for mat in context_materials:
        try:
            async with aiofiles.open(mat["file_path"], "rb") as f:
                mat_bytes = await f.read()
            
            mat_text = extract_text_from_file(mat_bytes, mat["file_name"])
            
            context_text += f"\n\n--- {mat['material_type'].upper()}: {mat['title']} ---\n{mat_text[:5000]}"
        except Exception:
            pass
    
    # Call GPT-5.2 for review
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
    feedback = ""
    try:
        chat = LlmChat(
            api_key=api_key,
            session_id=f"review_{submission_id}",
            system_message="""You are a supportive and encouraging AI tutor helping students learn.
Your role is to provide qualitative, structured feedback on homework submissions.

Guidelines:
- Be warm, supportive, and encouraging
- Use specific examples from their work to support each point
- Do NOT give grades or scores
- Write in a mentoring, supportive tone
- Keep each bullet point concise (1-2 sentences)

You MUST structure your feedback EXACTLY as follows:

A brief encouraging opening sentence acknowledging their effort.

What You Did Well:
- [specific strength with example from their work]
- [specific strength with example from their work]
- [specific strength with example from their work]

Areas for Growth:
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]
- [constructive suggestion framed positively with guidance]

A brief closing sentence with encouragement and motivation to keep going."""
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Please review this student's homework submission and provide structured feedback.

ASSIGNMENT: {material['title']}
{f"DESCRIPTION: {material['description']}" if material.get('description') else ""}

COURSE CONTEXT (Week {material['week_number']} materials):
{context_text[:8000] if context_text else "No additional context available."}

STUDENT SUBMISSION:
{submission_text[:10000]}

Provide feedback with exactly 3 bullet points under "What You Did Well:" and exactly 3 bullet points under "Areas for Growth:". Use specific examples from their submission."""

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
    
    # Send email to student
    feedback_html = feedback.replace("\n", "<br>")
    coach_max_url = f"{os.environ.get('FRONTEND_URL', 'https://cohort-feedback-hub.preview.emergentagent.com')}/coach-max/{submission_id}"
    email_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">Your Feedback is Ready!</h1>
        </div>
        <div style="background-color: #F9F8F6; padding: 24px;">
            <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                Hi <strong>{student['name'].split()[0]}</strong>,
            </p>
            <p style="color: #5A5A5A; font-size: 14px; margin-bottom: 16px;">
                Your instructor has reviewed your submission for <strong>{material['title'] if material else 'Homework'}</strong> 
                (Week {material['week_number'] if material else '?'}).
            </p>
            <div style="background-color: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; padding: 20px; margin: 20px 0;">
                <p style="color: #166534; font-size: 15px; line-height: 1.7; margin: 0;">
                    {feedback_html}
                </p>
            </div>
            <div style="text-align: center; margin: 24px 0;">
                <a href="{coach_max_url}" style="display: inline-block; background-color: #22438E; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600;">
                    Ask Coach Max a Question
                </a>
                <p style="color: #888; font-size: 12px; margin-top: 8px;">Have questions about your feedback? Chat with Coach Max for personalized guidance.</p>
            </div>
            <p style="color: #5A5A5A; font-size: 14px; margin-top: 20px;">
                Keep up the great work!<br>
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
    coach_max_url = f"{os.environ.get('FRONTEND_URL', 'https://cohort-feedback-hub.preview.emergentagent.com')}/coach-max/{submission_id}"
    
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
            email_params = {
                "from": f"The Boost Pad <{SENDER_EMAIL}>",
                "to": [student["email"]],
                "subject": f"Your Feedback Report: {material_title} - Week {week_num}",
                "html": f"""
                <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #22438E; padding: 20px; border-radius: 12px 12px 0 0;">
                        <h1 style="color: #FFFFFF; margin: 0; font-size: 24px;">Your Feedback Report</h1>
                    </div>
                    <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
                        <p style="color: #1A1A1A; font-size: 16px;">
                            Hi <strong>{student_name.split()[0]}</strong>,
                        </p>
                        <p style="color: #5A5A5A; font-size: 14px;">
                            Your feedback for <strong>{material_title}</strong> (Week {week_num}) is attached as a PDF.
                        </p>
                        <div style="text-align: center; margin: 24px 0;">
                            <a href="{coach_max_url}" style="display: inline-block; background-color: #22438E; color: #FFFFFF; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-size: 16px; font-weight: 600;">
                                Ask Coach Max a Question
                            </a>
                            <p style="color: #888; font-size: 12px; margin-top: 8px;">Have questions about your feedback? Chat with Coach Max for guidance.</p>
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
            logger.error(f"Failed to email PDF to {student['email']}: {e}")
    
    # Clean up temp file
    os.unlink(tmp_path)
    
    # Return PDF as download for instructor
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pdf_filename}"'}
    )

# ==================== UTILITY ENDPOINTS ====================

@api_router.get("/")
async def root():
    return {"message": "The Boost Pad API"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

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


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
