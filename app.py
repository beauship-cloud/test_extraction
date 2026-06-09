import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import math

st.set_page_config(page_title="NMA Data Extraction Tool", layout="wide")

# 구글 시트 연동 (기존과 동일)
@st.cache_resource
def init_connection():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds)

client = init_connection()
# 💡 여기에 본인의 진짜 구글 시트 링크를 넣으세요!
sheet_url = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit"
worksheet = client.open_by_url(sheet_url).sheet1

st.title("🌐 NMA Data Extraction Tool (V4 PRO)")
st.markdown("**지침:** 1개 Arm 단위로 데이터를 추출합니다. 모든 탭을 작성한 후 마지막에 Submit을 누르세요.")

# 폼 시작 (이 안에 있는 모든 입력은 Submit을 눌러야만 전송됨)
with st.form("extraction_form", clear_on_submit=False):
    
    # 4개의 탭 생성
    tab1, tab2, tab3, tab4 = st.tabs(["📑 1. Study Info", "🛠️ 2. Intervention", "📈 3. Outcomes", "⚖️ 4. Risk of Bias"])
    
    with tab1:
        st.subheader("General Study & Population Characteristics")
        col1, col2, col3 = st.columns(3)
        with col1:
            author = st.text_input("Lead Author")
            year = st.number_input("Publication Year", 1990, 2030, 2026)
            study_type = st.selectbox("Study Type", ["RCT", "Crossover", "Cluster", "Pilot", "Quasi-experimental"])
        with col2:
            country = st.text_input("Country")
            setting = st.selectbox("Simulation Setting", ["OR", "ICU", "ED", "Neonatal unit", "Other"])
            scenario = st.text_input("Scenario (e.g., cardiac arrest)")
        with col3:
            total_n = st.number_input("Total N (All arms)", min_value=0)
            arm_n = st.number_input("★ N (This arm)", min_value=0, help="NMA-Critical Field")
            exp_level = st.selectbox("★ Experience Level", ["Trainee", "Experienced", "Mixed"])
            
    with tab2:
        st.subheader("Intervention & Implementation Factors")
        col1, col2 = st.columns(2)
        with col1:
            nma_node = st.selectbox("★ NMA Node", ["Static", "Dynamic", "Control"])
            arm_label = st.text_input("★ Arm Label (e.g., Paper checklist)")
            arm_no = st.number_input("★ Arm No.", 1, 10, 1)
            aid_name = st.text_input("Name of Cognitive Aid")
        with col2:
            medium = st.selectbox("Medium", ["Paper", "Digital", "Hybrid", "N/A (Control)"])
            designated_reader = st.selectbox("Designated Reader?", ["Yes", "No", "Not reported"])
            training = st.selectbox("Training Intensity", ["None", "Minimal (<30m)", "Structured (≥30m)"])
            
    with tab3:
        st.subheader("Outcome Measures")
        st.markdown("---")
        
        # 🧮 호조 메소드 계산기 토글
        use_hozo = st.checkbox("💡 Mean/SD가 없고 Median/Range만 있나요? (Hozo Method 계산기 열기)")
        if use_hozo:
            st.info("Hozo et al. (2005) 공식에 따라 중앙값(Median)과 최소/최대값으로 Mean/SD를 추정합니다.")
            h_col1, h_col2, h_col3, h_col4 = st.columns(4)
            with h_col1: h_med = st.number_input("Median (m)", value=0.0)
            with h_col2: h_min = st.number_input("Min (a)", value=0.0)
            with h_col3: h_max = st.number_input("Max (b)", value=0.0)
            with h_col4: h_n = st.number_input("Sample size (n)", min_value=1, value=10)
            
            # 실시간 호조 계산 로직 노출
            est_mean = (h_min + 2*h_med + h_max) / 4
            if h_n <= 15: est_sd = (h_max - h_min) / (2 * math.sqrt(3))
            elif 15 < h_n <= 70: est_sd = (h_max - h_min) / 4
            else: est_sd = (h_max - h_min) / 6
            st.success(f"**추정 결과 ➔ Mean: {est_mean:.2f} | SD: {est_sd:.2f}** (이 값을 아래에 입력하세요)")

        st.markdown("##### 1. Adherence / Task Performance [Continuous]")
        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1: mean_val = st.text_input("★ Mean")
        with c_col2: sd_val = st.text_input("★ SD")
        with c_col3: n_outcome = st.text_input("N (Outcome)")
        
        st.markdown("##### 2. Adherence [Dichotomous] & Time to Action")
        d_col1, d_col2 = st.columns(2)
        with d_col1: events = st.text_input("Events (Dichotomous)")
        with d_col2: time_mean = st.text_input("Time to Action Mean")
        
        conversion_note = st.text_area("Conversion Note (Hozo 변환 등 특이사항 기록)")

    with tab4:
        st.subheader("Quality Assessment (RoB 2)")
        r_col1, r_col2 = st.columns(2)
        with r_col1:
            d1 = st.selectbox("D1: Randomization", ["Low", "Some concerns", "High"])
            d2 = st.selectbox("D2: Deviation", ["Low", "Some concerns", "High"])
            d3 = st.selectbox("D3: Missing Data", ["Low", "Some concerns", "High"])
        with r_col2:
            d4 = st.selectbox("D4: Measurement", ["Low", "Some concerns", "High"])
            d5 = st.selectbox("D5: Selective Reporting", ["Low", "Some concerns", "High"])
            rob_overall = st.selectbox("★ Overall RoB", ["Low", "Some concerns", "High"])

    # 폼 제출 버튼
    submitted = st.form_submit_button("💾 데이터 1개 Arm 전송하기")
    
    if submitted:
        # 구글 시트에 전송될 한 줄의 데이터 리스트 (컬럼 순서대로 매핑)
        row_data = [
            str(datetime.now()), author, str(year), study_type, country, setting, scenario, 
            str(total_n), str(arm_n), exp_level, nma_node, arm_label, str(arm_no), 
            aid_name, medium, designated_reader, training, 
            mean_val, sd_val, n_outcome, events, time_mean, conversion_note,
            d1, d2, d3, d4, d5, rob_overall
        ]
        
        # 구글 시트 추가 명령어
        worksheet.append_row(row_data)
        st.success(f"✅ {author} ({year}) 연구의 [Arm {arm_no}: {arm_label}] 데이터가 성공적으로 저장되었습니다!")
        st.balloons()
