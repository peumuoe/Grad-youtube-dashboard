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
    "이란",
    "이란의",
    "이스라엘",
    "이스라엘의",
    "미국",
    "미국과",
    "미국이",
    "대통령",
    "대통령은",
    "대통령이",
    "대통령의",
    "트럼프",
    "트럼프의",
    "도널드",
    "중동",
    "공격",
    "공격을",
    "공습",
    "미사일",
    "전쟁",
    "해협을",
    "것으로",
    "있습니다",
    "있는",
    "있다고",
    "말했습니다",
    "밝혔습니다",
    "지금",
    "그런",
    "그래서",
    "이렇게",
    "하고",
    "하는",
    "이게",
    "우리가",
    "어떻게",
    "우리",
    "이번",
    "추가",
    "확인하실",
    "자세한",
    "내용은",
    "기자",
    "채널",
    "메일",
    "social",
    "검색해",
    "앵커",
    "바랍니다",
    "때문에",
    "때문",
    "얘기",
    "생각",
    "정도",
    "상황",
    "경우",
    "부분",
    "아마",
    "있는데",
    "대해서",
    "관련해서",
    "입장",
    "가지",
    "일단",
    "있지",
    "것들",
    "것이",
    "상당히",
    "하나",
    "그니까",
    "있기",
    "문제",
    "사태",
    "대규모",
    "들어보시죠",
    "보입니다",
    "굉장히",
    "그렇게",
    "계속",
    "그러면",
    "그럼",
    "해서",
    "있다",
    "저는",
    "조금",
    "이거",
    "제가",
    "그다음",
    "결국",
    "이것",
    "새로운",
    "고맙습니다",
    "저희",
    "같습니다",
    "것은",
    "만약",
    "되면",
    "수가",
    "거죠",
    "가장",
    "어느",
    "위해서",
    "그것",
    "없는",
    "그게",
    "수도",
    "가능성",
    "거기",
    "보니까",
    "하면",
    "수밖",
    "여기",
    "봤을",
    "되고",
    "iran",
    "km",
    "ho",
    "최고",
    "지도자",
    "음악",
    "프로그램",
    "시사",
    "유튜브",
    "mbc",
    "뉴스데스크",
    "뉴스투데이",
    "뉴스zip",
    "뉴스꾹",
    "한국경제tv",
    "빠르고",
    "정확한",
    "이런",
    "사실",
    "보면",
    "말씀",
    "그리고",
    "대로",
    "자체",
    "기업들",
    "같은",
    "많이",
    "그러니까",
    "어떤",
    "겁니다",
    "근데",
    "가지고",
    "있고",
    "현재",
    "다시",
    "않을까",
    "아니라",
    "보고",
    "가운데",
    "명이",
    "우리나라",
    "기자입니다",
    "세계",
    "korean",
    "하지",
    "여러",
    "아직",
    "사람",
    "정말",
    "무슨",
    "이건",
    "저녁",
    "가성비",
    "한번",
    "개국",
    "역사",
    "나오고",
    "목표",
    "사망한",
    "꼽히",
    "최근",
    "그래",
    "특히",
    "때는",
    "오히려",
    "되는",
    "앞서",
    "함께",
    "of",
    "to",
    "왜냐면",
    "있고요",
    "그거",
    "그렇습니다",
    "00",
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "the",
    "and",
    "will",
    "us",
    "american",
    "may",
    "you",
    "that",
    "they",
    "with",
    "from",
    "into",
    "have",
    "this",
    "your",
    "about",
    "there",
    "them",
    "what",
    "when",
    "where",
    "which",
    "while",
    "because",
    "would",
    "could",
    "should",
}

TOPIC_NOISE_TERMS = {
    "채널 안내·부가 문구",
    "뉴스 포맷·프로그램 묶음",
    "프로그램 소개·부가 문구",
    "진행 멘트·일반 설명",
}

TOPIC_PARTICLE_SUFFIXES = (
    "이라고",
    "라고",
    "이며",
    "인데",
    "에서",
    "으로",
    "에게",
    "까지",
    "부터",
    "처럼",
    "보다",
    "의",
    "이",
    "가",
    "은",
    "는",
    "을",
    "를",
    "와",
    "과",
    "에",
    "도",
    "만",
    "로",
    "나",
)

TOPIC_ENDING_PATTERNS = (
    r"(있습니다|했습니다|합니다|였습니다|됩니다)$",
    r"(말했습니다|밝혔습니다|전했습니다|보도했습니다)$",
    r"(이라고|라고|이며|인데|것이라고|것으로)$",
)

TOPIC_HARD_FILTERS = {
    "기사",
    "기자",
    "영상편집",
    "보도",
    "대한",
    "대해",
    "관련",
    "함께",
    "가운데",
    "지금",
    "이제",
    "이번",
    "이런",
    "그런",
    "그런데",
    "그래서",
    "이렇게",
    "어떤",
    "우리가",
    "어떻게",
    "그리고",
    "그러니까",
    "근데",
    "보면",
    "같은",
    "많이",
    "사실",
    "가지고",
    "있는",
    "있을",
    "있고",
    "있다고",
    "되는",
    "된다",
    "바랍니다",
    "추가",
    "검색해",
    "확인하실",
    "자세한",
    "내용은",
    "채널",
    "메일",
    "social",
    "앵커",
    "도널드",
    "최고",
    "지도자",
    "음악",
    "프로그램",
    "시사",
    "유튜브",
    "카카오톡",
    "제보",
    "뉴스가",
    "됩니다",
    "제보가",
    "당신의",
    "무단전재",
    "저작권자",
    "저작권자 무단전재",
    "the",
    "and",
    "you",
    "that",
    "they",
    "with",
    "from",
    "into",
    "have",
    "this",
    "your",
    "about",
    "there",
    "them",
    "what",
    "when",
    "where",
    "which",
    "while",
    "because",
    "would",
    "could",
    "should",
    "to",
    "of",
    "we",
    "in",
    "is",
    "it",
    "are",
    "for",
    "on",
    "but",
    "be",
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


def normalize_topic_token(token: str) -> str:
    token = token.strip().lower()
    if not token:
        return ""

    if re.fullmatch(r"[가-힣]+", token):
        for pattern in TOPIC_ENDING_PATTERNS:
            token = re.sub(pattern, "", token)
        stripped = True
        while stripped and token:
            stripped = False
            for suffix in TOPIC_PARTICLE_SUFFIXES:
                if token.endswith(suffix) and len(token) > len(suffix) + 1:
                    token = token[: -len(suffix)]
                    stripped = True
                    break

    token = token.strip()
    if len(token) < 2:
        return ""
    if token in DEFAULT_STOPWORDS or token in TOPIC_HARD_FILTERS:
        return ""
    return token


def tokenize_topic_text(text: str) -> list[str]:
    raw_tokens = re.findall(r"[가-힣A-Za-z]{2,}", str(text or "").lower())
    tokens = [normalize_topic_token(token) for token in raw_tokens]
    return [token for token in tokens if token]


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
        tokenizer=tokenize_topic_text,
        preprocessor=None,
        token_pattern=None,
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.9,
        lowercase=False,
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
