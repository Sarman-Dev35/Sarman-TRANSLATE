import json
import unittest
from unittest.mock import patch

from gemini_settings import ModelFetchWorker


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class GeminiSettingsTests(unittest.TestCase):
    def test_model_fetch_paginates_and_filters_generate_content(self):
        pages = [
            FakeResponse({
                "models": [
                    {"name": "models/gemini-flash-a", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embed-a", "supportedGenerationMethods": ["embedContent"]},
                ],
                "nextPageToken": "next-page",
            }),
            FakeResponse({
                "models": [
                    {"name": "models/gemini-flash-b", "supportedGenerationMethods": ["generateContent"]},
                ],
            }),
        ]
        completed = []
        failed = []
        worker = ModelFetchWorker("test-api-key")
        worker.completed.connect(completed.append)
        worker.failed.connect(failed.append)
        with patch("gemini_settings.urllib.request.urlopen", side_effect=pages) as urlopen:
            worker.run()
        self.assertEqual(len(urlopen.call_args_list), 2)
        self.assertFalse(failed)
        self.assertEqual([item["name"] for item in completed[0]], [
            "models/gemini-flash-a", "models/gemini-flash-b"
        ])
        first_request = urlopen.call_args_list[0].args[0]
        second_request = urlopen.call_args_list[1].args[0]
        self.assertNotIn("test-api-key", first_request.full_url)
        self.assertIn("next-page", second_request.full_url)
        self.assertEqual(first_request.get_header("X-goog-api-key"), "test-api-key")


if __name__ == "__main__":
    unittest.main()
