
import json
import logging
import re
from datetime import date
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schemas import GenerateContentRequest

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GEMINI_INTERACTIONS_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)

SYSTEM_PROMPT = """You are MarketUp's AI social media copywriter for small Indian businesses.
You write concise, warm, locally-flavoured social media posts that match a business's brand voice.

You MUST respond with exactly one valid JSON object.
Do not include markdown fences, explanations, preambles, or text outside the JSON.

Follow this structure exactly:
{
  "caption": "string, 2-4 sentences, engaging, no hashtags inside it",
  "hashtags": ["#tag1", "#tag2", "5 to 8 relevant hashtags"],
  "cta": "short call to action",
  "image_prompt": "a descriptive prompt for generating a branded social media image",
  "reel_idea": "a short video idea, or an empty string when not requested"
}

All values must be valid JSON values. Escape quotation marks and special characters correctly.
"""


class GeminiAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def _call_gemini(
    url: str,
    body: dict,
    api_key: str,
    timeout: int,
    api_revision: str | None = None,
) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    if api_revision:
        headers["Api-Revision"] = api_revision

    gemini_request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(gemini_request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:1000]
        logger.warning(
            "Gemini request failed (http_status=%s, response=%s)",
            exc.code,
            error_body,
        )
        raise GeminiAPIError(
            f"Gemini API request failed with HTTP status {exc.code}.",
            status_code=exc.code,
        ) from exc

    except (URLError, TimeoutError) as exc:
        logger.warning(
            "Could not reach Gemini API (%s)",
            type(exc).__name__,
        )
        raise GeminiAPIError(
            "Could not connect to the Gemini API."
        ) from exc

    except json.JSONDecodeError as exc:
        logger.error("Gemini returned a non-JSON API response")
        raise GeminiAPIError(
            "Gemini returned an invalid API response."
        ) from exc

    if not isinstance(response_data, dict):
        raise GeminiAPIError("Gemini returned an invalid response.")

    return response_data


def _parse_post_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Recover a JSON object if Gemini added text outside the JSON.
    decoder = json.JSONDecoder()

    for index, character in enumerate(cleaned):
        if character != "{":
            continue

        try:
            data, _ = decoder.raw_decode(cleaned[index:])
            if isinstance(data, dict):
                logger.warning(
                    "Recovered JSON object from Gemini response with extra text."
                )
                return data
        except json.JSONDecodeError:
            continue

    logger.error(
        "Gemini post JSON parsing failed (response_length=%s)",
        len(raw_text),
    )
    raise GeminiAPIError("Gemini returned malformed post content.")


def _extract_generated_image(response_data: dict) -> str:
    status = response_data.get("status")

    if status not in (None, "completed"):
        raise GeminiAPIError(
            f"Gemini image generation did not complete (status: {status})."
        )

    content_items = []

    for step in response_data.get("steps") or []:
        if not isinstance(step, dict):
            continue

        step_content = step.get("content")

        if isinstance(step_content, list):
            content_items.extend(step_content)

    output_image = response_data.get("output_image")

    if isinstance(output_image, dict):
        content_items.append(output_image)

    for item in content_items:
        if not isinstance(item, dict):
            continue

        inline_data = (
            item.get("inline_data")
            or item.get("inlineData")
            or {}
        )

        if not isinstance(inline_data, dict):
            inline_data = {}

        image_data = (
            item.get("data")
            or inline_data.get("data")
        )

        mime_type = (
            item.get("mime_type")
            or item.get("mimeType")
            or inline_data.get("mime_type")
            or inline_data.get("mimeType")
        )

        if (
            isinstance(image_data, str)
            and image_data
            and isinstance(mime_type, str)
            and mime_type.startswith("image/")
        ):
            logger.info(
                "Gemini generated image successfully (mime_type=%s, base64_length=%s)",
                mime_type,
                len(image_data),
            )
            return f"data:{mime_type};base64,{image_data}"

    logger.error(
        "Gemini completed without recognizable image data. "
        "Response keys: %s",
        list(response_data.keys()),
    )

    raise GeminiAPIError(
        "Gemini completed without returning image data."
    )


def _build_user_prompt(request: GenerateContentRequest) -> str:
    business = request.business_profile

    occasion_line = (
        f"Occasion / theme to write about: {request.occasion}."
        if request.occasion
        else (
            f"No specific occasion was given — pick something naturally relevant "
            f"for today ({date.today().isoformat()}) for this type of business "
            f"(e.g. a seasonal angle, a general trust/quality angle, "
            f"or a light promotional angle)."
        )
    )

    colors = (
        ", ".join(business.brand_colors)
        if business.brand_colors
        else "not specified"
    )

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
    request: GenerateContentRequest,
    api_key: Optional[str] = None,
) -> dict:
    """Generate branded social media content and optionally a generated image."""

    provider_api_key = api_key or settings.api_key

    if not provider_api_key:
        raise RuntimeError(
            "No API key was provided. Add one in the app or configure API_KEY on the server."
        )

    model = settings.gemini_model
    url = GEMINI_API_URL.format(model=quote(model, safe=""))

    body = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {"parts": [{"text": _build_user_prompt(request)}]}
        ],
        "generationConfig": {
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
        },
    }

    logger.info(
        "Starting Gemini content generation (model=%s)",
        model,
    )

    response_data = _call_gemini(
        url,
        body,
        provider_api_key,
        timeout=75,
    )

    candidates = response_data.get("candidates") or []

    if not candidates:
        block_reason = (
            response_data.get("promptFeedback") or {}
        ).get("blockReason")

        logger.warning(
            "Gemini returned no candidates (block_reason=%s)",
            block_reason,
        )

        raise GeminiAPIError(
            f"Gemini did not generate a response "
            f"(block reason: {block_reason or 'unknown'})."
        )

    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []

    raw_text = "".join(
        part["text"]
        for part in parts
        if isinstance(part, dict)
        and isinstance(part.get("text"), str)
    ).strip()

    if not raw_text:
        finish_reason = candidate.get("finishReason", "unknown")

        raise GeminiAPIError(
            f"Gemini returned no text content "
            f"(finish reason: {finish_reason})."
        )

    data = _parse_post_json(raw_text)

    caption = data.get("caption")

    if not isinstance(caption, str) or not caption.strip():
        raise GeminiAPIError(
            "Gemini response did not include a valid caption."
        )

    hashtags = data.get("hashtags", [])

    if not isinstance(hashtags, list):
        hashtags = []

    cta = data.get("cta", "")

    if not isinstance(cta, str):
        cta = ""

    profile = request.business_profile

    image_prompt = (
        data.get("image_prompt", "")
        if request.include_image_prompt
        else ""
    )

    if not isinstance(image_prompt, str):
        image_prompt = ""

    generated_image = None

    if request.include_image_prompt:
        if not image_prompt.strip():
            raise GeminiAPIError(
                "Gemini response did not include an image prompt."
            )

        image_request = {
            "model": settings.gemini_image_model,
            "input": (
                "Create one polished, square social media image based on "
                "this art direction. "
                "Use the business brand colors and visual identity. "
                "Create a professional, realistic, high-quality image. "
                "Do not add text, captions, watermarks, or logos to the image itself:\n\n"
                f"{image_prompt.strip()}"
            ),
            "response_format": {
                "type": "image",
                "mime_type": "image/png",
                "aspect_ratio": "1:1",
                "image_size": "1K",
            },
            "store": False,
        }

        logger.info(
            "Starting Gemini image generation (model=%s)",
            settings.gemini_image_model,
        )

        image_response = _call_gemini(
            GEMINI_INTERACTIONS_API_URL,
            image_request,
            provider_api_key,
            timeout=150,
            api_revision="2026-05-20",
        )

        generated_image = _extract_generated_image(image_response)

    reel_idea = data.get("reel_idea", "")

    if not isinstance(reel_idea, str):
        reel_idea = ""

    return {
        "caption": caption.strip(),
        "hashtags": hashtags if request.include_hashtags else [],
        "cta": cta if request.include_cta else "",
        "image_prompt": image_prompt,
        "generated_image": generated_image,
        "reel_idea": reel_idea if request.include_reel_idea else None,
        "business_id": profile.id,
        "model_used": model,
    }
