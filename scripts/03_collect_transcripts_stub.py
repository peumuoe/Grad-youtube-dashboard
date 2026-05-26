from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_provided_scripts, load_transcript_replacements
from src.io_utils import (
    ensure_directories,
    get_timestamp_utc,
    load_dataframe_if_exists,
    save_dataframe,
    setup_logger,
)
from src.stt_client import STTClient
from src.text_cleaner import build_cleaned_transcript_text
from src.transcript_client import TranscriptClient, TranscriptFetchResult


VIDEO_BASENAME = "videos_raw"
TRANSCRIPTS_BASENAME = "transcripts_raw"
VALID_TRANSCRIPT_SOURCES = {"public_caption", "provided_script", "stt", "none"}
DEFAULT_TRANSCRIPT_LANGUAGES = ["ko", "en"]
DEFAULT_MAX_VIDEOS_PER_RUN = 300
DEFAULT_SAVE_EVERY = 25
DEFAULT_MAX_CONSECUTIVE_IP_BLOCKS = 10
DEFAULT_RETRY_NONE_ROWS = 0
DEFAULT_PUBLIC_CAPTION_SLEEP_SECONDS = 1.0
DEFAULT_ENABLE_STT = 0
DEFAULT_STT_MODEL_SIZE = "tiny"
DEFAULT_STT_DEVICE = "cpu"
DEFAULT_STT_COMPUTE_TYPE = "int8"
DEFAULT_STT_BEAM_SIZE = 1
DEFAULT_AUDIO_CACHE_DIR = "data/raw/audio_cache"
DEFAULT_KEEP_DOWNLOADED_AUDIO = 0
DEFAULT_YTDLP_PUBLIC_SUBTITLE_FALLBACK = 1
DEFAULT_YTDLP_AUDIO_FORMAT = "bestaudio[abr<=96]/bestaudio/best"
DEFAULT_YTDLP_PREFER_SUBTITLE_FALLBACK = 1
DEFAULT_TRANSCRIPT_COLLECTION_MODE = "hybrid"
DEFAULT_REQUEST_SLEEP_MIN_SECONDS = 2.5
DEFAULT_REQUEST_SLEEP_MAX_SECONDS = 6.0
DEFAULT_FAILURE_BACKOFF_MIN_SECONDS = 8.0
DEFAULT_FAILURE_BACKOFF_MAX_SECONDS = 18.0
DEFAULT_IP_BLOCK_COOLDOWN_SECONDS = 90.0
TRANSCRIPT_DEFAULTS = {
    "transcript_text_raw": "",
    "transcript_text_clean": "",
    "transcript_text_corrected": "",
    "transcript_quality": "",
    "stt_applied": 0,
    "transcript_language_code": "",
    "transcript_language": "",
    "transcript_is_generated": 0,
    "transcript_segment_count": 0,
    "correction_status": "raw",
    "correction_notes": "",
    "text_needs_review": 0,
    "transcript_error": "",
}


def parse_bool_flag(raw_value: str, default: int = 0) -> bool:
    """Parse a typical env flag."""
    normalized = str(raw_value if raw_value is not None else default).strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def parse_transcript_languages(raw_value: str) -> list[str]:
    """Parse a comma-separated language preference list."""
    languages = [item.strip() for item in raw_value.split(",") if item.strip()]
    return languages or DEFAULT_TRANSCRIPT_LANGUAGES


def parse_collection_mode(raw_value: str) -> str:
    """Normalize transcript collection mode."""
    normalized = str(raw_value or DEFAULT_TRANSCRIPT_COLLECTION_MODE).strip().lower()
    valid_modes = {"hybrid", "public_only", "stt_only"}
    if normalized not in valid_modes:
        raise ValueError(f"Invalid TRANSCRIPT_COLLECTION_MODE: {raw_value}")
    return normalized


def build_empty_transcript_row(video_id: str, collected_at: str, error_message: str = "") -> dict:
    """Return a stable row when a public caption is not available."""
    transcript_source = "none"
    return {
        "video_id": video_id,
        "transcript_source": transcript_source,
        "transcript_text_raw": "",
        "transcript_text_clean": "",
        "transcript_text_corrected": "",
        "transcript_quality": "",
        "stt_applied": 0,
        "transcript_language_code": "",
        "transcript_language": "",
        "transcript_is_generated": 0,
        "transcript_segment_count": 0,
        "correction_status": "raw",
        "correction_notes": "",
        "text_needs_review": 0,
        "transcript_error": error_message,
        "collected_at": collected_at,
    }


def build_transcript_row(
    video_id: str,
    collected_at: str,
    transcript_result: TranscriptFetchResult,
    replacements_df: pd.DataFrame,
) -> dict:
    """Convert a transcript client response into one table row."""
    if transcript_result.transcript_source not in VALID_TRANSCRIPT_SOURCES:
        raise ValueError(f"Invalid transcript_source: {transcript_result.transcript_source}")

    cleaned_text = build_cleaned_transcript_text(
        raw_text=transcript_result.transcript_text_raw,
        replacements_df=replacements_df,
        source=transcript_result.transcript_source,
    )

    return {
        "video_id": video_id,
        "transcript_source": transcript_result.transcript_source,
        "transcript_text_raw": transcript_result.transcript_text_raw,
        "transcript_text_clean": cleaned_text.transcript_text_clean,
        "transcript_text_corrected": cleaned_text.transcript_text_corrected,
        "transcript_quality": transcript_result.transcript_quality,
        "stt_applied": transcript_result.stt_applied,
        "transcript_language_code": transcript_result.transcript_language_code,
        "transcript_language": transcript_result.transcript_language,
        "transcript_is_generated": transcript_result.transcript_is_generated,
        "transcript_segment_count": transcript_result.transcript_segment_count,
        "correction_status": cleaned_text.correction_status,
        "correction_notes": cleaned_text.correction_notes,
        "text_needs_review": cleaned_text.text_needs_review,
        "transcript_error": transcript_result.transcript_error,
        "collected_at": collected_at,
    }


def merge_transcript_rows(existing_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """Keep the newest row per video_id so stub/none rows can be replaced later."""
    if existing_df.empty and new_df.empty:
        return pd.DataFrame()
    if existing_df.empty:
        return new_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)
    if new_df.empty:
        return existing_df.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)

    merged = pd.concat([existing_df, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)
    return standardize_transcript_dataframe(merged)


def standardize_transcript_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure transcript output columns exist with stable default values."""
    standardized = df.copy()
    for column_name, default_value in TRANSCRIPT_DEFAULTS.items():
        if column_name not in standardized.columns:
            standardized[column_name] = default_value
        standardized[column_name] = standardized[column_name].fillna(default_value)
    return standardized


def save_progress(
    existing_df: pd.DataFrame,
    rows: list[dict],
    output_path_base: Path,
    output_format: str,
) -> pd.DataFrame:
    """Persist partial transcript results so long runs can resume safely."""
    if not rows:
        return existing_df

    partial_df = pd.DataFrame(rows).drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)
    merged_df = merge_transcript_rows(existing_df=existing_df, new_df=partial_df)
    save_dataframe(merged_df, output_path_base, output_format)
    return merged_df


def is_ip_block_error(error_message: str) -> bool:
    """Detect repeated blocking messages from transcript retrieval."""
    normalized = error_message.lower()
    ip_block_markers = [
        "blocking requests from your ip",
        "ip has been blocked",
        "http error 429",
        "too many requests",
        "winerror 10013",
        "failed to establish a new connection",
    ]
    return any(marker in normalized for marker in ip_block_markers)


def sleep_with_jitter(
    minimum_seconds: float,
    maximum_seconds: float,
    logger,
    reason: str,
) -> None:
    """Sleep for a randomized duration so requests are less bursty."""
    lower_bound = max(0.0, minimum_seconds)
    upper_bound = max(lower_bound, maximum_seconds)
    if upper_bound <= 0:
        return

    duration = random.uniform(lower_bound, upper_bound)
    logger.info("Sleeping %.2f seconds before %s", duration, reason)
    time.sleep(duration)


def build_provided_script_lookup(
    provided_scripts_df: pd.DataFrame,
    project_root: Path,
) -> dict[str, TranscriptFetchResult]:
    """Build a video_id keyed lookup from externally provided scripts."""
    lookup: dict[str, TranscriptFetchResult] = {}
    if provided_scripts_df.empty:
        return lookup

    for row in provided_scripts_df.itertuples(index=False):
        video_id = str(getattr(row, "video_id", "")).strip()
        if not video_id:
            continue

        raw_text = str(getattr(row, "script_text_raw", "")).strip()
        script_file_path = str(getattr(row, "script_file_path", "")).strip()
        if not raw_text and script_file_path:
            candidate_path = Path(script_file_path)
            if not candidate_path.is_absolute():
                candidate_path = project_root / candidate_path
            if candidate_path.exists():
                raw_text = candidate_path.read_text(encoding="utf-8")

        if not raw_text.strip():
            continue

        lookup[video_id] = TranscriptFetchResult(
            transcript_source="provided_script",
            transcript_text_raw=raw_text,
            transcript_text_clean=raw_text,
            transcript_quality="provided_script",
            stt_applied=0,
            transcript_language_code="ko",
            transcript_language="Korean",
            transcript_is_generated=0,
            transcript_segment_count=0,
            transcript_error="",
        )

    return lookup


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    output_format = os.getenv("OUTPUT_FORMAT", "csv").lower().strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")
    transcript_languages = parse_transcript_languages(os.getenv("TRANSCRIPT_LANGUAGES", "ko,en"))
    max_videos_per_run = int(os.getenv("TRANSCRIPT_MAX_VIDEOS_PER_RUN", str(DEFAULT_MAX_VIDEOS_PER_RUN)))
    save_every = int(os.getenv("TRANSCRIPT_SAVE_EVERY", str(DEFAULT_SAVE_EVERY)))
    max_consecutive_ip_blocks = int(
        os.getenv(
            "TRANSCRIPT_MAX_CONSECUTIVE_IP_BLOCKS",
            str(DEFAULT_MAX_CONSECUTIVE_IP_BLOCKS),
        )
    )
    retry_none_rows = int(os.getenv("TRANSCRIPT_RETRY_NONE_ROWS", str(DEFAULT_RETRY_NONE_ROWS)))
    public_caption_sleep_seconds = float(
        os.getenv("PUBLIC_CAPTION_SLEEP_SECONDS", str(DEFAULT_PUBLIC_CAPTION_SLEEP_SECONDS))
    )
    enable_stt = parse_bool_flag(os.getenv("ENABLE_STT", str(DEFAULT_ENABLE_STT)))
    stt_model_size = os.getenv("STT_MODEL_SIZE", DEFAULT_STT_MODEL_SIZE).strip() or DEFAULT_STT_MODEL_SIZE
    stt_device = os.getenv("STT_DEVICE", DEFAULT_STT_DEVICE).strip() or DEFAULT_STT_DEVICE
    stt_compute_type = os.getenv("STT_COMPUTE_TYPE", DEFAULT_STT_COMPUTE_TYPE).strip() or DEFAULT_STT_COMPUTE_TYPE
    stt_beam_size = int(os.getenv("STT_BEAM_SIZE", str(DEFAULT_STT_BEAM_SIZE)))
    audio_cache_dir = os.getenv("AUDIO_CACHE_DIR", DEFAULT_AUDIO_CACHE_DIR).strip() or DEFAULT_AUDIO_CACHE_DIR
    keep_downloaded_audio = parse_bool_flag(
        os.getenv("KEEP_DOWNLOADED_AUDIO", str(DEFAULT_KEEP_DOWNLOADED_AUDIO))
    )
    use_ytdlp_public_subtitle_fallback = parse_bool_flag(
        os.getenv(
            "YTDLP_PUBLIC_SUBTITLE_FALLBACK",
            str(DEFAULT_YTDLP_PUBLIC_SUBTITLE_FALLBACK),
        )
    )
    prefer_ytdlp_when_authenticated = parse_bool_flag(
        os.getenv(
            "YTDLP_PREFER_SUBTITLE_FALLBACK",
            str(DEFAULT_YTDLP_PREFER_SUBTITLE_FALLBACK),
        )
    )
    ytdlp_cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    ytdlp_cookiefile = os.getenv("YTDLP_COOKIEFILE", "").strip()
    ytdlp_audio_format = os.getenv("YTDLP_AUDIO_FORMAT", DEFAULT_YTDLP_AUDIO_FORMAT).strip() or DEFAULT_YTDLP_AUDIO_FORMAT
    collection_mode = parse_collection_mode(
        os.getenv("TRANSCRIPT_COLLECTION_MODE", DEFAULT_TRANSCRIPT_COLLECTION_MODE)
    )
    request_sleep_min_seconds = float(
        os.getenv("TRANSCRIPT_REQUEST_SLEEP_MIN_SECONDS", str(DEFAULT_REQUEST_SLEEP_MIN_SECONDS))
    )
    request_sleep_max_seconds = float(
        os.getenv("TRANSCRIPT_REQUEST_SLEEP_MAX_SECONDS", str(DEFAULT_REQUEST_SLEEP_MAX_SECONDS))
    )
    failure_backoff_min_seconds = float(
        os.getenv("TRANSCRIPT_FAILURE_BACKOFF_MIN_SECONDS", str(DEFAULT_FAILURE_BACKOFF_MIN_SECONDS))
    )
    failure_backoff_max_seconds = float(
        os.getenv("TRANSCRIPT_FAILURE_BACKOFF_MAX_SECONDS", str(DEFAULT_FAILURE_BACKOFF_MAX_SECONDS))
    )
    ip_block_cooldown_seconds = float(
        os.getenv("TRANSCRIPT_IP_BLOCK_COOLDOWN_SECONDS", str(DEFAULT_IP_BLOCK_COOLDOWN_SECONDS))
    )

    if collection_mode == "public_only":
        enable_stt = False
    elif collection_mode == "stt_only":
        use_ytdlp_public_subtitle_fallback = False

    logger = setup_logger(PROJECT_ROOT / "logs", "03_collect_transcripts_stub", log_level)
    ensure_directories([PROJECT_ROOT / "data" / "raw"])

    videos_path = (PROJECT_ROOT / "data" / "raw" / VIDEO_BASENAME).with_suffix(f".{output_format}")
    videos_df = load_dataframe_if_exists(videos_path)
    if videos_df.empty:
        raise ValueError(f"No video data found at {videos_path}. Run 01_collect_videos.py first.")

    output_path = (PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME).with_suffix(f".{output_format}")
    existing_df = load_dataframe_if_exists(output_path)
    collected_at = get_timestamp_utc()
    transcript_client = TranscriptClient(
        project_root=PROJECT_ROOT,
        use_ytdlp_fallback=use_ytdlp_public_subtitle_fallback,
        cookies_from_browser=ytdlp_cookies_from_browser,
        cookiefile=ytdlp_cookiefile,
        prefer_ytdlp_when_authenticated=prefer_ytdlp_when_authenticated,
    )
    stt_client = STTClient(
        enabled=enable_stt,
        project_root=PROJECT_ROOT,
        model_size=stt_model_size,
        device=stt_device,
        compute_type=stt_compute_type,
        beam_size=stt_beam_size,
        audio_cache_dir=audio_cache_dir,
        keep_downloaded_audio=keep_downloaded_audio,
        cookies_from_browser=ytdlp_cookies_from_browser,
        cookiefile=ytdlp_cookiefile,
        audio_format=ytdlp_audio_format,
    )
    provided_scripts_df = load_provided_scripts(PROJECT_ROOT / "config")
    replacements_df = load_transcript_replacements(PROJECT_ROOT / "config")
    provided_script_lookup = build_provided_script_lookup(provided_scripts_df, PROJECT_ROOT)

    completed_video_ids: set[str] = set()
    attempted_video_ids: set[str] = set()
    retry_none_df = pd.DataFrame()
    if not existing_df.empty and "transcript_source" in existing_df.columns:
        completed_mask = existing_df["transcript_source"].astype(str).isin(["public_caption", "provided_script", "stt"])
        completed_video_ids = set(existing_df.loc[completed_mask, "video_id"].astype(str).tolist())
        attempted_video_ids = set(existing_df["video_id"].astype(str).tolist())
        retry_none_df = existing_df.loc[
            existing_df["transcript_source"].astype(str) == "none",
            ["video_id", "collected_at"],
        ].copy()

    all_video_ids = videos_df["video_id"].astype(str).drop_duplicates().tolist()
    unseen_video_ids = [
        video_id
        for video_id in all_video_ids
        if video_id not in attempted_video_ids and video_id not in completed_video_ids
    ]
    retry_video_ids = []
    if retry_none_rows == 1:
        if retry_none_df.empty:
            retry_video_ids = [
                video_id
                for video_id in all_video_ids
                if video_id in attempted_video_ids and video_id not in completed_video_ids
            ]
        else:
            retry_none_df["collected_at"] = retry_none_df["collected_at"].astype(str).fillna("")
            retry_none_df = retry_none_df.drop_duplicates(subset=["video_id"], keep="last")
            retry_none_df = retry_none_df.sort_values(["collected_at", "video_id"], ascending=[True, True])
            retry_video_ids = retry_none_df["video_id"].astype(str).tolist()

    target_video_ids = unseen_video_ids + retry_video_ids
    target_video_ids = target_video_ids[:max_videos_per_run]

    logger.info(
        "Transcript collection started for %s videos with languages=%s provided_scripts=%s stt_enabled=%s",
        len(target_video_ids),
        ",".join(transcript_languages),
        len(provided_script_lookup),
        int(enable_stt),
    )
    logger.info(
        "collection_mode=%s yt-dlp_fallback_enabled=%s ytdlp_prefer_when_authenticated=%s cookies_from_browser=%s cookiefile=%s audio_format=%s request_sleep=%.1f-%.1fs failure_backoff=%.1f-%.1fs ip_block_cooldown=%.1fs",
        collection_mode,
        int(use_ytdlp_public_subtitle_fallback),
        int(prefer_ytdlp_when_authenticated),
        ytdlp_cookies_from_browser or "(none)",
        ytdlp_cookiefile or "(none)",
        ytdlp_audio_format,
        request_sleep_min_seconds,
        request_sleep_max_seconds,
        failure_backoff_min_seconds,
        failure_backoff_max_seconds,
        ip_block_cooldown_seconds,
    )

    rows: list[dict] = []
    output_path_base = PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME
    consecutive_ip_blocks = 0
    for index, video_id in enumerate(tqdm(target_video_ids, desc="Collecting transcripts"), start=1):
        video_url = ""
        matched_rows = videos_df.loc[videos_df["video_id"].astype(str) == video_id, "url"]
        if not matched_rows.empty:
            video_url = str(matched_rows.iloc[0])

        should_delay_request = video_id not in provided_script_lookup
        if should_delay_request and index > 1:
            sleep_with_jitter(
                request_sleep_min_seconds,
                request_sleep_max_seconds,
                logger,
                reason=f"requesting transcript for video={video_id}",
            )

        try:
            if video_id in provided_script_lookup:
                transcript_result = provided_script_lookup[video_id]
            elif collection_mode == "stt_only":
                stt_result = stt_client.fetch_transcript(video_id=video_id, video_url=video_url)
                transcript_result = TranscriptFetchResult(
                    transcript_source="stt",
                    transcript_text_raw=stt_result.transcript_text_raw,
                    transcript_text_clean=stt_result.transcript_text_raw,
                    transcript_quality=stt_result.transcript_quality,
                    stt_applied=1,
                    transcript_language_code=stt_result.transcript_language_code,
                    transcript_language=stt_result.transcript_language,
                    transcript_is_generated=0,
                    transcript_segment_count=stt_result.transcript_segment_count,
                    transcript_error=stt_result.transcript_error,
                )
            else:
                transcript_result = transcript_client.fetch_public_transcript(video_id, transcript_languages)

            rows.append(build_transcript_row(video_id, collected_at, transcript_result, replacements_df))
            consecutive_ip_blocks = 0
            logger.info(
                "Collected transcript for video=%s source=%s language=%s generated=%s",
                video_id,
                transcript_result.transcript_source,
                transcript_result.transcript_language_code,
                transcript_result.transcript_is_generated,
            )
        except Exception as exc:
            error_message = str(exc)
            if enable_stt:
                try:
                    stt_result = stt_client.fetch_transcript(video_id=video_id, video_url=video_url)
                    transcript_result = TranscriptFetchResult(
                        transcript_source="stt",
                        transcript_text_raw=stt_result.transcript_text_raw,
                        transcript_text_clean=stt_result.transcript_text_raw,
                        transcript_quality=stt_result.transcript_quality,
                        stt_applied=1,
                        transcript_language_code=stt_result.transcript_language_code,
                        transcript_language=stt_result.transcript_language,
                        transcript_is_generated=0,
                        transcript_segment_count=stt_result.transcript_segment_count,
                        transcript_error=stt_result.transcript_error,
                    )
                    rows.append(build_transcript_row(video_id, collected_at, transcript_result, replacements_df))
                    logger.info("Collected transcript for video=%s source=stt", video_id)
                    consecutive_ip_blocks = 0
                    continue
                except Exception as stt_exc:
                    error_message = f"{error_message}\n\nSTT fallback failed: {stt_exc}"

            rows.append(build_empty_transcript_row(video_id, collected_at, error_message))
            logger.warning("No transcript collected for video=%s: %s", video_id, exc)
            if is_ip_block_error(error_message):
                consecutive_ip_blocks += 1
                logger.warning(
                    "Detected blocking/network error for video=%s (%s consecutive)",
                    video_id,
                    consecutive_ip_blocks,
                )
                sleep_with_jitter(
                    failure_backoff_min_seconds,
                    failure_backoff_max_seconds,
                    logger,
                    reason=f"network backoff after video={video_id}",
                )
            else:
                consecutive_ip_blocks = 0
                sleep_with_jitter(
                    failure_backoff_min_seconds / 2,
                    failure_backoff_max_seconds / 2,
                    logger,
                    reason=f"general failure cooldown after video={video_id}",
                )

        if public_caption_sleep_seconds > 0 and video_id not in provided_script_lookup and not enable_stt:
            time.sleep(public_caption_sleep_seconds)

        if len(rows) % save_every == 0:
            existing_df = save_progress(existing_df, rows, output_path_base, output_format)
            logger.info("Saved partial transcript progress for %s rows", len(rows))

        if consecutive_ip_blocks >= max_consecutive_ip_blocks:
            logger.warning(
                "Stopping early after %s consecutive IP block errors; cooling down for %.1f seconds",
                consecutive_ip_blocks,
                ip_block_cooldown_seconds,
            )
            if ip_block_cooldown_seconds > 0:
                time.sleep(ip_block_cooldown_seconds)
            break

    new_df = pd.DataFrame(rows).drop_duplicates(subset=["video_id"], keep="last").reset_index(drop=True)

    merged_df = merge_transcript_rows(existing_df=existing_df, new_df=new_df)
    final_path = save_dataframe(merged_df, PROJECT_ROOT / "data" / "raw" / TRANSCRIPTS_BASENAME, output_format)

    public_caption_count = 0
    if not merged_df.empty:
        public_caption_count = int((merged_df["transcript_source"] == "public_caption").sum())

    logger.info(
        "Transcript collection finished. Saved %s rows to %s with %s public captions",
        len(merged_df),
        final_path,
        public_caption_count,
    )
    print(f"Saved {len(merged_df)} transcript rows to {final_path} ({public_caption_count} public captions)")


if __name__ == "__main__":
    main()
