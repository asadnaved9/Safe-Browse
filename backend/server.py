from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import jwt
from passlib.context import CryptContext
import re
import base64
from bson import ObjectId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Safe environment variable loader
def _get_env(name: str, default: Optional[str] = None) -> str:
    value = os.environ.get(name, default or "")
    if isinstance(value, str):
        value = value.strip().strip('\'"')
    return value

# MongoDB connection with safe env loading
mongo_url = _get_env('MONGO_URL', 'mongodb://localhost:27017')
db_name = _get_env('DB_NAME', 'safebrowse_db')
client = AsyncIOMotorClient(mongo_url)
db = client[db_name]

# Security setup
SECRET_KEY = _get_env('JWT_SECRET_KEY', 'safebrowse-secret-key-change-in-production')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Create the main app
app = FastAPI(title="SafeBrowse API")
api_router = APIRouter(prefix="/api")

# ==================== MODELS ====================

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Dict[str, Any]

class ChildProfile(BaseModel):
    name: str
    age: int
    maturity_level: Optional[str] = None  # 'strict', 'moderate', 'lenient'
    blocked_sites: List[str] = Field(default_factory=list)
    whitelisted_sites: List[str] = Field(default_factory=list)

class ChildProfileResponse(BaseModel):
    id: str
    parent_id: str
    name: str
    age: int
    maturity_level: str
    blocked_sites: List[str]
    whitelisted_sites: List[str]
    created_at: datetime

class ContentAnalysisRequest(BaseModel):
    profile_id: str
    content_type: str  # 'text', 'image', 'url'
    content: str  # text content, base64 image, or URL
    context: Optional[str] = None

class ContentAnalysisResponse(BaseModel):
    is_safe: bool
    confidence: float
    reasons: List[str]
    blocked: bool

class ContentLog(BaseModel):
    profile_id: str
    content_type: str
    detected_at: datetime = Field(default_factory=datetime.utcnow)
    is_safe: bool
    confidence: float
    reasons: List[str]
    content_snippet: str
    url: Optional[str] = None

class ContentLogResponse(BaseModel):
    id: str
    profile_id: str
    profile_name: str
    content_type: str
    detected_at: datetime
    is_safe: bool
    confidence: float
    reasons: List[str]
    content_snippet: str
    url: Optional[str] = None

class PINUpdate(BaseModel):
    pin: str

# ==================== SECURITY HELPERS ====================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

# ==================== CONTENT FILTERING ====================

# Explicit content keywords and patterns
EXPLICIT_KEYWORDS = [
    'porn', 'xxx', 'sex', 'nude', 'naked', 'explicit', 'adult',
    'nsfw', 'hentai', 'fuck', 'shit', 'bitch', 'ass', 'dick',
    'pussy', 'cock', 'cum', 'masturbate', 'orgasm', 'rape'
]

SLANG_TERMS = [
    'netflix and chill', 'hook up', 'fwb', 'dtf', 'smash',
    'thot', 'simp', 'daddy', 'kinky', 'naughty'
]

EMOJI_PATTERNS = [
    '🍆', '🍑', '💦', '🔥', '👅', '🌶️', '🔞'
]

VIOLENCE_KEYWORDS = [
    'kill', 'murder', 'suicide', 'death', 'blood', 'gore',
    'torture', 'weapon', 'gun', 'knife', 'bomb'
]

def analyze_text_content(text: str, age: int) -> Tuple[bool, float, List[str]]:
    """
    Analyze text for harmful content
    Returns: (is_safe, confidence, reasons)
    """
    text_lower = text.lower()
    reasons = []
    score = 0
    
    # Check explicit keywords
    for keyword in EXPLICIT_KEYWORDS:
        if keyword in text_lower:
            reasons.append(f"Explicit content: '{keyword}'")
            score += 20
    
    # Check slang terms
    for slang in SLANG_TERMS:
        if slang in text_lower:
            reasons.append(f"Inappropriate slang: '{slang}'")
            score += 10
    
    # Check emoji patterns
    for emoji in EMOJI_PATTERNS:
        if emoji in text:
            reasons.append(f"Suggestive emoji: '{emoji}'")
            score += 15
    
    # Check violence
    for keyword in VIOLENCE_KEYWORDS:
        if keyword in text_lower:
            reasons.append(f"Violence-related: '{keyword}'")
            score += 15
    
    # Age-based thresholds
    if age <= 8:
        threshold = 20  # Very strict
    elif age <= 12:
        threshold = 35  # Moderate
    else:
        threshold = 50  # Lenient
    
    confidence = min(score / 100.0, 1.0)
    is_safe = score < threshold
    
    return is_safe, confidence, reasons

def analyze_url(url: str) -> Tuple[bool, float, List[str]]:
    """
    Analyze URL for harmful patterns
    """
    url_lower = url.lower()
    reasons = []
    score = 0
    
    # Known adult domains
    adult_domains = ['pornhub', 'xvideos', 'xnxx', 'redtube', 'youporn']
    for domain in adult_domains:
        if domain in url_lower:
            reasons.append(f"Adult website: {domain}")
            score += 100
    
    # Check for adult keywords in URL
    for keyword in EXPLICIT_KEYWORDS:
        if keyword in url_lower:
            reasons.append(f"Explicit keyword in URL: '{keyword}'")
            score += 30
    
    confidence = min(score / 100.0, 1.0)
    is_safe = score < 30
    
    return is_safe, confidence, reasons

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/signup", response_model=Token)
async def signup(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create user
    user_dict = {
        "email": user_data.email,
        "password": hash_password(user_data.password),
        "name": user_data.name,
        "pin": None,
        "created_at": datetime.utcnow()
    }
    
    result = await db.users.insert_one(user_dict)
    user_id = str(result.inserted_id)
    
    # Create token
    access_token = create_access_token(data={"sub": user_id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name
        }
    }

@api_router.post("/auth/login", response_model=Token)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    
    user_id = str(user["_id"])
    access_token = create_access_token(data={"sub": user_id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user["email"],
            "name": user["name"],
            "pin": user.get("pin")
        }
    }

@api_router.get("/auth/me")
async def get_me(current_user = Depends(get_current_user)):
    return {
        "id": str(current_user["_id"]),
        "email": current_user["email"],
        "name": current_user["name"],
        "pin": current_user.get("pin")
    }

@api_router.put("/auth/pin")
async def update_pin(pin_data: PINUpdate, current_user = Depends(get_current_user)):
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"pin": pin_data.pin}}
    )
    return {"message": "PIN updated successfully"}

# ==================== PROFILE ROUTES ====================

@api_router.post("/profiles", response_model=ChildProfileResponse)
async def create_profile(profile: ChildProfile, current_user = Depends(get_current_user)):
    # Determine maturity level based on age if not provided
    maturity = profile.maturity_level
    if not maturity:
        if profile.age <= 8:
            maturity = 'strict'
        elif profile.age <= 12:
            maturity = 'moderate'
        else:
            maturity = 'lenient'
    
    profile_dict = {
        "parent_id": str(current_user["_id"]),
        "name": profile.name,
        "age": profile.age,
        "maturity_level": maturity,
        "blocked_sites": profile.blocked_sites or [],
        "whitelisted_sites": profile.whitelisted_sites or [],
        "created_at": datetime.utcnow()
    }
    
    result = await db.profiles.insert_one(profile_dict)
    profile_dict["id"] = str(result.inserted_id)
    
    return profile_dict

@api_router.get("/profiles", response_model=List[ChildProfileResponse])
async def get_profiles(current_user = Depends(get_current_user)):
    profiles = await db.profiles.find({"parent_id": str(current_user["_id"])}).to_list(100)
    
    result = []
    for profile in profiles:
        profile["id"] = str(profile["_id"])
        result.append(profile)
    
    return result

@api_router.get("/profiles/{profile_id}", response_model=ChildProfileResponse)
async def get_profile(profile_id: str, current_user = Depends(get_current_user)):
    profile = await db.profiles.find_one({
        "_id": ObjectId(profile_id),
        "parent_id": str(current_user["_id"])
    })
    
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile["id"] = str(profile["_id"])
    return profile

@api_router.put("/profiles/{profile_id}", response_model=ChildProfileResponse)
async def update_profile(profile_id: str, profile: ChildProfile, current_user = Depends(get_current_user)):
    result = await db.profiles.update_one(
        {"_id": ObjectId(profile_id), "parent_id": str(current_user["_id"])},
        {"$set": profile.dict()}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    updated_profile = await db.profiles.find_one({"_id": ObjectId(profile_id)})
    updated_profile["id"] = str(updated_profile["_id"])
    
    return updated_profile

@api_router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str, current_user = Depends(get_current_user)):
    result = await db.profiles.delete_one({
        "_id": ObjectId(profile_id),
        "parent_id": str(current_user["_id"])
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    # Also delete associated logs
    await db.logs.delete_many({"profile_id": profile_id})
    
    return {"message": "Profile deleted successfully"}

# ==================== CONTENT ANALYSIS ROUTES ====================

@api_router.post("/content/analyze", response_model=ContentAnalysisResponse)
async def analyze_content(request: ContentAnalysisRequest):
    # Get profile to determine age-based thresholds
    profile = await db.profiles.find_one({"_id": ObjectId(request.profile_id)})
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    age = profile["age"]
    is_safe = True
    confidence = 0.0
    reasons = []
    
    # Analyze based on content type
    if request.content_type == "text":
        is_safe, confidence, reasons = analyze_text_content(request.content, age)
    elif request.content_type == "url":
        is_safe, confidence, reasons = analyze_url(request.content)
    elif request.content_type == "image":
        # For MVP, basic image analysis (would be enhanced with ML model)
        reasons.append("Image analysis not yet implemented - marked as safe")
        is_safe = True
        confidence = 0.5
    
    # Log the detection if harmful
    if not is_safe:
        log_dict = {
            "profile_id": request.profile_id,
            "content_type": request.content_type,
            "detected_at": datetime.utcnow(),
            "is_safe": is_safe,
            "confidence": confidence,
            "reasons": reasons,
            "content_snippet": request.content[:200] if request.content_type == "text" else "[Content blocked]",
            "url": request.context
        }
        await db.logs.insert_one(log_dict)
    
    return {
        "is_safe": is_safe,
        "confidence": confidence,
        "reasons": reasons,
        "blocked": not is_safe
    }

# ==================== LOGS ROUTES ====================

@api_router.get("/logs", response_model=List[ContentLogResponse])
async def get_logs(
    profile_id: Optional[str] = None,
    limit: int = 50,
    current_user = Depends(get_current_user)
):
    # Build query
    query = {}
    if profile_id:
        # Verify profile belongs to user
        profile = await db.profiles.find_one({
            "_id": ObjectId(profile_id),
            "parent_id": str(current_user["_id"])
        })
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        query["profile_id"] = profile_id
    else:
        # Get all profiles for user
        profiles = await db.profiles.find({"parent_id": str(current_user["_id"])}).to_list(100)
        profile_ids = [str(p["_id"]) for p in profiles]
        query["profile_id"] = {"$in": profile_ids}
    
    # Get logs
    logs = await db.logs.find(query).sort("detected_at", -1).limit(limit).to_list(limit)
    
    # Enrich with profile names
    result = []
    for log in logs:
        profile = await db.profiles.find_one({"_id": ObjectId(log["profile_id"])})
        log["id"] = str(log["_id"])
        log["profile_name"] = profile["name"] if profile else "Unknown"
        # Remove the _id field to avoid serialization issues
        del log["_id"]
        result.append(log)
    
    return result

@api_router.get("/logs/search", response_model=List[ContentLogResponse])
async def search_logs(
    keyword: str,
    current_user = Depends(get_current_user)
):
    # Get all profiles for user
    profiles = await db.profiles.find({"parent_id": str(current_user["_id"])}).to_list(100)
    profile_ids = [str(p["_id"]) for p in profiles]
    
    # Search in logs
    logs = await db.logs.find({
        "profile_id": {"$in": profile_ids},
        "$or": [
            {"content_snippet": {"$regex": keyword, "$options": "i"}},
            {"reasons": {"$regex": keyword, "$options": "i"}},
            {"url": {"$regex": keyword, "$options": "i"}}
        ]
    }).sort("detected_at", -1).limit(50).to_list(50)
    
    result = []
    for log in logs:
        profile = await db.profiles.find_one({"_id": ObjectId(log["profile_id"])})
        log["id"] = str(log["_id"])
        log["profile_name"] = profile["name"] if profile else "Unknown"
        # Remove the _id field to avoid serialization issues
        del log["_id"]
        result.append(log)
    
    return result

# ==================== MAIN APP SETUP ====================

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
