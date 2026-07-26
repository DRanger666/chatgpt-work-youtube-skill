import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "artifact_cache_v3.py"
SPEC = importlib.util.spec_from_file_location("artifact_cache_v3", MODULE_PATH)
artifact_cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(artifact_cache)

VIDEO_ID = "uSibwB2TQC4"
NOW = "2026-07-27T12:00:00Z"
LATER = "2026-07-27T12:01:00Z"


def interval(start, end):
    return {"startMs": start, "endMs": end}


def provenance(name="exec-1", fingerprint=None):
    return [
        {
            "executionId": name,
            "fingerprint": fingerprint or ("a" * 64),
            "route": "gemini-generate-content",
            "model": "gemini-test",
            "startedAt": NOW,
            "finishedAt": LATER,
        }
    ]


def metadata(**overrides):
    value = {
        "video": f"https://youtu.be/{VIDEO_ID}?si=test",
        "kind": "transcript",
        "contract": {"name": "gemini-transcript", "version": 1},
        "timestampBasis": "full_video",
        "languagePolicy": {"mode": "source"},
        "requestedCoverage": [interval(0, 600_000)],
        "validCoverage": [interval(0, 600_000)],
        "completionState": "complete",
    }
    value.update(overrides)
    return value


class ArtifactCacheV3StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"

    def tearDown(self):
        self.temporary.cleanup()

    def create_artifact(self, **metadata_overrides):
        artifact = artifact_cache.build_artifact(
            metadata(**metadata_overrides),
            {"segments": [{"startMs": 0, "endMs": 1_000, "text": "test"}]},
            provenance(),
        )
        path = artifact_cache.write_immutable_artifact(self.artifacts, artifact)
        return artifact, path

    def test_locates_manifest_in_separate_no_space_namespace(self):
        variants = [
            VIDEO_ID,
            f"https://youtu.be/{VIDEO_ID}?si=value",
            f"https://www.youtube.com/watch?v={VIDEO_ID}&feature=shared",
            f"https://youtube.com/shorts/{VIDEO_ID}",
            f"https://youtube-nocookie.com/embed/{VIDEO_ID}",
        ]
        for source in variants:
            with self.subTest(source=source):
                self.assertEqual(
                    artifact_cache.normalize_youtube_video_id(source),
                    VIDEO_ID,
                )
        self.assertEqual(
            artifact_cache.manifest_filename(VIDEO_ID),
            f"{VIDEO_ID}--manifest.json",
        )
        self.assertEqual(
            artifact_cache.DRIVE_NAMESPACE,
            "YouTubeArtifactCacheV3",
        )
        self.assertNotIn(" ", artifact_cache.DRIVE_NAMESPACE)

    def test_clean_slate_native_records_start_at_schema_one(self):
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        artifact, _ = self.create_artifact()

        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(artifact["schemaVersion"], 1)
        self.assertEqual(
            manifest["cacheSystem"],
            "youtube-artifact-cache-v3",
        )
        serialized = json.dumps({"manifest": manifest, "artifact": artifact})
        for legacy_field in (
            "requestFingerprint",
            "retrySameRequest",
            "selectedBucket",
            "schemaVersion\": 2",
        ):
            self.assertNotIn(legacy_field, serialized)

    def test_stores_immutable_artifact_and_indexes_integrity(self):
        artifact, artifact_path = self.create_artifact()
        original_bytes = artifact_path.read_bytes()
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)

        updated = artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at=LATER,
        )

        self.assertEqual(artifact_path.read_bytes(), original_bytes)
        self.assertEqual(len(updated["artifacts"]), 1)
        entry = updated["artifacts"][0]
        self.assertEqual(entry["artifactId"], artifact["artifactId"])
        self.assertEqual(
            entry["integrity"]["value"],
            artifact_cache.sha256_hex(original_bytes),
        )
        self.assertEqual(entry["driveFileId"], "drive-file-1")
        self.assertEqual(updated["executions"][0]["executionId"], "exec-1")
        self.assertEqual(
            updated["executions"][0]["artifactIds"],
            [artifact["artifactId"]],
        )

    def test_readding_identical_artifact_is_idempotent(self):
        artifact, artifact_path = self.create_artifact()
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at=LATER,
        )
        snapshot = json.loads(json.dumps(manifest))

        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at="2026-07-27T12:02:00Z",
        )

        self.assertEqual(manifest, snapshot)

    def test_readding_repairs_a_missing_execution_reference(self):
        artifact, artifact_path = self.create_artifact()
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at=LATER,
        )
        manifest["executions"] = []

        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at="2026-07-27T12:02:00Z",
        )

        self.assertEqual(
            [item["executionId"] for item in manifest["executions"]],
            ["exec-1"],
        )

    def test_rebuilds_missing_manifest_from_native_artifacts(self):
        first, first_path = self.create_artifact()
        second = artifact_cache.build_artifact(
            metadata(
                requestedCoverage=[interval(600_000, 1_200_000)],
                validCoverage=[interval(600_000, 1_200_000)],
            ),
            {"segments": [{"startMs": 600_000, "text": "next"}]},
            provenance(name="exec-2", fingerprint="b" * 64),
        )
        second_path = artifact_cache.write_immutable_artifact(
            self.artifacts,
            second,
        )

        rebuilt = artifact_cache.rebuild_manifest(
            VIDEO_ID,
            [second_path, first_path],
            {
                first_path.name: "drive-file-1",
                second_path.name: "drive-file-2",
            },
            updated_at=LATER,
        )

        self.assertEqual(rebuilt["schemaVersion"], 1)
        self.assertEqual(len(rebuilt["artifacts"]), 2)
        self.assertEqual(
            {item["artifactId"] for item in rebuilt["artifacts"]},
            {first["artifactId"], second["artifactId"]},
        )
        self.assertEqual(
            {item["executionId"] for item in rebuilt["executions"]},
            {"exec-1", "exec-2"},
        )

    def test_rejects_legacy_fields_in_native_manifest(self):
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        manifest["requestFingerprint"] = "a" * 64

        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "unsupported fields",
        ):
            artifact_cache.validate_manifest(manifest)

    def test_truncated_artifact_stores_only_confirmed_coverage(self):
        artifact, _ = self.create_artifact(
            validCoverage=[interval(0, 420_000)],
            completionState="truncated",
        )

        self.assertEqual(artifact["validCoverage"], [interval(0, 420_000)])
        self.assertEqual(artifact["gaps"], [interval(420_000, 600_000)])
        self.assertEqual(artifact["completionState"], "truncated")

    def test_complete_artifact_cannot_claim_a_gap(self):
        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "Complete artifacts cannot contain coverage gaps",
        ):
            artifact_cache.build_artifact(
                metadata(validCoverage=[interval(0, 420_000)]),
                {"segments": []},
                provenance(),
            )


class ArtifactCacheV3SearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        self.counter = 0

    def tearDown(self):
        self.temporary.cleanup()

    def add_artifact(
        self,
        start,
        end,
        *,
        requested=None,
        completion_state="complete",
        contract=None,
        language_policy=None,
        task_description=None,
        kind="transcript",
    ):
        self.counter += 1
        artifact_metadata = metadata(
            requestedCoverage=requested or [interval(start, end)],
            validCoverage=[interval(start, end)],
            completionState=completion_state,
            contract=contract
            or {"name": "gemini-transcript", "version": 1},
            languagePolicy=language_policy or {"mode": "source"},
            kind=kind,
        )
        if task_description:
            artifact_metadata["taskDescription"] = task_description
        artifact = artifact_cache.build_artifact(
            artifact_metadata,
            {"segments": [{"startMs": start, "endMs": end, "text": "test"}]},
            provenance(
                name=f"exec-{self.counter}",
                fingerprint=f"{self.counter:x}".rjust(64, "0"),
            ),
        )
        path = artifact_cache.write_immutable_artifact(self.artifacts, artifact)
        artifact_cache.add_artifact_to_manifest(
            self.manifest,
            artifact,
            f"drive-file-{self.counter}",
            path,
            updated_at=LATER,
        )
        return artifact, path

    def query(self, start=0, end=600_000, **overrides):
        value = {
            "video": f"https://youtube.com/watch?v={VIDEO_ID}",
            "kind": "transcript",
            "contract": {"name": "gemini-transcript", "version": 1},
            "timestampBasis": "full_video",
            "languagePolicy": {"mode": "source"},
            "requestedCoverage": [interval(start, end)],
        }
        value.update(overrides)
        return value

    def search(self, query=None):
        return artifact_cache.search_artifacts(
            self.manifest,
            self.artifacts,
            query or self.query(),
        )

    def test_exact_coverage_reuses_one_artifact(self):
        artifact, _ = self.add_artifact(0, 600_000)

        plan = self.search()

        self.assertEqual(plan["coverageStatus"], "complete")
        self.assertEqual(plan["coverageCases"], ["exact"])
        self.assertEqual(plan["newRequestIntervals"], [])
        self.assertEqual(
            plan["selectedArtifacts"][0]["artifactId"],
            artifact["artifactId"],
        )

    def test_empty_clean_slate_manifest_requests_the_whole_interval(self):
        plan = self.search()

        self.assertEqual(plan["coverageStatus"], "missing")
        self.assertEqual(plan["coverageCases"], ["missing"])
        self.assertEqual(
            plan["newRequestIntervals"],
            [interval(0, 600_000)],
        )

    def test_containing_artifact_satisfies_smaller_interval(self):
        self.add_artifact(0, 600_000)

        plan = self.search(self.query(120_000, 240_000))

        self.assertEqual(plan["coverageCases"], ["containing"])
        self.assertEqual(plan["coveredIntervals"], [interval(120_000, 240_000)])
        self.assertEqual(plan["newRequestIntervals"], [])

    def test_adjacent_artifacts_compose_complete_coverage(self):
        self.add_artifact(0, 300_000)
        self.add_artifact(300_000, 600_000)

        plan = self.search()

        self.assertEqual(plan["coverageStatus"], "complete")
        self.assertEqual(plan["coverageCases"], ["composite"])
        self.assertEqual(len(plan["selectedArtifacts"]), 2)
        self.assertEqual(plan["newRequestIntervals"], [])

    def test_overlapping_artifacts_compose_without_a_gap(self):
        self.add_artifact(0, 360_000)
        self.add_artifact(300_000, 600_000)

        plan = self.search()

        self.assertEqual(
            plan["coverageCases"],
            ["composite", "overlapping"],
        )
        self.assertEqual(plan["coveredIntervals"], [interval(0, 600_000)])
        self.assertEqual(plan["uncoveredIntervals"], [])

    def test_only_the_uncovered_gap_needs_a_new_request(self):
        self.add_artifact(0, 180_000)
        self.add_artifact(420_000, 600_000)

        plan = self.search()

        self.assertEqual(plan["coverageStatus"], "partial")
        self.assertIn("missing", plan["coverageCases"])
        self.assertEqual(
            plan["newRequestIntervals"],
            [interval(180_000, 420_000)],
        )

    def test_truncated_artifact_contributes_only_confirmed_coverage(self):
        self.add_artifact(
            0,
            420_000,
            requested=[interval(0, 600_000)],
            completion_state="truncated",
        )

        plan = self.search()

        self.assertEqual(
            plan["coverageCases"],
            ["truncated", "missing"],
        )
        self.assertEqual(plan["coveredIntervals"], [interval(0, 420_000)])
        self.assertEqual(
            plan["newRequestIntervals"],
            [interval(420_000, 600_000)],
        )

    def test_incompatible_contract_and_language_are_not_reused(self):
        self.add_artifact(
            0,
            600_000,
            contract={"name": "gemini-transcript", "version": 2},
            language_policy={"mode": "translated", "target": "en"},
        )

        plan = self.search()

        self.assertEqual(
            plan["coverageCases"],
            ["incompatible", "missing"],
        )
        self.assertEqual(plan["selectedArtifacts"], [])
        self.assertEqual(
            plan["incompatibleArtifacts"][0]["reasons"],
            ["contract", "language_policy"],
        )

    def test_missing_artifact_file_is_reported_as_stale_manifest_state(self):
        artifact, path = self.add_artifact(0, 600_000)
        path.unlink()

        plan = self.search()

        self.assertEqual(plan["coverageStatus"], "missing")
        self.assertEqual(plan["coverageCases"], ["missing"])
        self.assertEqual(
            plan["staleManifestEntries"],
            [
                {
                    "artifactId": artifact["artifactId"],
                    "driveFileId": "drive-file-1",
                    "fileName": path.name,
                    "reason": "missing_artifact_file",
                }
            ],
        )

    def test_integrity_failure_is_not_reused(self):
        artifact, path = self.add_artifact(0, 600_000)
        path.write_text('{"corrupted":true}\n', encoding="utf-8")

        plan = self.search()

        self.assertEqual(plan["selectedArtifacts"], [])
        self.assertEqual(
            plan["staleManifestEntries"][0],
            {
                "artifactId": artifact["artifactId"],
                "driveFileId": "drive-file-1",
                "fileName": path.name,
                "reason": "integrity_mismatch",
            },
        )

    def test_incompatible_timestamp_basis_is_not_reused(self):
        self.add_artifact(0, 600_000)

        plan = self.search(self.query(timestampBasis="clip_relative"))

        self.assertEqual(
            plan["coverageCases"],
            ["incompatible", "missing"],
        )
        self.assertEqual(
            plan["incompatibleArtifacts"][0]["reasons"],
            ["timestamp_basis"],
        )

    def test_analysis_artifact_requires_explicit_agent_approval(self):
        artifact, _ = self.add_artifact(
            0,
            600_000,
            task_description="Identify visual evidence of laboratory methods.",
            kind="question_analysis",
        )

        analysis_query = self.query(kind="question_analysis")
        first_plan = self.search(analysis_query)
        approved_plan = self.search(
            self.query(
                kind="question_analysis",
                agentApprovedArtifactIds=[artifact["artifactId"]],
            )
        )

        self.assertTrue(first_plan["requiresAgentReview"])
        self.assertEqual(first_plan["selectedArtifacts"], [])
        self.assertEqual(
            first_plan["reviewCandidates"][0]["taskDescription"],
            "Identify visual evidence of laboratory methods.",
        )
        self.assertFalse(approved_plan["requiresAgentReview"])
        self.assertEqual(approved_plan["coverageCases"], ["exact"])

    def test_analysis_artifact_requires_a_task_description(self):
        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "require a task description",
        ):
            artifact_cache.build_artifact(
                metadata(kind="question_analysis"),
                {"observations": []},
                provenance(),
            )


class ArtifactCacheV3ExecutionGuardTests(unittest.TestCase):
    def setUp(self):
        self.manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)

    def execution_spec(self, request=None):
        return {
            "video": f"https://youtu.be/{VIDEO_ID}",
            "route": "gemini-generate-content",
            "model": "gemini-test",
            "requestedCoverage": [interval(0, 600_000)],
            "request": request
            or {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "fileData": {
                                    "fileUri": f"https://youtu.be/{VIDEO_ID}",
                                    "mimeType": "video/*",
                                }
                            },
                            {"text": "test"},
                        ],
                    }
                ],
                "generationConfig": {"maxOutputTokens": 8192},
            },
        }

    def test_execution_fingerprint_is_canonical_not_raw_serialization(self):
        first = self.execution_spec()
        second = {
            "request": {
                "generationConfig": {"maxOutputTokens": 8192},
                "contents": [
                    {
                        "parts": [
                            {
                                "fileData": {
                                    "mimeType": "video/*",
                                    "fileUri": (
                                        "https://www.youtube.com/watch"
                                        f"?v={VIDEO_ID}&feature=shared"
                                    ),
                                }
                            },
                            {"text": "test"},
                        ],
                        "role": "user",
                    }
                ],
            },
            "requestedCoverage": [interval(0, 600_000)],
            "model": "gemini-test",
            "route": "gemini-generate-content",
            "video": f"https://www.youtube.com/watch?v={VIDEO_ID}",
        }

        self.assertEqual(
            artifact_cache.execution_fingerprint(first),
            artifact_cache.execution_fingerprint(second),
        )

    def test_pending_execution_blocks_identical_submission(self):
        first = artifact_cache.start_execution(
            self.manifest,
            self.execution_spec(),
            started_at=NOW,
        )

        with self.assertRaises(artifact_cache.DuplicateExecutionError) as caught:
            artifact_cache.start_execution(
                self.manifest,
                self.execution_spec(),
                started_at=LATER,
            )

        self.assertEqual(caught.exception.execution["executionId"], first["executionId"])
        self.assertEqual(caught.exception.execution["status"], "pending")

    def test_completed_execution_blocks_identical_submission(self):
        execution = artifact_cache.start_execution(
            self.manifest,
            self.execution_spec(),
            started_at=NOW,
        )
        artifact_cache.finish_execution(
            self.manifest,
            execution["executionId"],
            "completed",
            artifact_ids=["a" * 64],
            finished_at=LATER,
        )

        with self.assertRaises(artifact_cache.DuplicateExecutionError):
            artifact_cache.start_execution(
                self.manifest,
                self.execution_spec(),
            )

    def test_failed_execution_allows_a_new_guarded_attempt(self):
        first = artifact_cache.start_execution(
            self.manifest,
            self.execution_spec(),
            started_at=NOW,
        )
        artifact_cache.finish_execution(
            self.manifest,
            first["executionId"],
            "failed",
            finished_at=LATER,
        )

        second = artifact_cache.start_execution(
            self.manifest,
            self.execution_spec(),
            started_at="2026-07-27T12:02:00Z",
        )

        self.assertNotEqual(first["executionId"], second["executionId"])
        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertTrue(second["executionId"].endswith("-2"))

    def test_pending_execution_yields_safe_artifact_provenance(self):
        execution = artifact_cache.start_execution(
            self.manifest,
            self.execution_spec(),
            started_at=NOW,
        )

        result = artifact_cache.provenance_for_execution(
            self.manifest,
            execution["executionId"],
            finished_at=LATER,
        )

        self.assertEqual(
            result,
            [
                {
                    "executionId": execution["executionId"],
                    "fingerprint": execution["fingerprint"],
                    "route": "gemini-generate-content",
                    "model": "gemini-test",
                    "startedAt": NOW,
                    "finishedAt": LATER,
                }
            ],
        )
        serialized = json.dumps(result)
        self.assertNotIn("request", serialized)
        self.assertNotIn("credential", serialized)


class ArtifactCacheV3ChunkPlanningTests(unittest.TestCase):
    def test_chunks_only_uncovered_intervals(self):
        chunks = artifact_cache.plan_chunks(
            [interval(180_000, 1_380_000)],
            chunk_seconds=600,
            overlap_seconds=4,
        )

        self.assertEqual(
            chunks,
            [
                interval(180_000, 780_000),
                interval(776_000, 1_376_000),
                interval(1_372_000, 1_380_000),
            ],
        )

    def test_rejects_overlap_equal_to_chunk_size(self):
        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "overlap < chunk size",
        ):
            artifact_cache.plan_chunks(
                [interval(0, 600_000)],
                chunk_seconds=600,
                overlap_seconds=600,
            )


class ArtifactCacheV3CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_empty_manifest_search_and_chunk_plan(self):
        manifest = self.root / "manifest.json"
        query_path = self.root / "query.json"
        search_plan = self.root / "search-plan.json"
        chunk_plan = self.root / "chunk-plan.json"
        query_path.write_text(
            json.dumps(
                {
                    "video": VIDEO_ID,
                    "kind": "transcript",
                    "contract": {"name": "gemini-transcript", "version": 1},
                    "timestampBasis": "full_video",
                    "languagePolicy": {"mode": "source"},
                    "requestedCoverage": [interval(0, 600_000)],
                }
            ),
            encoding="utf-8",
        )

        initialized = self.run_cli(
            "init-manifest",
            "--video",
            VIDEO_ID,
            "--output",
            str(manifest),
            "--updated-at",
            NOW,
        )
        searched = self.run_cli(
            "search",
            "--manifest",
            str(manifest),
            "--artifacts-dir",
            str(self.artifacts),
            "--query",
            str(query_path),
            "--output",
            str(search_plan),
        )
        chunked = self.run_cli(
            "plan-chunks",
            "--search-plan",
            str(search_plan),
            "--chunk-seconds",
            "300",
            "--output",
            str(chunk_plan),
        )

        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        self.assertEqual(searched.returncode, 0, searched.stderr)
        self.assertEqual(chunked.returncode, 0, chunked.stderr)
        self.assertEqual(
            json.loads(search_plan.read_text(encoding="utf-8"))[
                "newRequestIntervals"
            ],
            [interval(0, 600_000)],
        )
        self.assertEqual(
            json.loads(chunk_plan.read_text(encoding="utf-8"))["chunks"],
            [interval(0, 300_000), interval(300_000, 600_000)],
        )

    def test_cli_reports_duplicate_pending_execution(self):
        manifest = self.root / "manifest.json"
        pending = self.root / "pending.json"
        duplicate_output = self.root / "duplicate.json"
        spec_path = self.root / "execution-spec.json"
        artifact_cache.write_json(
            manifest,
            artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW),
        )
        spec_path.write_text(
            json.dumps(
                {
                    "video": VIDEO_ID,
                    "route": "gemini-generate-content",
                    "model": "gemini-test",
                    "requestedCoverage": [interval(0, 600_000)],
                    "request": {"contents": []},
                }
            ),
            encoding="utf-8",
        )

        started = self.run_cli(
            "start-execution",
            "--manifest",
            str(manifest),
            "--execution-spec",
            str(spec_path),
            "--output",
            str(pending),
            "--started-at",
            NOW,
        )
        duplicate = self.run_cli(
            "start-execution",
            "--manifest",
            str(pending),
            "--execution-spec",
            str(spec_path),
            "--output",
            str(duplicate_output),
            "--started-at",
            LATER,
        )

        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(duplicate.returncode, 3, duplicate.stderr)
        self.assertEqual(
            json.loads(duplicate.stdout)["executionStatus"],
            "pending",
        )
        self.assertFalse(duplicate_output.exists())


if __name__ == "__main__":
    unittest.main()
