from __future__ import annotations

import re


URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MULTISPACE_PATTERN = re.compile(r"\s+")

BOILERPLATE_PATTERNS = [
    re.compile(r"방송사\s*:\s*[^\n]+", re.IGNORECASE),
    re.compile(r"기사\s*전문\s*[^\n]*", re.IGNORECASE),
    re.compile(r"시리즈\s*더\s*보기\s*[^\n]*", re.IGNORECASE),
    re.compile(r"제보하기\s*[^\n]*", re.IGNORECASE),
    re.compile(r"모바일라이브\s*시청하기\s*[^\n]*", re.IGNORECASE),
    re.compile(r"공식\s*페이지\s*[^\n]*", re.IGNORECASE),
    re.compile(r"페이스북\s*[^\n]*", re.IGNORECASE),
    re.compile(r"인스타그램\s*[^\n]*", re.IGNORECASE),
    re.compile(r"트위터\s*[^\n]*", re.IGNORECASE),
    re.compile(r"x\(트위터\)\s*[^\n]*", re.IGNORECASE),
    re.compile(r"유튜브\s*구독하기\s*[^\n]*", re.IGNORECASE),
    re.compile(r"유튜브\s*커뮤니티\s*[^\n]*", re.IGNORECASE),
    re.compile(r"지금,\s*이슈의\s*현장을\s*실시간으로[^\n]*", re.IGNORECASE),
    re.compile(r"all rights reserved", re.IGNORECASE),
    re.compile(r"copyright", re.IGNORECASE),
    re.compile(r"무단\s*전재\s*재배포\s*금지", re.IGNORECASE),
    re.compile(r"ai학습\s*포함[^\n]*", re.IGNORECASE),
    re.compile(r"뉴스를\s*더하다[^\n]*", re.IGNORECASE),
    re.compile(r"연합뉴스tv\s*\(yonhapnewstv\)[^\n]*", re.IGNORECASE),
    re.compile(r"yonhapnewstv[^\n]*", re.IGNORECASE),
    re.compile(r"뉴스의\s*시작[^\n]*", re.IGNORECASE),
    re.compile(r"특집\s*뉴스a", re.IGNORECASE),
    re.compile(r"뉴스top10", re.IGNORECASE),
    re.compile(r"시사쇼\s*정치다", re.IGNORECASE),
    re.compile(r"sbs\s*실시간\s*라이브", re.IGNORECASE),
    re.compile(r"라이브\s*[^\n]*", re.IGNORECASE),
    re.compile(r"#shorts", re.IGNORECASE),
    re.compile(r"shorts", re.IGNORECASE),
    re.compile(r"ai\s*데이터\s*활용\s*금지", re.IGNORECASE),
    re.compile(r"ai학습\s*이용\s*금지", re.IGNORECASE),
    re.compile(r"ai학습\s*이용", re.IGNORECASE),
    re.compile(r"채널a\s*/\s*뉴스a", re.IGNORECASE),
    re.compile(r"jtbc\s*news", re.IGNORECASE),
    re.compile(r"jtbc\s*뉴스룸", re.IGNORECASE),
    re.compile(r"kbs\s*\d{4}\.\d{2}\.\d{2}\.", re.IGNORECASE),
]


GENERIC_PHRASES = [
    "jtbc 모바일라이브 시청하기",
    "jtbc유튜브 구독하기",
    "jtbc유튜브 커뮤니티",
    "공식 페이지",
    "모바일라이브",
    "유튜브 구독하기",
    "유튜브 커뮤니티",
    "지금 이슈의 현장을 실시간으로",
    "무단 전재 재배포 금지",
    "all rights reserved",
    "copyright",
    "연합뉴스tv",
    "yonhapnewstv",
    "뉴스의 시작",
    "특집 뉴스a",
    "뉴스top10",
    "시사쇼 정치다",
    "빠르고 정확한",
    "뉴스데스크",
    "뉴스투데이",
    "뉴스zip",
    "뉴스꾹",
    "한국경제tv",
    "실시간 라이브",
    "shorts",
    "ai 데이터 활용 금지",
    "ai학습 이용 금지",
]


def strip_boilerplate(text: str) -> str:
    """Remove broadcast boilerplate and links from analysis text."""
    cleaned = str(text or "")
    cleaned = URL_PATTERN.sub(" ", cleaned)
    for pattern in BOILERPLATE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    for phrase in GENERIC_PHRASES:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = MULTISPACE_PATTERN.sub(" ", cleaned).strip()
    return cleaned
