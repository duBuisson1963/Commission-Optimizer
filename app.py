import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- FULL SALARY SCALES (RESTORED COMPLETELY) ---
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}

# --- SAP DATA REPOSITORY (25/26 Financial Year) ---
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

# --- RESTORED CORE LOGIC ---
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
    is_negative = num_str.startswith('-')
    parts = num_str.split('.')
    if len(parts) > 1:
        integer_part = re.sub(r'\D', '', ''.join(parts[:-1]))
        decimal_part = re.sub(r'\D', '', parts[-1])
        final_str = f"{integer_part}.{decimal_part}"
    else:
        final_str = re.sub(r'\D', '', num_str)
    try: val = float(final_str)
    except: val = 0.0
    return -val if is_negative else val

def extract_file_data(file_obj):
    data = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        reader = PyPDF2.PdfReader(file_obj)
        pdf_text = "".join([page.extract_text() for page in reader.pages])
        norm_text = re.sub(r'\s+', ' ', pdf_text.replace('"', ''))
        date_match = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", norm_text, re.IGNORECASE)
        pers_match = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target|ZAR)", norm_text, re.IGNORECASE)
        tc_match = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", norm_text, re.IGNORECASE)
        if date_match: data["period"] = date_match.group(1).strip()
        if pers_match:
            data["pers_num"] = pers_match.group(1).strip()
            data["emp_name"] = pers_match.group(2).strip()
        if tc_match: data["midpoint"] = parse_sabc_number(tc_match.group(1))
        for s in ALL_SEGMENTS:
            s_regex = s.replace(' ', r'\s*') + r"s?"
            pattern = rf"{s_regex}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})"
            match = re.search(pattern, norm_text, re.IGNORECASE)
            if match:
                data["segments"][s]["act"] = parse_sabc_number(match.group(1))
                data["segments"][s]["tar"] = parse_sabc_number(match.group(2))
    except: pass
    return data

def run_scenario(entries, mid, w_map, logic_type='absorbed'):
    lines, sum_seg = [], Decimal('0')
    ta = sum(Decimal(str(e["act"])) for e in entries if e["name"] in w_map)
    tt = sum(Decimal(str(e["tar"])) for e in entries if e["name"] in w_map)
    overall_ach = (ta / tt * 100) if tt > 0 else Decimal('0')
    mult = get_mult(overall_ach)
    m_pay = (mid * mult).quantize(Decimal('0.01'), ROUND_HALF_UP)
    for e in entries:
        w = Decimal(str(w_map.get(e["name"], 0))) / 100
        if w == 0: continue
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        pct = (a / t * 100) if t > 0 else Decimal('0')
        sc = (mid * w) if pct >= 100 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {pct:>7.1f}% | R{sc:>11,.2f}")
    total = max(sum_seg, m_pay) if logic_type == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "sum_seg": sum_seg, "m_pay": m_pay, "tot": total, "mult": mult, "ach": overall_ach}

# --- RESTORED SWAP FUNCTION ---
def swap_act_tar(seg):
    st.session_state[f"tar_{seg}"] = st.session_state[f"act_{seg}"]
    st.session_state[f"act_{seg}"] = 0.0

# --- UI SETUP ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

if "init" not in st.session_state:
    st.session_state.update({"emp_name": "", "pers_num": "", "period": "", "init": True})
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = 0.0, 1.0

selected_profile = st.radio("Select Profile:", list(PROFILES.keys()), horizontal=True)
uploaded_file = st.file_uploader("Upload SABC Statement PDF", type=['pdf'])

if uploaded_file:
    data = extract_file_data(uploaded_file)
    st.session_state["emp_name"] = data["emp_name"]
    st.session_state["pers_num"] = data["pers_num"]
    st.session_state["period"] = data["period"]
    st.session_state["midpoint_val"] = f"{data['midpoint']:.2f}"
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"] = data["segments"][s]["act"]
        st.session_state[f"tar_{s}"] = data["segments"][s]["tar"]

st.divider()
st.subheader("Employee Details & Scale Selection")
ce1, ce2, ce3 = st.columns(3)
st.session_state["emp_name"] = ce1.text_input("Name:", value=st.session_state["emp_name"])
st.session_state["pers_num"] = ce2.text_input("Personnel #:", value=st.session_state["pers_num"])
st.session_state["period"] = ce3.text_input("Period:", value=st.session_state["period"])

cm1, cm2, cm3 = st.columns(3)
mid_stmt_input = cm1.text_input("Statement Midpoint:", value=st.session_state.get("midpoint_val", "0.00"))
scale_2021 = cm2.selectbox("2021 Scale:", list(MIDPOINTS_2021.keys()))
scale_curr = cm3.selectbox("Current Scale:", list(MIDPOINTS_CURRENT.keys()))

st.subheader("Segment Verification (🔴 Swap Actuals and Targets if SABC miscalculated)")
entries = []
visible_segments = list(PROFILES[selected_profile]["statement"].keys())
for s in visible_segments:
    cols = st.columns([3, 2, 2, 1])
    cols[0].write(f"**{s}**")
    act_val = cols[1].number_input(f"Act {s}", key=f"act_{s}", step=100.0, label_visibility="collapsed")
    tar_val = cols[2].number_input(f"Tar {s}", key=f"tar_{s}", step=100.0, label_visibility="collapsed")
    cols[3].button("🔴 Swap", key=f"btn_swap_{s}", on_click=swap_act_tar, args=(s,))
    entries.append({"name": s, "act": act_val, "tar": tar_val})

# --- SAP INTEGRATION ---
activate_sap = st.checkbox("Reconcile with SAP Data?") if selected_profile == "Standard AE / SMME" else True
if activate_sap:
    st.subheader("📊 SAP reconciliation (Matched from Monthly Reference)")
    month_match = next((m for m in SAP_DATA_25_26.keys() if m in st.session_state["period"]), "April")
    sap_r, sap_t = SAP_DATA_25_26.get(month_match, (0.0, 0.0))
    sc1, sc2 = st.columns(2)
    final_sap_rad = sc1.number_input(f"SAP Radio Actual ({month_match})", value=sap_r)
    final_sap_tv = sc2.number_input(f"SAP TV Actual ({month_match})", value=sap_t)

if st.button("RUN FULL FORENSIC COMPARISON", type="primary", use_container_width=True):
    mid_manual = Decimal(str(mid_stmt_input).replace(',', ''))
    mid_2021 = Decimal(str(MIDPOINTS_2021[scale_2021])) / 12
    mid_curr = Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12
    
    def build_report_block(title, res):
        block = f"--- {title} ---\n"
        block += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
        block += "\n".join(res["lines"]) + "\n" + "-"*81 + "\n"
        block += f"{'TOTAL SEGMENT COMMISSION:':<35} R {res['sum_seg']:>12,.2f}\n"
        block += f"{'MULTIPLIER PAYOUT (' + str(res['mult']) + 'x):':<35} R {res['m_pay']:>12,.2f}\n"
        block += f"{'FINAL COMMISSION DUE:':<35} R {res['tot']:>12,.2f}\n\n"
        return block

    report = f"FORENSIC AUDIT FOR: {st.session_state['emp_name']} ({st.session_state['pers_num']})\nPERIOD: {st.session_state['period']}\n\n"
    report += build_report_block("SCENARIO 1: SABC WEIGHTS (STATEMENT MIDPOINT)", run_scenario(entries, mid_manual, PROFILES[selected_profile]["statement"]))
    report += build_report_block("SCENARIO 2: SABC WEIGHTS (CURRENT SCALE)", run_scenario(entries, mid_curr, PROFILES[selected_profile]["statement"]))
    report += build_report_block("SCENARIO 5: POLICY WEIGHTS (CURRENT SCALE)", run_scenario(entries, mid_curr, PROFILES[selected_profile]["policy"], 'additive'))

    if selected_profile == "Sports PM" and activate_sap:
        sap_entries = [e.copy() for e in entries]
        for e in sap_entries:
            if e["name"] == "Radio Sport Sponsorship": e["act"] = final_sap_rad
            if e["name"] == "TV Sport Sponsorship": e["act"] = final_sap_tv
        
        report += build_report_block("SCENARIO 6: SAP RECONCILIATION (WITH DIGITAL)", run_scenario(sap_entries, mid_curr, PROFILES[selected_profile]["statement"]))
        sap_no_dig = [e for e in sap_entries if e["name"] != "Digital"]
        report += build_report_block("SCENARIO 7: SAP RECONCILIATION (EXCL. DIGITAL)", run_scenario(sap_no_dig, mid_curr, {"Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0}))

    st.code(report, language="text")
    
    # Filename: [Personnel]_[Name]_[Period].pdf
    safe_name = st.session_state["emp_name"].replace(" ", "_")
    safe_per = st.session_state["period"].replace(" ", "_")
    final_filename = f"{st.session_state['pers_num']}_{safe_name}_{safe_per}.pdf"
    
    pdf = FPDF()
    pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0, 4, report.encode('latin-1','replace').decode('latin-1'))
    st.download_button("Download Forensic PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=final_filename)
