import copy
import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import gemini_request_log as request_log
import youtube_work_common as common
from build_gemini_chunk_request import TRANSCRIPT_PROMPT, TRANSCRIPT_RESPONSE_SCHEMA


VIDEO_ID = "lhSq1RzDcZg"
ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.6-flash:generateContent"
)
MODEL = "gemini-3.6-flash"
T0 = "2026-08-01T10:00:00Z"
T1 = "2026-08-01T10:00:01Z"
T2 = "2026-08-01T10:00:02Z"


def request_value(video_url=None, prompt="Inspect this interval.", start=0, end=600):
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "fileData": {
                            "fileUri": video_url
                            or f"https://www.youtube.com/watch?v={VIDEO_ID}",
                            "mimeType": "video/*",
                        },
                        "videoMetadata": {
                            "startOffset": f"{start}s",
                            "endOffset": f"{end}s",
                        },
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }


def write_request(path, value=None, compact=False):
    value = value or request_value()
    if compact:
        path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    else:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def attempt(
    number=1,
    classification="success",
    http_status=200,
    started=T0,
    finished=T1,
    bucket="primary",
    **extra,
):
    return {
        "attemptNumber": number,
        "bucket": bucket,
        "startedAt": started,
        "finishedAt": finished,
        "httpStatus": http_status,
        "classification": classification,
        **extra,
    }


def router_result(request, run, response_hash=None, attempts=None, status="succeeded"):
    attempts = attempts if attempts is not None else [attempt()]
    result = {
        "fileFormatVersion": 1,
        "status": status,
        "requestId": request["requestId"],
        "runNumber": run["runNumber"],
        "exactRequestSha256": run["exactRequestSha256"],
        "selectedBucket": attempts[-1]["bucket"] if status == "succeeded" else None,
        "attempts": attempts,
        "completedAt": attempts[-1]["finishedAt"] if attempts else T1,
    }
    if status == "succeeded":
        result["responseSha256"] = response_hash or "a" * 64
    return result


class RequestLogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.request_path = write_request(self.directory / "request.json")

    def tearDown(self):
        self.temporary.cleanup()

    def new_log(self):
        return request_log.new_request_log(VIDEO_ID, updated_at=T0)

    def start_one_time(self, log=None, content_class="direct_answer", **kwargs):
        log = log or self.new_log()
        request, run = request_log.start_run(
            log,
            self.request_path,
            VIDEO_ID,
            ENDPOINT,
            MODEL,
            "POST",
            content_class,
            started_at=kwargs.pop("started_at", T0),
            **kwargs,
        )
        return log, request, run

    def start_transcript(self, log=None, **kwargs):
        log = log or self.new_log()
        transcript_request = request_value(prompt=TRANSCRIPT_PROMPT)
        transcript_request["generationConfig"]["responseJsonSchema"] = (
            TRANSCRIPT_RESPONSE_SCHEMA
        )
        transcript_path = write_request(
            self.directory / "transcript-request.json", transcript_request
        )
        request, run = request_log.start_run(
            log,
            transcript_path,
            VIDEO_ID,
            ENDPOINT,
            MODEL,
            "POST",
            "video_material",
            output_type="transcript",
            output_format={"name": "gemini-transcript", "version": 1},
            language_policy={"sourceLanguage": "original"},
            started_at=kwargs.pop("started_at", T0),
            **kwargs,
        )
        return log, request, run

    def finish_one_time(self, log, request, run, response_value=None):
        response_path = self.directory / f"response-{run['runNumber']}.json"
        common.write_json(response_path, response_value or {"answer": "observed"})
        response_hash = common.sha256_hex(response_path.read_bytes())
        result = router_result(request, run, response_hash=response_hash)
        return request_log.finish_run(
            log,
            request["requestId"],
            run["runNumber"],
            router_result=result,
            response_path=response_path,
            updated_at=T2,
        )

    def test_request_id_normalizes_url_and_json_format_but_exact_hash_does_not(self):
        first = request_log.inspect_request_file(self.request_path)
        second_path = write_request(
            self.directory / "request-compact.json",
            request_value(video_url=f"https://youtu.be/{VIDEO_ID}?si=test"),
            compact=True,
        )
        second = request_log.inspect_request_file(second_path)
        self.assertEqual(first["normalizedRequestSha256"], second["normalizedRequestSha256"])
        self.assertNotEqual(first["exactRequestSha256"], second["exactRequestSha256"])
        first_id = request_log.derive_request_id(
            first["normalizedRequestSha256"], ENDPOINT, MODEL, "POST", VIDEO_ID,
            first["requestedTimeRange"],
        )
        second_id = request_log.derive_request_id(
            second["normalizedRequestSha256"], ENDPOINT, MODEL, "POST", VIDEO_ID,
            second["requestedTimeRange"],
        )
        self.assertEqual(first_id, second_id)

    def test_transcript_run_fixes_reusable_metadata_and_retains_exact_prompt(self):
        log, request, run = self.start_transcript()
        self.assertEqual(request["contentClass"], "video_material")
        self.assertEqual(request["outputType"], "transcript")
        self.assertEqual(request["outputFormat"], {"name": "gemini-transcript", "version": 1})
        self.assertEqual(request["languagePolicy"], {"sourceLanguage": "original"})
        self.assertEqual(request["promptText"], TRANSCRIPT_PROMPT)
        self.assertEqual(run["runNumber"], 1)
        self.assertEqual(run["runStatus"], "pending")
        self.assertNotIn("retryAuthorization", run)
        request_log.validate_request_log(log)

    def test_rejects_invalid_type_format_pair_and_one_time_output_fields(self):
        with self.assertRaisesRegex(common.YouTubeWorkError, "requires output format"):
            request_log.start_run(
                self.new_log(), self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "video_material", output_type="transcript",
                output_format={"name": "gemini-free-form-text", "version": 1},
                started_at=T0,
            )
        with self.assertRaisesRegex(request_log.RequestLogError, "cannot declare"):
            request_log.start_run(
                self.new_log(), self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "direct_answer", output_type="summary",
                output_format={"name": "gemini-free-form-text", "version": 1},
                started_at=T0,
            )

    def test_transcript_label_rejects_a_non_transcript_request(self):
        with self.assertRaisesRegex(request_log.RequestLogError, "transcript-only"):
            request_log.start_run(
                self.new_log(), self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "video_material", output_type="transcript",
                output_format={"name": "gemini-transcript", "version": 1},
                language_policy={"sourceLanguage": "original"},
                started_at=T0,
            )

    def test_reusable_metadata_is_complete_before_a_run_starts(self):
        transcript_request = request_value(prompt=TRANSCRIPT_PROMPT)
        transcript_request["generationConfig"]["responseJsonSchema"] = (
            TRANSCRIPT_RESPONSE_SCHEMA
        )
        transcript_path = write_request(
            self.directory / "metadata-transcript.json", transcript_request
        )
        with self.assertRaisesRegex(request_log.RequestLogError, "original-language"):
            request_log.start_run(
                self.new_log(),
                transcript_path,
                VIDEO_ID,
                ENDPOINT,
                MODEL,
                "POST",
                "video_material",
                output_type="transcript",
                output_format={"name": "gemini-transcript", "version": 1},
                started_at=T0,
            )

    def test_request_logs_and_cli_reject_removed_timestamp_coordinate_fields(self):
        log, _, _ = self.start_transcript()
        for field in ("timestamps" + "RelativeTo", "timestamp" + "Basis"):
            with self.subTest(field=field):
                changed = copy.deepcopy(log)
                changed["requests"][0][field] = "full_video"
                with self.assertRaisesRegex(common.YouTubeWorkError, "unsupported fields"):
                    request_log.validate_request_log(changed)

        parser = request_log.build_parser()
        removed_flag = "--timestamps-" + "relative-to"
        arguments = [
            "start-run",
            "--request-log", "log.json",
            "--request", "request.json",
            "--endpoint", ENDPOINT,
            "--model", MODEL,
            "--video", VIDEO_ID,
            "--output", "updated-log.json",
            "--content-class", "direct_answer",
            removed_flag, "full_video",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(arguments)

    def test_translation_is_not_a_reusable_output_type(self):
        with self.assertRaisesRegex(
            common.YouTubeWorkError, "Unsupported reusable output type"
        ):
            request_log.start_run(
                self.new_log(),
                self.request_path,
                VIDEO_ID,
                ENDPOINT,
                MODEL,
                "POST",
                "video_material",
                output_type="translation",
                output_format={"name": "gemini-free-form-text", "version": 1},
                started_at=T0,
            )

    def test_relabelling_same_request_is_rejected_without_creating_another_identity(self):
        log, request, run = self.start_one_time()
        request_log.mark_run_interrupted(
            log, request["requestId"], run["runNumber"], "Session stopped", True, at=T1
        )
        with self.assertRaisesRegex(request_log.RequestLogError, "conflicting immutable metadata"):
            request_log.start_run(
                log, self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "task_specific_observation", retry_reason="User approved another run",
                started_at=T2,
            )
        self.assertEqual(len(log["requests"]), 1)
        self.assertEqual(len(log["requests"][0]["runs"]), 1)

    def test_only_one_run_for_a_video_can_be_pending(self):
        log, _, _ = self.start_one_time()
        other_path = write_request(
            self.directory / "other.json", request_value(prompt="Different prompt")
        )
        with self.assertRaisesRegex(request_log.PendingRunError, "already pending"):
            request_log.start_run(
                log, other_path, VIDEO_ID, ENDPOINT, MODEL, "POST", "direct_answer",
                started_at=T1,
            )

    def test_one_time_success_is_derived_from_bound_router_result(self):
        log, request, run = self.start_one_time()
        finished_request, finished = self.finish_one_time(log, request, run)
        self.assertEqual(finished["runStatus"], "succeeded")
        self.assertEqual(finished["endedAt"], T1)
        self.assertEqual(finished["routingAttempts"], [attempt()])
        self.assertIs(finished["responseNotSavedByPolicy"], True)
        self.assertNotIn("savedResponseId", finished)
        request_log.validate_request_log(log)

    def test_one_time_success_rejects_missing_or_different_response_bytes(self):
        log, request, run = self.start_one_time()
        result = router_result(request, run, response_hash="b" * 64)
        with self.assertRaisesRegex(request_log.RequestLogError, "actual response file"):
            request_log.finish_run(
                log, request["requestId"], 1, router_result=result, updated_at=T2
            )
        response = self.directory / "wrong.json"
        common.write_json(response, {"wrong": True})
        with self.assertRaisesRegex(request_log.RequestLogError, "response bytes"):
            request_log.finish_run(
                log,
                request["requestId"],
                1,
                router_result=result,
                response_path=response,
                updated_at=T2,
            )
        self.assertEqual(log["requests"][0]["runs"][0]["runStatus"], "pending")

    def test_one_time_success_rejects_failed_or_mismatched_router_result(self):
        log, request, run = self.start_one_time()
        response = self.directory / "response.json"
        common.write_json(response, {"answer": 1})
        failed_attempt = attempt(classification="request_failure", http_status=400)
        failed = router_result(request, run, attempts=[failed_attempt], status="failed")
        with self.assertRaisesRegex(request_log.RequestLogError, "Failed router result"):
            request_log.finish_run(
                log,
                request["requestId"],
                1,
                router_result=failed,
                response_path=response,
                updated_at=T2,
            )
        success = router_result(
            request, run, response_hash=common.sha256_hex(response.read_bytes())
        )
        success["requestId"] = "f" * 64
        with self.assertRaisesRegex(request_log.RequestLogError, "does not belong"):
            request_log.finish_run(
                log,
                request["requestId"],
                1,
                router_result=success,
                response_path=response,
                updated_at=T2,
            )

    def test_failed_run_retains_attempts_and_requires_authorized_retry(self):
        log, request, run = self.start_one_time()
        failed_attempt = attempt(
            classification="transient",
            http_status=503,
            cooldownUntil="2026-08-01T10:05:00Z",
        )
        result = router_result(request, run, attempts=[failed_attempt], status="failed")
        result["earliestCooldownUntil"] = "2026-08-01T10:05:00Z"
        request_log.finish_run(
            log, request["requestId"], 1, router_result=result, updated_at=T2
        )
        self.assertEqual(log["requests"][0]["runs"][0]["runStatus"], "failed")
        self.assertEqual(log["requests"][0]["runs"][0]["routingAttempts"], [failed_attempt])
        with self.assertRaises(request_log.RetryAuthorizationRequired):
            request_log.start_run(
                log, self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "direct_answer", started_at="2026-08-01T10:06:00Z",
            )
        with self.assertRaisesRegex(request_log.RequestLogError, "cooling down"):
            request_log.start_run(
                log, self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "direct_answer", retry_reason="User approved retry",
                started_at="2026-08-01T10:04:00Z",
            )
        _, second = request_log.start_run(
            log, self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
            "direct_answer", retry_reason="User approved retry",
            authorized_at="2026-08-01T10:05:30Z",
            started_at="2026-08-01T10:06:00Z",
        )
        self.assertEqual(second["runNumber"], 2)
        self.assertEqual(second["retryAuthorization"]["usedAt"], "2026-08-01T10:06:00Z")
        self.assertEqual(log["requests"][0]["runs"][0]["runStatus"], "failed")

    def test_terminal_request_failure_cannot_be_repeated_unchanged(self):
        log, request, run = self.start_one_time()
        failed_attempt = attempt(classification="request_failure", http_status=400)
        result = router_result(request, run, attempts=[failed_attempt], status="failed")
        request_log.finish_run(
            log, request["requestId"], 1, router_result=result, updated_at=T1
        )
        with self.assertRaises(request_log.TerminalRequestError):
            request_log.start_run(
                log, self.request_path, VIDEO_ID, ENDPOINT, MODEL, "POST",
                "direct_answer", retry_reason="Try again", started_at=T2,
            )

    def test_authorized_runs_preserve_every_prior_outcome(self):
        log, request, run = self.start_one_time()
        self.finish_one_time(log, request, run)
        _, second = request_log.start_run(
            log,
            self.request_path,
            VIDEO_ID,
            ENDPOINT,
            MODEL,
            "POST",
            "direct_answer",
            retry_reason="User explicitly requested another answer",
            started_at="2026-08-01T10:10:00Z",
        )
        self.assertEqual(second["runNumber"], 2)
        self.assertEqual(log["requests"][0]["runs"][0]["responseNotSavedByPolicy"], True)
        self.assertEqual(log["requests"][0]["runs"][1]["runStatus"], "pending")

    def test_attempt_prefix_must_match_exactly(self):
        log, request, run = self.start_one_time()
        retained = attempt(
            classification="transient",
            http_status=503,
            finished=T1,
            backoffSeconds=1.0,
        )
        run["routingAttempts"] = [retained]
        log["updatedAt"] = T1
        second = attempt(
            number=2,
            started=T1,
            finished=T2,
            classification="success",
            http_status=200,
            bucket="fallback",
        )
        response = self.directory / "response.json"
        common.write_json(response, {"answer": "ok"})
        result = router_result(
            request,
            run,
            response_hash=common.sha256_hex(response.read_bytes()),
            attempts=[retained, second],
        )
        request_log.finish_run(
            log,
            request["requestId"],
            1,
            router_result=result,
            response_path=response,
            updated_at="2026-08-01T10:00:03Z",
        )
        self.assertEqual(log["requests"][0]["runs"][0]["routingAttempts"], [retained, second])

        other_log, other_request, other_run = self.start_one_time()
        conflicting = copy.deepcopy(retained)
        conflicting["bucket"] = "fallback"
        other_run["routingAttempts"] = [conflicting]
        other_log["updatedAt"] = T1
        result["requestId"] = other_request["requestId"]
        result["exactRequestSha256"] = other_run["exactRequestSha256"]
        with self.assertRaisesRegex(request_log.RequestLogError, "exact prefix"):
            request_log.finish_run(
                other_log,
                other_request["requestId"],
                1,
                router_result=result,
                response_path=response,
            )

    def test_interrupted_run_requires_confirmation_and_records_no_invented_attempt(self):
        log, request, run = self.start_one_time()
        with self.assertRaisesRegex(request_log.RequestLogError, "confirmation"):
            request_log.mark_run_interrupted(
                log, request["requestId"], 1, "No longer active", False, at=T1
            )
        request_log.mark_run_interrupted(
            log, request["requestId"], 1, "User confirmed prior session stopped", True, at=T1
        )
        finished = log["requests"][0]["runs"][0]
        self.assertEqual(finished["runStatus"], "interrupted")
        self.assertEqual(finished["routingAttempts"], [])
        self.assertNotIn("responseNotSavedByPolicy", finished)

    def test_request_file_verification_rejects_every_changed_binding(self):
        log, request, run = self.start_one_time()
        request_log.verify_pending_run(
            log, self.request_path, ENDPOINT, MODEL, "POST", request["requestId"], 1
        )
        cases = [
            ("endpoint", ENDPOINT + "?changed", MODEL, "POST"),
            ("model", ENDPOINT, "gemini-other", "POST"),
            ("method", ENDPOINT, MODEL, "PUT"),
        ]
        for label, endpoint, model, method in cases:
            with self.subTest(label=label):
                with self.assertRaises(request_log.RequestLogError):
                    request_log.verify_pending_run(
                        log,
                        self.request_path,
                        endpoint,
                        model,
                        method,
                        request["requestId"],
                        run["runNumber"],
                    )
        changed = write_request(
            self.directory / "changed.json", request_value(prompt="Changed prompt")
        )
        with self.assertRaises(request_log.RequestLogError):
            request_log.verify_pending_run(
                log, changed, ENDPOINT, MODEL, "POST", request["requestId"], 1
            )

    def test_router_attempt_semantics_reject_reversal_and_false_success(self):
        log, request, run = self.start_one_time()
        reversed_time = router_result(
            request,
            run,
            attempts=[attempt(started=T2, finished=T1)],
        )
        with self.assertRaisesRegex(request_log.RequestLogError, "before it starts"):
            request_log.validate_router_result(reversed_time)
        false_success = router_result(
            request,
            run,
            attempts=[attempt(classification="success", http_status=500)],
        )
        with self.assertRaisesRegex(request_log.RequestLogError, "2xx"):
            request_log.validate_router_result(false_success)

    def test_terminal_attempt_cannot_be_followed_by_another_attempt(self):
        log, request, run = self.start_one_time()
        terminal = attempt(
            classification="request_failure",
            http_status=400,
            finished=T1,
        )
        later = attempt(
            number=2,
            classification="transient",
            http_status=503,
            started=T1,
            finished=T2,
            cooldownUntil="2026-08-01T10:05:00Z",
        )
        result = router_result(
            request, run, attempts=[terminal, later], status="failed"
        )
        with self.assertRaisesRegex(request_log.RequestLogError, "must be final"):
            request_log.validate_router_result(result)

    def test_run_and_log_times_must_follow_recorded_history(self):
        log, request, run = self.start_one_time()
        self.finish_one_time(log, request, run)
        before_prior_end = "2026-08-01T10:00:00Z"
        with self.assertRaisesRegex(request_log.RequestLogError, "prior run"):
            request_log.start_run(
                log,
                self.request_path,
                VIDEO_ID,
                ENDPOINT,
                MODEL,
                "POST",
                "direct_answer",
                retry_reason="User requested another run",
                authorized_at=before_prior_end,
                started_at="2026-08-01T10:10:00Z",
            )
        self.assertEqual(len(log["requests"][0]["runs"]), 1)

        log["updatedAt"] = T0
        with self.assertRaisesRegex(request_log.RequestLogError, "updatedAt"):
            request_log.validate_request_log(log)

    def test_untrusted_or_malformed_endpoint_is_rejected(self):
        for endpoint in (
            "https://example.com/v1beta/models/gemini-3.6-flash:generateContent",
            "https://generativelanguage.googleapis.com:bad/v1beta/models/gemini-3.6-flash:generateContent",
            ENDPOINT + "?redirect=true",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaisesRegex(
                    request_log.RequestLogError, "Unsupported Gemini"
                ):
                    request_log.start_run(
                        self.new_log(),
                        self.request_path,
                        VIDEO_ID,
                        endpoint,
                        MODEL,
                        "POST",
                        "direct_answer",
                        started_at=T0,
                    )

    def test_serialized_log_contains_no_credentials_or_request_body_copy(self):
        log, _, _ = self.start_one_time()
        serialized = json.dumps(log)
        self.assertNotIn("GEMINI_API_KEY", serialized)
        self.assertNotIn("x-goog-api-key", serialized)
        self.assertNotIn("generationConfig", serialized)
        self.assertNotIn("requestStatus", serialized)
        self.assertNotIn("writer", serialized)
        self.assertNotIn("lease", serialized)


if __name__ == "__main__":
    unittest.main()
