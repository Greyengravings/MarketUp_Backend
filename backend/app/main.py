
import os
import hmac
import json
import urllib.request
import urllib.error
from urllib.parse import quote

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.core.config import settings
from app.routers import ai_content, auth, business

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MarketUp API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(business.router)
app.include_router(ai_content.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/gemini-check")
def gemini_check(
    x_diagnostic_token: str | None = Header(default=None)
):
    expected_token = os.getenv("DEBUG_DIAGNOSTIC_TOKEN", "")

    if (
        not expected_token
        or not x_diagnostic_token
        or not hmac.compare_digest(x_diagnostic_token, expected_token)
    ):
        raise HTTPException(status_code=404, detail="Not found")

    api_key = settings.api_key
    model = settings.gemini_model

    result = {
        "api_key_configured": bool(api_key),
        "model_configured": model,
        "models_endpoint_status": None,
        "generation_status": None,
        "generation_result": None,
    }

    if not api_key:
        result["error"] = "API_KEY is missing in the backend environment."
        return result

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    # Test 1: Ask Google which models are available.
    models_url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
    )

    models_request = urllib.request.Request(
        models_url,
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(models_request, timeout=25) as response:
            models_data = json.loads(response.read().decode())
            result["models_endpoint_status"] = response.status

            available_models = [
                item.get("name", "").replace("models/", "")
                for item in models_data.get("models", [])
                if "generateContent" in item.get(
                    "supportedGenerationMethods", []
                )
            ]

            result["configured_model_available"] = model in available_models
            result["available_flash_models"] = [
                item for item in available_models if "flash" in item.lower()
            ]

    except urllib.error.HTTPError as error:
        result["models_endpoint_status"] = error.code
        result["models_error"] = error.read().decode()[:2000]
        return result

    except Exception as error:
        result["models_error"] = str(error)
        return result

    # Test 2: Generate a tiny text response using the configured model.
    encoded_model = quote(model, safe="-.")

    generation_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{encoded_model}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Reply with exactly: MarketUp test successful"}
                ]
            }
        ]
    }

    generation_request = urllib.request.Request(
        generation_url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            generation_request, timeout=40
        ) as response:
            response_data = json.loads(response.read().decode())

            result["generation_status"] = response.status
            result["generation_result"] = (
                response_data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "No text returned")
            )

    except urllib.error.HTTPError as error:
        result["generation_status"] = error.code
        result["generation_error"] = error.read().decode()[:3000]

    except Exception as error:
        result["generation_error"] = str(error)

    return result
