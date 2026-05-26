from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from pandas import isna
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_provided_scripts
from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


TRANSCRIPTS_BASENAME = "transcripts_raw"
REVIEW_BASENAME = "transcripts_review_queue"
OUTPUT_BASENAME = "transcripts_analysis_ready"


def build_provided_transcript_rows(provided_df: pd.DataFrame) -> pd.DataFrame:
    """Normalize provided-script rows into transcript-analysis schema."""
    if provided_df.empty:
        return pd.DataFrame()

    working_df = provided_df.copy()
    working_df["video_id"] = working_df["video_id"].astype(str).str.strip()
    working_df["script_text_raw"] = working_df["script_text_raw"].astype(str).fillna("").str.strip()
    working_df = working_df.loc[
        (working_df["video_id"] != "") & (working_df["script_text_raw"] != "")
    ].copy()
    if working_df.empty:
        return pd.DataFrame()

    normalized_df = pd.DataFrame(
        {
            "video_id": working_df["video_id"],
            "transcript_source": "provided_script",
            "transcript_text_raw": working_df["script_text_raw"],
            "transcript_text_clean": working_df["script_text_raw"],
            "transcript_quality": "provided_script",
            "stt_applied": 0,
            "transcript_language_code": "ko",
            "transcript_language": "Korean",
            "transcript_is_generated": 0,
            "transcript_segment_count": 0,
            "transcript_error": "",
            "collected_at": "",
            "transcript_text_corrected": working_df["script_text_raw"],
            "correction_status": "provided_script",
            "correction_notes": "Imported from provided_scripts_master.csv",
            "text_needs_review": 0,
            "manual_quality_label": "",
            "manual_review_status": "",
            "manual_corrected_text": "",
            "manual_title_summary": "",
            "manual_key_terms": "",
            "manual_review_notes": "",
            "final_use_flag": 1,
            "quality_label": "usable",
            "quality_score": 1.0,
            "recommended_use": "analysis",
        }
    )
    return normalized_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)


def normalize_text_value(value: object) -> str:
    """Return a clean string while treating NaN-like values as empty."""
    if isna(value):
        return ""
    return str(value or "").strip()


def choose_analysis_text(row: pd.Series) -> str:
    """Choose the best available text for downstream analysis."""
    manual_text = normalize_text_value(row.get("manual_corrected_text", ""))
    corrected_text = normalize_text_value(row.get("transcript_text_corrected", ""))
    clean_text = normalize_text_value(row.get("transcript_text_clean", ""))
    raw_text = normalize_text_value(row.get("transcript_text_raw", ""))

    if manual_text:
        return manual_text
    if corrected_text:
        return corrected_text
    if clean_text:
        return clean_text
    return raw_text


def choose_quality_label(row: pd.Series) -> str:
    """Prefer the manual label if present."""
    manual_label = normalize_text_value(row.get("manual_quality_label", ""))
    if manual_label:
        return manual_label
    return normalize_text_value(row.get("quality_label", ""))


def compute_use_flag(row: pd.Series) -> int:
    """Decide whether the transcript is ready for downstream analysis."""
    final_use_flag = row.get("final_use_flag", 0)
    if isna(final_use_flag):
        final_use_flag = 0
    if int(float(final_use_flag or 0)) == 1:
        return 1

    source = normalize_text_value(row.get("transcript_source", ""))
    quality_label = choose_quality_label(row)
    manual_status = normalize_text_value(row.get("manual_review_status", "")).lower()

    if source in {"provided_script", "public_caption"}:
        return 1
    if manual_status in {"approved", "usable"} and quality_label in {"usable", "partially_usable"}:
        return 1
    return 0


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "05_build_transcript_analysis_ready", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    transcripts_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(f".{output_format}")
    transcripts_df = load_dataframe_if_exists(transcripts_path)
    if transcripts_df.empty:
        raise ValueError(f"No transcript data found at {transcripts_path}. Run 03_collect_transcripts_stub.py first.")

    provided_scripts_df = load_provided_scripts(PROJECT_ROOT / "config")
    provided_transcripts_df = build_provided_transcript_rows(provided_scripts_df)
    if not provided_transcripts_df.empty:
        transcripts_df = pd.concat([transcripts_df, provided_transcripts_df], ignore_index=True)
        transcripts_df = transcripts_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)

    review_path = (PROJECT_ROOT / "data" / "processed" / REVIEW_BASENAME).with_suffix(f".{output_format}")
    review_df = load_dataframe_if_exists(review_path)

    if review_df.empty:
        merged_df = transcripts_df.copy()
    else:
        review_columns = [
            "video_id",
            "manual_quality_label",
            "manual_review_status",
            "manual_corrected_text",
            "manual_title_summary",
            "manual_key_terms",
            "manual_review_notes",
            "final_use_flag",
            "quality_label",
            "quality_score",
            "recommended_use",
        ]
        available_columns = [column for column in review_columns if column in review_df.columns]
        merged_df = transcripts_df.merge(
            review_df[available_columns].drop_duplicates(subset=["video_id"], keep="last"),
            on="video_id",
            how="left",
        )

    merged_df["analysis_text"] = merged_df.apply(choose_analysis_text, axis=1)
    merged_df["analysis_quality_label"] = merged_df.apply(choose_quality_label, axis=1)
    merged_df["analysis_use_flag"] = merged_df.apply(compute_use_flag, axis=1)

    final_path = save_dataframe(
        merged_df.reset_index(drop=True),
        PROJECT_ROOT / "data" / "processed" / OUTPUT_BASENAME,
        output_format,
    )

    usable_count = int((merged_df["analysis_use_flag"] == 1).sum())
    logger.info(
        "Built analysis-ready transcripts with %s rows and %s usable rows at %s",
        len(merged_df),
        usable_count,
        final_path,
    )
    print(f"Saved {len(merged_df)} transcript analysis rows to {final_path} ({usable_count} usable)")


if __name__ == "__main__":
    main()
