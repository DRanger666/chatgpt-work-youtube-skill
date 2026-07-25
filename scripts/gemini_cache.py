#!/usr/bin/env python3

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def request_fingerprint(request_path: Path) -> str:
    return hashlib.sha256(request_path.read_bytes()).hexdigest()


def start(args) -> int:
    request_path = Path(args.request).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = request_fingerprint(request_path)
    output_path = output_dir / f"{args.video_id}--{fingerprint[:16]}.json"
    if output_path.exists():
        print(json.dumps({"status": "exists", "record": str(output_path), "fingerprint": fingerprint}))
        return 3

    record = {
        "schemaVersion": 1,
        "videoId": args.video_id,
        "videoUrl": args.video_url,
        "requestFingerprint": fingerprint,
        "route": args.route,
        "model": args.model,
        "prompt": args.prompt,
        "status": "pending",
        "attemptStartedAt": utc_now(),
        "retrySameRequest": False,
    }
    if args.clip_start is not None or args.clip_end is not None:
        record["clip"] = {
            "startOffset": f"{args.clip_start}s",
            "endOffset": f"{args.clip_end}s",
        }
    if args.retry_reason:
        record["retryReason"] = args.retry_reason
    write_json(output_path, record)
    print(json.dumps({"status": "created", "record": str(output_path), "fingerprint": fingerprint}))
    return 0


def finish(args) -> int:
    record_path = Path(args.record).resolve()
    record = load_json(record_path)
    if record.get("status") != "pending":
        raise SystemExit("Refusing to finish a record that is not pending")

    record["status"] = args.status
    record["attemptFinishedAt"] = utc_now()
    record["httpStatus"] = args.http_status
    record["retrySameRequest"] = False

    if args.response:
        response = load_json(Path(args.response).resolve())
        if args.status == "succeeded":
            candidate = response["candidates"][0]
            text = candidate["content"]["parts"][0]["text"]
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                result = {"text": text}
            record["modelVersion"] = response.get("modelVersion")
            record["finishReason"] = candidate.get("finishReason")
            record["usageMetadata"] = response.get("usageMetadata")
            record["result"] = result
        else:
            record["error"] = response.get("error", response)
    elif args.error_message:
        record["error"] = {"message": args.error_message}

    if args.conclusion:
        record["conclusion"] = args.conclusion
    write_json(record_path, record)
    print(json.dumps({"status": record["status"], "record": str(record_path)}))
    return 0


def plan(args) -> int:
    if args.duration_seconds <= 0 or args.chunk_seconds <= 0:
        raise SystemExit("Durations must be positive")
    overlap = args.overlap_seconds
    if overlap < 0 or overlap >= args.chunk_seconds:
        raise SystemExit("Overlap must be non-negative and smaller than the chunk")

    intervals = []
    start_offset = 0
    while start_offset < args.duration_seconds:
        end_offset = min(start_offset + args.chunk_seconds, args.duration_seconds)
        intervals.append({"startOffset": start_offset, "endOffset": end_offset})
        if end_offset == args.duration_seconds:
            break
        start_offset = end_offset - overlap
    print(json.dumps(intervals, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create and finish cache records for Gemini video calls")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--video-id", required=True)
    start_parser.add_argument("--video-url", required=True)
    start_parser.add_argument("--request", required=True)
    start_parser.add_argument("--output-dir", required=True)
    start_parser.add_argument("--route", required=True)
    start_parser.add_argument("--model", required=True)
    start_parser.add_argument("--prompt", required=True)
    start_parser.add_argument("--clip-start", type=int)
    start_parser.add_argument("--clip-end", type=int)
    start_parser.add_argument("--retry-reason")
    start_parser.set_defaults(function=start)

    finish_parser = subparsers.add_parser("finish")
    finish_parser.add_argument("--record", required=True)
    finish_parser.add_argument("--status", required=True, choices=("succeeded", "failed"))
    finish_parser.add_argument("--http-status", required=True, type=int)
    finish_parser.add_argument("--response")
    finish_parser.add_argument("--error-message")
    finish_parser.add_argument("--conclusion")
    finish_parser.set_defaults(function=finish)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--duration-seconds", required=True, type=int)
    plan_parser.add_argument("--chunk-seconds", type=int, default=1800)
    plan_parser.add_argument("--overlap-seconds", type=int, default=0)
    plan_parser.set_defaults(function=plan)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.function(args)


if __name__ == "__main__":
    sys.exit(main())
