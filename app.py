"""
Cognitive Aids NMA — Data Extraction Tool (v4.5)
Streamlit app matching extraction form v4.5.
Deploy: GitHub → Streamlit Community Cloud.

Requires:
  - st.secrets["gcp_service_account"] : service-account JSON
  - Google Sheet with header row matching SHEET_HEADERS below

v4.5 changelog (Jun 2026):
  - Removed Clear ALL / Clear arm-specific buttons. Streamlit form caching
    made these unreliable, and F5 (browser refresh) is the simpler, more
    predictable reset path. Saves complexity, focuses on save reliability.
  - Workflow returns to: F5 = fresh study; manually edit fields between
    arms of the same study (the pilot workflow that already worked).
  - MERSQI calculator: replaced single-total text input with 6 domain
    selectboxes (Reed et al. 2007). Total is auto-computed and saved to
    the existing "MERSQI total" column. No new columns — only the total
    is stored; per-domain selections are not preserved across submits.

v4.4 retained:
  - enter_to_submit=False on the form (Enter no longer accidentally submits).
  - +1 column: Coding uncertainty log (Tab 1 end).
  - Personal-name references removed from form text.
  - Explicit `key=` on every widget (kept for Streamlit best practice).

v4.3 retained:
  - +3 columns: Publication type, Author contact status,
    Adherence outcome direction.
  - Dropdown additions: Setting +"In-flight/aeromedical",
    Reader use mode +"Encouraged (not mandated)",
    Fidelity check +"Yes — ordinal scale".
"""

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from zoneinfo import ZoneInfo
import math
from statistics import NormalDist

# Project timezone — all submissions stamped in Montréal time (EDT/EST)
# regardless of where the reviewer is located.
TZ = ZoneInfo("America/Toronto")

# stdlib replacement for scipy.stats.norm.ppf — avoids the scipy dependency
_norm_ppf = NormalDist().inv_cdf

st.set_page_config(page_title="Cognitive Aids NMA Extraction v4.5", layout="wide")

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
    # v4.3 additions (appended at end to preserve existing pilot row alignment)
    "Publication type",
    "Author contact status",
    "Adherence outcome direction",
    # v4.4 addition
    "Coding uncertainty log",
]

# =============================================================================
# UI
# =============================================================================
st.title("🌐 Cognitive Aids NMA — Data Extraction (v4.5)")
st.info(
    """
**📌 INSTRUCTIONS**
1. Enter your name in **Reviewer Name** (Tab 1) — required.
2. Extract data for **ONE arm per submission**.
3. **Multi-arm study**: after submitting arm 1, just update Arm No., Arm Label, NMA Node, and Outcomes → Submit again. Other fields stay.
4. **New study**: refresh browser (F5 / Cmd+R) to clear all fields.
5. ★ = NMA-critical field (Node, N per arm, Mean/SD/N for primary outcome).
6. For median-reported outcomes, use the **Median → Mean/SD converter** in Tab 4 (Wan 2014 > Hozo 2005 > Luo 2018).
"""
)

with st.form("extraction_form", clear_on_submit=False, enter_to_submit=False):

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
            author = st.text_input("Lead Author (last name)", key="author")
            year = st.number_input("Publication Year", 1990, 2030, 2024, key="year")
            study_type = st.selectbox(
                "Study Type",
                ["RCT", "Pilot RCT", "Cluster RCT", "Crossover RCT",
                 "Quasi-experimental", "Observational/Non-randomised", "Other"],
            
                key="study_type",)
        with c2:
            country = st.text_input("Country", key="country")
            setting = st.selectbox(
                "Simulated scenario setting",
                ["OR / Anaesthesia", "ICU", "ED", "Neonatal / Paediatric",
                 "Pre-hospital / EMS", "In-flight / aeromedical", "Ward", "Other"],
                help="Clinical context of the simulated emergency itself "
                     "(NOT the training course context). E.g., an ICU-course "
                     "simulating an in-hospital RRT call to ED → code as 'ED'.",
            
                key="setting",)
            scenario = st.text_input("Scenario (e.g., MH, cardiac arrest, anaphylaxis)", key="scenario")
        with c3:
            total_n = st.number_input(
                "Total N (all arms)", min_value=0, value=0,
                help="Enter N at the UNIT OF ANALYSIS for the primary outcome. "
                     "If unit-of-randomisation ≠ unit-of-analysis (e.g., teams "
                     "randomised but process-steps analysed), state both in "
                     "the Adherence comments field.",
            
                key="total_n",)
            arm_n = st.number_input(
                "★ N (this arm)", min_value=0, value=0,
                help="NMA-critical: per-arm N at the unit of analysis. "
                     "For team-randomised studies analysed at process-step level, "
                     "use the level that matches the Mean/SD or events/N reported.",
            
                key="arm_n",)

        # v4.3: publication metadata
        pm1, pm2 = st.columns(2)
        with pm1:
            pub_type = st.selectbox(
                "Publication type (NEW v4.3)",
                ["Full original research",
                 "Correspondence / Letter",
                 "Conference abstract",
                 "Other"],
                help="Donze 2019 was published as a Letter — flag here so "
                     "RoB-2 D5 / MERSQI / sample-size scrutiny can be adjusted.",
            
                key="pub_type",)
        with pm2:
            author_contact = st.selectbox(
                "Author contact status (NEW v4.3)",
                ["Not needed",
                 "Pending decision",
                 "Sent — awaiting reply",
                 "Received — data added",
                 "Sent — no reply / declined"],
                help="Tracks studies where raw data was requested from authors "
                     "(e.g., Sellmann 5th/95th percentile, Donze n unknown).",
            
                key="author_contact",)

        st.markdown("---")
        st.subheader("Population & Team")
        p1, p2, p3 = st.columns(3)
        with p1:
            unit_random = st.selectbox(
                "Unit of randomisation",
                ["Individual (single-provider)", "Team (multi-provider)",
                 "Cluster", "Unclear"],
            
                key="unit_random",)
            exp_level = st.selectbox(
                "★ Provider experience [for S4 sensitivity]",
                ["Trainee", "Experienced", "Mixed", "Unclear"],
            
                key="exp_level",)
        with p2:
            team_compo = st.text_input(
                "Team composition (free text — e.g., 'surgeon + 2 nurses')"
            ,
                key="team_compo",)
            team_inter = st.selectbox(
                "Team interprofessionality (NEW v4.1)",
                ["Single-discipline",
                 "Interdisciplinary (multi-specialty, same profession)",
                 "Interprofessional (multi-profession: MD + RN + paramedic etc.)",
                 "Mixed across arms", "Individual (N/A)", "Unclear"],
                help="Captures team composition. "
                     "Interdisciplinary = e.g., anaesthesia + IM + surgery residents (all MDs). "
                     "Interprofessional = e.g., MD + RN + RT. "
                     "Distinct from individual/team unit-of-randomisation.",
            
                key="team_inter",)

        st.markdown("---")
        st.subheader("Coding uncertainty log (NEW v4.4)")
        coding_uncertainty_log = st.text_area(
            "If any field in any tab was coded as 'Unclear' / 'Not reported', "
            "note WHY here — one line per field. (Leave blank if no Unclears.)",
            help="Lets the reconciliation step distinguish 'truly missing from paper' "
                 "(→ author contact candidate) from 'ambiguous wording in main text' "
                 "(→ re-read or check supplementary) from 'definition issue' "
                 "(→ codebook clarification). "
                 "Example: 'Unit-of-rand: paper says randomised, level not stated; "
                 "CA logic: appendix needed to judge branching.' "
                 "Does NOT replace node_rationale (NMA Node has its own dedicated field).",
            height=100,
            key="coding_uncertainty_log",
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
            nma_node = st.selectbox("★ NMA Node", ["Control", "Static", "Dynamic"], key="nma_node")
            arm_no = st.number_input("★ Arm No.", 1, 10, 1, key="arm_no")
        with n2:
            node_rationale = st.text_area(
                "Node rationale (1 line — why Static vs Dynamic, audits borderline cases)",
                help="e.g., 'Harari AR = fixed checklist overlay → Static'; "
                     "'Siebert AR = auto-calculates doses → Dynamic'.",
                height=68,
            
                key="node_rationale",)

        st.markdown("---")
        st.subheader("Cognitive Aid Description")
        a1, a2 = st.columns(2)
        with a1:
            arm_label = st.text_input("★ Arm Label (e.g., 'Paper checklist', 'iPad app')", key="arm_label")
            aid_name = st.text_input("Name of Cognitive Aid (e.g., 'Stanford EM Manual')", key="aid_name")
        with a2:
            medium = st.selectbox(
                "Format — medium",
                ["Paper", "Digital — PDF/static screen", "Digital — app/tablet",
                 "Digital — AR/VR", "Hybrid (paper + digital)",
                 "N/A (Control arm)", "Other"],
            
                key="medium",)
            ca_type = st.selectbox(
                "Format — type",
                ["Checklist", "Chart / flow diagram", "App", "Tablet interface",
                 "AR overlay", "Mnemonic / memory aid", "N/A (Control)", "Other"],
            
                key="ca_type",)

        ca_logic = st.selectbox(
            "CA logic structure (NEW v4.1) — handoff §7 effect modifier",
            ["Linear (sequential, no branching)",
             "Stepwise (sequential, one path)",
             "Branching (decision-tree, adapts to user input)",
             "Mixed",
             "Unclear from main text (appendix / supplementary needed)",
             "N/A (Control)"],
            help="Marshall 2016 and van Haperen explicitly compared linear vs branched. "
                 "If main text doesn't show enough of the CA to judge, code Unclear and "
                 "flag in Implementation narrative — author contact or appendix lookup needed.",
        
            key="ca_logic",)

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
            
                key="pretrain_intensity",)
            train_duration = st.text_input(
                "Training duration (free text — e.g., '15 min', '2 sessions of 1 h')"
            ,
                key="train_duration",)
        with t2:
            train_method = st.selectbox(
                "Training method",
                ["None", "Lecture", "Video", "Hands-on / orientation",
                 "Combined", "Unclear"],
            
                key="train_method",)
            train_timing = st.selectbox(
                "Training timing",
                ["None", "Immediately before scenario", "Same day",
                 "Earlier in study (remote)", "Unclear"],
            
                key="train_timing",)
        pretrain_desc = st.text_area("Pre-training description (free text, if provided)", height=68, key="pretrain_desc")

        st.markdown("---")
        st.subheader("Reader & Interaction")
        r1, r2 = st.columns(2)
        with r1:
            reader_present = st.selectbox(
                "Designated Reader present?",
                ["Yes — mandated role (protocol-defined)",
                 "Yes — team's discretion (role exists but team decides who/whether)",
                 "No",
                 "Not reported"],
                help="Sellmann-style studies where a reader role exists but "
                     "allocation is 'up to the team' code as Yes-discretion, not Yes.",
            
                key="reader_present",)
            reader_mode = st.selectbox(
                "Reader use mode (NEW v4.1)",
                ["Mandated (required by protocol)",
                 "Encouraged (not mandated)",
                 "Suggested / encouraged",
                 "Discretionary",
                 "Not used",
                 "Unclear"],
                help="Captures whether reader-use was enforced. "
                     "Distinct from who reads. "
                     "v4.3: 'Encouraged (not mandated)' added for Koers-style studies "
                     "where reader-use was actively promoted but not required.",
            
                key="reader_mode",)
        with r2:
            interaction = st.selectbox(
                "Interaction style",
                ["Read-do", "Challenge-response", "Self-read silent",
                 "Combined", "N/A (Control)", "Unclear"],
            
                key="interaction",)
            strictness = st.selectbox(
                "Strictness of CA workflow (within the aid)",
                ["Strict (every step must be completed)",
                 "Discretionary (steps can be skipped)",
                 "Mixed", "N/A (Control)", "Unclear"],
                help="If overlaps with CA use enforcement below, prioritise enforcement field.",
            
                key="strictness",)

        st.markdown("---")
        st.subheader("CA use enforcement & fidelity")
        st.caption(
            "📌 Key methodological question: *'What did the study do to ensure "
            "participants USED the cognitive aid?'* "
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
            
                key="enforcement",)
            fidelity_check = st.selectbox(
                "CA use fidelity check (was actual use monitored?)",
                ["Yes — quantitative (e.g., observed/timed use)",
                 "Yes — ordinal scale (e.g., 0–5 rating)",
                 "Yes — qualitative only (mentioned in narrative)",
                 "No (not reported)",
                 "Unclear"],
                help="v4.3: 'Yes — ordinal scale' added for Bould-style fidelity "
                     "ratings (0–5 use scale) — distinct from raw observed counts.",
            
                key="fidelity_check",)
        with e2:
            fidelity_rate = st.text_input(
                "CA use fidelity rate (% participants who actually used CA, if reported)",
                help="Leave blank if not reported. "
                     "Convention: 'wrong CA selected' counts as USED (denominator stays same, "
                     "included in numerator). Report as % and add raw counts in the "
                     "Implementation narrative — e.g., '53% (63/120 used, 5 wrong, 41 not-used)'."
            ,
                key="fidelity_rate",)

        implementation_narrative = st.text_area(
            "Implementation narrative (NEW v4.1 — free text)",
            help="Describe how the CA was implemented. Supports Plan-B narrative synthesis "
                 "if NMA proves infeasible from heterogeneity (UGRA-paper template).",
            height=100,
        
            key="implementation_narrative",)

    # -------------------------------------------------------------------------
    # TAB 4 — OUTCOMES
    # -------------------------------------------------------------------------
    with tab4:
        st.warning(
            """
**📌 Which outcome block does this study's primary result go in?**

- **Adherence (continuous, Mean/SD)** — use when study reports a continuous score (e.g., adherence %, checklist score out of N).
- **Error rate (dichotomous, events/N)** — use when study reports counts of failures (e.g., "X/Y critical steps missed", absolute/relative risk reduction).
- **Both?** If the primary outcome is process-step failure rate (Sellmann, Arriaga-style), the study can go in EITHER block depending on how the numbers are reported.
  - Has Mean failure rate per team + SD across teams → **Adherence**.
  - Has events/N at process-step level (e.g., 413/960 steps failed) → **Error rate**.
  - If both formats available, prefer Adherence (matches Protocol §8 primary).
  - If only median + percentiles in a figure (Sellmann case), flag for author contact and leave Adherence Mean/SD blank.
"""
        )
        st.markdown("---")

        # --------- Conversion calculator (Wan > Hozo > Luo) ----------
        with st.expander("💡 Median → Mean/SD Converter (Wan 2014 > Hozo 2005 > Luo 2018)",
                         expanded=False):
            st.markdown(
                "**Hierarchy** (per Protocol v2): use **Wan 2014** when median + IQR (Q1, Q3) "
                "reported; **Hozo 2005** when only median + range (min, max); **Luo 2018** "
                "for skewed or very large samples. Record which method you used. "
                "**Not covered**: median + 5th/95th percentile (Sellmann case) — flag for "
                "author contact in Adherence comments."
            )
            cvt_method = st.radio(
                "Pick reported statistic:",
                ["Wan 2014 — median + Q1 + Q3",
                 "Hozo 2005 — median + min + max",
                 "Luo 2018 — median + (min, max) [alternative mean estimator]"],
                horizontal=False,
            
                key="cvt_method",)
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
        adh_direction = st.radio(
            "★ Outcome direction (NEW v4.3 — needed for NMA SMD sign)",
            ["Higher = better (e.g., % steps completed, checklist score)",
             "Lower = better (e.g., % steps missed, failure rate)",
             "N/A — outcome not extracted in this arm"],
            horizontal=True,
            help="NMA convention: SMDs aligned so positive = pro-CA. "
                 "If outcome is reported in the 'lower=better' direction (failure %, "
                 "errors per case), the SMD sign will be flipped at analysis. "
                 "Recording direction here removes guesswork at sign-alignment.",
        
            key="adh_direction",)
        o1c1, o1c2, o1c3 = st.columns(3)
        with o1c1: adh_mean = st.text_input("★ Mean", key="adh_mean")
        with o1c2: adh_sd = st.text_input("★ SD", key="adh_sd")
        with o1c3: adh_n = st.text_input("★ N analyzed (this arm)", key="adh_n")
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
        with o2c1: time_mean = st.text_input("Mean", key="time_mean")
        with o2c2: time_sd = st.text_input("SD", key="time_sd")
        with o2c3: time_n = st.text_input("N analyzed", key="time_n")
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
        with e3c1: err_events = st.text_input("Events (this arm)", key="err_events")
        with e3c2: err_n = st.text_input("N analyzed (this arm)", key="err_n")
        with e3c3:
            err_measure = st.selectbox(
                "Effect measure",
                ["RR (primary)", "OR (secondary)", "Other", "Not reported"],
            
                key="err_measure",)
        err_orig = st.text_input("Original reporting (events/n, %, RR/OR with CI)", key="err_orig")
        err_comments = st.text_input("Error comments", key="err_comments")

        st.markdown("---")

        # --------- Outcome 4: Teamwork / NTS ----------
        st.markdown("### Outcome 4 — Teamwork / NTS (separate analysis)")
        st.caption("Non-technical skills / teamwork analysed separately.")
        nts1, nts2, nts3 = st.columns(3)
        with nts1: nts_mean = st.text_input("Mean", key="nts_mean")
        with nts2: nts_sd = st.text_input("SD", key="nts_sd")
        with nts3: nts_n = st.text_input("N analyzed", key="nts_n")
        nts_instrument = st.text_input("Instrument (e.g., ANTS, NOTECHS, T-NOTECHS)", key="nts_instrument")
        nts_comments = st.text_input("NTS comments", key="nts_comments")

    # -------------------------------------------------------------------------
    # TAB 5 — RoB & QUALITY
    # -------------------------------------------------------------------------
    with tab5:
        st.subheader("RoB-2 (for RCTs)")
        rob_levels = ["Low", "Some concerns", "High", "N/A (non-randomised)"]
        rc1, rc2 = st.columns(2)
        with rc1:
            d1 = st.selectbox("D1 — Randomisation process", rob_levels, key="d1")
            d2 = st.selectbox("D2 — Deviation from intended intervention", rob_levels, key="d2")
            d3 = st.selectbox("D3 — Missing outcome data", rob_levels, key="d3")
        with rc2:
            d4 = st.selectbox("D4 — Measurement of outcome", rob_levels, key="d4")
            d5 = st.selectbox("D5 — Selective reporting", rob_levels, key="d5")
            rob_overall = st.selectbox("★ Overall RoB-2", rob_levels, key="rob_overall")
        rob_comments = st.text_area("RoB-2 comments / supporting quotes", height=68, key="rob_comments")

        st.markdown("---")
        st.subheader("ROBINS-I (for non-randomised studies — e.g., Burden, Everett)")
        ri1, ri2 = st.columns(2)
        with ri1:
            robins_applicable = st.selectbox(
                "ROBINS-I applicable?",
                ["No — study is RCT", "Yes — non-randomised"],
            
                key="robins_applicable",)
        with ri2:
            robins_overall = st.selectbox(
                "ROBINS-I Overall",
                ["N/A", "Low", "Moderate", "Serious", "Critical", "No information"],
            
                key="robins_overall",)
        robins_comments = st.text_area("ROBINS-I comments (record per-domain judgements here)",
                                       height=68,
            key="robins_comments",)

        st.markdown("---")
        st.subheader("MERSQI (medical education research quality)")
        st.caption(
            "📊 Score each of 6 domains (Reed et al. 2007). Total is auto-computed "
            "on Submit. Per-domain scores are NOT separately stored — only the "
            "total goes to the Sheet. Use the comments box for any subscale "
            "rationale that needs to be preserved."
        )

        mq1, mq2 = st.columns(2)
        with mq1:
            mersqi_design = st.selectbox(
                "1. Study design",
                [(1.0, "Single group, post-test only"),
                 (1.5, "Single group, pre-post"),
                 (2.0, "Non-randomised 2-group"),
                 (3.0, "Randomised controlled trial (RCT)")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                key="mersqi_design",
            )
            mersqi_sampling = st.selectbox(
                "2. Sampling (institutions + response rate)",
                [(0.5, "1 institution OR response <50%"),
                 (1.0, "1 institution + response 50–74%"),
                 (1.5, "1 inst. + response ≥75%, OR 2 inst. + response 50–74%"),
                 (2.0, "2 institutions + response ≥75%"),
                 (2.5, "≥3 institutions + response 50–74%"),
                 (3.0, "≥3 institutions + response ≥75%")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                help="Simplified composite: institutions (0.5–1.5) + response rate (0.5–1.5). "
                     "Pick the row that best matches your study; use Comments for edge cases.",
                key="mersqi_sampling",
            )
            mersqi_data = st.selectbox(
                "3. Type of data",
                [(1.0, "Subjective only (self-reported)"),
                 (3.0, "Objective (observed/measured)")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                key="mersqi_data",
            )
        with mq2:
            mersqi_validity = st.selectbox(
                "4. Validity of evaluation instrument",
                [(0.0, "None of content/structure/relationships reported"),
                 (1.0, "1 of 3 validity dimensions reported"),
                 (2.0, "2 of 3 validity dimensions reported"),
                 (3.0, "All 3 (content + internal structure + relationships)")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                key="mersqi_validity",
            )
            mersqi_analysis = st.selectbox(
                "5. Data analysis (appropriateness + sophistication)",
                [(1.0, "Appropriate, descriptive only"),
                 (2.0, "Appropriate, beyond descriptive (inferential)"),
                 (3.0, "Appropriate + sophisticated (e.g., multivariable / mixed)")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                key="mersqi_analysis",
            )
            mersqi_outcomes = st.selectbox(
                "6. Outcomes (highest level only)",
                [(1.0, "Satisfaction / attitudes / opinions"),
                 (1.5, "Knowledge / skills"),
                 (2.0, "Behaviours (in practice)"),
                 (3.0, "Patient / healthcare outcomes")],
                format_func=lambda x: f"{x[0]} — {x[1]}",
                key="mersqi_outcomes",
            )

        # Auto-computed total. Note: inside an st.form, this displays the value
        # from the LAST script run (initial load or previous submit). On the
        # rerun triggered by Submit, it reflects the user's current selections,
        # which is also when it's saved to the Sheet — so the saved value is
        # always correct, even if the displayed value lags by one submit cycle.
        mersqi_total_num = (
            mersqi_design[0] + mersqi_sampling[0] + mersqi_data[0]
            + mersqi_validity[0] + mersqi_analysis[0] + mersqi_outcomes[0]
        )
        mersqi_total = f"{mersqi_total_num:.1f}"  # store as string to match other fields
        st.info(f"📊 **MERSQI total (auto-computed): {mersqi_total} / 18**")

        mersqi_comments = st.text_area(
            "MERSQI comments / subscale rationale",
            height=68,
            help="Optional. Note any domain you scored conservatively or any "
                 "ambiguity (e.g., 'Sampling: only 1 institution but unusually "
                 "high response rate of 92% — scored 1.5').",
            key="mersqi_comments",
        )

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
                datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z"), reviewer,
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
                # v4.3 additions (appended to match SHEET_HEADERS)
                pub_type, author_contact, adh_direction,
                # v4.4 addition
                coding_uncertainty_log,
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
- **NEXT ARM, same study**: update Arm No., Arm Label, NMA Node, and Outcomes only — other fields stay.
- **NEW study**: refresh browser (F5 / Cmd+R) to clear all fields.
"""
                    )
                except Exception as e:
                    st.error(f"❌ Could not write to sheet: {e}")
