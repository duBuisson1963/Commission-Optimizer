import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- SALARY SCALES (ORIGINAL) ---
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}

# --- SAP DATA REPOSITORY ---
SAP_DATA_25_26 = {
    "April": (2203779.00, 4505945.00), "May": (1538161.00, 10188453.00), "June": (1694411.00, 4538062.00),
    "July": (1467963.00, 8661770.00), "August": (3458608.00, 9990594.00), "September": (2296581.00, 5831207.00),
    "October": (3452423.00, 12681402.00), "November": (4283430.00, 12475440.00), "December": (3519159.00, 25149365.00),
    "January": (2635456.00, 14276893.00), "February": (2294525.00, 11612287.00), "March": (2401005.00, 13393847.00)
}

PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0, "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "policy": {"TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0, "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "display": "45/24/6"
    },
    "Sports PM": {
        "statement": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "policy": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "display": "10/30/60"
    }
}

ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- CORE FUNCTIONS ---
def get_mult(score):
    if score < 100: return Decimal('0.00')
    if score == 100: return Decimal('0.50')
    if score <= 120: return Decimal('1.00')
    if score <= 150: return Decimal('2.10')
    if score <= 180: return Decimal('4.10')
    return Decimal('6.20')

def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = str(num_str).strip().replace('"', '')
    is_neg = num_str.startswith('-')
    parts = num_str.split('.')
    integer = re.sub(r'\D', '', ''.join(parts[:-1])) if len(parts) > 1 else re.sub(r'\D', '', num_str)
    decimal = re.sub(r'\D', '', parts[-1]) if len(parts) > 1 else "00"
    try: val = float(f"{integer}.{decimal}")
    except: val = 0.0
    return -val if is_neg else val

def extract_file_data(file_obj):
    data = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        reader = PyPDF2.PdfReader(file_obj)
        pdf_text = "".join([page.extract_text() for page in reader.pages])
        norm = re.sub(r'\s+', ' ', pdf_text.replace('"', ''))
        dm = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", norm, re.I)
        pm = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target|ZAR)", norm, re.I)
        tm = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", norm, re.I)
        if dm: data["period"] = dm.group(1).strip()
        if pm: data["pers_num"], data["emp_name"] = pm.group(1).strip(), pm.group(2).strip()
        if tm: data["midpoint"] = parse_sabc_number(tm.group(1))
        for s in ALL_SEGMENTS:
            reg = s.replace(' ', r'\s*') + r"s?"
            m = re.search(rf"{reg}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})", norm, re.I)
            if m: data["segments"][s]["act"], data["segments"][s]["tar"] = parse_sabc_number(m.group(1)), parse_sabc_number(m.group(2))
    except: pass
    return data

def swap_act_tar(seg):
    st.session_state[f"tar_{seg}"] = st.session_state[f"act_{seg}"]
    st.session_state[f"act_{seg}"] = 0.0

def run_scenario(entries, mid, weights, logic='absorbed'):
    lines, sum_seg = [], Decimal('0')
    ta = sum(Decimal(str(e["act"])) for e in entries if e["name"] in weights)
    tt = sum(Decimal(str(e["tar"])) for e in entries if e["name"] in weights)
    ach_total = (ta / tt * 100) if tt > 0 else Decimal('0')
    mult = get_mult(ach_total)
    m_pay = (mid * mult).quantize(Decimal('0.01'), ROUND_HALF_UP)
    for e in entries:
        w = Decimal(str(weights.get(e["name"], 0))) / 100
        if w == 0: continue
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        pct = (a / t * 100) if t > 0 else Decimal('0')
        sc = (mid * w) if pct >= 100 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {pct:>7.1f}% | R{sc:>11,.2f}")
    tot = max(sum_seg, m_pay) if logic == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "sum_seg": sum_seg, "m_pay": m_pay, "tot": tot, "mult": mult, "ach": ach_total}

# --- UI SETUP ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

if "emp_name" not in st.session_state:
    st.session_state.update({"emp_name": "", "pers_num": "", "period": "", "midpoint_val": "0.00"})
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = 0.0, 1.0

prof_key = st.radio("Select Profile Category:", list(PROFILES.keys()), horizontal=True)
uploaded_file = st.file_uploader("Upload Statement PDF", type=['pdf'])

if uploaded_file:
    data = extract_file_data(uploaded_file)
    st.session_state["emp_name"], st.session_state["pers_num"] = data["emp_name"], data["pers_num"]
    st.session_state["period"], st.session_state["midpoint_val"] = data["period"], f"{data['midpoint']:.2f}"
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = data["segments"][s]["act"], data["segments"][s]["tar"]

st.divider()
st.subheader("1. Extract Identity & Scale Selection")
ce1, ce2, ce3 = st.columns(3)
emp_name = ce1.text_input("Name:", value=st.session_state["emp_name"])
pers_num = ce2.text_input("Personnel #:", value=st.session_state["pers_num"])
period_str = ce3.text_input("Period:", value=st.session_state["period"])

cm1, cm3 = st.columns([1, 2])
mid_stmt_input = cm1.text_input("Target Commission (Statement):", value=st.session_state["midpoint_val"])
scale_curr = cm3.selectbox("Current Midpoint (Scale Code):", list(MIDPOINTS_CURRENT.keys()))

st.subheader("2. Stream Overrides (🔴 Swap Actuals and Targets)")
entries = []
visible_segments = list(PROFILES[prof_key]["statement"].keys())
for s in visible_segments:
    cols = st.columns([3, 2, 2, 1])
    cols[0].write(f"**{s}**")
    act_v = cols[1].number_input(f"Act {s}", key=f"act_{s}", step=100.0, label_visibility="collapsed")
    tar_v = cols[2].number_input(f"Tar {s}", key=f"tar_{s}", step=100.0, label_visibility="collapsed")
    cols[3].button("🔴 Swap", key=f"btn_sw_{s}", on_click=swap_act_tar, args=(s,))
    entries.append({"name": s, "act": act_v, "tar": tar_v})

# --- SAP RECONCILIATION ---
activate_sap = st.checkbox("Reconcile with SAP Data?") if prof_key == "Standard AE / SMME" else True
if activate_sap:
    st.subheader("📊 SAP Reconciliation (Matched from Reference Tables)")
    month_match = next((m for m in SAP_DATA_25_26.keys() if m in period_str), "April")
    sap_r, sap_t = SAP_DATA_25_26.get(month_match, (0.0, 0.0))
    sc1, sc2 = st.columns(2)
    sap_r_in = sc1.number_input(f"SAP Radio Actual ({month_match})", value=sap_r)
    sap_t_in = sc2.number_input(f"SAP TV Actual ({month_match})", value=sap_t)

if st.button("RUN FULL FORENSIC COMPARISON", type="primary", use_container_width=True):
    m_stmt = Decimal(str(mid_stmt_input).replace(',', ''))
    m_curr = Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12
    weights_display = PROFILES[prof_key]["display"]

    def build_report_block(title, res, mid_applied, label):
        block = f"--- {title} ---\n"
        block += f"Midpoint Applied (Target Commission): R {mid_applied:,.2f} ({label})\n"
        block += f"Weights Applied: {weights_display} | Total Ach: {res['ach']:.2f}% | Mult: {res['mult']}x\n"
        block += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
        block += "\n".join(res["lines"]) + "\n" + "-"*81 + "\n"
        block += f"{'TOTAL SEGMENT COMMISSION:':<35} R {res['sum_seg']:>12,.2f}\n"
        block += f"{'MULTIPLIER COMMISSION:':<35} R {res['m_pay']:>12,.2f}\n"
        block += f"{'FINAL COMMISSION DUE:':<35} R {res['tot']:>12,.2f}\n\n"
        return block

    final_report = f"PERSONNEL: {pers_num} | NAME: {emp_name} | PERIOD: {period_str}\n\n"
    final_report += build_report_block("SCENARIO 1: SABC WEIGHTS (STATEMENT MIDPOINT)", run_scenario(entries, m_stmt, PROFILES[prof_key]["statement"]), m_stmt, "Statement")
    final_report += build_report_block("SCENARIO 2: SABC WEIGHTS (CURRENT SCALE)", run_scenario(entries, m_curr, PROFILES[prof_key]["statement"]), m_curr, f"Scale {scale_curr}")
    
    if prof_key == "Sports PM" and activate_sap:
        sap_entries = [e.copy() for e in entries]
        for e in sap_entries:
            if e["name"] == "Radio Sport Sponsorship": e["act"] = sap_r_in
            if e["name"] == "TV Sport Sponsorship": e["act"] = sap_t_in
        
        final_report += build_report_block("SCENARIO 6: SAP RECONCILIATION (WITH DIGITAL)", run_scenario(sap_entries, m_curr, PROFILES[prof_key]["statement"]), m_curr, f"Scale {scale_curr}")
        sap_no_dig = [e for e in sap_entries if e["name"] != "Digital"]
        final_report += build_report_block("SCENARIO 7: SAP RECONCILIATION (EXCL. DIGITAL)", run_scenario(sap_no_dig, m_curr, {"Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0}), m_curr, f"Scale {scale_curr}")

    st.code(final_report, language="text")
    
    fn = f"{pers_num}_{emp_name.replace(' ','_')}_{period_str.replace(' ','_')}.pdf"
    pdf = FPDF()
    pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0, 4, final_report.encode('latin-1','replace').decode('latin-1'))
    st.download_button("Download Report PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=fn)
