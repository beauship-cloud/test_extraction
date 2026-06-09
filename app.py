import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import math

st.set_page_config(page_title="NMA Data Extraction Tool", layout="wide")

# Google Sheets Connection
@st.cache_resource
def init_connection():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds)

client = init_connection()
# 본인의 구글 시트 링크 확인
sheet_url = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit"
worksheet = client.open_by_url(sheet_url).sheet1

# Title and Instructions
st.title("🌐 NMA Data Extraction Tool")
st.info("""
**📌 INSTRUCTIONS (Please read before starting):**
1. **Identify Yourself:** Enter your name in the **`Reviewer Name`** field in Tab 1.
2. **One Arm Per Submission:** Extract data for ONE study arm at a time.
3. **Multi-Arm Studies:** After submitting the 1st arm, the form will NOT clear. Simply update the `Arm No.`, `Arm Label` (Tab 2), and `Outcome values` (Tab 3), then click Submit again for the 2nd arm.
4. **New Study:** To start extracting a completely new study, **refresh your browser (F5 or Cmd+R)** to clear all fields.
""")

# Form Start (clear_on_submit is False)
with st.form("extraction_form", clear_on_submit=False):
    
    # 4 Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📑 1. Study Info", "🛠️ 2. Intervention", "📈 3. Outcomes", "⚖️ 4. Risk of Bias"])
    
    with tab1:
        st.subheader("General Study & Population Characteristics")
        # 리뷰어 이름을 가장 먼저 입력하도록 상단에 배치
        reviewer = st.text_input("Reviewer Name (Your Name) ★")
        st.markdown("---")
        
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
        
        # Hozo Method Calculator
        use_hozo = st.checkbox("💡 Missing Mean/SD? Click here to use Hozo Method Calculator")
        if use_hozo:
            st.info("Estimates Mean and SD from Median and Range (Hozo et al. 2005).")
            h_col1, h_col2, h_col3, h_col4 = st.columns(4)
            with h_col1: h_med = st.number_input("Median (m)", value=0.0)
            with h_col2: h_min = st.number_input("Min (a)", value=0.0)
            with h_col3: h_max = st.number_input("Max (b)", value=0.0)
            with h_col4: h_n = st.number_input("Sample size (n)", min_value=1, value=10)
            
            # Logic for Hozo
            est_mean = (h_min + 2*h_med + h_max) / 4
            if h_n <= 15: est_sd = (h_max - h_min) / (2 * math.sqrt(3))
            elif 15 < h_n <= 70: est_sd = (h_max - h_min) / 4
            else: est_sd = (h_max - h_min) / 6
            st.success(f"**Estimated Result ➔ Mean: {est_mean:.2f} | SD: {est_sd:.2f}** (Input these values below)")

        st.markdown("##### 1. Adherence / Task Performance [Continuous]")
        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1: mean_val = st.text_input("★ Mean")
        with c_col2: sd_val = st.text_input("★ SD")
        with c_col3: n_outcome = st.text_input("N (Outcome)")
        
        st.markdown("##### 2. Adherence [Dichotomous] & Time to Action")
        d_col1, d_col2 = st.columns(2)
        with d_col1: events = st.text_input("Events (Dichotomous)")
        with d_col2: time_mean = st.text_input("Time to Action Mean")
        
        conversion_note = st.text_area("Conversion Note (e.g., Used Hozo for SD)")

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

    # Submit Button
    submitted = st.form_submit_button("💾 Submit Arm Data")
    
    if submitted:
        # Data list to send (reviewer added right after timestamp)
        row_data = [
            str(datetime.now()), reviewer, author, str(year), study_type, country, setting, scenario, 
            str(total_n), str(arm_n), exp_level, nma_node, arm_label, str(arm_no), 
            aid_name, medium, designated_reader, training, 
            mean_val, sd_val, n_outcome, events, time_mean, conversion_note,
            d1, d2, d3, d4, d5, rob_overall
        ]
        
        # Append to Sheet
        worksheet.append_row(row_data)
        
        # English Success Message
        st.success(f"✅ Data for **{author} ({year}) - [Arm {arm_no}: {arm_label}]** has been successfully saved by {reviewer}!")
        st.balloons()
        
        # English Warning Message
        st.warning("""
        **⚠️ WAIT BEFORE YOU CLICK SUBMIT AGAIN!**
        * **For the NEXT ARM of the SAME study:** Please update the `Arm No.`, `Arm Label`, and `Outcomes` before submitting again. (Your `Reviewer Name` will stay saved!)
        * **For a completely NEW study:** Please **refresh your browser** (F5 / Cmd+R) to clear all previous data.
        """)
