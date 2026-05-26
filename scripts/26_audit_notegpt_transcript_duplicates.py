from __future__ import annotations

import argparse
import hashlib
import json
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT_DIRS = [
    PROJECT_ROOT / "data" / "raw" / "notegpt_exports_batch001_guarded",
    PROJECT_ROOT / "data" / "raw" / "notegpt_exports_batch001_retry",
]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "notegpt_transcript_duplicate_audit.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit NoteGPT transcript JSON files for exact and near duplicates."
    )
    parser.add_argument(
        "--export-dir",
        action="append",
        dest="export_dirs",
        default=[],
        help="Directory containing *_transcript.json files. Repeat as needed.",
    )
    parser.add_argument(
        "--output-path",
        default=str(DEFAULT_OUTPUT_PATH),
        help="CSV file to write duplicate audit results.",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.9,
        help="Near-duplicate similarity threshold. Default: 0.9",
    )
    return parser.parse_args()


def resolve_export_dirs(args: argparse.Namespace) -> list[Path]:
    if args.export_dirs:
        dirs = [Path(value) for value in args.export_dirs]
    else:
        dirs = DEFAULT_EXPORT_DIRS
    return [path if path.is_absolute() else PROJECT_ROOT / path for path in dirs]


def load_payload_rows(export_dirs: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for export_dir in export_dirs:
        if not export_dir.exists():
            continue
        for path in sorted(export_dir.glob("*_transcript.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = str(payload.get("transcript_text") or "").strip()
            rows.append(
                {
                    "source_json_path": str(path),
                    "source_dir": str(export_dir),
                    "video_id": str(payload.get("video_id") or "").strip(),
                    "title": str(payload.get("title") or "").strip(),
                    "url": str(payload.get("url") or "").strip(),
                    "text": text,
                    "text_length": str(len(text)),
                    "text_hash": hashlib.sha1(text.encode("utf-8")).hexdigest() if text else "",
                }
            )
    return rows


def build_duplicate_rows(rows: list[dict[str, str]], similarity_threshold: float) -> list[dict[str, str | float]]:
    duplicate_rows: list[dict[str, str | float]] = []
    for index, left in enumerate(rows):
        left_text = left["text"]
        if not left_text:
            continue
        for right in rows[index + 1 :]:
            right_text = right["text"]
            if not right_text:
                continue

            if left["text_hash"] == right["text_hash"]:
                similarity = 1.0
                duplicate_type = "exact"
            else:
                similarity = SequenceMatcher(None, left_text[:12000], right_text[:12000]).ratio()
                if similarity < similarity_threshold:
                    continue
                duplicate_type = "near"

            duplicate_rows.append(
                {
                    "duplicate_type": duplicate_type,
                    "similarity": round(similarity, 4),
                    "video_id_a": left["video_id"],
                    "video_id_b": right["video_id"],
                    "title_a": left["title"],
                    "title_b": right["title"],
                    "text_length_a": left["text_length"],
                    "text_length_b": right["text_length"],
                    "source_json_path_a": left["source_json_path"],
                    "source_json_path_b": right["source_json_path"],
                }
            )
    return sorted(
        duplicate_rows,
        key=lambda row: (row["duplicate_type"] != "exact", -float(row["similarity"])),
    )


def main() -> None:
    args = parse_args()
    export_dirs = resolve_export_dirs(args)
    rows = load_payload_rows(export_dirs)
    duplicate_rows = build_duplicate_rows(rows, args.similarity_threshold)

    output_path = Path(args.output_path)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(duplicate_rows).to_csv(output_path, index=False, encoding="utf-8-sig")
    print(
        f"Audited {len(rows)} transcript JSON files and wrote {len(duplicate_rows)} duplicate rows to {output_path}"
    )


if __name__ == "__main__":
    main()
