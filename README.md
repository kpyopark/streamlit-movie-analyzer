# Human Activity Monitoring System

실시간 영상 분석을 통한 Action 행위 판단 모니터링 시스템입니다. 이 시스템은 Streamlit을 기반으로 하며, Google Cloud Platform의 다양한 서비스들을 활용하여 영상 분석 및 음성 알림 기능을 제공합니다.

## 주요 기능

- 영상 파일 업로드 및 분석
- Gemini AI를 활용한 위험 상황 감지
- 위험 상황 발생 시 음성 알림 생성
- Google Cloud Storage를 통한 영상 저장
- 실시간 모니터링 및 알림

## 시스템 요구사항

### 필수 환경
- Python 3.7 이상
- Google Cloud Platform 계정
- 필요한 GCP API 활성화:
  - Vertex AI API
  - Cloud Storage API
  - Text-to-Speech API

### 필수 라이브러리
```bash
streamlit
google-cloud-storage
google-cloud-texttospeech
google-cloud-aiplatform
vertexai
pygame
python-dotenv
```

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/kpyopark/streamlit-movie-analyzer.git
cd streamlit-movie-analyzer
```

2. venv 환경 설정
```bash
virtualenv .venv -p 3.9
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
```

3. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

4. 환경 변수 설정
`.env` 파일을 생성하고 다음 변수들을 설정:
```
GCS_BUCKET=your-bucket-name   ## 임시로 동영상을 보관하는 곳.
PROJECT_ID=your-project-id
LOCATION=us-central1
```

## 실행 방법

1. Streamlit 앱 실행:
```bash
streamlit run main.py
```

2. 웹 브라우저에서 `http://localhost:8501` 접속

## 주요 컴포넌트 설명

### 1. 영상 업로드 및 저장
- 지원 파일 형식: MP4, AVI, MOV, MKV, WEBM
- 업로드된 파일은 임시 저장 후 GCS에 저장
- MIME 타입 자동 감지 기능

### 2. Gemini AI 분석
분석하는 주요 위험 상황:
- 위험한 행동
- 울거나 도움이 필요한 상황
- 위험한 물건 접근
- 아이가 혼자 있는 상황

### 3. 음성 알림 시스템
- Google Cloud TTS를 활용한 음성 변환
- Pygame 기반 오디오 재생
- 큐 시스템을 통한 순차적 알림 처리

## 반환 데이터 형식

분석 결과는 다음과 같은 JSON 형식으로 반환됩니다:
```json
{
    "alarm_needed": boolean,
    "severity": "high/medium/low",
    "situation": "상황 설명",
    "recommended_action": "권장 조치",
    "recommended_shout_message": "음성 알림 메시지"
}
```

## 에러 처리

- GCS 버킷 접근 오류 처리
- 파일 업로드 실패 처리
- 영상 분석 실패 처리
- 음성 변환 실패 처리

## 보안 고려사항

- GCP 인증 필요
- 적절한 IAM 권한 설정 필요
- 환경 변수를 통한 민감 정보 관리

## 제한사항

- 업로드 가능한 최대 파일 크기는 Streamlit 설정에 따름
- 실시간 스트리밍은 현재 지원되지 않음
- 동시 분석 요청 수 제한 있음

