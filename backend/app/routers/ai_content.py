from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db import get_db
from app.models import Business, Post, User
from app.schemas import GenerateContentRequest, PostActionResponse, PostResponse
from app.services.ai_service import generate_post_content

router = APIRouter(tags=["ai-content"])


def _get_business_or_404(db: Session, user: User) -> Business:
    business = db.query(Business).filter(Business.user_id == user.id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Complete business onboarding first")
    return business


@router.post("/ai/generate", response_model=PostResponse, status_code=201)
def generate_content(
    payload: GenerateContentRequest,
    api_key: str | None = Header(default=None, alias="X-Api-Key"),
):
    try:
        result = generate_post_content(payload, api_key=api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    return PostResponse(
        id=str(uuid4()),
        business_id=result["business_id"],
        occasion=payload.occasion,
        caption=result["caption"],
        hashtags=result["hashtags"],
        cta=result["cta"],
        image_prompt=result["image_prompt"],
        generated_image=result["generated_image"],
        reel_idea=result["reel_idea"],
        status="pending",
        ai_model_used=result["model_used"],
        created_at=datetime.now(timezone.utc),
    )


@router.get("/businesses/me/posts", response_model=list[PostResponse])
def list_posts(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    business = _get_business_or_404(db, current_user)
    query = db.query(Post).filter(Post.business_id == business.id)
    if status_filter:
        query = query.filter(Post.status == status_filter)
    return query.order_by(Post.created_at.desc()).all()


@router.post("/posts/{post_id}/approve", response_model=PostActionResponse)
def approve_post(
    post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    business = _get_business_or_404(db, current_user)
    post = db.query(Post).filter(Post.id == post_id, Post.business_id == business.id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    post.status = "scheduled"
    post.approved_at = datetime.now(timezone.utc)
    db.commit()
    return PostActionResponse(id=post.id, status=post.status)


@router.post("/posts/{post_id}/reject", response_model=PostActionResponse)
def reject_post(
    post_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    business = _get_business_or_404(db, current_user)
    post = db.query(Post).filter(Post.id == post_id, Post.business_id == business.id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    post.status = "rejected"
    db.commit()
    return PostActionResponse(id=post.id, status=post.status)
