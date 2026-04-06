import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

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

def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = str(num_str).strip().replace(' ', '')
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
            mult_match = re.search(r"Multiplier Commission[^\d]*?(-?\d[\d\.,]*\.\d{2})[^\d]*?(-?\d[\d\.,]*\.\d{2})", norm_text, re.IGNORECASE)
            if mult_match: data["sabc_target"] = parse_sabc_number(mult_match.group(2))
    except Exception: pass
    return data

def parse_period_for_sorting(period_str):
    try: return datetime.strptime(period_str.strip(), "%B %Y")
    except Exception: return datetime.max

# --- UI ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

col_top1, col_top2 = st.columns(2)
with col_top1:
    selected_profile = st.radio("Select AE Profile / Category:", ["Standard AE / SMME", "Sports PM"], horizontal=True)
with col_top2:
    analysis_mode = st.radio("Analysis Mode:", ["Single Statement", "Bulk Statements (Underpayment Summary)"], horizontal=True)

st.divider()

if "emp_name" not in st.session_state: st.session_state["emp_name"] = ""
if "pers_num" not in st.session_state: st.session_state["pers_num"] = ""
if "period" not in st.session_state: st.session_state["period"] = ""

# --- BULK MODE ---
if analysis_mode == "Bulk Statements (Underpayment Summary)":
    input_method = st.radio("Bulk Data Source:", ["Upload PDFs/CSVs", "Manual Grid Entry (Spreadsheet Data)"], horizontal=True)
    scale_current = st.selectbox("Correct Current Midpoint (Scale Code):", list(MIDPOINTS_CURRENT.keys()))
    
    bulk_data_list = []

    if input_method == "Upload PDFs/CSVs":
        uploaded_files = st.file_uploader("Upload SABC Statements", type=['pdf', 'csv', 'xlsx'], accept_multiple_files=True)
        if uploaded_files:
            for f in uploaded_files:
                f.seek(0)
                d = extract_file_data(f)
                if not st.session_state["emp_name"]: st.session_state["emp_name"] = d["emp_name"]
                if not st.session_state["pers_num"]: st.session_state["pers_num"] = d["pers_num"]
                
                ents = []
                for s in ALL_SEGMENTS:
                    a, t = d["segments"][s]["act"], d["segments"][s]["tar"]
                    if t == 100.0: t, a = a, 0.0 # Auto-Swap logic
                    ents.append({"name": s, "act": a, "tar": t})
                bulk_data_list.append({"period": d["period"], "mid_stmt": Decimal(str(d["midpoint"])), "entries": ents})

    else:
        st.info("Fill in the grid below using your spreadsheet data (like Titus's figures).")
        month_grid = st.data_editor(
            pd.DataFrame([{"Month/Year": "", "Midpoint on Statement": 27276.33, "Actual Revenue (Total)": 0.0, "Target Revenue (Total)": 1.0}]),
            num_rows="dynamic", use_container_width=True
        )
        if not month_grid.empty:
            for _, row in month_grid.iterrows():
                # Simplified entries for manual bulk: put everything into one main segment to get the multiplier
                dummy_entries = [{"name": "Digital", "act": row["Actual Revenue (Total)"], "tar": row["Target Revenue (Total)"]}]
                bulk_data_list.append({"period": row["Month/Year"], "mid_stmt": Decimal(str(row["Midpoint on Statement"])), "entries": dummy_entries})

    st.subheader("Final Details Override")
    c1, c2, c3 = st.columns(3)
    c1.text_input("Employee Name:", key="emp_name")
    c2.text_input("Personnel Number:", key="pers_num")
    c3.text_input("Bulk Period Name:", key="period", placeholder="e.g. 2025 FY")

    if st.button("RUN BULK UNDERPAYMENT REPORT", type="primary", use_container_width=True) and bulk_data_list:
        active_stmt_w = PROFILES[selected_profile]["statement"]
        mid_curr = (Decimal(str(MIDPOINTS_CURRENT[scale_current])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        bulk_results, total_short = [], Decimal('0')

        for item in bulk_data_list:
            ta = sum(Decimal(str(e["act"])) for e in item["entries"])
            tt = sum(Decimal(str(e["tar"])) for e in item["entries"])
            rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
            m = get_mult(rev_ach)
            
            m_pay_stmt = (item["mid_stmt"] * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            m_pay_curr = (mid_curr * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            # Use specific segment weights if detailed entries exist, otherwise dummy
            w_map = active_stmt_w if len(item["entries"]) > 1 else {"Digital": 100.0}
            
            res_stmt = run_scenario(item["entries"], item["mid_stmt"], w_map, m_pay_stmt, 'absorbed')
            res_curr = run_scenario(item["entries"], mid_curr, w_map, m_pay_curr, 'absorbed')
            
            diff = res_curr['tot'] - res_stmt['tot']
            total_short += diff
            bulk_results.append({"period": item["period"], "mid_s": item["mid_stmt"], "comm_s": res_stmt['tot'], "mid_c": mid_curr, "comm_c": res_curr['tot'], "diff": diff})

        bulk_results.sort(key=lambda x: parse_period_for_sorting(x["period"]))
        
        rep = "FORENSIC ANALYSIS OF UNDERPAYMENT OF COMMISSION DUE TO WRONG MIDPOINT USED.\n\n"
        rep += f"EMPLOYEE:          {st.session_state['emp_name']}\nPERSONNELL NUMBER: {st.session_state['pers_num']}\n"
        if st.session_state['period']: rep += f"PERIOD:            {st.session_state['period']}\n"
        rep += f"CORRECT MIDPOINT:  R {mid_curr:,.2f} (Scale {scale_current})\n\n"
        rep += f"{'PERIOD':<18} | {'STMT MIDPOINT':>13} | {'STMT COMM':>13} | {'CURR MIDPOINT':>13} | {'CURR COMM':>13} | {'DIFFERENCE':>13}\n" + "-"*98 + "\n"
        for r in bulk_results:
            rep += f"{r['period']:<18} | R{r['mid_s']:>12,.2f} | R{r['comm_s']:>12,.2f} | R{r['mid_c']:>12,.2f} | R{r['comm_c']:>12,.2f} | R{r['diff']:>12,.2f}\n"
        rep += "-"*98 + "\n" + f"{'TOTAL UNDERPAID COMMISSION DUE:':<82} R {total_short:>11,.2f}\n"
        
        st.code(rep, language="text")
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0, 4, rep.encode('latin-1', 'replace').decode('latin-1'))
        fname = f"{st.session_state['emp_name'].replace(' ','_')}_{st.session_state['period'].replace(' ','_')}_Bulk_UNDERPAID.pdf"
        st.download_button("📄 Download Bulk Audit PDF", pdf.output(dest='S').encode('latin-1'), file_name=fname, mime="application/pdf")

# --- SINGLE MODE ---
else:
    underpayment_only = st.checkbox("Underpayment Report Only?")
    for s in ALL_SEGMENTS:
        if f"act_{s}" not in st.session_state: st.session_state[f"act_{s}"] = 0.0
        if f"tar_{s}" not in st.session_state: st.session_state[f"tar_{s}"] = 1.0

    up_file = st.file_uploader("Upload SABC Statement", type=['pdf', 'csv'])
    if up_file:
        d = extract_file_data(up_file)
        st.session_state["period"], st.session_state["pers_num"], st.session_state["emp_name"] = d["period"], d["pers_num"], d["emp_name"]
        st.session_state["midpoint_input_val"], st.session_state["sabc_target_default"] = f"{d['midpoint']:.2f}", f"{d['sabc_target']:.2f}"
        for s in ALL_SEGMENTS: st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = d["segments"][s]["act"], d["segments"][s]["tar"]

    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.text_input("Employee Name:", key="emp_name")
    col_e2.text_input("Personnel Number:", key="pers_num")
    col_e3.text_input("Statement Period:", key="period")

    col1, col2 = st.columns([1, 2])
    mid_in = col1.text_input("Target Commission (Statement Midpoint):", key="midpoint_input_val")
    sabc_t = col1.text_input("SABC Multiplier Target:", key="sabc_target_default")
    scale_2021 = col1.selectbox("2021 Midpoints:", list(MIDPOINTS_2021.keys()))
    scale_curr = col1.selectbox("Current Midpoints:", list(MIDPOINTS_CURRENT.keys()))

    visible_segments = ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if selected_profile == "Sports PM" else ALL_SEGMENTS
    entries = []
    for s in visible_segments:
        ca, cb, cc, cd = st.columns([3, 2, 2, 1])
        ca.write(s)
        act = cb.number_input(f"Act {s}", key=f"act_{s}", step=1000.0, label_visibility="collapsed")
        tar = cc.number_input(f"Tar {s}", key=f"tar_{s}", step=1000.0, label_visibility="collapsed")
        if cd.button("🔴 Swap", key=f"swp_{s}"):
            st.session_state[f"tar_{s}"], st.session_state[f"act_{s}"] = st.session_state[f"act_{s}"], 0.0
            st.rerun()
        entries.append({"name": s, "act": act, "tar": tar})

    for s in ALL_SEGMENTS:
        if s not in visible_segments: entries.append({"name": s, "act": st.session_state[f"act_{s}"], "tar": st.session_state[f"tar_{s}"]})

    if st.button("RUN FORENSIC COMPARISON", type="primary", use_container_width=True):
        mid_m = Decimal(str(mid_in).replace(',',''))
        mid_c = (Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        ta, tt = sum(Decimal(str(e["act"])) for e in entries), sum(Decimal(str(e["tar"])) for e in entries)
        rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
        m = get_mult(rev_ach)
        m_pay_m, m_pay_c = (mid_m * m).quantize(Decimal('0.01'), ROUND_HALF_UP), (mid_c * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
        res_m = run_scenario(entries, mid_m, PROFILES[selected_profile]["statement"], m_pay_m, 'absorbed')
        res_c = run_scenario(entries, mid_c, PROFILES[selected_profile]["statement"], m_pay_c, 'absorbed')
        
        rep = ""
        if underpayment_only:
            rep = "FORENSIC ANALYSIS OF UNDERPAYMENT OF COMMISSION DUE TO WRONG MIDPOINT USED.\n\n"
            rep += f"EMPLOYEE: {st.session_state['emp_name']}\nPERSONNEL: {st.session_state['pers_num']}\nPERIOD: {st.session_state['period']}\n"
            rep += f"MIDPOINT USED: R{mid_m:,.2f}\nCORRECT MIDPOINT: R{mid_c:,.2f} (Scale {scale_curr})\n\n"
            def tbl(title, r, mp, tot):
                b = f"--- {title} ---\n{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
                b += "\n".join(r['lines']) + "\n" + "-"*81 + "\n"
                b += f"{'MULTIPLIER COMMISSION:':<35} R {mp:>12,.2f}\n{'COMMISSION DUE:':<35} R {tot:>12,.2f}\n"
                return b
            rep += tbl("CALCULATION 1: SABC APPLIED", res_m, m_pay_m, res_m['tot']) + "\n" + tbl("CALCULATION 2: CORRECT MIDPOINT", res_c, m_pay_c, res_c['tot'])
            rep += f"\nTOTAL UNDERPAYMENT: R {(res_c['tot'] - res_m['tot']):,.2f}"
        else:
            rep = f"Forensic analysis of: {st.session_state['period']} | {st.session_state['emp_name']}\n\n"
            rep += f"SABC OWN WEIGHTING (Statement): R {res_m['tot']:,.2f}\n"
            rep += f"SABC OWN WEIGHTING (Current):   R {res_c['tot']:,.2f}\n"
            rep += f"UNDERPAYMENT:                   R {(res_c['tot'] - res_m['tot']):,.2f}"

        st.code(rep, language="text")
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0, 4, rep.encode('latin-1', 'replace').decode('latin-1'))
        fname = f"{st.session_state['emp_name'].replace(' ','_')}_{st.session_state['period'].replace(' ','_')}_UNDERPAID.pdf"
        st.download_button("📄 Download PDF", pdf.output(dest='S').encode('latin-1'), file_name=fname, mime="application/pdf")
