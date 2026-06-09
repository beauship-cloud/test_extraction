import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Cognitive Aids NMA Extraction Tool", layout="wide")

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def init_connection():
    # Streamlit Cloud의 보안 비밀번호(Secrets) 기능을 사용할 예정입니다.
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    client = gspread.authorize(creds)
    return client

try:
    client = init_connection()
    sheet_url = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit?usp=sharing"
    sh = client.open_by_url(sheet_url)
    worksheet = sh.sheet1
except Exception as e:
    st.error(f"구글 시트 연결 실패! 에러내용: {e}")

st.title("☁️ NMA 데이터 추출기 (구글 시트 연동 완전판)")
st.markdown("여기에 입력하는 데이터는 팀 공유 구글 스프레드시트로 실시간 전송됩니다.")

with st.form("full_extraction_form", clear_on_submit=True):
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 1. 일반 특성 (General)", 
        "🛠️ 2. 중재 & 구현 (Interventions)", 
        "📈 3. 결과 (Outcomes)", 
        "⚖️ 4. 비뚤림 위험 (Quality/RoB)"
    ])
    
    with tab1:
        st.subheader("연구 기본 정보")
        c1, c2, c3 = st.columns(3)
        with c1:
            author = st.text_input("Lead Author Last Name", placeholder="예: Harari")
            year = st.number_input("Year", min_value=1990, max_value=2030, value=2024, step=1)
            country = st.text_input("Country", placeholder="예: Canada")
        with c2:
            study_type = st.selectbox("Study Type", ["RCT", "pilot RCT", "crossover", "observational", "other"])
            setting = st.text_input("Simulation Setting", placeholder="예: ICU, ED")
            scenario = st.text_input("Scenario", placeholder="예: Cardiac Arrest")
        with c3:
            n_size = st.number_input("전체 샘플 수 (N)", min_value=0, step=1)
            individual_team = st.selectbox("Individual vs Team", ["Individual", "Team"])

    with tab2:
        st.subheader("보조도구 특성 및 NMA 노드 분류")
        c4, c5 = st.columns(2)
        with c4:
            aid_name = st.text_input("Name of Cognitive Aid", placeholder="예: 고유 앱 이름 또는 도구 명칭")
            format_type = st.selectbox("Format", ["paper", "digital", "unclear"])
            training_intensity = st.selectbox("Training Intensity", ["0 = none/minimal (<15 min)", "1 = brief familiarization (≤60 min)", "2 = structured workshop", "Not specified"])
        with c5:
            st.markdown("**📌 NMA 네트워크 노드 매핑 (중요!)**")
            arm1 = st.selectbox("Arm 1 분류", ["Control", "Static", "Dynamic"])
            arm2 = st.selectbox("Arm 2 분류", ["Static", "Control", "Dynamic"])
            arm3 = st.selectbox("Arm 3 (있을 때만 선택)", ["없음", "Control", "Static", "Dynamic"])

    with tab3:
        st.subheader("결과 지표 데이터 기입")
        out_adherence = st.text_area("Outcome Measure: Adherence (수행도/준수율 관련 결과)", placeholder="텍스트나 수치 입력")
        out_time = st.text_area("Outcome Measure: Time (소요 시간 관련 결과)", placeholder="텍스트나 수치 입력")

    with tab4:
        st.subheader("품질 및 비뚤림 위험 평가 (RoB)")
        rob_type = st.radio("평가 도구 선택", ["RoB-2 (RCT 연구용)", "ROBBINS-I (관찰 연구용)"])
        rob_rating = st.selectbox("👉 최종 Overall Rating 결정", ["Low risk / Low", "Some concerns / Moderate", "High risk / Serious", "평가 안함"])

    st.markdown("---")
    submitted = st.form_submit_button("💾 구글 시트로 데이터 전송하기", use_container_width=True)

    if submitted:
        if not author:
            st.error("❌ 에러: 저자 이름(Lead Author Last Name)은 필수 입력 항목입니다!")
        else:
            try:
                if len(worksheet.get_all_values()) == 0:
                    headers = [
                        "Timestamp", "Author", "Year", "Study_Type", "Country", "Setting", 
                        "Scenario", "N", "Indiv_or_Team", "Aid_Name", "Format", "Arm1", 
                        "Arm2", "Arm3", "Training_Intensity", "Outcome_Adherence", 
                        "Outcome_Time", "Quality_Tool_Used", "Overall_RoB_Rating"
                    ]
                    worksheet.append_row(headers)
                
                row_data = [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    author, str(year), study_type, country, setting, scenario, str(n_size),
                    individual_team, aid_name, format_type, arm1, arm2, arm3,
                    training_intensity, out_adherence, out_time, rob_type, rob_rating
                ]
                worksheet.append_row(row_data)
                st.success(f"🎉 성공! '{author} ({year})' 연구 데이터가 구글 스프레드시트에 안전하게 저장되었습니다!")
            except Exception as e:
                st.error(f"데이터 전송 중 오류 발생: {e}")
