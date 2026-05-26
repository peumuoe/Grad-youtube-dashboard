from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import save_dataframe, setup_logger


EXPORT_DIR = PROJECT_ROOT / "data" / "raw" / "notegpt_exports"
OUTPUT_TEMPLATE_PATH = PROJECT_ROOT / "data" / "processed" / "browser_extension_provided_script_template.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "notegpt_export_import_report.csv"

REQUIRED_COLUMNS = [
    "batch_id",
    "video_id",
    "channel_name",
    "channel_type",
    "published_at",
    "search_keyword",
    "title",
    "url",
    "script_title",
    "script_text_raw",
    "script_file_path",
    "use_flag",
    "source_note",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import NoteGPT transcript JSON files into the transcript template CSV."
    )
    parser.add_argument(
        "--export-dir",
        default=str(EXPORT_DIR),
        help="Directory containing *_transcript.json files.",
    )
    parser.add_argument(
        "--template-path",
        default=str(OUTPUT_TEMPLATE_PATH),
        help="CSV file to update with imported transcript text.",
    )
    parser.add_argument(
        "--report-path",
        default=str(REPORT_PATH),
        help="CSV path for the import report.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan export_dir for *_transcript.json files.",
    )
    return parser.parse_args()


def load_existing_template(template_path: Path) -> pd.DataFrame:
    if not template_path.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.read_csv(template_path, dtype=str).fillna("")
    if "batch_id" not in df.columns and "notebooklm_batch_id" in df.columns:
        df["batch_id"] = df["notebooklm_batch_id"].astype(str)
    for column in REQUIRED_COLUMNS:
        if column not in df.columns:
            df[column] = ""
    return df[REQUIRED_COLUMNS].copy()


def load_export_payloads(export_dir: Path, recursive: bool = False) -> list[dict[str, str]]:
    payloads: list[dict[str, str]] = []
    path_iter = export_dir.rglob("*_transcript.json") if recursive else export_dir.glob("*_transcript.json")
    for path in sorted(path_iter):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["source_json_path"] = str(path)
        payloads.append(payload)
    return payloads


def merge_exports_into_template(template_df: pd.DataFrame, payloads: list[dict[str, str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not payloads:
        empty_report = pd.DataFrame(columns=["video_id", "title", "source_json_path", "text_length", "matched"])
        return template_df.copy(), empty_report

    updated_df = template_df.copy()
    report_rows: list[dict[str, str | int]] = []

    for payload in payloads:
        video_id = str(payload.get("video_id", "")).strip()
        title = str(payload.get("title", "")).strip()
        transcript_text = str(payload.get("transcript_text", "")).strip()
        source_json_path = str(payload.get("source_json_path", ""))

        if not transcript_text:
            report_rows.append(
                {
                    "video_id": video_id,
                    "title": title,
                    "source_json_path": source_json_path,
                    "text_length": 0,
                    "matched": 0,
                }
            )
            continue

        matched_mask = updated_df["video_id"].astype(str).str.strip() == video_id
        matched = int(bool(video_id) and matched_mask.any())

        if matched:
            updated_df.loc[matched_mask, "script_title"] = updated_df.loc[matched_mask, "script_title"].replace("", title)
            updated_df.loc[matched_mask, "script_text_raw"] = transcript_text
            updated_df.loc[matched_mask, "script_file_path"] = source_json_path
            updated_df.loc[matched_mask, "use_flag"] = "1"
            updated_df.loc[matched_mask, "source_note"] = "NoteGPT transcript export"
        else:
            updated_df.loc[len(updated_df)] = {
                "batch_id": "",
                "video_id": video_id,
                "channel_name": "",
                "channel_type": "",
                "published_at": "",
                "search_keyword": "",
                "title": title,
                "url": str(payload.get("url", "")).strip(),
                "script_title": title,
                "script_text_raw": transcript_text,
                "script_file_path": source_json_path,
                "use_flag": "1",
                "source_note": "NoteGPT transcript export",
            }

        report_rows.append(
            {
                "video_id": video_id,
                "title": title,
                "source_json_path": source_json_path,
                "text_length": len(transcript_text),
                "matched": matched,
            }
        )

    report_df = pd.DataFrame(report_rows)
    updated_df = updated_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)
    return updated_df, report_df


def main() -> None:
    args = parse_args()
    export_dir = Path(args.export_dir)
    template_path = Path(args.template_path)
    report_path = Path(args.report_path)

    logger = setup_logger(PROJECT_ROOT / "logs", "19_import_notegpt_exports", "INFO")
    export_dir.mkdir(parents=True, exist_ok=True)

    template_df = load_existing_template(template_path)
    payloads = load_export_payloads(export_dir, recursive=args.recursive)
    updated_df, report_df = merge_exports_into_template(template_df, payloads)

    save_dataframe(updated_df, template_path.with_suffix(""), "csv")
    save_dataframe(report_df, report_path.with_suffix(""), "csv")

    logger.info("Imported NoteGPT exports: payloads=%s updated_rows=%s", len(payloads), len(updated_df))
    print(
        f"Imported {len(payloads)} NoteGPT transcript JSON files into {template_path} "
        f"(rows now {len(updated_df)})"
    )


if __name__ == "__main__":
    main()
