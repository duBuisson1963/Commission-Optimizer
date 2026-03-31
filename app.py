import streamlit as st
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF

# --- BASELINE WEIGHTS (v10.35) ---
STATEMENT_W = {
    "Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
    "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
}

POLICY_W = {
    "TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0,
    "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
}

# --- SALARY SCALES (ANNUAL) ---
MIDPOINTS_2021 = {
    '300': 459910, '401': 416379, '402': 327316, '403': 254447, 
    '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634
}

MIDPOINTS_CURRENT = {
    '300': 480606, '401': 435116, '402B': 394241, '402': 342045, 
    '403': 265897, '404': 208254, '405': 159945, '405A': 141872, '406B': 122336
}

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
        ach = a / t if t > 0 else Decimal('0')
        sc = (mid * w) if ach >= 1.0 else Decimal('0')
        sum_seg += sc
        lines.append(f"{e['name']:<25} {ach*100:>7.1f}% R {sc:>12,.2f}")
    
    total = max(sum_seg, m_pay) if logic_type == 'absorbed' else sum_seg + m_pay
    return {"lines": lines, "tot": total}

# --- UI SETUP ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

# --- INPUTS ---
col1, col2 = st.columns([1, 2])
with col1:
    midpoint_input = st.text_input("Target Commission (Manual Midpoint):", value="27276.33")
    scale_2021 = st.selectbox("2021 Midpoints (Scale Code):", list(MIDPOINTS_2021.keys()))
    scale_current = st.selectbox("Current Midpoints (Scale Code):", list(MIDPOINTS_CURRENT.keys()))
    
with col2:
    uploaded_file = st.file_uploader("Upload SABC Statement (CSV or Excel)", type=['csv', 'xlsx'])

segments = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]
entries = []

st.subheader("Manual Entry / Verification")
cols = st.columns(3)
cols[0].write("**Segment Name**")
cols[1].write("**Actual Revenue**")
cols[2].write("**Target Revenue**")

form_data = {s: {"act": 0.0, "tar": 1.0} for s in segments}

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, encoding='latin-1')
        else:
            df = pd.read_excel(uploaded_file)
            
        for _, row in df.iterrows():
            seg_name = str(row.get('Segment', '')).strip()
            for s in segments:
                if seg_name.lower() == s.lower():
                    form_data[s]["act"] = float(row.get('Actuals', row.get('Actual', 0)))
                    form_data[s]["tar"] = float(row.get('Target', 1))
        st.success("File loaded successfully!")
    except Exception as e:
        st.error(f"Error reading file: {e}")

for s in segments:
    col_a, col_b, col_c = st.columns(3)
    col_a.write(s)
    act = col_b.number_input(f"Act {s}", value=float(form_data[s]["act"]), step=1000.0, label_visibility="collapsed")
    tar = col_c.number_input(f"Tar {s}", value=float(form_data[s]["tar"]), step=1000.0, label_visibility="collapsed")
    entries.append({"name": s, "act": act, "tar": tar})

# --- CALCULATION ---
if st.button("RUN FORENSIC COMPARISON", type="primary", use_container_width=True):
    try:
        # Base Midpoints
        mid_manual = Decimal(str(midpoint_input).replace(',', ''))
        mid_2021 = (Decimal(str(MIDPOINTS_2021[scale_2021])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        mid_curr = (Decimal(str(MIDPOINTS_CURRENT[scale_current])) / 12).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        # Achievement & Multiplier
        ta = sum(Decimal(str(e["act"])) for e in entries)
        tt = sum(Decimal(str(e["tar"])) for e in entries)
        rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
        m = get_mult(rev_ach)
        
        # Multiplier Payouts based on midpoints
        m_pay_manual = (mid_manual * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
        m_pay_2021 = (mid_2021 * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
        m_pay_curr = (mid_curr * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        # Scenario Runs
        applied = run_scenario(entries, mid_manual, STATEMENT_W, m_pay_manual, 'absorbed')
        policy_man = run_scenario(entries, mid_manual, POLICY_W, m_pay_manual, 'additive')
        policy_2021 = run_scenario(entries, mid_2021, POLICY_W, m_pay_2021, 'additive')
        policy_curr = run_scenario(entries, mid_curr, POLICY_W, m_pay_curr, 'additive')
        
        st.header(f"SABC APPLIED PAYOUT (Manual Midpoint): R {applied['tot']:,.2f}")
        
        # --- GENERATE STRINGS ---
        def build_audit_block(title, mid_val, mid_label, weights, lines, m_pay, tot, label_tot):
            b = f"--- {title} ---\n"
            b += f"Midpoint Used: R {mid_val:,.2f} {mid_label}\n"
            b += f"Weights Applied: {weights} | Total Ach: {rev_ach}% | Mult: {m}x\n"
            b += f"{'STREAM':<25} {'% ACH':>8} {'PAYOUT DUE':>14}\n" + "-"*50 + "\n"
            b += "\n".join(lines) + "\n" + "-"*50 + "\n"
            b += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
            b += f"{label_tot:<35} R {tot:>12,.2f}\n"
            return b

        audit1 = build_audit_block(
            "SCENARIO 1: SABC APPLIED CALCULATION", mid_manual, "(Manual Entry)", "45/24/6", 
            applied["lines"], m_pay_manual, applied["tot"], "FINAL SABC PAYOUT (Absorbed):"
        )
        audit2 = build_audit_block(
            "SCENARIO 2: POLICY DICTATED CALCULATION", mid_manual, "(Manual Entry)", "40/30/10", 
            policy_man["lines"], m_pay_manual, policy_man["tot"], "FINAL POLICY DUE (Additive):"
        )
        audit3 = build_audit_block(
            "SCENARIO 3: POLICY DICTATED (2021 SCALES)", mid_2021, f"(Scale {scale_2021} / 12)", "40/30/10", 
            policy_2021["lines"], m_pay_2021, policy_2021["tot"], "FINAL POLICY DUE (Additive):"
        )
        audit4 = build_audit_block(
            "SCENARIO 4: POLICY DICTATED (CURRENT SCALES)", mid_curr, f"(Scale {scale_current} / 12)", "40/30/10", 
            policy_curr["lines"], m_pay_curr, policy_curr["tot"], "FINAL POLICY DUE (Additive):"
        )

        adv = "--- FORENSIC DISCREPANCY SUMMARY ---\n\n"
        adv += f"1. SABC APPLIED PAYOUT (Manual):         R {applied['tot']:>12,.2f}\n"
        adv += f"2. POLICY DICTATED DUE (Manual):         R {policy_man['tot']:>12,.2f}\n"
        adv += f"3. POLICY DUE @ 2021 (Scale {scale_2021:<4}):      R {policy_2021['tot']:>12,.2f}\n"
        adv += f"4. POLICY DUE @ Current (Scale {scale_current:<4}):   R {policy_curr['tot']:>12,.2f}\n"
        adv += "-"*56 + "\n"
        adv += f"SHORTFALL 1 (Policy vs Applied):         R {(policy_man['tot'] - applied['tot']):>12,.2f}\n"
        adv += f"SHORTFALL 2 (2021 vs Applied):           R {(policy_2021['tot'] - applied['tot']):>12,.2f}\n"
        adv += f"SHORTFALL 3 (Current vs Applied):        R {(policy_curr['tot'] - applied['tot']):>12,.2f}\n"

        # --- DISPLAY ---
        col_out1, col_out2 = st.columns(2)
        with col_out1: st.code(audit1 + "\n\n" + audit2, language="text")
        with col_out2: st.code(audit3 + "\n\n" + audit4, language="text")
        st.code(adv, language="text")
            
        # --- PDF GENERATION ---
        full_report = audit1 + "\n\n" + audit2 + "\n\n" + audit3 + "\n\n" + audit4 + "\n\n" + adv
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, full_report.encode('latin-1', 'replace').decode('latin-1'))
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        
        st.download_button(
            label="📄 Download Full PDF Audit Report",
            data=pdf_bytes,
            file_name="BEMAWU_Comprehensive_Forensic_Audit.pdf",
            mime="application/pdf",
            type="primary"
        )
            
    except Exception as e:
        st.error(f"Calculation Error: Check inputs. Details: {e}")
