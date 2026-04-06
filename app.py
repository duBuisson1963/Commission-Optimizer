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

# --- SALARY SCALES ---
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
    pct_tv, pct_rad, pct_dig = (act_tv/tar_tv)*100, (act_rad/tar_rad)*100, (act_dig/tar_dig)*100
    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% |   (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% |   (Pooled)")
    lines.append(f"{'Digital':<23} R{act_dig:>11,.2f} | R{tar_dig:>11,.2f} | {pct_dig:>7.1f}% |   (Pooled)")
    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)
    if ach_count == 0: return Decimal('0'), "MODE C (No Sport Targets Hit)", "0.00x", lines
    elif ach_count == 1:
        if pct_tv >= 100: return target_commission * Decimal('0.60'), "MODE B (TV Fallback)", "Fallback (60%)", lines
        else: return target_commission * Decimal('0.30'), "MODE B (Radio Fallback)", "Fallback (30%)", lines
    else:
        weighted_pct = (Decimal('0.60') * min(pct_tv, 180)) + (Decimal('0.30') * min(pct_rad, 180)) + (Decimal('0.10') * min(pct_dig, 180))
        m = get_mult(weighted_pct)
        return target_commission * m, f"MODE A (Weighted {weighted_pct:.1f}%)", f"{m}x", lines

def run_alt_sports_exclude_digital(entries, target_commission):
    lines = []
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))
    pct_tv, pct_rad = (act_tv/tar_tv)*100, (act_rad/tar_rad)*100
    lines.append(f"{'TV Sport Sponsorship':<23} R{act_tv:>11,.2f} | R{tar_tv:>11,.2f} | {pct_tv:>7.1f}% |   (Pooled)")
    lines.append(f"{'Radio Sport Sponsorship':<23} R{act_rad:>11,.2f} | R{tar_rad:>11,.2f} | {pct_rad:>7.1f}% |   (Pooled)")
    lines.append(f"{'Digital (EXCLUDED)':<23} R{0:>11,.2f} | R{0:>11,.2f} | {0:>7.1f}% |   (Ignored)")
    ach_count = int(pct_tv >= 100) + int(pct_rad >= 100)
    if ach_count == 0: return Decimal('0'), "MODE C", "0.00x", lines
    elif ach_count == 1:
        if pct_tv >= 100: return target_commission * Decimal('0.60'), "MODE B (TV)", "60%", lines
        else: return target_commission * Decimal('0.30'), "MODE B (Radio)", "30%", lines
    else:
        weighted_pct = ((Decimal('0.60') * min(pct_tv, 180)) + (Decimal('0.30') * min(pct_rad, 180))) / Decimal('0.90')
        m = get_mult(weighted_pct)
        return target_commission * m, f"MODE A (Weighted {weighted_pct:.1f}%)", f"{m}x", lines

def run_alternative_smme_logic(entries, target_commission, mid_to_use):
    lines = []
    nd = ["Radio Classic", "Radio Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship", "Radio Sport Sponsorship"]
    t_act = sum(Decimal(str(e["act"])) for e in entries if e["name"] in nd)
    t_tar = sum(Decimal(str(e["tar"])) for e in entries if e["name"] in nd)
    ovr = (t_act / t_tar * 100) if t_tar > 0 else Decimal('0')
    cw = {"Radio Classic": Decimal('0.45'), "Radio Sponsorship": Decimal('0.15'), "TV Classic": Decimal('0.24'), "TV Sponsorship": Decimal('0.06'), "TV Sport Sponsorship": Decimal('0.025'), "Radio Sport Sponsorship": Decimal('0.025'), "Digital": Decimal('0.05')}
    comm = Decimal('0')
    for e in entries:
        p = (Decimal(str(e["act"]))/Decimal(str(e["tar"]))*100) if Decimal(str(e["tar"]))>0 else 0
        sc = target_commission * cw.get(e["name"], 0) if (ovr < 100 and p >= 100) else 0
        comm += sc
        lines.append(f"{e['name']:<23} R{e['act']:>11,.2f} | R{e['tar']:>11,.2f} | {p:>7.1f}% | R{sc:>11,.2f}")
    if ovr < 100: return comm, f"Sub-100% Logic ({ovr:.1f}%)", "No Mult", lines
    m = get_mult(ovr); return target_commission * m, f"Mult Triggered ({ovr:.1f}%)", f"{m}x", lines

# --- ENGINE ---
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = str(num_str).strip().replace(' ', '')
    is_neg = num_str.startswith('-')
    parts = num_str.split('.')
    if len(parts) > 1:
        integer = re.sub(r'\D', '', ''.join(parts[:-1]))
        decimal = re.sub(r'\D', '', parts[-1])
        f_str = f"{integer}.{decimal}"
    else: f_str = re.sub(r'\D', '', num_str)
    val = float(f_str) if f_str else 0.0
    return -val if is_neg else val

def extract_file_data(f):
    d = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "sabc_target": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: d["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        fb = f.read()
        if f.name.lower().endswith('.pdf'):
            txt = ""
            try:
                r = PyPDF2.PdfReader(io.BytesIO(fb))
                for p in r.pages: txt += p.extract_text() + "\n"
            except: pass
            if len(txt.strip()) < 50:
                try: txt = fb.decode('utf-8')
                except: txt = fb.decode('latin-1', errors='ignore')
            nt = re.sub(r'\s+', ' ', txt.replace('"', ''))
            dm = re.search(r"Commission Statement for\s+([A-Za-z]+\s+\d{4})", nt, re.I)
            pm = re.search(r"Personnel Number:\s*(\d+)\s+([A-Za-z\s]+?)\s*(?:Position|Target|ZAR)", nt, re.I)
            tm = re.search(r"Target Commission:[^\d]*?([\d\.,]+\.\d{2})", nt, re.I)
            if dm: d["period"] = dm.group(1).strip()
            if pm: d["pers_num"], d["emp_name"] = pm.group(1).strip(), pm.group(2).strip()
            if tm: d["midpoint"] = parse_sabc_number(tm.group(1))
            for s in ALL_SEGMENTS:
                sr = s.replace(' ', r'\s*') + r"s?"
                m = re.search(rf"{sr}[^\d]*?(-?\d[\d\.,]*\.\d{{2}})[^\d]*?(-?\d[\d\.,]*\.\d{{2}})", nt, re.I)
                if m: d["segments"][s]["act"], d["segments"][s]["tar"] = parse_sabc_number(m.group(1)), parse_sabc_number(m.group(2))
            mm = re.search(r"Multiplier Commission[^\d]*?(-?\d[\d\.,]*\.\d{2})[^\d]*?(-?\d[\d\.,]*\.\d{2})", nt, re.I)
            if mm: d["sabc_target"] = parse_sabc_number(mm.group(2))
    except: pass
    return d

def parse_period_sort(p):
    try: return datetime.strptime(p.strip(), "%B %Y")
    except: return datetime.max

# --- UI ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

if "emp_name" not in st.session_state: st.session_state["emp_name"] = ""
if "pers_num" not in st.session_state: st.session_state["pers_num"] = ""
if "period" not in st.session_state: st.session_state["period"] = ""

ct1, ct2 = st.columns(2)
with ct1: selected_profile = st.radio("Select AE Profile / Category:", ["Standard AE / SMME", "Sports PM"], horizontal=True)
with ct2:
    analysis_mode = st.radio("Analysis Mode:", ["Single Statement", "Bulk Statements (Underpayment Summary)"], horizontal=True)
    if analysis_mode == "Single Statement": underpayment_only = st.checkbox("Underpayment Report Only?")

st.divider()

# --- BULK MODE ---
if analysis_mode == "Bulk Statements (Underpayment Summary)":
    uploaded_files = st.file_uploader("Upload all Statements", type=['pdf', 'csv'], accept_multiple_files=True)
    if uploaded_files:
        if not st.session_state["emp_name"]:
            for f in uploaded_files:
                f.seek(0); d = extract_file_data(f)
                if d["emp_name"]: st.session_state["emp_name"], st.session_state["pers_num"] = d["emp_name"], d["pers_num"]
                if st.session_state["emp_name"]: break
    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.text_input("Employee Name:", key="emp_name")
    col_e2.text_input("Personnel Number:", key="pers_num")
    col_e3.text_input("Period (Optional):", key="period")
    scale_curr = st.selectbox("Current Midpoint (Scale):", list(MIDPOINTS_CURRENT.keys()))
    
    if st.button("RUN BULK REPORT", type="primary", use_container_width=True) and uploaded_files:
        mid_c = (Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        bulk_res, total_up = [], Decimal('0')
        for f in uploaded_files:
            f.seek(0); d = extract_file_data(f); ents = []
            for s in ALL_SEGMENTS:
                a, t = d["segments"][s]["act"], d["segments"][s]["tar"]
                if t == 100: t, a = a, 0.0
                ents.append({"name": s, "act": a, "tar": t})
            ms = Decimal(str(d["midpoint"])).quantize(Decimal('0.01'), ROUND_HALF_UP)
            if ms == 0: ms = mid_c
            ta, tt = sum(Decimal(str(e["act"])) for e in ents), sum(Decimal(str(e["tar"])) for e in ents)
            m = get_mult((ta/tt*100) if tt>0 else 0)
            res_s = run_scenario(ents, ms, PROFILES[selected_profile]["statement"], ms*m, 'absorbed')
            res_c = run_scenario(ents, mid_c, PROFILES[selected_profile]["statement"], mid_c*m, 'absorbed')
            diff = res_c['tot'] - res_s['tot']; total_up += diff
            bulk_res.append({"per": d["period"] or "Unknown", "ms": ms, "cs": res_s['tot'], "mc": mid_c, "cc": res_c['tot'], "df": diff})
        bulk_res.sort(key=lambda x: parse_period_sort(x["per"]))
        rep = f"FORENSIC ANALYSIS: UNDERPAYMENT DUE TO WRONG MIDPOINT\nEMPLOYEE: {st.session_state['emp_name']}\n\n"
        rep += f"{'PERIOD':<18} | {'STMT MID':>12} | {'STMT COM':>12} | {'CURR MID':>12} | {'CURR COM':>12} | {'DIFF':>12}\n" + "-"*95 + "\n"
        for r in bulk_res: rep += f"{r['per']:<18} | R{r['ms']:>11,.2f} | R{r['cs']:>11,.2f} | R{r['mc']:>11,.2f} | R{r['cc']:>11,.2f} | R{r['df']:>11,.2f}\n"
        rep += "-"*95 + "\n" + f"{'TOTAL UNDERPAYMENT:':<80} R {total_up:>11,.2f}"
        st.code(rep, language="text")
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0,4,rep.encode('latin-1','replace').decode('latin-1'))
        fname = f"{st.session_state['emp_name'].replace(' ','_')}_Bulk_UNDERPAID.pdf"
        st.download_button("📄 Download Bulk PDF", pdf.output(dest='S').encode('latin-1'), file_name=fname, mime="application/pdf")

# --- SINGLE MODE ---
else:
    for s in ALL_SEGMENTS:
        if f"act_{s}" not in st.session_state: st.session_state[f"act_{s}"] = 0.0
        if f"tar_{s}" not in st.session_state: st.session_state[f"tar_{s}"] = 1.0
    u_file = st.file_uploader("Upload Statement", type=['pdf', 'csv'])
    if u_file:
        d = extract_file_data(u_file)
        st.session_state["period"], st.session_state["pers_num"], st.session_state["emp_name"] = d["period"], d["pers_num"], d["emp_name"]
        st.session_state["midpoint_input_val"], st.session_state["sabc_target_default"] = f"{d['midpoint']:.2f}", f"{d['sabc_target']:.2f}"
        for s in ALL_SEGMENTS: st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = d["segments"][s]["act"], d["segments"][s]["tar"]
    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.text_input("Name:", key="emp_name"); col_e2.text_input("Pers No:", key="pers_num"); col_e3.text_input("Period:", key="period")
    col1, col2 = st.columns([1, 2])
    mid_in = col1.text_input("Stmt Midpoint:", key="midpoint_input_val")
    sabc_t = col1.text_input("SABC Declared Target:", key="sabc_target_default")
    scale_curr = col1.selectbox("Current Midpoint (Scale):", list(MIDPOINTS_CURRENT.keys()))
    scale_2021 = col1.selectbox("2021 Midpoint:", list(MIDPOINTS_2021.keys()))
    
    vis = ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if selected_profile == "Sports PM" else ALL_SEGMENTS
    entries = []
    for s in vis:
        ca, cb, cc, cd = st.columns([3, 2, 2, 1])
        ca.write(s)
        act = cb.number_input(f"Act {s}", key=f"act_{s}", step=1000.0, label_visibility="collapsed")
        tar = cc.number_input(f"Tar {s}", key=f"tar_{s}", step=1000.0, label_visibility="collapsed")
        if cd.button("🔴 Swap", key=f"sw_{s}"): st.session_state[f"tar_{s}"], st.session_state[f"act_{s}"] = st.session_state[f"act_{s}"], 0.0; st.rerun()
        entries.append({"name": s, "act": act, "tar": tar})
    for s in ALL_SEGMENTS:
        if s not in vis: entries.append({"name": s, "act": st.session_state[f"act_{s}"], "tar": st.session_state[f"tar_{s}"]})

    if st.button("RUN FORENSIC COMPARISON", type="primary", use_container_width=True):
        mid_m = Decimal(str(mid_in).replace(',',''))
        mid_c = (Decimal(str(MIDPOINTS_CURRENT[scale_curr])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        mid_21 = (Decimal(str(MIDPOINTS_2021[scale_2021])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        ta, tt = sum(Decimal(str(e["act"])) for e in entries), sum(Decimal(str(e["tar"])) for e in entries)
        rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
        m = get_mult(rev_ach)
        
        m_pay_m, m_pay_c = mid_m * m, mid_c * m
        res_m = run_scenario(entries, mid_m, PROFILES[selected_profile]["statement"], m_pay_m, 'absorbed')
        res_c = run_scenario(entries, mid_c, PROFILES[selected_profile]["statement"], m_pay_c, 'absorbed')
        
        if underpayment_only:
            rep = f"UNDERPAYMENT REPORT: {st.session_state['emp_name']} ({st.session_state['period']})\n"
            rep += f"SABC Payout: R{res_m['tot']:,.2f} | Correct Payout: R{res_c['tot']:,.2f}\n"
            rep += f"UNDERPAYMENT: R{(res_c['tot']-res_m['tot']):,.2f}"
        else:
            # RESTORED 7-SCENARIO LOGIC
            pol_m = run_scenario(entries, mid_m, PROFILES[selected_profile]["policy"], m_pay_m, 'additive')
            pol_21 = run_scenario(entries, mid_21, PROFILES[selected_profile]["policy"], mid_21*m, 'additive')
            pol_c = run_scenario(entries, mid_c, PROFILES[selected_profile]["policy"], mid_c*m, 'additive')
            if selected_profile == "Sports PM":
                alt_6_val, alt_6_mode, alt_6_m, alt_6_lines = run_alt_sports_with_digital(entries, mid_m)
                alt_7_val, alt_7_mode, alt_7_m, alt_7_lines = run_alt_sports_exclude_digital(entries, mid_m)
            else:
                alt_6_val, alt_6_mode, alt_6_m, alt_6_lines = run_alternative_smme_logic(entries, mid_m, mid_m)
                alt_7_val, alt_7_mode, alt_7_m, alt_7_lines = run_alternative_smme_logic(entries, mid_c, mid_c)
            
            s_t = Decimal(str(sabc_t).replace(',',''))
            gap = tt - s_t
            warn = f"!!! SAP ANOMALY: Target manipulated by R{abs(gap):,.2f} !!!\n" if abs(gap)>10 else ""
            
            rep = f"FORENSIC REPORT: {st.session_state['emp_name']} | {st.session_state['period']}\n{warn}\n"
            rep += f"SCENARIO 1 (Stmt Mid): R {res_m['tot']:>12,.2f}\n"
            rep += f"SCENARIO 2 (Curr Mid): R {res_c['tot']:>12,.2f}\n"
            rep += f"SCENARIO 3 (Policy):   R {pol_m['tot']:>12,.2f}\n"
            rep += f"SCENARIO 4 (2021):     R {pol_21['tot']:>12,.2f}\n"
            rep += f"SCENARIO 5 (Policy C): R {pol_c['tot']:>12,.2f}\n"
            rep += f"SCENARIO 6 (Alt A):    R {alt_6_val:>12,.2f}\n"
            rep += f"SCENARIO 7 (SAP Final Analysis): R {alt_7_val:>12,.2f}\n"
            rep += f"\nUNDERPAYMENT: R {(res_c['tot'] - res_m['tot']):,.2f}"

        st.code(rep, language="text")
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=8); pdf.multi_cell(0,4,rep.encode('latin-1','replace').decode('latin-1'))
        fname = f"{st.session_state['emp_name'].replace(' ','_')}_{st.session_state['period'].replace(' ','_')}_UNDERPAID.pdf"
        st.download_button("📄 Download PDF", pdf.output(dest='S').encode('latin-1'), file_name=fname, mime="application/pdf")
