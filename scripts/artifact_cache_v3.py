#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SCHEMA_VERSION = 1
CACHE_SYSTEM = "youtube-artifact-cache-v3"
DRIVE_NAMESPACE = "YouTubeArtifactCacheV3"
TIMESTAMP_BASIS = "full_video"
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_FIELDS = {
    "schemaVersion",
    "cacheSystem",
    "videoId",
    "artifacts",
    "updatedAt",
}
ARTIFACT_FIELDS = {
    "schemaVersion",
    "cacheSystem",
    "artifactId",
    "videoId",
    "kind",
    "contract",
    "timestampBasis",
    "languagePolicy",
    "validCoverage",
    "content",
}
ARTIFACT_OPTIONAL_FIELDS = {"taskDescription"}
MANIFEST_ARTIFACT_FIELDS = {
    "artifactId",
    "driveFileId",
    "fileName",
    "kind",
    "contract",
    "timestampBasis",
    "languagePolicy",
    "validCoverage",
    "integrity",
}
MANIFEST_ARTIFACT_OPTIONAL_FIELDS = {"taskDescription"}
QUERY_FIELDS = {
    "video",
    "kind",
    "contract",
    "timestampBasis",
    "languagePolicy",
    "requestedCoverage",
}
QUERY_OPTIONAL_FIELDS = {"agentApprovedArtifactIds"}
COVERAGE_CASE_ORDER = (
    "exact",
    "containing",
    "composite",
    "overlapping",
    "incompatible",
    "missing",
)


class CacheV3Error(ValueError):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def canonical_json_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def stored_json_bytes(value) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        raise CacheV3Error(f"Cannot read JSON from {path}: {error}") from error


def write_json(path: Path, value) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(stored_json_bytes(value))
    temporary.replace(path)


def require_exact_fields(value, required, optional, label) -> None:
    if not isinstance(value, dict):
        raise CacheV3Error(f"{label} must be an object")
    missing = required - value.keys()
    extra = value.keys() - required - optional
    if missing:
        raise CacheV3Error(f"{label} is missing fields: {sorted(missing)}")
    if extra:
        raise CacheV3Error(f"{label} has unsupported fields: {sorted(extra)}")


def normalize_youtube_video_id(source: str) -> str:
    if not isinstance(source, str) or not source.strip():
        raise CacheV3Error("YouTube video source must be a non-empty string")
    source = source.strip()
    if VIDEO_ID_PATTERN.fullmatch(source):
        return source

    parsed = urlparse(source if "://" in source else f"https://{source}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host.startswith("m."):
        host = host[2:]

    video_id = None
    if host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
    elif host in {"youtube.com", "youtube-nocookie.com"}:
        path_parts = [part for part in parsed.path.split("/") if part]
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(path_parts) >= 2 and path_parts[0] in {
            "embed",
            "shorts",
            "live",
        }:
            video_id = path_parts[1]

    if not video_id or not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise CacheV3Error(f"Cannot normalize a YouTube video ID from: {source}")
    return video_id


def manifest_filename(video_id: str) -> str:
    normalized = normalize_youtube_video_id(video_id)
    return f"{normalized}--manifest.json"


def artifact_filename(video_id: str, kind: str, artifact_id: str) -> str:
    normalized = normalize_youtube_video_id(video_id)
    validate_kind(kind)
    validate_sha256(artifact_id, "artifact ID")
    return f"{normalized}--{kind}--{artifact_id}.json"


def validate_kind(kind: str) -> None:
    if not isinstance(kind, str) or not KIND_PATTERN.fullmatch(kind):
        raise CacheV3Error(
            "Artifact kind must use lowercase letters, digits, underscores, or hyphens"
        )


def validate_sha256(value: str, label: str) -> None:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise CacheV3Error(f"{label} must be a lowercase SHA-256 hex digest")


def validate_contract(contract) -> None:
    require_exact_fields(contract, {"name", "version"}, set(), "contract")
    if not isinstance(contract["name"], str) or not contract["name"]:
        raise CacheV3Error("Contract name must be a non-empty string")
    version = contract["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise CacheV3Error("Contract version must be a positive integer")


def validate_language_policy(policy) -> None:
    if not isinstance(policy, dict) or not policy:
        raise CacheV3Error("Language policy must be a non-empty object")


def normalize_intervals(intervals, label="coverage"):
    if not isinstance(intervals, list):
        raise CacheV3Error(f"{label} must be an array")
    normalized = []
    for index, interval in enumerate(intervals):
        require_exact_fields(
            interval,
            {"startMs", "endMs"},
            set(),
            f"{label}[{index}]",
        )
        start = interval["startMs"]
        end = interval["endMs"]
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
        ):
            raise CacheV3Error(
                f"{label}[{index}] must satisfy 0 <= startMs < endMs"
            )
        normalized.append({"startMs": start, "endMs": end})

    normalized.sort(key=lambda item: (item["startMs"], item["endMs"]))
    merged = []
    for interval in normalized:
        if not merged or interval["startMs"] > merged[-1]["endMs"]:
            merged.append(dict(interval))
        else:
            merged[-1]["endMs"] = max(merged[-1]["endMs"], interval["endMs"])
    return merged


def intersect_intervals(left, right):
    left = normalize_intervals(left, "left coverage")
    right = normalize_intervals(right, "right coverage")
    intersections = []
    left_index = 0
    right_index = 0
    while left_index < len(left) and right_index < len(right):
        start = max(left[left_index]["startMs"], right[right_index]["startMs"])
        end = min(left[left_index]["endMs"], right[right_index]["endMs"])
        if start < end:
            intersections.append({"startMs": start, "endMs": end})
        if left[left_index]["endMs"] <= right[right_index]["endMs"]:
            left_index += 1
        else:
            right_index += 1
    return normalize_intervals(intersections, "intersection")


def subtract_intervals(requested, covered):
    requested = normalize_intervals(requested, "requested coverage")
    covered = normalize_intervals(covered, "covered coverage")
    gaps = []
    for target in requested:
        cursor = target["startMs"]
        for interval in covered:
            if interval["endMs"] <= cursor:
                continue
            if interval["startMs"] >= target["endMs"]:
                break
            if interval["startMs"] > cursor:
                gaps.append(
                    {
                        "startMs": cursor,
                        "endMs": min(interval["startMs"], target["endMs"]),
                    }
                )
            cursor = max(cursor, min(interval["endMs"], target["endMs"]))
            if cursor >= target["endMs"]:
                break
        if cursor < target["endMs"]:
            gaps.append({"startMs": cursor, "endMs": target["endMs"]})
    return normalize_intervals(gaps, "gaps")


def validate_timestamp(value: str, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise CacheV3Error(f"{label} must be a non-empty timestamp string")


def new_manifest(video_source: str, updated_at=None):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": normalize_youtube_video_id(video_source),
        "artifacts": [],
        "updatedAt": updated_at or utc_now(),
    }


def validate_manifest(manifest):
    require_exact_fields(manifest, MANIFEST_FIELDS, set(), "manifest")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise CacheV3Error(
            f"Unsupported native manifest schema version: {manifest['schemaVersion']}"
        )
    if manifest["cacheSystem"] != CACHE_SYSTEM:
        raise CacheV3Error("Manifest belongs to a different cache system")
    manifest["videoId"] = normalize_youtube_video_id(manifest["videoId"])
    validate_timestamp(manifest["updatedAt"], "updatedAt")
    if not isinstance(manifest["artifacts"], list):
        raise CacheV3Error("Manifest artifacts must be an array")

    artifact_ids = set()
    file_names = set()
    for entry in manifest["artifacts"]:
        validate_manifest_artifact_entry(entry, manifest["videoId"])
        if entry["artifactId"] in artifact_ids:
            raise CacheV3Error(f"Duplicate artifact ID: {entry['artifactId']}")
        if entry["fileName"] in file_names:
            raise CacheV3Error(f"Duplicate artifact filename: {entry['fileName']}")
        artifact_ids.add(entry["artifactId"])
        file_names.add(entry["fileName"])
    return manifest


def build_artifact(metadata, content):
    required = {
        "video",
        "kind",
        "contract",
        "timestampBasis",
        "languagePolicy",
        "validCoverage",
    }
    optional = {"taskDescription"}
    require_exact_fields(metadata, required, optional, "artifact metadata")
    validate_kind(metadata["kind"])
    validate_contract(metadata["contract"])
    if metadata["timestampBasis"] != TIMESTAMP_BASIS:
        raise CacheV3Error(
            f"Native v3 timestamp basis must be {TIMESTAMP_BASIS}"
        )
    validate_language_policy(metadata["languagePolicy"])
    valid = normalize_intervals(metadata["validCoverage"], "valid coverage")
    if not valid:
        raise CacheV3Error("Artifact valid coverage cannot be empty")

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": normalize_youtube_video_id(metadata["video"]),
        "kind": metadata["kind"],
        "contract": metadata["contract"],
        "timestampBasis": metadata["timestampBasis"],
        "languagePolicy": metadata["languagePolicy"],
        "validCoverage": valid,
        "content": content,
    }
    task_description = metadata.get("taskDescription")
    if "analysis" in metadata["kind"] and task_description is None:
        raise CacheV3Error("Analysis artifacts require a task description")
    if task_description is not None:
        if not isinstance(task_description, str) or not task_description.strip():
            raise CacheV3Error("Task description must be a non-empty string")
        artifact["taskDescription"] = task_description.strip()
    artifact["artifactId"] = sha256_hex(canonical_json_bytes(artifact))
    validate_artifact(artifact)
    return artifact


def validate_artifact(artifact):
    require_exact_fields(
        artifact,
        ARTIFACT_FIELDS,
        ARTIFACT_OPTIONAL_FIELDS,
        "artifact",
    )
    if artifact["schemaVersion"] != SCHEMA_VERSION:
        raise CacheV3Error(
            f"Unsupported native artifact schema version: {artifact['schemaVersion']}"
        )
    if artifact["cacheSystem"] != CACHE_SYSTEM:
        raise CacheV3Error("Artifact belongs to a different cache system")
    artifact["videoId"] = normalize_youtube_video_id(artifact["videoId"])
    validate_kind(artifact["kind"])
    validate_contract(artifact["contract"])
    if artifact["timestampBasis"] != TIMESTAMP_BASIS:
        raise CacheV3Error(
            f"Native v3 timestamp basis must be {TIMESTAMP_BASIS}"
        )
    validate_language_policy(artifact["languagePolicy"])
    artifact["validCoverage"] = normalize_intervals(
        artifact["validCoverage"],
        "artifact valid coverage",
    )
    if not artifact["validCoverage"]:
        raise CacheV3Error("Artifact valid coverage cannot be empty")
    if "taskDescription" in artifact and (
        not isinstance(artifact["taskDescription"], str)
        or not artifact["taskDescription"].strip()
    ):
        raise CacheV3Error("Task description must be a non-empty string")
    if "analysis" in artifact["kind"] and "taskDescription" not in artifact:
        raise CacheV3Error("Analysis artifacts require a task description")
    validate_sha256(artifact["artifactId"], "artifact ID")
    content_for_id = dict(artifact)
    content_for_id.pop("artifactId")
    expected_id = sha256_hex(canonical_json_bytes(content_for_id))
    if artifact["artifactId"] != expected_id:
        raise CacheV3Error("Artifact ID does not match its canonical content")
    return artifact


def write_immutable_artifact(directory: Path, artifact):
    validate_artifact(artifact)
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / artifact_filename(
        artifact["videoId"],
        artifact["kind"],
        artifact["artifactId"],
    )
    payload = stored_json_bytes(artifact)
    if path.exists():
        if path.read_bytes() != payload:
            raise CacheV3Error(f"Refusing to rewrite immutable artifact: {path}")
        return path
    path.write_bytes(payload)
    return path


def manifest_artifact_entry(artifact, drive_file_id: str, path: Path):
    validate_artifact(artifact)
    if not isinstance(drive_file_id, str) or not drive_file_id:
        raise CacheV3Error("Drive file ID must be a non-empty string")
    expected_name = artifact_filename(
        artifact["videoId"],
        artifact["kind"],
        artifact["artifactId"],
    )
    if path.name != expected_name:
        raise CacheV3Error("Artifact filename does not match its native identity")
    entry = {
        "artifactId": artifact["artifactId"],
        "driveFileId": drive_file_id,
        "fileName": expected_name,
        "kind": artifact["kind"],
        "contract": artifact["contract"],
        "timestampBasis": artifact["timestampBasis"],
        "languagePolicy": artifact["languagePolicy"],
        "validCoverage": artifact["validCoverage"],
        "integrity": {
            "algorithm": "sha256",
            "value": sha256_hex(path.read_bytes()),
        },
    }
    if "taskDescription" in artifact:
        entry["taskDescription"] = artifact["taskDescription"]
    validate_manifest_artifact_entry(entry, artifact["videoId"])
    return entry


def validate_manifest_artifact_entry(entry, video_id: str) -> None:
    require_exact_fields(
        entry,
        MANIFEST_ARTIFACT_FIELDS,
        MANIFEST_ARTIFACT_OPTIONAL_FIELDS,
        "manifest artifact entry",
    )
    validate_sha256(entry["artifactId"], "artifact ID")
    if not isinstance(entry["driveFileId"], str) or not entry["driveFileId"]:
        raise CacheV3Error("Drive file ID must be a non-empty string")
    validate_kind(entry["kind"])
    expected_name = artifact_filename(video_id, entry["kind"], entry["artifactId"])
    if entry["fileName"] != expected_name:
        raise CacheV3Error("Manifest artifact filename is not deterministic")
    validate_contract(entry["contract"])
    if entry["timestampBasis"] != TIMESTAMP_BASIS:
        raise CacheV3Error(
            f"Native v3 timestamp basis must be {TIMESTAMP_BASIS}"
        )
    validate_language_policy(entry["languagePolicy"])
    entry["validCoverage"] = normalize_intervals(
        entry["validCoverage"],
        "manifest artifact valid coverage",
    )
    if not entry["validCoverage"]:
        raise CacheV3Error("Manifest artifact valid coverage cannot be empty")
    require_exact_fields(
        entry["integrity"],
        {"algorithm", "value"},
        set(),
        "artifact integrity",
    )
    if entry["integrity"]["algorithm"] != "sha256":
        raise CacheV3Error("Native artifact integrity must use SHA-256")
    validate_sha256(entry["integrity"]["value"], "artifact integrity")
    if "taskDescription" in entry and (
        not isinstance(entry["taskDescription"], str)
        or not entry["taskDescription"].strip()
    ):
        raise CacheV3Error("Task description must be a non-empty string")
    if "analysis" in entry["kind"] and "taskDescription" not in entry:
        raise CacheV3Error("Analysis artifacts require a task description")


def add_artifact_to_manifest(
    manifest,
    artifact,
    drive_file_id: str,
    artifact_path: Path,
    updated_at=None,
):
    validate_manifest(manifest)
    validate_artifact(artifact)
    if manifest["videoId"] != artifact["videoId"]:
        raise CacheV3Error("Artifact and manifest video IDs differ")
    entry = manifest_artifact_entry(artifact, drive_file_id, artifact_path)
    existing = next(
        (
            item
            for item in manifest["artifacts"]
            if item["artifactId"] == artifact["artifactId"]
        ),
        None,
    )
    if existing is not None:
        if existing != entry:
            raise CacheV3Error("Artifact ID already has different manifest metadata")
        return manifest

    manifest["artifacts"].append(entry)
    manifest["artifacts"].sort(key=lambda item: item["artifactId"])
    manifest["updatedAt"] = updated_at or utc_now()
    validate_manifest(manifest)
    return manifest


def rebuild_manifest(
    video_source: str,
    artifact_paths,
    drive_file_ids,
    updated_at=None,
):
    manifest = new_manifest(video_source, updated_at=updated_at)
    for path in sorted((Path(item).resolve() for item in artifact_paths), key=str):
        artifact = load_json(path)
        validate_artifact(artifact)
        if artifact["videoId"] != manifest["videoId"]:
            continue
        drive_file_id = drive_file_ids.get(path.name)
        if not drive_file_id:
            raise CacheV3Error(f"Missing Drive file ID for {path.name}")
        add_artifact_to_manifest(
            manifest,
            artifact,
            drive_file_id,
            path,
            updated_at=updated_at,
        )
    manifest["updatedAt"] = updated_at or utc_now()
    validate_manifest(manifest)
    return manifest


def verify_artifact_for_entry(entry, artifact_directory: Path, video_id: str):
    path = artifact_directory.resolve() / entry["fileName"]
    if not path.is_file():
        raise CacheV3Error("missing_artifact_file")
    if sha256_hex(path.read_bytes()) != entry["integrity"]["value"]:
        raise CacheV3Error("integrity_mismatch")
    artifact = load_json(path)
    validate_artifact(artifact)
    if artifact["videoId"] != video_id:
        raise CacheV3Error("video_identity_mismatch")
    expected_entry = manifest_artifact_entry(
        artifact,
        entry["driveFileId"],
        path,
    )
    if expected_entry != entry:
        raise CacheV3Error("manifest_metadata_mismatch")
    return artifact


def validate_query(query):
    require_exact_fields(query, QUERY_FIELDS, QUERY_OPTIONAL_FIELDS, "query")
    query["videoId"] = normalize_youtube_video_id(query.pop("video"))
    validate_kind(query["kind"])
    validate_contract(query["contract"])
    if (
        not isinstance(query["timestampBasis"], str)
        or not query["timestampBasis"]
    ):
        raise CacheV3Error("Query timestamp basis must be a non-empty string")
    validate_language_policy(query["languagePolicy"])
    query["requestedCoverage"] = normalize_intervals(
        query["requestedCoverage"],
        "query requested coverage",
    )
    if not query["requestedCoverage"]:
        raise CacheV3Error("Query requested coverage cannot be empty")
    approved = query.get("agentApprovedArtifactIds", [])
    if not isinstance(approved, list) or not all(
        isinstance(item, str) and SHA256_PATTERN.fullmatch(item)
        for item in approved
    ):
        raise CacheV3Error(
            "agentApprovedArtifactIds must contain artifact SHA-256 IDs"
        )
    query["agentApprovedArtifactIds"] = sorted(set(approved))
    return query


def compatibility_reasons(entry, query):
    reasons = []
    if entry["contract"] != query["contract"]:
        reasons.append("contract")
    if entry["timestampBasis"] != query["timestampBasis"]:
        reasons.append("timestamp_basis")
    if canonical_json_bytes(entry["languagePolicy"]) != canonical_json_bytes(
        query["languagePolicy"]
    ):
        reasons.append("language_policy")
    return reasons


def entry_summary(entry):
    summary = {
        "artifactId": entry["artifactId"],
        "driveFileId": entry["driveFileId"],
        "fileName": entry["fileName"],
        "validCoverage": entry["validCoverage"],
    }
    if "taskDescription" in entry:
        summary["taskDescription"] = entry["taskDescription"]
    return summary


def intervals_cover(covering, requested) -> bool:
    return not subtract_intervals(requested, covering)


def interval_duration(intervals) -> int:
    return sum(item["endMs"] - item["startMs"] for item in intervals)


def choose_covering_artifact(candidates, requested):
    covering = [
        item
        for item in candidates
        if intervals_cover(item["validCoverage"], requested)
    ]
    if not covering:
        return None
    covering.sort(
        key=lambda item: (
            item["validCoverage"] != requested,
            interval_duration(item["validCoverage"]),
            item["artifactId"],
        )
    )
    return covering[0]


def choose_composite_artifacts(candidates, requested):
    selected = {}
    for target in requested:
        cursor = target["startMs"]
        while cursor < target["endMs"]:
            choices = []
            next_start = None
            for entry in candidates:
                for coverage in intersect_intervals(
                    entry["validCoverage"],
                    [target],
                ):
                    if coverage["startMs"] <= cursor < coverage["endMs"]:
                        choices.append((coverage["endMs"], entry["artifactId"], entry))
                    elif coverage["startMs"] > cursor:
                        if next_start is None or coverage["startMs"] < next_start:
                            next_start = coverage["startMs"]
            if choices:
                _, _, chosen = max(choices, key=lambda item: (item[0], item[1]))
                selected[chosen["artifactId"]] = chosen
                furthest = max(
                    coverage["endMs"]
                    for coverage in intersect_intervals(
                        chosen["validCoverage"],
                        [target],
                    )
                    if coverage["startMs"] <= cursor < coverage["endMs"]
                )
                cursor = furthest
            elif next_start is not None and next_start < target["endMs"]:
                cursor = next_start
            else:
                break
    return [selected[key] for key in sorted(selected)]


def selected_artifacts_overlap(selected, requested) -> bool:
    intervals = []
    for entry in selected:
        for interval in intersect_intervals(entry["validCoverage"], requested):
            intervals.append(
                (
                    interval["startMs"],
                    interval["endMs"],
                    entry["artifactId"],
                )
            )
    intervals.sort()
    for index, left in enumerate(intervals):
        for right in intervals[index + 1 :]:
            if right[0] >= left[1]:
                break
            if left[2] != right[2] and right[0] < left[1]:
                return True
    return False


def plan_artifact_search(manifest, query, excluded_artifact_ids=None):
    validate_manifest(manifest)
    query = validate_query(dict(query))
    if manifest["videoId"] != query["videoId"]:
        raise CacheV3Error("Query and manifest video IDs differ")

    approved = set(query["agentApprovedArtifactIds"])
    excluded = set(excluded_artifact_ids or [])
    for artifact_id in excluded:
        validate_sha256(artifact_id, "excluded artifact ID")
    compatible = []
    incompatible = []
    review_candidates = []

    for entry in manifest["artifacts"]:
        if entry["kind"] != query["kind"]:
            continue
        if entry["artifactId"] in excluded:
            continue
        reasons = compatibility_reasons(entry, query)
        if reasons:
            incompatible.append(
                {
                    **entry_summary(entry),
                    "reasons": reasons,
                }
            )
            continue
        if "taskDescription" in entry and entry["artifactId"] not in approved:
            review_candidates.append(entry_summary(entry))
            continue
        if intersect_intervals(
            entry["validCoverage"],
            query["requestedCoverage"],
        ):
            compatible.append(entry)

    selected = []
    cases = set()
    covering = choose_covering_artifact(
        compatible,
        query["requestedCoverage"],
    )
    if covering is not None:
        selected = [covering]
        if covering["validCoverage"] == query["requestedCoverage"]:
            cases.add("exact")
        else:
            cases.add("containing")
    else:
        selected = choose_composite_artifacts(
            compatible,
            query["requestedCoverage"],
        )
        if len(selected) > 1:
            cases.add("composite")
            if selected_artifacts_overlap(
                selected,
                query["requestedCoverage"],
            ):
                cases.add("overlapping")

    selected_coverage = normalize_intervals(
        [
            interval
            for entry in selected
            for interval in intersect_intervals(
                entry["validCoverage"],
                query["requestedCoverage"],
            )
        ],
        "selected coverage",
    )
    uncovered = subtract_intervals(
        query["requestedCoverage"],
        selected_coverage,
    )
    if incompatible:
        cases.add("incompatible")
    if uncovered:
        cases.add("missing")

    if not uncovered:
        coverage_status = "complete"
    elif selected_coverage:
        coverage_status = "partial"
    else:
        coverage_status = "missing"

    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": manifest["videoId"],
        "kind": query["kind"],
        "coverageStatus": coverage_status,
        "coverageCases": [
            item for item in COVERAGE_CASE_ORDER if item in cases
        ],
        "requestedCoverage": query["requestedCoverage"],
        "coveredIntervals": selected_coverage,
        "uncoveredIntervals": uncovered,
        "newRequestIntervals": uncovered,
        "selectedArtifacts": [entry_summary(entry) for entry in selected],
        "incompatibleArtifacts": incompatible,
        "reviewCandidates": review_candidates,
        "requiresAgentReview": bool(review_candidates),
        "staleManifestEntries": [],
        "artifactIdsToFetch": [
            entry["artifactId"] for entry in selected
        ],
        "verificationStatus": (
            "fetch_required" if selected else "not_required"
        ),
    }


def validate_search_plan(plan):
    require_exact_fields(
        plan,
        {
            "schemaVersion",
            "cacheSystem",
            "videoId",
            "kind",
            "coverageStatus",
            "coverageCases",
            "requestedCoverage",
            "coveredIntervals",
            "uncoveredIntervals",
            "newRequestIntervals",
            "selectedArtifacts",
            "incompatibleArtifacts",
            "reviewCandidates",
            "requiresAgentReview",
            "staleManifestEntries",
            "artifactIdsToFetch",
            "verificationStatus",
        },
        set(),
        "search plan",
    )
    if plan["schemaVersion"] != SCHEMA_VERSION or plan["cacheSystem"] != CACHE_SYSTEM:
        raise CacheV3Error("Search plan is not native cache v3")
    plan["videoId"] = normalize_youtube_video_id(plan["videoId"])
    if plan["verificationStatus"] not in {
        "fetch_required",
        "verified",
        "not_required",
    }:
        raise CacheV3Error("Unsupported search verification status")
    return plan


def verify_search_plan(manifest, artifact_directory: Path, query, plan):
    validate_manifest(manifest)
    raw_query = dict(query)
    query = validate_query(dict(query))
    plan = validate_search_plan(dict(plan))
    if manifest["videoId"] != query["videoId"] or plan["videoId"] != query["videoId"]:
        raise CacheV3Error("Manifest, query, and search plan video IDs differ")

    planned_ids = {
        item["artifactId"] for item in plan["selectedArtifacts"]
    }
    if planned_ids != set(plan["artifactIdsToFetch"]):
        raise CacheV3Error("Search plan fetch IDs do not match selected artifacts")

    by_id = {entry["artifactId"]: entry for entry in manifest["artifacts"]}
    stale = []
    for artifact_id in sorted(planned_ids):
        entry = by_id.get(artifact_id)
        if entry is None:
            stale.append(
                {
                    "artifactId": artifact_id,
                    "driveFileId": None,
                    "fileName": None,
                    "reason": "missing_manifest_entry",
                }
            )
            continue
        try:
            verify_artifact_for_entry(
                entry,
                artifact_directory,
                manifest["videoId"],
            )
        except CacheV3Error as error:
            stale.append(
                {
                    "artifactId": entry["artifactId"],
                    "driveFileId": entry["driveFileId"],
                    "fileName": entry["fileName"],
                    "reason": str(error),
                }
            )

    if not stale:
        verified = dict(plan)
        verified["artifactIdsToFetch"] = []
        verified["verificationStatus"] = (
            "verified" if planned_ids else "not_required"
        )
        validate_search_plan(verified)
        return verified

    excluded = {item["artifactId"] for item in stale}
    replanned = plan_artifact_search(
        manifest,
        raw_query,
        excluded_artifact_ids=excluded,
    )
    replanned["staleManifestEntries"] = stale
    return replanned


def plan_chunks(intervals, chunk_seconds: int, overlap_seconds: int = 0):
    if (
        not isinstance(chunk_seconds, int)
        or isinstance(chunk_seconds, bool)
        or chunk_seconds <= 0
    ):
        raise CacheV3Error("Chunk size must be a positive integer")
    if (
        not isinstance(overlap_seconds, int)
        or isinstance(overlap_seconds, bool)
        or overlap_seconds < 0
        or overlap_seconds >= chunk_seconds
    ):
        raise CacheV3Error("Overlap must satisfy 0 <= overlap < chunk size")
    chunk_ms = chunk_seconds * 1_000
    overlap_ms = overlap_seconds * 1_000
    chunks = []
    for interval in normalize_intervals(intervals, "chunk coverage"):
        start = interval["startMs"]
        while start < interval["endMs"]:
            end = min(start + chunk_ms, interval["endMs"])
            chunks.append({"startMs": start, "endMs": end})
            if end == interval["endMs"]:
                break
            start = end - overlap_ms
    return chunks


def command_locate(args) -> int:
    video_id = normalize_youtube_video_id(args.video)
    print(
        json.dumps(
            {
                "cacheSystem": CACHE_SYSTEM,
                "namespace": DRIVE_NAMESPACE,
                "videoId": video_id,
                "manifestFileName": manifest_filename(video_id),
            },
            sort_keys=True,
        )
    )
    return 0


def command_init_manifest(args) -> int:
    if not args.confirmed_no_artifacts:
        raise CacheV3Error(
            "Refusing empty manifest initialization until existing native "
            "artifacts have been enumerated"
        )
    manifest = new_manifest(args.video, updated_at=args.updated_at)
    write_json(Path(args.output), manifest)
    print(Path(args.output).resolve())
    return 0


def command_create_artifact(args) -> int:
    metadata = load_json(Path(args.metadata))
    content = load_json(Path(args.content))
    artifact = build_artifact(metadata, content)
    path = write_immutable_artifact(Path(args.output_dir), artifact)
    print(
        json.dumps(
            {
                "artifactId": artifact["artifactId"],
                "fileName": path.name,
                "path": str(path),
                "sha256": sha256_hex(path.read_bytes()),
            },
            sort_keys=True,
        )
    )
    return 0


def command_add_artifact(args) -> int:
    manifest = load_json(Path(args.manifest))
    artifact_path = Path(args.artifact).resolve()
    artifact = load_json(artifact_path)
    updated = add_artifact_to_manifest(
        manifest,
        artifact,
        args.drive_file_id,
        artifact_path,
        updated_at=args.updated_at,
    )
    write_json(Path(args.output), updated)
    print(Path(args.output).resolve())
    return 0


def command_rebuild_manifest(args) -> int:
    artifact_directory = Path(args.artifacts_dir).resolve()
    drive_map = load_json(Path(args.drive_map))
    if not isinstance(drive_map, dict):
        raise CacheV3Error("Drive map must be an object keyed by filename")
    video_id = normalize_youtube_video_id(args.video)
    paths = artifact_directory.glob(f"{video_id}--*--*.json")
    manifest = rebuild_manifest(
        video_id,
        paths,
        drive_map,
        updated_at=args.updated_at,
    )
    write_json(Path(args.output), manifest)
    print(Path(args.output).resolve())
    return 0


def command_search(args) -> int:
    manifest = load_json(Path(args.manifest))
    query = load_json(Path(args.query))
    plan = plan_artifact_search(manifest, query)
    write_json(Path(args.output), plan)
    print(Path(args.output).resolve())
    return 0


def command_verify_search(args) -> int:
    manifest = load_json(Path(args.manifest))
    query = load_json(Path(args.query))
    plan = load_json(Path(args.search_plan))
    plan = verify_search_plan(
        manifest,
        Path(args.artifacts_dir),
        query,
        plan,
    )
    write_json(Path(args.output), plan)
    print(Path(args.output).resolve())
    return 0


def command_plan_chunks(args) -> int:
    search_plan = validate_search_plan(
        load_json(Path(args.search_plan))
    )
    if search_plan["artifactIdsToFetch"]:
        raise CacheV3Error(
            "Search plan must verify selected artifacts before chunk planning"
        )
    chunks = plan_chunks(
        search_plan["newRequestIntervals"],
        args.chunk_seconds,
        args.overlap_seconds,
    )
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": search_plan["videoId"],
        "kind": search_plan["kind"],
        "chunks": chunks,
    }
    write_json(Path(args.output), output)
    print(Path(args.output).resolve())
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        description="Manage the clean-slate YouTube artifact cache v3"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    locate = subparsers.add_parser("locate")
    locate.add_argument("--video", required=True)
    locate.set_defaults(handler=command_locate)

    initialize = subparsers.add_parser("init-manifest")
    initialize.add_argument("--video", required=True)
    initialize.add_argument("--output", required=True)
    initialize.add_argument("--updated-at")
    initialize.add_argument(
        "--confirmed-no-artifacts",
        action="store_true",
        help="Confirm that native artifacts were enumerated and none exist",
    )
    initialize.set_defaults(handler=command_init_manifest)

    create = subparsers.add_parser("create-artifact")
    create.add_argument("--metadata", required=True)
    create.add_argument("--content", required=True)
    create.add_argument("--output-dir", required=True)
    create.set_defaults(handler=command_create_artifact)

    add = subparsers.add_parser("add-artifact")
    add.add_argument("--manifest", required=True)
    add.add_argument("--artifact", required=True)
    add.add_argument("--drive-file-id", required=True)
    add.add_argument("--output", required=True)
    add.add_argument("--updated-at")
    add.set_defaults(handler=command_add_artifact)

    rebuild = subparsers.add_parser("rebuild-manifest")
    rebuild.add_argument("--video", required=True)
    rebuild.add_argument("--artifacts-dir", required=True)
    rebuild.add_argument("--drive-map", required=True)
    rebuild.add_argument("--output", required=True)
    rebuild.add_argument("--updated-at")
    rebuild.set_defaults(handler=command_rebuild_manifest)

    search = subparsers.add_parser("search")
    search.add_argument("--manifest", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--output", required=True)
    search.set_defaults(handler=command_search)

    verify = subparsers.add_parser("verify-search")
    verify.add_argument("--manifest", required=True)
    verify.add_argument("--artifacts-dir", required=True)
    verify.add_argument("--query", required=True)
    verify.add_argument("--search-plan", required=True)
    verify.add_argument("--output", required=True)
    verify.set_defaults(handler=command_verify_search)

    chunks = subparsers.add_parser("plan-chunks")
    chunks.add_argument("--search-plan", required=True)
    chunks.add_argument("--chunk-seconds", required=True, type=int)
    chunks.add_argument("--overlap-seconds", type=int, default=0)
    chunks.add_argument("--output", required=True)
    chunks.set_defaults(handler=command_plan_chunks)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except CacheV3Error as error:
        parser.error(str(error))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
