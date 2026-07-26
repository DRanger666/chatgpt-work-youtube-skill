import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPOSITORY_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

ARTIFACT_PATH = SCRIPTS / "artifact_cache_v3.py"
ARTIFACT_SPEC = importlib.util.spec_from_file_location(
    "artifact_cache_v3",
    ARTIFACT_PATH,
)
artifact_cache = importlib.util.module_from_spec(ARTIFACT_SPEC)
sys.modules["artifact_cache_v3"] = artifact_cache
ARTIFACT_SPEC.loader.exec_module(artifact_cache)

JOURNAL_PATH = SCRIPTS / "gemini_execution_journal_v3.py"
JOURNAL_SPEC = importlib.util.spec_from_file_location(
    "gemini_execution_journal_v3",
    JOURNAL_PATH,
)
journal = importlib.util.module_from_spec(JOURNAL_SPEC)
JOURNAL_SPEC.loader.exec_module(journal)

VIDEO_ID = "uSibwB2TQC4"
SECOND_VIDEO_ID = "lhSq1RzDcZg"
OWNER_A = "work-session-a"
OWNER_B = "work-session-b"
NOW = "2026-07-27T12:00:00Z"
SOON = "2026-07-27T12:10:00Z"
LATER = "2026-07-27T13:01:00Z"
LATEST = "2026-07-27T14:00:00Z"


def interval(start=0, end=600_000):
    return {"startMs": start, "endMs": end}


def execution_spec(video=VIDEO_ID, prompt="test"):
    return {
        "video": f"https://youtu.be/{video}",
        "route": "gemini-generate-content",
        "model": "gemini-test",
        "requestedCoverage": [interval()],
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": f"https://youtu.be/{video}?si=test",
                                "mimeType": "video/*",
                            }
                        },
                        {"text": prompt},
                    ],
                }
            ],
            "generationConfig": {"maxOutputTokens": 8192},
        },
    }


def routing_success():
    return {
        "schemaVersion": 1,
        "status": "succeeded",
        "selectedBucket": "fallback",
        "attempts": [
            {
                "bucket": "primary",
                "startedAt": "2026-07-27T12:00:01Z",
                "finishedAt": "2026-07-27T12:00:02Z",
                "httpStatus": 429,
                "classification": "rate_limited",
                "errorStatus": "RESOURCE_EXHAUSTED",
                "retryDelaySeconds": 30.0,
                "cooldownUntil": "2026-07-27T12:00:32Z",
            },
            {
                "bucket": "fallback",
                "startedAt": "2026-07-27T12:00:03Z",
                "finishedAt": "2026-07-27T12:00:04Z",
                "httpStatus": 200,
                "classification": "success",
            },
        ],
    }


def routing_failure(classification="transient", error_status="UNAVAILABLE"):
    return {
        "schemaVersion": 1,
        "status": "failed",
        "selectedBucket": None,
        "attempts": [
            {
                "bucket": "primary",
                "startedAt": "2026-07-27T12:00:01Z",
                "finishedAt": "2026-07-27T12:00:02Z",
                "httpStatus": 503 if classification == "transient" else 400,
                "classification": classification,
                "errorStatus": error_status,
                **(
                    {
                        "cooldownUntil": "2026-07-27T12:05:00Z",
                        "backoffSeconds": 1.0,
                    }
                    if classification == "transient"
                    else {}
                ),
            }
        ],
        "earliestCooldownUntil": (
            "2026-07-27T12:05:00Z"
            if classification == "transient"
            else None
        ),
    }


class WriterPolicyTests(unittest.TestCase):
    def setUp(self):
        self.state = journal.new_journal(VIDEO_ID, updated_at=NOW)

    def acquire_a(self):
        return journal.acquire_writer(
            self.state,
            OWNER_A,
            lease_seconds=3600,
            at=NOW,
        )

    def test_journal_uses_predictable_native_schema_one_identity(self):
        self.assertEqual(
            journal.journal_filename(f"https://youtu.be/{VIDEO_ID}?si=x"),
            f"{VIDEO_ID}--gemini-executions.json",
        )
        self.assertEqual(self.state["schemaVersion"], 1)
        self.assertEqual(
            set(self.state),
            {
                "schemaVersion",
                "cacheSystem",
                "recordType",
                "videoId",
                "writer",
                "writerHistory",
                "executions",
                "updatedAt",
            },
        )

    def test_same_video_writer_blocks_another_session(self):
        self.acquire_a()
        snapshot = json.loads(json.dumps(self.state))

        with self.assertRaises(journal.WriterOwnedError):
            journal.acquire_writer(
                self.state,
                OWNER_B,
                lease_seconds=3600,
                at=SOON,
            )

        self.assertEqual(self.state, snapshot)

    def test_read_only_inspection_does_not_mutate_writer_state(self):
        self.acquire_a()
        snapshot = artifact_cache.stored_json_bytes(self.state)

        journal.validate_journal(self.state)
        json.dumps(self.state)

        self.assertEqual(artifact_cache.stored_json_bytes(self.state), snapshot)

    def test_different_video_ids_have_independent_writers(self):
        other = journal.new_journal(SECOND_VIDEO_ID, updated_at=NOW)

        journal.acquire_writer(self.state, OWNER_A, at=NOW)
        journal.acquire_writer(other, OWNER_B, at=NOW)

        self.assertEqual(self.state["writer"]["ownerId"], OWNER_A)
        self.assertEqual(other["writer"]["ownerId"], OWNER_B)

    def test_expiry_requires_reconciliation_not_automatic_takeover(self):
        self.acquire_a()

        with self.assertRaises(journal.WriterReconciliationRequired):
            journal.acquire_writer(
                self.state,
                OWNER_B,
                at=LATER,
            )

        self.assertEqual(self.state["writer"]["ownerId"], OWNER_A)

    def test_original_session_can_renew_after_rereading_expired_state(self):
        self.acquire_a()

        renewed = journal.renew_writer(
            self.state,
            OWNER_A,
            lease_seconds=1800,
            at=LATER,
        )

        self.assertEqual(renewed["leaseExpiresAt"], "2026-07-27T13:31:00Z")
        self.assertEqual(self.state["writerHistory"][-1]["type"], "renewed")

    def test_clean_handoff_is_recorded_before_incoming_acquisition(self):
        self.acquire_a()

        journal.release_writer(
            self.state,
            OWNER_A,
            "Work completed and state persisted.",
            handoff_to=OWNER_B,
            at=SOON,
        )
        journal.acquire_writer(self.state, OWNER_B, at=LATER)

        handoff = self.state["writerHistory"][-2]
        self.assertEqual(handoff["type"], "handoff")
        self.assertEqual(handoff["toOwnerId"], OWNER_B)
        self.assertEqual(self.state["writer"]["ownerId"], OWNER_B)

    def test_writer_cannot_release_with_pending_execution(self):
        self.acquire_a()
        journal.start_execution(
            self.state,
            execution_spec(),
            OWNER_A,
            started_at=SOON,
        )

        with self.assertRaises(journal.PendingExecutionError):
            journal.release_writer(
                self.state,
                OWNER_A,
                "Unsafe release",
                at=SOON,
            )

    def test_expired_pending_work_requires_human_confirmed_reconciliation(self):
        self.acquire_a()
        first = journal.start_execution(
            self.state,
            execution_spec(),
            OWNER_A,
            started_at=SOON,
        )

        with self.assertRaises(journal.WriterReconciliationRequired):
            journal.reconcile_expired_writer(
                self.state,
                OWNER_B,
                "abandoned",
                "Original VM disappeared.",
                "The user has not confirmed termination.",
                False,
                at=LATER,
            )

        journal.reconcile_expired_writer(
            self.state,
            OWNER_B,
            "abandoned",
            "Original VM was lost.",
            "User confirmed that the original session will no longer write.",
            True,
            at=LATER,
        )

        self.assertIsNone(self.state["writer"])
        self.assertEqual(first["status"], "abandoned")
        self.assertEqual(first["reconciliation"]["reconciledBy"], OWNER_B)
        self.assertTrue(first["reconciliation"]["humanConfirmedStopped"])
        self.assertEqual(self.state["writerHistory"][-1]["type"], "reconciled")


class ExecutionLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.state = journal.new_journal(VIDEO_ID, updated_at=NOW)
        journal.acquire_writer(
            self.state,
            OWNER_A,
            lease_seconds=10800,
            at=NOW,
        )

    def start(self, **kwargs):
        return journal.start_execution(
            self.state,
            execution_spec(),
            OWNER_A,
            started_at=SOON,
            **kwargs,
        )

    def test_execution_fingerprint_is_canonical_across_url_forms(self):
        first = execution_spec()
        second = execution_spec()
        second["video"] = f"https://www.youtube.com/watch?v={VIDEO_ID}"
        second["request"]["contents"][0]["parts"][0]["fileData"][
            "fileUri"
        ] = f"https://youtube.com/embed/{VIDEO_ID}"

        self.assertEqual(
            journal.execution_fingerprint(first),
            journal.execution_fingerprint(second),
        )

    def test_any_pending_execution_blocks_another_video_request(self):
        first = self.start()

        with self.assertRaises(journal.PendingExecutionError):
            journal.start_execution(
                self.state,
                execution_spec(prompt="different request"),
                OWNER_A,
                started_at=SOON,
            )

        self.assertEqual(first["status"], "pending")

    def test_completed_identical_execution_is_not_repeated(self):
        first = self.start()
        journal.finish_execution(
            self.state,
            first["executionId"],
            OWNER_A,
            "completed",
            routing_success(),
            artifact_ids=["a" * 64],
            finished_at=LATER,
        )

        with self.assertRaises(journal.DuplicateExecutionError):
            journal.start_execution(
                self.state,
                execution_spec(),
                OWNER_A,
                started_at=LATEST,
            )

    def test_failed_identical_execution_requires_and_preserves_reason(self):
        first = self.start()
        journal.finish_execution(
            self.state,
            first["executionId"],
            OWNER_A,
            "failed",
            routing_failure(),
            finished_at=LATER,
        )

        with self.assertRaises(journal.RetryAuthorizationRequired):
            journal.start_execution(
                self.state,
                execution_spec(),
                OWNER_A,
                started_at=LATEST,
            )

        second = journal.start_execution(
            self.state,
            execution_spec(),
            OWNER_A,
            retry_reason="Transient service failure after recorded cooldown.",
            started_at=LATEST,
        )

        self.assertEqual(second["attemptNumber"], 2)
        self.assertEqual(
            second["retryAuthorization"]["reason"],
            "Transient service failure after recorded cooldown.",
        )
        self.assertEqual(first["routerAttempts"][0]["classification"], "transient")

    def test_terminal_request_failure_cannot_be_retried_unchanged(self):
        first = self.start()
        journal.finish_execution(
            self.state,
            first["executionId"],
            OWNER_A,
            "failed",
            routing_failure(
                classification="request_failure",
                error_status="INVALID_ARGUMENT",
            ),
            finished_at=LATER,
        )

        with self.assertRaises(journal.TerminalExecutionError):
            journal.start_execution(
                self.state,
                execution_spec(),
                OWNER_A,
                retry_reason="Try the same invalid request again.",
                started_at=LATEST,
            )

    def test_router_attempts_and_fallback_selection_are_durable(self):
        execution = self.start()

        finished = journal.finish_execution(
            self.state,
            execution["executionId"],
            OWNER_A,
            "completed",
            routing_success(),
            artifact_ids=["b" * 64],
            finished_at=LATER,
            result_metadata={
                "modelVersion": "gemini-test-001",
                "usageMetadata": {"totalTokenCount": 42},
            },
        )

        self.assertEqual(
            [item["classification"] for item in finished["routerAttempts"]],
            ["rate_limited", "success"],
        )
        self.assertEqual(finished["selectedBucket"], "fallback")
        self.assertEqual(
            finished["routerAttempts"][0]["retryDelaySeconds"],
            30.0,
        )
        self.assertEqual(finished["artifactIds"], ["b" * 64])
        self.assertEqual(finished["modelVersion"], "gemini-test-001")

    def test_no_available_bucket_failure_preserves_cooldown_without_fake_attempt(self):
        execution = self.start()
        routing = {
            "schemaVersion": 1,
            "status": "failed",
            "selectedBucket": None,
            "attempts": [],
            "earliestCooldownUntil": "2026-07-27T12:30:00Z",
        }

        finished = journal.finish_execution(
            self.state,
            execution["executionId"],
            OWNER_A,
            "failed",
            routing,
            finished_at=LATER,
        )

        self.assertEqual(finished["routerAttempts"], [])
        self.assertEqual(
            finished["earliestCooldownUntil"],
            "2026-07-27T12:30:00Z",
        )

    def test_routing_metadata_rejects_unapproved_fields(self):
        execution = self.start()
        unsafe = routing_success()
        unsafe["apiKeyFingerprint"] = "secret-derived"

        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "unsupported fields",
        ):
            journal.finish_execution(
                self.state,
                execution["executionId"],
                OWNER_A,
                "completed",
                unsafe,
                finished_at=LATER,
            )

    def test_manifest_bytes_do_not_change_during_execution_lifecycle(self):
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        before = artifact_cache.stored_json_bytes(manifest)
        execution = self.start()
        journal.finish_execution(
            self.state,
            execution["executionId"],
            OWNER_A,
            "failed",
            routing_failure(),
            finished_at=LATER,
        )

        self.assertEqual(artifact_cache.stored_json_bytes(manifest), before)

    def test_execution_to_artifact_reference_is_one_way(self):
        artifact = artifact_cache.build_artifact(
            {
                "video": VIDEO_ID,
                "kind": "transcript",
                "contract": {"name": "gemini-transcript", "version": 1},
                "timestampBasis": "full_video",
                "languagePolicy": {"mode": "source"},
                "validCoverage": [interval()],
            },
            {"segments": []},
        )
        execution = self.start()
        journal.finish_execution(
            self.state,
            execution["executionId"],
            OWNER_A,
            "completed",
            routing_success(),
            artifact_ids=[artifact["artifactId"]],
            finished_at=LATER,
        )

        self.assertEqual(execution["artifactIds"], [artifact["artifactId"]])
        serialized_artifact = json.dumps(artifact)
        self.assertNotIn(execution["executionId"], serialized_artifact)
        self.assertNotIn("execution", serialized_artifact)

    def test_abandoned_execution_retry_continues_attempt_numbering(self):
        first = self.start()
        takeover_at = "2026-07-27T15:01:00Z"
        journal.reconcile_expired_writer(
            self.state,
            OWNER_B,
            "abandoned",
            "Original writer crashed.",
            "User confirmed original session termination.",
            True,
            at=takeover_at,
        )
        journal.acquire_writer(
            self.state,
            OWNER_B,
            lease_seconds=3600,
            at=takeover_at,
        )

        second = journal.start_execution(
            self.state,
            execution_spec(),
            OWNER_B,
            retry_reason="Recover abandoned work after confirmed termination.",
            started_at=takeover_at,
        )

        self.assertEqual(first["status"], "abandoned")
        self.assertEqual(second["attemptNumber"], 2)
        self.assertTrue(second["executionId"].endswith("-2"))

    def test_serialized_journal_contains_no_request_or_credentials(self):
        self.start()

        serialized = json.dumps(self.state)

        self.assertNotIn('"request"', serialized)
        self.assertNotIn("apiKey", serialized)
        self.assertNotIn("credential", serialized.lower())


class JournalCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(JOURNAL_PATH), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_requires_lookup_confirmation_then_acquires_writer(self):
        journal_path = self.root / "journal.json"
        acquired_path = self.root / "acquired.json"

        refused = self.run_cli(
            "init-journal",
            "--video",
            VIDEO_ID,
            "--output",
            str(journal_path),
        )
        initialized = self.run_cli(
            "init-journal",
            "--video",
            VIDEO_ID,
            "--output",
            str(journal_path),
            "--confirmed-no-journal",
            "--updated-at",
            NOW,
        )
        acquired = self.run_cli(
            "acquire-writer",
            "--journal",
            str(journal_path),
            "--output",
            str(acquired_path),
            "--owner-id",
            OWNER_A,
            "--at",
            NOW,
        )

        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertEqual(acquired.returncode, 0, acquired.stderr)
        state = json.loads(acquired_path.read_text(encoding="utf-8"))
        self.assertEqual(state["writer"]["ownerId"], OWNER_A)


if __name__ == "__main__":
    unittest.main()
