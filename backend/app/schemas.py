from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------- Auth ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------- Business ----------
class BusinessCreate(BaseModel):
    business_name: str
    owner_name: Optional[str] = None
    sector: str
    sub_sector: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    email: Optional[EmailStr] = None
    brand_colors: List[str] = Field(default_factory=list)
    brand_personality: Optional[str] = None
    tone_of_voice: Optional[str] = None
    target_audience: Optional[str] = None
    preferred_cta: Optional[str] = None
    social_handles: dict[str, str] = Field(default_factory=dict)
    website: Optional[str] = None


class GenerationBusinessProfile(BusinessCreate):
    id: str
    created_at: Optional[datetime] = None


class BusinessResponse(BusinessCreate):
    id: str
    logo_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- AI Content ----------
class GenerateContentRequest(BaseModel):
    business_profile: GenerationBusinessProfile
    occasion: Optional[str] = None
    post_type: Optional[str] = None
    tone: Optional[str] = None
    goal: Optional[str] = None
    include_hashtags: bool = True
    include_cta: bool = True
    include_image_prompt: bool = True
    include_reel_idea: bool = False


class PostResponse(BaseModel):
    id: str
    business_id: str
    occasion: Optional[str]
    caption: str
    hashtags: List[str]
    cta: str
    image_prompt: str
    generated_image: Optional[str] = None
    reel_idea: Optional[str] = None
    carousel_slides: List[str] = Field(default_factory=list)
    status: str
    ai_model_used: str
    created_at: datetime

    class Config:
        from_attributes = True


class PostActionResponse(BaseModel):
    id: str
    status: str
