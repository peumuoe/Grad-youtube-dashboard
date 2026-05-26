from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import pandas as pd

from src.analyze.boilerplate_filters import strip_boilerplate


DEFAULT_STOPWORDS = {
    "jtbc",
    "ytn",
    "kbs",
    "mbn",
    "sbs",
    "news",
    "뉴스",
    "뉴스룸",
    "자막뉴스",
    "지금이뉴스",
    "속보",
    "영상",
    "방송사",
    "구독",
    "공식",
    "페이지",
    "페이스북",
    "인스타그램",
    "트위터",
    "youtube",
    "www",
    "https",
    "report",
    "community",
    "co",
    "kr",
    "구독하기",
    "커뮤니티",
    "공식",
    "페이지",
    "제보하기",
    "모바일라이브",
    "시청하기",
    "무단",
    "전재",
    "재배포",
    "금지",
    "방송사",
    "채널a",
    "연합뉴스tv",
    "yonhapnewstv",
    "tv조선",
    "tvchosun",
    "머니쇼",
    "뉴스a",
    "뉴스top10",
    "시사쇼",
    "정치다",
    "mbc뉴스",
    "sbs뉴스",
    "jtbc뉴스",
    "imbc",
    "kbsnews",
    "sbs8news",
    "티조clip",
    "뉴스다",
    "실시간",
    "라이브",
    "shorts",
    "ai",
    "학습",
    "이용",
    "포함",
    "원문",
    "제보",
}

TOPIC_EXCLUDE_TITLE_PATTERNS = [
    re.compile(r"#shorts", re.IGNORECASE),
    re.compile(r"\bshorts\b", re.IGNORECASE),
    re.compile(r"🔴\s*live", re.IGNORECASE),
    re.compile(r"\blive\b", re.IGNORECASE),
    re.compile(r"실시간\s*라이브", re.IGNORECASE),
    re.compile(r"현장영상", re.IGNORECASE),
    re.compile(r"현장쏙", re.IGNORECASE),
    re.compile(r"티조clip", re.IGNORECASE),
    re.compile(r"#뉴스다", re.IGNORECASE),
]


@dataclass
class TopicModelArtifacts:
    video_topics_df: pd.DataFrame
    topic_summary_df: pd.DataFrame
    channel_topic_share_df: pd.DataFrame
    metadata: dict[str, Any]


def choose_topic_count(document_count: int, requested_topics: int) -> int:
    """Choose a stable topic count from corpus size."""
    if document_count < 20:
        return max(2, min(requested_topics, document_count))
    if document_count < 80:
        return min(requested_topics, 4)
    if document_count < 200:
        return min(requested_topics, 6)
    return min(requested_topics, 8)


def format_top_terms(feature_names: list[str], weights: list[float], top_n: int = 10) -> str:
    """Format topic keywords for readable output."""
    paired = [(feature_names[idx], float(weight)) for idx, weight in enumerate(weights)]
    ordered = sorted(paired, key=lambda item: item[1], reverse=True)[:top_n]
    return ", ".join([term for term, _ in ordered if term])


def is_topic_excluded_title(title: str) -> bool:
    """Return True when a title is likely a noisy clip/live artifact for topic modeling."""
    normalized = str(title or "").strip()
    return any(pattern.search(normalized) for pattern in TOPIC_EXCLUDE_TITLE_PATTERNS)


def run_topic_model(
    topic_df: pd.DataFrame,
    requested_topics: int = 8,
    min_characters: int = 30,
    max_features: int = 5000,
    random_state: int = 42,
) -> TopicModelArtifacts:
    """Run a lightweight TF-IDF + NMF topic model over topic input text."""
    from sklearn.decomposition import NMF
    from sklearn.feature_extraction.text import TfidfVectorizer

    working_df = topic_df.copy()
    working_df["topic_text"] = working_df["topic_text"].fillna("").astype(str).str.strip()
    working_df["topic_text_cleaned"] = working_df["topic_text"].apply(strip_boilerplate)
    working_df = working_df[~working_df["title"].fillna("").astype(str).apply(is_topic_excluded_title)].copy()
    working_df = working_df[working_df["topic_text_cleaned"].str.len() >= min_characters].copy()
    if working_df.empty:
        raise ValueError("No topic documents passed the minimum text-length filter.")

    n_topics = choose_topic_count(len(working_df), requested_topics)
    vectorizer = TfidfVectorizer(
        max_features=max_features,
        stop_words=list(DEFAULT_STOPWORDS),
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
    )
    matrix = vectorizer.fit_transform(working_df["topic_text_cleaned"])
    nmf = NMF(n_components=n_topics, random_state=random_state, init="nndsvda", max_iter=400)
    doc_topic = nmf.fit_transform(matrix)
    topic_term = nmf.components_

    feature_names = vectorizer.get_feature_names_out().tolist()
    dominant_topic_idx = doc_topic.argmax(axis=1)
    dominant_topic_strength = doc_topic.max(axis=1)

    working_df["topic_id"] = dominant_topic_idx.astype(int)
    working_df["topic_label"] = working_df["topic_id"].apply(lambda value: f"topic_{value:02d}")
    working_df["topic_strength"] = dominant_topic_strength.astype(float)

    summary_rows: list[dict[str, Any]] = []
    for topic_idx in range(n_topics):
        member_mask = working_df["topic_id"] == topic_idx
        summary_rows.append(
            {
                "topic_id": topic_idx,
                "topic_label": f"topic_{topic_idx:02d}",
                "document_count": int(member_mask.sum()),
                "share_of_documents": float(member_mask.mean()),
                "top_terms": format_top_terms(feature_names, topic_term[topic_idx].tolist(), top_n=12),
                "sample_title": str(working_df.loc[member_mask, "title"].head(1).squeeze() or ""),
            }
        )

    topic_summary_df = pd.DataFrame(summary_rows).sort_values(
        ["document_count", "topic_id"], ascending=[False, True]
    ).reset_index(drop=True)

    channel_topic_share_df = (
        working_df.groupby(["channel_name", "topic_label"], dropna=False)
        .size()
        .rename("video_count")
        .reset_index()
    )
    channel_topic_share_df["channel_total"] = channel_topic_share_df.groupby("channel_name")["video_count"].transform("sum")
    channel_topic_share_df["topic_share_within_channel"] = (
        channel_topic_share_df["video_count"] / channel_topic_share_df["channel_total"]
    )
    channel_topic_share_df = channel_topic_share_df.sort_values(
        ["channel_name", "video_count", "topic_label"], ascending=[True, False, True]
    ).reset_index(drop=True)

    metadata = {
        "document_count": int(len(working_df)),
        "requested_topics": int(requested_topics),
        "actual_topics": int(n_topics),
        "min_characters": int(min_characters),
        "max_features": int(max_features),
        "model": "tfidf_nmf",
    }

    keep_columns = [
        "video_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "search_keyword",
        "published_at",
        "title",
        "topic_text",
        "topic_text_cleaned",
        "topic_text_char_count",
        "topic_source_type",
        "analysis_stage2_note",
        "topic_id",
        "topic_label",
        "topic_strength",
    ]
    return TopicModelArtifacts(
        video_topics_df=working_df[keep_columns].reset_index(drop=True),
        topic_summary_df=topic_summary_df,
        channel_topic_share_df=channel_topic_share_df,
        metadata=metadata,
    )
