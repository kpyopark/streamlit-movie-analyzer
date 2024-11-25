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
import threading
import queue

load_dotenv()

# 환경 변수 설정
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
PROJECT_ID = os.getenv("PROJECT_ID", "")
LOCATION = os.getenv("LOCATION", "us-central1")

vertexai.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel(
    "gemini-1.5-flash-001",
)
storage_client = storage.Client()

def get_mime_type(file_path):
    """파일의 MIME 타입을 감지"""
    mime_type = mimetypes.guess_type(file_path)[0]
    if mime_type is None:
        # 알 수 없는 형식의 경우 기본값으로 video/mp4 반환
        return "video/mp4"
    return mime_type


def clean_bucket_name(bucket_name):
    """
    GCS 버킷 이름에서 gs:// 접두사를 제거하고 깨끗한 버킷 이름을 반환
    
    Args:
        bucket_name (str): 원본 버킷 이름
    Returns:
        str: 정제된 버킷 이름
    """
    # gs:// 접두사 제거
    cleaned_name = bucket_name.replace('gs://', '').strip()
    # 후행 슬래시 제거
    cleaned_name = cleaned_name.rstrip('/')
    return cleaned_name

def check_bucket_exists(bucket_name):
    """버킷 존재 여부 및 위치 확인"""
    try:
        bucket_name = clean_bucket_name(bucket_name)
        bucket = storage_client.get_bucket(bucket_name)
        bucket_location = bucket.location.lower()
        st.info(f"버킷 위치: {bucket_location}")
        
        # 예상 위치와 다른 경우 경고
        if bucket_location != "asia-northeast3":
            st.warning(f"버킷이 예상 위치(asia-northeast3)와 다른 리전({bucket_location})에 있습니다.")
        
        return bucket
    except Exception as e:
        print(e)
        st.error(f"버킷을 찾을 수 없습니다: {bucket_name}")
        return None

def upload_to_gcs(bucket_name, source_file, destination_blob_name):
    """파일을 GCS에 업로드"""
    bucket = check_bucket_exists(bucket_name)
    blob = bucket.blob(destination_blob_name)
    print(f"Uploading {source_file} to {destination_blob_name}...")
    blob.upload_from_filename(source_file)
    return f"gs://{bucket_name}/{destination_blob_name}"

def parse_gemini_response(json_str):
    start_index = json_str.find('```json') + 7
    end_index = json_str.find('```', start_index)
    if start_index == -1 or end_index == -1:
        return json.loads(json_str)
    json_str = json_str[start_index:end_index].strip()
    print('cleaned string.')
    print(json_str)
    try:
        return_json = json.loads(cleaned_string)
    except Exception as e:
        print(f'parsing error... {e}')
        return_json = {}
    return return_json

def analyze_video_with_gemini(video_gcs_uri, mime_type):
    prompt = """
    이 비디오를 분석하여 어린이 보살핌 서비스에 필요한 알람 상황을 찾아주세요.
    다음과 같은 상황에 특히 주의해주세요:
    1. 아이가 위험한 행동을 하는 경우
    2. 아이가 울거나 도움이 필요해 보이는 경우
    3. 아이가 위험한 물건에 접근하는 경우
    4. 아이가 혼자 있는 경우
    
    결과를 다음 JSON 형식으로 반환해주세요 (제일 중요한 한가지 Item만 반환해주세요.):
    {
        "alarm_needed": boolean,
        "severity": "high/medium/low",
        "situation": "상황 설명",
        "recommended_action": "권장 조치",
	    "recommended_shout_message": "해당하는 상황에 맞는 애들에게 필요한 메시지. 스피커로 나올 메시지임"
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
    print('response_text')
    print(response.text)
    try:
        return parse_gemini_response(response.text)
    except Exception as e:
        print(e)
        print("Error parsing response")
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

class AudioPlayer:
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.is_playing = False
        pygame.mixer.init()

    def play_audio_file(self, audio_file):
        try:
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
        finally:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
            if os.path.exists(audio_file):
                os.remove(audio_file)

    def play(self, audio_file):
        if self.is_playing:
            self.audio_queue.put(audio_file)
        else:
            self.is_playing = True
            threading.Thread(target=self._play_thread, args=(audio_file,), daemon=True).start()

    def _play_thread(self, initial_audio_file):
        try:
            self.play_audio_file(initial_audio_file)
            
            while not self.audio_queue.empty():
                next_audio = self.audio_queue.get()
                self.play_audio_file(next_audio)
        finally:
            self.is_playing = False

def main():
    st.title("Human Activity 모니터링 시스템")
    
    # Streamlit 세션 상태에 AudioPlayer 인스턴스 저장
    if 'audio_player' not in st.session_state:
        st.session_state.audio_player = AudioPlayer()
    
    mimetypes.init()
    
    uploaded_file = st.file_uploader("동영상 파일을 선택하세요", 
                                   type=["mp4", "avi", "mov", "mkv", "webm"])
    
    if uploaded_file:
        st.video(uploaded_file)
        
        if st.button("분석 시작"):
            upload_status = st.empty()
            analysis_status = st.empty()
            
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(
                temp_dir, 
                f"temp_video_{uuid.uuid4()}.{uploaded_file.name.split('.')[-1]}"
            )
            
            try:
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                
                mime_type = get_mime_type(temp_path)
                st.info(f"비디오 형식: {mime_type}")
                
                with upload_status:
                    with st.spinner("GCS에 동영상 업로드 중..."):
                        gcs_uri = upload_to_gcs(
                            GCS_BUCKET,
                            temp_path,
                            f"videos/{os.path.basename(temp_path)}"
                        )
                st.success("GCS 업로드 완료!")
                
                with analysis_status:
                    with st.spinner("Gemini AI로 동영상 분석 중..."):
                        analysis_result = analyze_video_with_gemini(gcs_uri, mime_type)
                
                print(analysis_result)
                if analysis_result:
                    st.success("동영상 분석 완료!")
                    st.json(analysis_result)
                    
                    if analysis_result.get("alarm_needed"):
                        alert_text = analysis_result['recommended_shout_message']
                        audio_file = text_to_speech(alert_text)
                        
                        # 오디오 파일 재생
                        st.audio(audio_file, format="audio/mp3")
                        st.session_state.audio_player.play(audio_file)
                        
                        st.warning(alert_text)
                else:
                    st.error("비디오 분석 중 오류가 발생했습니다.")
                    
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(temp_dir):
                    os.rmdir(temp_dir)

if __name__ == "__main__":
    main()