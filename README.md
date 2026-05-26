# YouTube Collection Pipeline for Iran War Coverage Study

이 저장소는 `2026-03-01 ~ 2026-03-21` 기간의 이란 전쟁 관련 한국 유튜브 뉴스 채널 영상을 수집하기 위한 1차 파이프라인입니다. 현재 단계의 목표는 분석이 아니라 `영상 메타데이터`, `최상위 댓글`, `자막/스크립트용 스텁 데이터셋`을 재실행 가능한 형태로 구축하는 것입니다.

## 1. 프로젝트 구조

```text
project/
  data/
    raw/
    processed/
    mart/
  config/
    channels_master.csv
    keywords_master.csv
  scripts/
    01_collect_videos.py
    02_collect_comments.py
    03_collect_transcripts_stub.py
  src/
    config_loader.py
    io_utils.py
    youtube_client.py
  logs/
  .env.example
  requirements.txt
  README.md
```

현재 실제 작업 루트는 이 저장소 루트이며, 위 `project/`는 구조 설명용 이름입니다.

## 2. 가상환경 생성 및 활성화

Windows PowerShell 기준:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

비활성화:

```powershell
deactivate
```

## 3. 패키지 설치

```powershell
pip install -r requirements.txt
```

## 4. `.env` 설정 방법

1. `.env.example` 파일을 복사해서 `.env` 파일을 만듭니다.
2. 아래처럼 YouTube Data API 키를 입력합니다.

```env
YOUTUBE_API_KEY=your_real_api_key
OUTPUT_FORMAT=csv
LOG_LEVEL=INFO
```

`OUTPUT_FORMAT`은 `csv` 또는 `parquet`를 사용할 수 있고, 기본 권장값은 `csv`입니다.

## 5. 설정 파일 수정 방법

### `config/channels_master.csv`

컬럼:

- `channel_type`
- `channel_name`
- `channel_id`
- `priority`
- `include_flag`
- `notes`

수집 대상에 포함할 채널은 `include_flag=1`로 둡니다.

### `channel_id` 채우는 방법

가장 안정적인 방법은 각 채널의 YouTube 페이지에서 실제 채널 ID(`UC...`)를 확인해 직접 넣는 것입니다.

1. 유튜브에서 해당 채널을 엽니다.
2. 채널 URL이 `https://www.youtube.com/channel/UC...` 형태면 `UC...` 전체를 복사합니다.
3. `@handle` 형태 URL만 보일 경우, 채널의 공유 링크나 페이지 소스, 또는 YouTube Data API 조회 결과에서 실제 `UC...` 채널 ID를 확인합니다.
4. `config/channels_master.csv`의 `channel_id` 칸에 입력합니다.

예시:

```csv
공영·지상파,KBS 뉴스,UC...실제채널ID...,1,1,입력완료
```

### `config/keywords_master.csv`

컬럼:

- `priority`
- `keyword`
- `note`

키워드는 이후 확장 가능하며, 코드에 하드코딩하지 않고 이 파일에서 관리합니다.

## 6. 실행 순서

### 0) 채널 ID 후보 찾기

`channel_id`가 비어 있으면 먼저 후보를 조회할 수 있습니다.

```powershell
python scripts/00_resolve_channel_ids.py
```

동작:

- `channels_master.csv`에서 `include_flag=1`이면서 `channel_id`가 빈 채널을 읽음
- 채널명 기준으로 유튜브 채널 검색
- 후보 결과를 `data/raw/channel_id_candidates.csv`에 저장
- 저장된 후보를 보고 실제 `UC...` 값을 `config/channels_master.csv`에 반영

### 1) 영상 수집

```powershell
python scripts/01_collect_videos.py
```

동작:

- `channels_master.csv`와 `keywords_master.csv`를 읽음
- `include_flag=1` 채널만 수집
- 채널 x 키워드 x 기간 기준 검색
- `video_id` 기준 중복 제거
- `data/raw/videos_raw.csv` 또는 `data/raw/videos_raw.parquet` 저장

### 2) 댓글 수집

```powershell
python scripts/02_collect_comments.py
```

동작:

- `videos_raw`를 읽음
- 각 `video_id`의 최상위 댓글만 수집
- `comment_id` 기준 중복 제거
- `data/raw/comments_raw.csv` 또는 `parquet` 저장

### 3) 자막/스크립트 스텁 생성

```powershell
python scripts/03_collect_transcripts_stub.py
```

동작:

- `videos_raw`를 읽음
- `provided_script -> public_caption -> stt -> none` 순서로 수집 시도
- `provided_script`는 `config/provided_scripts_master.csv` 기준으로 우선 반영
- 공개 자막은 `youtube-transcript-api`로 수집 시도
- STT는 아직 구조만 분리되어 있고 실제 전사는 추후 구현
- `data/raw/transcripts_raw.csv` 또는 `parquet` 저장

### 4) 자막 검토 큐 생성

```powershell
python scripts/04_prepare_transcript_review.py
```

동작:

- `transcripts_raw`를 읽음
- `public_caption`, `stt`처럼 검토가 필요한 텍스트를 추림
- `data/processed/transcripts_review_queue.csv` 생성
- 수동 검토용 컬럼 유지:
  - `manual_quality_label`
  - `manual_review_status`
  - `manual_corrected_text`
  - `manual_title_summary`
  - `manual_key_terms`
  - `manual_review_notes`
  - `final_use_flag`

### 5) 분석용 전사본 생성

```powershell
python scripts/05_build_transcript_analysis_ready.py
```

동작:

- `transcripts_raw`와 `transcripts_review_queue`를 합침
- 수동 보정 텍스트가 있으면 우선 사용
- 최종 분석 투입 여부를 `analysis_use_flag`로 표시
- `data/processed/transcripts_analysis_ready.csv` 생성

### 6) 텍스트 분석 코퍼스 생성

```powershell
python scripts/06_build_text_analysis_corpus.py
```

동작:

- `videos_raw`를 기본 모체로 사용
- 댓글이 있으면 영상 단위로 집계해서 결합
- 검토 완료된 전사만 `analysis_use_flag=1`로 반영
- 기본 분석 텍스트는 `title + description`
- 신뢰 가능한 전사가 있으면 여기에만 전사 텍스트를 추가
- `data/processed/text_analysis_corpus.csv` 생성

### 7) 보수적 1차 전처리

```powershell
python scripts/07_preprocess_text_corpus.py
```

동작:

- 원문은 유지
- `normalized`, `light_clean`, `char_count`, `token_count`, `flag` 컬럼만 추가
- 의미를 바꾸는 적극적 치환은 하지 않음
- `data/processed/text_analysis_corpus_preprocessed.csv` 생성

### 8) 2차 분석 입력셋 준비

```powershell
python scripts/08_prepare_analysis_inputs.py
```

동작:

- 1차 전처리 결과를 읽음
- `title/description`, `comments`, `transcript`의 사용 여부를 분리 판단
- `topic_input_text`, `frame_input_text`, `audience_input_text`, `analysis_bundle_text` 생성
- `data/processed/text_analysis_inputs_stage2.csv` 생성

## 7. 저장 파일 스키마

### `videos_raw`

- `video_id`
- `channel_id`
- `channel_name`
- `channel_type`
- `title`
- `description`
- `published_at`
- `view_count`
- `like_count`
- `comment_count`
- `duration`
- `url`
- `search_keyword`
- `collected_at`

### `comments_raw`

- `comment_id`
- `video_id`
- `author_display_name`
- `author_channel_id`
- `comment_text_raw`
- `like_count`
- `published_at`
- `collected_at`

### `transcripts_raw`

- `video_id`
- `transcript_source`
- `transcript_text_raw`
- `transcript_text_clean`
- `transcript_text_corrected`
- `transcript_quality`
- `stt_applied`
- `transcript_language_code`
- `transcript_language`
- `transcript_is_generated`
- `transcript_segment_count`
- `correction_status`
- `correction_notes`
- `text_needs_review`
- `transcript_error`
- `collected_at`

`transcript_source`는 아래 값만 쓰도록 설계했습니다.

- `public_caption`
- `provided_script`
- `stt`
- `none`

## 8. 로그와 재실행

- 각 스크립트는 `logs/` 아래에 실행 로그를 남깁니다.
- 이미 저장된 파일이 있으면 기존 데이터와 새 데이터를 합친 뒤 중복을 제거합니다.
- 현재 기준 중복 키:
  - 영상: `video_id`
  - 댓글: `comment_id`
  - 자막 스텁: `video_id`

## 9. 다음 단계 확장 방향

### STT 연결

다음 단계에서는 `03_collect_transcripts_stub.py`를 실제 수집기로 바꾸면 됩니다.

- 공개 자막이 있으면 `transcript_source=public_caption`
- 외부에서 확보한 스크립트가 있으면 `transcript_source=provided_script`
- 자막이 없으면 음성 추출 + STT 적용 후 `transcript_source=stt`
- 아무것도 없으면 `transcript_source=none`

추천 확장:

- `src/transcript_client.py` 추가
- `src/stt_client.py`에 실제 STT 엔진 연결
- 음성 다운로드, 세그먼트 정리, 품질 점수 계산 함수 분리

### 제공 스크립트와 보정 규칙

- `config/provided_scripts_master.csv`
  - `video_id` 기준으로 외부 확보 스크립트를 연결
- `config/transcript_replacements.csv`
  - 자주 틀리는 표기나 고유명사 보정 규칙 관리

### 분석 파이프라인 연결

이후에는 아래 순서로 붙이면 됩니다.

1. `data/raw` 기반 전처리 모듈 작성
2. 제목/설명/댓글 정제 데이터셋 생성
3. 토픽 분석용 코퍼스 구성
4. 프레임 분류용 피처 및 라벨 스키마 설계
5. 채널별 이슈 코퍼스 단위의 상대적 이념적 기울기 추정
6. Streamlit 대시보드 연결

## 10. 주의사항

- 이 프로젝트는 채널의 본질적 정치 성향을 판정하지 않습니다.
- 이후 분석 단계에서도 “정치 성향 판정” 대신 “이념적 기울기 추정” 또는 “상대적 위치 추정” 표현을 사용해야 합니다.
- 댓글은 채널 성향 판정용이 아니라 수용자 반응 분석용으로 우선 사용합니다.

## 11. 2026-05 운영 메모

- 현재 운영 우선순위는 `provided_script > public_caption > stt > none` 입니다.
- 다만 실제 연구 마감 전략은 다음처럼 가져갑니다.
  - 전수 분석의 기본 텍스트: `title + description`
  - 댓글 수집 가능 시 댓글 텍스트 병행
  - `provided_script`는 최우선 텍스트 소스
  - `public_caption`은 확보되면 사용하되, 네트워크 차단으로 전수 확보를 전제하지 않음
  - `stt`는 수동 검토와 보정 후 일부만 사용
- 따라서 2026년 5월 3주차 마감 기준 전수 코퍼스는 `제목/설명/댓글 중심`, 전사는 `부분 보강 자료`로 보는 것이 안전합니다.
