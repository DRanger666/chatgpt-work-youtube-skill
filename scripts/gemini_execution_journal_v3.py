#!/usr/bin/env python3

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import artifact_cache_v3 as artifact_cache


SCHEMA_VERSION = 1
CACHE_SYSTEM = artifact_cache.CACHE_SYSTEM
RECORD_TYPE = "gemini_execution_journal"
DEFAULT_LEASE_SECONDS = 3600
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
EXECUTION_STATUSES = {"pending", "completed", "failed", "abandoned"}
ATTEMPT_CLASSIFICATIONS = {
    "success",
    "rate_limited",
    "transient",
    "credential_failure",
    "request_failure",
}
ATTEMPT_REQUIRED_FIELDS = {
    "bucket",
    "startedAt",
    "finishedAt",
    "httpStatus",
    "classification",
}
ATTEMPT_OPTIONAL_FIELDS = {
    "errorStatus",
    "cooldownUntil",
    "retryDelaySeconds",
    "backoffSeconds",
}
JOURNAL_FIELDS = {
    "schemaVersion",
    "cacheSystem",
    "recordType",
    "videoId",
    "writer",
    "writerHistory",
    "executions",
    "updatedAt",
}
WRITER_FIELDS = {"ownerId", "acquiredAt", "leaseExpiresAt"}
WRITER_EVENT_REQUIRED_FIELDS = {"eventId", "type", "ownerId", "at"}
WRITER_EVENT_OPTIONAL_FIELDS = {
    "leaseExpiresAt",
    "toOwnerId",
    "reason",
    "evidence",
    "humanConfirmedStopped",
}
EXECUTION_REQUIRED_FIELDS = {
    "executionId",
    "fingerprint",
    "attemptNumber",
    "status",
    "route",
    "model",
    "requestedCoverage",
    "ownerId",
    "startedAt",
    "leaseExpiresAt",
    "routerAttempts",
    "artifactIds",
}
EXECUTION_OPTIONAL_FIELDS = {
    "retryAuthorization",
    "finishedAt",
    "selectedBucket",
    "earliestCooldownUntil",
    "modelVersion",
    "usageMetadata",
    "reconciliation",
}
EXECUTION_SPEC_FIELDS = {
    "video",
    "route",
    "model",
    "requestedCoverage",
    "request",
}
ROUTING_REQUIRED_FIELDS = {
    "schemaVersion",
    "status",
    "selectedBucket",
    "attempts",
}
ROUTING_OPTIONAL_FIELDS = {"earliestCooldownUntil"}


class JournalV3Error(ValueError):
    pass


class WriterOwnedError(JournalV3Error):
    pass


class WriterReconciliationRequired(JournalV3Error):
    pass


class DuplicateExecutionError(JournalV3Error):
    def __init__(self, execution):
        super().__init__(
            "Identical execution is already "
            f"{execution['status']}: {execution['executionId']}"
        )
        self.execution = execution


class RetryAuthorizationRequired(JournalV3Error):
    pass


class TerminalExecutionError(JournalV3Error):
    pass


class PendingExecutionError(JournalV3Error):
    pass


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_timestamp(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise JournalV3Error(f"{label} must be a non-empty timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise JournalV3Error(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise JournalV3Error(f"{label} must include a timezone")
    return parsed.astimezone(timezone.utc)


def isoformat(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def add_seconds(value: str, seconds: int) -> str:
    return isoformat(
        parse_timestamp(value, "lease start") + timedelta(seconds=seconds)
    )


def require_exact_fields(value, required, optional, label) -> None:
    artifact_cache.require_exact_fields(value, required, optional, label)


def validate_owner_id(owner_id: str) -> None:
    if not isinstance(owner_id, str) or not OWNER_PATTERN.fullmatch(owner_id):
        raise JournalV3Error(
            "Owner ID must use 1-128 letters, digits, dots, underscores, "
            "colons, or hyphens"
        )


def validate_lease_seconds(seconds: int) -> None:
    if (
        not isinstance(seconds, int)
        or isinstance(seconds, bool)
        or seconds <= 0
    ):
        raise JournalV3Error("Lease duration must be a positive integer")


def journal_filename(video_source: str) -> str:
    video_id = artifact_cache.normalize_youtube_video_id(video_source)
    return f"{video_id}--gemini-executions.json"


def new_journal(video_source: str, updated_at=None):
    return {
        "schemaVersion": SCHEMA_VERSION,
        "cacheSystem": CACHE_SYSTEM,
        "recordType": RECORD_TYPE,
        "videoId": artifact_cache.normalize_youtube_video_id(video_source),
        "writer": None,
        "writerHistory": [],
        "executions": [],
        "updatedAt": updated_at or utc_now(),
    }


def validate_writer(writer) -> None:
    if writer is None:
        return
    require_exact_fields(writer, WRITER_FIELDS, set(), "writer")
    validate_owner_id(writer["ownerId"])
    acquired = parse_timestamp(writer["acquiredAt"], "writer acquiredAt")
    expires = parse_timestamp(writer["leaseExpiresAt"], "writer leaseExpiresAt")
    if expires <= acquired:
        raise JournalV3Error("Writer lease must expire after acquisition")


def validate_writer_event(event, index: int) -> None:
    require_exact_fields(
        event,
        WRITER_EVENT_REQUIRED_FIELDS,
        WRITER_EVENT_OPTIONAL_FIELDS,
        f"writerHistory[{index}]",
    )
    expected_id = f"writer-event-{index + 1}"
    if event["eventId"] != expected_id:
        raise JournalV3Error(
            f"Writer event IDs must be sequential; expected {expected_id}"
        )
    if event["type"] not in {
        "acquired",
        "renewed",
        "released",
        "handoff",
        "reconciled",
    }:
        raise JournalV3Error(f"Unsupported writer event type: {event['type']}")
    validate_owner_id(event["ownerId"])
    parse_timestamp(event["at"], "writer event timestamp")
    if "leaseExpiresAt" in event:
        parse_timestamp(event["leaseExpiresAt"], "writer event lease expiry")
    if "toOwnerId" in event:
        validate_owner_id(event["toOwnerId"])
    for field in ("reason", "evidence"):
        if field in event and (
            not isinstance(event[field], str) or not event[field].strip()
        ):
            raise JournalV3Error(f"Writer event {field} must be non-empty")
    if "humanConfirmedStopped" in event and not isinstance(
        event["humanConfirmedStopped"], bool
    ):
        raise JournalV3Error("humanConfirmedStopped must be boolean")


def validate_router_attempt(attempt, label: str):
    require_exact_fields(
        attempt,
        ATTEMPT_REQUIRED_FIELDS,
        ATTEMPT_OPTIONAL_FIELDS,
        label,
    )
    if attempt["bucket"] not in {"primary", "fallback"}:
        raise JournalV3Error("Router attempt bucket must be primary or fallback")
    for field in ("startedAt", "finishedAt"):
        parse_timestamp(attempt[field], f"{label} {field}")
    status = attempt["httpStatus"]
    if not isinstance(status, int) or isinstance(status, bool) or status < 0:
        raise JournalV3Error("Router attempt HTTP status must be a non-negative integer")
    if attempt["classification"] not in ATTEMPT_CLASSIFICATIONS:
        raise JournalV3Error(
            f"Unsupported router classification: {attempt['classification']}"
        )
    if "errorStatus" in attempt and (
        not isinstance(attempt["errorStatus"], str)
        or not attempt["errorStatus"]
    ):
        raise JournalV3Error("Router error status must be a non-empty string")
    if "cooldownUntil" in attempt:
        parse_timestamp(attempt["cooldownUntil"], "router cooldownUntil")
    for field in ("retryDelaySeconds", "backoffSeconds"):
        if field in attempt and (
            not isinstance(attempt[field], (int, float))
            or isinstance(attempt[field], bool)
            or attempt[field] < 0
        ):
            raise JournalV3Error(f"Router {field} must be non-negative")
    return dict(attempt)


def validate_retry_authorization(value) -> None:
    require_exact_fields(
        value,
        {"reason", "authorizedAt"},
        set(),
        "retry authorization",
    )
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise JournalV3Error("Retry reason must be a non-empty string")
    parse_timestamp(value["authorizedAt"], "retry authorization timestamp")


def validate_reconciliation(value) -> None:
    require_exact_fields(
        value,
        {"reason", "evidence", "reconciledAt", "reconciledBy", "humanConfirmedStopped"},
        set(),
        "execution reconciliation",
    )
    for field in ("reason", "evidence"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise JournalV3Error(f"Reconciliation {field} must be non-empty")
    parse_timestamp(value["reconciledAt"], "reconciliation timestamp")
    validate_owner_id(value["reconciledBy"])
    if value["humanConfirmedStopped"] is not True:
        raise JournalV3Error(
            "Expired-writer reconciliation requires explicit confirmation"
        )


def validate_execution(execution) -> None:
    require_exact_fields(
        execution,
        EXECUTION_REQUIRED_FIELDS,
        EXECUTION_OPTIONAL_FIELDS,
        "execution",
    )
    artifact_cache.validate_sha256(
        execution["fingerprint"],
        "execution fingerprint",
    )
    attempt_number = execution["attemptNumber"]
    if (
        not isinstance(attempt_number, int)
        or isinstance(attempt_number, bool)
        or attempt_number < 1
    ):
        raise JournalV3Error("Execution attempt number must be positive")
    expected_id = (
        f"exec-{execution['fingerprint'][:16]}-{attempt_number}"
    )
    if execution["executionId"] != expected_id:
        raise JournalV3Error(f"Execution ID must be {expected_id}")
    if execution["status"] not in EXECUTION_STATUSES:
        raise JournalV3Error(
            f"Unsupported execution status: {execution['status']}"
        )
    for field in ("route", "model"):
        if not isinstance(execution[field], str) or not execution[field]:
            raise JournalV3Error(f"Execution {field} must be non-empty")
    execution["requestedCoverage"] = artifact_cache.normalize_intervals(
        execution["requestedCoverage"],
        "execution requested coverage",
    )
    if not execution["requestedCoverage"]:
        raise JournalV3Error("Execution requested coverage cannot be empty")
    validate_owner_id(execution["ownerId"])
    parse_timestamp(execution["startedAt"], "execution startedAt")
    parse_timestamp(execution["leaseExpiresAt"], "execution leaseExpiresAt")
    if not isinstance(execution["routerAttempts"], list):
        raise JournalV3Error("routerAttempts must be an array")
    execution["routerAttempts"] = [
        validate_router_attempt(item, f"routerAttempts[{index}]")
        for index, item in enumerate(execution["routerAttempts"])
    ]
    artifact_ids = execution["artifactIds"]
    if not isinstance(artifact_ids, list):
        raise JournalV3Error("artifactIds must be an array")
    for artifact_id in artifact_ids:
        artifact_cache.validate_sha256(artifact_id, "artifact ID")
    if artifact_ids != sorted(set(artifact_ids)):
        raise JournalV3Error("artifactIds must be sorted and unique")

    if attempt_number == 1 and "retryAuthorization" in execution:
        raise JournalV3Error("First execution attempt cannot have retry authorization")
    if attempt_number > 1:
        if "retryAuthorization" not in execution:
            raise JournalV3Error("Repeated execution requires retry authorization")
        validate_retry_authorization(execution["retryAuthorization"])

    if execution["status"] == "pending":
        forbidden = {
            "finishedAt",
            "selectedBucket",
            "earliestCooldownUntil",
            "modelVersion",
            "usageMetadata",
            "reconciliation",
        }
        present = forbidden & execution.keys()
        if present:
            raise JournalV3Error(
                f"Pending execution has terminal fields: {sorted(present)}"
            )
        if execution["routerAttempts"] or execution["artifactIds"]:
            raise JournalV3Error(
                "Pending execution cannot contain router attempts or artifacts"
            )
    else:
        parse_timestamp(execution.get("finishedAt"), "execution finishedAt")
        if execution["status"] in {"failed", "abandoned"} and artifact_ids:
            raise JournalV3Error(
                f"{execution['status'].capitalize()} execution cannot reference artifacts"
            )
        if execution["status"] == "abandoned":
            if "reconciliation" not in execution:
                raise JournalV3Error("Abandoned execution requires reconciliation")
            validate_reconciliation(execution["reconciliation"])
        if execution["status"] == "completed":
            if (
                not execution["routerAttempts"]
                or execution["routerAttempts"][-1]["classification"] != "success"
            ):
                raise JournalV3Error(
                    "Completed execution must end with a successful router attempt"
                )
            if "selectedBucket" not in execution:
                raise JournalV3Error(
                    "Completed execution must record the selected bucket"
                )
        if execution["status"] == "failed":
            if (
                execution["routerAttempts"]
                and execution["routerAttempts"][-1]["classification"] == "success"
            ):
                raise JournalV3Error(
                    "Failed execution cannot end with a successful router attempt"
                )
            if "selectedBucket" in execution:
                raise JournalV3Error(
                    "Failed execution cannot record a selected bucket"
                )
    if "selectedBucket" in execution and execution["selectedBucket"] not in {
        "primary",
        "fallback",
    }:
        raise JournalV3Error("Selected bucket must be primary or fallback")
    if "earliestCooldownUntil" in execution:
        parse_timestamp(
            execution["earliestCooldownUntil"],
            "execution earliestCooldownUntil",
        )
    if "modelVersion" in execution and (
        not isinstance(execution["modelVersion"], str)
        or not execution["modelVersion"]
    ):
        raise JournalV3Error("Model version must be a non-empty string")
    if "usageMetadata" in execution and not isinstance(
        execution["usageMetadata"], dict
    ):
        raise JournalV3Error("Usage metadata must be an object")
    if "reconciliation" in execution and execution["status"] != "abandoned":
        validate_reconciliation(execution["reconciliation"])


def validate_journal(journal):
    require_exact_fields(journal, JOURNAL_FIELDS, set(), "execution journal")
    if journal["schemaVersion"] != SCHEMA_VERSION:
        raise JournalV3Error("Unsupported execution journal schema version")
    if journal["cacheSystem"] != CACHE_SYSTEM:
        raise JournalV3Error("Execution journal belongs to another cache system")
    if journal["recordType"] != RECORD_TYPE:
        raise JournalV3Error("Unsupported execution journal record type")
    journal["videoId"] = artifact_cache.normalize_youtube_video_id(
        journal["videoId"]
    )
    validate_writer(journal["writer"])
    if not isinstance(journal["writerHistory"], list):
        raise JournalV3Error("writerHistory must be an array")
    for index, event in enumerate(journal["writerHistory"]):
        validate_writer_event(event, index)
    if not isinstance(journal["executions"], list):
        raise JournalV3Error("executions must be an array")
    execution_ids = set()
    numbers_by_fingerprint = {}
    pending = []
    for execution in journal["executions"]:
        validate_execution(execution)
        if execution["executionId"] in execution_ids:
            raise JournalV3Error(
                f"Duplicate execution ID: {execution['executionId']}"
            )
        execution_ids.add(execution["executionId"])
        numbers_by_fingerprint.setdefault(execution["fingerprint"], []).append(
            execution["attemptNumber"]
        )
        if execution["status"] == "pending":
            pending.append(execution)
    for fingerprint, numbers in numbers_by_fingerprint.items():
        expected = list(range(1, len(numbers) + 1))
        if sorted(numbers) != expected:
            raise JournalV3Error(
                f"Execution attempt numbers are not contiguous for {fingerprint}"
            )
    if len(pending) > 1:
        raise JournalV3Error("Only one Gemini execution may be pending per video")
    if pending:
        writer = journal["writer"]
        if writer is None or writer["ownerId"] != pending[0]["ownerId"]:
            raise JournalV3Error("Pending execution must belong to current writer")
    parse_timestamp(journal["updatedAt"], "journal updatedAt")
    return journal


def writer_event(journal, event_type: str, owner_id: str, at: str, **fields):
    event = {
        "eventId": f"writer-event-{len(journal['writerHistory']) + 1}",
        "type": event_type,
        "ownerId": owner_id,
        "at": at,
        **fields,
    }
    validate_writer_event(event, len(journal["writerHistory"]))
    journal["writerHistory"].append(event)
    return event


def writer_is_expired(writer, at: str) -> bool:
    return parse_timestamp(at, "current time") >= parse_timestamp(
        writer["leaseExpiresAt"],
        "writer lease expiry",
    )


def require_current_writer(journal, owner_id: str, at: str):
    validate_journal(journal)
    validate_owner_id(owner_id)
    writer = journal["writer"]
    if writer is None:
        raise WriterOwnedError("No write-capable session owns this video")
    if writer["ownerId"] != owner_id:
        if writer_is_expired(writer, at):
            raise WriterReconciliationRequired(
                "Expired writer must be reconciled before another session writes"
            )
        raise WriterOwnedError(
            f"Video is owned by another session: {writer['ownerId']}"
        )
    return writer


def acquire_writer(journal, owner_id: str, lease_seconds=DEFAULT_LEASE_SECONDS, at=None):
    validate_journal(journal)
    validate_owner_id(owner_id)
    validate_lease_seconds(lease_seconds)
    at = at or utc_now()
    parse_timestamp(at, "writer acquisition time")
    current = journal["writer"]
    if current is not None:
        if current["ownerId"] == owner_id:
            raise WriterOwnedError("Session already owns this video; renew its lease")
        if writer_is_expired(current, at):
            raise WriterReconciliationRequired(
                "Expired writer must be reconciled before takeover"
            )
        raise WriterOwnedError(
            f"Video is owned by another session: {current['ownerId']}"
        )
    expires_at = add_seconds(at, lease_seconds)
    journal["writer"] = {
        "ownerId": owner_id,
        "acquiredAt": at,
        "leaseExpiresAt": expires_at,
    }
    writer_event(
        journal,
        "acquired",
        owner_id,
        at,
        leaseExpiresAt=expires_at,
    )
    journal["updatedAt"] = at
    validate_journal(journal)
    return journal["writer"]


def renew_writer(journal, owner_id: str, lease_seconds=DEFAULT_LEASE_SECONDS, at=None):
    validate_lease_seconds(lease_seconds)
    at = at or utc_now()
    writer = require_current_writer(journal, owner_id, at)
    expires_at = add_seconds(at, lease_seconds)
    writer["leaseExpiresAt"] = expires_at
    for execution in journal["executions"]:
        if execution["status"] == "pending" and execution["ownerId"] == owner_id:
            execution["leaseExpiresAt"] = expires_at
    writer_event(
        journal,
        "renewed",
        owner_id,
        at,
        leaseExpiresAt=expires_at,
    )
    journal["updatedAt"] = at
    validate_journal(journal)
    return writer


def release_writer(journal, owner_id: str, reason: str, handoff_to=None, at=None):
    at = at or utc_now()
    require_current_writer(journal, owner_id, at)
    if not isinstance(reason, str) or not reason.strip():
        raise JournalV3Error("Writer release reason must be non-empty")
    if any(item["status"] == "pending" for item in journal["executions"]):
        raise PendingExecutionError(
            "Cannot release writer while a Gemini execution is pending"
        )
    fields = {"reason": reason.strip()}
    event_type = "released"
    if handoff_to is not None:
        validate_owner_id(handoff_to)
        if handoff_to == owner_id:
            raise JournalV3Error("Writer cannot hand off to itself")
        event_type = "handoff"
        fields["toOwnerId"] = handoff_to
    writer_event(journal, event_type, owner_id, at, **fields)
    journal["writer"] = None
    journal["updatedAt"] = at
    validate_journal(journal)


def normalize_request_video_uris(value):
    if isinstance(value, list):
        return [normalize_request_video_uris(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {}
    for key, item in value.items():
        if key == "fileUri" and isinstance(item, str):
            try:
                video_id = artifact_cache.normalize_youtube_video_id(item)
            except artifact_cache.CacheV3Error:
                normalized[key] = item
            else:
                normalized[key] = (
                    f"https://www.youtube.com/watch?v={video_id}"
                )
        else:
            normalized[key] = normalize_request_video_uris(item)
    return normalized


def normalize_execution_spec(spec):
    require_exact_fields(
        spec,
        EXECUTION_SPEC_FIELDS,
        set(),
        "execution spec",
    )
    normalized = {
        "videoId": artifact_cache.normalize_youtube_video_id(spec["video"]),
        "route": spec["route"],
        "model": spec["model"],
        "requestedCoverage": artifact_cache.normalize_intervals(
            spec["requestedCoverage"],
            "execution requested coverage",
        ),
        "request": normalize_request_video_uris(spec["request"]),
    }
    for field in ("route", "model"):
        if not isinstance(normalized[field], str) or not normalized[field]:
            raise JournalV3Error(f"Execution {field} must be non-empty")
    if not normalized["requestedCoverage"]:
        raise JournalV3Error("Execution requested coverage cannot be empty")
    if not isinstance(normalized["request"], dict):
        raise JournalV3Error("Execution request must be a JSON object")
    return normalized


def execution_fingerprint(spec) -> str:
    normalized = normalize_execution_spec(dict(spec))
    return artifact_cache.sha256_hex(
        artifact_cache.canonical_json_bytes(normalized)
    )


def terminal_failure(execution) -> bool:
    return any(
        item["classification"] == "request_failure"
        for item in execution["routerAttempts"]
    )


def start_execution(
    journal,
    spec,
    owner_id: str,
    retry_reason=None,
    started_at=None,
):
    started_at = started_at or utc_now()
    writer = require_current_writer(journal, owner_id, started_at)
    if writer_is_expired(writer, started_at):
        raise WriterReconciliationRequired(
            "Writer lease expired; renew or reconcile before execution"
        )
    normalized = normalize_execution_spec(dict(spec))
    if journal["videoId"] != normalized["videoId"]:
        raise JournalV3Error("Execution and journal video IDs differ")
    pending = next(
        (
            item
            for item in journal["executions"]
            if item["status"] == "pending"
        ),
        None,
    )
    if pending is not None:
        raise PendingExecutionError(
            f"Another Gemini execution is pending: {pending['executionId']}"
        )
    fingerprint = artifact_cache.sha256_hex(
        artifact_cache.canonical_json_bytes(normalized)
    )
    prior = [
        item
        for item in journal["executions"]
        if item["fingerprint"] == fingerprint
    ]
    for execution in prior:
        if execution["status"] in {"pending", "completed"}:
            raise DuplicateExecutionError(execution)
    if prior:
        latest = max(prior, key=lambda item: item["attemptNumber"])
        if terminal_failure(latest):
            raise TerminalExecutionError(
                "Terminal Gemini request failure cannot be retried unchanged"
            )
        if not isinstance(retry_reason, str) or not retry_reason.strip():
            raise RetryAuthorizationRequired(
                "Identical failed or abandoned execution requires a retry reason"
            )
    elif retry_reason is not None:
        raise JournalV3Error("First execution cannot supply a retry reason")

    attempt_number = len(prior) + 1
    execution = {
        "executionId": f"exec-{fingerprint[:16]}-{attempt_number}",
        "fingerprint": fingerprint,
        "attemptNumber": attempt_number,
        "status": "pending",
        "route": normalized["route"],
        "model": normalized["model"],
        "requestedCoverage": normalized["requestedCoverage"],
        "ownerId": owner_id,
        "startedAt": started_at,
        "leaseExpiresAt": writer["leaseExpiresAt"],
        "routerAttempts": [],
        "artifactIds": [],
    }
    if prior:
        execution["retryAuthorization"] = {
            "reason": retry_reason.strip(),
            "authorizedAt": started_at,
        }
    validate_execution(execution)
    journal["executions"].append(execution)
    journal["updatedAt"] = started_at
    validate_journal(journal)
    return execution


def sanitize_routing_metadata(routing_metadata):
    require_exact_fields(
        routing_metadata,
        ROUTING_REQUIRED_FIELDS,
        ROUTING_OPTIONAL_FIELDS,
        "routing metadata",
    )
    if routing_metadata["schemaVersion"] != 1:
        raise JournalV3Error("Unsupported routing metadata schema version")
    if routing_metadata["status"] not in {"succeeded", "failed"}:
        raise JournalV3Error("Routing metadata must be terminal")
    selected = routing_metadata["selectedBucket"]
    if selected not in {None, "primary", "fallback"}:
        raise JournalV3Error("Unsupported selected bucket")
    attempts = routing_metadata["attempts"]
    if not isinstance(attempts, list):
        raise JournalV3Error("Routing attempts must be an array")
    safe = {
        "status": routing_metadata["status"],
        "selectedBucket": selected,
        "attempts": [
            validate_router_attempt(item, f"routing attempts[{index}]")
            for index, item in enumerate(attempts)
        ],
    }
    if "earliestCooldownUntil" in routing_metadata:
        value = routing_metadata["earliestCooldownUntil"]
        if value is not None:
            parse_timestamp(value, "routing earliestCooldownUntil")
            safe["earliestCooldownUntil"] = value
    return safe


def find_execution(journal, execution_id: str):
    execution = next(
        (
            item
            for item in journal["executions"]
            if item["executionId"] == execution_id
        ),
        None,
    )
    if execution is None:
        raise JournalV3Error(f"Unknown execution ID: {execution_id}")
    return execution


def finish_execution(
    journal,
    execution_id: str,
    owner_id: str,
    status: str,
    routing_metadata,
    artifact_ids=None,
    finished_at=None,
    result_metadata=None,
):
    finished_at = finished_at or utc_now()
    require_current_writer(journal, owner_id, finished_at)
    if status not in {"completed", "failed"}:
        raise JournalV3Error("Execution can finish only as completed or failed")
    execution = find_execution(journal, execution_id)
    if execution["status"] != "pending":
        raise JournalV3Error("Only a pending execution can be finished")
    if execution["ownerId"] != owner_id:
        raise WriterOwnedError("Pending execution belongs to another owner")
    routing = sanitize_routing_metadata(dict(routing_metadata))
    expected_routing_status = "succeeded" if status == "completed" else "failed"
    if routing["status"] != expected_routing_status:
        raise JournalV3Error("Execution status conflicts with routing metadata")
    artifact_ids = sorted(set(artifact_ids or []))
    for artifact_id in artifact_ids:
        artifact_cache.validate_sha256(artifact_id, "artifact ID")
    if status == "failed" and artifact_ids:
        raise JournalV3Error("Failed execution cannot reference artifacts")

    execution["status"] = status
    execution["finishedAt"] = finished_at
    execution["routerAttempts"] = routing["attempts"]
    execution["artifactIds"] = artifact_ids
    if routing["selectedBucket"] is not None:
        execution["selectedBucket"] = routing["selectedBucket"]
    if "earliestCooldownUntil" in routing:
        execution["earliestCooldownUntil"] = routing["earliestCooldownUntil"]
    if result_metadata is not None:
        require_exact_fields(
            result_metadata,
            set(),
            {"modelVersion", "usageMetadata"},
            "result metadata",
        )
        if "modelVersion" in result_metadata:
            execution["modelVersion"] = result_metadata["modelVersion"]
        if "usageMetadata" in result_metadata:
            execution["usageMetadata"] = result_metadata["usageMetadata"]
    journal["updatedAt"] = finished_at
    validate_journal(journal)
    return execution


def reconcile_expired_writer(
    journal,
    reconciled_by: str,
    outcome: str,
    reason: str,
    evidence: str,
    human_confirmed_stopped: bool,
    at=None,
    routing_metadata=None,
    artifact_ids=None,
):
    validate_journal(journal)
    validate_owner_id(reconciled_by)
    at = at or utc_now()
    writer = journal["writer"]
    if writer is None:
        raise JournalV3Error("No writer exists to reconcile")
    if writer["ownerId"] == reconciled_by:
        raise JournalV3Error("Current owner should renew or release, not reconcile itself")
    if not writer_is_expired(writer, at):
        raise WriterOwnedError("Active writer cannot be reconciled")
    if human_confirmed_stopped is not True:
        raise WriterReconciliationRequired(
            "Human confirmation is required before expired-writer takeover"
        )
    for field, value in (("reason", reason), ("evidence", evidence)):
        if not isinstance(value, str) or not value.strip():
            raise JournalV3Error(f"Reconciliation {field} must be non-empty")
    if outcome not in {"completed", "failed", "abandoned"}:
        raise JournalV3Error("Unsupported reconciliation outcome")

    pending = next(
        (
            item
            for item in journal["executions"]
            if item["status"] == "pending"
        ),
        None,
    )
    if pending is not None:
        if outcome == "abandoned":
            pending["status"] = "abandoned"
            pending["finishedAt"] = at
            pending["artifactIds"] = []
            pending["reconciliation"] = {
                "reason": reason.strip(),
                "evidence": evidence.strip(),
                "reconciledAt": at,
                "reconciledBy": reconciled_by,
                "humanConfirmedStopped": True,
            }
        else:
            if routing_metadata is None:
                raise JournalV3Error(
                    "Completed or failed reconciliation requires routing metadata"
                )
            routing = sanitize_routing_metadata(dict(routing_metadata))
            expected = "succeeded" if outcome == "completed" else "failed"
            if routing["status"] != expected:
                raise JournalV3Error(
                    "Reconciliation outcome conflicts with routing metadata"
                )
            pending["status"] = outcome
            pending["finishedAt"] = at
            pending["routerAttempts"] = routing["attempts"]
            pending["artifactIds"] = sorted(set(artifact_ids or []))
            if outcome == "failed" and pending["artifactIds"]:
                raise JournalV3Error(
                    "Failed reconciliation cannot reference artifacts"
                )
            for artifact_id in pending["artifactIds"]:
                artifact_cache.validate_sha256(artifact_id, "artifact ID")
            if routing["selectedBucket"] is not None:
                pending["selectedBucket"] = routing["selectedBucket"]
            if "earliestCooldownUntil" in routing:
                pending["earliestCooldownUntil"] = routing[
                    "earliestCooldownUntil"
                ]
            pending["reconciliation"] = {
                "reason": reason.strip(),
                "evidence": evidence.strip(),
                "reconciledAt": at,
                "reconciledBy": reconciled_by,
                "humanConfirmedStopped": True,
            }
    elif outcome != "abandoned":
        raise JournalV3Error(
            "No pending execution exists for completed or failed reconciliation"
        )

    writer_event(
        journal,
        "reconciled",
        writer["ownerId"],
        at,
        toOwnerId=reconciled_by,
        reason=reason.strip(),
        evidence=evidence.strip(),
        humanConfirmedStopped=True,
    )
    journal["writer"] = None
    journal["updatedAt"] = at
    validate_journal(journal)


def command_locate(args) -> int:
    video_id = artifact_cache.normalize_youtube_video_id(args.video)
    print(
        json.dumps(
            {
                "cacheSystem": CACHE_SYSTEM,
                "namespace": artifact_cache.DRIVE_NAMESPACE,
                "videoId": video_id,
                "journalFileName": journal_filename(video_id),
            },
            sort_keys=True,
        )
    )
    return 0


def command_init_journal(args) -> int:
    if not args.confirmed_no_journal:
        raise JournalV3Error(
            "Refusing journal initialization until exact-name lookup confirms "
            "that no native execution journal exists"
        )
    artifact_cache.write_json(
        Path(args.output),
        new_journal(args.video, updated_at=args.updated_at),
    )
    print(Path(args.output).resolve())
    return 0


def mutate_journal(args, operation):
    journal = artifact_cache.load_json(Path(args.journal))
    result = operation(journal)
    artifact_cache.write_json(Path(args.output), journal)
    return result


def command_acquire_writer(args) -> int:
    writer = mutate_journal(
        args,
        lambda journal: acquire_writer(
            journal,
            args.owner_id,
            lease_seconds=args.lease_seconds,
            at=args.at,
        ),
    )
    print(json.dumps({"status": "acquired", **writer}, sort_keys=True))
    return 0


def command_renew_writer(args) -> int:
    writer = mutate_journal(
        args,
        lambda journal: renew_writer(
            journal,
            args.owner_id,
            lease_seconds=args.lease_seconds,
            at=args.at,
        ),
    )
    print(json.dumps({"status": "renewed", **writer}, sort_keys=True))
    return 0


def command_release_writer(args) -> int:
    mutate_journal(
        args,
        lambda journal: release_writer(
            journal,
            args.owner_id,
            args.reason,
            handoff_to=args.handoff_to,
            at=args.at,
        ),
    )
    print(json.dumps({"status": "released"}, sort_keys=True))
    return 0


def command_start_execution(args) -> int:
    spec = artifact_cache.load_json(Path(args.execution_spec))
    execution = mutate_journal(
        args,
        lambda journal: start_execution(
            journal,
            spec,
            args.owner_id,
            retry_reason=args.retry_reason,
            started_at=args.started_at,
        ),
    )
    print(
        json.dumps(
            {
                "status": "started",
                "executionId": execution["executionId"],
                "fingerprint": execution["fingerprint"],
                "attemptNumber": execution["attemptNumber"],
            },
            sort_keys=True,
        )
    )
    return 0


def command_finish_execution(args) -> int:
    routing = artifact_cache.load_json(Path(args.routing_metadata))
    result_metadata = (
        artifact_cache.load_json(Path(args.result_metadata))
        if args.result_metadata
        else None
    )
    execution = mutate_journal(
        args,
        lambda journal: finish_execution(
            journal,
            args.execution_id,
            args.owner_id,
            args.status,
            routing,
            artifact_ids=args.artifact_id,
            finished_at=args.finished_at,
            result_metadata=result_metadata,
        ),
    )
    print(
        json.dumps(
            {
                "status": execution["status"],
                "executionId": execution["executionId"],
                "networkAttempts": len(execution["routerAttempts"]),
            },
            sort_keys=True,
        )
    )
    return 0


def command_reconcile_writer(args) -> int:
    routing = (
        artifact_cache.load_json(Path(args.routing_metadata))
        if args.routing_metadata
        else None
    )
    mutate_journal(
        args,
        lambda journal: reconcile_expired_writer(
            journal,
            args.owner_id,
            args.outcome,
            args.reason,
            args.evidence,
            args.human_confirmed_stopped,
            at=args.at,
            routing_metadata=routing,
            artifact_ids=args.artifact_id,
        ),
    )
    print(json.dumps({"status": "reconciled"}, sort_keys=True))
    return 0


def add_mutation_paths(parser):
    parser.add_argument("--journal", required=True)
    parser.add_argument("--output", required=True)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Manage native cache-v3 Gemini execution journals"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    locate = subparsers.add_parser("locate")
    locate.add_argument("--video", required=True)
    locate.set_defaults(handler=command_locate)

    initialize = subparsers.add_parser("init-journal")
    initialize.add_argument("--video", required=True)
    initialize.add_argument("--output", required=True)
    initialize.add_argument("--updated-at")
    initialize.add_argument("--confirmed-no-journal", action="store_true")
    initialize.set_defaults(handler=command_init_journal)

    acquire = subparsers.add_parser("acquire-writer")
    add_mutation_paths(acquire)
    acquire.add_argument("--owner-id", required=True)
    acquire.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    acquire.add_argument("--at")
    acquire.set_defaults(handler=command_acquire_writer)

    renew = subparsers.add_parser("renew-writer")
    add_mutation_paths(renew)
    renew.add_argument("--owner-id", required=True)
    renew.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    renew.add_argument("--at")
    renew.set_defaults(handler=command_renew_writer)

    release = subparsers.add_parser("release-writer")
    add_mutation_paths(release)
    release.add_argument("--owner-id", required=True)
    release.add_argument("--reason", required=True)
    release.add_argument("--handoff-to")
    release.add_argument("--at")
    release.set_defaults(handler=command_release_writer)

    start = subparsers.add_parser("start-execution")
    add_mutation_paths(start)
    start.add_argument("--execution-spec", required=True)
    start.add_argument("--owner-id", required=True)
    start.add_argument("--retry-reason")
    start.add_argument("--started-at")
    start.set_defaults(handler=command_start_execution)

    finish = subparsers.add_parser("finish-execution")
    add_mutation_paths(finish)
    finish.add_argument("--execution-id", required=True)
    finish.add_argument("--owner-id", required=True)
    finish.add_argument("--status", choices=("completed", "failed"), required=True)
    finish.add_argument("--routing-metadata", required=True)
    finish.add_argument("--artifact-id", action="append", default=[])
    finish.add_argument("--result-metadata")
    finish.add_argument("--finished-at")
    finish.set_defaults(handler=command_finish_execution)

    reconcile = subparsers.add_parser("reconcile-writer")
    add_mutation_paths(reconcile)
    reconcile.add_argument("--owner-id", required=True)
    reconcile.add_argument(
        "--outcome",
        choices=("completed", "failed", "abandoned"),
        required=True,
    )
    reconcile.add_argument("--reason", required=True)
    reconcile.add_argument("--evidence", required=True)
    reconcile.add_argument("--human-confirmed-stopped", action="store_true")
    reconcile.add_argument("--routing-metadata")
    reconcile.add_argument("--artifact-id", action="append", default=[])
    reconcile.add_argument("--at")
    reconcile.set_defaults(handler=command_reconcile_writer)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = args.handler(args)
    except (JournalV3Error, artifact_cache.CacheV3Error) as error:
        parser.error(str(error))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
