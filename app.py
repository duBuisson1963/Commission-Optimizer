import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- CONFIG & PROFILE WEIGHTS ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")

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

# --- SAP DATA REPOSITORY (25/26 Financial Year) ---
SAP_DATA_25_26 = {
    "April": (1994172.36, 4413357.92),
    "May": (1695579.59, 10031033.78),
    "June": (2458550.76, 6796250.05),
    "July": (1472644.74, 8553218.60),
    "August": (3458607.79, 11862475.53),
    "September": (2348743.96, 5387932.09),
    "October": (3120609.85, 17508431.93),
    "November": (4015248.49, 14155035.46),
    "December": (7851158.14, 20839700.17),
    "January": (2670369.08, 13925350.09),
    "February": (2334959.23, 11571852.77),
    "March": (2426110.27, 4731844.09)
}

# --- SALARY SCALES ---
MIDPOINTS_CURRENT = {'110A': 3459277, '110B': 2767421, '115A': 2213937, '115B': 1844948, '120': 1724250, '125': 1228406, '130': 944928, '401': 435116, '402': 342045}
ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- HELPER FUNCTIONS ---
def get_mult(score):
    if score < 100: return Decimal('0.00')
    if score == 100: return Decimal('0.50')
    if score <= 120: return Decimal('1.00')
    if score <= 150: return Decimal('2.10')
    if score <= 180: return Decimal('4.10')
    return Decimal('6.20')

def run_scenario(entries, mid, w_map, m_pay, logic_type):
    lines, sum_seg = [], Decimal('0')
    for e in entries:
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        w = Decimal(str(w_map.get(e["name"], 0))) / 100
        if w == Decimal('0'): continue
        ach = a / t if t > 0 else Decimal('0')
        sc = (mid * w) if ach >= 1.0 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {ach*100:>7.1f}% | R{sc:>11,.2f}")
    total = max(sum_seg, m_pay) if logic_type == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "sum_seg": sum_seg, "tot": total}

# --- DUAL SPORT LOGIC ---
def run_alt_sports_with_digital(entries, target_commission):
    lines = []
    # Simplified extraction from entries list for pooled calculation
    act_vals = {e["name"]: Decimal(str(e["act"])) for e in entries}
    tar_vals = {e["name"]: Decimal(str(e["tar"])) for e in entries}
    
    # TV (60%), Radio (30%), Digital (10%)
    pct_tv = (act_vals.get("TV Sport Sponsorship", 0) / tar_vals.get("TV Sport Sponsorship", 1)) * 100
    pct_rad = (act_vals.get("Radio Sport Sponsorship", 0) / tar_vals.get("Radio Sport Sponsorship", 1)) * 100
    pct_dig = (act_vals.get("Digital", 0) / tar_vals.get("Digital", 1)) * 100

    weighted_pct = (Decimal('0.60') * min(pct_tv, 180)) + (Decimal('0.30') * min(pct_rad, 180)) + (Decimal('0.10') * min(pct_dig, 180))
    mult = get_mult(weighted_pct)
    
    for k in ["TV Sport Sponsorship", "Radio Sport Sponsorship", "Digital"]:
        lines.append(f"{k:<23} R{act_vals.get(k,0):>11,.2f} | R{tar_vals.get(k,1):>11,.2f} | (Pooled)")
    
    return target_commission * mult, f"With Digital ({weighted_pct:.1f}%)", f"{mult}x", lines

def run_alt_sports_exclude_digital(entries, target_commission):
    lines = []
    act_vals = {e["name"]: Decimal(str(e["act"])) for e in entries}
    tar_vals = {e["name"]: Decimal(str(e["tar"])) for e in entries}
    
    pct_tv = (act_vals.get("TV Sport Sponsorship", 0) / tar_vals.get("TV Sport Sponsorship", 1)) * 100
    pct_rad = (act_vals.get("Radio Sport Sponsorship", 0) / tar_vals.get("Radio Sport Sponsorship", 1)) * 100

    # Re-weight: TV (60/90), Radio (30/90)
    weighted_pct = ((Decimal('0.60') * min(pct_tv, 180)) + (Decimal('0.30') * min(pct_rad, 180))) / Decimal('0.90')
    mult = get_mult(weighted_pct)
    
    for k in ["TV Sport Sponsorship", "Radio Sport Sponsorship"]:
        lines.append(f"{k:<23} R{act_vals.get(k,0):>11,.2f} | R{tar_vals.get(k,1):>11,.2f} | (Pooled)")
    
    return target_commission * mult, f"Excl. Digital ({weighted_pct:.1f}%)", f"{mult}x", lines

# --- PARSING ENGINE ---
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = num_str.strip().replace('"', '')
    is_negative = num_str.startswith('-')
    clean = re.sub(r'[^\d.]', '', num_str)
    try: return -float(clean) if is_negative else float(clean)
    except: return 0.0

def extract_file_data(file_obj):
    data = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    
    try:
        reader = PyPDF2.PdfReader(file_obj)
        text = ""
        for page in reader.pages: text += page.extract_text() + "\n"
        norm_text = re.sub(r'\s+', ' ', text)
        
        date_match = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", norm_text, re.IGNORECASE)
        pers_match = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target|ZAR)", norm_text, re.IGNORECASE)
        tc_match = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", norm_text, re.IGNORECASE)

        if date_match: data["period"] = date_match.group(1).strip()
        if pers_match:
            data["pers_num"] = pers_match.group(1).strip()
            data["emp_name"] = pers_match.group(2).strip()
        if tc_match: data["midpoint"] = parse_sabc_number(tc_match.group(1))

        for s in ALL_SEGMENTS:
            pattern = rf"{s.replace(' ', r'\s*')}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})"
            match = re.search(pattern, norm_text, re.IGNORECASE)
            if match:
                data["segments"][s]["act"] = parse_sabc_number(match.group(1))
                data["segments"][s]["tar"] = parse_sabc_number(match.group(2))
    except: pass
    return data

# --- APP UI ---
st.title("BEMAWU Dual-Profile Forensic Simulator")

# Session State Initialization
if "emp_name" not in st.session_state: st.session_state.update({"emp_name": "", "pers_num": "", "period": ""})

selected_profile = st.radio("Select Profile:", ["Standard AE / SMME", "Sports PM"], horizontal=True)

uploaded_file = st.file_uploader("Upload SABC Statement (PDF)", type=['pdf'])

if uploaded_file:
    data = extract_file_data(uploaded_file)
    
    st.subheader("📝 Verify & Rectify Extracted Details")
    c_v1, c_v2, c_v3 = st.columns(3)
    st.session_state["emp_name"] = c_v1.text_input("Employee Name:", value=data["emp_name"])
    st.session_state["pers_num"] = c_v2.text_input("Personnel Number:", value=data["pers_num"])
    st.session_state["period"] = c_v3.text_input("Statement Period:", value=data["period"])
    
    st.divider()

    # Midpoint Settings
    col_m1, col_m2 = st.columns(2)
    mid_stmt = col_m1.number_input("Statement Midpoint:", value=float(data["midpoint"]))
    scale_key = col_m2.selectbox("Correct Scale (Current):", list(MIDPOINTS_CURRENT.keys()))
    mid_curr = Decimal(str(MIDPOINTS_CURRENT[scale_key])) / 12

    # Segment Inputs
    entries = []
    st.write("### Segment Values")
    for s in ALL_SEGMENTS:
        if selected_profile == "Sports PM" and s not in ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"]:
            continue
        c1, c2, c3 = st.columns([3, 2, 2])
        act = c2.number_input(f"{s} Actual", value=data["segments"][s]["act"], key=f"act_{s}")
        tar = c3.number_input(f"{s} Target", value=data["segments"][s]["tar"], key=f"tar_{s}")
        entries.append({"name": s, "act": act, "tar": tar})

    # SAP Integration Logic
    activate_sap = False
    if selected_profile == "Sports PM":
        activate_sap = True
    else:
        activate_sap = st.checkbox("Activate SAP data reconciliation for SMME profile?")

    if activate_sap:
        st.subheader("📊 SAP Reconciliation")
        ext_month = next((m for m in SAP_DATA_25_26.keys() if m in st.session_state["period"]), "April")
        sap_rad_def, sap_tv_def = SAP_DATA_25_26.get(ext_month, (0.0, 0.0))
        
        c_s1, c_s2 = st.columns(2)
        sap_rad = c_s1.number_input(f"SAP Radio Actual ({ext_month}):", value=sap_rad_def)
        sap_tv = c_s2.number_input(f"SAP TV Actual ({ext_month}):", value=sap_tv_def)
        
        # Override entries with SAP values for the comparison
        for e in entries:
            if e["name"] == "Radio Sport Sponsorship": e["act"] = sap_rad
            if e["name"] == "TV Sport Sponsorship": e["act"] = sap_tv

    if st.button("RUN FORENSIC AUDIT", type="primary"):
        mid_m = Decimal(str(mid_stmt))
        mid_c = mid_curr.quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        # Reports
        if selected_profile == "Sports PM":
            res_w, mod_w, mul_w, lines_w = run_alt_sports_with_digital(entries, mid_m)
            res_no, mod_no, mul_no, lines_no = run_alt_sports_exclude_digital(entries, mid_m)
            
            out_c1, out_c2 = st.columns(2)
            out_c1.info(f"**Scenario A: {mod_w}**\nPayout: R {res_w:,.2f}")
            out_c2.warning(f"**Scenario B: {mod_no}**\nPayout: R {res_no:,.2f}")
        
        # Filename Generation
        safe_name = st.session_state["emp_name"].replace(" ", "_")
        safe_per = st.session_state["period"].replace(" ", "_")
        filename = f"{st.session_state['pers_num']}_{safe_name}_{safe_per}.pdf"
        
        # PDF Generation (Simple Text Dump)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=10)
        pdf.cell(200, 10, txt=f"FORENSIC AUDIT: {st.session_state['emp_name']}", ln=1, align='C')
        pdf.multi_cell(0, 5, f"Personnel: {st.session_state['pers_num']}\nPeriod: {st.session_state['period']}\nFilename: {filename}")
        
        st.download_button("Download Report PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=filename)
