from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_channels
from src.io_utils import setup_logger
from src.youtube_client import YouTubeClient


def search_channels(client: YouTubeClient, query: str, max_results: int = 5) -> list[dict]:
    """Search channel candidates by display name."""
    data = client._request(
        "search",
        {
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": max_results,
        },
    )
    return data.get("items", [])


def build_rows(channel_name: str, channel_type: str, items: list[dict]) -> list[dict]:
    """Convert channel search results into a simple table."""
    rows: list[dict] = []
    for rank, item in enumerate(items, start=1):
        snippet = item.get("snippet", {})
        rows.append(
            {
                "source_channel_name": channel_name,
                "source_channel_type": channel_type,
                "candidate_rank": rank,
                "candidate_channel_id": item.get("snippet", {}).get("channelId", ""),
                "candidate_channel_name": snippet.get("title", ""),
                "candidate_description": snippet.get("description", ""),
                "candidate_custom_url": snippet.get("customUrl", ""),
                "published_at": snippet.get("publishedAt", ""),
            }
        )
    return rows


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    log_level = os.getenv("LOG_LEVEL", "INFO")

    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is missing. Please set it in .env.")

    logger = setup_logger(PROJECT_ROOT / "logs", "00_resolve_channel_ids", log_level)
    client = YouTubeClient(api_key=api_key)

    channels_df = load_channels(PROJECT_ROOT / "config")
    targets_df = channels_df[channels_df["channel_id"].astype(str).str.strip() == ""].copy()

    if targets_df.empty:
        print("All included channels already have channel_id values.")
        return

    results: list[dict] = []
    for row in targets_df.itertuples(index=False):
        try:
            items = search_channels(client, row.channel_name)
            results.extend(build_rows(row.channel_name, row.channel_type, items))
            logger.info("Resolved %s candidates for %s", len(items), row.channel_name)
        except Exception as exc:
            logger.exception("Failed resolving channel_id candidates for %s: %s", row.channel_name, exc)

    result_df = pd.DataFrame(results)
    output_path = PROJECT_ROOT / "data" / "raw" / "channel_id_candidates.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Saved channel candidates to {output_path}")
    print("Review candidate_channel_id values and copy the correct IDs into config/channels_master.csv")


if __name__ == "__main__":
    main()
