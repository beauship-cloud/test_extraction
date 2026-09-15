"""
Cognitive Aids NMA — Data Extraction Tool (v5.4)
Streamlit app matching extraction form.
Deploy: GitHub → Streamlit Community Cloud.

Requires:
  - st.secrets["gcp_service_account"] : service-account JSON
  - Google Sheet with header row matching SHEET_HEADERS below

v5.4 changes (from v5.3) — post-calibration fixes. NO new sheet columns; the
Google Sheet header row does NOT need to change (still 87 columns).

  A. GATE_OPTS expanded from 4 to 6 options. The old set could not record a paper
     that is simply SILENT about an outcome: "Not measured" is a claim that the
     study did not assess it, which silence does not support. Added:
       * "Partially reported"        — some statistics present, others absent
       * "Not reported (paper silent)" — DEFAULT for silence
       * "Explicitly not measured"   — replaces the old bare "Not measured";
                                       use ONLY when the paper states it
     Stored as a string in the existing gate columns → column count unchanged.

  B. ADHERENCE SD no longer blocks submission when the paper does not report it.
     v5.3 required Mean + SD + N whenever the gate == "Reported". A paper with a
     mean and no SD (e.g. McEvoy) therefore could not be submitted honestly, and
     the only way past validation was to type SD = 0 — which is what happened in
     the calibration data. Now: a blank SD is allowed IF "Adherence comments"
     explains it. An unexplained blank still blocks.
     Adherence sub-field validation now fires on "Partially reported" as well.

  C. Misplaced st.caption fixed. The "never enter 0" caption was inside the
     `if submitted:` validation block, so it rendered below the Submit button
     AFTER submission instead of beside the SD input. Moved to Tab 4.

  D. Restored validation for "Adherence conversion method" and "Adherence
     Kirkpatrick level", which were dropped when C was introduced.

  E. Arm Label and Node rationale are now enforced. Both are marked ★ but were
     never checked: CRITICAL_FIELDS tests `val is None`, and an empty text_input
     returns "" rather than None, so both could be submitted blank.

  F. Duplicate dropdown options removed (reviewers were splitting arbitrarily
     between synonyms, which looks like disagreement at merge time):
       * "CA logic structure": "Linear (sequential, no branching)" and
         "Stepwise (sequential, one path)" merged into one option.
       * "Reader use mode": "Suggested / encouraged" removed (duplicate of
         "Encouraged (not mandated)").
     NOTE: rows already stored under the removed strings keep them; harmonise at
     the reconciliation stage.

  G. Time / Error / Sim-patient gated validation now fires on "Partially
     reported" as well as "Reported", for consistency with the adherence block.

  H. Median→Mean/SD converter, Hozo n<=15 branch: the original Hozo (2005)
     small-sample SD estimator includes a median-position term,
         SD ≈ sqrt( ( (a - 2m + b)^2 / 4 + (b - a)^2 ) / 12 )
     which reduces to range/(2*sqrt(3)) ONLY when the median sits exactly at the
     centre of the range. v5.3 applied the reduced form to every small sample.
     Fixed to the full expression. The 15<n<=70 and n>70 branches are unchanged.
     The converter remains a convenience display only — it writes nothing to the
     sheet, and project policy is that conversions are done centrally, once, on
     the consensus data.

v5.3 changes (from v5.2) — protocol↔form reconciliation before extraction start:
  - SIMULATED PATIENT OUTCOME (new Outcome 5). The protocol lists simulated
    patient-related outcomes as a secondary outcome, "descriptive only, not pooled".
    v5.2 had NO field for it, so such outcomes would have been silently dropped and
    the affected papers re-opened later. Added:
      * "Sim patient outcome reported?" — gate (GATE_OPTS), REQUIRED every arm,
        same true-absence-vs-blank logic as the other four gates.
      * "Sim patient outcome description" — free-text narrative, REQUIRED when the
        gate == "Reported". Deliberately NO numeric mean/SD/N block — the protocol
        says this outcome is described, never pooled, so a numeric block would invite
        accidental meta-analysis. SHEET_HEADERS +2.
  - ADHERENCE (PRIMARY) instrument + tier + scale-max. The protocol's primary is a
    hierarchy — steps proportion → checklist total → validated performance score,
    one measure per study — but v5.2 recorded none of WHICH measure/instrument was
    taken. A secondary outcome (NTS) had an instrument field while the primary did
    not. Added, immediately after the Adherence gate:
      * "Adherence measure tier" — which hierarchy level this value is (tier 1/2/3
        / other). REQUIRED when Adherence gate == "Reported". Gives the one-measure-
        per-study audit trail.
      * "Adherence instrument" — free text (e.g., study checklist, OSCAR, TAPAS).
        REQUIRED only for tier 3 (validated scores are named); optional otherwise.
      * "Adherence scale max" — denominator/max of the scale. REQUIRED for tier 2 &
        tier 3 (needed to interpret a raw score across instruments); optional for a
        proportion (implicit 0–100). SHEET_HEADERS +3.
  - UNIT split. The protocol extracts "unit of ANALYSIS"; v5.2's single field was
    labelled "Unit of randomisation" (and the sheet header "Unit (individual/team)").
    For cluster/team designs these differ, and mislabelling them risks a unit-of-
    analysis error in the NMA. Split into TWO required fields:
      * "Unit of randomisation"  (replaces the old ambiguous "Unit (individual/team)")
      * "Unit of analysis"       (new)
    SHEET_HEADERS +1.
  - FIDELITY scale: NO code change. The form keeps its 3-tier (Low/Mid/High/Unclear)
    scale on purpose — it is collapsible to the protocol's 2-tier later without
    re-extraction, whereas 2-tier → 3-tier would force re-reading. Action is on the
    PROTOCOL text (amend its 2-tier wording to 3-tier); do NOT "fix" this form back
    to 2 tiers.
  - Net column count: 81 -> 87. Update the Google Sheet header row BEFORE extraction
    (see the ⚠️ block below for exact insert positions).

v5.2 changes (from v5.1):
  - MERGE KEYS for 4-reviewer dual independent extraction:
      * "Study ID (Covidence)" — the Covidence record number (e.g. 9405), REQUIRED.
      * "Phase" — Calibration / Main, REQUIRED.
    Both inserted right after "Reviewer" (sheet columns 3 and 4). SHEET_HEADERS 79 -> 81.
    Reconciliation / IRR merge key = Study ID + Phase + Reviewer + Arm No.
  - Reviewer field can be locked to a fixed pick-list via REVIEWERS.

v5.1 changes (from v5.0):
  - FIDELITY-RATE GATE: "CA use fidelity rate (%)" is gated by the existing
    "CA use fidelity check" field, NOT by a new gate column. Validation-time only.
  - Robustness: "Adherence outcome direction" written via _s().

v5.0 changes (from prior build):
  - RoB-2 and MERSQI optional (study-level, normally assessed on Arm 1).
  - Error effect-measure field records HOW THE PAPER reported it.
  - Median-converter input labels clarified per method (IQR vs range).
  - Total N / Arm N default to blank (None) instead of 0.
  - OUTCOME GATES introduced for the 4 outcomes.
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

st.set_page_config(page_title="Cognitive Aids NMA Extraction v5.4", layout="wide")

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
# ⚠️ v5.0: FOUR gate columns inserted.       Total columns: 75 -> 79.
# ⚠️ v5.1: NO new columns.                   Total columns: 79.
# ⚠️ v5.2: TWO merge-key columns after "Reviewer".  Total: 79 -> 81.
# ⚠️ v5.3: SIX new columns.                  Total: 81 -> 87.
# ⚠️ v5.4: NO new columns — validation, option lists and captions only.
#          The Google Sheet header row is UNCHANGED at 87 columns.
# =============================================================================
SHEET_HEADERS = [
    "Timestamp", "Reviewer",
    # Merge keys (v5.2) — Covidence record # + extraction phase
    "Study ID (Covidence)", "Phase",
    # Study info
    "Lead Author", "Year", "Study Type", "Country", "Setting", "Scenario",
    "Simulation Fidelity", "Scenario Complexity",
    # Population
    "Total N (all arms)", "N (this arm)",
    "Unit of randomisation", "Unit of analysis",   # v5.3: split (was "Unit (individual/team)")
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
    "Adherence measure tier", "Adherence instrument", "Adherence scale max",  # v5.3
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
    # Outcome 5: Simulated patient outcome (v5.3 — DESCRIPTIVE ONLY, never pooled)
    "Sim patient outcome reported?", "Sim patient outcome description",
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

# Shared option list for the five outcome gates (v5.4: 4 -> 6 options)
GATE_OPTS = ["Reported",
             "Partially reported",
             "Not reported (paper silent)",
             "Explicitly not measured",
             "Measured – not extractable",
             "Unclear"]

# Gate values that trigger the numeric sub-field checks
GATE_ACTIVE = ("Reported", "Partially reported")

# Fixed reviewer pick-list — prevents name-spelling drift that would break the merge.
REVIEWERS = [
    "Angélique",
    "Rohit Bompalli",
    "YeonJung",
    "Shayan",
]

# =============================================================================
# UI
# =============================================================================
st.title("🌐 Cognitive Aids NMA — Data Extraction (v5.4)")
st.info(
    """
**📌 INSTRUCTIONS**
1. **Reviewer / Study ID / Phase** (Tab 1) — all required. **Study ID = the Covidence record number** for this paper (e.g. 9405); type it exactly as Covidence shows it. **Phase** = *Calibration* (the shared alignment papers) or *Main* (the full extraction).
2. Extract data for **ONE arm per submission**.
3. **Multi-arm study**: after submitting arm 1, update Arm No., Arm Label, NMA Node, Node rationale, **N (this arm)** and all Outcomes → Submit again. Everything else stays on screen — **re-check the arm-specific implementation fields (reader, training, enforcement) rather than assuming they carry over.**
4. **New study**: refresh browser (F5 / Cmd+R) to clear all fields.
5. ★ = NMA-critical field. As of v5.4 every ★ field is enforced at submission, including **Arm Label** and **Node rationale**.
6. **Do not use the Median → Mean/SD converter to fill the sheet.** Enter the raw statistics (median; Q1–Q3 or min–max; n) in the *Raw median stats* box. Conversions are done once, centrally, on the consensus data. The converter in Tab 4 is a sanity-check display only.
7. **RoB-2 & MERSQI are study-level** in this form — assess once per study (normally on Arm 1) and leave blank on later arms. **Record which outcome and analysis you assessed RoB-2 against on the first line of RoB-2 comments**, and give a rationale for every domain *including the ones you rate Low*.
8. **Outcome gates** (Tab 4) — for EACH of the **five** outcomes pick one of six:
   * **Reported** — usable numbers present
   * **Partially reported** — some statistics present, others absent (e.g. mean but no SD)
   * **Not reported (paper silent)** — the paper says nothing. **This is the default for silence**
   * **Explicitly not measured** — the paper states it did not measure this. Paste the sentence in the uncertainty log
   * **Measured – not extractable** — assessed, but no usable numbers (→ author-contact candidate)
   * **Unclear** — cannot tell. Give the reason in the log
9. **Never type 0 for an SD the paper does not report.** Leave SD blank and say so in *Adherence comments*; the form will accept it.
10. **Fidelity rate** (Tab 3): fill *CA use fidelity rate (%)* ONLY when *CA use fidelity check* = "Yes — quantitative" (then it is required). A quantitative check is not always a percentage — if it is a count or a duration, type the number with its unit and explain in the implementation narrative.
11. **Unit** (Tab 1): *Unit of randomisation* = what was allocated to arms; *Unit of analysis* = what the effect size is computed on. Fill both. **Team allocation alone does not make a study a cluster RCT** — that matters only when the outcome is analysed at a level below the allocated unit.
12. **Adherence tier** (Tab 4): pick which hierarchy level the primary value is. Instrument is required for validated (Tier 3) scores; scale-max is required for Tier 2/3. *Note: the Tier 1 > 2 > 3 preference is not stated in the current protocol — record in comments why you chose this measure.*
13. **Simulated patient outcome** (Tab 4, Outcome 5): narrative only, never pooled — but still record the reported numbers and their denominator in the description so they are not lost.
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
                     "It stays the same across all arms of the study. If a trial has "
                     "TWO Covidence records (e.g. Roitsch 9464 / 11651), enter the one "
                     "you are extracting from and note the other in the uncertainty log.")
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
            author = st.text_input("Lead Author (last name) ★", key="author")
            year = st.number_input(
                "Publication Year ★",
                min_value=1990, max_value=2030,
                value=None, step=1,
                placeholder="— enter year —",
                key="year",
            )
            # Study types: RCT designs only (observational/pilot removed)
            study_type = st.selectbox(
                "Study Type ★",
                ["Parallel RCT", "Crossover RCT", "Cluster RCT", "Other"],
                help="Code what was ACTUALLY done, not the paper's self-description. "
                     "Team allocation by itself is NOT a cluster design: choose "
                     "Cluster RCT only when groups were allocated and the outcome is "
                     "analysed at a LOWER level than the allocated unit (e.g. wards "
                     "allocated, individuals analysed). If allocation and analysis are "
                     "both at team level, this is a parallel trial with the team as the "
                     "unit of observation.",
                key="study_type",
                index=None,
                placeholder="— select —",
            )
        with c2:
            country = st.text_input("Country", key="country")
            setting = st.selectbox(
                "Simulated scenario setting ★",
                ["OR / Anaesthesia", "ICU", "ED", "Neonatal / Paediatric",
                 "Pre-hospital / EMS", "In-flight / aeromedical", "Ward", "Other"],
                key="setting",
                index=None,
                placeholder="— select —",
            )
            scenario = st.text_input("Scenario (e.g., MH, cardiac arrest)", key="scenario")
        with c3:
            total_n = st.number_input("Total N (all arms)", min_value=0, value=None,
                                      step=1, placeholder="— enter N —", key="total_n",
                                      help="In the unit the authors computed the effect "
                                           "size on. Record the other totals "
                                           "(randomised vs analysed, people vs teams) in "
                                           "the Coding uncertainty log.")
            arm_n = st.number_input("★ N (this arm)", min_value=0, value=None,
                                    step=1, placeholder="— enter N —", key="arm_n",
                                    help="Same unit as Total N. If an individual outcome "
                                         "is analysed on a different number, record that "
                                         "in that outcome's own 'N analyzed' box.")

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
                    "• **Mid**: full manikin (e.g., Resusci Anne, Resusci Junior, ALS Skillmaster, NeoNatalie) "
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
                "Publication type ★",
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
                help="Set to 'Pending decision' as soon as you hit a missing statistic "
                     "you cannot recover from the paper or its supplements.",
                key="author_contact",
                index=None,
                placeholder="— select —",
            )

        st.markdown("---")
        st.subheader("Population & Team")
        p1, p2, p3 = st.columns(3)
        with p1:
            unit_random = st.selectbox(
                "Unit of randomisation ★",
                ["Individual (single-provider)", "Team (multi-provider)", "Cluster", "Unclear"],
                help="What was RANDOMLY ALLOCATED to arms (the design's unit). For a "
                     "cluster RCT this is the cluster (ward/centre/session); it can "
                     "differ from the unit the OUTCOME is analysed at — record that "
                     "separately in 'Unit of analysis'.",
                key="unit_random",
                index=None,
                placeholder="— select —",
            )
            unit_analysis = st.selectbox(
                "★ Unit of analysis",
                ["Individual (single-provider)", "Team (multi-provider)", "Cluster", "Unclear"],
                help="The unit the effect size / N is computed on (one data point = ?). "
                     "Often equals the randomisation unit, but NOT always: e.g. cluster- "
                     "randomised yet analysed per individual. A MISMATCH is the thing "
                     "that flags a unit-of-analysis issue for the NMA — note it in the "
                     "uncertainty log. A match (team allocated, team analysed) does not.",
                key="unit_analysis",
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
            team_compo = st.text_input("Team composition (free text)", key="team_compo",
                help="The professions of the ACTUAL STUDY PARTICIPANTS. Record "
                     "standardised actors / confederates separately — they are not "
                     "participants and do not make a sample interprofessional.")
            team_inter = st.selectbox(
                "Team interprofessionality ★",
                ["Single-discipline", "Interdisciplinary (multi-specialty, same profession)",
                 "Interprofessional (multi-profession)", "Mixed across arms", "Individual (N/A)", "Unclear"],
                help="Code from the actual participants, not from confederates/actors.",
                key="team_inter",
                index=None,
                placeholder="— select —",
            )

        st.markdown("---")
        st.subheader("Coding uncertainty log")
        coding_uncertainty_log = st.text_area(
            "If any field was coded as 'Unclear' / 'Not reported', note WHY here:",
            height=120,
            key="coding_uncertainty_log",
            placeholder=(
                "One line per item, in this format so it can be parsed later:\n"
                "FIELD: what the paper says | what I entered | why\n\n"
                "e.g.\n"
                "Total N: randomised 35 teams/105 people, analysed 32 teams/96 people | 32 | "
                "authors computed effect size on teams\n"
                "Node: paper calls it 'control' but the arm received a paper guideline | Static | "
                "node follows what the arm received\n"
                "Adherence SD: not reported; CI is on an arcsine scale | left blank | "
                "no back-calculation; author contact pending"
            ),
        )

    # -------------------------------------------------------------------------
    # TAB 2 — CA & NMA NODE
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("NMA Node — classify by FUNCTION, not medium")
        n1, n2 = st.columns([1, 2])
        with n1:
            nma_node = st.selectbox("★ NMA Node", ["Control", "Static", "Dynamic"],
                help="The test is whether the tool RESPONDS to what the user does.\n\n"
                     "• **Control**: no eligible cognitive aid provided.\n"
                     "• **Static**: fixed content the user reads or navigates — paper, "
                     "PDF or screen. An electronic checklist with no branching is Static. "
                     "A branching flowchart PRINTED ON PAPER is Static.\n"
                     "• **Dynamic**: the guidance presented changes with user input or "
                     "task progress.\n\n"
                     "Two things that do NOT decide the node: what the paper calls the "
                     "arm, and who physically operates the aid.\n\n"
                     "If you genuinely cannot tell, pick the closest node, start the "
                     "rationale with 'NODE UNCERTAIN' and explain in the uncertainty log.",
                key="nma_node", index=None, placeholder="— select —")
            arm_no = st.number_input("★ Arm No.", 1, 10, 1, key="arm_no",
                help="Project convention: Control = 1, Static = 2, Dynamic = 3, so the "
                     "R analysis sees a consistent order. If a study has TWO arms of the "
                     "same node, distinguish them in Arm Label and flag it in the log.")
        with n2:
            node_rationale = st.text_area("★ Node rationale (1 line + source)", height=68,
                key="node_rationale",
                placeholder="e.g. Tool asks patient type, then pulse y/n; next screen "
                            "depends on answer — Supplement Fig S2")
        st.caption("**Node rationale is required.** Give the reason AND where you read it "
                   "(page / table / figure). 'dynamic aid' just repeats the verdict and "
                   "the second reviewer cannot check it.")

        st.markdown("---")
        st.subheader("Cognitive Aid Description")
        a1, a2 = st.columns(2)
        with a1:
            arm_label = st.text_input("★ Arm Label", key="arm_label",
                help="The paper's own name for this group, verbatim — e.g. "
                     "\"control group\", \"PediAppRREST group\", \"Reader + DST\". "
                     "This is what keeps a Static-coded 'control group' traceable.")
            aid_name = st.text_input("Name of Cognitive Aid", key="aid_name")
        with a2:
            medium = st.selectbox("Format — medium ★",
                ["Paper", "Digital — PDF/static screen", "Digital — app/tablet",
                 "Digital — AR/VR", "Hybrid (paper + digital)", "N/A (Control arm)", "Other"],
                key="medium", index=None, placeholder="— select —")
            ca_type = st.selectbox("Format — type ★",
                ["Checklist", "Chart / flow diagram", "App", "Tablet interface",
                 "AR overlay", "Mnemonic / memory aid", "N/A (Control)", "Other"],
                key="ca_type", index=None, placeholder="— select —")

        # v5.4 F: "Linear" and "Stepwise" merged — they described the same thing and
        # reviewers were splitting between them arbitrarily.
        ca_logic = st.selectbox("CA logic structure ★",
            ["Linear / stepwise (sequential, no branching)",
             "Branching (decision-tree, adapts to user input)", "Mixed",
             "Unclear from main text", "N/A (Control)"],
            help="This describes the CONTENT. A printed algorithm can be 'Branching' "
                 "here and still be Static in the node above — if so, say why in the "
                 "node rationale.",
            key="ca_logic", index=None, placeholder="— select —")

    # -------------------------------------------------------------------------
    # TAB 3 — IMPLEMENTATION FACTORS
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Pre-training (before the simulation)")
        t1, t2 = st.columns(2)
        with t1:
            pretrain_intensity = st.selectbox("Pre-training intensity ★",
                ["None", "Minimal (<30 min)", "Structured (≥30 min)", "Unclear"],
                key="pretrain_intensity", index=None, placeholder="— select —")
            train_duration = st.text_input("Training duration", key="train_duration")
        with t2:
            train_method = st.selectbox("Training method ★",
                ["None", "Lecture", "Video", "Hands-on / orientation", "Combined", "Unclear"],
                key="train_method", index=None, placeholder="— select —")
            train_timing = st.selectbox("Training timing ★",
                ["None", "Immediately before scenario", "Same day", "Earlier in study", "Unclear"],
                key="train_timing", index=None, placeholder="— select —")
        pretrain_desc = st.text_area("Pre-training description", height=80, key="pretrain_desc",
            placeholder="Separate the two kinds of training explicitly, e.g.\n"
                        "common: 40 min simulator orientation (all arms)\n"
                        "aid-specific: 20 min CDSS training (this arm only)")
        st.caption("**Separate the common orientation from aid-specific training.** If you "
                   "merge them, an arm that got 20 extra minutes on the aid looks as if it "
                   "got more simulator practice — and that difference is a potential "
                   "confound, not a detail.")

        st.markdown("---")
        st.subheader("Reader & Interaction")
        r1, r2 = st.columns(2)
        with r1:
            reader_present = st.selectbox("Designated Reader present? ★",
                ["Yes — mandated role (protocol-defined)",
                 "Yes — team's discretion (role exists but team decides)",
                 "No", "Not reported"],
                help="Ask this of EVERY arm, including control. Do not assume a control "
                     "arm had no reader. Use 'Not reported' if the text is silent.",
                key="reader_present", index=None, placeholder="— select —")
            # v5.4 F: "Suggested / encouraged" removed as a duplicate of "Encouraged".
            reader_mode = st.selectbox("Reader use mode",
                ["Mandated (required by protocol)", "Encouraged (not mandated)",
                 "Discretionary", "Not used", "Unclear"],
                help="If participants could decline the reader's offer, that is "
                     "'Encouraged', not 'Mandated'.",
                key="reader_mode", index=None, placeholder="— select —")
        with r2:
            interaction = st.selectbox("Interaction style ★",
                ["Read-do", "Do-verify", "Challenge-response", "Self-read silent", "Combined", "N/A (Control)", "Unclear"],
                help="'Read-do' means reading the aid before acting. 'Do-verify' means acting from memory first, then checking the aid to catch missed steps.",
                key="interaction", index=None, placeholder="— select —")
            strictness = st.selectbox("Strictness of CA workflow ★",
                ["Strict (every step must be completed)", "Discretionary (steps can be skipped)",
                 "Mixed", "N/A (Control)", "Unclear"],
                key="strictness", index=None, placeholder="— select —")

        st.markdown("---")
        st.subheader("CA use enforcement & fidelity")
        e1, e2 = st.columns(2)
        with e1:
            enforcement = st.selectbox("CA use enforcement ★",
                ["Mandated (participants required to consult CA)",
                 "Encouraged (instructed but not enforced)",
                 "Available-only (CA placed in environment, no instruction)", "Unclear", "N/A (Control)"],
                key="enforcement", index=None, placeholder="— select —")
            fidelity_check = st.selectbox("CA use fidelity check (was actual use monitored?) ★",
                ["Yes — quantitative (e.g., observed/timed use)",
                 "Yes — ordinal scale (e.g., 0–5 rating)",
                 "Yes — qualitative only", "No (not reported)", "Unclear", "N/A (Control)"],
                help="'No (not reported)' covers both 'the authors checked and report "
                     "nothing' and 'the authors never checked'. Say which in the "
                     "implementation narrative.",
                key="fidelity_check", index=None, placeholder="— select —")
        with e2:
            fidelity_rate = st.text_input(
                "CA use fidelity rate (%)",
                help="Gated by 'CA use fidelity check'. Required ONLY when the check = "
                     "'Yes — quantitative'. For any other check value leave blank — the "
                     "blank is explained by the check field, not an unrecorded value. "
                     "A quantitative check is not always a percentage: if it is a count "
                     "or a duration, type the number WITH its unit "
                     "(e.g. '3.2 consultations/team') and explain in the narrative.",
                key="fidelity_rate",
            )
            st.caption("Required only if fidelity check = 'Yes — quantitative'; otherwise a "
                       "blank is a true 'no quantitative measure in source', not an unfilled field.")

        implementation_narrative = st.text_area("Implementation narrative", height=100,
            key="implementation_narrative",
            placeholder="Include: what the control arm was allowed to use; whether the "
                        "reader was an existing team member or extra personnel; anything "
                        "that differed between arms besides the aid itself.")

    # -------------------------------------------------------------------------
    # TAB 4 — OUTCOMES
    # -------------------------------------------------------------------------
    with tab4:
        with st.expander("💡 Median → Mean/SD Converter (sanity check only — do NOT paste results into the sheet)"):
            st.caption("Project policy: extractors record the RAW statistics; conversion "
                       "is done once, centrally, on the consensus data. Use this only to "
                       "see roughly what a value will become.")
            cvt_method = st.radio("Pick reported statistic:",
                ["Wan 2014 — median + Q1 + Q3 (IQR)",
                 "Hozo 2005 — median + min + max (range)",
                 "Luo 2018 mean + Hozo 2005 SD — median + min + max (range)"],
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
                    def _hozo_sd(a, m, b, n):
                        """Hozo 2005 range-based SD.

                        v5.4 fix: for n <= 15 the original estimator is
                            sqrt( ( (a - 2m + b)^2 / 4 + (b - a)^2 ) / 12 )
                        which collapses to range/(2*sqrt(3)) only when the median lies
                        exactly at the centre of the range. v5.3 applied the collapsed
                        form to every small sample, understating SD for skewed data.
                        """
                        if n <= 15:
                            sd = math.sqrt((((a - 2 * m + b) ** 2) / 4 + (b - a) ** 2) / 12)
                            return sd, "n≤15: Hozo eq. with median-position term"
                        elif n <= 70:
                            return (b - a) / 4, "15<n≤70: range/4"
                        else:
                            return (b - a) / 6, "n>70: range/6"

                    if cvt_method.startswith("Wan"):
                        # Wan 2014, median + IQR (Eq. 14 mean, Eq. 16 SD)
                        mean_est = (cv_a + cv_med + cv_b) / 3
                        xi = 2 * _norm_ppf((0.75 * cv_n - 0.125) / (cv_n + 0.25))
                        sd_est = (cv_b - cv_a) / xi
                        method_used = f"Wan 2014 IQR (η={xi:.3f})"
                    elif cvt_method.startswith("Hozo"):
                        # Hozo 2005, median + range
                        mean_est = (cv_a + 2 * cv_med + cv_b) / 4
                        sd_est, sd_rule = _hozo_sd(cv_a, cv_med, cv_b, cv_n)
                        method_used = f"Hozo 2005 ({sd_rule})"
                    else:
                        # Luo 2018 mean (range) + Hozo 2005 SD (range) — consistent range basis
                        w = 4 / (4 + cv_n ** 0.75)
                        mean_est = w * (cv_a + cv_b) / 2 + (1 - w) * cv_med
                        sd_est, sd_rule = _hozo_sd(cv_a, cv_med, cv_b, cv_n)
                        method_used = f"Luo 2018 mean + Hozo 2005 SD ({sd_rule})"
                    st.success(f"**Mean ≈ {mean_est:.3f} | SD ≈ {sd_est:.3f}** ({method_used})")
                    st.caption("Record the RAW statistics in the sheet, not this result.")
                except Exception as e:
                    st.error(f"Calc error: {e}")

        st.markdown("---")
        st.markdown("### Outcome 1 — Adherence / task completion (★ PRIMARY, continuous, SMD)")
        adh_gate = st.selectbox("★ Adherence reported?", GATE_OPTS,
            help="**Reported** = usable numbers present. "
                 "**Partially reported** = some statistics present, others absent "
                 "(e.g. a mean but no SD) — use this instead of typing 0. "
                 "**Not reported (paper silent)** = the paper says nothing; this is the "
                 "default for silence. "
                 "**Explicitly not measured** = the paper STATES it did not assess this. "
                 "**Measured – not extractable** = assessed but no usable numbers "
                 "(→ author-contact candidate). "
                 "**Unclear** = cannot tell from the text.",
            key="adh_gate", index=None, placeholder="— select —")
        st.caption("Record the RAW values as reported. Direction harmonisation (so higher = better) is done at the ANALYSIS stage, not here — you only record the value + which direction it represents.")
        adh_direction = st.radio("★ Outcome direction",
            ["Higher = better (e.g., % steps completed, checklist score)",
             "Lower = better (e.g., % steps missed, failure rate)",
             "N/A — outcome not extracted in this arm"],
            horizontal=True, key="adh_direction", index=None)

        # v5.3 — record WHICH measure in the protocol hierarchy this value is, plus its
        # instrument + scale, so a study contributing multiple adherence-type measures
        # has a documented one-measure-per-study choice and cross-instrument SMD context.
        at1, at2, at3 = st.columns(3)
        with at1:
            adh_tier = st.selectbox("★ Adherence measure tier",
                ["Tier 1 — steps completed/missed (proportion)",
                 "Tier 2 — checklist-based adherence score",
                 "Tier 3 — validated technical performance score",
                 "Other / composite"],
                help="Record the tier of the value you extracted. NOTE: the Tier 1 > 2 > 3 "
                     "preference is NOT stated in the current protocol — prefer the "
                     "measure the STUDY designated as primary, and record in comments why "
                     "you chose the one you did.",
                key="adh_tier", index=None, placeholder="— select —")
        with at2:
            adh_instrument = st.text_input("Adherence instrument",
                help="Name of the checklist / scale (e.g., study-specific checklist, "
                     "c-DEV15plus, TAPAS). Required for Tier 3 (validated scores are "
                     "named); optional for Tier 1/2. Note OSCAR is a NON-technical "
                     "skills instrument and belongs under NTS, not here.",
                key="adh_instrument")
        with at3:
            adh_scalemax = st.number_input("Adherence scale max",
                value=None, min_value=0.0, format="%.4f",
                help="Maximum possible value of the scale (denominator). Required for "
                     "Tier 2 & Tier 3 to interpret a raw score across instruments; leave "
                     "blank for a proportion (implicit 0–100).",
                key="adh_scalemax")

        o1c1, o1c2, o1c3 = st.columns(3)
        with o1c1: adh_mean = st.number_input("★ Mean", value=None, format="%.4f", key="adh_mean")
        with o1c2: adh_sd = st.number_input("★ SD", value=None, min_value=0.0, format="%.4f", key="adh_sd")
        with o1c3: adh_n = st.number_input("★ N analyzed (this arm)", value=None, min_value=0, step=1, key="adh_n")
        # v5.4 C: this caption used to sit inside the `if submitted:` block, so it only
        # appeared under the Submit button AFTER submission. It belongs here.
        st.caption("**SD not reported? Leave it blank, set the gate to 'Partially reported' "
                   "and say so in Adherence comments. NEVER type 0** — a zero SD makes the "
                   "study look infinitely precise and it will dominate the meta-analysis. "
                   "Do not back-calculate an SD from a CI on a transformed scale.")
        o1c4, o1c5 = st.columns(2)
        with o1c4:
            adh_orig = st.selectbox("Original reporting format",
                ["mean ± SD", "median + IQR", "median + range", "%/proportion", "Other", "Not extractable"],
                key="adh_orig", index=None, placeholder="— select —")
            adh_raw = st.text_input("Raw median stats (median; Q1–Q3 OR min–max; n)", key="adh_raw",
                help="Type every statistic the paper prints, verbatim — e.g. "
                     "'median 80; Q1 70; Q3 90; n 30'. Check Q1 ≤ median ≤ Q3; if the "
                     "source contradicts itself, enter it as printed and flag it in the log.")
        with o1c5:
            adh_conv = st.selectbox("Conversion method (if median→mean)",
                ["N/A — reported as mean", "Wan 2014 (median+IQR)", "Hozo 2005 (median+range)", "Luo 2018", "Other"],
                help="This records WHICH method will be applied centrally. It is not a "
                     "statement that you converted anything.",
                key="adh_conv", index=None, placeholder="— select —")
            adh_kp = st.selectbox("Kirkpatrick level",
                ["KP1 Reaction", "KP2 Learning", "KP3 Behaviour", "KP4 Results", "N/A"],
                help="Simulated patient states (e.g. simulated ROSC) are NOT KP4 — a "
                     "simulated patient is not a patient.",
                key="adh_kp", index=None, placeholder="— select —")
        adh_comments = st.text_input("Adherence comments", key="adh_comments",
            help="Required when SD is blank. Also use it for: the measure you chose and "
                 "why; values from a second analysis set (ITT vs per-protocol); the "
                 "source page and table.")

        st.markdown("---")
        st.markdown("### Outcome 2 — Time to critical action (SECONDARY, continuous)")
        time_gate = st.selectbox("★ Time reported?", GATE_OPTS,
            key="time_gate", index=None, placeholder="— select —")
        st.caption("This block holds ONE timing. If the paper reports several, enter the "
                   "selected one here and list the rest in Time comments in a fixed "
                   "format. Record the time origin and endpoint — and if the value is "
                   "defined only for participants who performed the action, put the "
                   "number who performed it in 'N analyzed' and flag the conditional "
                   "comparison in comments.")
        o2c1, o2c2, o2c3 = st.columns(3)
        with o2c1: time_mean = st.number_input("Mean (seconds)", value=None, format="%.4f", key="time_mean")
        with o2c2: time_sd = st.number_input("SD (seconds)", value=None, min_value=0.0, format="%.4f", key="time_sd")
        with o2c3: time_n = st.number_input("N analyzed", value=None, min_value=0, step=1, key="time_n",
            help="For a performers-only outcome this is the number who performed the "
                 "action, not the arm N. Never impute 0 or a time limit for "
                 "non-performers.")
        o2c4, o2c5 = st.columns(2)
        with o2c4:
            time_orig = st.selectbox("Original reporting format",
                ["mean ± SD", "median + IQR", "median + range", "Other", "Not reported"],
                key="time_orig", index=None, placeholder="— select —")
        with o2c5:
            time_raw = st.text_input("Raw median stats (if median)", key="time_raw",
                help="Watch the notation: '2.46' in minutes.seconds is 2 min 46 s = 166 s, "
                     "not 2.46 minutes. Enter the printed number and state the notation "
                     "in Time comments.")
            time_conv = st.selectbox("Conversion method",
                ["N/A", "Wan 2014", "Hozo 2005", "Luo 2018", "Other"],
                key="time_conv", index=None, placeholder="— select —")
        time_comments = st.text_input("Time comments", key="time_comments",
            help="SELECTED: <action> | origin | endpoint | source. "
                 "Then ALSO REPORTED: the other timings, one per line. "
                 "Flag performers-only comparisons here.")

        st.markdown("---")
        st.markdown("### Outcome 3 — Error rate (SECONDARY, dichotomous)")
        err_gate = st.selectbox("★ Error reported?", GATE_OPTS,
            key="err_gate", index=None, placeholder="— select —")
        st.caption("Extract raw EVENTS + N. The pooled effect measure for the NMA is RR, "
                   "computed from events/N at the analysis stage. **Events are counts, not "
                   "percentages** — if the paper prints 12.5% of 16, the count is 2. A "
                   "summed deviation score belongs in Outcome 1, not here.")
        e3c1, e3c2, e3c3 = st.columns(3)
        with e3c1: err_events = st.number_input("★ Events (this arm)", value=None, min_value=0, step=1, key="err_events",
            help="An integer count of events. If the paper gives only a percentage, "
                 "convert only when the denominator makes the integer unique, and record "
                 "both in Error comments.")
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
            help="NTS = NON-TECHNICAL skills: teamwork, leadership, situation awareness, "
                 "communication. A clinical performance score is technical performance "
                 "and belongs in Outcome 1. NASA-TLX is workload and SUS is usability — "
                 "neither is NTS.",
            key="nts_gate", index=None, placeholder="— select —")
        nts1, nts2, nts3 = st.columns(3)
        with nts1: nts_mean = st.number_input("Mean", value=None, format="%.4f", key="nts_mean")
        with nts2: nts_sd = st.number_input("SD", value=None, min_value=0.0, format="%.4f", key="nts_sd")
        with nts3: nts_n = st.number_input("N analyzed", value=None, min_value=0, step=1, key="nts_n")
        nts_instrument = st.text_input("Instrument", key="nts_instrument")
        nts_comments = st.text_input("NTS comments", key="nts_comments",
            help="Record the subscale, scale range and direction here — the instrument "
                 "name alone is not enough to interpret the score.")

        st.markdown("---")
        st.markdown("### Outcome 5 — Simulated patient outcome (SECONDARY, DESCRIPTIVE ONLY — never pooled)")
        simpt_gate = st.selectbox("★ Simulated patient outcome reported?", GATE_OPTS,
            help="Pick 'Reported' if the study reports a simulated-patient-level outcome "
                 "(e.g., simulated survival / ROSC as a patient state, simulated "
                 "complication or harm) — even if the authors do not list it as a formal "
                 "outcome, as long as the numbers are there. Use 'Not reported (paper "
                 "silent)' when the paper says nothing.",
            key="simpt_gate", index=None, placeholder="— select —")
        st.caption("By protocol this outcome is DESCRIPTIVE ONLY and is NOT pooled — so "
                   "there is deliberately no mean/SD/N block. **Still record the reported "
                   "numbers and their denominator in the text below** so they are not "
                   "lost; just mark them as not pooled. Also note if the outcome was "
                   "determined by the scenario script rather than measured independently.")
        simpt_desc = st.text_area(
            "Simulated patient outcome description (required if 'Reported' / 'Partially reported')",
            height=80, key="simpt_desc",
            placeholder="e.g. ROSC achieved: 25/32 (app), 10/35 (paper), 6/33 (none). "
                        "Supplement eTable 3. Descriptive only — not pooled. Authors note "
                        "ROSC followed from correct task completion in the scripted scenario.")

    # -------------------------------------------------------------------------
    # TAB 5 — RoB & QUALITY  (study-level — assess once per study, normally Arm 1)
    # -------------------------------------------------------------------------
    with tab5:
        st.info("ℹ️ **RoB-2 and MERSQI are entered ONCE per study** (normally on Arm 1). "
                "On later arms of the same study leave these blank — they are optional "
                "and will not block submission.")
        st.subheader("RoB-2 (for RCTs)")
        st.caption("RoB-2 assesses a specific RESULT, not a study. Until this form is "
                   "restructured, assess against the **primary adherence outcome** and "
                   "write on the first line of the comments box which outcome and which "
                   "analysis set you assessed — e.g. 'Assessed for: overall adherence, "
                   "ITT analysis'. Give a rationale for EVERY domain, **including the ones "
                   "you rate Low**. Crossover and cluster designs need a different RoB-2 "
                   "version; say which you used.")
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
        rob_comments = st.text_area("RoB-2 comments", height=90, key="rob_comments",
            placeholder="Assessed for: <outcome>, <analysis set>\n"
                        "D1: ... | D2: ... | D3: ... | D4: ... | D5: ...\n"
                        "Version used: RoB 2 (parallel / crossover / cluster)")

        st.markdown("---")
        st.subheader("MERSQI (medical education research quality)")
        st.caption("Two options below do not match the original instrument. **Sampling**: "
                   "the original scores institutions (0.5/1.0/1.5) and response rate "
                   "(0.5/1.0/1.5) SEPARATELY and sums them — a single-institution study "
                   "with ≥75% response should total 2.0, but the nearest option here gives "
                   "1.5. **Data analysis**: the original scores appropriateness and "
                   "sophistication separately, not 'complex model = 3'. Pick the closest "
                   "option, then write the correct breakdown in the comments box. The "
                   "sheet stores only the total, so **write all six domain scores and your "
                   "reasoning in the comments** or the second reviewer cannot see where "
                   "you differ.")
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
                help="Score the instrument used for the PRIMARY ADHERENCE outcome only — "
                     "not NASA-TLX, not SUS.\n\n"
                     "• **Content**: items built from existing guidelines or established "
                     "evidence.\n"
                     "• **Internal structure**: internal reliability or inter-rater "
                     "agreement reported.\n"
                     "• **Relationships to other variables**: the INSTRUMENT'S SCORES "
                     "analysed against external variables. Scored on whether it is "
                     "REPORTED, not on whether it was significant — a non-significant "
                     "correlation still earns the point. A baseline-characteristics "
                     "comparison between arms does NOT count.\n\n"
                     "Record which of the three you awarded, and why, in the comments.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_validity", index=None, placeholder="— select —")
            mersqi_analysis = st.selectbox("5. Data analysis (appropriateness + sophistication)",
                [(1.0, "Appropriate, descriptive only"), (2.0, "Appropriate, beyond descriptive (inferential)"),
                 (3.0, "Appropriate + sophisticated (e.g., multivariable / mixed)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_analysis", index=None, placeholder="— select —")
            mersqi_outcomes = st.selectbox("6. Outcomes (highest level only)",
                [(1.0, "Satisfaction / attitudes / opinions"), (1.5, "Knowledge / skills"),
                 (2.0, "Behaviours (in practice)"), (3.0, "Patient / healthcare outcomes")],
                help="A SIMULATED patient outcome is not a patient outcome. Do not score "
                     "3.0 for simulated ROSC.",
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

        mersqi_comments = st.text_area("MERSQI comments", height=90, key="mersqi_comments",
            placeholder="1: 3.0 RCT | 2: 0.5 (1 inst) + 1.5 (resp ≥75%) = 2.0 — form option "
                        "gives 1.5 | 3: 3.0 objective | 4: content 1 + structure 1 + "
                        "relationships 0 = 2.0, reasoning: ... | 5: 1 + 2 = 3.0 | "
                        "6: 1.5 knowledge/skills")

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
        # v5.4 E: both are marked ★ but were never enforced. CRITICAL_FIELDS tests
        # `val is None`, and an empty text widget returns "" rather than None.
        if not arm_label.strip(): missing_text.append("Arm Label (Tab 2)")
        if not node_rationale.strip(): missing_text.append("Node rationale (Tab 2)")

        # Required per-ARM fields (study/intervention/implementation/outcome-gates).
        # RoB-2 and MERSQI are STUDY-LEVEL and intentionally NOT included here.
        CRITICAL_FIELDS = [
            ("Study type",                 study_type,         "Tab 1"),
            ("Setting",                    setting,            "Tab 1"),
            ("Simulation fidelity",        sim_fidelity,       "Tab 1"),
            ("Scenario complexity",        scen_complexity,    "Tab 1"),
            ("Publication type",           pub_type,           "Tab 1"),
            ("Unit of randomisation",      unit_random,        "Tab 1"),
            ("Unit of analysis",           unit_analysis,      "Tab 1"),
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
            # Outcome gates — all five required every arm
            ("Adherence reported?",        adh_gate,           "Tab 4"),
            ("Time reported?",             time_gate,          "Tab 4"),
            ("Error reported?",            err_gate,           "Tab 4"),
            ("NTS reported?",              nts_gate,           "Tab 4"),
            ("Sim patient outcome reported?", simpt_gate,      "Tab 4"),
        ]
        # NOTE: "Adherence outcome direction" is not always-required; it is conditional
        # on the Adherence gate being Reported / Partially reported (see below).

        missing_select = [f"• **{name}** ({tab})" for name, val, tab in CRITICAL_FIELDS if val is None]

        conditional_missing = []

        # --- Adherence -------------------------------------------------------
        # v5.4 B: fires on "Partially reported" too, and a blank SD is allowed when
        # Adherence comments explains it. An UNEXPLAINED blank still blocks, so a
        # forgotten SD is caught while a genuinely unreported SD can be recorded
        # honestly instead of being typed as 0.
        if adh_gate in GATE_ACTIVE:
            if adh_direction is None: conditional_missing.append("• **Adherence outcome direction** (Tab 4)")
            if adh_tier is None:      conditional_missing.append("• **Adherence measure tier** (Tab 4)")
            if adh_mean is None:      conditional_missing.append("• **Adherence Mean** (Tab 4)")
            if adh_n is None:         conditional_missing.append("• **Adherence N analyzed** (Tab 4)")
            if adh_sd is None and not adh_comments.strip():
                conditional_missing.append(
                    "• **Adherence SD** is blank — enter it, or explain in "
                    "**Adherence comments** why the paper does not report it. "
                    "Do NOT type 0. (Tab 4)")
            if adh_orig is None:      conditional_missing.append("• **Adherence original format** (Tab 4)")
            # v5.4 D: these two were dropped in an earlier edit — restored.
            if adh_conv is None:      conditional_missing.append("• **Adherence conversion method** (Tab 4)")
            if adh_kp is None:        conditional_missing.append("• **Adherence Kirkpatrick level** (Tab 4)")
            # Tier-conditional: validated scores are named (instrument required); scored
            # scales (Tier 2/3) need a max to interpret; a proportion (Tier 1) does not.
            _is_tier2 = adh_tier == "Tier 2 — checklist-based adherence score"
            _is_tier3 = adh_tier == "Tier 3 — validated technical performance score"
            if _is_tier3 and not adh_instrument.strip():
                conditional_missing.append("• **Adherence instrument** — required for Tier 3 (Tab 4)")
            if (_is_tier2 or _is_tier3) and adh_scalemax is None:
                conditional_missing.append("• **Adherence scale max** — required for Tier 2/3 (Tab 4)")

        # --- Simulated patient outcome ---------------------------------------
        if simpt_gate in GATE_ACTIVE and not simpt_desc.strip():
            conditional_missing.append("• **Simulated patient outcome description** (Tab 4)")

        # --- Time -------------------------------------------------------------
        if time_gate in GATE_ACTIVE:
            if time_orig is None: conditional_missing.append("• **Time original format** (Tab 4)")
            if time_conv is None: conditional_missing.append("• **Time conversion method** (Tab 4)")

        # --- Error ------------------------------------------------------------
        if err_gate in GATE_ACTIVE:
            if err_measure is None: conditional_missing.append("• **Error measure as reported** (Tab 4)")
            # Sanity check: events cannot exceed the denominator. Catches a percentage
            # typed into the Events box (e.g. 12.5% of 16 entered as "12").
            if err_events is not None and err_n is not None and err_events > err_n:
                conditional_missing.append(
                    f"• **Error events ({int(err_events)}) exceed N analyzed ({int(err_n)})** — "
                    "did you enter a percentage instead of a count? (Tab 4)")

        # --- NTS: gate required, no sub-fields forced -------------------------

        # --- Fidelity-rate gate (v5.1) ---------------------------------------
        if (fidelity_check == "Yes — quantitative (e.g., observed/timed use)"
                and not fidelity_rate.strip()):
            conditional_missing.append(
                "• **CA use fidelity rate (%)** — required because fidelity check = "
                "'Yes — quantitative' (Tab 3)")

        # --- MERSQI partial-entry guard --------------------------------------
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
                _s(total_n), _s(arm_n), unit_random, unit_analysis, team_compo,
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
                _s(adh_tier), adh_instrument, _s(adh_scalemax),
                _s(adh_mean), _s(adh_sd), _s(adh_n),
                _s(adh_orig), adh_raw, _s(adh_conv), _s(adh_kp), adh_comments,
                _s(time_gate),
                _s(time_mean), _s(time_sd), _s(time_n),
                _s(time_orig), time_raw, _s(time_conv), time_comments,
                _s(err_gate),
                _s(err_events), _s(err_n), _s(err_measure), err_orig, err_comments,
                _s(nts_gate),
                _s(nts_mean), _s(nts_sd), _s(nts_n), nts_instrument, nts_comments,
                _s(simpt_gate), simpt_desc,
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
                    st.warning(
                        "**⚠️ Before clicking Submit again:**\n"
                        "- **NEXT ARM**: update Arm No., Arm Label, Node, Node rationale, "
                        "**N (this arm)** and all Outcomes. Also re-check the arm-specific "
                        "implementation fields (reader, training, enforcement) — they are "
                        "still showing the previous arm's values. "
                        "(RoB-2/MERSQI already recorded for this study — leave blank.)\n"
                        "- **NEW study**: refresh browser (F5) to clear.")
                except Exception as e:
                    st.error(f"❌ Could not write to sheet: {e}")
