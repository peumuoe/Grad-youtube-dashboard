from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
}

GENERIC_BODY_SELECTORS = [
    "article",
    '[role="main"]',
    "main",
    ".article_body",
    ".article-body",
    ".article_txt",
    ".article_view",
    ".news_body",
    ".newsct_article",
    ".news_text",
    ".view_txt",
    ".story-news.article",
    "#articleBody",
    "#articlebody",
    "#newsEndContents",
    "#content",
]

GENERIC_TITLE_SELECTORS = [
    "meta[property='og:title']",
    "meta[name='title']",
    "h1",
    "title",
]

DROP_TAGS = ["script", "style", "noscript", "svg", "header", "footer", "nav", "aside", "form"]


@dataclass
class ArticleSourceRule:
    """Channel/domain-specific rule for article body extraction."""

    channel_name: str
    base_domain: str
    article_url_contains: str
    title_selector: str
    body_selector: str
    notes: str


@dataclass
class ArticleFetchResult:
    """Normalized article body payload for provided_script import."""

    article_title: str
    article_body_raw: str
    source_note: str


class ArticleClient:
    """Fetch and extract article body text from broadcaster web pages."""

    def __init__(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch_article(self, article_url: str, source_rule: ArticleSourceRule | None = None) -> ArticleFetchResult:
        """Fetch one article URL and extract title/body text."""
        response = self.session.get(article_url, timeout=self.timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        for tag_name in DROP_TAGS:
            for node in soup.find_all(tag_name):
                node.decompose()

        title_text = self._extract_title(soup, source_rule)
        body_text = self._extract_body_text(soup, source_rule)
        source_label = source_rule.channel_name if source_rule and source_rule.channel_name else urlparse(article_url).netloc

        return ArticleFetchResult(
            article_title=title_text.strip(),
            article_body_raw=body_text.strip(),
            source_note=f"Broadcast article body | {source_label}",
        )

    def _extract_title(self, soup: BeautifulSoup, source_rule: ArticleSourceRule | None) -> str:
        """Extract a best-effort article title."""
        selector_candidates: list[str] = []
        if source_rule and source_rule.title_selector:
            selector_candidates.append(source_rule.title_selector)
        selector_candidates.extend(GENERIC_TITLE_SELECTORS)

        for selector in selector_candidates:
            selected = soup.select_one(selector)
            if selected is None:
                continue
            if selected.name == "meta":
                content = (selected.get("content") or "").strip()
                if content:
                    return content
            else:
                text_value = selected.get_text(" ", strip=True)
                if text_value:
                    return text_value
        return ""

    def _extract_body_text(self, soup: BeautifulSoup, source_rule: ArticleSourceRule | None) -> str:
        """Extract a best-effort body text with generic fallbacks."""
        selector_candidates: list[str] = []
        if source_rule and source_rule.body_selector:
            selector_candidates.append(source_rule.body_selector)
        selector_candidates.extend(GENERIC_BODY_SELECTORS)

        candidate_texts: list[str] = []
        for selector in selector_candidates:
            selected_nodes = soup.select(selector)
            for node in selected_nodes:
                text_value = self._flatten_node_text(node)
                if len(text_value) >= 200:
                    candidate_texts.append(text_value)

        if candidate_texts:
            return max(candidate_texts, key=len)

        return self._flatten_node_text(soup)

    def _flatten_node_text(self, node: BeautifulSoup) -> str:
        """Flatten one HTML subtree into a paragraph-oriented text block."""
        paragraph_like_texts: list[str] = []
        for paragraph in node.select("p, h1, h2, h3, li"):
            text_value = paragraph.get_text(" ", strip=True)
            if text_value:
                paragraph_like_texts.append(text_value)

        if paragraph_like_texts:
            return "\n".join(paragraph_like_texts)

        return node.get_text("\n", strip=True)
