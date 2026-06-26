"""
Cognitive Aids NMA — Data Extraction Tool (v5.2)
Streamlit app matching extraction form.
Deploy: GitHub → Streamlit Community Cloud.

Requires:
  - st.secrets["gcp_service_account"] : service-account JSON
  - Google Sheet with header row matching SHEET_HEADERS below

v5.2 changes (from v5.1):
  - MERGE KEYS for 4-reviewer dual independent extraction:
      * "Study ID (Covidence)" — the Covidence record number (e.g. 9405), REQUIRED.
        This is the stable per-study key reviewers read straight off Covidence; it
        removes author/year ambiguity (Siebert x4, St Pierre x2, Marshall x2, etc.)
        when two reviewers' rows are reconciled later.
      * "Phase" — Calibration / Main, REQUIRED. Calibration papers are re-extracted
        in Main, so the same reviewer enters a study twice; Phase keeps them apart.
    Both inserted right after "Reviewer" (sheet columns 3 and 4). SHEET_HEADERS 79 -> 81.
    Reconciliation / IRR merge key = Study ID + Phase + Reviewer + Arm No.
  - Reviewer field can be locked to a fixed pick-list: set REVIEWERS = [...4 names...]
    near the top to make it a dropdown (prevents "A"/"a"/"Reviewer A" drift that breaks
    merging). Left empty ([]), Reviewer stays a free-text box (unchanged behaviour).

v5.1 changes (from v5.0):
  - FIDELITY-RATE GATE: "CA use fidelity rate (%)" is now gated by the existing
    "CA use fidelity check" field, NOT by a new 5th gate column.
      * If fidelity check == "Yes — quantitative", a rate is REQUIRED (a blank is
        treated as missing → blocks submission). A quantitative check implies the
        source reported a number, so a blank there is an unrecorded value.
      * For any other check value (ordinal / qualitative / No / Unclear / N-A),
        the rate is left blank and that blank is EXPLAINED by the check field —
        i.e. a true "no quantitative fidelity measure in source", not a forgotten
        entry. This resolves the blank-vs-absent ambiguity WITHOUT adding a column.
    Validation-time only (consistent with the four outcome gates), because widgets
    inside st.form do not re-render on change. SHEET_HEADERS unchanged (still 79).
  - Robustness: "Adherence outcome direction" is now written via _s() so a None
    (when the Adherence gate != "Reported") is stored as "" like every other gated
    field, instead of a raw Python None.

v5.0 changes (from prior build):
  - RoB-2 and MERSQI are now OPTIONAL (assess once per study, normally on Arm 1).
    They are NOT in the blocking required-field checks, so Arm 2/3 submissions
    no longer force re-entry of identical study-level ratings.
  - Error effect-measure field re-labelled to record HOW THE PAPER reported it
    (RR / OR / raw counts / not reported). Raw events + N remain the true
    extraction target; pooled measure (RR) is computed at analysis stage.
  - Median-converter input labels clarified per method (IQR vs range).
  - Total N / Arm N default to blank (None) instead of 0.
  - Adherence-direction note: harmonisation to "higher = better" is performed
    at ANALYSIS stage; here you only record the raw values + their direction.
  - OUTCOME GATES: each of the 4 outcomes (Adherence, Time, Error, NTS) now has
    a required "... reported?" selectbox with options
    [Reported / Not measured / Measured – not extractable / Unclear].
    This distinguishes a TRUE ABSENCE in the source from a blank (not-yet-entered).
    Sub-fields are only enforced when the gate == "Reported".
    Adherence outcome direction is now conditional on the Adherence gate too.
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
TZ = ZoneInfo("America/Toronto")

# stdlib replacement for scipy.stats.norm.ppf
_norm_ppf = NormalDist().inv_cdf

st.set_page_config(page_title="Cognitive Aids NMA Extraction v5.2", layout="wide")

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
# ⚠️ WARNING: Ensure ROBINS-I columns are deleted from the Google Sheet!
# ⚠️ v5.0 gate update: insert FOUR new header columns, each immediately to the
#    LEFT of its outcome block's first field:
#      "Adherence reported?"  before  "Adherence Mean"
#      "Time reported?"       before  "Time Mean"
#      "Error reported?"      before  "Error events"
#      "NTS reported?"        before  "NTS Mean"
#    Total columns: 75 -> 79.
# ⚠️ v5.1: NO new columns. The fidelity-rate gate is validation-only and reuses
#    the existing "CA use fidelity check" field. Column count stays 79.
# ⚠️ v5.2: insert TWO new header columns immediately AFTER "Reviewer" (sheet cols
#    C and D), shifting everything else right:
#      "Study ID (Covidence)"   (col C)
#      "Phase"                  (col D)
#    Do this BEFORE any extraction starts. Total columns: 79 -> 81.
# =============================================================================
SHEET_HEADERS = [
    "Timestamp", "Reviewer",
    # Merge keys (v5.2) — Covidence record # + extraction phase
    "Study ID (Covidence)", "Phase",
    # Study info
    "Lead Author", "Year", "Study Type", "Country", "Setting", "Scenario",
    "Simulation Fidelity", "Scenario Complexity",
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
    "Adherence reported?",
    "Adherence Mean", "Adherence SD", "Adherence N analyzed",
    "Adherence original format", "Adherence raw median stats",
    "Adherence conversion method", "Adherence Kirkpatrick level",
    "Adherence comments",
    # Outcome 2: Time to critical action (SECONDARY, continuous)
    "Time reported?",
    "Time Mean", "Time SD", "Time N analyzed",
    "Time original format", "Time raw median stats",
    "Time conversion method", "Time comments",
    # Outcome 3: Error rate (SECONDARY, dichotomous)
    "Error reported?",
    "Error events", "Error N analyzed", "Error measure as reported",
    "Error original reporting", "Error comments",
    # Outcome 4: Teamwork / NTS (separate analysis)
    "NTS reported?",
    "NTS Mean", "NTS SD", "NTS N analyzed",
    "NTS instrument", "NTS comments",
    # RoB-2 (RCT only — assess once per study, normally on Arm 1)
    "RoB-2 D1 Randomization", "RoB-2 D2 Deviation",
    "RoB-2 D3 Missing data", "RoB-2 D4 Measurement",
    "RoB-2 D5 Selective reporting", "RoB-2 Overall", "RoB-2 Comments",
    # MERSQI (assess once per study, normally on Arm 1)
    "MERSQI total (max 18)", "MERSQI Comments",
    # Metadata
    "Publication type",
    "Author contact status",
    "Adherence outcome direction",
    "Coding uncertainty log",
]

# Shared option list for the four outcome gates
GATE_OPTS = ["Reported", "Not measured", "Measured – not extractable", "Unclear"]

# Optional fixed reviewer pick-list (v5.2). Fill in the 4 reviewer names to turn the
# Reviewer field into a dropdown — this prevents name-spelling drift ("A"/"a"/
# "Reviewer A") that would break the later merge. Leave empty ([]) to keep Reviewer
# as a free-text box (unchanged from v5.1).
REVIEWERS = []  # e.g. ["Angelique", "Reviewer B", "Reviewer C", "Reviewer D"]

# =============================================================================
# UI
# =============================================================================
st.title("🌐 Cognitive Aids NMA — Data Extraction (v5.2)")
st.info(
    """
**📌 INSTRUCTIONS**
1. **Reviewer / Study ID / Phase** (Tab 1) — all required. **Study ID = the Covidence record number** for this paper (e.g. 9405); type it exactly as Covidence shows it. **Phase** = *Calibration* (the shared alignment papers) or *Main* (the full extraction).
2. Extract data for **ONE arm per submission**.
3. **Multi-arm study**: after submitting arm 1, just update Arm No., Arm Label, NMA Node, and Outcomes → Submit again. Other fields stay.
4. **New study**: refresh browser (F5 / Cmd+R) to clear all fields.
5. ★ = NMA-critical field (Node, N per arm, Mean/SD/N for primary outcome).
6. For median-reported outcomes, use the **Median → Mean/SD converter** in Tab 4.
7. **RoB-2 & MERSQI are study-level** — assess them ONCE per study (normally on Arm 1). They are optional on later arms of the same study; leave blank to avoid duplicate entry.
8. **Outcome gates** (Tab 4): for EACH outcome pick whether it is *Reported / Not measured / Measured–not extractable / Unclear*. Sub-fields are only required when you pick **Reported**. This records a TRUE absence instead of an ambiguous blank.
9. **Fidelity rate** (Tab 3): fill *CA use fidelity rate (%)* ONLY when *CA use fidelity check* = "Yes — quantitative" (then it is required). For any other check value, leave it blank — the check field already records why there is no rate.
"""
)

def _s(x):
    """Stringify safely for gspread: None → empty string, else str(x)."""
    return "" if x is None else str(x)

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
        st.subheader("Reviewer & Study key")
        rv1, rv2, rv3 = st.columns(3)
        with rv1:
            if REVIEWERS:
                reviewer = st.selectbox("Reviewer ★", REVIEWERS, key="reviewer",
                    index=None, placeholder="— select your name —")
            else:
                reviewer = st.text_input("Reviewer Name ★", key="reviewer")
        with rv2:
            study_id = st.number_input(
                "Study ID (Covidence) ★", min_value=1, value=None, step=1,
                placeholder="— Covidence # —", key="study_id",
                help="The Covidence record number shown for this study (e.g. 9405). "
                     "This is the MERGE KEY — type it exactly as Covidence shows it. "
                     "It stays the same across all arms of the study.")
        with rv3:
            phase = st.selectbox(
                "Phase ★", ["Calibration", "Main"], key="phase",
                index=None, placeholder="— select —",
                help="Calibration = the shared 3–5 alignment papers (all reviewers). "
                     "Main = the full extraction. Calibration papers are re-extracted "
                     "in Main, so pick the correct phase for THIS entry.")

        st.markdown("---")
        st.subheader("General Study Characteristics")
        c1, c2, c3 = st.columns(3)
        with c1:
            author = st.text_input("Lead Author (last name)", key="author")
            year = st.number_input(
                "Publication Year",
                min_value=1990, max_value=2030,
                value=None, step=1,
                placeholder="— enter year —",
                key="year",
            )
            # Study types: RCT designs only (observational/pilot removed)
            study_type = st.selectbox(
                "Study Type",
                ["Parallel RCT", "Crossover RCT", "Cluster RCT", "Other"],
                key="study_type",
                index=None,
                placeholder="— select —",
            )
        with c2:
            country = st.text_input("Country", key="country")
            setting = st.selectbox(
                "Simulated scenario setting",
                ["OR / Anaesthesia", "ICU", "ED", "Neonatal / Paediatric",
                 "Pre-hospital / EMS", "In-flight / aeromedical", "Ward", "Other"],
                key="setting",
                index=None,
                placeholder="— select —",
            )
            scenario = st.text_input("Scenario (e.g., MH, cardiac arrest)", key="scenario")
        with c3:
            total_n = st.number_input("Total N (all arms)", min_value=0, value=None,
                                      step=1, placeholder="— enter N —", key="total_n")
            arm_n = st.number_input("★ N (this arm)", min_value=0, value=None,
                                    step=1, placeholder="— enter N —", key="arm_n")

        st.markdown("---")
        st.subheader("Simulation Context")
        sc1, sc2 = st.columns(2)
        with sc1:
            sim_fidelity = st.selectbox(
                "★ Simulation fidelity [for heterogeneity analysis]",
                ["Low-fidelity (part-task / paper case / static manikin)",
                 "Mid-fidelity (full manikin + scripted vitals, no physiology engine)",
                 "High-fidelity (full manikin + dynamic physiology + realistic environment)",
                 "Unclear"],
                help=(
                    "Three-tier framework (Maran & Glavin 2003; INACSL standards). "
                    "Code by the SIMULATOR + ENVIRONMENT actually used in the study, "
                    "not by the study's self-label.\n\n"
                    "• **Low**: part-task trainer, paper/screen-only case, static manikin — no dynamic response.\n"
                    "• **Mid**: full manikin (e.g., Resusci Anne, ALS Skillmaster, NeoNatalie) "
                    "with scripted or operator-driven vitals; monitor displays values but no underlying physiology engine.\n"
                    "• **High**: full-body manikin (e.g., SimMan 3G, HPS) with dynamic physiology AND realistic clinical environment (sim OR / ED / ICU).\n"
                    "• **Unclear**: simulator details not reported sufficiently to classify — note in Coding uncertainty log."
                ),
                key="sim_fidelity",
                index=None,
                placeholder="— select —",
            )
        with sc2:
            scen_complexity = st.selectbox(
                "★ Scenario complexity [for heterogeneity analysis]",
                ["Complex emergency", "Simple task", "Unclear"],
                help="Complex emergencies require differential diagnoses or managing multiple concurrent actions (e.g., MH, cardiac arrest). Simple tasks involve linear, routine clinical procedures.",
                key="scen_complexity",
                index=None,
                placeholder="— select —",
            )

        st.markdown("---")
        st.subheader("Publication Metadata")
        pm1, pm2 = st.columns(2)
        with pm1:
            pub_type = st.selectbox(
                "Publication type",
                ["Full original research", "Correspondence / Letter", "Conference abstract", "Other"],
                key="pub_type",
                index=None,
                placeholder="— select —",
            )
        with pm2:
            author_contact = st.selectbox(
                "Author contact status",
                ["Not needed", "Pending decision", "Sent — awaiting reply",
                 "Received — data added", "Sent — no reply / declined"],
                key="author_contact",
                index=None,
                placeholder="— select —",
            )

        st.markdown("---")
        st.subheader("Population & Team")
        p1, p2, p3 = st.columns(3)
        with p1:
            unit_random = st.selectbox(
                "Unit of randomisation",
                ["Individual (single-provider)", "Team (multi-provider)", "Cluster", "Unclear"],
                key="unit_random",
                index=None,
                placeholder="— select —",
            )
            exp_level = st.selectbox(
                "★ Provider experience",
                ["Trainee", "Experienced", "Mixed", "Unclear"],
                key="exp_level",
                index=None,
                placeholder="— select —",
            )
        with p2:
            team_compo = st.text_input("Team composition (free text)", key="team_compo")
            team_inter = st.selectbox(
                "Team interprofessionality",
                ["Single-discipline", "Interdisciplinary (multi-specialty, same profession)",
                 "Interprofessional (multi-profession)", "Mixed across arms", "Individual (N/A)", "Unclear"],
                key="team_inter",
                index=None,
                placeholder="— select —",
            )

        st.markdown("---")
        st.subheader("Coding uncertainty log")
        coding_uncertainty_log = st.text_area(
            "If any field was coded as 'Unclear' / 'Not reported', note WHY here:",
            height=100,
            key="coding_uncertainty_log",
        )

    # -------------------------------------------------------------------------
    # TAB 2 — CA & NMA NODE
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("NMA Node — classify by FUNCTION, not medium")
        n1, n2 = st.columns([1, 2])
        with n1:
            nma_node = st.selectbox("★ NMA Node", ["Control", "Static", "Dynamic"], key="nma_node",
                index=None, placeholder="— select —")
            arm_no = st.number_input("★ Arm No.", 1, 10, 1, key="arm_no")
        with n2:
            node_rationale = st.text_area("Node rationale (1 line)", height=68, key="node_rationale")

        st.markdown("---")
        st.subheader("Cognitive Aid Description")
        a1, a2 = st.columns(2)
        with a1:
            arm_label = st.text_input("★ Arm Label", key="arm_label")
            aid_name = st.text_input("Name of Cognitive Aid", key="aid_name")
        with a2:
            medium = st.selectbox("Format — medium",
                ["Paper", "Digital — PDF/static screen", "Digital — app/tablet",
                 "Digital — AR/VR", "Hybrid (paper + digital)", "N/A (Control arm)", "Other"],
                key="medium", index=None, placeholder="— select —")
            ca_type = st.selectbox("Format — type",
                ["Checklist", "Chart / flow diagram", "App", "Tablet interface",
                 "AR overlay", "Mnemonic / memory aid", "N/A (Control)", "Other"],
                key="ca_type", index=None, placeholder="— select —")

        ca_logic = st.selectbox("CA logic structure",
            ["Linear (sequential, no branching)", "Stepwise (sequential, one path)",
             "Branching (decision-tree, adapts to user input)", "Mixed",
             "Unclear from main text", "N/A (Control)"],
            key="ca_logic", index=None, placeholder="— select —")

    # -------------------------------------------------------------------------
    # TAB 3 — IMPLEMENTATION FACTORS
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Pre-training (before the simulation)")
        t1, t2 = st.columns(2)
        with t1:
            pretrain_intensity = st.selectbox("Pre-training intensity",
                ["None", "Minimal (<30 min)", "Structured (≥30 min)", "Unclear"],
                key="pretrain_intensity", index=None, placeholder="— select —")
            train_duration = st.text_input("Training duration", key="train_duration")
        with t2:
            train_method = st.selectbox("Training method",
                ["None", "Lecture", "Video", "Hands-on / orientation", "Combined", "Unclear"],
                key="train_method", index=None, placeholder="— select —")
            train_timing = st.selectbox("Training timing",
                ["None", "Immediately before scenario", "Same day", "Earlier in study", "Unclear"],
                key="train_timing", index=None, placeholder="— select —")
        pretrain_desc = st.text_area("Pre-training description", height=68, key="pretrain_desc")

        st.markdown("---")
        st.subheader("Reader & Interaction")
        r1, r2 = st.columns(2)
        with r1:
            reader_present = st.selectbox("Designated Reader present?",
                ["Yes — mandated role (protocol-defined)",
                 "Yes — team's discretion (role exists but team decides)",
                 "No", "Not reported"],
                key="reader_present", index=None, placeholder="— select —")
            reader_mode = st.selectbox("Reader use mode",
                ["Mandated (required by protocol)", "Encouraged (not mandated)",
                 "Suggested / encouraged", "Discretionary", "Not used", "Unclear"],
                key="reader_mode", index=None, placeholder="— select —")
        with r2:
            interaction = st.selectbox("Interaction style",
                ["Read-do", "Do-verify", "Challenge-response", "Self-read silent", "Combined", "N/A (Control)", "Unclear"],
                help="'Read-do' means reading the aid before acting. 'Do-verify' means acting from memory first, then checking the aid to catch missed steps.",
                key="interaction", index=None, placeholder="— select —")
            strictness = st.selectbox("Strictness of CA workflow",
                ["Strict (every step must be completed)", "Discretionary (steps can be skipped)",
                 "Mixed", "N/A (Control)", "Unclear"],
                key="strictness", index=None, placeholder="— select —")

        st.markdown("---")
        st.subheader("CA use enforcement & fidelity")
        e1, e2 = st.columns(2)
        with e1:
            enforcement = st.selectbox("CA use enforcement",
                ["Mandated (participants required to consult CA)",
                 "Encouraged (instructed but not enforced)",
                 "Available-only (CA placed in environment, no instruction)", "Unclear", "N/A (Control)"],
                key="enforcement", index=None, placeholder="— select —")
            fidelity_check = st.selectbox("CA use fidelity check (was actual use monitored?)",
                ["Yes — quantitative (e.g., observed/timed use)",
                 "Yes — ordinal scale (e.g., 0–5 rating)",
                 "Yes — qualitative only", "No (not reported)", "Unclear", "N/A (Control)"],
                key="fidelity_check", index=None, placeholder="— select —")
        with e2:
            fidelity_rate = st.text_input(
                "CA use fidelity rate (%)",
                help="Gated by 'CA use fidelity check'. Enter the observed % CA use ONLY when "
                     "the check = 'Yes — quantitative' (then it is required). For any other "
                     "check value (ordinal / qualitative / No / Unclear / N-A), leave blank — "
                     "the blank is explained by the check field, not an unrecorded value.",
                key="fidelity_rate",
            )
            st.caption("Required only if fidelity check = 'Yes — quantitative'; otherwise a "
                       "blank is a true 'no quantitative measure in source', not an unfilled field.")

        implementation_narrative = st.text_area("Implementation narrative", height=100, key="implementation_narrative")

    # -------------------------------------------------------------------------
    # TAB 4 — OUTCOMES
    # -------------------------------------------------------------------------
    with tab4:
        with st.expander("💡 Median → Mean/SD Converter"):
            cvt_method = st.radio("Pick reported statistic:",
                ["Wan 2014 — median + Q1 + Q3 (IQR)",
                 "Hozo 2005 — median + min + max (range)",
                 "Luo 2018 — median + min + max (range)"],
                key="cvt_method")
            # Dynamic labels per method
            if cvt_method.startswith("Wan"):
                lo_label, hi_label = "Q1 (lower quartile)", "Q3 (upper quartile)"
            else:
                lo_label, hi_label = "min", "max"
            cv1, cv2, cv3, cv4 = st.columns(4)
            with cv1: cv_med = st.number_input("Median", value=0.0, format="%.4f", key="cv_med")
            with cv2: cv_a = st.number_input(lo_label, value=0.0, format="%.4f", key="cv_a")
            with cv3: cv_b = st.number_input(hi_label, value=0.0, format="%.4f", key="cv_b")
            with cv4: cv_n = st.number_input("n", min_value=1, value=10, key="cv_n")

            if st.form_submit_button("📐 Compute"):
                try:
                    if cvt_method.startswith("Wan"):
                        # Wan 2014, median + IQR (Eq. 14 mean, Eq. 16 SD)
                        mean_est = (cv_a + cv_med + cv_b) / 3
                        xi = 2 * _norm_ppf((0.75 * cv_n - 0.125) / (cv_n + 0.25))
                        sd_est = (cv_b - cv_a) / xi
                        method_used = f"Wan 2014 IQR (η={xi:.3f})"
                    elif cvt_method.startswith("Hozo"):
                        # Hozo 2005, median + range
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
                        # Luo 2018 mean (range) + Hozo 2005 SD (range) — consistent range basis
                        w = 4 / (4 + cv_n ** 0.75)
                        mean_est = w * (cv_a + cv_b) / 2 + (1 - w) * cv_med
                        if cv_n <= 15:
                            sd_est = (cv_b - cv_a) / (2 * math.sqrt(3))
                            sd_rule = "n≤15: range/(2√3)"
                        elif cv_n <= 70:
                            sd_est = (cv_b - cv_a) / 4
                            sd_rule = "15<n≤70: range/4"
                        else:
                            sd_est = (cv_b - cv_a) / 6
                            sd_rule = "n>70: range/6"
                        method_used = f"Luo 2018 mean + Hozo 2005 SD ({sd_rule})"
                    st.success(f"**Mean ≈ {mean_est:.3f} | SD ≈ {sd_est:.3f}** ({method_used})")
                except Exception as e:
                    st.error(f"Calc error: {e}")

        st.markdown("---")
        st.markdown("### Outcome 1 — Adherence / task completion (★ PRIMARY, continuous, SMD)")
        adh_gate = st.selectbox("★ Adherence reported?", GATE_OPTS,
            help="Pick 'Reported' only if mean/SD/N (or convertible median stats) are available. "
                 "'Not measured' = study did not assess this outcome. "
                 "'Measured – not extractable' = assessed but usable numbers not given (→ author-contact candidate). "
                 "'Unclear' = cannot tell from the text.",
            key="adh_gate", index=None, placeholder="— select —")
        st.caption("Record the RAW values as reported. Direction harmonisation (so higher = better) is done at the ANALYSIS stage, not here — you only record the value + which direction it represents.")
        adh_direction = st.radio("★ Outcome direction",
            ["Higher = better (e.g., % steps completed, checklist score)",
             "Lower = better (e.g., % steps missed, failure rate)",
             "N/A — outcome not extracted in this arm"],
            horizontal=True, key="adh_direction", index=None)
        o1c1, o1c2, o1c3 = st.columns(3)
        with o1c1: adh_mean = st.number_input("★ Mean", value=None, format="%.4f", key="adh_mean")
        with o1c2: adh_sd = st.number_input("★ SD", value=None, min_value=0.0, format="%.4f", key="adh_sd")
        with o1c3: adh_n = st.number_input("★ N analyzed (this arm)", value=None, min_value=0, step=1, key="adh_n")
        o1c4, o1c5 = st.columns(2)
        with o1c4:
            adh_orig = st.selectbox("Original reporting format",
                ["mean ± SD", "median + IQR", "median + range", "%/proportion", "Other", "Not extractable"],
                key="adh_orig", index=None, placeholder="— select —")
            adh_raw = st.text_input("Raw median stats (median; Q1–Q3 OR min–max; n)", key="adh_raw")
        with o1c5:
            adh_conv = st.selectbox("Conversion method (if median→mean)",
                ["N/A — reported as mean", "Wan 2014 (median+IQR)", "Hozo 2005 (median+range)", "Luo 2018", "Other"],
                key="adh_conv", index=None, placeholder="— select —")
            adh_kp = st.selectbox("Kirkpatrick level",
                ["KP1 Reaction", "KP2 Learning", "KP3 Behaviour", "KP4 Results", "N/A"],
                key="adh_kp", index=None, placeholder="— select —")
        adh_comments = st.text_input("Adherence comments", key="adh_comments")

        st.markdown("---")
        st.markdown("### Outcome 2 — Time to first critical action (SECONDARY, continuous)")
        time_gate = st.selectbox("★ Time reported?", GATE_OPTS,
            key="time_gate", index=None, placeholder="— select —")
        o2c1, o2c2, o2c3 = st.columns(3)
        with o2c1: time_mean = st.number_input("Mean (seconds)", value=None, format="%.4f", key="time_mean")
        with o2c2: time_sd = st.number_input("SD (seconds)", value=None, min_value=0.0, format="%.4f", key="time_sd")
        with o2c3: time_n = st.number_input("N analyzed", value=None, min_value=0, step=1, key="time_n")
        o2c4, o2c5 = st.columns(2)
        with o2c4:
            time_orig = st.selectbox("Original reporting format",
                ["mean ± SD", "median + IQR", "median + range", "Other", "Not reported"],
                key="time_orig", index=None, placeholder="— select —")
        with o2c5:
            time_raw = st.text_input("Raw median stats (if median)", key="time_raw")
            time_conv = st.selectbox("Conversion method",
                ["N/A", "Wan 2014", "Hozo 2005", "Luo 2018", "Other"],
                key="time_conv", index=None, placeholder="— select —")
        time_comments = st.text_input("Time comments", key="time_comments")

        st.markdown("---")
        st.markdown("### Outcome 3 — Error rate (SECONDARY, dichotomous)")
        err_gate = st.selectbox("★ Error reported?", GATE_OPTS,
            key="err_gate", index=None, placeholder="— select —")
        st.caption("Extract raw EVENTS + N. The pooled effect measure for the NMA is RR, computed from events/N at the analysis stage. The field below only records HOW THE PAPER reported it (for reference / when raw counts are unavailable).")
        e3c1, e3c2, e3c3 = st.columns(3)
        with e3c1: err_events = st.number_input("★ Events (this arm)", value=None, min_value=0, step=1, key="err_events")
        with e3c2: err_n = st.number_input("★ N analyzed (this arm)", value=None, min_value=0, step=1, key="err_n")
        with e3c3:
            err_measure = st.selectbox("Measure as reported in paper",
                ["Raw counts / events given", "RR reported", "OR reported",
                 "Other relative measure", "Not reported"],
                help="What did the paper itself report? If raw counts/events are available, prefer those (enter Events + N on the left); we compute RR ourselves. Record OR only if that is all the paper provides.",
                key="err_measure", index=None, placeholder="— select —")
        err_orig = st.text_input("Original reporting (free text — e.g., 'OR 2.3 (1.1–4.8)')", key="err_orig")
        err_comments = st.text_input("Error comments", key="err_comments")

        st.markdown("---")
        st.markdown("### Outcome 4 — Teamwork / NTS (separate analysis)")
        nts_gate = st.selectbox("★ NTS reported?", GATE_OPTS,
            key="nts_gate", index=None, placeholder="— select —")
        nts1, nts2, nts3 = st.columns(3)
        with nts1: nts_mean = st.number_input("Mean", value=None, format="%.4f", key="nts_mean")
        with nts2: nts_sd = st.number_input("SD", value=None, min_value=0.0, format="%.4f", key="nts_sd")
        with nts3: nts_n = st.number_input("N analyzed", value=None, min_value=0, step=1, key="nts_n")
        nts_instrument = st.text_input("Instrument", key="nts_instrument")
        nts_comments = st.text_input("NTS comments", key="nts_comments")

    # -------------------------------------------------------------------------
    # TAB 5 — RoB & QUALITY  (study-level — assess once per study, normally Arm 1)
    # -------------------------------------------------------------------------
    with tab5:
        st.info("ℹ️ **RoB-2 and MERSQI are STUDY-LEVEL.** Assess them once per study (normally on Arm 1). On later arms of the same study you may leave these blank — they are optional and will not block submission.")
        st.subheader("RoB-2 (for RCTs)")
        rob_levels = ["Low", "Some concerns", "High"]
        rc1, rc2 = st.columns(2)
        with rc1:
            d1 = st.selectbox("D1 — Randomisation process", rob_levels, key="d1", index=None, placeholder="— select —")
            d2 = st.selectbox("D2 — Deviation from intended intervention", rob_levels, key="d2", index=None, placeholder="— select —")
            d3 = st.selectbox("D3 — Missing outcome data", rob_levels, key="d3", index=None, placeholder="— select —")
        with rc2:
            d4 = st.selectbox("D4 — Measurement of outcome", rob_levels, key="d4", index=None, placeholder="— select —")
            d5 = st.selectbox("D5 — Selective reporting", rob_levels, key="d5", index=None, placeholder="— select —")
            rob_overall = st.selectbox("Overall RoB-2", rob_levels, key="rob_overall", index=None, placeholder="— select —")
        rob_comments = st.text_area("RoB-2 comments", height=68, key="rob_comments")

        st.markdown("---")
        st.subheader("MERSQI (medical education research quality)")
        mq1, mq2 = st.columns(2)
        with mq1:
            mersqi_design = st.selectbox("1. Study design",
                [(1.0, "Single group, post-test only"), (1.5, "Single group, pre-post"),
                 (2.0, "Non-randomised 2-group"), (3.0, "Randomised controlled trial (RCT)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_design", index=None, placeholder="— select —")
            mersqi_sampling = st.selectbox("2. Sampling (institutions + response rate)",
                [(0.5, "1 institution OR response <50%"), (1.0, "1 institution + response 50–74%"),
                 (1.5, "1 inst. + response ≥75%, OR 2 inst. + response 50–74%"),
                 (2.0, "2 institutions + response ≥75%"), (2.5, "≥3 institutions + response 50–74%"),
                 (3.0, "≥3 institutions + response ≥75%")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_sampling", index=None, placeholder="— select —")
            mersqi_data = st.selectbox("3. Type of data",
                [(1.0, "Subjective only (self-reported)"), (3.0, "Objective (observed/measured)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_data", index=None, placeholder="— select —")
        with mq2:
            mersqi_validity = st.selectbox("4. Validity of evaluation instrument",
                [(0.0, "None of content/structure/relationships reported"),
                 (1.0, "1 of 3 validity dimensions reported"),
                 (2.0, "2 of 3 validity dimensions reported"),
                 (3.0, "All 3 (content + internal structure + relationships)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_validity", index=None, placeholder="— select —")
            mersqi_analysis = st.selectbox("5. Data analysis (appropriateness + sophistication)",
                [(1.0, "Appropriate, descriptive only"), (2.0, "Appropriate, beyond descriptive (inferential)"),
                 (3.0, "Appropriate + sophisticated (e.g., multivariable / mixed)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_analysis", index=None, placeholder="— select —")
            mersqi_outcomes = st.selectbox("6. Outcomes (highest level only)",
                [(1.0, "Satisfaction / attitudes / opinions"), (1.5, "Knowledge / skills"),
                 (2.0, "Behaviours (in practice)"), (3.0, "Patient / healthcare outcomes")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_outcomes", index=None, placeholder="— select —")

        _mersqi_subscores = [mersqi_design, mersqi_sampling, mersqi_data, mersqi_validity, mersqi_analysis, mersqi_outcomes]
        if any(s is None for s in _mersqi_subscores):
            mersqi_total = ""
            _n_done = sum(1 for s in _mersqi_subscores if s is not None)
            if _n_done > 0:
                st.warning(f"⚠️ MERSQI partial: {_n_done}/6 domains selected. Complete all 6 (study-level) or leave all blank on duplicate arms.")
        else:
            mersqi_total_num = sum(s[0] for s in _mersqi_subscores)
            mersqi_total = f"{mersqi_total_num:.1f}"
            st.info(f"📊 **MERSQI total (auto-computed): {mersqi_total} / 18**")

        mersqi_comments = st.text_area("MERSQI comments", height=68, key="mersqi_comments")

    # =========================================================================
    # SUBMIT
    # =========================================================================
    st.markdown("---")
    submitted = st.form_submit_button("💾 Submit Arm Data")

    if submitted:
        missing_text = []
        if not (reviewer and str(reviewer).strip()): missing_text.append("Reviewer (Tab 1)")
        if study_id is None: missing_text.append("Study ID (Covidence) (Tab 1)")
        if phase is None: missing_text.append("Phase (Tab 1)")
        if not author.strip(): missing_text.append("Lead Author (Tab 1)")
        if year is None: missing_text.append("Publication Year (Tab 1)")

        # Required per-ARM fields (study/intervention/implementation/outcome-gates).
        # RoB-2 and MERSQI are STUDY-LEVEL and intentionally NOT included here.
        CRITICAL_FIELDS = [
            ("Study type",                 study_type,         "Tab 1"),
            ("Setting",                    setting,            "Tab 1"),
            ("Simulation fidelity",        sim_fidelity,       "Tab 1"),
            ("Scenario complexity",        scen_complexity,    "Tab 1"),
            ("Publication type",           pub_type,           "Tab 1"),
            ("Unit of randomisation",      unit_random,        "Tab 1"),
            ("Provider experience level",  exp_level,          "Tab 1"),
            ("Team interprofessionality",  team_inter,         "Tab 1"),
            ("NMA Node",                   nma_node,           "Tab 2"),
            ("CA medium",                  medium,             "Tab 2"),
            ("CA type",                    ca_type,            "Tab 2"),
            ("CA logic structure",         ca_logic,           "Tab 2"),
            ("Pre-training intensity",     pretrain_intensity, "Tab 3"),
            ("Training method",            train_method,       "Tab 3"),
            ("Training timing",            train_timing,       "Tab 3"),
            ("Reader present",             reader_present,     "Tab 3"),
            ("Interaction style",          interaction,        "Tab 3"),
            ("Strictness",                 strictness,         "Tab 3"),
            ("Enforcement",                enforcement,        "Tab 3"),
            ("Fidelity check",             fidelity_check,     "Tab 3"),
            # Outcome gates — all four required every arm
            ("Adherence reported?",        adh_gate,           "Tab 4"),
            ("Time reported?",             time_gate,          "Tab 4"),
            ("Error reported?",            err_gate,           "Tab 4"),
            ("NTS reported?",              nts_gate,           "Tab 4"),
        ]
        # NOTE: "Adherence outcome direction" is no longer always-required; it is
        # now conditional on the Adherence gate == "Reported" (see below).

        missing_select = [f"• **{name}** ({tab})" for name, val, tab in CRITICAL_FIELDS if val is None]

        conditional_missing = []
        # Adherence: enforce sub-fields only when the outcome is actually reported
        if adh_gate == "Reported":
            if adh_direction is None: conditional_missing.append("• **Adherence outcome direction** (Tab 4)")
            if adh_mean is None: conditional_missing.append("• **Adherence Mean** (Tab 4)")
            if adh_sd is None:   conditional_missing.append("• **Adherence SD** (Tab 4)")
            if adh_n is None:    conditional_missing.append("• **Adherence N analyzed** (Tab 4)")
            if adh_orig is None: conditional_missing.append("• **Adherence original format** (Tab 4)")
            if adh_conv is None: conditional_missing.append("• **Adherence conversion method** (Tab 4)")
            if adh_kp is None:   conditional_missing.append("• **Adherence Kirkpatrick level** (Tab 4)")
        # Time: enforce reporting format + conversion only when reported
        if time_gate == "Reported":
            if time_orig is None: conditional_missing.append("• **Time original format** (Tab 4)")
            if time_conv is None: conditional_missing.append("• **Time conversion method** (Tab 4)")
        # Error: enforce 'measure as reported' only when reported
        if err_gate == "Reported":
            if err_measure is None: conditional_missing.append("• **Error measure as reported** (Tab 4)")
        # NTS: gate is required but no sub-fields are forced (mean/SD/instrument left to reviewer)

        # Fidelity-rate gate (v5.1): a rate is required only when the fidelity check is
        # quantitative. This disambiguates a blank (true N/A vs unrecorded) WITHOUT a
        # 5th gate column — the check field carries the "is there a measure?" signal.
        if (fidelity_check == "Yes — quantitative (e.g., observed/timed use)"
                and not fidelity_rate.strip()):
            conditional_missing.append(
                "• **CA use fidelity rate (%)** — required because fidelity check = "
                "'Yes — quantitative' (Tab 3)")

        # MERSQI partial-entry guard: if SOME but not all 6 domains entered, block
        # (prevents half-filled study-level scores). All-blank is allowed (duplicate arm).
        _n_mersqi = sum(1 for s in _mersqi_subscores if s is not None)
        if 0 < _n_mersqi < 6:
            conditional_missing.append("• **MERSQI** — complete all 6 domains or leave all blank (Tab 5)")

        if missing_text or missing_select or conditional_missing:
            err_lines = ["❌ **Cannot submit — required fields missing:**"]
            if missing_text: err_lines += [f"• **{x}**" for x in missing_text]
            err_lines += missing_select + conditional_missing
            st.error("\n\n".join(err_lines))
        else:
            row_data = [
                datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z"), reviewer,
                ("" if study_id is None else str(int(study_id))), phase,
                author, _s(year), study_type, country, setting, scenario,
                sim_fidelity, scen_complexity,
                _s(total_n), _s(arm_n), unit_random, team_compo,
                team_inter, exp_level,
                nma_node, node_rationale, str(arm_no), arm_label, aid_name,
                medium, ca_type, ca_logic,
                pretrain_intensity, pretrain_desc,
                train_duration, train_method, train_timing,
                reader_present, reader_mode,
                interaction, strictness,
                enforcement, fidelity_check, fidelity_rate,
                implementation_narrative,
                _s(adh_gate),
                _s(adh_mean), _s(adh_sd), _s(adh_n),
                _s(adh_orig), adh_raw, _s(adh_conv), _s(adh_kp), adh_comments,
                _s(time_gate),
                _s(time_mean), _s(time_sd), _s(time_n),
                _s(time_orig), time_raw, _s(time_conv), time_comments,
                _s(err_gate),
                _s(err_events), _s(err_n), _s(err_measure), err_orig, err_comments,
                _s(nts_gate),
                _s(nts_mean), _s(nts_sd), _s(nts_n), nts_instrument, nts_comments,
                _s(d1), _s(d2), _s(d3), _s(d4), _s(d5), _s(rob_overall), rob_comments,
                mersqi_total, mersqi_comments,
                pub_type, _s(author_contact), _s(adh_direction),
                coding_uncertainty_log,
            ]

            if len(row_data) != len(SHEET_HEADERS):
                st.error(f"⚠️ Internal column-count mismatch: row has {len(row_data)} fields, SHEET_HEADERS has {len(SHEET_HEADERS)}.")
            else:
                try:
                    worksheet.append_row(row_data)
                    st.success(f"✅ Saved: **{author} ({year}) — Arm {arm_no}: {arm_label}** by {reviewer}")
                    st.balloons()
                    st.warning("**⚠️ Before clicking Submit again:**\n- **NEXT ARM**: update Arm No., Label, Node, Outcomes. (RoB-2/MERSQI already recorded for this study — leave blank.)\n- **NEW study**: refresh browser (F5) to clear.")
                except Exception as e:
                    st.error(f"❌ Could not write to sheet: {e}")
