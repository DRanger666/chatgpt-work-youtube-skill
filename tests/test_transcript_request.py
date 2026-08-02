import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPOSITORY_ROOT / "scripts" / "build_gemini_chunk_request.py"


class TranscriptRequestTests(unittest.TestCase):
    def build(self, *arguments, start_seconds=0, end_seconds=600):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "request.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--video-url",
                    "https://www.youtube.com/watch?v=test",
                    "--start-seconds",
                    str(start_seconds),
                    "--end-seconds",
                    str(end_seconds),
                    "--output",
                    str(output),
                    *arguments,
                ],
                capture_output=True,
                text=True,
            )
            request = json.loads(output.read_text()) if output.exists() else None
            return result, request

    def test_transcript_mode_builds_tested_contract(self):
        result, request = self.build("--transcript-only")

        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = request["contents"][0]["parts"][1]["text"]
        generation = request["generationConfig"]
        schema = generation["responseJsonSchema"]

        self.assertTrue(prompt.startswith("TRANSCRIPT-ONLY MODE."))
        self.assertIn("do not summarize", prompt)
        self.assertIn("Do not describe visuals", prompt)
        self.assertEqual(generation["maxOutputTokens"], 8192)
        self.assertEqual(generation["responseMimeType"], "application/json")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["properties"]["segments"]["items"]["properties"]["vocal_type"]["enum"],
            ["sung", "spoken", "spoken_over_music", "other"],
        )
        self.assertEqual(
            schema["properties"]["clip_start_timestamp"]["pattern"],
            r"^[0-9]{2,}:[0-5][0-9]\.[0-9]{3}$",
        )

    def test_transcript_mode_supports_timestamps_after_two_hours(self):
        result, request = self.build(
            "--transcript-only",
            start_seconds=7200,
            end_seconds=7800,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        video = request["contents"][0]["parts"][0]["videoMetadata"]
        pattern = request["generationConfig"]["responseJsonSchema"]["properties"][
            "clip_start_timestamp"
        ]["pattern"]

        self.assertEqual(video, {"startOffset": "7200s", "endOffset": "7800s"})
        self.assertIsNotNone(re.fullmatch(pattern, "120:00.000"))
        self.assertIsNone(re.fullmatch(pattern, "9:00.000"))

    def test_prompt_driven_request_uses_plain_text_output(self):
        result, request = self.build("--prompt", "Analyze this interval.")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            request["contents"][0]["parts"][1]["text"],
            "Analyze this interval.",
        )
        self.assertEqual(
            request["generationConfig"],
            {"maxOutputTokens": 2048},
        )

    def test_transcript_mode_rejects_a_custom_prompt(self):
        result, request = self.build(
            "--transcript-only",
            "--prompt",
            "Describe the visuals.",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(request)
        self.assertIn("cannot be combined", result.stderr)


if __name__ == "__main__":
    unittest.main()
