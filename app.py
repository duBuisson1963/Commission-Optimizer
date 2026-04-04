import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF

# --- PROFILE WEIGHTS ---
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

# --- SALARY SCALES (ANNUAL) ---
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}

ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

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

# --- ALTERNATIVE LOGIC ---
def run_alt_sports_with_digital(entries, target_commission):
    lines = []
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))
    act_dig = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Digital"), Decimal('0'))
    tar_dig = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Digital"), Decimal('1'))

    pct_tv = (act_tv / tar_tv) * 100 if tar_tv > 0 else Decimal('0')
    pct_rad = (act_rad / tar_rad) * 100 if tar_rad > 0 else Decimal('0')
    pct_dig = (act_dig / tar_dig) * 100 if tar_dig > 0 else Decimal('0')

    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% |   (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% |   (Pooled)")
    lines.append(f"{'Digital':<23} R{act_dig:>11,.2f} | R{tar_dig:>11,.2f} | {pct_dig:>7.1f}% |   (Pooled)")

    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)

    if ach_count == 0: return Decimal('0'), "MODE C (No Sport Targets Hit)", "0.00x", lines
    elif ach_count == 1:
        if pct_tv >= 100: return target_commission * Decimal('0.60'), "MODE B (TV Only Fallback)", "Fallback (60%)", lines
        else: return target_commission * Decimal('0.30'), "MODE B (Radio Only Fallback)", "Fallback (30%)", lines
    else:
        pct_tv_cap, pct_rad_cap, pct_dig_cap = min(pct_tv, Decimal('180')), min(pct_rad, Decimal('180')), min(pct_dig, Decimal('180'))
        weighted_pct = (Decimal('0.60') * pct_tv_cap) + (Decimal('0.30') * pct_rad_cap) + (Decimal('0.10') * pct_dig_cap)
        if weighted_pct < 100: mult = Decimal('0.00')
        elif weighted_pct <= 120: mult = Decimal('1.00')
        elif weighted_pct <= 150: mult = Decimal('2.10')
        else: mult = Decimal('4.10')
        return target_commission * mult, f"MODE A (Both Hit - {weighted_pct:.1f}% Weighted)", f"{mult}x", lines

def run_alt_sports_exclude_digital(entries, target_commission):
    lines = []
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))

    pct_tv = (act_tv / tar_tv) * 100 if tar_tv > 0 else Decimal('0')
    pct_rad = (act_rad / tar_rad) * 100 if tar_rad > 0 else Decimal('0')

    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% |   (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% |   (Pooled)")
    lines.append(f"{'Digital (EXCLUDED)':<23} R{0:>11,.2f} | R{0:>11,.2f} | {0:>7.1f}% |   (Ignored)")

    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)

    if ach_count == 0: return Decimal('0'), "MODE C (No Sport Targets Hit)", "0.00x", lines
    elif ach_count == 1:
        if pct_tv >= 100: return target_commission * Decimal('0.60'), "MODE B (TV Only Fallback)", "Fallback (60%)", lines
        else: return target_commission * Decimal('0.30'), "MODE B (Radio Only Fallback)", "Fallback (30%)", lines
    else:
        pct_tv_cap, pct_rad_cap = min(pct_tv, Decimal('180')), min(pct_rad, Decimal('180'))
        weighted_pct = ((Decimal('0.60') * pct_tv_cap) + (Decimal('0.30') * pct_rad_cap)) / Decimal('0.90')
        if weighted_pct < 100: mult = Decimal('0.00')
        elif weighted_pct <= 120: mult = Decimal('1.00')
        elif weighted_pct <= 150: mult = Decimal('2.10')
        else: mult = Decimal('4.10')
        return target_commission * mult, f"MODE A (Both Hit - {weighted_pct:.1f}% Re-Weighted)", f"{mult}x", lines

def run_alternative_smme_logic(entries, target_commission):
    lines = []
    non_digital = ["Radio Classic", "Radio Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship", "Radio Sport Sponsorship"]
    tot_act_nd = sum(Decimal(str(e["act"])) for e in entries if e["name"] in non_digital)
    tot_tar_nd = sum(Decimal(str(e["tar"])) for e in entries if e["name"] in non_digital)
    overall_pct = (tot_act_nd / tot_tar_nd) * 100 if tot_tar_nd > 0 else Decimal('0')
    cw = {"Radio Classic": Decimal('0.45'), "Radio Sponsorship": Decimal('0.15'), "TV Classic": Decimal('0.24'), "TV Sponsorship": Decimal('0.06'), "TV Sport Sponsorship": Decimal('0.025'), "Radio Sport Sponsorship": Decimal('0.025'), "Digital": Decimal('0.05')}

    comm = Decimal('0')
    for e in entries:
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        pct = (a / t) * 100 if t > 0 else Decimal('0')
        sc, sc_display = Decimal('0'), "  (Pooled)"
        if overall_pct < 100:
            if pct >= 100: sc = target_commission * cw.get(e["name"], Decimal('0'))
            sc_display = f"R{sc:>11,.2f}"
        comm += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {pct:>7.1f}% | {sc_display}")

    if overall_pct < 100: return comm, f"Sub-100% (Excluded Digital | {overall_pct:.1f}%)", "No Multiplier", lines
    else:
        if overall_pct <= 120: mult = Decimal('1.00')
        elif overall_pct <= 150: mult = Decimal('2.10')
        elif overall_pct <= 180: mult = Decimal('4.10')
        else: mult = Decimal('6.20')
        return target_commission * mult, f"Multiplier Triggered (Excluded Digital | {overall_pct:.1f}%)", f"{mult}x", lines


# --- FILE EXTRACTION ENGINE ---
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = num_str.strip()
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
    data = {
        "period": "", "pers_num": "", "emp_name": "",
        "midpoint": 0.0, "sabc_target": 0.0, "segments": {}
    }
    for s in ALL_SEGMENTS: data["segments"][s] = {"act": 0.0, "tar": 1.0}
    
    try:
        file_bytes = file_obj.read()
        if file_obj.name.lower().endswith('.pdf'):
            pdf_text = ""
            try:
                reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages: pdf_text += page.extract_text() + "\n"
            except Exception: pass
            
            if len(pdf_text.strip()) < 50:
                try: pdf_text = file_bytes.decode('utf-8')
                except Exception: pdf_text = file_bytes.decode('latin-1', errors='ignore')
                    
            norm_text = pdf_text.replace('"', '')
            norm_text = re.sub(r'\s+', ' ', norm_text)
            
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

            mult_match = re.search(r"Multiplier Commission[^\d]*?(-?\d[\d\.,]*\.\d{2})[^\d]*?(-?\d[\d\.,]*\.\d{2})", norm_text, re.IGNORECASE)
            if mult_match: data["sabc_target"] = parse_sabc_number(mult_match.group(2))

        elif file_obj.name.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_bytes), encoding='latin-1')
            for _, row in df.iterrows():
                seg_name = str(row.get('Segment', '')).strip()
                for s in ALL_SEGMENTS:
                    if seg_name.lower() == s.lower() or seg_name.lower() == s.lower() + "s":
                        data["segments"][s]["act"] = float(row.get('Actuals', row.get('Actual', 0)))
                        data["segments"][s]["tar"] = float(row.get('Target', 1))
    except Exception as e:
        pass
    return data


# --- UI SETUP & STATE MANAGEMENT ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

# Init persistent employee info across modes
if "emp_name" not in st.session_state: st.session_state["emp_name"] = ""
if "pers_num" not in st.session_state: st.session_state["pers_num"] = ""
if "period" not in st.session_state: st.session_state["period"] = ""

col_top1, col_top2 = st.columns(2)
with col_top1:
    selected_profile = st.radio("Select AE Profile / Category:", ["Standard AE / SMME", "Sports PM"], horizontal=True)
with col_top2:
    analysis_mode = st.radio("Analysis Mode:", ["Single Statement", "Bulk Statements (Underpayment Summary)"], horizontal=True)
    if analysis_mode == "Single Statement":
        underpayment_only = st.checkbox("Underpayment Report Only?", help="Hides alternative policies, shows only Midpoint math error", value=False)
st.divider()

# --- BULK STATEMENTS MODE ---
if analysis_mode == "Bulk Statements (Underpayment Summary)":
    st.subheader("Bulk Forensic Underpayment Compiler")
    uploaded_files = st.file_uploader("Upload all SABC Statements for this member (PDF/CSV)", type=['pdf', 'csv', 'xlsx'], accept_multiple_files=True)
    
    if uploaded_files:
        if not st.session_state["emp_name"] or not st.session_state["pers_num"]:
            for f in uploaded_files:
                f.seek(0)
                temp_data = extract_file_data(f)
                if temp_data["emp_name"] and not st.session_state["emp_name"]: st.session_state["emp_name"] = temp_data["emp_name"]
                if temp_data["pers_num"] and not st.session_state["pers_num"]: st.session_state["pers_num"] = temp_data["pers_num"]
                if st.session_state["emp_name"]: break

    st.subheader("Employee Details (Extracted or Manual Entry)")
    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1: st.text_input("Employee Name:", key="emp_name", placeholder="e.g. John Doe")
    with col_e2: st.text_input("Personnel Number:", key="pers_num", placeholder="e.g. 11502")
    with col_e3: st.text_input("Statement Period (Optional for Bulk):", key="period", placeholder="e.g. 2025 Financial Year")

    scale_current = st.selectbox("Correct Current Midpoint (Scale Code):", list(MIDPOINTS_CURRENT.keys()))
    
    if st.button("RUN BULK UNDERPAYMENT REPORT", type="primary", use_container_width=True) and uploaded_files:
        active_stmt_w = PROFILES[selected_profile]["statement"]
        mid_curr = (Decimal(str(MIDPOINTS_CURRENT[scale_current])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        bulk_results = []
        total_underpayment = Decimal('0')
        
        disp_emp = st.session_state["emp_name"].strip() or "[Manual Entry]"
        disp_pers = st.session_state["pers_num"].strip() or "[Manual Entry]"
        disp_per = st.session_state["period"].strip()

        for file in uploaded_files:
            file.seek(0)
            data = extract_file_data(file)
            
            entries = []
            for s in ALL_SEGMENTS:
                act_val = data["segments"][s]["act"]
                tar_val = data["segments"][s]["tar"]
                
                # --- BULK AUTO-SWAP INTELLIGENCE ---
                # Detects the SABC SAP blank-column glitch where Target is captured as 100 Area %
                if tar_val == 100.0 or tar_val == 100:
                    tar_val = act_val
                    act_val = 0.0
                    
                entries.append({"name": s, "act": act_val, "tar": tar_val})
            
            mid_stmt = Decimal(str(data["midpoint"])).quantize(Decimal('0.01'), ROUND_HALF_UP)
            if mid_stmt == Decimal('0'): mid_stmt = mid_curr # Fallback if missing
            
            ta = sum(Decimal(str(e["act"])) for e in entries)
            tt = sum(Decimal(str(e["tar"])) for e in entries)
            rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
            m = get_mult(rev_ach)
            
            m_pay_stmt = (mid_stmt * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            m_pay_curr = (mid_curr * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            applied_stmt = run_scenario(entries, mid_stmt, active_stmt_w, m_pay_stmt, 'absorbed')
            applied_curr = run_scenario(entries, mid_curr, active_stmt_w, m_pay_curr, 'absorbed')
            
            diff = applied_curr['tot'] - applied_stmt['tot']
            total_underpayment += diff
            
            bulk_results.append({
                "period": data["period"] or "Unknown",
                "mid_stmt": mid_stmt,
                "comm_stmt": applied_stmt['tot'],
                "mid_curr": mid_curr,
                "comm_curr": applied_curr['tot'],
                "diff": diff
            })

        rep = "FORENSIC ANALYSIS OF UNDERPAYMENT OF COMMISSION DUE TO WRONG MIDPOINT USED.\n\n"
        rep += f"EMPLOYEE:          {disp_emp}\n"
        rep += f"PERSONNELL NUMBER: {disp_pers}\n"
        if disp_per:
            rep += f"PERIOD:            {disp_per}\n"
        rep += f"CORRECT MIDPOINT:  R {mid_curr:,.2f} (Scale {scale_current})\n\n"
        
        rep += f"{'PERIOD':<18} | {'STMT MIDPOINT':>13} | {'STMT COMM':>13} | {'CURR MIDPOINT':>13} | {'CURR COMM':>13} | {'DIFFERENCE':>13}\n"
        rep += "-"*98 + "\n"
        
        for r in bulk_results:
            rep += f"{r['period']:<18} | R {r['mid_stmt']:>11,.2f} | R {r['comm_stmt']:>11,.2f} | R {r['mid_curr']:>11,.2f} | R {r['comm_curr']:>11,.2f} | R {r['diff']:>11,.2f}\n"
            
        rep += "-"*98 + "\n"
        rep += f"{'TOTAL UNDERPAID COMMISSION DUE:':<82} R {total_underpayment:>11,.2f}\n"
        
        st.code(rep, language="text")
        
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, rep.encode('latin-1', 'replace').decode('latin-1'))
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        
        safe_emp = disp_emp.replace(' ', '_') if disp_emp != "[Manual Entry]" else "Employee"
        safe_per = f"_{disp_per.replace(' ', '_').replace('/', '-')}" if disp_per else ""
        final_pdf_name = f"{safe_emp}{safe_per}_Bulk_UNDERPAID.pdf"
        
        st.download_button(label=f"📄 Download Bulk Audit PDF: {final_pdf_name}", data=pdf_bytes, file_name=final_pdf_name, mime="application/pdf", type="primary")


# --- SINGLE STATEMENT MODE ---
if analysis_mode == "Single Statement":
    
    if "midpoint_input_val" not in st.session_state: st.session_state["midpoint_input_val"] = "27276.33"
    if "sabc_target_default" not in st.session_state: st.session_state["sabc_target_default"] = "7917181.70"
    if "header_info" not in st.session_state: st.session_state["header_info"] = ""

    for s in ALL_SEGMENTS:
        if f"act_{s}" not in st.session_state: st.session_state[f"act_{s}"] = 0.0
        if f"tar_{s}" not in st.session_state: st.session_state[f"tar_{s}"] = 1.0

    def swap_act_tar(seg):
        st.session_state[f"tar_{seg}"] = st.session_state[f"act_{seg}"]
        st.session_state[f"act_{seg}"] = 0.0

    uploaded_file = st.file_uploader("Upload Single SABC Statement (PDF, CSV, Excel)", type=['pdf', 'csv', 'xlsx'])

    if uploaded_file is not None:
        file_hash = hash(uploaded_file.getvalue())
        if st.session_state.get("last_file_hash") != file_hash:
            st.session_state["last_file_hash"] = file_hash
            data = extract_file_data(uploaded_file)
            
            if data["period"]: st.session_state["period"] = data["period"]
            if data["pers_num"]: st.session_state["pers_num"] = data["pers_num"]
            if data["emp_name"]: st.session_state["emp_name"] = data["emp_name"]
            
            if data["midpoint"] > 0: st.session_state["midpoint_input_val"] = f"{data['midpoint']:.2f}"
            if data["sabc_target"] > 0: st.session_state["sabc_target_default"] = f"{data['sabc_target']:.2f}"
            
            for s in ALL_SEGMENTS:
                st.session_state[f"act_{s}"] = data["segments"][s]["act"]
                st.session_state[f"tar_{s}"] = data["segments"][s]["tar"]
            
            st.success("File parsed successfully! Verify details below.")

    st.subheader("Employee Details (Extracted or Manual Entry)")
    col_e1, col_e2, col_e3 = st.columns(3)
    with col_e1: st.text_input("Employee Name:", key="emp_name", placeholder="e.g. John Doe")
    with col_e2: st.text_input("Personnel Number:", key="pers_num", placeholder="e.g. 11502")
    with col_e3: st.text_input("Statement Period:", key="period", placeholder="e.g. August 2025")

    st.divider()

    col1, col2 = st.columns([1, 2])
    with col1:
        midpoint_input = st.text_input("Target Commission (Statement Midpoint):", key="midpoint_input_val")
        sabc_overall_target = st.text_input("SABC Multiplier Target (Pre-filled from PDF):", key="sabc_target_default")
        scale_2021 = st.selectbox("2021 Midpoints (Scale Code):", list(MIDPOINTS_2021.keys()))
        scale_current = st.selectbox("Current Midpoints (Scale Code):", list(MIDPOINTS_CURRENT.keys()))

    st.subheader("Statement Values Verification (Override Blank Values)")
    cols = st.columns([3, 2, 2, 1])
    cols[0].write("**Segment Name**")
    cols[1].write("**Actual Revenue**")
    cols[2].write("**Target Revenue**")

    entries = []
    visible_segments = ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if selected_profile == "Sports PM" else ALL_SEGMENTS

    for s in visible_segments:
        col_a, col_b, col_c, col_d = st.columns([3, 2, 2, 1])
        col_a.write(s)
        act = col_b.number_input(f"Act {s}", key=f"act_{s}", step=1000.0, label_visibility="collapsed")
        tar = col_c.number_input(f"Tar {s}", key=f"tar_{s}", step=1000.0, label_visibility="collapsed")
        col_d.button("🔴 Swap", key=f"swap_btn_{s}", on_click=swap_act_tar, args=(s,), help="Moves Actual to Target")
        entries.append({"name": s, "act": act, "tar": tar})

    for s in ALL_SEGMENTS:
        if s not in visible_segments:
            entries.append({"name": s, "act": st.session_state[f"act_{s}"], "tar": st.session_state[f"tar_{s}"]})

    st.divider()

    if st.button("RUN FORENSIC COMPARISON", type="primary", use_container_width=True):
        try:
            active_stmt_w = PROFILES[selected_profile]["statement"]
            active_pol_w = PROFILES[selected_profile]["policy"]
            str_stmt = PROFILES[selected_profile]["display_stmt"]
            str_pol = PROFILES[selected_profile]["display_pol"]

            mid_manual = Decimal(str(midpoint_input).replace(',', ''))
            mid_2021 = (Decimal(str(MIDPOINTS_2021[scale_2021])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
            mid_curr = (Decimal(str(MIDPOINTS_CURRENT[scale_current])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            ta = sum(Decimal(str(e["act"])) for e in entries)
            tt = sum(Decimal(str(e["tar"])) for e in entries)
            rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
            m = get_mult(rev_ach)
            
            m_pay_manual = (mid_manual * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            m_pay_2021 = (mid_2021 * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            m_pay_curr = (mid_curr * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            applied_manual = run_scenario(entries, mid_manual, active_stmt_w, m_pay_manual, 'absorbed')
            applied_curr   = run_scenario(entries, mid_curr, active_stmt_w, m_pay_curr, 'absorbed')
            
            disp_emp = st.session_state["emp_name"].strip() or "[Manual Entry]"
            disp_pers = st.session_state["pers_num"].strip() or "[Manual Entry]"
            disp_per = st.session_state["period"].strip() or "[Manual Entry]"

            if underpayment_only:
                rep = "FORENSIC ANALYSIS OF UNDERPAYMENT OF COMMISSION DUE TO WRONG MIDPOINT USED.\n\n"
                rep += f"EMPLOYEE:          {disp_emp}\n"
                rep += f"PERSONNELL NUMBER: {disp_pers}\n"
                rep += f"PERIOD:            {disp_per}\n"
                rep += f"MIDPOINT USED:     R {mid_manual:,.2f}\n"
                rep += f"CORRECT MIDPOINT:  R {mid_curr:,.2f} (Scale {scale_current})\n\n"

                def build_up_table(title, lines, sum_seg, m_pay, tot):
                    b = f"--- {title} ---\n"
                    b += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
                    b += "\n".join(lines) + "\n" + "-"*81 + "\n"
                    b += f"{'TOTAL SEGMENT COMMISSION:':<35} R {sum_seg:>12,.2f}\n"
                    b += f"{'MULTIPLIER APPLIED:':<35} {m}x\n"
                    b += f"{'MULTIPLIER COMMISSION:':<35} R {m_pay:>12,.2f}\n"
                    b += f"{'COMMISSION DUE:':<35} R {tot:>12,.2f}\n"
                    return b

                rep += build_up_table("CALCULATION 1: SABC APPLIED (MIDPOINT USED)", applied_manual['lines'], applied_manual['sum_seg'], m_pay_manual, applied_manual['tot']) + "\n\n"
                rep += build_up_table("CALCULATION 2: SABC APPLIED (CORRECT MIDPOINT)", applied_curr['lines'], applied_curr['sum_seg'], m_pay_curr, applied_curr['tot']) + "\n\n"

                shortfall = applied_curr['tot'] - applied_manual['tot']
                rep += "-"*81 + "\n"
                rep += f"{'TOTAL COMMISSION DUE (CORRECT SCALES):':<40} R {applied_curr['tot']:>12,.2f}\n"
                rep += f"{'TOTAL UNDERPAYMENT AMOUNT:':<40} R {shortfall:>12,.2f}\n"
                rep += "-"*81 + "\n"
                
                st.code(rep, language="text")
                full_report = rep
                
            else:
                policy_manual  = run_scenario(entries, mid_manual, active_pol_w, m_pay_manual, 'additive')
                policy_2021    = run_scenario(entries, mid_2021, active_pol_w, m_pay_2021, 'additive')
                policy_curr    = run_scenario(entries, mid_curr, active_pol_w, m_pay_curr, 'additive')
                
                st.header(f"SABC OWN WEIGHTING PAYOUT (Statement Midpoint): R {applied_manual['tot']:,.2f}")
                
                sabc_declared_target = Decimal(str(sabc_overall_target).replace(',', ''))
                target_discrepancy = tt - sabc_declared_target
                
                target_warning = ""
                if abs(target_discrepancy) > Decimal('10'):
                    if sabc_declared_target < tt: manip_text = "(SABC artificially lowered the overall target, inflating the achievement %)"
                    else: manip_text = "(SABC artificially INFLATED the overall target, deflating the achievement % - reducing the payout)"

                    target_warning = f"!!! FORENSIC WARNING: TARGET MANIPULATION DETECTED !!!\n"
                    target_warning += f"Sum of Individual Segment Targets: R {tt:,.2f}\n"
                    target_warning += f"Target Used by SABC for Multiplier: R {sabc_declared_target:,.2f}\n"
                    target_warning += f"Unexplained Target Gap:             R {abs(target_discrepancy):,.2f}\n"
                    target_warning += f"{manip_text}\n\n"
                    st.error(target_warning)
                    
                file_header = f"Forensic analysis of: Statement: {disp_per} | Personnel: {disp_pers} ({disp_emp})\n\n"

                def build_audit_block(title, mid_val, mid_label, weights, lines, m_pay, tot, label_tot):
                    b = f"--- {title} ---\n"
                    b += f"Profile: {selected_profile}\n"
                    b += f"Midpoint Applied: R {mid_val:,.2f} {mid_label}\n"
                    b += f"Weights Applied: {weights} | Total Ach: {rev_ach}% | Mult: {m}x\n"
                    b += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
                    b += "\n".join(lines) + "\n" + "-"*81 + "\n"
                    b += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
                    b += f"{label_tot:<35} R {tot:>12,.2f}\n"
                    return b

                def build_alternative_block(title, c_mode, c_mult, lines, c_tot, scale_label=""):
                    b = f"--- {title} ---\n"
                    b += f"Logic Rule: {c_mode}\nMultiplier Applied: {c_mult}\n"
                    b += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
                    b += "\n".join(lines) + "\n" + "-"*81 + "\n"
                    b += f"FINAL ALTERNATIVE PAYOUT {scale_label}: R {c_tot:>12,.2f}\n\n"
                    return b

                audit1 = file_header + target_warning + build_audit_block("SCENARIO 1: SABC OWN WEIGHTING (STATEMENT MIDPOINT)", mid_manual, "(Statement Entry)", str_stmt, applied_manual["lines"], m_pay_manual, applied_manual["tot"], "FINAL SABC PAYOUT (Absorbed):")
                audit2 = build_audit_block("SCENARIO 2: SABC OWN WEIGHTING (CURRENT SCALES)", mid_curr, f"(Scale {scale_current} / 12)", str_stmt, applied_curr["lines"], m_pay_curr, applied_curr["tot"], "FINAL SABC PAYOUT (Absorbed):")
                audit3 = build_audit_block("SCENARIO 3: POLICY DICTATED (STATEMENT MIDPOINT)", mid_manual, "(Statement Entry)", str_pol, policy_manual["lines"], m_pay_manual, policy_manual["tot"], "FINAL POLICY DUE (Additive):")
                audit4 = build_audit_block("SCENARIO 4: POLICY DICTATED (2021 SCALES)", mid_2021, f"(Scale {scale_2021} / 12)", str_pol, policy_2021["lines"], m_pay_2021, policy_2021["tot"], "FINAL POLICY DUE (Additive):")
                audit5 = build_audit_block("SCENARIO 5: POLICY DICTATED (CURRENT SCALES)", mid_curr, f"(Scale {scale_current} / 12)", str_pol, policy_curr["lines"], m_pay_curr, policy_curr["tot"], "FINAL POLICY DUE (Additive):")

                if selected_profile == "Sports PM":
                    c_tot_with, c_mod_with, c_mul_with, c_lines_with = run_alt_sports_with_digital(entries, mid_manual)
                    c_tot_excl, c_mod_excl, c_mul_excl, c_lines_excl = run_alt_sports_exclude_digital(entries, mid_manual)
                    audit6 = build_alternative_block("SCENARIO 6: ALTERNATIVE CALCULATION (WITH DIGITAL)", c_mod_with, c_mul_with, c_lines_with, c_tot_with, "(Statement Midpoint)")
                    audit7 = build_alternative_block("SCENARIO 7: ALTERNATIVE CALCULATION (EXCLUDING DIGITAL)", c_mod_excl, c_mul_excl, c_lines_excl, c_tot_excl, "(Statement Midpoint)")
                else:
                    c_tot_man, c_mod_man, c_mul_man, c_lines_man = run_alternative_smme_logic(entries, mid_manual)
                    c_tot_cur, c_mod_cur, c_mul_cur, c_lines_cur = run_alternative_smme_logic(entries, mid_curr)
                    audit6 = build_alternative_block("SCENARIO 6: ALTERNATIVE CALCULATION (STATEMENT MIDPOINT)", c_mod_man, c_mul_man, c_lines_man, c_tot_man, "(Statement)")
                    audit7 = build_alternative_block("SCENARIO 7: ALTERNATIVE CALCULATION (CURRENT SCALES)", c_mod_cur, c_mul_cur, c_lines_cur, c_tot_cur, f"(Scale {scale_current})")

                short_payment_midpoint = applied_curr['tot'] - applied_manual['tot']

                adv = "--- FORENSIC DISCREPANCY SUMMARY ---\n\n"
                adv += f"Profile Audited: {selected_profile}\n\n"
                adv += f"1. SABC OWN WEIGHTING (Statement):       R {applied_manual['tot']:>12,.2f}\n"
                adv += f"2. SABC OWN WEIGHTING @ Current (Scale {scale_current:<4}): R {applied_curr['tot']:>12,.2f}\n"
                adv += f"3. POLICY DUE (Statement):               R {policy_manual['tot']:>12,.2f}\n"
                adv += f"4. POLICY DUE @ 2021 (Scale {scale_2021:<4}):      R {policy_2021['tot']:>12,.2f}\n"
                adv += f"5. POLICY DUE @ Current (Scale {scale_current:<4}):   R {policy_curr['tot']:>12,.2f}\n"
                
                if selected_profile == "Sports PM":
                    adv += f"6. ALTERNATIVE CALCULATION (W/ Digital): R {c_tot_with:>12,.2f}\n"
                    adv += f"7. ALTERNATIVE CALCULATION (No Digital): R {c_tot_excl:>12,.2f}\n"
                else:
                    adv += f"6. ALTERNATIVE CALCULATION (Statement):  R {c_tot_man:>12,.2f}\n"
                    adv += f"7. ALTERNATIVE CALCULATION @ Current:    R {c_tot_cur:>12,.2f}\n"
                    
                adv += "-"*56 + "\n"
                adv += f"SHORTFALL A (Policy Stmt vs SABC Stmt):       R {(policy_manual['tot'] - applied_manual['tot']):>12,.2f}\n"
                adv += f"SHORTFALL B (Policy Current vs SABC Current): R {(policy_curr['tot'] - applied_curr['tot']):>12,.2f}\n"
                adv += f"ULTIMATE SHORTFALL (Policy Curr vs SABC Stmt):R {(policy_curr['tot'] - applied_manual['tot']):>12,.2f}\n\n"
                adv += f"SHORTPAYMENT DUE TO WRONG MIDPOINT APPLIED:   R {short_payment_midpoint:>12,.2f}\n"

                col_out1, col_out2 = st.columns(2)
                with col_out1: 
                    st.code(audit1 + "\n\n" + audit2 + "\n\n" + audit3 + "\n\n" + audit4, language="text")
                with col_out2: 
                    st.code(audit5 + "\n\n" + audit6 + audit7, language="text")
                st.code(adv, language="text")
                    
                full_report = audit1 + "\n\n" + audit2 + "\n\n" + audit3 + "\n\n" + audit4 + "\n\n" + audit5 + "\n\n" + audit6 + audit7 + adv

            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Courier", size=8)
            pdf.multi_cell(0, 4, full_report.encode('latin-1', 'replace').decode('latin-1'))
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            
            safe_emp = disp_emp.replace(' ', '_') if disp_emp != "[Manual Entry]" else "Employee"
            safe_per = disp_per.replace(' ', '_').replace('/', '-') if disp_per != "[Manual Entry]" else "Period"
            
            final_pdf_name = f"{safe_emp}_{safe_per}_UNDERPAID.pdf"
            
            st.download_button(label=f"📄 Download PDF: {final_pdf_name}", data=pdf_bytes, file_name=final_pdf_name, mime="application/pdf", type="primary")
                
        except Exception as e:
            st.error(f"Calculation Error: Check inputs. Details: {e}")
