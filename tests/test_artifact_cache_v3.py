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


def metadata(start=0, end=600_000, **overrides):
    value = {
        "video": f"https://youtu.be/{VIDEO_ID}?si=test",
        "kind": "transcript",
        "contract": {"name": "gemini-transcript", "version": 1},
        "timestampBasis": "full_video",
        "languagePolicy": {"mode": "source"},
        "validCoverage": [interval(start, end)],
    }
    value.update(overrides)
    return value


def content(start=0, end=600_000, text="test"):
    return {
        "segments": [
            {"startMs": start, "endMs": end, "text": text}
        ]
    }


class ArtifactCacheV3StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.artifacts = self.root / "artifacts"

    def tearDown(self):
        self.temporary.cleanup()

    def create_artifact(self, start=0, end=600_000, text="test", **overrides):
        artifact = artifact_cache.build_artifact(
            metadata(start, end, **overrides),
            content(start, end, text),
        )
        path = artifact_cache.write_immutable_artifact(
            self.artifacts,
            artifact,
        )
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

    def test_manifest_and_artifact_are_search_only_schema_one_records(self):
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        artifact, _ = self.create_artifact()

        self.assertEqual(
            set(manifest),
            {"schemaVersion", "cacheSystem", "videoId", "artifacts", "updatedAt"},
        )
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(artifact["schemaVersion"], 1)
        serialized = json.dumps({"manifest": manifest, "artifact": artifact})
        for forbidden in (
            "execution",
            "fingerprint",
            "provenance",
            "retry",
            "lease",
            "cooldown",
            "requestedCoverage",
            "completionState",
            "gaps",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_artifact_identity_does_not_depend_on_execution(self):
        first = artifact_cache.build_artifact(metadata(), content())
        second = artifact_cache.build_artifact(metadata(), content())

        self.assertEqual(first["artifactId"], second["artifactId"])
        self.assertEqual(first, second)

    def test_stores_immutable_artifact_and_minimal_manifest_entry(self):
        artifact, artifact_path = self.create_artifact()
        original_bytes = artifact_path.read_bytes()
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)

        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            artifact_path,
            updated_at=LATER,
        )

        self.assertEqual(artifact_path.read_bytes(), original_bytes)
        self.assertEqual(len(manifest["artifacts"]), 1)
        entry = manifest["artifacts"][0]
        self.assertEqual(
            set(entry),
            {
                "artifactId",
                "driveFileId",
                "fileName",
                "kind",
                "contract",
                "timestampBasis",
                "languagePolicy",
                "validCoverage",
                "integrity",
            },
        )
        self.assertEqual(entry["artifactId"], artifact["artifactId"])
        self.assertEqual(
            entry["integrity"]["value"],
            artifact_cache.sha256_hex(original_bytes),
        )

    def test_readding_identical_artifact_is_byte_stable(self):
        artifact, path = self.create_artifact()
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            path,
            updated_at=LATER,
        )
        snapshot = artifact_cache.stored_json_bytes(manifest)

        artifact_cache.add_artifact_to_manifest(
            manifest,
            artifact,
            "drive-file-1",
            path,
            updated_at="2026-07-27T12:02:00Z",
        )

        self.assertEqual(artifact_cache.stored_json_bytes(manifest), snapshot)

    def test_rebuilds_missing_manifest_only_from_native_artifacts(self):
        first, first_path = self.create_artifact(0, 600_000, text="first")
        second, second_path = self.create_artifact(
            600_000,
            1_200_000,
            text="second",
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

        self.assertEqual(len(rebuilt["artifacts"]), 2)
        self.assertNotIn("executions", rebuilt)
        self.assertEqual(
            {item["artifactId"] for item in rebuilt["artifacts"]},
            {first["artifactId"], second["artifactId"]},
        )

    def test_partial_result_is_represented_only_by_valid_coverage(self):
        artifact, _ = self.create_artifact(0, 420_000)

        self.assertEqual(
            artifact["validCoverage"],
            [interval(0, 420_000)],
        )
        self.assertNotIn("completionState", artifact)
        self.assertNotIn("gaps", artifact)
        self.assertNotIn("requestedCoverage", artifact)

    def test_analysis_artifact_requires_task_description(self):
        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "require a task description",
        ):
            artifact_cache.build_artifact(
                metadata(kind="question_analysis"),
                {"observations": []},
            )

    def test_rejects_execution_fields_in_manifest(self):
        manifest = artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW)
        manifest["executions"] = []

        with self.assertRaisesRegex(
            artifact_cache.CacheV3Error,
            "unsupported fields",
        ):
            artifact_cache.validate_manifest(manifest)


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
        contract=None,
        language_policy=None,
        task_description=None,
        kind="transcript",
        text=None,
    ):
        self.counter += 1
        artifact_metadata = metadata(
            start,
            end,
            contract=contract
            or {"name": "gemini-transcript", "version": 1},
            languagePolicy=language_policy or {"mode": "source"},
            kind=kind,
        )
        if task_description:
            artifact_metadata["taskDescription"] = task_description
        artifact = artifact_cache.build_artifact(
            artifact_metadata,
            content(start, end, text or f"artifact-{self.counter}"),
        )
        path = artifact_cache.write_immutable_artifact(
            self.artifacts,
            artifact,
        )
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

    def plan(self, query=None):
        return artifact_cache.plan_artifact_search(
            self.manifest,
            query or self.query(),
        )

    def verify(self, plan, query=None):
        return artifact_cache.verify_search_plan(
            self.manifest,
            self.artifacts,
            query or self.query(),
            plan,
        )

    def test_exact_coverage_plans_then_verifies_one_artifact(self):
        artifact, _ = self.add_artifact(0, 600_000)

        planned = self.plan()
        verified = self.verify(planned)

        self.assertEqual(planned["coverageStatus"], "complete")
        self.assertEqual(planned["coverageCases"], ["exact"])
        self.assertEqual(
            planned["artifactIdsToFetch"],
            [artifact["artifactId"]],
        )
        self.assertEqual(verified["verificationStatus"], "verified")
        self.assertEqual(verified["artifactIdsToFetch"], [])
        self.assertEqual(verified["newRequestIntervals"], [])

    def test_manifest_planning_does_not_read_artifact_files(self):
        artifact, path = self.add_artifact(0, 600_000)
        path.unlink()

        planned = self.plan()

        self.assertEqual(
            planned["artifactIdsToFetch"],
            [artifact["artifactId"]],
        )
        self.assertEqual(planned["verificationStatus"], "fetch_required")

    def test_containing_artifact_satisfies_smaller_interval(self):
        self.add_artifact(0, 600_000)
        query = self.query(120_000, 240_000)

        plan = self.plan(query)

        self.assertEqual(plan["coverageCases"], ["containing"])
        self.assertEqual(plan["coveredIntervals"], [interval(120_000, 240_000)])

    def test_adjacent_artifacts_compose_complete_coverage(self):
        self.add_artifact(0, 300_000)
        self.add_artifact(300_000, 600_000)

        plan = self.plan()

        self.assertEqual(plan["coverageCases"], ["composite"])
        self.assertEqual(len(plan["selectedArtifacts"]), 2)
        self.assertEqual(plan["newRequestIntervals"], [])

    def test_overlapping_artifacts_compose_without_gap(self):
        self.add_artifact(0, 360_000)
        self.add_artifact(300_000, 600_000)

        plan = self.plan()

        self.assertEqual(
            plan["coverageCases"],
            ["composite", "overlapping"],
        )
        self.assertEqual(plan["coveredIntervals"], [interval(0, 600_000)])

    def test_only_uncovered_gap_becomes_new_work(self):
        self.add_artifact(0, 180_000)
        self.add_artifact(420_000, 600_000)

        plan = self.plan()

        self.assertEqual(plan["coverageStatus"], "partial")
        self.assertEqual(
            plan["newRequestIntervals"],
            [interval(180_000, 420_000)],
        )

    def test_partial_artifact_contributes_only_valid_coverage(self):
        self.add_artifact(0, 420_000)

        plan = self.plan()

        self.assertEqual(plan["coveredIntervals"], [interval(0, 420_000)])
        self.assertEqual(
            plan["newRequestIntervals"],
            [interval(420_000, 600_000)],
        )

    def test_incompatible_contract_and_language_are_not_selected(self):
        self.add_artifact(
            0,
            600_000,
            contract={"name": "gemini-transcript", "version": 2},
            language_policy={"mode": "translated", "target": "en"},
        )

        plan = self.plan()

        self.assertEqual(
            plan["coverageCases"],
            ["incompatible", "missing"],
        )
        self.assertEqual(plan["selectedArtifacts"], [])
        self.assertEqual(
            plan["incompatibleArtifacts"][0]["reasons"],
            ["contract", "language_policy"],
        )

    def test_analysis_artifact_requires_explicit_approval(self):
        artifact, _ = self.add_artifact(
            0,
            600_000,
            task_description="Identify laboratory-method visuals.",
            kind="question_analysis",
        )
        query = self.query(kind="question_analysis")

        first = self.plan(query)
        approved = self.plan(
            self.query(
                kind="question_analysis",
                agentApprovedArtifactIds=[artifact["artifactId"]],
            )
        )

        self.assertTrue(first["requiresAgentReview"])
        self.assertEqual(first["selectedArtifacts"], [])
        self.assertEqual(
            first["reviewCandidates"][0]["taskDescription"],
            "Identify laboratory-method visuals.",
        )
        self.assertFalse(approved["requiresAgentReview"])
        self.assertEqual(approved["coverageCases"], ["exact"])

    def test_verification_fetches_only_selected_candidates(self):
        _, selected_path = self.add_artifact(0, 600_000, text="exact")
        _, unselected_path = self.add_artifact(0, 900_000, text="larger")
        plan = self.plan()
        selected_name = plan["selectedArtifacts"][0]["fileName"]
        if selected_path.name != selected_name:
            selected_path, unselected_path = unselected_path, selected_path
        unselected_path.unlink()

        verified = self.verify(plan)

        self.assertEqual(verified["verificationStatus"], "verified")
        self.assertEqual(verified["staleManifestEntries"], [])

    def test_stale_selected_artifact_replans_before_new_request(self):
        first, first_path = self.add_artifact(0, 600_000, text="first")
        second, second_path = self.add_artifact(0, 600_000, text="second")
        plan = self.plan()
        selected_id = plan["selectedArtifacts"][0]["artifactId"]
        path_by_id = {
            first["artifactId"]: first_path,
            second["artifactId"]: second_path,
        }
        path_by_id[selected_id].unlink()

        replanned = self.verify(plan)

        self.assertEqual(len(replanned["staleManifestEntries"]), 1)
        self.assertEqual(
            replanned["staleManifestEntries"][0]["artifactId"],
            selected_id,
        )
        self.assertEqual(replanned["verificationStatus"], "fetch_required")
        self.assertNotEqual(
            replanned["artifactIdsToFetch"],
            [selected_id],
        )
        verified = self.verify(replanned)
        self.assertEqual(verified["verificationStatus"], "verified")

    def test_integrity_failure_is_replanned_as_stale(self):
        artifact, path = self.add_artifact(0, 600_000)
        plan = self.plan()
        path.write_text('{"corrupted":true}\n', encoding="utf-8")

        replanned = self.verify(plan)

        self.assertEqual(replanned["selectedArtifacts"], [])
        self.assertEqual(
            replanned["staleManifestEntries"],
            [
                {
                    "artifactId": artifact["artifactId"],
                    "driveFileId": "drive-file-1",
                    "fileName": path.name,
                    "reason": "integrity_mismatch",
                }
            ],
        )
        self.assertEqual(
            replanned["newRequestIntervals"],
            [interval(0, 600_000)],
        )


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

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, str(MODULE_PATH), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_empty_manifest_requires_prior_artifact_enumeration(self):
        output = self.root / "manifest.json"

        refused = self.run_cli(
            "init-manifest",
            "--video",
            VIDEO_ID,
            "--output",
            str(output),
        )
        created = self.run_cli(
            "init-manifest",
            "--video",
            VIDEO_ID,
            "--output",
            str(output),
            "--confirmed-no-artifacts",
            "--updated-at",
            NOW,
        )

        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse("Traceback" in refused.stderr)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertTrue(output.exists())

    def test_empty_two_phase_search_and_chunk_plan(self):
        manifest = self.root / "manifest.json"
        query_path = self.root / "query.json"
        search_plan = self.root / "search-plan.json"
        chunk_plan = self.root / "chunk-plan.json"
        artifact_cache.write_json(
            manifest,
            artifact_cache.new_manifest(VIDEO_ID, updated_at=NOW),
        )
        artifact_cache.write_json(
            query_path,
            {
                "video": VIDEO_ID,
                "kind": "transcript",
                "contract": {"name": "gemini-transcript", "version": 1},
                "timestampBasis": "full_video",
                "languagePolicy": {"mode": "source"},
                "requestedCoverage": [interval(0, 600_000)],
            },
        )

        searched = self.run_cli(
            "search",
            "--manifest",
            str(manifest),
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

        self.assertEqual(searched.returncode, 0, searched.stderr)
        self.assertEqual(chunked.returncode, 0, chunked.stderr)
        self.assertEqual(
            json.loads(chunk_plan.read_text(encoding="utf-8"))["chunks"],
            [interval(0, 300_000), interval(300_000, 600_000)],
        )


if __name__ == "__main__":
    unittest.main()
