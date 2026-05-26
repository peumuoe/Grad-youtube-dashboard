from __future__ import annotations

from pathlib import Path

import pandas as pd


def get_project_root() -> Path:
    """Return the project root based on this file location."""
    return Path(__file__).resolve().parents[1]


def get_config_dir() -> Path:
    """Return the config directory path."""
    return get_project_root() / "config"


def load_channels(config_dir: Path | None = None) -> pd.DataFrame:
    """Load channel master data and keep only rows marked for collection."""
    base_dir = config_dir or get_config_dir()
    channels_path = base_dir / "channels_master.csv"
    df = pd.read_csv(channels_path, dtype=str).fillna("")

    required_columns = {
        "channel_type",
        "channel_name",
        "channel_id",
        "priority",
        "include_flag",
        "notes",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"channels_master.csv is missing columns: {sorted(missing_columns)}")

    df["include_flag"] = df["include_flag"].astype(str).str.strip().replace("", "0")
    df = df[df["include_flag"] == "1"].copy()
    df["priority"] = pd.to_numeric(df["priority"], errors="coerce").fillna(999).astype(int)
    df["channel_id"] = df["channel_id"].astype(str).str.strip()
    df = df.sort_values(["priority", "channel_name"]).reset_index(drop=True)
    return df


def load_keywords(config_dir: Path | None = None) -> pd.DataFrame:
    """Load keyword master data for YouTube search queries."""
    base_dir = config_dir or get_config_dir()
    keywords_path = base_dir / "keywords_master.csv"
    df = pd.read_csv(keywords_path, dtype=str).fillna("")

    required_columns = {"priority", "keyword", "note"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"keywords_master.csv is missing columns: {sorted(missing_columns)}")

    df["priority"] = pd.to_numeric(df["priority"], errors="coerce").fillna(999).astype(int)
    df["keyword"] = df["keyword"].astype(str).str.strip()
    df = df[df["keyword"] != ""].copy()
    df = df.sort_values(["priority", "keyword"]).reset_index(drop=True)
    return df


def load_provided_scripts(config_dir: Path | None = None) -> pd.DataFrame:
    """Load externally secured script mappings keyed by video_id."""
    base_dir = config_dir or get_config_dir()
    scripts_path = base_dir / "provided_scripts_master.csv"
    if not scripts_path.exists():
        return pd.DataFrame(
            columns=[
                "video_id",
                "script_title",
                "script_text_raw",
                "script_file_path",
                "use_flag",
                "source_note",
            ]
        )

    df = pd.read_csv(scripts_path, dtype=str).fillna("")
    required_columns = {
        "video_id",
        "script_title",
        "script_text_raw",
        "script_file_path",
        "use_flag",
        "source_note",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"provided_scripts_master.csv is missing columns: {sorted(missing_columns)}")

    df["use_flag"] = df["use_flag"].astype(str).str.strip().replace("", "0")
    df["video_id"] = df["video_id"].astype(str).str.strip()
    df = df[(df["use_flag"] == "1") & (df["video_id"] != "")].copy()
    return df.reset_index(drop=True)


def load_transcript_replacements(config_dir: Path | None = None) -> pd.DataFrame:
    """Load replacement rules for transcript typo correction."""
    base_dir = config_dir or get_config_dir()
    replacements_path = base_dir / "transcript_replacements.csv"
    if not replacements_path.exists():
        return pd.DataFrame(columns=["priority", "wrong_text", "corrected_text", "active_flag", "note"])

    df = pd.read_csv(replacements_path, dtype=str).fillna("")
    required_columns = {"priority", "wrong_text", "corrected_text", "active_flag", "note"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"transcript_replacements.csv is missing columns: {sorted(missing_columns)}")
    return df.reset_index(drop=True)


def load_article_sources(config_dir: Path | None = None) -> pd.DataFrame:
    """Load article source rules keyed by channel/domain."""
    base_dir = config_dir or get_config_dir()
    article_sources_path = base_dir / "article_sources_master.csv"
    if not article_sources_path.exists():
        return pd.DataFrame(
            columns=[
                "channel_name",
                "base_domain",
                "article_url_contains",
                "title_selector",
                "body_selector",
                "active_flag",
                "notes",
            ]
        )

    df = pd.read_csv(article_sources_path, dtype=str).fillna("")
    required_columns = {
        "channel_name",
        "base_domain",
        "article_url_contains",
        "title_selector",
        "body_selector",
        "active_flag",
        "notes",
    }
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"article_sources_master.csv is missing columns: {sorted(missing_columns)}")

    df["active_flag"] = df["active_flag"].astype(str).str.strip().replace("", "0")
    df = df[df["active_flag"] == "1"].copy()
    df["channel_name"] = df["channel_name"].astype(str).str.strip()
    df["base_domain"] = df["base_domain"].astype(str).str.strip()
    df["article_url_contains"] = df["article_url_contains"].astype(str).str.strip()
    df["title_selector"] = df["title_selector"].astype(str).str.strip()
    df["body_selector"] = df["body_selector"].astype(str).str.strip()
    return df.reset_index(drop=True)
