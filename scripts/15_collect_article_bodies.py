from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.article_client import ArticleClient, ArticleSourceRule
from src.config_loader import load_article_sources
from src.io_utils import load_dataframe_if_exists, save_dataframe, setup_logger


QUEUE_BASENAME = "article_script_queue"
DEFAULT_MAX_ROWS_PER_RUN = 50
DEFAULT_SAVE_EVERY = 10


@dataclass
class QueueUpdateResult:
    """One row update payload after article body retrieval."""

    row_index: int
    article_title: str
    article_body_raw: str
    use_flag: int
    source_note: str


def build_article_source_rules(df: pd.DataFrame) -> list[ArticleSourceRule]:
    """Convert config dataframe into source rule objects."""
    rules: list[ArticleSourceRule] = []
    if df.empty:
        return rules

    for row in df.itertuples(index=False):
        rules.append(
            ArticleSourceRule(
                channel_name=str(getattr(row, "channel_name", "")).strip(),
                base_domain=str(getattr(row, "base_domain", "")).strip(),
                article_url_contains=str(getattr(row, "article_url_contains", "")).strip(),
                title_selector=str(getattr(row, "title_selector", "")).strip(),
                body_selector=str(getattr(row, "body_selector", "")).strip(),
                notes=str(getattr(row, "notes", "")).strip(),
            )
        )
    return rules


def find_matching_rule(article_url: str, channel_name: str, rules: list[ArticleSourceRule]) -> ArticleSourceRule | None:
    """Match one queue row to the most relevant article source rule."""
    parsed_domain = urlparse(article_url).netloc.lower()
    normalized_channel_name = str(channel_name).strip()

    for rule in rules:
        if rule.channel_name and rule.channel_name == normalized_channel_name:
            if not rule.base_domain or rule.base_domain.lower() in parsed_domain:
                return rule

    for rule in rules:
        if rule.base_domain and rule.base_domain.lower() in parsed_domain:
            return rule

    for rule in rules:
        if rule.article_url_contains and rule.article_url_contains.lower() in article_url.lower():
            return rule

    return None


def apply_updates(queue_df: pd.DataFrame, updates: list[QueueUpdateResult]) -> pd.DataFrame:
    """Apply fetched article bodies back to the queue dataframe."""
    if not updates:
        return queue_df

    updated_df = queue_df.copy()
    for update in updates:
        updated_df.at[update.row_index, "article_title"] = update.article_title
        updated_df.at[update.row_index, "article_body_raw"] = update.article_body_raw
        updated_df.at[update.row_index, "use_flag"] = str(update.use_flag)
        updated_df.at[update.row_index, "source_note"] = update.source_note
    return updated_df


def save_queue(queue_df: pd.DataFrame) -> Path:
    """Persist the article body queue to disk."""
    return save_dataframe(queue_df, PROJECT_ROOT / "data" / "processed" / QUEUE_BASENAME, "csv")


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")

    logger = setup_logger(PROJECT_ROOT / "logs", "15_collect_article_bodies", "INFO")
    queue_path = PROJECT_ROOT / "data" / "processed" / f"{QUEUE_BASENAME}.csv"
    queue_df = load_dataframe_if_exists(queue_path)
    if queue_df.empty:
        raise ValueError("article_script_queue.csv is required. Run 12_prepare_article_script_queue.py first.")

    source_rules = build_article_source_rules(load_article_sources(PROJECT_ROOT / "config"))
    article_client = ArticleClient()

    queue_df = queue_df.copy()
    queue_df["article_candidate_url"] = queue_df["article_candidate_url"].astype(str)
    queue_df["article_body_raw"] = queue_df["article_body_raw"].astype(str)
    queue_df["use_flag"] = queue_df["use_flag"].astype(str).str.strip().replace("", "0")

    target_df = queue_df.loc[
        (queue_df["article_candidate_url"].str.strip() != "")
        & (queue_df["article_body_raw"].str.strip() == "")
    ].copy()
    target_df = target_df.head(DEFAULT_MAX_ROWS_PER_RUN)

    logger.info("Article body collection started for %s rows", len(target_df))

    updates: list[QueueUpdateResult] = []
    for position, row in enumerate(tqdm(target_df.itertuples(), total=len(target_df), desc="Collecting article bodies"), start=1):
        article_url = str(getattr(row, "article_candidate_url", "")).strip()
        channel_name = str(getattr(row, "channel_name", "")).strip()
        row_index = int(getattr(row, "Index"))
        source_rule = find_matching_rule(article_url, channel_name, source_rules)

        try:
            result = article_client.fetch_article(article_url=article_url, source_rule=source_rule)
            use_flag = 1 if len(result.article_body_raw.strip()) >= 200 else 0
            updates.append(
                QueueUpdateResult(
                    row_index=row_index,
                    article_title=result.article_title,
                    article_body_raw=result.article_body_raw,
                    use_flag=use_flag,
                    source_note=result.source_note,
                )
            )
            logger.info("Collected article body for video=%s url=%s", getattr(row, "video_id", ""), article_url)
        except Exception as exc:
            logger.warning(
                "Failed collecting article body for video=%s url=%s: %s",
                getattr(row, "video_id", ""),
                article_url,
                exc,
            )

        if position % DEFAULT_SAVE_EVERY == 0:
            queue_df = apply_updates(queue_df, updates)
            save_queue(queue_df)
            updates = []

    queue_df = apply_updates(queue_df, updates)
    final_path = save_queue(queue_df)
    logger.info("Article body collection finished. Saved queue to %s", final_path)
    print(f"Saved article queue to {final_path}")


if __name__ == "__main__":
    main()
