import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- FULL MIDPOINT REPOSITORY ---
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}

SAP_DATA_25_26 = {
    "April": (1994172.36, 4413357.92), "May": (1695579.59, 10031033.78), "June": (2458550.76, 6796250.05),
    "July": (1472644.74, 8553218.60), "August": (3458607.79, 11862475.53), "September": (2348743.96, 5387932.09),
    "October": (3120609.85, 17508431.93), "November": (4015248.49, 14155035.46), "December": (7851158.14, 20839700.17),
    "January": (2670369.08, 13925350.09), "February": (2334959.23, 11571852.77), "March": (2426110.27, 4731844.09)
}

PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0, "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "policy": {"TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0, "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5}
    },
    "Sports PM": {
        "statement": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "policy": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0}
    }
}

ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- CORE LOGIC ---
def get_mult(score):
    if score < 100: return Decimal('0.00')
    if score == 100: return Decimal('0.50')
    if score <= 120: return Decimal('1.00')
    if score <= 150: return Decimal('2.10')
    if score <= 180: return Decimal('4.10')
    return Decimal('6.20')

def parse_sabc_num(s):
    if not s: return 0.0
    s = str(s).strip().replace('"', '')
    neg = s.startswith('-')
    parts = s.split('.')
    integer = re.sub(r'\D', '', ''.join(parts[:-1])) if len(parts) > 1 else re.sub(r'\D', '', s)
    decimal = re.sub(r'\D', '', parts[-1]) if len(parts) > 1 else "00"
    try: val = float(f"{integer}.{decimal}")
    except: val = 0.0
    return -val if neg else val

def extract_data(f):
    d = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: d["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        reader = PyPDF2.PdfReader(f)
        text = " ".join([p.extract_text() for p in reader.pages])
        norm = re.sub(r'\s+', ' ', text)
        dm = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", norm, re.I)
        pm = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target|ZAR)", norm, re.I)
        tm = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", norm, re.I)
        if dm: d["period"] = dm.group(1).strip()
        if pm: d["pers_num"], d["emp_name"] = pm.group(1).strip(), pm.group(2).strip()
        if tm: d["midpoint"] = parse_sabc_num(tm.group(1))
        for s in ALL_SEGMENTS:
            reg = s.replace(' ', r'\s*') + r"s?"
            m = re.search(rf"{reg}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})", norm, re.I)
            if m: d["segments"][s]["act"], d["segments"][s]["tar"] = parse_sabc_num(m.group(1)), parse_sabc_num(m.group(2))
    except: pass
    return d

def run_calc(entries, mid, weights, logic='absorbed'):
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
        pct = (a/t*100) if t > 0 else Decimal('0')
        sc = (mid * w) if pct >= 100 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {pct:>7.1f}% | R{sc:>11,.2f}")
    tot = max(sum_seg, m_pay) if logic == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "sum_seg": sum_seg, "m_pay": m_pay, "tot": tot, "mult": mult, "ach": ach_total}

# --- SWAP LOGIC ---
def swap_act_tar(seg):
    st.session_state[f"tar_{seg}"] = st.session_state[f"act_{seg}"]
    st.session_state[f"act_{seg}"] = 0.0

# --- UI SETUP ---
st.title("BEMAWU Dual-Profile Forensic Auditor")

if "emp_name" not in st.session_state:
    st.session_state.update({"emp_name": "", "pers_num": "", "period": ""})
    for s in ALL_SEGMENTS: 
        st.session_state[f"act_{s}"] = 0.0
        st.session_state[f"tar_{s}"] = 1.0

prof_key = st.radio("Auditing Profile:", list(PROFILES.keys()), horizontal=True)

up_file = st.file_uploader("Upload SABC Statement PDF", type=['pdf'])
if up_file:
    data = extract_data(up_file)
    st.session_state["emp_name"] = data["emp_name"]
    st.session_state["pers_num"] = data["pers_num"]
    st.session_state["period"] = data["period"]
    st.session_state["mid_input_val"] = f"{data['midpoint']:.2f}"
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"] = data["segments"][s]["act"]
        st.session_state[f"tar_{s}"] = data["segments"][s]["tar"]

st.divider()
st.subheader("Employee & Scale Details")
ce1, ce2, ce3 = st.columns(3)
st.session_state["emp_name"] = ce1.text_input("Confirm Name:", value=st.session_state["emp_name"])
st.session_state["pers_num"] = ce2.text_input("Confirm Personnel #:", value=st.session_state["pers_num"])
st.session_state["period"] = ce3.text_input("Confirm Period:", value=st.session_state["period"])

cm1, cm2, cm3 = st.columns(3)
mid_stmt = Decimal(cm1.text_input("Statement Midpoint:", value=st.session_state.get("mid_input_val", "0.00")).replace(',',''))
sc_2021 = cm2.selectbox("2021 Scale:", list(MIDPOINTS_2021.keys()))
sc_curr = cm3.selectbox("Current Scale:", list(MIDPOINTS_CURRENT.keys()))

st.subheader("Calculator Inputs & Override")
entries = []
visible_segments = list(PROFILES[prof_key]["statement"].keys())
for s in visible_segments:
    cols = st.columns([3, 2, 2, 1])
    cols[0].write(f"**{s}**")
    a = cols[1].number_input(f"Act {s}", key=f"act_{s}", step=1000.0, label_visibility="collapsed")
    t = cols[2].number_input(f"Tar {s}", key=f"tar_{s}", step=1000.0, label_visibility="collapsed")
    cols[3].button("🔴 Swap", key=f"swap_{s}", on_click=swap_act_tar, args=(s,))
    entries.append({"name": s, "act": a, "tar": t})

sap_active = st.checkbox("Reconcile with SAP Data?") if prof_key == "Standard AE / SMME" else True
if sap_active:
    st.subheader("📊 SAP reconciliation (Matched from Monthly Reference)")
    month = next((m for m in SAP_DATA_25_26.keys() if m in st.session_state["period"]), "April")
    r_sap, t_sap = SAP_DATA_25_26.get(month, (0.0, 0.0))
    sc1, sc2 = st.columns(2)
    sap_r = sc1.number_input(f"SAP Radio Actual ({month})", value=r_sap)
    sap_t = sc2.number_input(f"SAP TV Actual ({month})", value=t_sap)

if st.button("RUN FULL FORENSIC REPORT", type="primary", use_container_width=True):
    m_2021 = Decimal(str(MIDPOINTS_2021[sc_2021])) / 12
    m_curr = Decimal(str(MIDPOINTS_CURRENT[sc_curr])) / 12
    
    def fmt_rep(title, res):
        return f"--- {title} ---\n{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n" + "\n".join(res["lines"]) + f"\n{'-'*81}\nSEGMENT COMM: R {res['sum_seg']:>12,.2f}\nMULTIPLIER ({res['mult']}x): R {res['m_pay']:>12,.2f}\nTOTAL DUE: R {res['tot']:>12,.2f}\n\n"

    final_rep = f"PERSONNEL: {st.session_state['pers_num']} | NAME: {st.session_state['emp_name']} | PERIOD: {st.session_state['period']}\n\n"
    
    # Scenarios
    final_rep += fmt_rep("SCENARIO 1: SABC WEIGHTS (STMT MIDPOINT)", run_calc(entries, mid_stmt, PROFILES[prof_key]["statement"]))
    final_rep += fmt_rep("SCENARIO 2: SABC WEIGHTS (CURRENT SCALE)", run_calc(entries, m_curr, PROFILES[prof_key]["statement"]))
    final_rep += fmt_rep("SCENARIO 5: POLICY WEIGHTS (CURRENT SCALE)", run_calc(entries, m_curr, PROFILES[prof_key]["policy"], 'additive'))

    if prof_key == "Sports PM" and sap_active:
        sap_entries = [e.copy() for e in entries]
        for e in sap_entries:
            if e["name"] == "Radio Sport Sponsorship": e["act"] = sap_r
            if e["name"] == "TV Sport Sponsorship": e["act"] = sap_t
        
        final_rep += fmt_rep("SCENARIO 6: SAP RECONCILIATION (WITH DIGITAL)", run_calc(sap_entries, m_curr, PROFILES[prof_key]["statement"]))
        sap_no_dig = [e for e in sap_entries if e["name"] != "Digital"]
        final_rep += fmt_rep("SCENARIO 7: SAP RECONCILIATION (EXCL. DIGITAL)", run_calc(sap_no_dig, m_curr, {"Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0}))

    st.code(final_rep)
    
    # Filename: [Personnel]_[Name]_[Period].pdf
    fn = f"{st.session_state['pers_num']}_{st.session_state['emp_name'].replace(' ','_')}_{st.session_state['period'].replace(' ','_')}.pdf"
    pdf = FPDF()
    pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0, 4, final_rep.encode('latin-1','replace').decode('latin-1'))
    st.download_button("Download Forensic Report", data=pdf.output(dest='S').encode('latin-1'), file_name=fn)
