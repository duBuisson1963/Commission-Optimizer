import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- DATA REPOSITORIES ---
PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0, "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "policy": {"TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0, "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "display_stmt": "45/24/6", "display_pol": "40/30/10"
    },
    "Sports PM": {
        "statement": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0, "Radio Classic": 0.0, "TV Classic": 0.0, "TV Sponsorship": 0.0, "Radio Sponsorship": 0.0},
        "policy": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0, "Radio Classic": 0.0, "TV Classic": 0.0, "TV Sponsorship": 0.0, "Radio Sponsorship": 0.0},
        "display_stmt": "10/30/60", "display_pol": "10/30/60"
    }
}

SAP_DATA_25_26 = {
    "April": (1994172.36, 4413357.92), "May": (1695579.59, 10031033.78), "June": (2458550.76, 6796250.05),
    "July": (1472644.74, 8553218.60), "August": (3458607.79, 11862475.53), "September": (2348743.96, 5387932.09),
    "October": (3120609.85, 17508431.93), "November": (4015248.49, 14155035.46), "December": (7851158.14, 20839700.17),
    "January": (2670369.08, 13925350.09), "February": (2334959.23, 11571852.77), "March": (2426110.27, 4731844.09)
}

MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316}
MIDPOINTS_CURRENT = {'110A': 3459277, '110B': 2767421, '115A': 2213937, '115B': 1844948, '120': 1724250, '125': 1228406, '130': 944928, '401': 435116, '402': 342045}
ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- CORE LOGIC ---
def get_mult(score):
    if score < 100: return Decimal('0.00')
    if score == 100: return Decimal('0.50')
    if score <= 120: return Decimal('1.00')
    if score <= 150: return Decimal('2.10')
    if score <= 180: return Decimal('4.10')
    return Decimal('6.20')

def run_scenario(entries, mid, w_map, logic_type):
    lines, sum_seg = [], Decimal('0')
    ta = sum(Decimal(str(e["act"])) for e in entries)
    tt = sum(Decimal(str(e["tar"])) for e in entries)
    overall_ach = (ta / tt * 100) if tt > 0 else Decimal('0')
    mult = get_mult(overall_ach)
    m_pay = (mid * mult).quantize(Decimal('0.01'), ROUND_HALF_UP)

    for e in entries:
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        w = Decimal(str(w_map.get(e["name"], 0))) / 100
        if w == Decimal('0'): continue
        ach = (a / t * 100) if t > 0 else Decimal('0')
        sc = (mid * w) if ach >= 100 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {ach:>7.1f}% | R{sc:>11,.2f}")
    
    total = max(sum_seg, m_pay) if logic_type == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "sum_seg": sum_seg, "m_pay": m_pay, "tot": total, "mult": mult, "ach": overall_ach}

def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = num_str.strip().replace('"', '')
    is_neg = num_str.startswith('-')
    clean = "".join(filter(lambda x: x.isdigit() or x == '.', num_str))
    val = float(clean) if clean else 0.0
    return -val if is_neg else val

def extract_file_data(file_obj):
    data = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        reader = PyPDF2.PdfReader(file_obj)
        text = " ".join([p.extract_text() for p in reader.pages])
        norm = re.sub(r'\s+', ' ', text)
        d_m = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", norm, re.I)
        p_m = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target)", norm, re.I)
        t_m = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", norm, re.I)
        if d_m: data["period"] = d_m.group(1).strip()
        if p_m: data["pers_num"], data["emp_name"] = p_m.group(1), p_m.group(2).strip()
        if t_m: data["midpoint"] = parse_sabc_number(t_m.group(1))
        for s in ALL_SEGMENTS:
            reg = s.replace(' ', r'\s*') + r"s?"
            m = re.search(rf"{reg}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})", norm, re.I)
            if m: data["segments"][s]["act"], data["segments"][s]["tar"] = parse_sabc_number(m.group(1)), parse_sabc_number(m.group(2))
    except: pass
    return data

# --- UI ---
st.title("BEMAWU Forensic Multi-Scenario Auditor")

if "init" not in st.session_state:
    st.session_state.update({"emp_name": "", "pers_num": "", "period": "", "init": True})
    for s in ALL_SEGMENTS: st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = 0.0, 1.0

prof_key = st.radio("Auditing Profile:", list(PROFILES.keys()), horizontal=True)

up_file = st.file_uploader("Upload SABC PDF", type=['pdf'])
if up_file:
    d = extract_file_data(up_file)
    st.session_state["emp_name"] = st.text_input("Confirm Name:", value=d["emp_name"])
    st.session_state["pers_num"] = st.text_input("Confirm Personnel #:", value=d["pers_num"])
    st.session_state["period"] = st.text_input("Confirm Period:", value=d["period"])
    st.session_state["mid_stmt"] = d["midpoint"]
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = d["segments"][s]["act"], d["segments"][s]["tar"]

st.divider()
c1, c2, c3 = st.columns(3)
mid_stmt_val = c1.number_input("Statement Midpoint:", value=st.session_state.get("mid_stmt", 0.0))
scale_2021 = c2.selectbox("2021 Scale:", list(MIDPOINTS_2021.keys()))
scale_curr = c3.selectbox("Current Scale:", list(MIDPOINTS_CURRENT.keys()))

st.subheader("Calculator Inputs (Verify Stream Data)")
entries = []
for s in (["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if prof_key == "Sports PM" else ALL_SEGMENTS):
    cols = st.columns([3, 2, 2])
    cols[0].write(f"**{s}**")
    a = cols[1].number_input("Actual", key=f"act_{s}", step=100.0)
    t = cols[2].number_input("Target", key=f"tar_{s}", step=100.0)
    entries.append({"name": s, "act": a, "tar": t})

# SAP Logic
sap_act = st.checkbox("Activate SAP Comparison?")
if sap_act:
    month = next((m for m in SAP_DATA_25_26.keys() if m in st.session_state["period"]), "April")
    r_sap, t_sap = SAP_DATA_25_26.get(month, (0.0, 0.0))
    sc1, sc2 = st.columns(2)
    sap_r = sc1.number_input(f"SAP Radio ({month})", value=r_sap)
    sap_t = sc2.number_input(f"SAP TV ({month})", value=t_sap)

# --- REPORT GENERATION ---
if st.button("RUN FULL FORENSIC REPORT", type="primary", use_container_width=True):
    m_stmt = Decimal(str(mid_stmt_val))
    m_2021 = Decimal(str(MIDPOINTS_2021[scale_2021])) / 12
    m_curr = Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12

    def build_block(title, res):
        b = f"--- {title} ---\n"
        b += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
        b += "\n".join(res["lines"]) + "\n" + "-"*81 + "\n"
        b += f"{'TOTAL SEGMENT COMM:':<35} R {res['sum_seg']:>12,.2f}\n"
        b += f"{'MULTIPLIER (' + str(res['mult']) + 'x):':<35} R {res['m_pay']:>12,.2f}\n"
        b += f"{'TOTAL DUE:':<35} R {res['tot']:>12,.2f}\n\n"
        return b

    # Standard Scenarios
    rep = f"FORENSIC AUDIT: {st.session_state['emp_name']} ({st.session_state['pers_num']})\nPERIOD: {st.session_state['period']}\n\n"
    
    s1 = run_scenario(entries, m_stmt, PROFILES[prof_key]["statement"], 'absorbed')
    rep += build_block("SCENARIO 1: STATEMENT WEIGHTS (STMT MIDPOINT)", s1)
    
    s2 = run_scenario(entries, m_curr, PROFILES[prof_key]["statement"], 'absorbed')
    rep += build_block("SCENARIO 2: STATEMENT WEIGHTS (CURRENT SCALE)", s2)

    # SAP Scenarios (Sports Only)
    if prof_key == "Sports PM" and sap_act:
        sap_entries = [e.copy() for e in entries]
        for e in sap_entries:
            if e["name"] == "Radio Sport Sponsorship": e["act"] = sap_r
            if e["name"] == "TV Sport Sponsorship": e["act"] = sap_t
        
        # Scen 6: SAP With Digital
        s6 = run_scenario(sap_entries, m_curr, PROFILES[prof_key]["statement"], 'absorbed')
        rep += build_block("SCENARIO 6: SAP DATA @ CURRENT SCALE (INCL. DIGITAL)", s6)
        
        # Scen 7: SAP Excl Digital
        sap_no_dig = [e for e in sap_entries if e["name"] != "Digital"]
        s7 = run_scenario(sap_no_dig, m_curr, {"Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0}, 'absorbed')
        rep += build_block("SCENARIO 7: SAP DATA @ CURRENT SCALE (EXCL. DIGITAL)", s7)

    st.code(rep)
    
    f_name = f"{st.session_state['pers_num']}_{st.session_state['emp_name'].replace(' ','_')}_{st.session_state['period'].replace(' ','_')}.pdf"
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=8)
    pdf.multi_cell(0, 4, rep.encode('latin-1', 'replace').decode('latin-1'))
    st.download_button("Download Full Audit PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=f_name)
