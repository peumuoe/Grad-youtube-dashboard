# Project Overview

## Project Name
2026년 3월 이란 전쟁 관련 한국 유튜브 뉴스 채널의 담론 지형, 프레임, 이념적 기울기 및 수용자 반응 분석

## Goal
이 프로젝트는 YouTube Data API를 활용해 2026년 3월 이후 이란 전쟁 관련 한국어 유튜브 뉴스 영상을 수집하고, 영상 제목·설명·메타데이터·댓글을 분석하여 다음을 수행한다.

1. 주요 담론 토픽 추출
2. 채널별 프레임 분포 분석
3. 이란 전쟁 이슈에서의 상대적 이념적 기울기 추정
4. 댓글 기반 수용자 반응 분석
5. Streamlit 대시보드 구현

## Important Rules
- 채널의 본질적 정치 성향을 판정하지 않는다.
- “정치 성향 판정” 대신 “이념적 기울기 추정” 또는 “상대적 위치 추정”이라는 표현을 사용한다.
- 분석 대상은 “이란 전쟁 관련 이슈 코퍼스”에 한정한다.
- 댓글은 채널 자체의 성향 판정용이 아니라 수용자 반응 분석용으로 우선 사용한다.
- 프레임(frame)과 이념적 기울기(ideology)는 분리된 분석 축으로 다룬다.
- 모든 주요 단계 결과는 CSV 또는 JSON 파일로 저장한다.
- 코드와 설정은 최대한 하드코딩하지 말고 config 기반으로 작성한다.
- 모듈화된 구조를 유지한다.

## Recommended Project Structure
- data/raw
- data/processed
- outputs/figures
- outputs/tables
- src/collect
- src/preprocess
- src/analyze
- src/app

## Analysis Axes
### 1. Topic Analysis
- 입력 데이터: 영상 제목 + 설명, 댓글
- 방법: BERTopic 우선, 실패 시 TF-IDF + LDA/NMF 대체

### 2. Frame Classification
기본 프레임 범주:
- 안보·군사
- 국제정치·외교
- 경제·에너지
- 투자·시장
- 인도주의·민간피해
- 기타/혼합

### 3. Ideology Estimation
이념적 기울기 점수는 채널의 본질을 규정하는 라벨이 아니라, 이란 전쟁 이슈에서 드러난 상대적 위치 추정이다.

권장 범주:
- 진보적 기울기
- 혼합/중간
- 보수적 기울기

## Comment Selection Rules
영상별 상위 댓글 선정 기준:
- relevance 기준 상위 30개
- time 기준 최신 20개
- 병합 후 중복 제거
- 동일 작성자 최대 2개
- 15자 미만 제외
- 광고성/반복성/URL-only 댓글 제외

## Coding Style
- Python 코드에 type hint 사용
- 함수별 역할 분리
- 예외 처리 포함
- 주요 단계 logging 추가
- 저장 경로 자동 생성
- notebook 없이도 재실행 가능한 구조 지향

## Expected Deliverables
1. YouTube 데이터 수집 코드
2. 전처리 코드
3. 토픽 분석 코드
4. 프레임 분류 코드
5. 이념적 기울기 추정 코드
6. Streamlit 앱
7. README 및 실행 가이드

## Work Priority
1. 폴더 구조 확인
2. YouTube API 수집 모듈 작성
3. 전처리 모듈 작성
4. 분석 모듈 작성
5. 대시보드 작성
6. 결과 저장 및 문서화

## Output Preference
- 먼저 폴더 구조와 파일 생성
- 다음으로 설정 파일 작성
- 그다음 수집 코드
- 이후 전처리/분석/대시보드 순서로 진행
- 각 단계마다 바로 실행 가능한 코드 우선 제시