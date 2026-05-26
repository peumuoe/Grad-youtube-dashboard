from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import save_dataframe, setup_logger


NOTEBOOKLM_TEMPLATE_PATH = PROJECT_ROOT / "data" / "processed" / "notebooklm_provided_script_template.csv"
BROWSER_EXTENSION_TEMPLATE_PATH = PROJECT_ROOT / "data" / "processed" / "browser_extension_provided_script_template.csv"
ARTICLE_QUEUE_PATH = PROJECT_ROOT / "data" / "processed" / "article_script_queue.csv"
OUTPUT_PATH = PROJECT_ROOT / "config" / "provided_scripts_master.csv"
REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "provided_script_import_report.csv"

REQUIRED_OUTPUT_COLUMNS = [
    "video_id",
    "script_title",
    "script_text_raw",
    "script_file_path",
    "use_flag",
    "source_note",
]


def load_csv_if_exists(path: Path) -> pd.DataFrame:
    """Load one CSV if it exists, otherwise return an empty frame."""
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str).fillna("")


def normalize_script_template(
    df: pd.DataFrame,
    source_path: Path,
    default_source_note: str,
) -> pd.DataFrame:
    """Convert one manual script template into provided_script schema."""
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"])

    working_df = df.copy()
    working_df["use_flag"] = working_df["use_flag"].astype(str).str.strip().replace("", "0")
    working_df["video_id"] = working_df["video_id"].astype(str).str.strip()
    working_df["script_text_raw"] = working_df["script_text_raw"].astype(str)
    working_df = working_df.loc[
        (working_df["use_flag"] == "1")
        & (working_df["video_id"] != "")
        & (working_df["script_text_raw"].str.strip() != "")
    ].copy()

    if working_df.empty:
        return pd.DataFrame(columns=REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"])

    working_df["script_title"] = working_df["script_title"].astype(str)
    working_df["script_file_path"] = working_df.get("script_file_path", "").astype(str)
    working_df["source_note"] = working_df.get("source_note", "").astype(str).replace("", default_source_note)
    working_df["source_file"] = source_path.name
    working_df["text_length"] = working_df["script_text_raw"].str.len()
    return working_df[REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"]].reset_index(drop=True)


def normalize_article_queue(df: pd.DataFrame) -> pd.DataFrame:
    """Convert article body queue rows into provided_script schema."""
    if df.empty:
        return pd.DataFrame(columns=REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"])

    working_df = df.copy()
    working_df["use_flag"] = working_df["use_flag"].astype(str).str.strip().replace("", "0")
    working_df["video_id"] = working_df["video_id"].astype(str).str.strip()
    working_df["article_body_raw"] = working_df["article_body_raw"].astype(str)
    working_df = working_df.loc[
        (working_df["use_flag"] == "1")
        & (working_df["video_id"] != "")
        & (working_df["article_body_raw"].str.strip() != "")
    ].copy()

    if working_df.empty:
        return pd.DataFrame(columns=REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"])

    working_df["script_title"] = working_df["article_title"].astype(str)
    title_fallback_mask = working_df["script_title"].str.strip() == ""
    working_df.loc[title_fallback_mask, "script_title"] = working_df.loc[title_fallback_mask, "title"].astype(str)
    working_df["script_text_raw"] = working_df["article_body_raw"].astype(str)
    working_df["script_file_path"] = ""
    working_df["source_note"] = working_df.get("source_note", "").astype(str).replace(
        "",
        "Broadcast article body",
    )
    working_df["source_file"] = ARTICLE_QUEUE_PATH.name
    working_df["text_length"] = working_df["script_text_raw"].str.len()
    return working_df[REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"]].reset_index(drop=True)


def merge_candidates(existing_df: pd.DataFrame, candidate_df: pd.DataFrame) -> pd.DataFrame:
    """Merge imported rows and prefer the longest available text per video."""
    frames: list[pd.DataFrame] = []
    if not existing_df.empty:
        working_existing = existing_df.copy()
        for column_name in REQUIRED_OUTPUT_COLUMNS:
            if column_name not in working_existing.columns:
                working_existing[column_name] = ""
        working_existing["video_id"] = working_existing["video_id"].astype(str).str.strip()
        working_existing["script_text_raw"] = working_existing["script_text_raw"].astype(str)
        working_existing["use_flag"] = working_existing["use_flag"].astype(str).str.strip().replace("", "0")
        working_existing = working_existing.loc[
            (working_existing["video_id"] != "")
            & (working_existing["script_text_raw"].str.strip() != "")
            & (working_existing["use_flag"] == "1")
        ].copy()
        working_existing["source_file"] = "provided_scripts_master.csv"
        working_existing["text_length"] = working_existing["script_text_raw"].astype(str).str.len()
        if not working_existing.empty:
            frames.append(working_existing[REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"]])

    if not candidate_df.empty:
        frames.append(candidate_df[REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"]])

    if not frames:
        return pd.DataFrame(columns=REQUIRED_OUTPUT_COLUMNS + ["source_file", "text_length"])

    merged_df = pd.concat(frames, ignore_index=True)
    merged_df["video_id"] = merged_df["video_id"].astype(str).str.strip()
    merged_df["script_text_raw"] = merged_df["script_text_raw"].astype(str)
    merged_df["text_length"] = pd.to_numeric(merged_df["text_length"], errors="coerce").fillna(0).astype(int)
    merged_df = merged_df.sort_values(
        ["video_id", "text_length", "source_file"],
        ascending=[True, True, True],
    )
    merged_df = merged_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)
    return merged_df


def main() -> None:
    logger = setup_logger(PROJECT_ROOT / "logs", "13_import_provided_scripts", "INFO")

    existing_df = load_csv_if_exists(OUTPUT_PATH)
    notebooklm_df = normalize_script_template(
        load_csv_if_exists(NOTEBOOKLM_TEMPLATE_PATH),
        source_path=NOTEBOOKLM_TEMPLATE_PATH,
        default_source_note="NotebookLM transcript",
    )
    browser_extension_df = normalize_script_template(
        load_csv_if_exists(BROWSER_EXTENSION_TEMPLATE_PATH),
        source_path=BROWSER_EXTENSION_TEMPLATE_PATH,
        default_source_note="Browser extension transcript",
    )
    article_df = normalize_article_queue(load_csv_if_exists(ARTICLE_QUEUE_PATH))

    candidate_df = pd.concat([notebooklm_df, browser_extension_df, article_df], ignore_index=True)
    merged_df = merge_candidates(existing_df=existing_df, candidate_df=candidate_df)

    output_df = merged_df[REQUIRED_OUTPUT_COLUMNS].copy()
    save_dataframe(output_df, OUTPUT_PATH.with_suffix(""), "csv")

    report_df = merged_df[
        [
            "video_id",
            "script_title",
            "source_note",
            "source_file",
            "text_length",
        ]
    ].copy()
    save_dataframe(report_df, REPORT_PATH.with_suffix(""), "csv")

    logger.info(
        "Imported provided scripts: notebooklm=%s browser_extension=%s article=%s final_total=%s",
        len(notebooklm_df),
        len(browser_extension_df),
        len(article_df),
        len(output_df),
    )
    print(
        f"Imported provided scripts into {OUTPUT_PATH} "
        f"(NotebookLM={len(notebooklm_df)}, BrowserExtension={len(browser_extension_df)}, "
        f"Article={len(article_df)}, Final={len(output_df)})"
    )


if __name__ == "__main__":
    main()
