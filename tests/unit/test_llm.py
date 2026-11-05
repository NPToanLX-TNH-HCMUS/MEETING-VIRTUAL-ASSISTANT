import json
import unittest
from unittest.mock import Mock, patch

from src.backend.utils.llm import FALLBACK_MODEL, PRIMARY_MODEL, call_llm

SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}


def _success_response(content: str) -> Mock:
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [
            {"message": {"content": content}, "finish_reason": "stop"},
        ],
    }
    return response


class TestCallLLM(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(
            patch.dict(
                "os.environ",
                {"GROQ_API_KEY": "test-groq", "OPENROUTER_API_KEY": "test-openrouter"},
            )
        )
        self.enterContext(patch("src.backend.utils.llm.load_dotenv"))
        self.enterContext(patch("src.backend.utils.llm.sleep"))
        self.mock_post = self.enterContext(patch("src.backend.utils.llm.requests.post"))

    def test_retries_primary_before_calling_fallback(self) -> None:
        unavailable = Mock(ok=False, status_code=503)
        self.mock_post.side_effect = [
            unavailable,
            unavailable,
            _success_response('{"summary": "The prototype was approved."}'),
        ]

        result = call_llm("Summarize the meeting.", _schema=SCHEMA)

        self.assertEqual(json.loads(result), {"summary": "The prototype was approved."})
        payloads = [request.kwargs["json"] for request in self.mock_post.call_args_list]
        self.assertEqual(
            [payload["model"] for payload in payloads],
            [PRIMARY_MODEL, PRIMARY_MODEL, FALLBACK_MODEL],
        )
        for payload in payloads:
            self.assertEqual(payload["response_format"]["json_schema"]["schema"], SCHEMA)

    def test_retries_when_output_does_not_match_schema(self) -> None:
        self.mock_post.side_effect = [
            _success_response('{"summary": 123}'),
            _success_response('{"summary": "The meeting ended."}'),
        ]

        result = call_llm("Summarize the meeting.", _schema=SCHEMA)

        self.assertEqual(json.loads(result), {"summary": "The meeting ended."})
        self.assertEqual(self.mock_post.call_count, 2)
        for request in self.mock_post.call_args_list:
            self.assertEqual(request.kwargs["json"]["model"], PRIMARY_MODEL)


if __name__ == "__main__":
    unittest.main()