from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger
from src.preprocess.text_preprocessor import PreprocessResult, preprocess_text


INPUT_BASENAME = "text_analysis_corpus"
OUTPUT_BASENAME = "text_analysis_corpus_preprocessed"
TEXT_COLUMNS = [
    "title",
    "description",
    "title_description_text",
    "comments_text_joined",
    "best_transcript_text",
    "analysis_priority_text",
]


def apply_preprocessing_to_column(df: pd.DataFrame, column_name: str) -> pd.DataFrame:
    """Create conservative preprocessing outputs for one text column."""
    working_df = df.copy()
    if column_name not in working_df.columns:
        return working_df

    results = working_df[column_name].fillna("").astype(str).apply(preprocess_text)
    result_df = pd.DataFrame([result.__dict__ for result in results])
    result_df = result_df.rename(
        columns={
            "text_normalized": f"{column_name}_normalized",
            "text_light_clean": f"{column_name}_light_clean",
            "text_char_count": f"{column_name}_char_count",
            "text_token_count": f"{column_name}_token_count",
            "flag_has_url": f"{column_name}_flag_has_url",
            "flag_has_email": f"{column_name}_flag_has_email",
            "flag_has_korean": f"{column_name}_flag_has_korean",
            "flag_has_latin": f"{column_name}_flag_has_latin",
            "flag_has_digits": f"{column_name}_flag_has_digits",
            "flag_repeated_punct": f"{column_name}_flag_repeated_punct",
            "flag_has_pipe_delimiter": f"{column_name}_flag_has_pipe_delimiter",
            "flag_empty_after_clean": f"{column_name}_flag_empty_after_clean",
            "preprocess_notes": f"{column_name}_preprocess_notes",
        }
    )
    return pd.concat([working_df.reset_index(drop=True), result_df.reset_index(drop=True)], axis=1)


def build_row_level_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Summarize preprocessing risk flags across important text fields."""
    working_df = df.copy()
    risk_columns = [column for column in working_df.columns if column.endswith("_flag_has_url")]
    repeated_columns = [column for column in working_df.columns if column.endswith("_flag_repeated_punct")]
    empty_columns = [column for column in working_df.columns if column.endswith("_flag_empty_after_clean")]

    working_df["preprocess_row_has_any_url"] = (
        working_df[risk_columns].fillna(0).astype(int).sum(axis=1).gt(0).astype(int) if risk_columns else 0
    )
    working_df["preprocess_row_has_any_repeated_punct"] = (
        working_df[repeated_columns].fillna(0).astype(int).sum(axis=1).gt(0).astype(int) if repeated_columns else 0
    )
    working_df["preprocess_row_has_empty_text_field"] = (
        working_df[empty_columns].fillna(0).astype(int).sum(axis=1).gt(0).astype(int) if empty_columns else 0
    )

    return working_df


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    logger = setup_logger(PROJECT_ROOT / "logs", "07_preprocess_text_corpus", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "processed"])

    input_path = (PROJECT_ROOT / "data" / "processed" / INPUT_BASENAME).with_suffix(f".{output_format}")
    corpus_df = load_dataframe_if_exists(input_path)
    if corpus_df.empty:
        raise ValueError(f"No corpus data found at {input_path}. Run 06_build_text_analysis_corpus.py first.")

    processed_df = corpus_df.copy()
    for column_name in TEXT_COLUMNS:
        processed_df = apply_preprocessing_to_column(processed_df, column_name)

    processed_df = build_row_level_flags(processed_df)

    final_path = save_dataframe(
        processed_df.reset_index(drop=True),
        PROJECT_ROOT / "data" / "processed" / OUTPUT_BASENAME,
        output_format,
    )

    logger.info("Preprocessed text corpus with %s rows at %s", len(processed_df), final_path)
    print(f"Saved {len(processed_df)} preprocessed corpus rows to {final_path}")


if __name__ == "__main__":
    main()
