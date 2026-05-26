from __future__ import annotations

from collections import Counter
import base64
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyze.boilerplate_filters import strip_boilerplate
from src.analyze.topic_modeling import DEFAULT_STOPWORDS

TABLE_DIR = PROJECT_ROOT / "outputs" / "tables"
LOGO_DIR = PROJECT_ROOT / "src" / "app" / "assets" / "logos"
LOGO_MAP_PATH = LOGO_DIR / "channel_logo_map.json"
CHANNEL_NAME_ALIASES = {
    "YTN": "YTN",
    " YTN": "YTN",
    "KBS News": "KBS 뉴스",
    "뉴스TVCHOSUN": "TVCHOSUN News",
    "SBS Biz 뉴스": "SBS Biz",
}

FRAME_ORDER = [
    "안보·군사",
    "국제정치·외교",
    "경제·에너지",
    "투자·시장",
    "인도주의·민간피해",
    "기타/혼합",
]

FRAME_COLOR_MAP = {
    "안보·군사": "#3B82F6",
    "국제정치·외교": "#0D9488",
    "경제·에너지": "#F59E0B",
    "투자·시장": "#8B5CF6",
    "인도주의·민간피해": "#F97316",
    "기타/혼합": "#94A3B8",
}

REACTION_ORDER = [
    "비판/분노",
    "불안/공포",
    "지지/응원",
    "조롱/냉소",
    "정보보완/해설",
    "기타/혼합",
]

REACTION_COLOR_MAP = {
    "비판/분노": "#E11D48",
    "불안/공포": "#F59E0B",
    "지지/응원": "#10B981",
    "조롱/냉소": "#8B5CF6",
    "정보보완/해설": "#3B82F6",
    "기타/혼합": "#94A3B8",
}

FRAME_DESCRIPTION_MAP = {
    "안보·군사": "공습, 미사일, 병력, 방어 같은 군사 충돌 자체를 강조한 보도",
    "국제정치·외교": "정상회담, 협상, 제재, 외교 갈등처럼 국가 간 관계를 강조한 보도",
    "경제·에너지": "유가, 가스, 원유, 해협 통제처럼 실물경제와 에너지 이슈를 강조한 보도",
    "투자·시장": "주가, 환율, 반도체처럼 금융시장 반응을 강조한 보도",
    "인도주의·민간피해": "민간인 피해, 병원, 구호, 난민처럼 사람들의 피해를 강조한 보도",
    "기타/혼합": "여러 관점이 섞여 있거나 한 가지 틀로 보기 어려운 보도",
}

REACTION_DESCRIPTION_MAP = {
    "비판/분노": "정치 지도자나 전쟁 행위에 대한 비난과 분노",
    "불안/공포": "전쟁 확산, 경제 충격, 안보 위기에 대한 걱정",
    "지지/응원": "특정 국가나 행동에 대한 지지와 응원",
    "조롱/냉소": "비꼼, 조롱, 냉소적 반응",
    "정보보완/해설": "배경 설명, 맥락 설명, 원인 분석을 덧붙이는 반응",
    "기타/혼합": "한쪽으로 분류하기 어렵거나 여러 반응이 섞인 경우",
}

CHANNEL_TYPE_BADGE = {
    "공영·지상파": ("공영·지상파", "#E0F2FE", "#0369A1"),
    "종합편성": ("종합편성", "#F3E8FF", "#7E22CE"),
    "보도·경제전문": ("보도·경제전문", "#DCFCE7", "#166534"),
}

KEYWORD_EXTRA_STOPWORDS = {
    "이란",
    "이스라엘",
    "전쟁",
    "뉴스",
    "영상",
    "채널",
    "대한",
    "관련",
    "정부",
    "한국",
    "기자",
    "앵커",
    "보도",
    "오늘",
    "현지",
    "속보",
    "단독",
    "있습니다",
    "했습니다",
    "합니다",
    "됩니다",
    "나왔습니다",
    "보겠습니다",
    "전했습니다",
    "말했습니다",
    "하기",
    "통해",
    "위해",
    "대한민국",
    "카카오톡",
    "제보",
    "구독",
    "좋아요",
    "댓글",
    "라이브",
    "실시간",
    "shorts",
    "live",
    "있는",
    "지금",
    "추가",
    "중동",
    "이번",
    "이제",
    "것으로",
    "대해서",
    "대통령은",
    "대통령",
    "미국과",
    "미국이",
    "뉴스실시간",
    "jtbc실시간",
    "sbs실시간",
    "kbs뉴스",
    "jtbc뉴스",
    "연합뉴스tv",
    "채널a",
    "뉴스a",
    "itbc실시간",
    "itbc",
    "play",
}


@st.cache_data(show_spinner=False)
def _load_csv_cached(name: str, mtime_ns: int) -> pd.DataFrame:
    path = TABLE_DIR / name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def load_csv(name: str) -> pd.DataFrame:
    path = TABLE_DIR / name
    if not path.exists():
        return pd.DataFrame()
    stat = path.stat()
    return _load_csv_cached(name, stat.st_mtime_ns)


def normalize_channel_name(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_channel_column(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "channel_name" not in df.columns:
        return df
    cleaned_df = df.copy()
    cleaned_df["channel_name"] = cleaned_df["channel_name"].map(normalize_channel_name)
    return cleaned_df


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    return {
        "summary": normalize_channel_column(load_csv("channel_analysis_summary.csv")),
        "topic_summary": load_csv("topic_summary.csv"),
        "topic_video": normalize_channel_column(load_csv("topic_video_assignments.csv")),
        "topic_summary_script": load_csv("topic_summary_script.csv"),
        "topic_video_script": normalize_channel_column(load_csv("topic_video_assignments_script.csv")),
        "frame_dist": normalize_channel_column(load_csv("channel_frame_distribution.csv")),
        "audience_channel": normalize_channel_column(load_csv("channel_audience_reaction_distribution.csv")),
        "audience_video_summary": normalize_channel_column(load_csv("audience_video_reaction_summary.csv")),
    }


def apply_page_style() -> None:
    st.set_page_config(page_title="이란 전쟁 뉴스 채널 읽기", layout="wide")
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(91,143,249,0.08), transparent 28%),
                linear-gradient(180deg, #f8fafc 0%, #eef3f8 100%);
        }
        .block-container {
            max-width: 1320px;
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }
        section[data-testid="stSidebar"] {
            background: rgba(255,255,255,0.72);
            border-right: 1px solid rgba(226,232,240,0.9);
        }
        .hero {
            background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(245,248,252,0.96));
            border: 1px solid rgba(226,232,240,0.96);
            border-radius: 26px;
            padding: 24px 28px 22px 28px;
            box-shadow: 0 16px 34px rgba(15, 23, 42, 0.05);
            margin-bottom: 1.1rem;
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 850;
            color: #0f172a;
            margin-bottom: 0.35rem;
        }
        .hero-sub {
            color: #475569;
            font-size: 0.98rem;
            line-height: 1.55;
        }
        .channel-head {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 0.6rem;
        }
        .logo-dot {
            width: 56px;
            height: 56px;
            border-radius: 18px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #0f172a, #334155);
            color: white;
            font-size: 1.05rem;
            font-weight: 800;
            letter-spacing: 0.02em;
        }
        .channel-name {
            font-size: 1.9rem;
            font-weight: 850;
            color: #0f172a;
            line-height: 1.1;
        }
        .channel-sub {
            color: #64748b;
            font-size: 0.95rem;
            margin-top: 0.2rem;
        }
        .badge {
            display: inline-block;
            padding: 0.28rem 0.7rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            margin-right: 0.45rem;
        }
        .kpi-card {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(226,232,240,0.92);
            border-radius: 20px;
            padding: 16px 18px 14px 18px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
            min-height: 122px;
        }
        .kpi-label {
            color: #64748b;
            font-size: 0.83rem;
            font-weight: 700;
            margin-bottom: 0.42rem;
        }
        .kpi-value {
            color: #0f172a;
            font-size: 1.55rem;
            font-weight: 850;
            line-height: 1.15;
        }
        .kpi-sub {
            color: #475569;
            font-size: 0.9rem;
            margin-top: 0.42rem;
            line-height: 1.45;
        }
        .panel-head {
            background: #ffffff;
            border: 1px solid rgba(226,232,240,0.96);
            border-radius: 18px;
            padding: 14px 16px 12px 16px;
            margin-bottom: 1rem;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
        }
        .panel-shell {
            background: rgba(255,255,255,0.96);
            border: 1px solid rgba(226,232,240,0.92);
            border-radius: 22px;
            padding: 18px 18px 14px 18px;
            box-shadow: 0 12px 26px rgba(15, 23, 42, 0.05);
            margin-bottom: 0.9rem;
        }
        .tree-canvas {
            position: relative;
            width: 100%;
            height: 340px;
            background: #ffffff;
            border: none !important;
            border-radius: 18px;
            overflow: hidden;
            margin-top: 0.15rem;
            padding: 4px;
            box-shadow: none !important;
        }
        .tree-node {
            position: absolute;
            border-radius: 12px;
            outline: 3px solid #ffffff;
            box-shadow: none !important;
            padding: 10px 10px 8px 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: transform 120ms ease, filter 120ms ease;
        }
        .tree-node:hover {
            transform: translateY(-1px);
            filter: saturate(1.04);
        }
        .tree-label {
            color: #0f172a;
            font-size: 0.92rem;
            font-weight: 850;
            line-height: 1.15;
            word-break: keep-all;
        }
        .tree-share {
            color: rgba(15,23,42,0.82);
            font-size: 0.82rem;
            font-weight: 750;
        }
        .sidebar-logo-wrap {
            width: 38px;
            height: 38px;
            border-radius: 12px;
            overflow: hidden;
            background: #ffffff;
            border: 1px solid rgba(226,232,240,0.9);
            box-shadow: 0 6px 14px rgba(15, 23, 42, 0.06);
            display: flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 8px;
        }
        .sidebar-logo-wrap img {
            width: 100%;
            height: 100%;
            object-fit: contain;
            object-position: center;
            background: #ffffff;
            display: block;
            padding: 4px;
            box-sizing: border-box;
        }
        .sidebar-logo-grid {
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-top: 6px;
        }
        .sidebar-logo-link {
            display: inline-block;
            width: 38px;
            text-decoration: none;
        }
        .sidebar-logo-link.active .sidebar-logo-wrap {
            box-shadow: 0 0 0 2px rgba(59,130,246,0.28), 0 8px 16px rgba(15, 23, 42, 0.08);
            border-color: rgba(59,130,246,0.55);
        }
        .sidebar-brand-fallback {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.72rem;
            font-weight: 800;
            color: #ffffff;
        }
        .sidebar-logo-link {
            display: inline-block;
            text-decoration: none;
            margin-bottom: 8px;
        }
        .sidebar-logo-link.active .sidebar-logo-wrap {
            box-shadow: 0 0 0 2px rgba(59,130,246,0.28), 0 8px 16px rgba(15, 23, 42, 0.08);
            border-color: rgba(59,130,246,0.55);
        }
        .overview-card {
            background: linear-gradient(135deg, rgba(255,255,255,0.98), rgba(247,250,252,0.96));
            border: 1px solid rgba(226,232,240,0.96);
            border-radius: 22px;
            padding: 18px 20px 16px 20px;
            box-shadow: 0 12px 24px rgba(15, 23, 42, 0.04);
            margin: 0.2rem 0 1rem 0;
        }
        .overview-title {
            color: #475569;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            margin-bottom: 0.35rem;
        }
        .overview-text {
            color: #0f172a;
            font-size: 1.03rem;
            font-weight: 720;
            line-height: 1.55;
        }
        .section-title {
            color: #0f172a;
            font-size: 1.08rem;
            font-weight: 800;
            margin-bottom: 0.32rem;
            display: flex;
            align-items: center;
            gap: 0.45rem;
        }
        .section-caption {
            color: #64748b;
            font-size: 0.96rem;
            font-weight: 600;
            line-height: 1.45;
        }
        .title-help {
            cursor: help;
        }
        .title-help-icon {
            width: 20px;
            height: 20px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #e2e8f0;
            color: #475569;
            font-size: 0.75rem;
            font-weight: 800;
            line-height: 1;
        }
        .direction-pill {
            display: inline-block;
            padding: 0.4rem 0.78rem;
            border-radius: 999px;
            font-size: 0.84rem;
            font-weight: 800;
            margin-bottom: 0.65rem;
        }
        .direction-pill.progressive {
            background: #e0e7ff;
            color: #4338ca;
        }
        .direction-pill.neutral {
            background: #e2e8f0;
            color: #475569;
        }
        .direction-pill.conservative {
            background: #ffe4e6;
            color: #e11d48;
        }
        .direction-panel {
            padding: 0.2rem 0.2rem 0.25rem 0.2rem;
        }
        .direction-scale-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: #475569;
            font-size: 0.95rem;
            font-weight: 800;
            margin: 0.95rem 0 0.55rem 0;
        }
        .direction-scale-top .left {
            color: #4338ca;
        }
        .direction-scale-top .center {
            color: #475569;
        }
        .direction-scale-top .right {
            color: #e11d48;
        }
        .direction-bar-wrap {
            position: relative;
            margin: 0.45rem 0 0.7rem 0;
            padding-top: 1.7rem;
        }
        .direction-bar {
            position: relative;
            height: 68px;
            border-radius: 999px;
            overflow: hidden;
            background: linear-gradient(90deg, #e0e7ff 0%, #c7d2fe 50%, #fecdd3 50%, #ffe4e6 100%);
            border: 1px solid rgba(148,163,184,0.22);
        }
        .direction-center-line {
            position: absolute;
            top: 1.7rem;
            left: 50%;
            width: 2px;
            height: 68px;
            background: #cbd5e1;
            transform: translateX(-50%);
        }
        .direction-marker {
            position: absolute;
            top: 0;
            transform: translateX(-50%);
            z-index: 5;
        }
        .direction-marker-bubble {
            background: #0f172a;
            color: #ffffff;
            font-size: 0.84rem;
            font-weight: 800;
            padding: 0.38rem 0.7rem;
            border-radius: 999px;
            white-space: nowrap;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.18);
        }
        .direction-marker-stem {
            width: 3px;
            height: 19px;
            background: #0f172a;
            margin: 0 auto;
            border-radius: 999px;
        }
        .direction-scale-bottom {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 0.58rem;
            color: #94a3b8;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .direction-summary {
            margin-top: 0.82rem;
            color: #475569;
            font-size: 0.95rem;
            font-weight: 700;
            line-height: 1.5;
        }
        .video-card {
            background: linear-gradient(135deg, #ffffff, #fafcff);
            border: 1px solid rgba(226,232,240,0.92);
            border-radius: 20px;
            padding: 16px 16px 14px 16px;
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
            min-height: 210px;
        }
        .video-date {
            color: #64748b;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 0.4rem;
        }
        .video-title {
            color: #0f172a;
            font-size: 1rem;
            font-weight: 800;
            line-height: 1.45;
            margin-bottom: 0.7rem;
        }
        .video-meta {
            color: #475569;
            font-size: 0.88rem;
            line-height: 1.55;
        }
        .empty-state {
            background: rgba(255,255,255,0.92);
            border: 1px dashed #cbd5e1;
            border-radius: 24px;
            padding: 40px 28px;
            text-align: center;
            color: #475569;
            box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
            margin-top: 0.7rem;
        }
        .subsection-title {
            color: #0f172a;
            font-size: 1.18rem;
            font-weight: 850;
            margin: 1.2rem 0 0.35rem 0;
        }
        .subsection-caption {
            color: #64748b;
            font-size: 0.94rem;
            line-height: 1.55;
            margin-bottom: 0.9rem;
        }
        .status-card {
            background: linear-gradient(135deg, #ffffff, #f8fbff);
            border: 1px solid rgba(226,232,240,0.96);
            border-radius: 20px;
            padding: 16px 18px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
            margin-bottom: 1rem;
        }
        .status-title {
            color: #0f172a;
            font-size: 1rem;
            font-weight: 800;
            margin-bottom: 0.32rem;
        }
        .status-text {
            color: #475569;
            font-size: 0.92rem;
            line-height: 1.55;
        }
        .empty-title {
            color: #0f172a;
            font-size: 1.14rem;
            font-weight: 850;
            margin-bottom: 0.45rem;
        }
        div[data-testid="stPlotlyChart"] {
            margin-top: 0.3rem;
            margin-bottom: 0.9rem;
        }
        div[data-testid="stVerticalBlock"] > div:has(> div.panel-shell) {
            margin-bottom: 0.2rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(column, label: str, value: str, sub: str) -> None:
    with column:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def section_header(title: str, caption: str, help_text: str) -> None:
    st.markdown(
        (
            '<div class="panel-head">'
            '<div class="section-title">'
            f'<span>{title}</span>'
            f'<span class="title-help title-help-icon" title="{help_text}">i</span>'
            "</div>"
            f'<div class="section-caption">{caption}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
            <div class="hero-title">이란 전쟁 뉴스 채널 읽기</div>
            <div class="hero-sub">
                채널 하나를 고르면 이 채널이 이란 전쟁을 <b>어떤 주제로 많이 다뤘는지</b>,
                <b>어떤 시각으로 설명했는지</b>, 그리고 <b>시청자들이 어떤 반응을 보였는지</b>를
                한 화면에서 읽을 수 있습니다.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_logo_html(channel_name: str) -> str:
    data_uri = load_logo_data_uri(channel_name)
    if data_uri:
        return (
            '<div class="sidebar-logo-wrap">'
            f'<img src="{data_uri}" alt="{channel_name} logo" />'
            '</div>'
        )
    canonical_name = CHANNEL_NAME_ALIASES.get(channel_name.strip(), channel_name.strip())
    label, bg, fg = CHANNEL_BRAND_STYLE.get(
        canonical_name,
        (logo_text(channel_name), "linear-gradient(135deg, #334155, #64748B)", "#FFFFFF"),
    )
    return (
        '<div class="sidebar-logo-wrap">'
        f'<div class="sidebar-brand-fallback" style="background:{bg}; color:{fg};">{label}</div>'
        '</div>'
    )



def build_sidebar_logo_grid_html(channels: list[str], active_channel: str | None) -> str:
    parts = ['<div class="sidebar-logo-grid">']
    for channel in channels:
        active_class = ' active' if channel == active_channel else ''
        channel_param = quote(channel.strip())
        parts.append(
            f'<a class="sidebar-logo-link{active_class}" href="?selected_channel={channel_param}" target="_self" title="{channel.strip()}">'
            f'{sidebar_logo_html(channel)}'
            '</a>'
        )
    parts.append('</div>')
    return ''.join(parts)




def render_sidebar(summary_df: pd.DataFrame) -> str | None:
    none_option = "선택 안 함"

    st.sidebar.markdown("## 채널 선택")
    channels = sorted(summary_df["channel_name"].dropna().astype(str).unique().tolist()) if not summary_df.empty else []
    options = [none_option] + channels

    query_channel = st.query_params.get("selected_channel")
    if query_channel is None:
        query_channel = st.query_params.get("channel")
    if isinstance(query_channel, list):
        query_channel = query_channel[0] if query_channel else None
    query_channel = normalize_channel_name(query_channel) if query_channel else none_option
    if query_channel not in options:
        query_channel = none_option

    picker_key = "channel_picker_value"
    if picker_key not in st.session_state:
        st.session_state[picker_key] = query_channel

    picked = st.sidebar.selectbox("분석할 채널", options, key=picker_key)
    active_channel = None if picked == none_option else picked

    if picked != query_channel:
        if picked == none_option:
            st.query_params.clear()
        else:
            st.query_params["selected_channel"] = picked
        st.rerun()

    st.sidebar.markdown("### 빠르게 선택")
    st.sidebar.markdown(
        build_sidebar_logo_grid_html(channels, active_channel),
        unsafe_allow_html=True,
    )

    return active_channel


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="empty-state">
            <div class="empty-title">채널을 먼저 선택해 주세요</div>
            <div>왼쪽에서 채널 하나를 고르면, 그 채널의 보도 특징과 시청자 반응이 한 화면에 정리됩니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_subsection_header(title: str, caption: str) -> None:
    st.markdown(f'<div class="subsection-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subsection-caption">{caption}</div>', unsafe_allow_html=True)


def render_status_card(title: str, text: str) -> None:
    if "스크립트 기반 분석 사용 영상 수" in title or "실제 본문 분석" in text:
        return
    st.markdown(
        f"""
        <div class="status-card">
            <div class="status-title">{title}</div>
            <div class="status-text">{text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def filter_df(df: pd.DataFrame, channel: str) -> pd.DataFrame:
    if df.empty or "channel_name" not in df.columns:
        return df.copy()
    return df[df["channel_name"] == channel].copy()


def build_topic_name_map(topic_summary_df: pd.DataFrame) -> dict[str, str]:
    if topic_summary_df.empty:
        return {}

    topic_name_map: dict[str, str] = {}
    for row in topic_summary_df.itertuples(index=False):
        label = str(getattr(row, "topic_label", ""))
        terms = [term.strip() for term in str(getattr(row, "top_terms", "") or "").split(",") if term.strip()]
        joined = " ".join(terms[:8])

        if "호르무즈" in joined or "해협" in joined or "원유" in joined or "선박" in joined:
            topic_name = "호르무즈 해협과 원유 수송"
        elif "트럼프" in joined or "대통령" in joined or "미국" in joined:
            topic_name = "트럼프와 미국 대응"
        elif "이란" in joined and "이스라엘" in joined and ("미사일" in joined or "공습" in joined or "공격" in joined):
            topic_name = "이란-이스라엘 군사 충돌"
        elif "유가" in joined or "코스피" in joined or "반도체" in joined or "환율" in joined or "코스닥" in joined:
            topic_name = "전쟁의 시장·투자 충격"
        elif "기자" in joined or "채널" in joined or "social" in joined or "메일" in joined:
            topic_name = "채널 안내·부가 문구"
        elif "뉴스데스크" in joined or "뉴스투데이" in joined or "뉴스zip" in joined:
            topic_name = "뉴스 포맷·프로그램 묶음"
        elif "시사" in joined or "프로그램" in joined or "유튜브" in joined:
            topic_name = "프로그램 소개·부가 문구"
        elif "앵커" in joined or "있습니다" in joined or "그런" in joined or "그런데" in joined:
            topic_name = "진행 멘트·일반 설명"
        else:
            topic_name = " / ".join(terms[:3]) if terms else label

        topic_name_map[label] = topic_name
    return topic_name_map


def get_topic_display_name(topic_name_map: dict[str, str], label: str) -> str:
    if not label:
        return "주요 이슈"
    mapped = topic_name_map.get(label, label)
    return "기타/혼합 주제" if mapped == "채널 안내·부가 문구" else mapped


def classify_direction(score: float) -> str:
    if score >= 0.15:
        return "보수적 기울기"
    if score <= -0.15:
        return "진보적 기울기"
    return "혼합/중간"


def direction_explainer(score: float) -> str:
    direction = classify_direction(score)
    if direction == "보수적 기울기":
        return "안보·통제 쪽 표현이 상대적으로 더 많이 나타났습니다."
    if direction == "진보적 기울기":
        return "민간 피해·외교·중재 쪽 표현이 상대적으로 더 많이 나타났습니다."
    return "강하게 한쪽으로 치우치지 않고 여러 방향의 표현이 함께 나타났습니다."


def direction_short_caption(score: float) -> str:
    direction = classify_direction(score)
    if direction == "보수적 기울기":
        return "보수 쪽 표현이 상대적으로 더 자주 나타났습니다."
    if direction == "진보적 기울기":
        return "진보 쪽 표현이 상대적으로 더 자주 나타났습니다."
    return "한쪽으로 뚜렷하게 치우치지 않은 편입니다."


def direction_pill_html(score: float) -> str:
    direction = classify_direction(score)
    if direction == "보수적 기울기":
        return '<div class="direction-pill conservative">현재 읽기: 보수 쪽에 더 가까움</div>'
    if direction == "진보적 기울기":
        return '<div class="direction-pill progressive">현재 읽기: 진보 쪽에 더 가까움</div>'
    return '<div class="direction-pill neutral">현재 읽기: 중간 또는 혼합에 가까움</div>'


def build_direction_markup(score: float) -> str:
    clamped_score = max(-1.0, min(1.0, float(score)))
    marker_left = ((clamped_score + 1.0) / 2.0) * 100.0
    if clamped_score >= 0.15:
        marker_text = "보수 쪽에 더 가까움"
        bubble_bg = "#E11D48"
    elif clamped_score <= -0.15:
        marker_text = "진보 쪽에 더 가까움"
        bubble_bg = "#4338CA"
    else:
        marker_text = "중간에 가까움"
        bubble_bg = "#475569"

    return f"""
    <div class="direction-panel">
        {direction_pill_html(clamped_score)}
        <div class="direction-scale-top">
            <span class="left">진보 쪽</span>
            <span class="center">중간</span>
            <span class="right">보수 쪽</span>
        </div>
        <div class="direction-bar-wrap">
            <div class="direction-marker" style="left: {marker_left:.1f}%;">
                <div class="direction-marker-bubble" style="background:{bubble_bg};">{marker_text}</div>
                <div class="direction-marker-stem" style="background:{bubble_bg};"></div>
            </div>
            <div class="direction-bar"></div>
            <div class="direction-center-line"></div>
        </div>
        <div class="direction-scale-bottom">
            <span>진보</span>
            <span>중간</span>
            <span>보수</span>
        </div>
        <div class="direction-summary">
            현재 점수는 <b>{clamped_score:.3f}</b>이며, {direction_explainer(clamped_score)}
        </div>
    </div>
    """


def compress_minor_slices(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    threshold_pct: float = 3.0,
    other_label: str = "기타/미미",
    color_map: dict[str, str] | None = None,
    other_color: str = "#CBD5E1",
) -> tuple[pd.DataFrame, dict[str, str]]:
    chart_df = df.copy()
    minor_mask = chart_df[value_col] < threshold_pct
    if minor_mask.any():
        minor_sum = float(chart_df.loc[minor_mask, value_col].sum())
        major_df = chart_df.loc[~minor_mask].copy()
        other_row = pd.DataFrame([{category_col: other_label, value_col: minor_sum}])
        chart_df = pd.concat([major_df, other_row], ignore_index=True)
    else:
        chart_df = chart_df.copy()

    updated_color_map = dict(color_map or {})
    updated_color_map[other_label] = other_color
    return chart_df, updated_color_map


@st.cache_data(show_spinner=False)
def load_logo_map() -> dict[str, dict[str, str]]:
    if not LOGO_MAP_PATH.exists():
        return {}
    return json.loads(LOGO_MAP_PATH.read_text(encoding="utf-8"))


@st.cache_data(show_spinner=False)
def load_logo_data_uri(channel_name: str) -> str | None:
    normalized_name = channel_name.strip()
    canonical_name = CHANNEL_NAME_ALIASES.get(normalized_name, normalized_name)
    logo_map = load_logo_map()
    logo_info = logo_map.get(canonical_name)
    if not logo_info:
        return None
    logo_path = LOGO_DIR / logo_info["filename"]
    if not logo_path.exists():
        return None
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def channel_badge_html(channel_type: str) -> str:
    label, bg, fg = CHANNEL_TYPE_BADGE.get(channel_type, ("기타", "#E2E8F0", "#334155"))
    return f'<span class="badge" style="background:{bg}; color:{fg};">{label}</span>'


def logo_text(channel_name: str) -> str:
    cleaned = channel_name.replace("News", "").replace("??", "").strip()
    return cleaned[:3].upper()


CHANNEL_BRAND_STYLE = {
    "YTN": ("YTN", "linear-gradient(135deg, #1D4ED8, #2563EB)", "#FFFFFF"),
    "JTBC News": ("JTBC", "linear-gradient(135deg, #111827, #1F2937)", "#FFFFFF"),
    "KBS News": ("KBS", "linear-gradient(135deg, #1E3A8A, #2563EB)", "#FFFFFF"),
    "MBCNEWS": ("MBC", "linear-gradient(135deg, #0F172A, #334155)", "#FFFFFF"),
    "SBS ??": ("SBS", "linear-gradient(135deg, #0F766E, #14B8A6)", "#FFFFFF"),
    "TVCHOSUN News": ("TV?", "linear-gradient(135deg, #7C2D12, #C2410C)", "#FFFFFF"),
    "MBN News": ("MBN", "linear-gradient(135deg, #312E81, #6366F1)", "#FFFFFF"),
    "????TV": ("??", "linear-gradient(135deg, #1E293B, #475569)", "#FFFFFF"),
    "??A News": ("?A", "linear-gradient(135deg, #0F172A, #2563EB)", "#FFFFFF"),
    "SBS Biz": ("SBSB", "linear-gradient(135deg, #065F46, #10B981)", "#FFFFFF"),
    "????TV": ("??", "linear-gradient(135deg, #7C3AED, #A855F7)", "#FFFFFF"),
    "????TV": ("??", "linear-gradient(135deg, #92400E, #F59E0B)", "#FFFFFF"),
}


def channel_logo_badge(channel_name: str) -> str:
    data_uri = load_logo_data_uri(channel_name)
    if data_uri:
        return (
            '<div class="logo-dot" style="background:#ffffff; box-shadow: 0 10px 20px rgba(15, 23, 42, 0.10); padding:0; overflow:hidden;">'
            f'<img src="{data_uri}" alt="{channel_name} logo" style="width:100%; height:100%; object-fit:cover; display:block;" />'
            '</div>'
        )
    canonical_name = CHANNEL_NAME_ALIASES.get(channel_name.strip(), channel_name.strip())
    label, bg, fg = CHANNEL_BRAND_STYLE.get(
        canonical_name,
        (logo_text(channel_name), "linear-gradient(135deg, #334155, #64748B)", "#FFFFFF"),
    )
    return (
        f'<div class="logo-dot" style="background:{bg}; color:{fg}; '
        'box-shadow: 0 10px 20px rgba(15, 23, 42, 0.12);">'
        f"{label}</div>"
    )


def render_channel_header(channel_name: str, channel_type: str) -> None:
    st.markdown(
        f"""
        <div class="channel-head">
            {channel_logo_badge(channel_name)}
            <div>
                <div class="channel-name">{channel_name.strip()}</div>
                <div class="channel-sub">{channel_badge_html(channel_type)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_channel_summary_text(channel_row: pd.Series, topic_name_map: dict[str, str]) -> str:
    dominant_frame = str(channel_row.get("dominant_frame", "??/??"))
    dominant_topic = get_topic_display_name(topic_name_map, str(channel_row.get("dominant_topic", "")))
    dominant_reaction = str(channel_row.get("dominant_audience_reaction", "??/??"))
    direction = classify_direction(float(channel_row.get("ideology_relative_score", 0.0)))
    return (
        f"? ë¶ìí  ì±ë ë¶ìí  ì±ë {dominant_frame} ?ë¶ìí  ì±ë?, "
        f"?? {dominant_topic} ë¶ìí  ì±ë ????. "
        f"????? {dominant_reaction} ë¶ìí  ì±ë ????, "
        f"?????? {direction} ?ì í ì í¨?????."
    )



def render_channel_overview(channel_row: pd.Series, topic_name_map: dict[str, str]) -> None:
    summary_text = build_channel_summary_text(channel_row, topic_name_map)
    st.markdown(
        f"""
        <div class="overview-card">
            <div class="overview-title">?? ë¶ìí  ì±ë</div>
            <div class="overview-text">{summary_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_frame_donut(frame_dist_df: pd.DataFrame) -> go.Figure:
    chart_df = frame_dist_df.copy()
    chart_df["share_pct"] = chart_df["frame_share_within_channel"] * 100
    chart_df["primary_frame"] = pd.Categorical(chart_df["primary_frame"], categories=FRAME_ORDER, ordered=True)
    chart_df = chart_df.sort_values("primary_frame")
    chart_df, frame_colors = compress_minor_slices(
        chart_df,
        category_col="primary_frame",
        value_col="share_pct",
        threshold_pct=3.0,
        other_label="기타/미미",
        color_map=FRAME_COLOR_MAP,
        other_color="#CBD5E1",
    )
    chart_df = chart_df.sort_values("share_pct", ascending=True).copy()
    return go.Figure(
        go.Bar(
            x=chart_df["share_pct"],
            y=chart_df["primary_frame"],
            orientation="h",
            marker=dict(
                color=[frame_colors.get(label, "#CBD5E1") for label in chart_df["primary_frame"]],
                line=dict(color="rgba(255,255,255,0.85)", width=1),
            ),
            text=[f"{value:.1f}%" for value in chart_df["share_pct"]],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        )
    ).update_layout(
        height=255,
        margin=dict(l=80, r=28, t=6, b=6),
        xaxis_title="비중(%)",
        yaxis_title="",
        xaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
            gridcolor="rgba(148,163,184,0.18)",
        ),
        yaxis=dict(
            tickfont=dict(size=12, color="#334155"),
            automargin=True,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def build_reaction_donut(audience_channel_df: pd.DataFrame) -> go.Figure:
    chart_df = audience_channel_df.copy()
    chart_df["share_pct"] = chart_df["reaction_share_within_channel"] * 100
    chart_df["primary_reaction"] = pd.Categorical(chart_df["primary_reaction"], categories=REACTION_ORDER, ordered=True)
    chart_df = chart_df.sort_values("primary_reaction")
    chart_df, reaction_colors = compress_minor_slices(
        chart_df,
        category_col="primary_reaction",
        value_col="share_pct",
        threshold_pct=3.0,
        other_label="기타/미미",
        color_map=REACTION_COLOR_MAP,
        other_color="#CBD5E1",
    )
    chart_df = chart_df.sort_values("share_pct", ascending=True).copy()
    return go.Figure(
        go.Bar(
            x=chart_df["share_pct"],
            y=chart_df["primary_reaction"],
            orientation="h",
            marker=dict(
                color=[reaction_colors.get(label, "#CBD5E1") for label in chart_df["primary_reaction"]],
                line=dict(color="rgba(255,255,255,0.85)", width=1),
            ),
            text=[f"{value:.1f}%" for value in chart_df["share_pct"]],
            textposition="outside",
            hovertemplate="%{y}: %{x:.1f}%<extra></extra>",
        )
    ).update_layout(
        height=255,
        margin=dict(l=80, r=28, t=6, b=6),
        xaxis_title="비중(%)",
        yaxis_title="",
        xaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
            gridcolor="rgba(148,163,184,0.18)",
        ),
        yaxis=dict(
            tickfont=dict(size=12, color="#334155"),
            automargin=True,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def build_topic_bar(topic_video_df: pd.DataFrame, topic_name_map: dict[str, str]) -> go.Figure:
    chart_df = (
        topic_video_df.groupby("topic_label", as_index=False)
        .agg(video_count=("video_id", "count"))
        .sort_values("video_count", ascending=False)
        .head(5)
        .copy()
    )
    chart_df["topic_name"] = chart_df["topic_label"].apply(lambda label: get_topic_display_name(topic_name_map, str(label)))
    chart_df = chart_df.sort_values("video_count", ascending=True).copy()
    fig = go.Figure(
        go.Bar(
            x=chart_df["video_count"],
            y=chart_df["topic_name"],
            orientation="h",
            marker=dict(
                color="#3B82F6",
                line=dict(color="rgba(59,130,246,0.18)", width=1),
            ),
            opacity=0.92,
            hovertemplate="%{y}: %{x}개<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(l=160, r=20, t=8, b=18),
        xaxis_title="영상 수",
        yaxis_title="",
        yaxis=dict(
            tickfont=dict(size=13, color="#333333"),
            automargin=True,
        ),
        xaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
        ),
    )
    return fig


def _build_keyword_treemap(
    chart_df: pd.DataFrame,
    colorscale: list[list[float | int | str]],
) -> go.Figure:
    total_count = float(chart_df["count"].sum()) or 1.0
    chart_df = chart_df.copy()
    chart_df["share_pct"] = chart_df["count"] / total_count * 100.0
    fig = go.Figure(
        go.Treemap(
            labels=chart_df["keyword"],
            parents=[""] * len(chart_df),
            values=chart_df["count"],
            customdata=chart_df[["share_pct", "count"]].to_numpy(),
            texttemplate="%{label}<br>%{customdata[0]:.1f}%",
            textfont=dict(size=13, color="#0F172A"),
            textposition="middle center",
            hovertemplate="%{label}<br>?? %{customdata[0]:.1f}%<br>?? %{customdata[1]:,.0f}?<extra></extra>",
            marker=dict(
                colors=chart_df["count"],
                colorscale=colorscale,
                line=dict(color="#FFFFFF", width=3),
                showscale=False,
            ),
            root_color="#FFFFFF",
            tiling=dict(pad=3),
            pathbar=dict(visible=False),
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(l=0, r=0, t=4, b=4),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        template="plotly_white",
    )
    return fig


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _interpolate_hex(start: str, end: str, t: float) -> str:
    sr, sg, sb = _hex_to_rgb(start)
    er, eg, eb = _hex_to_rgb(end)
    r = round(sr + (er - sr) * t)
    g = round(sg + (eg - sg) * t)
    b = round(sb + (eb - sb) * t)
    return f"#{r:02X}{g:02X}{b:02X}"


KEYWORD_PARTICLE_SUFFIXES = (
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

KEYWORD_HARD_FILTERS = {
    "유튜브",
    "뉴스",
    "기사",
    "기자",
    "속보",
    "실시간",
    "라이브",
    "shorts",
    "live",
    "검색",
    "검색해",
    "검색하면",
    "제보",
    "제보가",
    "제보는",
    "카카오톡",
    "구독",
    "좋아요",
    "댓글",
    "당신",
    "당신의",
    "재배포",
    "재배포금지",
    "뉴스데스크",
    "뉴스투데이",
    "뉴스a",
    "채널a",
    "연합뉴스tv",
    "jtbc",
    "mbc",
    "ytn",
    "sbs",
    "sns",
    "social",
    "play",
    "뉴스1",
    "뉴스ip",
    "있습니다",
    "있다",
    "있다고",
    "했습니다",
    "합니다",
    "지금",
    "이제",
    "이번",
    "추가",
    "관련",
    "통해",
    "위해",
    "대통령",
    "것",
    "것으",
    "우리",
    "상황",
    "매일",
    "최고",
    "시간",
    "때문",
    "경우",
    "때문에",
    "대한",
    "대해",
    "이후",
    "당시",
    "계속",
    "또한",
    "때문에",
    "발행",
    "발행합니",
}


KEYWORD_ENDING_PATTERNS = (
    r"(있습니다|했습니다|합니다|였습니다|됩니다)$",
    r"(이라고|라고|이며|인데)$",
)


def normalize_keyword_token(token: str) -> str:
    token = token.strip().lower()
    if not token:
        return ""

    if re.fullmatch(r"[가-힣]+", token):
        for pattern in KEYWORD_ENDING_PATTERNS:
            token = re.sub(pattern, "", token)
        for suffix in KEYWORD_PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                token = token[: -len(suffix)]
                break

    token = token.strip()
    if len(token) < 2:
        return ""
    if token in KEYWORD_HARD_FILTERS:
        return ""
    return token


def extract_keyword_counter(text_series: pd.Series) -> Counter[str]:
    token_counter: Counter[str] = Counter()
    stopwords = (
        {str(word).strip().lower() for word in DEFAULT_STOPWORDS}
        | KEYWORD_EXTRA_STOPWORDS
        | KEYWORD_HARD_FILTERS
    )
    for text in text_series:
        tokens = re.findall(r"[가-힣A-Za-z]{2,}", text.lower())
        normalized_tokens = [normalize_keyword_token(token) for token in tokens]
        filtered_tokens = [
            token for token in normalized_tokens if token and token not in stopwords and len(token) >= 2
        ]
        token_counter.update(filtered_tokens)
    return token_counter

def _split_treemap_items(items: list[dict[str, float]]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    total = sum(float(item["value"]) for item in items)
    running = 0.0
    left: list[dict[str, float]] = []
    right: list[dict[str, float]] = []
    for item in items:
        if running < total / 2 or not left:
            left.append(item)
            running += float(item["value"])
        else:
            right.append(item)
    if not right and len(left) > 1:
        right.append(left.pop())
    return left, right


def _compute_treemap_layout(
    items: list[dict[str, float]],
    x: float,
    y: float,
    w: float,
    h: float,
) -> list[dict[str, float]]:
    if not items:
        return []
    if len(items) == 1:
        item = dict(items[0])
        item.update({"x": x, "y": y, "w": w, "h": h})
        return [item]

    total = sum(float(item["value"]) for item in items)
    left_items, right_items = _split_treemap_items(items)
    left_sum = sum(float(item["value"]) for item in left_items)
    ratio = 0.5 if total == 0 else left_sum / total

    if w >= h:
        left_w = w * ratio
        right_w = w - left_w
        return _compute_treemap_layout(left_items, x, y, left_w, h) + _compute_treemap_layout(
            right_items, x + left_w, y, right_w, h
        )

    top_h = h * ratio
    bottom_h = h - top_h
    return _compute_treemap_layout(left_items, x, y, w, top_h) + _compute_treemap_layout(
        right_items, x, y + top_h, w, bottom_h
    )


def _build_keyword_treemap_markup(
    chart_df: pd.DataFrame,
    color_start: str,
    color_end: str,
) -> str:
    data = chart_df.sort_values("count", ascending=False).copy()
    total_count = float(data["count"].sum()) or 1.0
    palette = [
        "#4F7DFF",
        "#6A92FF",
        "#84A6FF",
        "#9EB9FF",
        "#B8CCFF",
        "#D2E1FF",
        "#EAF1FF",
    ]
    items: list[dict[str, float]] = []
    rank_denom = max(len(data) - 1, 1)
    for idx, row in enumerate(data.itertuples(index=False)):
        share_pct = float(row.count) / total_count * 100.0
        rank_ratio = idx / rank_denom
        level = min(len(palette) - 1, int(rank_ratio * (len(palette) - 1)))
        color = palette[level]
        text_color = "#FFFFFF" if level <= 1 else "#0F172A"
        items.append(
            {
                "label": str(row.keyword),
                "value": float(row.count),
                "share_pct": share_pct,
                "color": color,
                "text_color": text_color,
            }
        )

    layout_items = _compute_treemap_layout(items, 0.0, 0.0, 100.0, 100.0)
    html_parts = ['<div class="tree-canvas">']
    for item in layout_items:
        style = (
            f"left:{item['x']:.2f}%; top:{item['y']:.2f}%; "
            f"width:{item['w']:.2f}%; height:{item['h']:.2f}%; "
            f"background:{item['color']}; color:{item['text_color']};"
        )
        title = f"{item['label']} | ?? {item['share_pct']:.1f}% | ?? {item['value']:,.0f}?"
        html_parts.append(
            f'<div class="tree-node" style="{style}" title="{title}">'
            f'<div class="tree-label">{item["label"]}</div>'
            f'<div class="tree-share">{item["share_pct"]:.1f}%</div>'
            "</div>"
        )
    html_parts.append("</div>")
    return "".join(html_parts)


def build_keyword_bar(topic_video_df: pd.DataFrame) -> go.Figure:
    text_series = (
        topic_video_df.get("topic_text_cleaned", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .apply(strip_boilerplate)
    )
    token_counter = extract_keyword_counter(text_series)

    keyword_rows = [{"keyword": word, "count": count} for word, count in token_counter.most_common(15)]
    if not keyword_rows:
        return go.Figure()

    chart_df = pd.DataFrame(keyword_rows).sort_values("count", ascending=False).copy()
    return _build_keyword_treemap(
        chart_df,
        [
            [0.0, "#DBEAFE"],
            [0.35, "#93C5FD"],
            [0.7, "#3B82F6"],
            [1.0, "#1D4ED8"],
        ],
    )


def build_keyword_treemap_markup(topic_video_df: pd.DataFrame) -> str:
    text_series = (
        topic_video_df.get("topic_text_cleaned", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .apply(strip_boilerplate)
    )
    token_counter = extract_keyword_counter(text_series)

    keyword_rows = [{"keyword": word, "count": count} for word, count in token_counter.most_common(15)]
    if not keyword_rows:
        return ""

    chart_df = pd.DataFrame(keyword_rows).sort_values("count", ascending=False).copy()
    return _build_keyword_treemap_markup(chart_df, "#DBEAFE", "#1D4ED8")


def build_volume_timeline(topic_video_df: pd.DataFrame) -> go.Figure:
    chart_df = topic_video_df.copy()
    chart_df["published_at"] = pd.to_datetime(chart_df["published_at"], errors="coerce")
    chart_df = chart_df.dropna(subset=["published_at"]).copy()
    chart_df["published_date"] = chart_df["published_at"].dt.date.astype(str)
    daily_df = chart_df.groupby("published_date", as_index=False).agg(video_count=("video_id", "count"))
    daily_df = daily_df.sort_values("published_date")

    fig = go.Figure(
        go.Scatter(
            x=daily_df["published_date"],
            y=daily_df["video_count"],
            mode="lines+markers",
            line=dict(color="#4338CA", width=3),
            marker=dict(size=7, color="#3B82F6"),
            fill="tozeroy",
            fillcolor="rgba(99,102,241,0.10)",
            hovertemplate="%{x}<br>영상 %{y}개<extra></extra>",
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(l=28, r=18, t=8, b=22),
        xaxis_title="날짜",
        yaxis_title="영상 수",
        xaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
        ),
        yaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
            gridcolor="rgba(148,163,184,0.18)",
        ),
    )
    return fig


def build_script_topic_bar(topic_video_df: pd.DataFrame, topic_name_map: dict[str, str]) -> go.Figure:
    chart_df = (
        topic_video_df.groupby("topic_label", as_index=False)
        .agg(video_count=("video_id", "count"))
        .sort_values("video_count", ascending=False)
        .head(5)
        .copy()
    )
    chart_df["topic_name"] = chart_df["topic_label"].apply(lambda label: get_topic_display_name(topic_name_map, str(label)))
    chart_df = chart_df.sort_values("video_count", ascending=True).copy()
    fig = go.Figure(
        go.Bar(
            x=chart_df["video_count"],
            y=chart_df["topic_name"],
            orientation="h",
            marker=dict(
                color="#14B8A6",
                line=dict(color="rgba(20,184,166,0.18)", width=1),
            ),
            opacity=0.92,
            hovertemplate="%{y}: %{x}?<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        margin=dict(l=160, r=20, t=8, b=18),
        xaxis_title="?? ?",
        yaxis_title="",
        yaxis=dict(
            tickfont=dict(size=13, color="#333333"),
            automargin=True,
        ),
        xaxis=dict(
            tickfont=dict(size=11, color="#64748B"),
            title_font=dict(size=12, color="#475569"),
        ),
    )
    return fig


def build_script_keyword_bar(topic_video_df: pd.DataFrame) -> go.Figure:
    text_series = (
        topic_video_df.get("topic_text_cleaned", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .apply(strip_boilerplate)
    )
    token_counter = extract_keyword_counter(text_series)

    keyword_rows = [{"keyword": word, "count": count} for word, count in token_counter.most_common(15)]
    if not keyword_rows:
        return go.Figure()

    chart_df = pd.DataFrame(keyword_rows).sort_values("count", ascending=False).copy()
    return _build_keyword_treemap(
        chart_df,
        [
            [0.0, "#DBEAFE"],
            [0.35, "#93C5FD"],
            [0.7, "#3B82F6"],
            [1.0, "#1D4ED8"],
        ],
    )


def build_script_keyword_treemap_markup(topic_video_df: pd.DataFrame) -> str:
    text_series = (
        topic_video_df.get("topic_text_cleaned", pd.Series(dtype=str))
        .fillna("")
        .astype(str)
        .apply(strip_boilerplate)
    )
    token_counter = extract_keyword_counter(text_series)

    keyword_rows = [{"keyword": word, "count": count} for word, count in token_counter.most_common(15)]
    if not keyword_rows:
        return ""

    chart_df = pd.DataFrame(keyword_rows).sort_values("count", ascending=False).copy()
    return _build_keyword_treemap_markup(chart_df, "#DBEAFE", "#1D4ED8")


def render_dashboard(data: dict[str, pd.DataFrame], channel: str) -> None:
    summary_df = filter_df(data["summary"], channel)
    topic_video_df = filter_df(data["topic_video"], channel)
    topic_video_script_df = filter_df(data["topic_video_script"], channel)
    frame_dist_df = filter_df(data["frame_dist"], channel)
    audience_channel_df = filter_df(data["audience_channel"], channel)
    if summary_df.empty:
        st.warning("선택한 채널의 데이터가 없습니다.")
        return

    channel_row = summary_df.iloc[0]
    topic_name_map = build_topic_name_map(data["topic_summary"])
    topic_name_map_script = build_topic_name_map(data["topic_summary_script"])
    channel_type = str(topic_video_df["channel_type"].dropna().iloc[0]) if not topic_video_df.empty else "기타"

    render_channel_header(channel, channel_type)
    st.markdown('<div style="height: 0.45rem;"></div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    metric_card(
        col1,
        "대표 보도 관점",
        str(channel_row.get("dominant_frame", "기타/혼합")),
        FRAME_DESCRIPTION_MAP.get(str(channel_row.get("dominant_frame", "기타/혼합")), ""),
    )
    metric_card(
        col2,
        "대표 주제",
        get_topic_display_name(topic_name_map, str(channel_row.get("dominant_topic", ""))),
        "이 채널에서 가장 자주 등장한 이슈 묶음",
    )
    metric_card(
        col3,
        "대표 댓글 반응",
        str(channel_row.get("dominant_audience_reaction", "기타/혼합")),
        REACTION_DESCRIPTION_MAP.get(str(channel_row.get("dominant_audience_reaction", "기타/혼합")), ""),
    )
    metric_card(
        col4,
        "해석 방향",
        classify_direction(float(channel_row.get("ideology_relative_score", 0.0))),
        direction_explainer(float(channel_row.get("ideology_relative_score", 0.0))),
    )

    st.markdown("")
    top_left, top_right = st.columns(2, gap="large")

    with top_left:
        section_header(
            "해석 방향",
            direction_short_caption(float(channel_row.get("ideology_relative_score", 0.0))),
            "이 점수는 채널의 본질적 정치 성향을 판정하는 값이 아니라, 이란 전쟁 이슈를 다룰 때 상대적으로 어떤 표현과 관점이 더 자주 등장했는지 보여주는 참고 지표입니다.",
        )
        st.markdown(build_direction_markup(float(channel_row.get("ideology_relative_score", 0.0))), unsafe_allow_html=True)

    with top_right:
        section_header(
            "보도 관점",
            f"가장 자주 등장한 관점은 {str(channel_row.get('dominant_frame', '기타/혼합'))}입니다.",
            "영상 내용을 여섯 가지 프레임으로 나눠 어떤 관점을 가장 자주 사용했는지 보여줍니다. 숫자가 높을수록 그 관점으로 설명한 보도가 많다는 뜻입니다.",
        )
        if frame_dist_df.empty:
            st.warning("프레임 데이터가 없습니다.")
        else:
            st.plotly_chart(build_frame_donut(frame_dist_df), use_container_width=True)

    st.markdown("")
    bottom_left, bottom_right = st.columns(2, gap="large")

    with bottom_left:
        section_header(
            "시청자 반응",
            f"가장 많이 나타난 반응은 {str(channel_row.get('dominant_audience_reaction', '기타/혼합'))}입니다.",
            "댓글을 여섯 가지 반응 유형으로 나눠 어떤 반응이 많았는지 보여줍니다. 채널 성향을 판정하는 용도가 아니라 시청자의 반응 분위기를 읽기 위한 지표입니다.",
        )
        if audience_channel_df.empty:
            st.warning("댓글 반응 데이터가 없습니다.")
        else:
            st.plotly_chart(build_reaction_donut(audience_channel_df), use_container_width=True)

    with bottom_right:
        section_header(
            "제목·설명 기준 주제",
            f"가장 많이 보인 주제는 {get_topic_display_name(topic_name_map, str(channel_row.get('dominant_topic', '')))}입니다.",
            "이 결과는 영상 본문 전체가 아니라 제목과 설명 텍스트를 묶어 분석한 결과입니다. 즉, 이 채널이 어떤 이슈를 어떤 이름으로 가장 자주 소개했는지 보여줍니다.",
        )
        if topic_video_df.empty:
            st.warning("주제 데이터가 없습니다.")
        else:
            st.plotly_chart(build_topic_bar(topic_video_df, topic_name_map), use_container_width=True)

    st.markdown("")
    extra_left, extra_right = st.columns(2, gap="large")

    with extra_left:
        section_header(
            "자주 나온 핵심 단어",
            "이 채널의 제목·설명에서 반복해서 많이 등장한 단어들입니다.",
            "제목과 설명 텍스트에서 불필요한 안내 문구를 제거한 뒤, 반복 빈도가 높은 단어를 집계한 결과입니다.",
        )
        if topic_video_df.empty:
            st.warning("단어 분석 데이터가 없습니다.")
        else:
            st.markdown(build_keyword_treemap_markup(topic_video_df), unsafe_allow_html=True)

    with extra_right:
        section_header(
            "날짜별 보도량",
            "이 채널이 이 이슈를 어느 시기에 더 많이 다뤘는지 보여줍니다.",
            "선택한 채널의 관련 영상이 날짜별로 몇 개씩 있었는지를 집계한 결과입니다.",
        )
        if topic_video_df.empty:
            st.warning("날짜별 집계 데이터가 없습니다.")
        else:
            st.plotly_chart(build_volume_timeline(topic_video_df), use_container_width=True)

    st.markdown("")
    render_subsection_header(
        "스크립트 기반 분석",
        "아래 결과는 제목·설명이 아니라 실제 영상 스크립트 본문을 기준으로 만든 분석입니다.",
    )

    script_doc_count = len(topic_video_script_df)
    if script_doc_count == 0:
        render_status_card(
            "이 채널은 현재 스크립트 기반 분석 대상이 없습니다",
            "수집된 스크립트가 없거나, 분석에 사용할 만큼 정리된 스크립트가 아직 없는 상태입니다. 그래서 아래 스크립트 기반 주제/핵심 단어 그래프는 이 채널에서 표시되지 않습니다.",
        )
        return

    script_left, script_right = st.columns(2, gap="large")

    with script_left:
        dominant_script_topic = (
            topic_video_script_df.groupby("topic_label")["video_id"].count().sort_values(ascending=False).index[0]
        )
        section_header(
            "스크립트 기준 주제",
            f"스크립트 본문 기준으로는 {get_topic_display_name(topic_name_map_script, str(dominant_script_topic))} 주제가 가장 많이 보입니다.",
            "이 결과는 제목·설명이 아니라 수집된 영상 스크립트 본문을 기반으로 만든 주제 분석입니다. 실제 보도 내용에서 어떤 이슈가 많이 등장했는지 보는 데 더 가깝습니다.",
        )
        st.plotly_chart(build_script_topic_bar(topic_video_script_df, topic_name_map_script), use_container_width=True)

    with script_right:
        section_header(
            "스크립트 핵심 단어",
            "영상 본문 스크립트에서 반복해서 많이 등장한 표현입니다.",
            "제목·설명 문구가 아니라 실제 스크립트 본문에서 나온 단어 빈도를 집계한 결과입니다.",
        )
        st.markdown(build_script_keyword_treemap_markup(topic_video_script_df), unsafe_allow_html=True)


def main() -> None:
    apply_page_style()
    data = load_data()
    render_header()
    selected_channel = render_sidebar(data["summary"])
    if not selected_channel:
        render_empty_state()
        return
    render_dashboard(data, selected_channel)


if __name__ == "__main__":
    main()
