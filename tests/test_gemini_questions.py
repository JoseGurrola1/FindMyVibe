import json
import os
import unittest
from unittest.mock import patch

import httpx
from google.genai import errors, types
from google.genai import Client as RealClient
from pydantic import ValidationError

from gemini_questions import (
    GeminiAPIError,
    InvalidResponseError,
    MissingCredentialsError,
    SessionData,
    generate_next_question,
)


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.session = SessionData(
            location="Austin, TX",
            active_preferences={"budget": "free"},
            previous_questions=["What is your budget?"],
            answers=["Free"],
        )
        self.valid = {
            "question": "What atmosphere sounds appealing?",
            "options": ["Quiet", "Lively"],
            "target_attribute": "atmosphere",
        }
        env = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-never-send"})
        env.start()
        self.addCleanup(env.stop)
        client_patch = patch("gemini_questions.genai.Client")
        self.client_factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.client = self.client_factory.return_value.__enter__.return_value
        self.respond(json.dumps(self.valid))

    def respond(self, text):
        # Use the real SDK response type so text extraction is exercised too.
        self.client.models.generate_content.return_value = types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(parts=[types.Part(text=text)]))]
        )

    def test_valid_question_and_request_contract(self):
        result = generate_next_question(self.session)
        self.assertEqual(result.model_dump(), self.valid)
        self.client_factory.assert_called_once()
        self.assertEqual(self.client_factory.call_args.kwargs["api_key"], "test-key-never-send")
        self.assertFalse(self.client_factory.call_args.kwargs["vertexai"])
        options = self.client_factory.call_args.kwargs["http_options"]
        self.assertEqual(options.timeout, 90_000)
        self.assertEqual(options.retry_options.attempts, 1)
        self.client.models.generate_content.assert_called_once()
        request = self.client.models.generate_content.call_args.kwargs
        self.assertEqual(json.loads(request["contents"]), self.session.model_dump())
        self.assertEqual(request["config"].response_mime_type, "application/json")
        schema = request["config"].response_json_schema
        self.assertEqual(schema["properties"]["options"]["minItems"], 2)
        self.assertEqual(schema["properties"]["options"]["maxItems"], 4)
        self.assertFalse(schema["additionalProperties"])
        self.client_factory.return_value.__exit__.assert_called_once()

    def test_accepts_two_three_or_four_options(self):
        for count in (2, 3, 4):
            with self.subTest(count=count):
                self.respond(json.dumps({**self.valid, "options": [f"Choice {i}" for i in range(count)]}))
                self.assertEqual(len(generate_next_question(self.session).options), count)

    def test_missing_or_blank_credentials_do_not_call_api(self):
        for key in (None, "", "  "):
            with self.subTest(key=key), patch.dict(os.environ, {}, clear=True):
                if key is not None:
                    os.environ["GEMINI_API_KEY"] = key
                with self.assertRaises(MissingCredentialsError):
                    generate_next_question(self.session)
        self.client_factory.assert_not_called()

    def test_api_failure_is_clear_and_redacted(self):
        for code in (400, 403, 429, 503):
            with self.subTest(code=code):
                self.client.models.generate_content.side_effect = errors.APIError(
                    code, {"error": {"message": "sensitive service details test-key-never-send"}}
                )
                with self.assertRaises(GeminiAPIError) as caught:
                    generate_next_question(self.session)
                self.assertIn(str(code), str(caught.exception))
                self.assertNotIn("test-key", str(caught.exception))

    def test_network_failure_and_timeout(self):
        for error in (httpx.ConnectError("private URL"), httpx.ReadTimeout("private URL")):
            with self.subTest(error=type(error).__name__):
                self.client.models.generate_content.side_effect = error
                with self.assertRaises(GeminiAPIError) as caught:
                    generate_next_question(self.session)
                self.assertNotIn("private URL", str(caught.exception))

    def test_invalid_json(self):
        for text in ("not JSON", "```json\n{}\n```", "null", "[]"):
            with self.subTest(text=text):
                self.respond(text)
                with self.assertRaises(InvalidResponseError):
                    generate_next_question(self.session)

    def test_invalid_fields(self):
        for changes in (
            {"question": "  "},
            {"question": 42},
            {"options": ["Only one"]},
            {"options": ["a", "b", "c", "d", "e"]},
            {"options": ["a", " "]},
            {"options": ["Quiet", " quiet "]},
            {"options": [1, 2]},
            {"target_attribute": ""},
            {"unexpected": "extra field"},
        ):
            with self.subTest(changes=changes):
                self.respond(json.dumps({**self.valid, **changes}))
                with self.assertRaises(InvalidResponseError):
                    generate_next_question(self.session)

    def test_missing_required_fields(self):
        for field in self.valid:
            with self.subTest(field=field):
                self.respond(json.dumps({k: v for k, v in self.valid.items() if k != field}))
                with self.assertRaises(InvalidResponseError):
                    generate_next_question(self.session)

    def test_blocked_or_empty_response(self):
        self.client.models.generate_content.return_value = types.GenerateContentResponse()
        with self.assertRaisesRegex(InvalidResponseError, "no question text"):
            generate_next_question(self.session)

    def test_repeated_question(self):
        self.respond(json.dumps({**self.valid, "question": "  WHAT IS YOUR BUDGET? "}))
        with self.assertRaisesRegex(InvalidResponseError, "repeated"):
            generate_next_question(self.session)

    def test_incomplete_session_history_is_rejected(self):
        with self.assertRaises(ValidationError):
            SessionData(**{**self.session.model_dump(), "answers": []})

    def test_new_session_and_model_override(self):
        session = SessionData(location="Austin, TX", active_preferences={}, previous_questions=[], answers=[])
        generate_next_question(session, model="explicit-model")
        self.assertEqual(self.client.models.generate_content.call_args.kwargs["model"], "explicit-model")

    def test_real_sdk_serializes_structured_request(self):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(200, json={
                "candidates": [{
                    "content": {"role": "model", "parts": [{"text": json.dumps(self.valid)}]},
                    "finishReason": "STOP",
                }],
            })

        def make_client(**kwargs):
            kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handle)}
            return RealClient(**kwargs)

        self.client_factory.side_effect = make_client
        self.assertEqual(generate_next_question(self.session).model_dump(), self.valid)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.host, "generativelanguage.googleapis.com")
        self.assertEqual(requests[0].headers["x-goog-api-key"], "test-key-never-send")
        body = json.loads(requests[0].content)
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(
            body["generationConfig"]["responseJsonSchema"]["properties"]["options"]["maxItems"], 4
        )
        self.assertEqual(json.loads(body["contents"][0]["parts"][0]["text"]), self.session.model_dump())


if __name__ == "__main__":
    unittest.main()
