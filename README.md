# 이란 전쟁 뉴스 채널 분석 대시보드

2026년 3월 이란 전쟁 관련 한국 유튜브 뉴스 채널의 보도 프레임, 담론 토픽, 이념적 기울기, 수용자 반응을 분석하고 Streamlit 대시보드로 시각화한 프로젝트입니다.

배포 링크: [grad-youtube-dashboard.streamlit.app](https://grad-youtube-dashboard.streamlit.app)

## 프로젝트 목적

이 프로젝트는 특정 채널의 본질적 정치 성향을 단정하지 않습니다. 분석 범위는 `2026.03.01 ~ 2026.03.21` 기간에 수집된 이란 전쟁 관련 유튜브 뉴스 데이터에 한정하며, 대시보드의 이념 지표는 해당 이슈 코퍼스 안에서 드러난 상대적 표현 방향을 보여주는 `이념적 기울기 추정`으로 해석합니다.

주요 목표는 다음과 같습니다.

- 채널별 보도 프레임 분포 확인
- 제목·설명 기반 메타데이터 토픽 분석
- 스크립트 기반 본문 토픽 분석
- 댓글 기반 수용자 반응 분석
- 이란 전쟁 이슈 내 상대적 이념적 기울기 시각화
- 여러 채널의 프레임, 주제, 반응 차이 비교

## 대시보드 주요 기능

- 채널별 상세 보기: 로고가 포함된 채널 목록에서 한 채널을 선택해 요약 카드와 그래프를 확인합니다.
- 채널 비교 보기: 여러 채널을 비교 칸에 담아 주요 지표를 나란히 비교합니다.
- 보도 프레임 분석: 안보·군사, 국제정치·외교, 경제·에너지, 투자·시장, 인도주의·민간피해, 기타/혼합 프레임을 비교합니다.
- 메타데이터 기준 주제: 영상 제목과 설명문에서 나타난 주요 주제를 확인합니다.
- 스크립트 기준 주제: 영상 본문 스크립트 기준으로 나타난 주제를 확인합니다.
- 핵심 단어 트리맵: 제목·설명 및 스크립트에서 반복적으로 등장한 단어를 시각화합니다.
- 댓글 반응 분석: 수용자 댓글을 지지·공감, 정보·해석, 우려·불안, 비판·반대, 기타/혼합 등으로 분류해 보여줍니다.
- 이념적 기울기: 채널을 보수/진보로 단정하지 않고, 해당 이슈에서의 상대적 위치를 연속 스케일로 표시합니다.

## 분석 대상

분석 대상은 한국어 유튜브 뉴스 채널 12개입니다.

- JTBC News
- KBS News
- MBC NEWS
- MBN News
- SBS Biz 뉴스
- SBS 뉴스
- YTN
- 뉴스TV CHOSUN
- 매일경제TV
- 연합뉴스TV
- 채널A News
- 한국경제TV

## 수집 데이터

수집 기간은 `2026.03.01 ~ 2026.03.21`입니다.

수집 및 분석에 사용한 주요 데이터는 다음과 같습니다.

- 메타데이터: 영상 제목, 설명문, 업로드 날짜, 채널명, 조회수, 댓글 수 등
- 댓글 데이터: 영상별 최상위 댓글
- 스크립트: 공개 자막, 제공 스크립트, 보완 전사 자료

데이터 수집은 YouTube Data API 기반으로 수행했으며, 채널, 키워드, 기간 조건을 조합해 이란 전쟁 관련 영상을 선별했습니다.

## 분석 방법

### 1. 토픽 분석

영상 제목·설명과 스크립트 본문을 분리해 토픽을 추출했습니다. 짧은 텍스트의 한계를 보완하기 위해 스크립트 기반 분석을 별도로 구성했으며, 조사, 접속어, 방송 포맷성 단어, 반복 표현 등은 전처리 과정에서 제거했습니다.

### 2. 프레임 분류

보도 프레임은 다음 범주로 분류했습니다.

- 안보·군사
- 국제정치·외교
- 경제·에너지
- 투자·시장
- 인도주의·민간피해
- 기타/혼합

### 3. 이념적 기울기 추정

이념적 기울기는 채널 자체의 정치 성향 판정이 아니라, 이란 전쟁 이슈 코퍼스에서 나타난 상대적 표현 방향입니다. 프레임 분포와 텍스트 단서의 영향을 점검하되, 특정 채널을 사전에 보수 또는 진보로 분류하는 방식은 사용하지 않았습니다.

### 4. 수용자 반응 분석

댓글은 채널 성향 판정용이 아니라 수용자 반응 분석용으로 사용했습니다. 댓글 반응은 정보·해석, 우려·불안, 비판·반대, 지지·공감, 기타/혼합 등으로 분류했습니다.

## 프로젝트 구조

```text
.
├─ config/
│  ├─ channels_master.csv
│  ├─ keywords_master.csv
│  ├─ provided_scripts_master.csv
│  └─ transcript_replacements.csv
├─ data/
│  ├─ raw/
│  └─ processed/
├─ outputs/
│  ├─ figures/
│  └─ tables/
├─ scripts/
│  ├─ 01_collect_videos.py
│  ├─ 02_collect_comments.py
│  ├─ 32_run_topic_analysis.py
│  ├─ 33_run_frame_analysis.py
│  ├─ 34_run_ideology_estimation.py
│  ├─ 35_build_analysis_summary_tables.py
│  └─ 38_run_audience_reaction_analysis.py
├─ src/
│  ├─ analyze/
│  ├─ app/
│  │  └─ streamlit_app.py
│  ├─ collect/
│  └─ preprocess/
├─ requirements.txt
└─ README.md
```

## 로컬 실행 방법

Windows PowerShell 기준입니다.

```powershell
cd C:\Users\PC2512\Desktop\Grad
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run src\app\streamlit_app.py
```

이미 가상환경이 만들어져 있다면 아래 명령어만 실행하면 됩니다.

```powershell
cd C:\Users\PC2512\Desktop\Grad
.\.venv\Scripts\python.exe -m streamlit run src\app\streamlit_app.py
```

## 주요 재분석 명령어

```powershell
.\.venv\Scripts\python.exe scripts\32_run_topic_analysis.py
.\.venv\Scripts\python.exe scripts\33_run_frame_analysis.py
.\.venv\Scripts\python.exe scripts\34_run_ideology_estimation.py
.\.venv\Scripts\python.exe scripts\35_build_analysis_summary_tables.py
.\.venv\Scripts\python.exe scripts\38_run_audience_reaction_analysis.py
```

## 배포

Streamlit Community Cloud에서 다음 설정으로 배포합니다.

- Repository: `peumuoe/Grad-youtube-dashboard`
- Branch: `main`
- Main file path: `src/app/streamlit_app.py`
- App URL: `grad-youtube-dashboard.streamlit.app`

GitHub에 수정사항을 반영하면 Streamlit Cloud가 자동으로 재배포합니다. 반영이 늦을 경우 앱 우측 하단 `Manage app`에서 `Reboot app`을 실행하면 됩니다.

## 해석 시 주의사항

- 본 대시보드는 연구·실습 목적의 탐색적 분석 결과입니다.
- 채널의 본질적 정치 성향을 판정하지 않습니다.
- 이념적 기울기는 특정 기간과 특정 이슈 안에서 나타난 상대적 위치입니다.
- 댓글은 전체 여론을 대표하지 않으며, 해당 영상에 결합된 플랫폼 내 수용자 반응으로 제한해 해석해야 합니다.
- 자동 분류와 토픽 모델링 결과는 전처리 기준과 데이터 수집 범위에 따라 달라질 수 있습니다.

## 최종 업데이트

- 대시보드 배포 링크 추가
- 채널 로고 기반 선택 UI 반영
- 단일 채널 보기와 복수 채널 비교 기능 정리
- 메타데이터 기준 주제와 스크립트 기준 주제 설명 정리
- YTN 등 일부 채널에서 요약 카드가 `nan`으로 표시될 수 있는 문제 보정
- 트리맵 핵심 단어 전처리 및 노이즈 단어 정제
