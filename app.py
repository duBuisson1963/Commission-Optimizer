import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- CONFIG ---
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

MIDPOINTS_CURRENT = {'110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250, '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928, '300': 480606, '401': 435116, '402B': 394241, '402': 342045, '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336}
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910, '401': 416379, '402': 327316, '403': 254447, '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634}
ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

def get_mult(score):
    if score < 100: return Decimal('0.00')
    if score == 100: return Decimal('0.50')
    if score <= 120: return Decimal('1.00')
    if score <= 150: return Decimal('2.10')
    if score <= 180: return Decimal('4.10')
    return Decimal('6.20')

def run_scenario_calc(entries, midpoint, weights, multiplier_val, mode):
    lines, sum_seg = [], Decimal('0')
    for e in entries:
        a, t = Decimal(str(e["act"])), Decimal(str(e["tar"]))
        w = Decimal(str(weights.get(e["name"], 0))) / 100
        if w == 0: continue
        ach = (a / t) if t > 0 else Decimal('0')
        sc = (midpoint * w) if ach >= 1.0 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {ach*100:>7.1f}% | R{sc:>11,.2f}")
    m_payout = (midpoint * multiplier_val).quantize(Decimal('0.01'), ROUND_HALF_UP)
    final = max(sum_seg, m_payout) if mode == 'absorbed' else sum_seg + m_payout
    return {"lines": lines, "sum_seg": sum_seg, "m_pay": m_payout, "tot": final}

# --- PARSING ---
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = str(num_str).strip().replace(' ', '')
    is_neg = num_str.startswith('-')
    parts = num_str.split('.')
    if len(parts) > 1:
        f_str = f"{re.sub(r'\D', '', ''.join(parts[:-1]))}.{re.sub(r'\D', '', parts[-1])}"
    else: f_str = re.sub(r'\D', '', num_str)
    val = float(f_str) if f_str else 0.0
    return -val if is_neg else val

def extract_file_data(f):
    d = {"period": "", "pers_num": "", "emp_name": "", "midpoint": 0.0, "sabc_target": 0.0, "segments": {}}
    for s in ALL_SEGMENTS: d["segments"][s] = {"act": 0.0, "tar": 1.0}
    try:
        fb = f.read()
        txt = ""
        if f.name.lower().endswith('.pdf'):
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

# --- INITIALIZE STATE ---
for key in ["emp_name", "pers_num", "period", "midpoint_input_val", "sabc_target_default"]:
    if key not in st.session_state: st.session_state[key] = ""
for s in ALL_SEGMENTS:
    if f"act_{s}" not in st.session_state: st.session_state[f"act_{s}"] = 0.0
    if f"tar_{s}" not in st.session_state: st.session_state[f"tar_{s}"] = 1.0

# --- UI ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

st.sidebar.header("Report Configuration")
show_s = {i: st.sidebar.checkbox(f"Scenario {i}", True) for i in range(1, 8)}

ct1, ct2 = st.columns(2)
with ct1: selected_profile = st.radio("Select Profile:", ["Standard AE / SMME", "Sports PM"], horizontal=True)
with ct2: mode_sel = st.radio("Mode:", ["Single Statement", "Bulk Statements"], horizontal=True)

st.divider()

if mode_sel == "Bulk Statements":
    st.subheader("Bulk Underpayment Compiler")
    up_files = st.file_uploader("Upload Statements", type=['pdf','csv'], accept_multiple_files=True)
    c_e1, c_e2, c_e3 = st.columns(3)
    c_e1.text_input("Employee Name:", key="emp_name")
    c_e2.text_input("Personnel Number:", key="pers_num")
    c_e3.text_input("Period:", key="period")
    scale_curr_bulk = st.selectbox("Current Scale:", list(MIDPOINTS_CURRENT.keys()))
    
    if st.button("RUN BULK REPORT") and up_files:
        mid_c = Decimal(str(MIDPOINTS_CURRENT[scale_curr_bulk])) / 12
        bulk_res, total_up = [], Decimal('0')
        for f in up_files:
            f.seek(0); d = extract_file_data(f); ents = []
            for s in ALL_SEGMENTS:
                a, t = d["segments"][s]["act"], d["segments"][s]["tar"]
                if t == 100: t, a = a, 0.0
                ents.append({"name": s, "act": a, "tar": t})
            ms = Decimal(str(d["midpoint"])) if d["midpoint"] > 0 else mid_c
            ta, tt = sum(Decimal(str(e["act"])) for e in ents), sum(Decimal(str(e["tar"])) for e in ents)
            m = get_mult((ta/tt*100) if tt>0 else 0)
            res_s = run_scenario_calc(ents, ms, PROFILES[selected_profile]["statement"], m, 'absorbed')
            res_c = run_scenario_calc(ents, mid_c, PROFILES[selected_profile]["statement"], m, 'absorbed')
            diff = res_c['tot'] - res_s['tot']; total_up += diff
            bulk_res.append({"per": d["period"], "ms": ms, "cs": res_s['tot'], "mc": mid_c, "cc": res_c['tot'], "df": diff})
        st.code(f"BULK AUDIT: {st.session_state['emp_name']}\nTOTAL UNDERPAYMENT: R {total_up:,.2f}")

else:
    u_file = st.file_uploader("Upload Statement", type=['pdf', 'csv'])
    if u_file:
        d = extract_file_data(u_file)
        # Update session state ONLY if fields are blank to prevent disappearing names
        if not st.session_state["emp_name"]: st.session_state["emp_name"] = d["emp_name"]
        if not st.session_state["pers_num"]: st.session_state["pers_num"] = d["pers_num"]
        if not st.session_state["period"]: st.session_state["period"] = d["period"]
        st.session_state["midpoint_input_val"] = f"{d['midpoint']:.2f}"
        st.session_state["sabc_target_default"] = f"{d['sabc_target']:.2f}"
        for s in ALL_SEGMENTS:
            st.session_state[f"act_{s}"], st.session_state[f"tar_{s}"] = d["segments"][s]["act"], d["segments"][s]["tar"]

    col_e1, col_e2, col_e3 = st.columns(3)
    col_e1.text_input("Employee Name:", key="emp_name")
    col_e2.text_input("Pers No:", key="pers_num")
    col_e3.text_input("Period:", key="period")
    
    ci1, ci2 = st.columns([1, 2])
    with ci1:
        mid_in = st.text_input("Statement Midpoint:", key="midpoint_input_val")
        sabc_t_in = st.text_input("SABC Total Target (Bottom of PDF):", key="sabc_target_default")
        scale_c = st.selectbox("Current Scale (Benchmark):", list(MIDPOINTS_CURRENT.keys()))
        scale_h = st.selectbox("2021 Scale (History):", list(MIDPOINTS_2021.keys()))

    vis = ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"] if selected_profile == "Sports PM" else ALL_SEGMENTS
    entries = []
    for s in vis:
        ca, cb, cc, cd = st.columns([3, 2, 2, 1])
        ca.write(f"**{s}**")
        act_val = cb.number_input(f"Act {s}", key=f"act_{s}", step=100.0, label_visibility="collapsed")
        tar_val = cc.number_input(f"Tar {s}", key=f"tar_{s}", step=100.0, label_visibility="collapsed")
        if cd.button("Swap", key=f"sw_{s}"):
            st.session_state[f"tar_{s}"], st.session_state[f"act_{s}"] = st.session_state[f"act_{s}"], 0.0
            st.rerun()
        entries.append({"name": s, "act": act_val, "tar": tar_val})
    
    # Hidden data preservation
    for s in ALL_SEGMENTS:
        if s not in vis: entries.append({"name": s, "act": st.session_state[f"act_{s}"], "tar": st.session_state[f"tar_{s}"]})

    if st.button("RUN SCENARIO AUDIT", type="primary", use_container_width=True):
        m_stmt = Decimal(str(mid_in).replace(',',''))
        m_curr = Decimal(str(MIDPOINTS_CURRENT[scale_c])) / 12
        m_2021 = Decimal(str(MIDPOINTS_2021[scale_h])) / 12
        t_sabc = Decimal(str(sabc_t_in).replace(',',''))
        
        # MATH AUDIT
        t_act_sum = sum(Decimal(str(e["act"])) for e in entries)
        t_tar_sum = sum(Decimal(str(e["tar"])) for e in entries)
        
        m_actual = get_mult((t_act_sum / t_tar_sum * 100) if t_tar_sum > 0 else 0)
        m_printed = get_mult((t_act_sum / t_sabc * 100) if t_sabc > 0 else 0)
        
        sc_res = {
            1: run_scenario_calc(entries, m_stmt, PROFILES[selected_profile]["statement"], m_printed, 'absorbed'),
            2: run_scenario_calc(entries, m_curr, PROFILES[selected_profile]["statement"], m_printed, 'absorbed'),
            3: run_scenario_calc(entries, m_stmt, PROFILES[selected_profile]["policy"], m_actual, 'additive'),
            4: run_scenario_calc(entries, m_2021, PROFILES[selected_profile]["policy"], m_actual, 'additive'),
            5: run_scenario_calc(entries, m_curr, PROFILES[selected_profile]["policy"], m_actual, 'additive'),
            7: run_scenario_calc(entries, m_curr, PROFILES[selected_profile]["statement"], m_actual, 'absorbed')
        }

        full_rep = f"FORENSIC AUDIT: {st.session_state['emp_name']} | {st.session_state['period']}\n\n"
        
        def add_block(title, res, mid_v, lbl):
            b = f"--- {title} ---\nMIDPOINT: R {mid_v:,.2f} ({lbl})\n"
            b += f"{'STREAM':<23} {'ACTUAL':>13} | {'TARGET':>13} | {'% ACH':>8} | {'COMMISSION':>13}\n" + "-"*81 + "\n"
            b += "\n".join(res['lines']) + "\n" + "-"*81 + "\n"
            b += f"MULTIPLIER COMMISSION: R {res['m_pay']:>12,.2f}\nTOTAL PAYOUT: R {res['tot']:>12,.2f}\n\n"
            return b

        if show_s[1]: full_rep += add_block("SCENARIO 1: SABC BASELINE", sc_res[1], m_stmt, "As Printed")
        if show_s[2]: full_rep += add_block("SCENARIO 2: SABC WEIGHTS + CORRECT MIDPOINT", sc_res[2], m_curr, f"Scale {scale_c}")
        if show_s[3]: full_rep += add_block("SCENARIO 3: POLICY WEIGHTS + STMT MIDPOINT", sc_res[3], m_stmt, "As Printed")
        if show_s[4]: full_rep += add_block("SCENARIO 4: POLICY WEIGHTS + 2021 MIDPOINT", sc_res[4], m_2021, f"Scale {scale_h}")
        if show_s[5]: full_rep += add_block("SCENARIO 5: POLICY WEIGHTS + CORRECT MIDPOINT", sc_res[5], m_curr, f"Scale {scale_c}")
        
        if show_s[7]:
            gap = t_tar_sum - t_sabc
            anom = f"!!! SAP SYSTEM ANOMALY: Total Target gap of R {abs(gap):,.2f} detected !!!\n" if abs(gap) > 10 else ""
            full_rep += f"--- SCENARIO 7: SAP FINAL ANALYSIS ---\n{anom}"
            full_rep += f"Calculated Total Segment Targets: R {t_tar_sum:,.2f}\n"
            full_rep += add_block("FINAL CLEAN AUDIT (Correct Sum of Parts + Correct Scale)", sc_res[7], m_curr, f"Scale {scale_c}")

        st.code(full_rep)
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=7); pdf.multi_cell(0, 3.5, full_rep.encode('latin-1','replace').decode('latin-1'))
        st.download_button("Download PDF", pdf.output(dest='S').encode('latin-1'), file_name=f"{st.session_state['emp_name']}_Audit.pdf")
