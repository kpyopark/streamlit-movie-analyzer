import streamlit as st
import os
from google.cloud import storage
from google.cloud import texttospeech
from google.cloud import aiplatform
import tempfile
import json
import uuid
from vertexai.generative_models import GenerativeModel, Part, SafetySetting
import vertexai
import pygame
import time
from dotenv import load_dotenv
import mimetypes
import os

load_dotenv()

# 환경 변수 설정
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "")

vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel(
    "gemini-1.5-flash-002",
)

def initialize_gcs_client():
    """Google Cloud Storage 클라이언트 초기화"""
    return storage.Client(project=PROJECT_ID)

def get_mime_type(file_path):
    """파일의 MIME 타입을 감지"""
    mime_type = mimetypes.guess_type(file_path)[0]
    if mime_type is None:
        # 알 수 없는 형식의 경우 기본값으로 video/mp4 반환
        return "video/mp4"
    return mime_type

def upload_to_gcs(bucket_name, source_file, destination_blob_name):
    """파일을 GCS에 업로드"""
    storage_client = initialize_gcs_client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{destination_blob_name}"

def analyze_video_with_gemini(video_gcs_uri, mime_type):
    prompt = """
    이 비디오를 분석하여 어린이 보살핌 서비스에 필요한 알람 상황을 찾아주세요.
    다음과 같은 상황에 특히 주의해주세요:
    1. 아이가 위험한 행동을 하는 경우
    2. 아이가 울거나 도움이 필요해 보이는 경우
    3. 아이가 위험한 물건에 접근하는 경우
    4. 아이가 혼자 있는 경우
    
    결과를 다음 JSON 형식으로 반환해주세요:
    {
        "alarm_needed": boolean,
        "severity": "high/medium/low",
        "situation": "상황 설명",
        "recommended_action": "권장 조치"
    }
    """
    generation_config = {
        "max_output_tokens": 8192,
        "temperature": 1,
        "top_p": 0.95,
    }

    safety_settings = [
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=SafetySetting.HarmBlockThreshold.OFF
        ),
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=SafetySetting.HarmBlockThreshold.OFF
        ),
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=SafetySetting.HarmBlockThreshold.OFF
        ),
        SafetySetting(
            category=SafetySetting.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=SafetySetting.HarmBlockThreshold.OFF
        ),
    ]

    response = model.generate_content(
        [prompt, Part.from_uri(video_gcs_uri, mime_type=mime_type)],
        generation_config=generation_config,
        safety_settings=safety_settings,
        stream=False,
    )
    
    try:
        return json.loads(response.text)
    except:
        return None

def text_to_speech(text):
    """텍스트를 음성으로 변환"""
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    voice = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    
    temp_audio_path = f"temp_audio_{uuid.uuid4()}.mp3"
    with open(temp_audio_path, "wb") as out:
        out.write(response.audio_content)
    
    return temp_audio_path

def play_audio(audio_file):
    """음성 파일 재생"""
    pygame.mixer.init()
    pygame.mixer.music.load(audio_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
    pygame.mixer.quit()
    os.remove(audio_file)  # 임시 파일 삭제

def main():
    st.title("Human Activity 모니터링 시스템")
    
    # MIME 타입 매핑 초기화
    mimetypes.init()
    
    # 지원하는 비디오 형식 확장
    uploaded_file = st.file_uploader("동영상 파일을 선택하세요", 
                                   type=["mp4", "avi", "mov", "mkv", "webm"])
    
    if uploaded_file:
        st.video(uploaded_file)
        
        if st.button("분석 시작"):
            with st.spinner("동영상을 분석 중입니다..."):
                # 임시 파일로 저장
                temp_path = f"temp_video_{uuid.uuid4()}.{uploaded_file.name.split('.')[-1]}"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                # MIME 타입 감지
                mime_type = get_mime_type(temp_path)
                st.info(f"비디오 형식: {mime_type}")
                
                # GCS에 업로드
                gcs_uri = upload_to_gcs(
                    GCS_BUCKET,
                    temp_path,
                    f"temp_videos/{os.path.basename(temp_path)}"
                )
                
                # 감지된 MIME 타입으로 비디오 분석
                analysis_result = analyze_video_with_gemini(gcs_uri, mime_type)
                
                # 임시 파일 삭제
                os.remove(temp_path)
                
                if analysis_result:
                    st.json(analysis_result)
                    
                    if analysis_result.get("alarm_needed"):
                        alert_text = (
                            f"경고! {analysis_result['situation']} "
                            f"권장 조치: {analysis_result['recommended_action']}"
                        )
                        
                        # 텍스트를 음성으로 변환하고 재생
                        audio_file = text_to_speech(alert_text)
                        play_audio(audio_file)
                        
                        st.warning(alert_text)
                else:
                    st.error("비디오 분석 중 오류가 발생했습니다.")

if __name__ == "__main__":
    main()