#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


TRANSCRIPT_PROMPT = (
    "TRANSCRIPT-ONLY MODE. Transcribe every audible human vocal passage containing "
    "linguistic content in the supplied interval. Preserve the words and repetitions "
    "as heard; do not summarize, paraphrase, translate, romanize, interpret, or "
    "correct them. Use the original language and its native script. Separate sung "
    "from spoken passages. Do not describe visuals, music, mood, story, themes, "
    "people, or actions. Do not add commentary. Every timestamp must be a string in "
    "fixed MM:SS.mmm format relative to the complete source video; for example, "
    "5 minutes 26.5 seconds must be written as 05:26.500, never as 526.5 or as "
    "elapsed seconds. Cover the complete supplied interval. Mark unclear words as "
    "uncertain rather than inventing them; use [inaudible] only when no reliable "
    "wording can be recovered. Return only the specified JSON structure."
)

TIMESTAMP_SCHEMA = {
    "type": "string",
    "pattern": r"^[0-9]{2}:[0-5][0-9]\.[0-9]{3}$",
}

TRANSCRIPT_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "clip_start_timestamp": TIMESTAMP_SCHEMA,
        "clip_end_timestamp": TIMESTAMP_SCHEMA,
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "start_timestamp": TIMESTAMP_SCHEMA,
                    "end_timestamp": TIMESTAMP_SCHEMA,
                    "vocal_type": {
                        "type": "string",
                        "enum": ["sung", "spoken", "spoken_over_music", "other"],
                    },
                    "language": {"type": "string"},
                    "text": {"type": "string"},
                    "audibility": {
                        "type": "string",
                        "enum": ["clear", "uncertain", "inaudible"],
                    },
                },
                "required": [
                    "start_timestamp",
                    "end_timestamp",
                    "vocal_type",
                    "language",
                    "text",
                    "audibility",
                ],
            },
        },
        "completed_through_timestamp": TIMESTAMP_SCHEMA,
        "transcription_complete": {"type": "boolean"},
        "truncation_detected": {"type": "boolean"},
    },
    "required": [
        "clip_start_timestamp",
        "clip_end_timestamp",
        "segments",
        "completed_through_timestamp",
        "transcription_complete",
        "truncation_detected",
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a timestamp-clipped Gemini YouTube request")
    parser.add_argument("--video-url", required=True)
    parser.add_argument("--start-seconds", required=True, type=int)
    parser.add_argument("--end-seconds", required=True, type=int)
    parser.add_argument("--prompt")
    parser.add_argument("--transcript-only", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-output-tokens", type=int)
    args = parser.parse_args()

    if args.start_seconds < 0 or args.end_seconds <= args.start_seconds:
        raise SystemExit("Require 0 <= start-seconds < end-seconds")
    if args.transcript_only and args.prompt:
        raise SystemExit("--transcript-only cannot be combined with --prompt")
    if not args.transcript_only and not args.prompt:
        raise SystemExit("Require --prompt unless --transcript-only is selected")
    if args.max_output_tokens is not None and args.max_output_tokens <= 0:
        raise SystemExit("--max-output-tokens must be positive")

    prompt = TRANSCRIPT_PROMPT if args.transcript_only else args.prompt
    max_output_tokens = args.max_output_tokens
    if max_output_tokens is None:
        max_output_tokens = 8192 if args.transcript_only else 2048

    request = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "fileData": {
                            "fileUri": args.video_url,
                            "mimeType": "video/*",
                        },
                        "videoMetadata": {
                            "startOffset": f"{args.start_seconds}s",
                            "endOffset": f"{args.end_seconds}s",
                        },
                    },
                    {"text": prompt},
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": max_output_tokens,
        },
    }
    if args.transcript_only:
        request["generationConfig"]["responseJsonSchema"] = TRANSCRIPT_RESPONSE_SCHEMA

    output_path = Path(args.output).resolve()
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(request, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(output_path)


if __name__ == "__main__":
    main()
