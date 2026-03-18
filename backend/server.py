from fastapi import FastAPI, APIRouter, HTTPException, UploadFile, File, Depends, Response, Request
from fastapi.responses import JSONResponse
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Submission(BaseModel):
    submission_id: str = Field(default_factory=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    material_id: str
    cohort_id: str
    student_id: str
    file_path: str
    file_name: str
    status: str = "pending"  # "pending", "reviewed"
    ai_feedback: Optional[str] = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reviewed_at: Optional[datetime] = None

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
    """Require instructor role"""
    user = await get_current_user(request)
    if user.get("role") != "instructor":
        raise HTTPException(status_code=403, detail="Instructor access required")
    return user

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
                raise HTTPException(status_code=401, detail="Invalid session_id")
            user_data = resp.json()
        except Exception as e:
            logger.error(f"Auth error: {e}")
            raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Check if user exists
    existing_user = await db.users.find_one(
        {"email": user_data["email"]},
        {"_id": 0}
    )
    
    if existing_user:
        user_id = existing_user["user_id"]
        # Update user info
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": user_data["name"],
                "picture": user_data.get("picture")
            }}
        )
    else:
        # Create new user (default role: student)
        user_id = f"user_{uuid.uuid4().hex[:12]}"
        new_user = {
            "user_id": user_id,
            "email": user_data["email"],
            "name": user_data["name"],
            "picture": user_data.get("picture"),
            "role": "student",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(new_user)
    
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
    
    return {"user": user, "session_token": session_token}

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
    """Set user role (first time only or by admin)"""
    data = await request.json()
    role = data.get("role")
    
    if role not in ["instructor", "student"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"role": role}}
    )
    
    return {"message": "Role updated", "role": role}

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
    if user["role"] == "instructor":
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
    if user["role"] == "instructor" and cohort["instructor_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get student details if instructor
    if user["role"] == "instructor":
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
    
    if not cohort or cohort["instructor_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if update_data:
        await db.cohorts.update_one({"cohort_id": cohort_id}, {"$set": update_data})
    
    return {"message": "Cohort updated"}

@api_router.delete("/cohorts/{cohort_id}")
async def delete_cohort(cohort_id: str, user: dict = Depends(require_instructor)):
    """Delete a cohort"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    
    if not cohort or cohort["instructor_id"] != user["user_id"]:
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
    if not cohort or cohort["instructor_id"] != user["user_id"]:
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
    if not cohort or cohort["instructor_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Cohort not found")
    
    await db.cohorts.update_one(
        {"cohort_id": cohort_id},
        {"$pull": {"student_ids": student_id}}
    )
    
    return {"message": "Student removed"}

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
    user: dict = Depends(require_instructor)
):
    """Upload course material (workbook, case study, or homework assignment)"""
    cohort = await db.cohorts.find_one({"cohort_id": cohort_id}, {"_id": 0})
    if not cohort or cohort["instructor_id"] != user["user_id"]:
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
        uploaded_by=user["user_id"]
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
    if user["role"] == "instructor" and cohort["instructor_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if user["role"] == "student" and user["user_id"] not in cohort.get("student_ids", []):
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
    if not cohort or cohort["instructor_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Delete file
    try:
        os.remove(material["file_path"])
    except:
        pass
    
    await db.materials.delete_one({"material_id": material_id})
    return {"message": "Material deleted"}

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
        raise HTTPException(status_code=400, detail="Already submitted. Contact instructor for resubmission.")
    
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
    
    # Create submission
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
    await db.submissions.insert_one(doc)
    
    return {"submission_id": submission_id, "message": "Homework submitted"}

@api_router.get("/submissions")
async def get_submissions(user: dict = Depends(get_current_user)):
    """Get submissions for current user"""
    if user["role"] == "student":
        submissions = await db.submissions.find(
            {"student_id": user["user_id"]},
            {"_id": 0}
        ).to_list(100)
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
        if not cohort or cohort["instructor_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Add related info
    material = await db.materials.find_one({"material_id": submission["material_id"]}, {"_id": 0})
    submission["material"] = material
    
    if user["role"] == "instructor":
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
    if not cohort or cohort["instructor_id"] != user["user_id"]:
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
Your role is to provide qualitative, encouraging feedback on homework submissions.

Guidelines:
- Be warm, supportive, and encouraging
- Focus on what the student did well
- Provide constructive suggestions for improvement in a positive way
- Highlight areas of growth and potential
- Use specific examples from their work
- Do NOT give grades or scores
- Write in a mentoring, supportive tone
- End with encouragement and next steps for learning

Structure your feedback as:
1. Opening (acknowledge their effort)
2. Strengths (what they did well)
3. Areas for Growth (gentle suggestions)
4. Closing (encouragement and motivation)"""
        ).with_model("openai", "gpt-5.2")
        
        prompt = f"""Please review this student's homework submission.

ASSIGNMENT: {material['title']}
{f"DESCRIPTION: {material['description']}" if material.get('description') else ""}

COURSE CONTEXT (Week {material['week_number']} materials):
{context_text[:8000] if context_text else "No additional context available."}

STUDENT SUBMISSION:
{submission_text[:10000]}

Please provide encouraging, qualitative feedback for this student."""

        message = UserMessage(text=prompt)
        feedback = await chat.send_message(message)
        
    except Exception as e:
        logger.error(f"AI review error: {e}")
        raise HTTPException(status_code=500, detail=f"AI review failed: {str(e)}")
    
    # Save feedback
    await db.submissions.update_one(
        {"submission_id": submission_id},
        {"$set": {
            "ai_feedback": feedback,
            "status": "reviewed",
            "reviewed_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"feedback": feedback, "message": "Review complete"}

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
