"""
Cognitive Aids NMA — Data Extraction Tool (v4.1)
Streamlit app matching extraction form v4.1.
Deploy: GitHub → Streamlit Community Cloud.

Requires:
  - st.secrets["gcp_service_account"] : service-account JSON
  - Google Sheet with header row matching SHEET_HEADERS below
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import math
from statistics import NormalDist

# stdlib replacement for scipy.stats.norm.ppf — avoids the scipy dependency
_norm_ppf = NormalDist().inv_cdf

st.set_page_config(page_title="Cognitive Aids NMA Extraction v4.1", layout="wide")

# =============================================================================
# Google Sheets connection
# =============================================================================
@st.cache_resource
def init_connection():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)

client = init_connection()
SHEET_URL = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit"
worksheet = client.open_by_url(SHEET_URL).sheet1

# =============================================================================
# Sheet column order — MUST match the header row of your Google Sheet
# =============================================================================
SHEET_HEADERS = [
    "Timestamp", "Reviewer",
    # Study info
    "Lead Author", "Year", "Study Type", "Country", "Setting", "Scenario",
    # Population
    "Total N (all arms)", "N (this arm)", "Unit (individual/team)",
    "Team composition (free text)", "Team interprofessionality",
    "Provider experience",
    # Intervention / CA / Node
    "NMA Node", "Node rationale", "Arm No.", "Arm Label", "CA Name",
    "Format - medium", "Format - type", "CA logic structure",
    # Implementation
    "Pre-training intensity", "Pre-training description",
    "Training duration", "Training method", "Training timing",
    "Designated Reader present", "Reader use mode",
    "Interaction style", "Strictness of workflow",
    "CA use enforcement", "CA use fidelity check", "CA use fidelity rate (%)",
    "Implementation narrative",
    # Outcome 1: Adherence (PRIMARY, continuous)
    "Adherence Mean", "Adherence SD", "Adherence N analyzed",
    "Adherence original format", "Adherence raw median stats",
    "Adherence conversion method", "Adherence Kirkpatrick level",
    "Adherence comments",
    # Outcome 2: Time to critical action (SECONDARY, continuous)
    "Time Mean", "Time SD", "Time N analyzed",
    "Time original format", "Time raw median stats",
    "Time conversion method", "Time comments",
    # Outcome 3: Error rate (SECONDARY, dichotomous)
    "Error events", "Error N analyzed", "Error effect measure",
    "Error original reporting", "Error comments",
    # Outcome 4: Teamwork / NTS (separate analysis)
    "NTS Mean", "NTS SD", "NTS N analyzed",
    "NTS instrument", "NTS comments",
    # RoB-2 (RCT)
    "RoB-2 D1 Randomization", "RoB-2 D2 Deviation",
    "RoB-2 D3 Missing data", "RoB-2 D4 Measurement",
    "RoB-2 D5 Selective reporting", "RoB-2 Overall", "RoB-2 Comments",
    # ROBINS-I (non-randomised)
    "ROBINS-I applicable", "ROBINS-I Overall", "ROBINS-I Comments",
    # MERSQI
    "MERSQI total (max 18)", "MERSQI Comments",
]

# =============================================================================
# UI
# =============================================================================
st.title("🌐 Cognitive Aids NMA — Data Extraction (v4.1)")
st.info(
    """
**📌 INSTRUCTIONS**
1. Enter your name in **Reviewer Name** (Tab 1) — required.
2. Extract data for **ONE arm per submission**.
3. **Multi-arm study**: after submitting arm 1, just update Arm No., Arm Label, and Outcomes → click Submit again. Other fields stay.
4. **New study**: refresh browser (F5 / Cmd+R) to clear all fields.
5. ★ = NMA-critical field (Node, N per arm, Mean/SD/N for primary outcome).
6. For median-reported outcomes, use the **Median → Mean/SD converter** in Tab 4 (Wan 2014 > Hozo 2005 > Luo 2018).
"""
)

with st.form("extraction_form", clear_on_submit=False):

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📑 1. Study & Population",
        "🛠️ 2. CA & NMA Node",
        "⚙️ 3. Implementation",
        "📈 4. Outcomes",
        "⚖️ 5. RoB & Quality",
    ])

    # -------------------------------------------------------------------------
    # TAB 1 — STUDY & POPULATION
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("Reviewer")
        reviewer = st.text_input("Reviewer Name ★", key="reviewer")

        st.markdown("---")
        st.subheader("General Study Characteristics")
        c1, c2, c3 = st.columns(3)
        with c1:
            author = st.text_input("Lead Author (last name)")
            year = st.number_input("Publication Year", 1990, 2030, 2024)
            study_type = st.selectbox(
                "Study Type",
                ["RCT", "Pilot RCT", "Cluster RCT", "Crossover RCT",
                 "Quasi-experimental", "Observational/Non-randomised", "Other"],
            )
        with c2:
            country = st.text_input("Country")
            setting = st.selectbox(
                "Simulation Setting",
                ["OR / Anaesthesia", "ICU", "ED", "Neonatal / Paediatric",
                 "Pre-hospital / EMS", "Ward", "Other"],
            )
            scenario = st.text_input("Scenario (e.g., MH, cardiac arrest, anaphylaxis)")
        with c3:
            total_n = st.number_input("Total N (all arms)", min_value=0, value=0)
            arm_n = st.number_input("★ N (this arm)", min_value=0, value=0,
                                    help="NMA-critical: per-arm N")

        st.markdown("---")
        st.subheader("Population & Team")
        p1, p2, p3 = st.columns(3)
        with p1:
            unit_random = st.selectbox(
                "Unit of randomisation",
                ["Individual (single-provider)", "Team (multi-provider)",
                 "Cluster", "Unclear"],
            )
            exp_level = st.selectbox(
                "★ Provider experience [for S4 sensitivity]",
                ["Trainee", "Experienced", "Mixed", "Unclear"],
            )
        with p2:
            team_compo = st.text_input(
                "Team composition (free text — e.g., 'surgeon + 2 nurses')"
            )
            team_inter = st.selectbox(
                "Team interprofessionality (NEW v4.1)",
                ["Single-discipline", "Interprofessional",
                 "Mixed across arms", "Individual (N/A)", "Unclear"],
                help="Sharif (Apr mtg): distinct from individual/team unit-of-randomisation.",
            )

    # -------------------------------------------------------------------------
    # TAB 2 — CA & NMA NODE
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("NMA Node — classify by FUNCTION, not medium")
        st.caption(
            "**Control** = memory / no aid (mnemonics-from-memory included). "
            "**Static** = non-interactive, fixed/linear (any medium — paper, "
            "electronic PDF, wall chart, AR overlay displaying a fixed list). "
            "**Dynamic** = interactive / adaptive / computational / branching."
        )
        n1, n2 = st.columns([1, 2])
        with n1:
            nma_node = st.selectbox("★ NMA Node", ["Control", "Static", "Dynamic"])
            arm_no = st.number_input("★ Arm No.", 1, 10, 1)
        with n2:
            node_rationale = st.text_area(
                "Node rationale (1 line — why Static vs Dynamic, audits borderline cases)",
                help="e.g., 'Harari AR = fixed checklist overlay → Static'; "
                     "'Siebert AR = auto-calculates doses → Dynamic'.",
                height=68,
            )

        st.markdown("---")
        st.subheader("Cognitive Aid Description")
        a1, a2 = st.columns(2)
        with a1:
            arm_label = st.text_input("★ Arm Label (e.g., 'Paper checklist', 'iPad app')")
            aid_name = st.text_input("Name of Cognitive Aid (e.g., 'Stanford EM Manual')")
        with a2:
            medium = st.selectbox(
                "Format — medium",
                ["Paper", "Digital — PDF/static screen", "Digital — app/tablet",
                 "Digital — AR/VR", "Hybrid (paper + digital)",
                 "N/A (Control arm)", "Other"],
            )
            ca_type = st.selectbox(
                "Format — type",
                ["Checklist", "Chart / flow diagram", "App", "Tablet interface",
                 "AR overlay", "Mnemonic / memory aid", "N/A (Control)", "Other"],
            )

        ca_logic = st.selectbox(
            "CA logic structure (NEW v4.1) — handoff §7 effect modifier",
            ["Linear (sequential, no branching)",
             "Stepwise (sequential, one path)",
             "Branching (decision-tree, adapts to user input)",
             "Mixed",
             "N/A (Control)"],
            help="Marshall 2016 and van Haperen explicitly compared linear vs branched.",
        )

    # -------------------------------------------------------------------------
    # TAB 3 — IMPLEMENTATION FACTORS
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Pre-training (before the simulation)")
        t1, t2 = st.columns(2)
        with t1:
            pretrain_intensity = st.selectbox(
                "Pre-training intensity",
                ["None", "Minimal (<30 min)", "Structured (≥30 min)", "Unclear"],
            )
            train_duration = st.text_input(
                "Training duration (free text — e.g., '15 min', '2 sessions of 1 h')"
            )
        with t2:
            train_method = st.selectbox(
                "Training method",
                ["None", "Lecture", "Video", "Hands-on / orientation",
                 "Combined", "Unclear"],
            )
            train_timing = st.selectbox(
                "Training timing",
                ["None", "Immediately before scenario", "Same day",
                 "Earlier in study (remote)", "Unclear"],
            )
        pretrain_desc = st.text_area("Pre-training description (free text, if provided)", height=68)

        st.markdown("---")
        st.subheader("Reader & Interaction")
        r1, r2 = st.columns(2)
        with r1:
            reader_present = st.selectbox(
                "Designated Reader present?",
                ["Yes", "No", "Not reported"],
            )
            reader_mode = st.selectbox(
                "Reader use mode (NEW v4.1)",
                ["Mandated (required by protocol)",
                 "Suggested / encouraged",
                 "Discretionary",
                 "Not used",
                 "Unclear"],
                help="Sharif (Apr mtg): captures whether reader-use was enforced. "
                     "Distinct from who reads.",
            )
        with r2:
            interaction = st.selectbox(
                "Interaction style",
                ["Read-do", "Challenge-response", "Self-read silent",
                 "Combined", "N/A (Control)", "Unclear"],
            )
            strictness = st.selectbox(
                "Strictness of CA workflow (within the aid)",
                ["Strict (every step must be completed)",
                 "Discretionary (steps can be skipped)",
                 "Mixed", "N/A (Control)", "Unclear"],
                help="If overlaps with CA use enforcement below, prioritise enforcement field.",
            )

        st.markdown("---")
        st.subheader("CA use enforcement & fidelity (NEW v4.1 — Tim Ramsay's key methodological concern)")
        st.caption(
            "📌 Tim (Apr mtg): *'What did they do to ensure people USED the cognitive aid?'* "
            "Separates strong implementation studies from passive deployment."
        )
        e1, e2 = st.columns(2)
        with e1:
            enforcement = st.selectbox(
                "CA use enforcement",
                ["Mandated (participants required to consult CA)",
                 "Encouraged (instructed but not enforced)",
                 "Available-only (CA placed in environment, no instruction)",
                 "Unclear"],
            )
            fidelity_check = st.selectbox(
                "CA use fidelity check (was actual use monitored?)",
                ["Yes — quantitative (e.g., observed/timed use)",
                 "Yes — qualitative only (mentioned in narrative)",
                 "No (not reported)",
                 "Unclear"],
            )
        with e2:
            fidelity_rate = st.text_input(
                "CA use fidelity rate (% participants who actually used CA, if reported)",
                help="Leave blank if not reported."
            )

        implementation_narrative = st.text_area(
            "Implementation narrative (NEW v4.1 — free text)",
            help="Describe how the CA was implemented. Supports Plan-B narrative synthesis "
                 "if NMA proves infeasible from heterogeneity (Sharif's UGRA-paper template).",
            height=100,
        )

    # -------------------------------------------------------------------------
    # TAB 4 — OUTCOMES
    # -------------------------------------------------------------------------
    with tab4:
        # --------- Conversion calculator (Wan > Hozo > Luo) ----------
        with st.expander("💡 Median → Mean/SD Converter (Wan 2014 > Hozo 2005 > Luo 2018)",
                         expanded=False):
            st.markdown(
                "**Hierarchy** (per Protocol v2): use **Wan 2014** when median + IQR (Q1, Q3) "
                "reported; **Hozo 2005** when only median + range (min, max); **Luo 2018** "
                "for skewed or very large samples. Record which method you used."
            )
            cvt_method = st.radio(
                "Pick reported statistic:",
                ["Wan 2014 — median + Q1 + Q3",
                 "Hozo 2005 — median + min + max",
                 "Luo 2018 — median + (min, max) [alternative mean estimator]"],
                horizontal=False,
            )
            cv1, cv2, cv3, cv4 = st.columns(4)
            with cv1: cv_med = st.number_input("Median", value=0.0, format="%.4f", key="cv_med")
            with cv2: cv_a = st.number_input("Q1 / min", value=0.0, format="%.4f", key="cv_a")
            with cv3: cv_b = st.number_input("Q3 / max", value=0.0, format="%.4f", key="cv_b")
            with cv4: cv_n = st.number_input("n", min_value=1, value=10, key="cv_n")

            if st.form_submit_button("📐 Compute"):
                try:
                    if cvt_method.startswith("Wan"):
                        # Wan 2014 scenario C2 (median + IQR + n)
                        mean_est = (cv_a + cv_med + cv_b) / 3
                        xi = 2 * _norm_ppf((0.75 * cv_n - 0.125) / (cv_n + 0.25))
                        sd_est = (cv_b - cv_a) / xi
                        method_used = f"Wan 2014 (η={xi:.3f})"
                    elif cvt_method.startswith("Hozo"):
                        # Hozo 2005 scenario S1 (median + range)
                        mean_est = (cv_a + 2 * cv_med + cv_b) / 4
                        if cv_n <= 15:
                            sd_est = (cv_b - cv_a) / (2 * math.sqrt(3))
                            sd_rule = "n≤15: range/(2√3)"
                        elif cv_n <= 70:
                            sd_est = (cv_b - cv_a) / 4
                            sd_rule = "15<n≤70: range/4"
                        else:
                            sd_est = (cv_b - cv_a) / 6
                            sd_rule = "n>70: range/6"
                        method_used = f"Hozo 2005 ({sd_rule})"
                    else:
                        # Luo 2018 scenario S1 — mean from median + min + max
                        w = 4 / (4 + cv_n ** 0.75)
                        mean_est = w * (cv_a + cv_b) / 2 + (1 - w) * cv_med
                        # use Wan SD as companion (Luo paper recommends pairing)
                        xi = 2 * _norm_ppf((0.75 * cv_n - 0.125) / (cv_n + 0.25))
                        sd_est = (cv_b - cv_a) / xi  # approximation
                        method_used = "Luo 2018 mean + Wan 2014 SD"
                    st.success(
                        f"**Mean ≈ {mean_est:.3f} | SD ≈ {sd_est:.3f}** "
                        f"({method_used}). Copy into outcome fields below; "
                        f"record method in *Conversion method*."
                    )
                except Exception as e:
                    st.error(f"Calc error: {e}")

        st.markdown("---")

        # --------- Outcome 1: Adherence (PRIMARY, continuous) ----------
        st.markdown("### Outcome 1 — Adherence / task completion (★ PRIMARY, continuous, SMD)")
        o1c1, o1c2, o1c3 = st.columns(3)
        with o1c1: adh_mean = st.text_input("★ Mean")
        with o1c2: adh_sd = st.text_input("★ SD")
        with o1c3: adh_n = st.text_input("★ N analyzed (this arm)")
        o1c4, o1c5 = st.columns(2)
        with o1c4:
            adh_orig = st.selectbox(
                "Original reporting format",
                ["mean ± SD", "median + IQR", "median + range",
                 "%/proportion", "Other", "Not extractable"],
                key="adh_orig",
            )
            adh_raw = st.text_input("Raw median stats (median; Q1–Q3 OR min–max; n)", key="adh_raw")
        with o1c5:
            adh_conv = st.selectbox(
                "Conversion method (if median→mean)",
                ["N/A — reported as mean", "Wan 2014 (median+IQR)",
                 "Hozo 2005 (median+range)", "Luo 2018", "Other"],
                key="adh_conv",
            )
            adh_kp = st.selectbox(
                "Kirkpatrick level",
                ["KP1 Reaction", "KP2 Learning", "KP3 Behaviour", "KP4 Results", "N/A"],
                key="adh_kp",
            )
        adh_comments = st.text_input("Adherence comments", key="adh_comments")

        st.markdown("---")

        # --------- Outcome 2: Time to critical action (SECONDARY) ----------
        st.markdown("### Outcome 2 — Time to first critical action (SECONDARY, continuous)")
        st.caption("Time is SECONDARY — analysed separately, NOT in primary NMA.")
        o2c1, o2c2, o2c3 = st.columns(3)
        with o2c1: time_mean = st.text_input("Mean")
        with o2c2: time_sd = st.text_input("SD")
        with o2c3: time_n = st.text_input("N analyzed")
        o2c4, o2c5 = st.columns(2)
        with o2c4:
            time_orig = st.selectbox(
                "Original reporting format",
                ["mean ± SD", "median + IQR", "median + range", "Other",
                 "Not reported"],
                key="time_orig",
            )
        with o2c5:
            time_raw = st.text_input("Raw median stats (if median)", key="time_raw")
            time_conv = st.selectbox(
                "Conversion method (if any)",
                ["N/A", "Wan 2014", "Hozo 2005", "Luo 2018", "Other"],
                key="time_conv",
            )
        time_comments = st.text_input("Time comments", key="time_comments")

        st.markdown("---")

        # --------- Outcome 3: Error rate (SECONDARY, dichotomous) ----------
        st.markdown("### Outcome 3 — Error rate (SECONDARY, dichotomous, RR)")
        e3c1, e3c2, e3c3 = st.columns(3)
        with e3c1: err_events = st.text_input("Events (this arm)")
        with e3c2: err_n = st.text_input("N analyzed (this arm)")
        with e3c3:
            err_measure = st.selectbox(
                "Effect measure",
                ["RR (primary)", "OR (secondary)", "Other", "Not reported"],
            )
        err_orig = st.text_input("Original reporting (events/n, %, RR/OR with CI)")
        err_comments = st.text_input("Error comments")

        st.markdown("---")

        # --------- Outcome 4: Teamwork / NTS ----------
        st.markdown("### Outcome 4 — Teamwork / NTS (separate analysis)")
        st.caption("Non-technical skills / teamwork analysed separately.")
        nts1, nts2, nts3 = st.columns(3)
        with nts1: nts_mean = st.text_input("Mean", key="nts_mean")
        with nts2: nts_sd = st.text_input("SD", key="nts_sd")
        with nts3: nts_n = st.text_input("N analyzed", key="nts_n")
        nts_instrument = st.text_input("Instrument (e.g., ANTS, NOTECHS, T-NOTECHS)")
        nts_comments = st.text_input("NTS comments")

    # -------------------------------------------------------------------------
    # TAB 5 — RoB & QUALITY
    # -------------------------------------------------------------------------
    with tab5:
        st.subheader("RoB-2 (for RCTs)")
        rob_levels = ["Low", "Some concerns", "High", "N/A (non-randomised)"]
        rc1, rc2 = st.columns(2)
        with rc1:
            d1 = st.selectbox("D1 — Randomisation process", rob_levels)
            d2 = st.selectbox("D2 — Deviation from intended intervention", rob_levels)
            d3 = st.selectbox("D3 — Missing outcome data", rob_levels)
        with rc2:
            d4 = st.selectbox("D4 — Measurement of outcome", rob_levels)
            d5 = st.selectbox("D5 — Selective reporting", rob_levels)
            rob_overall = st.selectbox("★ Overall RoB-2", rob_levels)
        rob_comments = st.text_area("RoB-2 comments / supporting quotes", height=68)

        st.markdown("---")
        st.subheader("ROBINS-I (for non-randomised studies — e.g., Burden, Everett)")
        ri1, ri2 = st.columns(2)
        with ri1:
            robins_applicable = st.selectbox(
                "ROBINS-I applicable?",
                ["No — study is RCT", "Yes — non-randomised"],
            )
        with ri2:
            robins_overall = st.selectbox(
                "ROBINS-I Overall",
                ["N/A", "Low", "Moderate", "Serious", "Critical", "No information"],
            )
        robins_comments = st.text_area("ROBINS-I comments (record per-domain judgements here)",
                                       height=68)

        st.markdown("---")
        st.subheader("MERSQI (medical education research quality)")
        mersqi_total = st.text_input("MERSQI total score (max 18)",
                                     help="Sum of 6 subscales: study design (3), sampling (3), "
                                          "data type (3), validity (3), analysis appropriate (1), "
                                          "analysis sophistication (2), highest outcome (3).")
        mersqi_comments = st.text_area("MERSQI comments / subscale breakdown", height=68)

    # =========================================================================
    # SUBMIT
    # =========================================================================
    st.markdown("---")
    submitted = st.form_submit_button("💾 Submit Arm Data")

    if submitted:
        if not reviewer.strip():
            st.error("❌ Please enter your Reviewer Name (Tab 1) before submitting.")
        elif not author.strip():
            st.error("❌ Lead Author is required.")
        else:
            row_data = [
                str(datetime.now()), reviewer,
                # Study info
                author, str(year), study_type, country, setting, scenario,
                # Population
                str(total_n), str(arm_n), unit_random, team_compo,
                team_inter, exp_level,
                # CA / Node
                nma_node, node_rationale, str(arm_no), arm_label, aid_name,
                medium, ca_type, ca_logic,
                # Implementation
                pretrain_intensity, pretrain_desc,
                train_duration, train_method, train_timing,
                reader_present, reader_mode,
                interaction, strictness,
                enforcement, fidelity_check, fidelity_rate,
                implementation_narrative,
                # Outcome 1 — adherence
                adh_mean, adh_sd, adh_n,
                adh_orig, adh_raw, adh_conv, adh_kp, adh_comments,
                # Outcome 2 — time
                time_mean, time_sd, time_n,
                time_orig, time_raw, time_conv, time_comments,
                # Outcome 3 — error rate
                err_events, err_n, err_measure, err_orig, err_comments,
                # Outcome 4 — NTS
                nts_mean, nts_sd, nts_n, nts_instrument, nts_comments,
                # RoB-2
                d1, d2, d3, d4, d5, rob_overall, rob_comments,
                # ROBINS-I
                robins_applicable, robins_overall, robins_comments,
                # MERSQI
                mersqi_total, mersqi_comments,
            ]

            # Sanity check vs SHEET_HEADERS
            if len(row_data) != len(SHEET_HEADERS):
                st.error(
                    f"⚠️ Internal column-count mismatch: "
                    f"row has {len(row_data)} fields, SHEET_HEADERS has {len(SHEET_HEADERS)}. "
                    "Tell the developer."
                )
            else:
                try:
                    worksheet.append_row(row_data)
                    st.success(
                        f"✅ Saved: **{author} ({year}) — Arm {arm_no}: {arm_label}** "
                        f"by {reviewer}"
                    )
                    st.balloons()
                    st.warning(
                        """
**⚠️ Before clicking Submit again:**
- **NEXT ARM, same study**: update Arm No., Arm Label, NMA Node, and Outcomes only.
- **NEW study**: refresh browser (F5 / Cmd+R) to clear all fields.
"""
                    )
                except Exception as e:
                    st.error(f"❌ Could not write to sheet: {e}")

# =============================================================================
# Helper: show expected sheet headers (so user can paste them into row 1)
# =============================================================================
with st.expander("🔧 Setup — expected Google Sheet header row (paste into row 1)"):
    st.markdown(
        "Copy these into row 1 of your Google Sheet **in this exact order** "
        "before first use:"
    )
    st.code("\t".join(SHEET_HEADERS), language="text")
    st.caption(f"Total columns: {len(SHEET_HEADERS)}")
