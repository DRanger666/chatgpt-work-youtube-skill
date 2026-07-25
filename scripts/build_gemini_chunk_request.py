#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a timestamp-clipped Gemini YouTube request")
    parser.add_argument("--video-url", required=True)
    parser.add_argument("--start-seconds", required=True, type=int)
    parser.add_argument("--end-seconds", required=True, type=int)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    args = parser.parse_args()

    if args.start_seconds < 0 or args.end_seconds <= args.start_seconds:
        raise SystemExit("Require 0 <= start-seconds < end-seconds")

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
                    {"text": args.prompt},
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": args.max_output_tokens,
        },
    }
    output_path = Path(args.output).resolve()
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(request, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(output_path)


if __name__ == "__main__":
    main()
