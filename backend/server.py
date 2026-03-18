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
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
SUPER_ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "").lower().strip()

# ==================== EMAIL HELPER ====================

async def send_email_notification(to_email: str, subject: str, html_content: str):
    """Send email notification using Resend"""
    if not resend.api_key:
        logger.warning("Resend API key not configured, skipping email")
        return None
    
    try:
        params = {
            "from": SENDER_EMAIL,
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Email sent to {to_email}: {result.get('id')}")
        return result
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return None

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
    instructor_id: str
    student_ids: List[str] = []
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
    return cohort.get("instructor_id") == user.get("user_id")

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
                Great news! <strong>{user['name']}</strong> has promoted you to an instructor on ThinkificAI.
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
        "You've Been Promoted to Instructor - ThinkificAI",
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

# ==================== COHORT ENDPOINTS ====================

@api_router.post("/cohorts")
async def create_cohort(cohort_data: CohortCreate, user: dict = Depends(require_instructor)):
    """Create a new cohort (instructor only)"""
    cohort = Cohort(
        name=cohort_data.name,
        description=cohort_data.description,
        instructor_id=user["user_id"]
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
                {"instructor_id": user["user_id"]},
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
        if user["role"] == "instructor" and cohort["instructor_id"] != user["user_id"]:
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
    await db.materials.delete_many({"cohort_id": cohort_id})
    await db.submissions.delete_many({"cohort_id": cohort_id})
    
    return {"message": "Cohort deleted"}

@api_router.post("/cohorts/{cohort_id}/students")
async def add_student_to_cohort(cohort_id: str, request: Request, user: dict = Depends(require_instructor)):
    """Add student to cohort by email"""
    data = await request.json()
    student_email = data.get("email")
    
    if not student_email:
        raise HTTPException(status_code=400, detail="Student email required")
    
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or not is_cohort_manager(user, cohort):
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    # Find student by email
    student = await db.users.find_one({"email": student_email}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found. They need to sign up first.")
    
    if student["user_id"] in cohort.get("student_ids", []):
        raise HTTPException(status_code=400, detail="Student already in cohort")
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$push": {"student_ids": student["user_id"]}}
    )
    
    return {"message": "Student added", "student": {"user_id": student["user_id"], "name": student["name"], "email": student["email"]}}

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
    user: dict = Depends(require_instructor)
):
    """Bulk import students from CSV file.
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
    except:
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
    
    # Create CSV template
    template = "email,name\nstudent1@example.com,John Doe\nstudent2@example.com,Jane Smith\n"
    
    return Response(
        content=template,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_import_template.csv"}
    )

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
        except:
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
        except:
            return ""

def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Extract text from file based on extension"""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    
    if ext == "pdf":
        text = extract_text_from_pdf(file_bytes)
    elif ext in ["docx", "doc"]:
        text = extract_text_from_docx(file_bytes)
    else:
        # Try plain text
        try:
            text = file_bytes.decode('utf-8', errors='ignore').strip()
        except:
            text = ""
    
    # If still empty, try plain text as fallback
    if not text:
        try:
            text = file_bytes.decode('utf-8', errors='ignore').strip()
        except:
            pass
    
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
        if user["role"] == "instructor" and cohort["instructor_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    elif user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = {"cohort_id": cohort_id}
    if week:
        query["week_number"] = week
    
    materials = await db.materials.find(query, {"_id": 0}).to_list(100)
    
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
    except:
        pass
    
    await db.materials.delete_one({"material_id": material_id})
    return {"message": "Material deleted"}

@api_router.get("/materials/{material_id}/download")
async def download_material(material_id: str, user: dict = Depends(get_current_user)):
    """Download a material file"""
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    
    # Check access
    cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
    if not cohort:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    if user["role"] in ["instructor", "super_admin"]:
        if user["role"] == "instructor" and cohort["instructor_id"] != user["user_id"]:
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

# ==================== SUBMISSION ENDPOINTS ====================

@api_router.post("/materials/{material_id}/submit")
async def submit_homework(
    material_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Submit homework for review"""
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can submit homework")
    
    material = await db.materials.find_one({"material_id": material_id}, {"_id": 0})
    if not material or material["material_type"] != "homework":
        raise HTTPException(status_code=404, detail="Homework assignment not found")
    
    cohort = await db.cohorts.find_one({"cohort_id": material["cohort_id"]}, {"_id": 0})
    if not cohort or user["user_id"] not in cohort.get("student_ids", []):
        raise HTTPException(status_code=403, detail="Not enrolled in this cohort")
    
    # Check for existing submission
    existing = await db.submissions.find_one({
        "material_id": material_id,
        "student_id": user["user_id"]
    }, {"_id": 0})
    
    if existing:
        # Check if resubmission is allowed
        if not existing.get("resubmission_allowed", False):
            raise HTTPException(status_code=400, detail="Already submitted. Request resubmission from your instructor.")
        
        # Delete old file
        try:
            os.remove(existing["file_path"])
        except:
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
            cohort_id=material["cohort_id"],
            student_id=user["user_id"],
            file_path=str(file_path),
            file_name=filename
        )
        
        doc = submission.model_dump()
        doc["submitted_at"] = doc["submitted_at"].isoformat()
        doc["resubmission_count"] = 0
        await db.submissions.insert_one(doc)
        is_resubmission = False
    
    # Send email notification to instructor
    instructor = await db.users.find_one({"user_id": cohort["instructor_id"]}, {"_id": 0})
    if instructor:
        subject_prefix = "Resubmission" if is_resubmission else "New Submission"
        email_html = f"""
        <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background-color: {'#E0F2FE' if is_resubmission else '#FDE047'}; padding: 20px; border-radius: 12px 12px 0 0;">
                <h1 style="color: #1A1A1A; margin: 0; font-size: 24px;">{subject_prefix}: Homework</h1>
            </div>
            <div style="background-color: #F9F8F6; padding: 24px; border-radius: 0 0 12px 12px;">
                <p style="color: #1A1A1A; font-size: 16px; margin-bottom: 16px;">
                    <strong>{user['name']}</strong> has {'resubmitted' if is_resubmission else 'submitted'} homework for review.
                </p>
                <div style="background-color: white; border: 1px solid #E5E5E5; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <p style="margin: 0 0 8px 0; color: #5A5A5A; font-size: 14px;">Assignment</p>
                    <p style="margin: 0; color: #1A1A1A; font-weight: 500;">{material['title']}</p>
                    <p style="margin: 8px 0 0 0; color: #888; font-size: 14px;">Week {material['week_number']} • {cohort['name']}</p>
                </div>
                <p style="color: #5A5A5A; font-size: 14px;">
                    Log in to ThinkificAI to review this submission and provide AI-powered feedback.
                </p>
            </div>
        </div>
        """
        await send_email_notification(
            instructor["email"],
            f"{subject_prefix}: {material['title']} from {user['name']}",
            email_html
        )
    
    return {"submission_id": submission_id, "message": f"Homework {'resubmitted' if is_resubmission else 'submitted'}"}

@api_router.get("/submissions")
async def get_submissions(user: dict = Depends(get_current_user)):
    """Get submissions for current user"""
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
            {"instructor_id": user["user_id"]},
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
                    Log in to ThinkificAI to submit your updated work.
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
            {"instructor_id": user["user_id"]},
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
        
        student_progress.append({
            "user_id": student["user_id"],
            "name": student["name"],
            "email": student["email"],
            "picture": student.get("picture"),
            "submissions": len(student_subs),
            "completed": completed,
            "pending": pending,
            "completion_rate": round((completed / len(homework_materials) * 100) if homework_materials else 0, 1)
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
    except Exception as e:
        logger.error(f"Error reading submission: {e}")
        raise HTTPException(status_code=500, detail="Error reading submission file")
    
    if not submission_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from submission")
    
    # Build context from course materials
    context_text = ""
    for mat in context_materials:
        try:
            async with aiofiles.open(mat["file_path"], "rb") as f:
                mat_bytes = await f.read()
            
            mat_text = extract_text_from_file(mat_bytes, mat["file_name"])
            
            context_text += f"\n\n--- {mat['material_type'].upper()}: {mat['title']} ---\n{mat_text[:5000]}"
        except:
            pass
    
    # Call GPT-5.2 for review
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="AI service not configured")
    
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
    email_html = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background-color: #D1FAE5; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="color: #065F46; margin: 0; font-size: 24px;">Your Feedback is Ready!</h1>
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
            <p style="color: #5A5A5A; font-size: 14px; margin-top: 20px;">
                Keep up the great work!<br>
                — {instructor['name'] if instructor else 'Your Instructor'}
            </p>
        </div>
        <div style="background-color: #E5E5E5; padding: 16px; border-radius: 0 0 12px 12px; text-align: center;">
            <p style="color: #888; font-size: 12px; margin: 0;">
                ThinkificAI Tutor • {cohort['name']}
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

# ==================== UTILITY ENDPOINTS ====================

@api_router.get("/")
async def root():
    return {"message": "ThinkificAI Tutor API"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}

# Include the router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
