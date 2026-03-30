import streamlit as st
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

# --- BASELINE WEIGHTS (v10.35) ---
STATEMENT_W = {
    "Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
    "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 
2.5, "Radio Sport Sponsorship": 2.5
}

POLICY_W = {
    "TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0,
    "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 
2.5, "Radio Sport Sponsorship": 2.5
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
    midpoint_input = st.text_input("Target Commission (Midpoint):", 
value="27276.33")
with col2:
    uploaded_file = st.file_uploader("Upload SABC Statement (CSV or Excel)", type=['csv', 'xlsx'])

segments = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]
entries = []

st.subheader("Manual Entry / Verification")
# Create a grid for the inputs
cols = st.columns(3)
cols[0].write("**Segment Name**")
cols[1].write("**Actual Revenue**")
cols[2].write("**Target Revenue**")

# Default values
form_data = {s: {"act": 0.0, "tar": 1.0} for s in segments}

# Process Uploaded File
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, encoding='latin-1')
        else:
            df = pd.read_excel(uploaded_file)
            
        for _, row in df.iterrows():
            seg_name = str(row.get('Segment', '')).strip()
            # Try to match the segment name case-insensitively
            for s in segments:
                if seg_name.lower() == s.lower():
                    form_data[s]["act"] = float(row.get('Actuals', 
row.get('Actual', 0)))
                    form_data[s]["tar"] = float(row.get('Target', 1))
        st.success("File loaded successfully!")
    except Exception as e:
        st.error(f"Error reading file: {e}")

# Build the form rows
for s in segments:
    col_a, col_b, col_c = st.columns(3)
    col_a.write(s)
    act = col_b.number_input(f"Act {s}", value=float(form_data[s]["act"]), 
step=1000.0, label_visibility="collapsed")
    tar = col_c.number_input(f"Tar {s}", value=float(form_data[s]["tar"]), 
step=1000.0, label_visibility="collapsed")
    entries.append({"name": s, "act": act, "tar": tar})

# --- CALCULATION ---
if st.button("RUN FORENSIC COMPARISON", type="primary", 
use_container_width=True):
    try:
        mid = Decimal(str(midpoint_input).replace(',', ''))
        ta = sum(Decimal(str(e["act"])) for e in entries)
        tt = sum(Decimal(str(e["tar"])) for e in entries)
        
        rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
        m = get_mult(rev_ach)
        m_pay = (mid * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
        
        applied = run_scenario(entries, mid, STATEMENT_W, m_pay, 
'absorbed')
        policy = run_scenario(entries, mid, POLICY_W, m_pay, 'additive')
        
        st.header(f"SABC APPLIED PAYOUT: R {applied['tot']:,.2f}")
        
        # Output Texts
        audit1 = f"--- SCENARIO 1: SABC APPLIED CALCULATION ---\n"
        audit1 += f"Weights Applied: 45/24/6 | Total Ach: {rev_ach}% | Mult: {m}x\n"
        audit1 += f"{'STREAM':<25} {'% ACH':>8} {'SABC PAID':>14}\n" + "-"*50 + "\n"
        audit1 += "\n".join(applied["lines"]) + "\n" + "-"*50 + "\n"
        audit1 += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
        audit1 += f"{'FINAL SABC PAYOUT (Absorbed):':<35} R 
{applied['tot']:>12,.2f}\n"

        audit2 = f"--- SCENARIO 2: POLICY DICTATED CALCULATION ---\n"
        audit2 += f"Weights Applied: 40/30/10 | Total Ach: {rev_ach}% | 
Mult: {m}x\n"
        audit2 += f"{'STREAM':<25} {'% ACH':>8} {'POLICY DUE':>14}\n" + 
"-"*50 + "\n"
        audit2 += "\n".join(policy["lines"]) + "\n" + "-"*50 + "\n"
        audit2 += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
        audit2 += f"{'FINAL POLICY DUE (Additive):':<35} R 
{policy['tot']:>12,.2f}\n"

        shortfall = policy['tot'] - applied['tot']
        
        adv = "--- FORENSIC DISCREPANCY SUMMARY ---\n\n"
        adv += f"1. SABC APPLIED PAYOUT:  R {applied['tot']:,.2f}\n"
        adv += f"2. POLICY DICTATED DUE:  R {policy['tot']:,.2f}\n" + 
"-"*40 + "\n"
        adv += f"TOTAL SHORTFALL OWED:    R {shortfall:,.2f}\n"

        col_out1, col_out2 = st.columns(2)
        with col_out1:
            st.code(audit1 + "\n\n" + audit2, language="text")
        with col_out2:
            st.code(adv, language="text")
            
    except Exception as e:
        st.error(f"Calculation Error: Check inputs. Details: {e}")
