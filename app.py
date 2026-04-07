import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- PROFILE WEIGHTS (ORIGINAL) ---
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

# --- SAP DATA REPOSITORY (NEW) ---
SAP_DATA_25_26 = {
    "April": (1994172.36, 4413357.92), "May": (1695579.59, 10031033.78), "June": (2458550.76, 6796250.05),
    "July": (1472644.74, 8553218.60), "August": (3458607.79, 11862475.53), "September": (2348743.96, 5387932.09),
    "October": (3120609.85, 17508431.93), "November": (4015248.49, 14155035.46), "December": (7851158.14, 20839700.17),
    "January": (2670369.08, 13925350.09), "February": (2334959.23, 11571852.77), "March": (2426110.27, 4731844.09)
}

# --- SALARY SCALES (ORIGINAL) ---
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}

ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- ORIGINAL CORE LOGIC FUNCTIONS ---
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

# --- ORIGINAL SPORT LOGIC (INCL. DUAL REPORTING) ---
def run_alt_sports_with_digital(entries, target_commission):
    lines = []
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))
    act_dig = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Digital"), Decimal('0'))
    tar_dig = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Digital"), Decimal('1'))
    pct_tv, pct_rad, pct_dig = (act_tv/tar_tv)*100, (act_rad/tar_rad)*100, (act_dig/tar_dig)*100
    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% | (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% | (Pooled)")
    lines.append(f"{'Digital':<23} R{act_dig:>11,.2f} | R{tar_dig:>11,.2f} | {pct_dig:>7.1f}% | (Pooled)")
    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)
    if ach_count == 0: return Decimal('0'), "MODE C", "0.00x", lines
    elif ach_count == 1: return target_commission * (Decimal('0.6') if pct_tv >= 100 else Decimal('0.3')), "MODE B", "Fallback", lines
    else:
        weighted_pct = (Decimal('0.6') * min(pct_tv, 180)) + (Decimal('0.3') * min(pct_rad, 180)) + (Decimal('0.1') * min(pct_dig, 180))
        mult = get_mult(weighted_pct)
        return target_commission * mult, f"MODE A ({weighted_pct:.1f}%)", f"{mult}x", lines

def run_alt_sports_exclude_digital(entries, target_commission):
    lines = []
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))
    pct_tv, pct_rad = (act_tv/tar_tv)*100, (act_rad/tar_rad)*100
    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% | (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% | (Pooled)")
    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)
    if ach_count == 0: return Decimal('0'), "MODE C", "0.00x", lines
    elif ach_count == 1: return target_commission * (Decimal('0.6') if pct_tv >= 100 else Decimal('0.3')), "MODE B", "Fallback", lines
    else:
        weighted_pct = ((Decimal('0.6') * min(pct_tv, 180)) + (Decimal('0.3') * min(pct_rad, 180))) / Decimal('0.9')
        mult = get_mult(weighted_pct)
        return target_commission * mult, f"MODE A ({weighted_pct:.1f}%)", f"{mult}x", lines

# --- ORIGINAL EXTRACTION ENGINE ---
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = num_str.strip().replace('"', '')
    is_negative = num_str.startswith('-')
    parts = num_str.split('.')
    if len(parts) > 1:
        integer_part = re.sub(r'\D', '', ''.join(parts[:-1]))
        decimal_part = re.sub(r'\D', '', parts[-1])
        final_str = f"{integer_part}.{decimal_part}"
    else:
        final_str = re.sub(r'\D', '', num_str)
    val = float(final_str) if final_str else 0.0
    return -val if is_negative else val

def extract_file_data(file_obj):
    data = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "sabc_target": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        reader = PyPDF2.PdfReader(file_obj)
        pdf_text = ""
        for page in reader.pages: pdf_text += page.extract_text() + "\n"
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

# --- UI SETUP ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

if "emp_name" not in st.session_state: st.session_state.update({"emp_name": "", "pers_num": "", "period": ""})
for s in ALL_SEGMENTS:
    if f"act_{s}" not in st.session_state: st.session_state[f"act_{s}"] = 0.0
    if f"tar_{s}" not in st.session_state: st.session_state[f"tar_{s}"] = 1.0

selected_profile = st.radio("Select Profile:", ["Standard AE / SMME", "Sports PM"], horizontal=True)

uploaded_file = st.file_uploader("Upload Single SABC Statement (PDF)", type=['pdf'])

if uploaded_file:
    data = extract_file_data(uploaded_file)
    st.subheader("📝 Verify Extracted Identity")
    c1, c2, c3 = st.columns(3)
    st.session_state["emp_name"] = c1.text_input("Name:", value=data["emp_name"])
    st.session_state["pers_num"] = c2.text_input("Personnel #:", value=data["pers_num"])
    st.session_state["period"] = c3.text_input("Period:", value=data["period"])
    
    # Fill Original Calculator text boxes
    if data["midpoint"] > 0: st.session_state["midpoint_input_val"] = f"{data['midpoint']:.2f}"
    for s in ALL_SEGMENTS:
        st.session_state[f"act_{s}"] = data["segments"][s]["act"]
        st.session_state[f"tar_{s}"] = data["segments"][s]["tar"]

st.divider()

col_m1, col_m2 = st.columns(2)
with col_m1:
    midpoint_input = st.text_input("Target Commission (Statement):", key="midpoint_input_val", value="0.00")
    scale_curr = st.selectbox("Current Midpoints (Scale Code):", list(MIDPOINTS_CURRENT.keys()))
with col_m2:
    if selected_profile == "Standard AE / SMME":
        activate_sap = st.checkbox("Activate SAP data reconciliation for SMME?")
    else: activate_sap = True

# --- CALCULATOR ENTRIES ---
entries = []
st.subheader("Segment Verification")
visible_segments = ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if selected_profile == "Sports PM" else ALL_SEGMENTS
for s in visible_segments:
    ca, cb, cc = st.columns([3, 2, 2])
    ca.write(s)
    act = cb.number_input(f"Act {s}", key=f"act_{s}", step=100.0)
    tar = cc.number_input(f"Tar {s}", key=f"tar_{s}", step=100.0)
    entries.append({"name": s, "act": act, "tar": tar})

# --- SAP RECONCILIATION BLOCK ---
if activate_sap:
    st.subheader("📊 SAP Reconciliation (Matched from Screenshot)")
    ext_month = next((m for m in SAP_DATA_25_26.keys() if m in st.session_state["period"]), "April")
    sap_rad_val, sap_tv_val = SAP_DATA_25_26.get(ext_month, (0.0, 0.0))
    cs1, cs2 = st.columns(2)
    final_sap_rad = cs1.number_input(f"SAP Radio ({ext_month}):", value=sap_rad_val)
    final_sap_tv = cs2.number_input(f"SAP TV ({ext_month}):", value=sap_tv_val)
    
    # Apply SAP to entries for calculation
    for e in entries:
        if e["name"] == "Radio Sport Sponsorship": e["act"] = final_sap_rad
        if e["name"] == "TV Sport Sponsorship": e["act"] = final_sap_tv

# --- EXECUTION ---
if st.button("RUN FORENSIC COMPARISON", type="primary", use_container_width=True):
    mid_manual = Decimal(str(midpoint_input).replace(',', ''))
    mid_curr = (Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
    
    if selected_profile == "Sports PM":
        res_with = run_alt_sports_with_digital(entries, mid_manual)
        res_excl = run_alt_sports_exclude_digital(entries, mid_manual)
        
        c_out1, c_out2 = st.columns(2)
        with c_out1:
            st.info(f"Scenario A: {res_with[1]}\nPayout: R {res_with[0]:,.2f}")
            st.code("\n".join(res_with[3]))
        with c_out2:
            st.warning(f"Scenario B: {res_excl[1]}\nPayout: R {res_excl[0]:,.2f}")
            st.code("\n".join(res_excl[3]))

    # Filename Generation
    safe_name = st.session_state["emp_name"].strip().replace(' ', '_') or "Employee"
    safe_pers = st.session_state["pers_num"].strip() or "0000"
    safe_per = st.session_state["period"].strip().replace(' ', '_') or "Period"
    final_filename = f"{safe_pers}_{safe_name}_{safe_per}.pdf"
    
    # PDF generation logic remains original...
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Courier", size=8)
    pdf.cell(0, 10, f"Forensic Report: {final_filename}", ln=1)
    st.download_button(f"📄 Download: {final_filename}", data=pdf.output(dest='S').encode('latin-1'), file_name=final_filename)
