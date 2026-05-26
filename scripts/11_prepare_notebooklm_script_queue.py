from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.io_utils import ensure_directories, load_dataframe_if_exists, save_dataframe, setup_logger


VIDEO_BASENAME = "videos_raw"
TRANSCRIPTS_BASENAME = "transcripts_raw"
QUEUE_BASENAME = "notebooklm_script_queue"
TEMPLATE_BASENAME = "notebooklm_provided_script_template"
DEFAULT_BATCH_SIZE = 50
SUCCESS_SOURCES = {"public_caption", "provided_script", "stt"}
LIVE_KEYWORD_PATTERN = re.compile(
    r"(?:^|[\s\[\(])(?:live|stream(?:ing)?|실시간|생중계|생방송|라이브)(?:$|[\s\]\)])",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the NotebookLM transcript queue from videos missing usable scripts."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of URLs per batch file. Default: {DEFAULT_BATCH_SIZE}",
    )
    parser.add_argument(
        "--per-channel-limit",
        type=int,
        default=0,
        help="Optional maximum number of videos to keep per channel before batching. Default: 0 (no limit).",
    )
    parser.add_argument(
        "--sort-by",
        choices=["published_at", "view_count", "like_count", "engagement"],
        default="published_at",
        help="Priority field used before batching. Default: published_at",
    )
    parser.add_argument(
        "--descending",
        action="store_true",
        help="Sort the priority field in descending order. Useful for views/likes/engagement.",
    )
    parser.add_argument(
        "--max-duration-minutes",
        type=float,
        default=0,
        help="Optional maximum duration in minutes. Videos longer than this are excluded. Default: 0 (no limit).",
    )
    parser.add_argument(
        "--exclude-live-candidates",
        action="store_true",
        help="Exclude videos that look like live/streaming broadcasts based on title/description keywords.",
    )
    parser.add_argument(
        "--include-channels",
        default="",
        help="Optional comma-separated channel names to keep. Default: all channels.",
    )
    parser.add_argument(
        "--exclude-title-keywords",
        default="",
        help="Optional comma-separated title/description keywords to exclude.",
    )
    parser.add_argument(
        "--min-duration-seconds",
        type=float,
        default=0,
        help="Optional minimum duration in seconds. Videos shorter than this are excluded. Default: 0.",
    )
    return parser.parse_args()


def build_current_transcript_lookup(transcripts_df: pd.DataFrame) -> pd.DataFrame:
    """Return the newest transcript status per video."""
    if transcripts_df.empty:
        return pd.DataFrame(columns=["video_id", "transcript_source", "collected_at"])

    working_df = transcripts_df.copy()
    working_df["video_id"] = working_df["video_id"].astype(str)
    if "collected_at" not in working_df.columns:
        working_df["collected_at"] = ""

    working_df = working_df.sort_values(["video_id", "collected_at"], ascending=[True, True])
    working_df = working_df.drop_duplicates(subset=["video_id"], keep="last")
    return working_df[["video_id", "transcript_source", "collected_at"]].reset_index(drop=True)


def collect_existing_notegpt_video_ids(raw_dir: Path) -> set[str]:
    collected: set[str] = set()
    for path in raw_dir.rglob("*_transcript.json"):
        parent_name = path.parent.name.lower()
        if "debug" in parent_name:
            continue
        if not parent_name.startswith("notegpt_exports"):
            continue
        video_id = path.stem.removesuffix("_transcript")
        if video_id:
            collected.add(video_id)
    return collected


def make_batch_id(index_value: int, batch_size: int) -> str:
    """Return a human-friendly batch identifier."""
    batch_number = math.floor(index_value / batch_size) + 1
    return f"batch_{batch_number:03d}"


def write_batch_url_files(queue_df: pd.DataFrame, output_dir: Path) -> None:
    """Create one text file per batch so URLs can be pasted in chunks."""
    ensure_directories([output_dir])

    for stale_batch_file in output_dir.glob("batch_*_urls.txt"):
        stale_batch_file.unlink(missing_ok=True)

    for batch_id, batch_df in queue_df.groupby("notebooklm_batch_id", sort=True):
        lines: list[str] = []
        for row in batch_df.itertuples(index=False):
            lines.append(str(row.url))
        (output_dir / f"{batch_id}_urls.txt").write_text("\n".join(lines), encoding="utf-8")


def add_priority_columns(videos_df: pd.DataFrame) -> pd.DataFrame:
    working_df = videos_df.copy()
    for column in ["view_count", "like_count", "comment_count"]:
        if column not in working_df.columns:
            working_df[column] = 0
        working_df[column] = pd.to_numeric(working_df[column], errors="coerce").fillna(0)
    working_df["engagement"] = (
        working_df["view_count"] * 1.0
        + working_df["like_count"] * 20.0
        + working_df["comment_count"] * 30.0
    )
    return working_df


def parse_iso8601_duration_to_seconds(duration: str) -> float:
    value = str(duration or "").strip().upper()
    if not value or not value.startswith("P"):
        return 0.0

    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value,
    )
    if not match:
        return 0.0

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def mark_duration_and_live_candidates(videos_df: pd.DataFrame) -> pd.DataFrame:
    working_df = videos_df.copy()
    if "duration" not in working_df.columns:
        working_df["duration"] = ""
    if "title" not in working_df.columns:
        working_df["title"] = ""
    if "description" not in working_df.columns:
        working_df["description"] = ""

    working_df["duration_seconds"] = working_df["duration"].map(parse_iso8601_duration_to_seconds)
    working_df["duration_minutes"] = working_df["duration_seconds"] / 60.0
    live_text = (
        working_df["title"].astype(str).fillna("")
        + "\n"
        + working_df["description"].astype(str).fillna("")
    )
    working_df["is_live_candidate"] = live_text.str.contains(LIVE_KEYWORD_PATTERN, na=False)
    return working_df


def parse_csv_values(raw_value: str) -> list[str]:
    return [item.strip() for item in str(raw_value or "").split(",") if item.strip()]


def prioritize_missing_videos(
    missing_df: pd.DataFrame,
    sort_by: str,
    descending: bool,
    per_channel_limit: int,
    max_duration_minutes: float,
    exclude_live_candidates: bool,
    include_channels: list[str],
    exclude_title_keywords: list[str],
    min_duration_seconds: float,
) -> pd.DataFrame:
    working_df = add_priority_columns(mark_duration_and_live_candidates(missing_df))
    working_df["channel_name"] = working_df["channel_name"].astype(str).str.strip()
    working_df["title"] = working_df["title"].astype(str)
    working_df["description"] = working_df["description"].astype(str) if "description" in working_df.columns else ""

    if include_channels:
        include_set = {name.strip() for name in include_channels if name.strip()}
        working_df = working_df.loc[working_df["channel_name"].isin(include_set)].copy()

    if max_duration_minutes and max_duration_minutes > 0:
        working_df = working_df.loc[
            (working_df["duration_minutes"] <= max_duration_minutes)
            | (working_df["duration_minutes"] <= 0)
        ].copy()

    if min_duration_seconds and min_duration_seconds > 0:
        working_df = working_df.loc[
            (working_df["duration_seconds"] >= min_duration_seconds)
            | (working_df["duration_seconds"] <= 0)
        ].copy()

    if exclude_live_candidates:
        working_df = working_df.loc[~working_df["is_live_candidate"]].copy()

    if exclude_title_keywords:
        text_blob = (
            working_df["title"].astype(str).fillna("")
            + "\n"
            + working_df["description"].astype(str).fillna("")
        )
        pattern = "|".join(re.escape(keyword) for keyword in exclude_title_keywords)
        working_df = working_df.loc[~text_blob.str.contains(pattern, case=False, na=False, regex=True)].copy()

    sort_columns = ["channel_name", sort_by, "published_at", "video_id"]
    ascending_flags = [True, not descending, True, True]
    if sort_by == "published_at":
        ascending_flags = [True, not descending, True, True]

    working_df = working_df.sort_values(sort_columns, ascending=ascending_flags).reset_index(drop=True)

    if per_channel_limit and per_channel_limit > 0:
        working_df = (
            working_df.groupby("channel_name", group_keys=False, sort=True)
            .head(per_channel_limit)
            .reset_index(drop=True)
        )

    final_sort_columns = [sort_by, "channel_name", "published_at", "video_id"]
    final_ascending = [not descending, True, True, True]
    if sort_by == "published_at":
        final_ascending = [not descending, True, True, True]

    return working_df.sort_values(final_sort_columns, ascending=final_ascending).reset_index(drop=True)


def main() -> None:
    args = parse_args()
    output_format = "csv"
    logger = setup_logger(PROJECT_ROOT / "logs", "11_prepare_notebooklm_script_queue", "INFO")

    videos_path = (PROJECT_ROOT / "data" / "raw" / VIDEO_BASENAME).with_suffix(f".{output_format}")
    transcripts_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(
        f".{output_format}"
    )

    videos_df = load_dataframe_if_exists(videos_path)
    if videos_df.empty:
        raise ValueError(f"No video data found at {videos_path}.")

    transcripts_df = load_dataframe_if_exists(transcripts_path)
    transcript_status_df = build_current_transcript_lookup(transcripts_df)

    videos_df = videos_df.copy()
    videos_df["video_id"] = videos_df["video_id"].astype(str)
    videos_df["published_at"] = videos_df["published_at"].astype(str)
    videos_df["url"] = videos_df["url"].astype(str)

    merged_df = videos_df.merge(
        transcript_status_df,
        on="video_id",
        how="left",
        suffixes=("", "_transcript"),
    )
    merged_df["transcript_source"] = merged_df["transcript_source"].fillna("unattempted")

    existing_notegpt_ids = collect_existing_notegpt_video_ids(PROJECT_ROOT / "data" / "raw")
    if existing_notegpt_ids:
        merged_df.loc[
            merged_df["video_id"].isin(existing_notegpt_ids),
            "transcript_source",
        ] = "notegpt_collected"

    missing_df = merged_df.loc[~merged_df["transcript_source"].isin(SUCCESS_SOURCES)].copy()
    missing_df = missing_df.loc[missing_df["transcript_source"] != "notegpt_collected"].copy()
    missing_df = prioritize_missing_videos(
        missing_df,
        sort_by=args.sort_by,
        descending=args.descending,
        per_channel_limit=args.per_channel_limit,
        max_duration_minutes=args.max_duration_minutes,
        exclude_live_candidates=args.exclude_live_candidates,
        include_channels=parse_csv_values(args.include_channels),
        exclude_title_keywords=parse_csv_values(args.exclude_title_keywords),
        min_duration_seconds=args.min_duration_seconds,
    )

    batch_size = args.batch_size
    missing_df["queue_index"] = range(1, len(missing_df) + 1)
    missing_df["notebooklm_batch_id"] = [
        make_batch_id(index_value, batch_size)
        for index_value in range(len(missing_df))
    ]

    queue_columns = [
        "queue_index",
        "notebooklm_batch_id",
        "video_id",
        "channel_name",
        "channel_type",
        "published_at",
        "search_keyword",
        "title",
        "url",
        "transcript_source",
        "collected_at",
    ]
    queue_df = missing_df[queue_columns].copy()

    template_df = missing_df[
        [
            "notebooklm_batch_id",
            "video_id",
            "channel_name",
            "channel_type",
            "published_at",
            "search_keyword",
            "title",
            "url",
        ]
    ].copy()
    template_df["script_title"] = template_df["title"]
    template_df["script_text_raw"] = ""
    template_df["script_file_path"] = ""
    template_df["use_flag"] = 0
    template_df["source_note"] = "NotebookLM transcript candidate"

    queue_path = save_dataframe(queue_df, PROJECT_ROOT / "data" / "processed" / QUEUE_BASENAME, output_format)
    template_path = save_dataframe(
        template_df,
        PROJECT_ROOT / "data" / "processed" / TEMPLATE_BASENAME,
        output_format,
    )

    write_batch_url_files(queue_df, PROJECT_ROOT / "data" / "processed" / "notebooklm_batches")

    logger.info(
        "Prepared NotebookLM queue with %s missing-script videos across %s batches "
        "(sort_by=%s descending=%s per_channel_limit=%s max_duration_minutes=%s "
        "exclude_live_candidates=%s include_channels=%s exclude_title_keywords=%s "
        "min_duration_seconds=%s existing_notegpt_ids=%s)",
        len(queue_df),
        queue_df["notebooklm_batch_id"].nunique() if not queue_df.empty else 0,
        args.sort_by,
        args.descending,
        args.per_channel_limit,
        args.max_duration_minutes,
        args.exclude_live_candidates,
        parse_csv_values(args.include_channels),
        parse_csv_values(args.exclude_title_keywords),
        args.min_duration_seconds,
        len(existing_notegpt_ids),
    )
    print(
        f"Saved NotebookLM queue to {queue_path} and template to {template_path} "
        f"for {len(queue_df)} videos."
    )


if __name__ == "__main__":
    main()
