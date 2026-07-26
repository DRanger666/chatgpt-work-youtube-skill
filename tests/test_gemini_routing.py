#!/usr/bin/env python3

import argparse
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = REPOSITORY_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gemini_request = load_script("gemini_request")
gemini_cache = load_script("gemini_cache")


def response(status, error_status=None, message="", headers=None):
    if 200 <= status < 300:
        payload = {
            "candidates": [
                {
                    "content": {"parts": [{"text": json.dumps({"ok": True})}]},
                    "finishReason": "STOP",
                }
            ],
            "modelVersion": "test-model",
            "usageMetadata": {"totalTokenCount": 1},
        }
    else:
        payload = {
            "error": {
                "code": status,
                "status": error_status or "ERROR",
                "message": message,
            }
        }
    return status, headers or {}, json.dumps(payload).encode("utf-8")


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.keys = []

    def __call__(self, endpoint, api_key, request_bytes, timeout_seconds):
        self.keys.append(api_key)
        if not self.responses:
            raise AssertionError("Unexpected extra request")
        return self.responses.pop(0)


class GeminiRouterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.request = self.root / "request.json"
        self.request.write_text('{"contents":[]}\n', encoding="utf-8")
        self.response = self.root / "response.json"
        self.routing = self.root / "routing.json"
        self.state = self.root / "state.json"
        self.environment = mock.patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "test-primary",
                "GEMINI_API_KEY_FALLBACK": "test-fallback",
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def args(self, **overrides):
        values = {
            "request": str(self.request),
            "response": str(self.response),
            "routing_metadata": str(self.routing),
            "state": str(self.state),
            "endpoint": "https://example.invalid/generate",
            "timeout_seconds": 1.0,
            "max_transient_retries": 1,
            "base_backoff_seconds": 0.0,
            "max_backoff_seconds": 0.0,
            "default_cooldown_seconds": 60.0,
            "default_transient_cooldown_seconds": 30.0,
            "jitter_seconds": 0.0,
            "no_sleep": True,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def run_with(self, responses, **overrides):
        transport = FakeTransport(responses)
        with mock.patch.object(gemini_request, "send_request", transport):
            with mock.patch.object(gemini_request.random, "uniform", return_value=0.0):
                with contextlib.redirect_stdout(io.StringIO()):
                    result = gemini_request.run(self.args(**overrides))
        return result, transport

    def test_primary_success(self):
        result, transport = self.run_with([response(200)])
        self.assertEqual(result, 0)
        self.assertEqual(transport.keys, ["test-primary"])
        routing = json.loads(self.routing.read_text(encoding="utf-8"))
        self.assertEqual(routing["selectedBucket"], "primary")
        self.assertEqual(routing["attempts"][0]["classification"], "success")

    def test_rate_limit_cools_primary_and_uses_fallback(self):
        result, transport = self.run_with(
            [
                response(
                    429,
                    "RESOURCE_EXHAUSTED",
                    "Please retry in 30s.",
                    {"Retry-After": "30"},
                ),
                response(200),
            ]
        )
        self.assertEqual(result, 0)
        self.assertEqual(transport.keys, ["test-primary", "test-fallback"])
        routing = json.loads(self.routing.read_text(encoding="utf-8"))
        self.assertEqual(
            [attempt["classification"] for attempt in routing["attempts"]],
            ["rate_limited", "success"],
        )
        self.assertEqual(routing["attempts"][0]["retryDelaySeconds"], 30.0)
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertIsNotNone(state["buckets"]["primary"]["cooldownUntil"])

    def test_both_buckets_rate_limited(self):
        result, transport = self.run_with(
            [
                response(429, "RESOURCE_EXHAUSTED", "Retry in 10s."),
                response(429, "RESOURCE_EXHAUSTED", "Retry in 20s."),
            ]
        )
        self.assertEqual(result, 3)
        self.assertEqual(transport.keys, ["test-primary", "test-fallback"])
        routing = json.loads(self.routing.read_text(encoding="utf-8"))
        self.assertEqual(routing["status"], "failed")
        self.assertEqual(len(routing["attempts"]), 2)

    def test_transient_retry_stays_on_same_bucket(self):
        result, transport = self.run_with(
            [response(503, "UNAVAILABLE"), response(200)]
        )
        self.assertEqual(result, 0)
        self.assertEqual(transport.keys, ["test-primary", "test-primary"])
        routing = json.loads(self.routing.read_text(encoding="utf-8"))
        self.assertEqual(
            [attempt["classification"] for attempt in routing["attempts"]],
            ["transient", "success"],
        )

    def test_invalid_request_does_not_touch_fallback(self):
        result, transport = self.run_with(
            [response(400, "INVALID_ARGUMENT", "Malformed video metadata")]
        )
        self.assertEqual(result, 2)
        self.assertEqual(transport.keys, ["test-primary"])
        routing = json.loads(self.routing.read_text(encoding="utf-8"))
        self.assertEqual(routing["attempts"][0]["classification"], "request_failure")

    def test_invalid_primary_key_uses_fallback(self):
        result, transport = self.run_with(
            [
                response(400, "INVALID_ARGUMENT", "API key not valid"),
                response(200),
            ]
        )
        self.assertEqual(result, 0)
        self.assertEqual(transport.keys, ["test-primary", "test-fallback"])
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertTrue(state["buckets"]["primary"]["disabled"])

    def test_existing_primary_cooldown_starts_with_fallback(self):
        state = {
            "schemaVersion": 1,
            "buckets": {
                "primary": {
                    "cooldownUntil": "2999-01-01T00:00:00Z",
                    "disabled": False,
                    "reason": "rate_limited",
                },
                "fallback": {
                    "cooldownUntil": None,
                    "disabled": False,
                    "reason": None,
                },
            },
        }
        self.state.write_text(json.dumps(state), encoding="utf-8")
        result, transport = self.run_with([response(200)])
        self.assertEqual(result, 0)
        self.assertEqual(transport.keys, ["test-fallback"])

    def test_duplicate_credential_does_not_create_a_second_bucket(self):
        with mock.patch.dict(
            os.environ,
            {"GEMINI_API_KEY_FALLBACK": "test-primary"},
            clear=False,
        ):
            result, transport = self.run_with(
                [response(429, "RESOURCE_EXHAUSTED", "Retry in 10s.")]
            )
        self.assertEqual(result, 3)
        self.assertEqual(transport.keys, ["test-primary"])

    def test_retry_info_delay_is_respected_without_secret_state(self):
        rate_limited = {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exhausted",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "53s",
                    }
                ],
            }
        }
        result, _ = self.run_with(
            [
                (429, {}, json.dumps(rate_limited).encode("utf-8")),
                response(200),
            ]
        )
        self.assertEqual(result, 0)
        routing_text = self.routing.read_text(encoding="utf-8")
        state_text = self.state.read_text(encoding="utf-8")
        self.assertEqual(json.loads(routing_text)["attempts"][0]["retryDelaySeconds"], 53.0)
        self.assertNotIn("test-primary", routing_text + state_text)
        self.assertNotIn("test-fallback", routing_text + state_text)


class GeminiCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.request = self.root / "request.json"
        self.request.write_text('{"contents":[]}\n', encoding="utf-8")
        self.records = self.root / "records"

    def tearDown(self):
        self.temporary.cleanup()

    def start_args(self, retry_reason=None):
        return argparse.Namespace(
            request=str(self.request),
            output_dir=str(self.records),
            video_id="video",
            video_url="https://youtu.be/video",
            route="generate-content",
            model="test-model",
            prompt="test",
            clip_start=0,
            clip_end=30,
            retry_reason=retry_reason,
        )

    def test_attempt_history_survives_documented_retry(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini_cache.start(self.start_args()), 0)
        record_path = next(self.records.glob("*.json"))
        routing = self.root / "routing.json"
        routing.write_text(
            json.dumps(
                {
                    "selectedBucket": None,
                    "attempts": [
                        {
                            "bucket": "primary",
                            "startedAt": "2026-01-01T00:00:00Z",
                            "finishedAt": "2026-01-01T00:00:01Z",
                            "httpStatus": 429,
                            "classification": "rate_limited",
                            "retryDelaySeconds": 60,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        error_response = self.root / "error.json"
        error_response.write_text(
            json.dumps(
                {
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "message": "rate limited",
                    }
                }
            ),
            encoding="utf-8",
        )
        finish_args = argparse.Namespace(
            record=str(record_path),
            status="failed",
            http_status=429,
            response=str(error_response),
            error_message=None,
            conclusion="Retry through another project is permitted.",
            routing_metadata=str(routing),
            bucket="unrecorded",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini_cache.finish(finish_args), 0)
            self.assertEqual(gemini_cache.start(self.start_args()), 5)
            self.assertEqual(
                gemini_cache.start(self.start_args("project rate limit failover")),
                0,
            )
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["schemaVersion"], 2)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(len(record["attempts"]), 1)
        self.assertEqual(record["attempts"][0]["bucket"], "primary")
        self.assertTrue(record["retrySameRequest"])

        routing.write_text(
            json.dumps(
                {
                    "selectedBucket": "fallback",
                    "attempts": [
                        {
                            "bucket": "fallback",
                            "startedAt": "2026-01-01T00:01:00Z",
                            "finishedAt": "2026-01-01T00:01:01Z",
                            "httpStatus": 200,
                            "classification": "success",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        success_response = self.root / "success.json"
        success_response.write_text(
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": json.dumps({"ok": True})}]
                            },
                            "finishReason": "STOP",
                        }
                    ],
                    "modelVersion": "test-model",
                    "usageMetadata": {"totalTokenCount": 1},
                }
            ),
            encoding="utf-8",
        )
        success_finish_args = argparse.Namespace(
            record=str(record_path),
            status="succeeded",
            http_status=200,
            response=str(success_response),
            error_message=None,
            conclusion="Fallback project succeeded.",
            routing_metadata=str(routing),
            bucket="unrecorded",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini_cache.finish(success_finish_args), 0)
        succeeded = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(succeeded["status"], "succeeded")
        self.assertEqual([item["bucket"] for item in succeeded["attempts"]], ["primary", "fallback"])
        self.assertEqual(succeeded["selectedBucket"], "fallback")
        self.assertNotIn("error", succeeded)

    def test_migrates_legacy_record(self):
        self.records.mkdir()
        fingerprint = gemini_cache.request_fingerprint(self.request)
        record_path = self.records / f"video--{fingerprint[:16]}.json"
        record_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "videoId": "video",
                    "videoUrl": "https://youtu.be/video",
                    "requestFingerprint": fingerprint,
                    "route": "generate-content",
                    "model": "test-model",
                    "prompt": "test",
                    "status": "failed",
                    "attemptStartedAt": "2026-01-01T00:00:00Z",
                    "attemptFinishedAt": "2026-01-01T00:00:01Z",
                    "httpStatus": 429,
                    "retrySameRequest": False,
                }
            ),
            encoding="utf-8",
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gemini_cache.start(self.start_args("transient retry")), 0)
        migrated = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schemaVersion"], 2)
        self.assertEqual(migrated["attempts"][0]["bucket"], "unrecorded")
        self.assertEqual(migrated["attempts"][0]["httpStatus"], 429)


if __name__ == "__main__":
    unittest.main()
