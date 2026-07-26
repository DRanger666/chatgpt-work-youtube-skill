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
COMPLETION_STATES = {"complete", "partial", "truncated"}
EXECUTION_STATUSES = {"pending", "completed", "failed"}
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_FIELDS = {
    "schemaVersion",
    "cacheSystem",
    "videoId",
    "artifacts",
    "executions",
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
    "requestedCoverage",
    "validCoverage",
    "completionState",
    "gaps",
    "executionProvenance",
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
    "requestedCoverage",
    "validCoverage",
    "completionState",
    "gaps",
    "integrity",
    "executionIds",
}
MANIFEST_ARTIFACT_OPTIONAL_FIELDS = {"taskDescription"}
EXECUTION_FIELDS = {
    "executionId",
    "fingerprint",
    "status",
    "route",
    "model",
    "requestedCoverage",
    "startedAt",
}
EXECUTION_OPTIONAL_FIELDS = {"finishedAt", "artifactIds"}
PROVENANCE_FIELDS = {
    "executionId",
    "fingerprint",
    "route",
    "model",
    "startedAt",
    "finishedAt",
}


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


def validate_provenance(provenance) -> None:
    if not isinstance(provenance, list) or not provenance:
        raise CacheV3Error("executionProvenance must be a non-empty array")
    seen = set()
    for index, item in enumerate(provenance):
        require_exact_fields(
            item,
            PROVENANCE_FIELDS,
            set(),
            f"executionProvenance[{index}]",
        )
        execution_id = item["executionId"]
        if not isinstance(execution_id, str) or not execution_id:
            raise CacheV3Error("Execution ID must be a non-empty string")
        if execution_id in seen:
            raise CacheV3Error(f"Duplicate execution ID: {execution_id}")
        seen.add(execution_id)
        validate_sha256(item["fingerprint"], "execution fingerprint")
        for field in ("route", "model"):
            if not isinstance(item[field], str) or not item[field]:
                raise CacheV3Error(f"Execution {field} must be a non-empty string")
        validate_timestamp(item["startedAt"], "startedAt")
        validate_timestamp(item["finishedAt"], "finishedAt")


def validate_execution_record(execution) -> None:
    require_exact_fields(
        execution,
        EXECUTION_FIELDS,
        EXECUTION_OPTIONAL_FIELDS,
        "manifest execution",
    )
    if not isinstance(execution["executionId"], str) or not execution["executionId"]:
        raise CacheV3Error("Execution ID must be a non-empty string")
    validate_sha256(execution["fingerprint"], "execution fingerprint")
    if execution["status"] not in EXECUTION_STATUSES:
        raise CacheV3Error(f"Unsupported execution status: {execution['status']}")
    for field in ("route", "model"):
        if not isinstance(execution[field], str) or not execution[field]:
            raise CacheV3Error(f"Execution {field} must be a non-empty string")
    execution["requestedCoverage"] = normalize_intervals(
        execution["requestedCoverage"],
        "execution requested coverage",
    )
    validate_timestamp(execution["startedAt"], "startedAt")
    if execution["status"] == "pending":
        if "finishedAt" in execution or "artifactIds" in execution:
            raise CacheV3Error("Pending executions cannot be finished")
    else:
        validate_timestamp(execution.get("finishedAt"), "finishedAt")
        artifact_ids = execution.get("artifactIds", [])
        if not isinstance(artifact_ids, list) or not all(
            isinstance(item, str) and SHA256_PATTERN.fullmatch(item)
            for item in artifact_ids
        ):
            raise CacheV3Error("artifactIds must contain artifact SHA-256 IDs")


def new_manifest(video_source: str, updated_at=None):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": normalize_youtube_video_id(video_source),
        "artifacts": [],
        "executions": [],
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
    if not isinstance(manifest["executions"], list):
        raise CacheV3Error("Manifest executions must be an array")

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

    execution_ids = set()
    for execution in manifest["executions"]:
        validate_execution_record(execution)
        if execution["executionId"] in execution_ids:
            raise CacheV3Error(
                f"Duplicate execution ID: {execution['executionId']}"
            )
        execution_ids.add(execution["executionId"])
    return manifest


def validate_coverage_state(value) -> None:
    requested = normalize_intervals(
        value["requestedCoverage"],
        "requested coverage",
    )
    valid = normalize_intervals(value["validCoverage"], "valid coverage")
    outside = subtract_intervals(valid, requested)
    if outside:
        raise CacheV3Error("Valid coverage must stay inside requested coverage")
    gaps = subtract_intervals(requested, valid)
    if value["gaps"] != gaps:
        raise CacheV3Error("Stored gaps do not match requested minus valid coverage")
    state = value["completionState"]
    if state not in COMPLETION_STATES:
        raise CacheV3Error(f"Unsupported completion state: {state}")
    if state == "complete" and gaps:
        raise CacheV3Error("Complete artifacts cannot contain coverage gaps")
    if state in {"partial", "truncated"} and not gaps:
        raise CacheV3Error(f"{state.capitalize()} artifacts must contain a gap")
    value["requestedCoverage"] = requested
    value["validCoverage"] = valid


def build_artifact(metadata, content, provenance):
    required = {
        "video",
        "kind",
        "contract",
        "timestampBasis",
        "languagePolicy",
        "requestedCoverage",
        "validCoverage",
        "completionState",
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
    validate_provenance(provenance)

    requested = normalize_intervals(
        metadata["requestedCoverage"],
        "requested coverage",
    )
    valid = normalize_intervals(metadata["validCoverage"], "valid coverage")
    gaps = subtract_intervals(requested, valid)
    state = metadata["completionState"]
    if state not in COMPLETION_STATES:
        raise CacheV3Error(f"Unsupported completion state: {state}")
    if state == "complete" and gaps:
        raise CacheV3Error("Complete artifacts cannot contain coverage gaps")
    if state in {"partial", "truncated"} and not gaps:
        raise CacheV3Error(f"{state.capitalize()} artifacts must contain a gap")

    artifact = {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "videoId": normalize_youtube_video_id(metadata["video"]),
        "kind": metadata["kind"],
        "contract": metadata["contract"],
        "timestampBasis": metadata["timestampBasis"],
        "languagePolicy": metadata["languagePolicy"],
        "requestedCoverage": requested,
        "validCoverage": valid,
        "completionState": state,
        "gaps": gaps,
        "executionProvenance": provenance,
        "content": content,
    }
    task_description = metadata.get("taskDescription")
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
    validate_coverage_state(artifact)
    validate_provenance(artifact["executionProvenance"])
    if "taskDescription" in artifact and (
        not isinstance(artifact["taskDescription"], str)
        or not artifact["taskDescription"].strip()
    ):
        raise CacheV3Error("Task description must be a non-empty string")
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
        "requestedCoverage": artifact["requestedCoverage"],
        "validCoverage": artifact["validCoverage"],
        "completionState": artifact["completionState"],
        "gaps": artifact["gaps"],
        "integrity": {
            "algorithm": "sha256",
            "value": sha256_hex(path.read_bytes()),
        },
        "executionIds": [
            item["executionId"] for item in artifact["executionProvenance"]
        ],
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
    validate_coverage_state(entry)
    require_exact_fields(
        entry["integrity"],
        {"algorithm", "value"},
        set(),
        "artifact integrity",
    )
    if entry["integrity"]["algorithm"] != "sha256":
        raise CacheV3Error("Native artifact integrity must use SHA-256")
    validate_sha256(entry["integrity"]["value"], "artifact integrity")
    execution_ids = entry["executionIds"]
    if not isinstance(execution_ids, list) or not execution_ids or not all(
        isinstance(item, str) and item for item in execution_ids
    ):
        raise CacheV3Error("executionIds must be a non-empty string array")
    if len(set(execution_ids)) != len(execution_ids):
        raise CacheV3Error("executionIds cannot contain duplicates")
    if "taskDescription" in entry and (
        not isinstance(entry["taskDescription"], str)
        or not entry["taskDescription"].strip()
    ):
        raise CacheV3Error("Task description must be a non-empty string")


def execution_from_provenance(item, requested_coverage, artifact_id):
    return {
        "executionId": item["executionId"],
        "fingerprint": item["fingerprint"],
        "status": "completed",
        "route": item["route"],
        "model": item["model"],
        "requestedCoverage": normalize_intervals(
            requested_coverage,
            "execution requested coverage",
        ),
        "startedAt": item["startedAt"],
        "finishedAt": item["finishedAt"],
        "artifactIds": [artifact_id],
    }


def merge_artifact_provenance(manifest, artifact) -> None:
    by_id = {
        execution["executionId"]: execution for execution in manifest["executions"]
    }
    for item in artifact["executionProvenance"]:
        execution_id = item["executionId"]
        recovered = execution_from_provenance(
            item,
            artifact["requestedCoverage"],
            artifact["artifactId"],
        )
        existing = by_id.get(execution_id)
        if existing is None:
            manifest["executions"].append(recovered)
            by_id[execution_id] = recovered
            continue
        if (
            existing["fingerprint"] != recovered["fingerprint"]
            or existing["route"] != recovered["route"]
            or existing["model"] != recovered["model"]
            or existing["status"] != "completed"
        ):
            raise CacheV3Error(
                f"Execution provenance conflicts for {execution_id}"
            )
        existing["requestedCoverage"] = normalize_intervals(
            existing["requestedCoverage"] + recovered["requestedCoverage"],
            "execution requested coverage",
        )
        existing.setdefault("artifactIds", [])
        if artifact["artifactId"] not in existing["artifactIds"]:
            existing["artifactIds"].append(artifact["artifactId"])
            existing["artifactIds"].sort()


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

    merge_artifact_provenance(manifest, artifact)
    manifest["artifacts"].append(entry)
    manifest["artifacts"].sort(key=lambda item: item["artifactId"])
    manifest["executions"].sort(key=lambda item: item["executionId"])
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
    manifest = new_manifest(args.video, updated_at=args.updated_at)
    write_json(Path(args.output), manifest)
    print(Path(args.output).resolve())
    return 0


def command_create_artifact(args) -> int:
    metadata = load_json(Path(args.metadata))
    content = load_json(Path(args.content))
    provenance = load_json(Path(args.provenance))
    artifact = build_artifact(metadata, content, provenance)
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
    initialize.set_defaults(handler=command_init_manifest)

    create = subparsers.add_parser("create-artifact")
    create.add_argument("--metadata", required=True)
    create.add_argument("--content", required=True)
    create.add_argument("--provenance", required=True)
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
