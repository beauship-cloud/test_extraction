import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="NMA Data Extraction Tool", layout="wide")

# ... (init_connection 부분은 그대로 유지) ...
@st.cache_resource
def init_connection():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=[
        "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"
    ])
    return gspread.authorize(creds)

client = init_connection()
sheet_url = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit"
worksheet = client.open_by_url(sheet_url).sheet1

st.title("🌐 NMA Data Extraction Tool (Enhanced)")

with st.form("extraction_form", clear_on_submit=True):
    # 탭을 더 세분화함
    tab1, tab2, tab3, tab4 = st.tabs(["📑 1. Study Info", "🛠️ 2. Intervention", "📈 3. Outcomes", "⚖️ 4. Risk of Bias"])
    
    with tab1:
        st.subheader("General Study Information")
        author = st.text_input("Lead Author")
        year = st.number_input("Publication Year", 1990, 2030, 2026)
        study_design = st.selectbox("Study Design", ["RCT", "Quasi-experimental", "Observational"])
        
    with tab2:
        st.subheader("Intervention Details")
        aid_name = st.text_input("Cognitive Aid Name")
        category = st.selectbox("Aid Category", ["Checklist", "Algorithm", "Cognitive Aid App", "Other"])
        delivery = st.selectbox("Delivery Format", ["Paper", "Digital/Electronic", "Hybrid"])
        
    with tab3:
        st.subheader("Outcome Measures")
        adherence_rate = st.number_input("Adherence Rate (%)", 0, 100)
        time_to_completion = st.text_input("Time to Completion (min)")
        
    with tab4:
        st.subheader("Quality Assessment")
        rob = st.selectbox("Risk of Bias Level", ["Low", "Some Concerns", "High"])

    if st.form_submit_button("💾 Submit to Google Sheets"):
        worksheet.append_row([str(datetime.now()), author, str(year), study_design, aid_name, category, delivery, str(adherence_rate), time_to_completion, rob])
        st.success("Data Saved Successfully!")
