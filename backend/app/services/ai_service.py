import json
import logging
from datetime import date
from typing import Optional

import anthropic

from app.core.config import settings
from app.schemas import GenerateContentRequest

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are MarketUp's AI social media copywriter for small Indian businesses.
You write concise, warm, locally-flavoured social media posts that match a business's brand voice.
You ALWAYS respond with ONLY a single valid JSON object, no markdown fences, no preamble, matching exactly:
{
  "caption": "string, 2-4 sentences, engaging, no hashtags inside it",
  "hashtags": ["#tag1", "#tag2", "... 5 to 8 relevant hashtags"],
  "cta": "short call to action, e.g. 'Visit us today!'",
  "image_prompt": "a descriptive prompt for generating a branded social media image for this post",
  "reel_idea": "a short video idea, or an empty string when not requested"
}
"""


def _build_user_prompt(request: GenerateContentRequest) -> str:
    business = request.business_profile
    occasion_line = (
        f"Occasion / theme to write about: {request.occasion}."
        if request.occasion
        else f"No specific occasion was given — pick something naturally relevant for "
        f"today ({date.today().isoformat()}) for this type of business (e.g. a seasonal "
        f"angle, a general trust/quality angle, or a light promotional angle)."
    )
    colors = ", ".join(business.brand_colors) if business.brand_colors else "not specified"
    tone = request.tone or business.tone_of_voice or "Professional"
    post_type = request.post_type or "social media post"
    goal = request.goal or "Brand Awareness"
    return f"""Business name: {business.business_name}
Owner: {business.owner_name or "not specified"}
Sector: {business.sector} / {business.sub_sector or "n/a"}
Description: {business.description or "n/a"}
Location/address: {business.address or "n/a"}
Target audience: {business.target_audience or "not specified"}
Brand personality: {business.brand_personality or "not specified"}
Brand colors: {colors}
Post type: {post_type}
Tone: {tone}
Campaign goal: {goal}
{occasion_line}

Include hashtags: {request.include_hashtags}
Include a call to action: {request.include_cta}
Include an image prompt: {request.include_image_prompt}
Include a reel idea: {request.include_reel_idea}
Preferred call to action: {business.preferred_cta or "choose one that fits"}
Social handles: {business.social_handles or "not specified"}

Write one social media post for this business following the JSON schema exactly."""


def generate_post_content(
    request: GenerateContentRequest, api_key: Optional[str] = None
) -> dict:
    """Calls the real Anthropic API to generate a branded social media post.

    Uses the request's API key, or ANTHROPIC_API_KEY from the server environment.
    """
    provider_api_key = api_key or settings.anthropic_api_key
    if not provider_api_key:
        raise RuntimeError(
            "No Anthropic API key was provided. Add one in the app or configure ANTHROPIC_API_KEY."
        )

    client = anthropic.Anthropic(api_key=provider_api_key)

    logger.info("Starting Anthropic content generation (model=%s)", settings.anthropic_model)
    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=900,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(request)}],
        )
    except anthropic.APIStatusError as exc:
        logger.warning(
            "Anthropic content generation failed (http_status=%s request_id=%s)",
            exc.status_code,
            exc.request_id,
        )
        raise

    logger.info("Anthropic content generation succeeded (request_id=%s)", message.id)

    raw_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()

    # Defensive parsing in case the model wraps JSON in fences despite instructions
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    data = json.loads(raw_text)
    profile = request.business_profile
    image_prompt = data.get("image_prompt", "") if request.include_image_prompt else ""

    return {
        "caption": data["caption"],
        "hashtags": data.get("hashtags", []) if request.include_hashtags else [],
        "cta": data.get("cta", "") if request.include_cta else "",
        "image_prompt": image_prompt,
        "generated_image": None,
        "reel_idea": data.get("reel_idea") if request.include_reel_idea else None,
        "business_id": profile.id,
        "model_used": settings.anthropic_model,
    }
