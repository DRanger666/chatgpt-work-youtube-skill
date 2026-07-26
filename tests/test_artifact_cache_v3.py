import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()
