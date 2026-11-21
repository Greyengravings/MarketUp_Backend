import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.core.config import settings
from app.schemas import GenerateContentRequest, GenerationBusinessProfile
from app.services.ai_service import (
    GeminiAPIError,
    _extract_generated_image,
    generate_post_content,
)


class GeneratePostContentTests(unittest.TestCase):
    def setUp(self):
        profile = GenerationBusinessProfile(
            id="business-1",
            business_name="Test Cafe",
            sector="Food",
        )
        self.payload = GenerateContentRequest(business_profile=profile)

    def test_sends_app_key_and_extracts_gemini_text(self):
        generated = {
            "caption": "A fresh cup for your day.",
            "hashtags": ["#Cafe"],
            "cta": "Visit us today!",
            "image_prompt": "A warm cafe scene",
            "reel_idea": "Pouring coffee",
        }
        response_body = {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(generated)}]}}
            ]
        }
        image_response = {
            "status": "completed",
            "steps": [
                {
                    "type": "model_output",
                    "content": [
                        {
                            "type": "image",
                            "mime_type": "image/png",
                            "data": "aGVsbG8=",
                        }
                    ],
                }
            ],
        }

        with (
            patch.object(settings, "api_key", "server-key"),
            patch(
                "app.services.ai_service.urlopen",
                side_effect=[
                    io.BytesIO(json.dumps(response_body).encode()),
                    io.BytesIO(json.dumps(image_response).encode()),
                ],
            ) as urlopen_mock,
        ):
            result = generate_post_content(self.payload, api_key="app-key")

        request = urlopen_mock.call_args_list[0].args[0]
        api_key_header = next(
            value
            for name, value in request.header_items()
            if name.lower() == "x-goog-api-key"
        )
        sent_body = json.loads(request.data)
        self.assertEqual(api_key_header, "app-key")
        self.assertEqual(
            sent_body["generationConfig"]["responseMimeType"], "application/json"
        )
        self.assertEqual(result["caption"], generated["caption"])
        self.assertEqual(result["image_prompt"], generated["image_prompt"])
        self.assertEqual(
            result["generated_image"], "data:image/png;base64,aGVsbG8="
        )
        self.assertEqual(result["business_id"], "business-1")
        image_request = urlopen_mock.call_args_list[1].args[0]
        image_request_body = json.loads(image_request.data)
        self.assertEqual(
            image_request_body["model"], settings.gemini_image_model
        )
        self.assertIn(generated["image_prompt"], image_request_body["input"])
        self.assertFalse(image_request_body["store"])
        image_api_key = next(
            value
            for name, value in image_request.header_items()
            if name.lower() == "x-goog-api-key"
        )
        self.assertEqual(image_api_key, "app-key")
        self.assertEqual(
            image_request.get_header("Api-revision"), "2026-05-20"
        )

    def test_provider_http_error_is_reported_without_echoing_key(self):
        provider_error = HTTPError(
            "https://generativelanguage.googleapis.com/",
            403,
            "Forbidden",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"API key rejected"}}'),
        )

        with (
            patch.object(settings, "api_key", ""),
            patch("app.services.ai_service.urlopen", side_effect=provider_error),
        ):
            with self.assertRaises(GeminiAPIError) as raised:
                generate_post_content(self.payload, api_key="private-app-key")

        self.assertEqual(raised.exception.status_code, 403)
        self.assertNotIn("private-app-key", str(raised.exception))

    def test_uses_server_key_when_app_key_is_not_provided(self):
        response_body = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps(
                                    {
                                        "caption": "A fresh cup for your day.",
                                        "hashtags": [],
                                        "cta": "",
                                        "image_prompt": "",
                                    }
                                )
                            }
                        ]
                    }
                }
            ]
        }

        with (
            patch.object(settings, "api_key", "server-key"),
            patch(
                "app.services.ai_service.urlopen",
                return_value=io.BytesIO(json.dumps(response_body).encode()),
            ) as urlopen_mock,
        ):
            generate_post_content(
                self.payload.model_copy(update={"include_image_prompt": False})
            )

        api_key_header = next(
            value
            for name, value in urlopen_mock.call_args.args[0].header_items()
            if name.lower() == "x-goog-api-key"
        )
        self.assertEqual(api_key_header, "server-key")

    def test_requires_an_app_or_server_key(self):
        with patch.object(settings, "api_key", ""):
            with self.assertRaisesRegex(RuntimeError, "No API key was provided"):
                generate_post_content(self.payload)

    def test_completed_interaction_without_image_fails_explicitly(self):
        with self.assertRaisesRegex(GeminiAPIError, "without returning image data"):
            _extract_generated_image({"status": "completed", "steps": []})


if __name__ == "__main__":
    unittest.main()
