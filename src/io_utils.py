from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pandas.errors import EmptyDataError


def ensure_directories(paths: list[Path]) -> None:
    """Create directories if they do not exist."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def get_timestamp_utc() -> str:
    """Return a UTC timestamp string for collection metadata."""
    return datetime.now(timezone.utc).isoformat()


def setup_logger(log_dir: Path, log_name: str, level: str = "INFO") -> logging.Logger:
    """Create a file and console logger for collection scripts."""
    ensure_directories([log_dir])

    logger = logging.getLogger(log_name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_dir / f"{log_name}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def load_dataframe_if_exists(path: Path) -> pd.DataFrame:
    """Load an existing CSV or parquet file if it exists."""
    if not path.exists():
        return pd.DataFrame()

    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
    except EmptyDataError:
        return pd.DataFrame()

    raise ValueError(f"Unsupported file extension: {path.suffix}")


def save_dataframe(df: pd.DataFrame, path: Path, output_format: str = "csv") -> Path:
    """Save a DataFrame as CSV or parquet and return the final path."""
    normalized_format = output_format.lower().strip()
    if normalized_format not in {"csv", "parquet"}:
        raise ValueError("output_format must be either 'csv' or 'parquet'")

    final_path = path.with_suffix(f".{normalized_format}")
    ensure_directories([final_path.parent])

    if normalized_format == "csv":
        df.to_csv(final_path, index=False, encoding="utf-8-sig")
    else:
        df.to_parquet(final_path, index=False)

    return final_path


def merge_without_duplicates(
    existing_df: pd.DataFrame,
    new_df: pd.DataFrame,
    subset: list[str],
) -> pd.DataFrame:
    """Merge two DataFrames and drop duplicates by the given key columns."""
    if existing_df.empty and new_df.empty:
        return pd.DataFrame()
    if existing_df.empty:
        return new_df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
    if new_df.empty:
        return existing_df.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)

    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=subset, keep="first").reset_index(drop=True)
    return merged
