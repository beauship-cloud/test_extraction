"""Cognitive Aids NMA extraction v6.0.
Built from the user's v5.4. Existing 87 headers are unchanged.
Run: streamlit run app.py. No Google write occurs until a setup/save button is clicked.
"""
import hashlib
import json
import math
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

VERSION = "6.0"
TZ = ZoneInfo("America/Toronto")
SHEET_URL = "https://docs.google.com/spreadsheets/d/12HHfPH04LEsg9UTuMlm-w20X6UniAQDEFA2C2WmrKEA/edit"
OUTCOMES_TAB = "Outcomes"
GATE_OPTS = ["Reported", "Partially reported", "Not reported (paper silent)",
             "Explicitly not measured", "Measured – not extractable", "Unclear"]
GATE_ACTIVE = ("Reported", "Partially reported")
REVIEWERS = ["Angélique", "Rohit Bompalli", "YeonJung", "Shayan"]
DOMAINS = {"Adherence": "adh_gate", "Time": "time_gate", "Error": "err_gate", "NTS": "nts_gate"}
FORMATS = {
    "mean ± SD": ["Mean", "SD"],
    "mean (SE)": ["Mean", "SE"],
    "mean (CI)": ["Mean", "CI lower", "CI upper"],
    "mean + range": ["Mean", "Min", "Max"],
    "mean only": ["Mean"],
    "median + IQR (Q1, Q3)": ["Median", "Q1", "Q3"],
    "median + IQR width": ["Median", "IQR width"],
    "median + range": ["Median", "Min", "Max"],
    "median only": ["Median"],
    "events / N": ["Events", "N analyzed"],
    "percentage / proportion": ["Estimate"],
    "effect estimate (CI)": ["Estimate", "CI lower", "CI upper"],
    "Other / figure / narrative": [],
}
NUMERIC_FIELDS = ["Mean", "SD", "SE", "Median", "Q1", "Q3", "IQR width", "Min", "Max",
                  "Events", "Estimate", "CI lower", "CI upper", "CI level (%)"]
OUTCOME_FIELDS = ["Domain", "Outcome name", "Scenario", "Scenario scope", "Event / phase",
    "Result status", "Analysis population", "Estimate basis", "Instrument", "Adherence measure tier",
    "Scale max", "Outcome direction", "Kirkpatrick level", "Original reporting format",
    *NUMERIC_FIELDS, "Estimate type / comparison", "N analyzed", "N unit", "Measurement unit",
    "Time type", "Time origin", "Time endpoint", "Raw reported statistics", "Source", "Comments"]
OUTCOME_HEADERS = ["Timestamp", "Reviewer", "Study ID (Covidence)", "Phase", "Arm No.",
                   "Submission ID", "Outcome ID", "Form version", *OUTCOME_FIELDS]

SHEET_HEADERS = [
    'Timestamp',
    'Reviewer',
    'Study ID (Covidence)',
    'Phase',
    'Lead Author',
    'Year',
    'Study Type',
    'Country',
    'Setting',
    'Scenario',
    'Simulation Fidelity',
    'Scenario Complexity',
    'Total N (all arms)',
    'N (this arm)',
    'Unit of randomisation',
    'Unit of analysis',
    'Team composition (free text)',
    'Team interprofessionality',
    'Provider experience',
    'NMA Node',
    'Node rationale',
    'Arm No.',
    'Arm Label',
    'CA Name',
    'Format - medium',
    'Format - type',
    'CA logic structure',
    'Pre-training intensity',
    'Pre-training description',
    'Training duration',
    'Training method',
    'Training timing',
    'Designated Reader present',
    'Reader use mode',
    'Interaction style',
    'Strictness of workflow',
    'CA use enforcement',
    'CA use fidelity check',
    'CA use fidelity rate (%)',
    'Implementation narrative',
    'Adherence reported?',
    'Adherence measure tier',
    'Adherence instrument',
    'Adherence scale max',
    'Adherence Mean',
    'Adherence SD',
    'Adherence N analyzed',
    'Adherence original format',
    'Adherence raw median stats',
    'Adherence conversion method',
    'Adherence Kirkpatrick level',
    'Adherence comments',
    'Time reported?',
    'Time Mean',
    'Time SD',
    'Time N analyzed',
    'Time original format',
    'Time raw median stats',
    'Time conversion method',
    'Time comments',
    'Error reported?',
    'Error events',
    'Error N analyzed',
    'Error measure as reported',
    'Error original reporting',
    'Error comments',
    'NTS reported?',
    'NTS Mean',
    'NTS SD',
    'NTS N analyzed',
    'NTS instrument',
    'NTS comments',
    'Sim patient outcome reported?',
    'Sim patient outcome description',
    'RoB-2 D1 Randomization',
    'RoB-2 D2 Deviation',
    'RoB-2 D3 Missing data',
    'RoB-2 D4 Measurement',
    'RoB-2 D5 Selective reporting',
    'RoB-2 Overall',
    'RoB-2 Comments',
    'MERSQI total (max 18)',
    'MERSQI Comments',
    'Publication type',
    'Author contact status',
    'Adherence outcome direction',
    'Coding uncertainty log',
]


def _s(x):
    # Preserve real numeric cells, including MERSQI. Never convert missing values to zero.
    return "" if x is None else x


def has_value(x):
    return x is not None and str(x).strip() != ""


def canonical_key(record):
    def integerish(value):
        try:
            v = float(value)
            return str(int(v)) if v.is_integer() else str(value).strip()
        except (ValueError, TypeError):
            return str(value).strip()
    return (integerish(record.get("Study ID (Covidence)", "")),
            str(record.get("Phase", "")).strip(), str(record.get("Reviewer", "")).strip(),
            integerish(record.get("Arm No.", "")))


def validate_result(r):
    errors = []
    for f in ["Outcome name", "Scenario", "Scenario scope", "Analysis population",
              "Estimate basis", "Original reporting format", "Result status", "Source"]:
        if not has_value(r.get(f)):
            errors.append(f"{f} is required (use 'not reported' where appropriate).")
    fmt = r.get("Original reporting format")
    status = r.get("Result status")
    note = str(r.get("Comments") or "").strip()
    raw = str(r.get("Raw reported statistics") or "").strip()
    if fmt not in FORMATS:
        errors.append("Choose a supported reporting format.")
    if status not in ("Reported", "Partially reported", "Source pending / unclear"):
        errors.append("Select Result status.")
    if any("unclear" in str(r.get(f) or "").lower() for f in ["Analysis population", "Estimate basis", "Outcome direction", "N unit"]) and not note:
        errors.append("Explain unclear analysis, direction, or denominator choices in Comments.")
    expected = FORMATS.get(fmt, [])
    missing = [f for f in expected if not has_value(r.get(f))]
    if missing and not (status in ("Partially reported", "Source pending / unclear") and note):
        errors.append("Enter " + ", ".join(missing) + "; if absent, select Partially reported and explain.")
    if status in ("Partially reported", "Source pending / unclear") and not note:
        errors.append("Explain missing statistics or the unresolved source in Comments.")
    numeric_present = any(has_value(r.get(f)) for f in NUMERIC_FIELDS if f != "CI level (%)")
    # N or a scale maximum alone is not a result.
    if not numeric_present and not raw:
        errors.append("Enter a reported result or preserve the source statement/figure reference in Raw reported statistics.")
    unit_text = str(r.get("Measurement unit") or "").lower().replace(" ", "")
    if any(token in unit_text for token in ("min.seconds", "minutes.seconds", "mm:ss", "min:sec")) and not raw:
        errors.append("Preserve the exact printed time notation in Raw reported statistics (e.g. 5.40 = 5 min 40 s).")
    if fmt == "Other / figure / narrative" and not raw:
        errors.append("This format requires Raw reported statistics.")
    if not has_value(r.get("N analyzed")) and not note:
        errors.append("N analyzed is blank: explain in Comments; do not copy the arm N by default.")
    if has_value(r.get("N analyzed")) and not has_value(r.get("N unit")):
        errors.append("State the N unit (people, teams, simulations, etc.).")
    if numeric_present and not has_value(r.get("Measurement unit")):
        errors.append("State the measurement unit (%, proportion 0–1, points, seconds, etc.).")
    for f in NUMERIC_FIELDS + ["N analyzed", "Scale max"]:
        v = r.get(f)
        if has_value(v) and (not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)):
            errors.append(f"{f} must be a finite number.")
    for f in ["SD", "SE", "IQR width", "Events", "Scale max"]:
        if isinstance(r.get(f), (int, float)) and r[f] < 0:
            errors.append(f"{f} cannot be negative.")
    n = r.get("N analyzed")
    if isinstance(n, (int, float)) and n <= 0:
        errors.append("N analyzed must be positive; preserve a printed 0/0 in Raw statistics and explain instead.")
    if fmt == "events / N" and isinstance(n, (int, float)) and isinstance(r.get("Events"), (int, float)):
        if r["Events"] > n:
            errors.append("Events exceed N: this block represents a dichotomous count. Preserve repeated-event counts as Other with their exposure denominator.")
    checks = [("Q1", "Median", "Q3"), ("Min", "Median", "Max")]
    conflict = False
    for a,b,c in checks:
        if all(isinstance(r.get(f), (int,float)) for f in (a,b,c)) and not r[a] <= r[b] <= r[c]:
            conflict = True
    for a,b in [("Min","Max"),("Q1","Q3"),("CI lower","CI upper")]:
        if all(isinstance(r.get(f),(int,float)) for f in (a,b)) and r[a] > r[b]:
            conflict = True
    if conflict and not (r.get("Source conflict confirmed") and note):
        errors.append("Statistics are out of order. Correct the entry, or confirm that the source prints it this way and explain.")
    if fmt == "effect estimate (CI)" and not has_value(r.get("Estimate type / comparison")):
        errors.append("Identify the effect measure, comparison/reference and scale (e.g. adjusted OR; log-time ratio).")
    if fmt in ("mean (CI)", "effect estimate (CI)") and not has_value(r.get("CI level (%)")) and not note:
        errors.append("Record the CI level or explain that it is not stated.")
    if r.get("Domain") == "Time":
        for f in ("Time type", "Time origin", "Time endpoint"):
            if not has_value(r.get(f)):
                errors.append(f"{f} is required; 'not reported' is acceptable when explained.")
    if r.get("Domain") in ("Adherence", "NTS"):
        if not has_value(r.get("Outcome direction")):
            errors.append("Select the outcome direction, including Unclear if necessary.")
        if not has_value(r.get("Instrument")) and not note:
            errors.append("Name the checklist/instrument or explain that it is not reported.")
    return errors


def validate_domains(gates, records):
    errors = []
    for domain, gate in gates.items():
        selected = [r for r in records if r["Domain"] == domain]
        if gate is None:
            errors.append(f"{domain}: choose the reporting status.")
        if gate in GATE_ACTIVE and not selected:
            errors.append(f"{domain}: add at least one result, or correct the reporting status.")
        if gate not in GATE_ACTIVE and selected:
            errors.append(f"{domain}: result cards remain under '{gate}'. Remove them explicitly or restore Reported/Partially reported.")
        if gate in GATE_ACTIVE:
            for i, r in enumerate(selected,1):
                errors += [f"{domain} result {i}: {e}" for e in validate_result(r)]
    signatures = set()
    for r in records:
        signature = tuple(str(r.get(k) or '').strip().casefold() for k in
                          ['Domain','Outcome name','Scenario','Scenario scope','Event / phase','Analysis population','Estimate basis','Instrument'])
        if signature in signatures:
            errors.append("Two result cards have identical labels. Remove the duplicate or distinguish their analysis/instrument/event.")
        signatures.add(signature)
    return errors


def row_cells(values):
    result = []
    for v in values:
        if v is None or v == "":
            result.append({})
        elif isinstance(v, (int,float)) and not isinstance(v,bool):
            if not math.isfinite(v):
                raise ValueError("Cannot save a non-finite number.")
            result.append({"userEnteredValue": {"numberValue": v}})
        else:
            # Explicit stringValue also prevents spreadsheet formula injection.
            result.append({"userEnteredValue": {"stringValue": str(v)}})
    return {"values": result}


def check_headers(ws, expected):
    actual = ws.row_values(1)
    while actual and actual[-1] == "":
        actual.pop()
    if actual != expected:
        raise ValueError(f"'{ws.title}' headers do not match this version. Existing columns were not changed; check the header template.")


def ensure_outcomes(book, arms):
    check_headers(arms, SHEET_HEADERS)
    try:
        ws = book.worksheet(OUTCOMES_TAB)
        check_headers(ws, OUTCOME_HEADERS)
        return ws
    except gspread.WorksheetNotFound:
        sheet_id = uuid.uuid4().int % 2_000_000_000
        book.batch_update({"requests": [
            {"addSheet": {"properties": {"sheetId": sheet_id, "title": OUTCOMES_TAB,
                "gridProperties": {"rowCount": 1000, "columnCount": len(OUTCOME_HEADERS), "frozenRowCount": 1}}}},
            {"updateCells": {"start": {"sheetId": sheet_id, "rowIndex":0, "columnIndex":0},
                 "rows": [row_cells(OUTCOME_HEADERS)], "fields": "userEnteredValue"}}
        ]})
        return book.worksheet(OUTCOMES_TAB)


def existing_key_rows(ws, headers, key):
    return [dict(zip(headers,row)) for row in ws.get_all_values()[1:]
            if canonical_key(dict(zip(headers,row))) == key]


def save_submission(book, arms, outcomes, arm_record, records, submission_id):
    """Append both tabs atomically. A stable metadata ID rejects concurrent same-key submissions.
    There are no automatic overwrites of prior calibration or main-extraction rows.
    """
    check_headers(arms, SHEET_HEADERS)
    check_headers(outcomes, OUTCOME_HEADERS)
    key = canonical_key(arm_record)
    existing_arms = existing_key_rows(arms, SHEET_HEADERS, key)
    existing_outcomes = existing_key_rows(outcomes, OUTCOME_HEADERS, key)
    if existing_arms or existing_outcomes:
        if len(existing_arms) == 1 and records and len(existing_outcomes) == len(records):
            if all(r.get("Submission ID") == submission_id for r in existing_outcomes):
                return "already_saved"
        # Covers a retry of an all-gates-negative arm with no Outcomes rows.
        if len(existing_arms) == 1 and not records and not existing_outcomes:
            if str(existing_arms[0].get("Timestamp")) == str(arm_record["Timestamp"]):
                return "already_saved"
        raise ValueError("This Study ID / Phase / Reviewer / Arm No. already exists. Nothing was overwritten. Review the existing submission before correcting it.")
    key_json = json.dumps(key, ensure_ascii=False)
    metadata_id = int(hashlib.sha256(("nma-v6:"+key_json).encode()).hexdigest()[:8],16) % 2_000_000_000 + 1
    requests = [{"createDeveloperMetadata": {"developerMetadata": {
        "metadataId":metadata_id, "metadataKey":"nma_v6_arm", "metadataValue":key_json,
        "location":{"spreadsheet":True}, "visibility":"DOCUMENT"}}},
        {"appendCells":{"sheetId":arms.id, "rows":[row_cells([arm_record.get(h,"") for h in SHEET_HEADERS])],
                         "fields":"userEnteredValue"}}]
    if records:
        rows = []
        for record in records:
            complete = {**record, **{k:arm_record[k] for k in ['Timestamp','Reviewer','Study ID (Covidence)','Phase','Arm No.']},
                        "Submission ID":submission_id, "Form version":VERSION}
            rows.append(row_cells([complete.get(h,"") for h in OUTCOME_HEADERS]))
        requests.append({"appendCells":{"sheetId":outcomes.id, "rows":rows,"fields":"userEnteredValue"}})
    book.batch_update({"requests":requests})
    return "saved"


@st.cache_resource
def open_book():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    return gspread.authorize(creds).open_by_url(st.secrets.get("spreadsheet_url", SHEET_URL))


def add_result(domain):
    st.session_state.setdefault('_ids_'+domain, []).append(uuid.uuid4().hex[:12])


def delete_result(domain, rid):
    st.session_state['_ids_'+domain].remove(rid)
    for key in list(st.session_state):
        if key.startswith('r_'+rid+'_'):
            del st.session_state[key]


def clear_draft(new_study=False):
    keep = {'reviewer','phase'} if new_study else {
        'reviewer','phase','study_id','author','year','study_type','country','setting','scenario',
        'total_n','unit_random','unit_analysis','sim_fidelity','scen_complexity','pub_type',
        'author_contact','exp_level','team_compo','team_inter'}
    next_arm = int(st.session_state.get('arm_no',1)) + 1
    for key in list(st.session_state):
        if key not in keep:
            del st.session_state[key]
    if not new_study:
        st.session_state['arm_no'] = next_arm


def render_result(domain, rid, ordinal):
    prefix = 'r_'+rid+'_'
    r = {'Domain':domain, 'Outcome ID':rid}
    def txt(field, label=None, help=None):
        r[field] = st.text_input(label or field, key=prefix+field, help=help)
        return r[field]
    def pick(field, opts, help=None):
        r[field] = st.selectbox(field,opts,index=None,placeholder='— select —',key=prefix+field,help=help)
        return r[field]
    def number(field):
        if field == 'Events':
            r[field] = st.number_input(field,value=None,min_value=0,step=1,key=prefix+field)
        elif field == 'CI level (%)':
            r[field] = st.number_input(field,value=None,min_value=0.01,max_value=100.0,key=prefix+field)
        else:
            r[field] = st.number_input(field,value=None,format='%.6f',key=prefix+field)
    with st.expander(f'{domain} result {ordinal}',expanded=True):
        st.button('Delete this result',key='del_'+rid,on_click=delete_result,args=(domain,rid))
        c1,c2 = st.columns(2)
        with c1:
            txt('Outcome name',help='Name the score, action or event. Only extract outcomes selected under the review rules.')
            pick('Scenario scope',['Single scenario','Multiple scenarios combined','Not specified'])
            txt('Scenario',help="Use the named scenario, 'All scenarios', or 'Not reported'.")
            txt('Event / phase',help='Optional: e.g. primary event (SVT), secondary event (VT), post-test.')
        with c2:
            pick('Result status',['Reported','Partially reported','Source pending / unclear'])
            pick('Analysis population',['As randomised / ITT','Per-protocol / completers','As-treated / actual use','Other / unclear'])
            pick('Estimate basis',['Raw descriptive statistics','Model-based / adjusted estimate','Other / unclear'])
            if domain in ('Adherence','NTS'):
                txt('Instrument',help='Checklist/scale name; explain in Comments if absent.')
        if domain == 'Time':
            c1,c2,c3 = st.columns(3)
            with c1: pick('Time type',['Time to critical action','Total scenario / on-scene duration','Other time interval'])
            with c2: txt('Time origin',help='What starts the clock? If not reported, say so.')
            with c3: txt('Time endpoint',help='What stops the clock? Keep preset scenario stopping rules separate from observed results.')
        if domain in ('Adherence','NTS'):
            c1,c2 = st.columns(2)
            with c1: pick('Outcome direction',['Higher = better','Lower = better','Context-dependent / unclear'])
            with c2: number('Scale max')
        if domain == 'Adherence':
            c1,c2 = st.columns(2)
            with c1: pick('Adherence measure tier',['Tier 1 — steps completed/missed (proportion)',
                'Tier 2 — checklist-based adherence score','Tier 3 — validated technical performance score','Other / unclear'])
            with c2: pick('Kirkpatrick level',['KP1 Reaction','KP2 Learning','KP3 Behaviour','KP4 Results','N/A / unclear'])
        fmt = pick('Original reporting format',list(FORMATS),help='Keep source values. No median-to-mean or CI-to-SD conversion is done here.')
        primary = [f for f in FORMATS.get(fmt,[]) if f != 'N analyzed']
        if primary:
            cols = st.columns(min(len(primary),3))
            for i,f in enumerate(primary):
                with cols[i % len(cols)]: number(f)
        with st.expander('Additional statistics (only if reported)',expanded=False):
            rest = [f for f in NUMERIC_FIELDS if f not in primary]
            cols = st.columns(3)
            for i,f in enumerate(rest):
                with cols[i%3]: number(f)
        c1,c2,c3 = st.columns(3)
        with c1:
            r['N analyzed'] = st.number_input('N analyzed',value=None,min_value=1,step=1,key=prefix+'N analyzed')
        with c2: pick('N unit',['Individuals','Teams','Simulations / team-events','Action opportunities','Other / unclear'])
        with c3: txt('Measurement unit',help='E.g. %, proportion 0–1, score points, seconds, min.seconds. Keep source units.')
        txt('Estimate type / comparison',help='For effects: measure, comparator and scale, e.g. adjusted OR vs no aid. For model means: model name.')
        r['Raw reported statistics'] = st.text_area('Raw reported statistics (optional unless figure/other)',key=prefix+'Raw reported statistics',
            help='Preserve exact notation, extra statistics, or text-only findings here. No invented numbers.')
        txt('Source',help='Page/table/figure/supplement identifying this result.')
        r['Comments'] = st.text_area('Comments',key=prefix+'Comments',help='Missing statistics, differing N, selected analysis, or source conflicts.')
        r['Source conflict confirmed'] = st.checkbox('I checked an ordering conflict against the source; preserve the printed values',key=prefix+'Source conflict confirmed')
        if r['Source conflict confirmed']:
            r['Comments'] = '[Source ordering conflict confirmed] '+r['Comments'] if r['Comments'].strip() else ''
    return r


def main():
    st.set_page_config(page_title='Cognitive Aids NMA Extraction v6.0',layout='wide')
    st.title('Cognitive Aids NMA — Data Extraction (v6.0)')
    st.info('One arm per submission. In Tab 4, use ＋ Add result for additional selected outcomes or scenarios. '
            'Keep statistics as reported. Use the same arm numbering as your co-reviewer. Nothing is saved until Submit. '
            '**Refresh the browser to start a new study.**')
    st.button('Start next arm — clear arm/outcome fields',on_click=clear_draft,args=(False,))
    st.caption('Clears arm-specific and outcome fields and advances Arm No.; study-level fields stay. '
               '**For a NEW STUDY, refresh the browser (F5 / Cmd+R)** — that clears everything.')
    try:
        book = open_book()
        main_title = st.secrets.get('arms_sheet_name','')
        worksheet = book.worksheet(main_title) if main_title else book.sheet1
        if worksheet.title == OUTCOMES_TAB:
            raise ValueError('Set arms_sheet_name to the existing 87-column tab in secrets.')
    except Exception as exc:
        st.error('Cannot connect to the spreadsheet. Check the existing service-account secrets and access. '+str(exc))
        st.stop()
    with st.expander('One-time setup: Outcomes tab'):
        st.caption('The existing 87-column tab is preserved. This button creates Outcomes with the required headers, or checks an existing Outcomes tab.')
        if st.button('Create / check Outcomes tab',key='setup_outcomes'):
            try:
                ensure_outcomes(book,worksheet)
                st.success('Outcomes is ready. No study data were added.')
            except Exception as exc:
                st.error(str(exc))

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
                ["Parallel RCT", "Crossover RCT", "Cluster RCT", "Other", "Unclear"],
                help="Record the actual allocation design. Analysis at cluster level does not change a cluster-randomised design into a parallel individual trial. Record allocation and analysis units separately; describe repeated conditions in the log.",
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
            total_n = st.number_input("Total N (all arms)", min_value=1, value=None,
                                      step=1, placeholder="— enter N —", key="total_n",
                                      help="In the unit the authors computed the effect "
                                           "size on. Record the other totals "
                                           "(randomised vs analysed, people vs teams) in "
                                           "the Coding uncertainty log. For crossover/repeated conditions, do not add the same people or teams across conditions.")
            arm_n = st.number_input("N (this arm) ★ — or explain missing N in the log", min_value=1, value=None,
                                    step=1, placeholder="— enter N —", key="arm_n",
                                    help="Same unit as Total N. If an individual outcome "
                                         "is analysed on a different number, record that "
                                         "in that outcome's own 'N analyzed' box. If unavailable or conflicting, leave blank and explain in the uncertainty log.")

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
                ["Individual (single-provider)", "Team (multi-provider)", "Cluster", "Simulation / team-event", "Other", "Unclear"],
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
                ["Individual (single-provider)", "Team (multi-provider)", "Cluster", "Simulation / team-event", "Other", "Unclear"],
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
            "Unclear decisions, conflicting data, or analysis/unit notes (one line each):",
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
            arm_no = st.number_input("★ Arm No.", min_value=1, value=1, step=1, key="arm_no",
                help="Use a unique number within this study (1, 2, 3...). Both reviewers must use the same Arm Label-to-number mapping; default to paper order. This is not the NMA node code.")
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
                 "Yes — qualitative only", "Not reported", "Explicitly not checked", "Unclear", "N/A (Control)"],
                help="Use Not reported for silence; Explicitly not checked only when the authors say so.",
                key="fidelity_check", index=None, placeholder="— select —")
        with e2:
            fidelity_rate = st.text_input(
                "CA use fidelity value (include its unit)",
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
        st.caption('Leave absent statistics blank; never substitute zero for missing SD. Keep per-scenario results and author-reported combined summaries distinct. Do not average during extraction. '
                   'Only extract prespecified items; do not treat a total and its components as independent contributions.')
        outcome_records = []
        gates = {}
        for domain, gate_key in DOMAINS.items():
            st.subheader({'Adherence':'Outcome 1 — Adherence / task completion',
                          'Time':'Outcome 2 — Time', 'Error':'Outcome 3 — Error',
                          'NTS':'Outcome 4 — Teamwork / NTS'}[domain])
            gates[domain] = st.selectbox(f'★ {domain} reported?',GATE_OPTS,index=None,placeholder='— select —',key=gate_key,
                help='Reported: results available. Partially reported: some statistics absent. Use the other states for silence, explicitly not measured, measured but not extractable, or uncertainty.')
            ids = st.session_state.setdefault('_ids_'+domain,[])
            if gates[domain] in GATE_ACTIVE:
                if not ids:
                    add_result(domain)
                st.button('＋ Add result',key='add_'+domain,on_click=add_result,args=(domain,))
            elif ids:
                st.warning('Existing result cards are still shown. Remove them explicitly or restore the reporting status before submitting.')
            for i,rid in enumerate(list(st.session_state['_ids_'+domain]),1):
                outcome_records.append(render_result(domain,rid,i))
        adh_gate, time_gate, err_gate, nts_gate = [gates[d] for d in DOMAINS]
        st.subheader('Outcome 5 — Simulated patient outcome (descriptive only)')
        simpt_gate = st.selectbox('★ Simulated patient outcome reported?',GATE_OPTS,index=None,placeholder='— select —',key='simpt_gate')
        simpt_desc = st.text_area('Simulated patient outcome description',key='simpt_desc',
            help='Record observed numbers and denominators, source and whether script-determined. A scripted ROSC or preset stop time alone is not an observed outcome.')

    # Bind populated cards to their study/reviewer/phase/arm. Manual identity changes must not relabel them.
    identity = (study_id, phase, reviewer, arm_no)
    identity_complete = all(v is not None for v in identity)
    has_result_content = any(any(has_value(r.get(f)) for f in ['Outcome name','Raw reported statistics',*NUMERIC_FIELDS]) for r in outcome_records)
    if identity_complete and has_result_content and '_outcome_context' not in st.session_state:
        st.session_state['_outcome_context'] = identity
    context_changed = '_outcome_context' in st.session_state and st.session_state['_outcome_context'] != identity
    if context_changed:
        st.warning('Study/reviewer/phase/arm changed while outcome data remain. Restore the original identity, use Start next arm, or refresh the browser to start a new study.')
    with tab5:
        st.info("ℹ️ **RoB-2 and MERSQI are entered ONCE per study** (normally on Arm 1). "
                "On later arms leave these blank unless assessing a different RoB result — they are optional "
                "and will not block submission.")
        st.subheader("RoB-2 (for RCTs)")
        st.caption("Assess the review-selected result; state outcome ID/name, scenario, analysis population and RoB 2 version in comments. MERSQI is recorded once per study.")
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
        st.caption("Scores are calculated and saved automatically. Use comments for the assessed instrument, completion numerator/denominator and brief reasons.")
        mq1, mq2 = st.columns(2)
        with mq1:
            mersqi_design = st.selectbox("1. Study design",
                [(1.0, "Single group, post-test only"), (1.5, "Single group, pre-post"),
                 (2.0, "Non-randomised 2-group"), (3.0, "Randomised controlled trial (RCT)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_design", index=None, placeholder="— select —")

            st.markdown("**2. Sampling** — scored as institutions + completion rate")
            mersqi_inst = st.selectbox("2a. Number of institutions",
                [(0.5, "1 institution"), (1.0, "2 institutions"), (1.5, "≥3 institutions")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_inst", index=None, placeholder="— select —")
            mersqi_resp = st.selectbox("2b. Completion rate",
                [(0.5, "<50% or not reported"), (1.0, "50–74%"), (1.5, "≥75%")],
                help="For an intervention study this is the proportion of those ENROLLED "
                     "who completed the evaluation — not the proportion of those invited "
                     "who agreed to take part. A trial where every enrolled participant "
                     "completed the scenario scores ≥75%, even if many declined "
                     "recruitment. Record the numerator and denominator you used in the "
                     "comments box.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_resp", index=None, placeholder="— select —")

            mersqi_data = st.selectbox("3. Type of data",
                [(1.0, "Subjective only (self-reported)"), (3.0, "Objective (observed/measured)")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_data", index=None, placeholder="— select —")
        with mq2:
            st.markdown("**4. Validity of the evaluation instrument** — three components, 0 or 1 each")
            st.caption("Name the review-relevant performance instrument you assessed in comments; it may be an NTS instrument when no adherence score exists.")
            mersqi_v_content = st.selectbox("4a. Content",
                [(0.0, "Not reported"), (1.0, "Reported")],
                help="Items built from existing guidelines, published checklists or "
                     "established evidence; expert panel review.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_v_content", index=None, placeholder="— select —")
            mersqi_v_struct = st.selectbox("4b. Internal structure",
                [(0.0, "Not reported"), (1.0, "Reported")],
                help="Internal reliability, or inter-rater agreement (κ, ICC, CCC).",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_v_struct", index=None, placeholder="— select —")
            mersqi_v_rel = st.selectbox("4c. Relationships to other variables",
                [(0.0, "Not reported"), (1.0, "Reported")],
                help="The INSTRUMENT'S SCORES analysed against external variables. "
                     "Scored on whether it is REPORTED, not on whether it reached "
                     "significance — a non-significant correlation still earns the "
                     "point. A comparison of baseline characteristics between arms does "
                     "NOT count, and neither does a subgroup analysis that compares the "
                     "treatments within strata rather than relating scores to an "
                     "external criterion.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_v_rel", index=None, placeholder="— select —")

            st.markdown("**5. Data analysis** — appropriateness + sophistication")
            mersqi_a_approp = st.selectbox("5a. Appropriateness",
                [(0.0, "Inappropriate for the study design or type of data"),
                 (1.0, "Appropriate for the study design and type of data")],
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_a_approp", index=None, placeholder="— select —")
            mersqi_a_soph = st.selectbox("5b. Sophistication",
                [(1.0, "Descriptive analysis only"), (2.0, "Beyond descriptive (inferential)")],
                help="This is not a 'complex model scores higher' scale. Any inferential "
                     "analysis scores 2.0.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_a_soph", index=None, placeholder="— select —")

            mersqi_outcomes = st.selectbox("6. Outcomes (highest level only)",
                [(1.0, "Satisfaction / attitudes / opinions"), (1.5, "Knowledge / skills"),
                 (2.0, "Behaviours (in practice)"), (3.0, "Patient / healthcare outcomes")],
                help="A SIMULATED patient outcome is not a patient outcome. Do not score "
                     "3.0 for simulated ROSC.",
                format_func=lambda x: f"{x[0]} — {x[1]}", key="mersqi_outcomes", index=None, placeholder="— select —")

        # Ten inputs across the six MERSQI domains (max 18).
        _mersqi_items = [
            ("1 Design",              mersqi_design),
            ("2a Institutions",       mersqi_inst),
            ("2b Completion rate",    mersqi_resp),
            ("3 Type of data",        mersqi_data),
            ("4a Content",            mersqi_v_content),
            ("4b Internal structure", mersqi_v_struct),
            ("4c Relationships",      mersqi_v_rel),
            ("5a Appropriateness",    mersqi_a_approp),
            ("5b Sophistication",     mersqi_a_soph),
            ("6 Outcomes",            mersqi_outcomes),
        ]
        _mersqi_subscores = [v for _, v in _mersqi_items]
        _n_mersqi = sum(1 for v in _mersqi_subscores if v is not None)

        if _n_mersqi == 0:
            mersqi_total = ""
            _mersqi_detail = ""
        elif _n_mersqi < len(_mersqi_items):
            mersqi_total = ""
            _mersqi_detail = ""
            st.warning(f"⚠️ MERSQI partial: {_n_mersqi}/{len(_mersqi_items)} items selected. "
                       "Complete all of them (study-level) or leave all blank on duplicate arms.")
        else:
            _tot = sum(v[0] for v in _mersqi_subscores)
            mersqi_total = round(_tot, 1)
            _mersqi_detail = " | ".join(f"{lab}={v[0]} ({v[1]})" for lab, v in _mersqi_items)
            _dom = {
                "1 Design": mersqi_design[0],
                "2 Sampling": mersqi_inst[0] + mersqi_resp[0],
                "3 Data": mersqi_data[0],
                "4 Validity": mersqi_v_content[0] + mersqi_v_struct[0] + mersqi_v_rel[0],
                "5 Analysis": mersqi_a_approp[0] + mersqi_a_soph[0],
                "6 Outcomes": mersqi_outcomes[0],
            }
            st.info(f"📊 **MERSQI total (auto-computed): {mersqi_total} / 18**")
            st.caption("By domain — " + " · ".join(f"{k}: {v}" for k, v in _dom.items()))

        mersqi_rationale = st.text_area("MERSQI comments (your reasoning only)", height=90,
            key="mersqi_rationale",
            help="The scores above are saved automatically. Use this box for WHY — "
                 "especially for the three validity components and for the completion "
                 "rate numerator/denominator you used.",
            placeholder="4a content: checklist items drawn from published guideline "
                        "recommendations, p.3\n"
                        "4b structure: inter-rater CCC 0.960, p.5\n"
                        "4c relationships: not reported — subgroup analysis compares arms "
                        "within specialty, not instrument scores against an external "
                        "criterion\n"
                        "2b completion: 60/60 enrolled completed the scenario")

        # Stored as: auto-generated per-item scores, then the reviewer's reasoning.
        # "MERSQI total (max 18)" keeps the NUMBER ONLY.
        mersqi_comments = (f"[{_mersqi_detail}]\n{mersqi_rationale}".strip()
                           if _mersqi_detail else mersqi_rationale)

    st.markdown('---')
    st.caption(f'{len(outcome_records)} result row(s) will be linked to this arm. Results are saved in Outcomes; legacy result cells in the 87-column tab stay empty for new submissions.')
    submitted = st.button('💾 Submit Arm Data',key='submit_arm',disabled=bool(st.session_state.get('_saved')))
    if st.session_state.get('_saved'):
        st.success('Saved. Use Start next arm for the next arm of this study, or refresh the browser to start a new study.')
    if submitted:
        missing_text = []
        if not reviewer: missing_text.append('Reviewer (Tab 1)')
        if study_id is None: missing_text.append('Study ID (Tab 1)')
        if phase is None: missing_text.append('Phase (Tab 1)')
        if not author.strip(): missing_text.append('Lead Author (Tab 1)')
        if year is None: missing_text.append('Year (Tab 1)')
        if arm_n is None and not coding_uncertainty_log.strip(): missing_text.append('N (this arm), or a missing/conflicting-N explanation in the log')
        if not arm_label.strip(): missing_text.append('Arm Label (Tab 2)')
        if not node_rationale.strip(): missing_text.append('Node rationale (Tab 2)')
        CRITICAL_FIELDS = [('Study type', study_type, 'Tab 1'), ('Setting', setting, 'Tab 1'), ('Simulation fidelity', sim_fidelity, 'Tab 1'), ('Scenario complexity', scen_complexity, 'Tab 1'), ('Publication type', pub_type, 'Tab 1'), ('Unit of randomisation', unit_random, 'Tab 1'), ('Unit of analysis', unit_analysis, 'Tab 1'), ('Provider experience level', exp_level, 'Tab 1'), ('Team interprofessionality', team_inter, 'Tab 1'), ('NMA Node', nma_node, 'Tab 2'), ('CA medium', medium, 'Tab 2'), ('CA type', ca_type, 'Tab 2'), ('CA logic structure', ca_logic, 'Tab 2'), ('Pre-training intensity', pretrain_intensity, 'Tab 3'), ('Training method', train_method, 'Tab 3'), ('Training timing', train_timing, 'Tab 3'), ('Reader present', reader_present, 'Tab 3'), ('Interaction style', interaction, 'Tab 3'), ('Strictness', strictness, 'Tab 3'), ('Enforcement', enforcement, 'Tab 3'), ('Fidelity check', fidelity_check, 'Tab 3'), ('Adherence reported?', adh_gate, 'Tab 4'), ('Time reported?', time_gate, 'Tab 4'), ('Error reported?', err_gate, 'Tab 4'), ('NTS reported?', nts_gate, 'Tab 4'), ('Sim patient outcome reported?', simpt_gate, 'Tab 4')]
        errors = missing_text + [name+' ('+tab+')' for name,value,tab in CRITICAL_FIELDS if value is None]
        errors += validate_domains(gates,outcome_records)
        if context_changed:
            errors.append('Outcome identity changed: restore it or start a new arm/study.')
        unclear_fields = [name for name,value,tab in CRITICAL_FIELDS if isinstance(value,str) and 'unclear' in value.lower()]
        if reader_mode == 'Unclear': unclear_fields.append('Reader use mode')
        if unclear_fields and not coding_uncertainty_log.strip():
            errors.append('Explain Unclear selections in the log: '+', '.join(unclear_fields))
        if fidelity_check == 'Yes — quantitative (e.g., observed/timed use)' and not fidelity_rate.strip():
            errors.append('Enter the quantitative fidelity value with its unit, or explain its absence in the implementation narrative.' if not implementation_narrative.strip() else '')
        errors = [e for e in errors if e]
        if fidelity_rate.strip() and fidelity_check not in ['Yes — quantitative (e.g., observed/timed use)','Yes — ordinal scale (e.g., 0–5 rating)']:
            errors.append('A fidelity value remains under a non-quantitative status. Clear it or correct the status.')
        if simpt_gate in GATE_ACTIVE and not simpt_desc.strip(): errors.append('Describe the simulated patient result and its source.')
        if simpt_gate not in GATE_ACTIVE and simpt_desc.strip(): errors.append('A simulated patient result remains under an inactive status. Clear it or correct the status.')
        if 0 < _n_mersqi < len(_mersqi_items): errors.append('Complete all MERSQI components or leave all blank.')
        if _n_mersqi == len(_mersqi_items) and not mersqi_rationale.strip(): errors.append('MERSQI: identify the assessed instrument and give brief reasons in comments.')
        ratings = [d1,d2,d3,d4,d5,rob_overall]
        if any(v is not None for v in ratings):
            if not all(v is not None for v in ratings): errors.append('Complete RoB domains and overall rating, or leave all blank.')
            if not rob_comments.strip(): errors.append('RoB comments must identify the result/analysis/version and reasons.')
        if errors:
            st.error('Please resolve:\n\n'+'\n\n'.join('• '+e for e in errors))
            st.stop()
        arm_record = {
            'Timestamp': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %Z'),
            'Reviewer': reviewer,
            'Study ID (Covidence)': '' if study_id is None else str(int(study_id)),
            'Phase': phase,
            'Lead Author': author,
            'Year': _s(year),
            'Study Type': study_type,
            'Country': country,
            'Setting': setting,
            'Scenario': scenario,
            'Simulation Fidelity': sim_fidelity,
            'Scenario Complexity': scen_complexity,
            'Total N (all arms)': _s(total_n),
            'N (this arm)': _s(arm_n),
            'Unit of randomisation': unit_random,
            'Unit of analysis': unit_analysis,
            'Team composition (free text)': team_compo,
            'Team interprofessionality': team_inter,
            'Provider experience': exp_level,
            'NMA Node': nma_node,
            'Node rationale': node_rationale,
            'Arm No.': str(arm_no),
            'Arm Label': arm_label,
            'CA Name': aid_name,
            'Format - medium': medium,
            'Format - type': ca_type,
            'CA logic structure': ca_logic,
            'Pre-training intensity': pretrain_intensity,
            'Pre-training description': pretrain_desc,
            'Training duration': train_duration,
            'Training method': train_method,
            'Training timing': train_timing,
            'Designated Reader present': reader_present,
            'Reader use mode': reader_mode,
            'Interaction style': interaction,
            'Strictness of workflow': strictness,
            'CA use enforcement': enforcement,
            'CA use fidelity check': fidelity_check,
            'CA use fidelity rate (%)': fidelity_rate,
            'Implementation narrative': implementation_narrative,
            'Adherence reported?': _s(adh_gate),
            'Adherence measure tier': '',
            'Adherence instrument': '',
            'Adherence scale max': '',
            'Adherence Mean': '',
            'Adherence SD': '',
            'Adherence N analyzed': '',
            'Adherence original format': '',
            'Adherence raw median stats': '',
            'Adherence conversion method': '',
            'Adherence Kirkpatrick level': '',
            'Adherence comments': '',
            'Time reported?': _s(time_gate),
            'Time Mean': '',
            'Time SD': '',
            'Time N analyzed': '',
            'Time original format': '',
            'Time raw median stats': '',
            'Time conversion method': '',
            'Time comments': '',
            'Error reported?': _s(err_gate),
            'Error events': '',
            'Error N analyzed': '',
            'Error measure as reported': '',
            'Error original reporting': '',
            'Error comments': '',
            'NTS reported?': _s(nts_gate),
            'NTS Mean': '',
            'NTS SD': '',
            'NTS N analyzed': '',
            'NTS instrument': '',
            'NTS comments': '',
            'Sim patient outcome reported?': _s(simpt_gate),
            'Sim patient outcome description': simpt_desc,
            'RoB-2 D1 Randomization': _s(d1),
            'RoB-2 D2 Deviation': _s(d2),
            'RoB-2 D3 Missing data': _s(d3),
            'RoB-2 D4 Measurement': _s(d4),
            'RoB-2 D5 Selective reporting': _s(d5),
            'RoB-2 Overall': _s(rob_overall),
            'RoB-2 Comments': rob_comments,
            'MERSQI total (max 18)': mersqi_total,
            'MERSQI Comments': mersqi_comments,
            'Publication type': pub_type,
            'Author contact status': _s(author_contact),
            'Adherence outcome direction': '',
            'Coding uncertainty log': coding_uncertainty_log,
        }
        # Stable retry identifiers: do not generate a second submission after an ambiguous response.
        st.session_state.setdefault('_submission_id',uuid.uuid4().hex)
        st.session_state.setdefault('_draft_timestamp',datetime.now(TZ).isoformat(timespec='microseconds'))
        arm_record['Timestamp'] = st.session_state['_draft_timestamp']
        submission_id = st.session_state['_submission_id']
        try:
            outcomes_ws = book.worksheet(OUTCOMES_TAB)
        except gspread.WorksheetNotFound:
            st.error('First open One-time setup and click Create / check Outcomes tab. Your draft remains on screen.')
            st.stop()
        payload = {'arm':arm_record,'outcomes':outcome_records,'submission_id':submission_id}
        payload_digest = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if st.session_state.get('_attempt_digest') not in (None,payload_digest):
            st.error('A prior save attempt had an uncertain result and this draft changed. Restore that draft or inspect the sheet before starting a new entry. The original attempted data are available below.')
        else:
            st.session_state['_attempt_digest'] = payload_digest
            st.session_state['_attempt_payload'] = payload
            try:
                result = save_submission(book,worksheet,outcomes_ws,arm_record,outcome_records,submission_id)
                st.session_state['_saved'] = True
                st.success(f'Saved {author} ({year}), arm {arm_no}: 1 arm row + {len(outcome_records)} result rows.' if result=='saved' else 'This submission was already saved; no duplicate was added.')
            except Exception as exc:
                st.error('Save not confirmed: '+str(exc)+'. Keep this page open. Retry the unchanged draft; duplicate-key checks run before saving.')
    if st.session_state.get('_attempt_payload'):
        st.download_button('Download submitted/attempted data (JSON)',
            json.dumps(st.session_state['_attempt_payload'],ensure_ascii=False,indent=2),
            file_name='nma_submission.json',mime='application/json',key='download_attempt')


if __name__ == '__main__':
    main()
