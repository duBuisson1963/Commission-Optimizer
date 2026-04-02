import streamlit as st
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF

# --- PROFILE WEIGHTS ---
PROFILES = {
    "Standard AE / SMME": {
        "statement": {
            "Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
            "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
        },
        "policy": {
            "TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0,
            "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
        },
        "display_stmt": "45/24/6",
        "display_pol": "40/30/10"
    },
    "Sports PM": {
        "statement": {
            "Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0,
            "Radio Classic": 0.0, "TV Classic": 0.0, "TV Sponsorship": 0.0, "Radio Sponsorship": 0.0
        },
        "policy": {
            "Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0,
            "Radio Classic": 0.0, "TV Classic": 0.0, "TV Sponsorship": 0.0, "Radio Sponsorship": 0.0
        },
        "display_stmt": "10/30/60",
        "display_pol": "10/30/60"
    }
}

# --- SALARY SCALES (ANNUAL) ---
MIDPOINTS_2021 = {
    '110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000,
    '125': 1175508, '130': 904237,
    '300': 459910, '401': 416379, '402': 327316, '403': 254447, 
    '404': 199286, '405': 153057, '406': 135132, '407': 100704, '408': 71634
}

MIDPOINTS_CURRENT = {
    '110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, '115A': 2213937, '115B': 1844948, '120': 1724250,
    '125A': 1412667, '125': 1228406, '130A': 1091391, '130B': 1039420, '130': 944928,
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

# --- COPILOT LOGIC IMPLEMENTATION ---
def run_copilot_logic(entries, target_commission):
    # Extract values safely
    act_tv = next((Decimal(str(e["act"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('0'))
    tar_tv = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "TV Sport Sponsorship"), Decimal('1'))
    act_rad = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('0'))
    tar_rad = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Radio Sport Sponsorship"), Decimal('1'))
    act_dig = next((Decimal(str(e["act"])) for e in entries if e["name"] == "Digital"), Decimal('0'))
    tar_dig = next((Decimal(str(e["tar"])) for e in entries if e["name"] == "Digital"), Decimal('1'))

    # Step 1: Percentages
    pct_tv = (act_tv / tar_tv) * 100 if tar_tv > 0 else Decimal('0')
    pct_rad = (act_rad / tar_rad) * 100 if tar_rad > 0 else Decimal('0')
    pct_dig = (act_dig / tar_dig) * 100 if tar_dig > 0 else Decimal('0')

    # Step 2: Achievements
    ach_tv = pct_tv >= 100
    ach_rad = pct_rad >= 100
    ach_count = int(ach_tv) + int(ach_rad)

    # Mode Logic
    if ach_count == 0:
        return Decimal('0'), "MODE C (No Sport Targets Hit)", "0.00x", Decimal('0')
    
    elif ach_count == 1:
        if ach_tv:
            payout = target_commission * Decimal('0.60')
            return payout, "MODE B (TV Only Fallback)", "Fallback (60%)", pct_tv
        else:
            payout = target_commission * Decimal('0.30')
            return payout, "MODE B (Radio Only Fallback)", "Fallback (30%)", pct_rad
            
    else:
        # Mode A: Both Achieved (Weighted with 180 cap)
        pct_tv_cap = min(pct_tv, Decimal('180'))
        pct_rad_cap = min(pct_rad, Decimal('180'))
        pct_dig_cap = min(pct_dig, Decimal('180'))
        
        weighted_pct = (Decimal('0.60') * pct_tv_cap) + (Decimal('0.30') * pct_rad_cap) + (Decimal('0.10') * pct_dig_cap)
        
        if weighted_pct < 100: mult = Decimal('0.00')
        elif weighted_pct <= 120: mult = Decimal('1.00')
        elif weighted_pct <= 150: mult = Decimal('2.10')
        else: mult = Decimal('4.10') # Capped per Copilot
        
        payout = target_commission * mult
        return payout, f"MODE A (Both Hit - {weighted_pct:.1f}% Weighted)", f"{mult}x", weighted_pct

# --- UI SETUP ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

selected_profile = st.radio("Select AE Profile / Category:", ["Standard AE / SMME", "Sports PM"], horizontal=True)
st.divider()

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
        policy_manual  = run_scenario(entries, mid_manual, active_pol_w, m_pay_manual, 'additive')
        policy_2021    = run_scenario(entries, mid_2021, active_pol_w, m_pay_2021, 'additive')
        policy_curr    = run_scenario(entries, mid_curr, active_pol_w, m_pay_curr, 'additive')
        
        st.header(f"SABC APPLIED PAYOUT (Manual Midpoint): R {applied_manual['tot']:,.2f}")
        
        def build_audit_block(title, mid_val, mid_label, weights, lines, m_pay, tot, label_tot):
            b = f"--- {title} ---\n"
            b += f"Profile: {selected_profile}\n"
            b += f"Midpoint Used: R {mid_val:,.2f} {mid_label}\n"
            b += f"Weights Applied: {weights} | Total Ach: {rev_ach}% | Mult: {m}x\n"
            b += f"{'STREAM':<25} {'% ACH':>8} {'PAYOUT DUE':>14}\n" + "-"*50 + "\n"
            b += "\n".join(lines) + "\n" + "-"*50 + "\n"
            b += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
            b += f"{label_tot:<35} R {tot:>12,.2f}\n"
            return b

        audit1 = build_audit_block("SCENARIO 1: SABC APPLIED (MANUAL MIDPOINT)", mid_manual, "(Manual Entry)", str_stmt, applied_manual["lines"], m_pay_manual, applied_manual["tot"], "FINAL SABC PAYOUT (Absorbed):")
        audit2 = build_audit_block("SCENARIO 2: SABC APPLIED (CURRENT SCALES)", mid_curr, f"(Scale {scale_current} / 12)", str_stmt, applied_curr["lines"], m_pay_curr, applied_curr["tot"], "FINAL SABC PAYOUT (Absorbed):")
        audit3 = build_audit_block("SCENARIO 3: POLICY DICTATED (MANUAL MIDPOINT)", mid_manual, "(Manual Entry)", str_pol, policy_manual["lines"], m_pay_manual, policy_manual["tot"], "FINAL POLICY DUE (Additive):")
        audit4 = build_audit_block("SCENARIO 4: POLICY DICTATED (2021 SCALES)", mid_2021, f"(Scale {scale_2021} / 12)", str_pol, policy_2021["lines"], m_pay_2021, policy_2021["tot"], "FINAL POLICY DUE (Additive):")
        audit5 = build_audit_block("SCENARIO 5: POLICY DICTATED (CURRENT SCALES)", mid_curr, f"(Scale {scale_current} / 12)", str_pol, policy_curr["lines"], m_pay_curr, policy_curr["tot"], "FINAL POLICY DUE (Additive):")

        # COPILOT SCENARIO (ONLY FOR SPORTS PM)
        audit6 = ""
        copilot_tot = Decimal('0')
        if selected_profile == "Sports PM":
            copilot_tot, c_mode, c_mult, c_ach = run_copilot_logic(entries, mid_manual)
            audit6 = f"--- SCENARIO 6: COPILOT SUGGESTED LOGIC (SPORTS PM ONLY) ---\n"
            audit6 += f"Logic Rule: {c_mode}\n"
            audit6 += f"Capped Multiplier Applied: {c_mult}\n"
            audit6 += "-"*50 + "\n"
            audit6 += f"FINAL COPILOT PAYOUT (Manual Midpoint): R {copilot_tot:>12,.2f}\n\n"

        adv = "--- FORENSIC DISCREPANCY SUMMARY ---\n\n"
        adv += f"Profile Audited: {selected_profile}\n\n"
        adv += f"1. SABC APPLIED (Manual):                R {applied_manual['tot']:>12,.2f}\n"
        adv += f"2. SABC APPLIED @ Current (Scale {scale_current:<4}):  R {applied_curr['tot']:>12,.2f}\n"
        adv += f"3. POLICY DUE (Manual):                  R {policy_manual['tot']:>12,.2f}\n"
        adv += f"4. POLICY DUE @ 2021 (Scale {scale_2021:<4}):      R {policy_2021['tot']:>12,.2f}\n"
        adv += f"5. POLICY DUE @ Current (Scale {scale_current:<4}):   R {policy_curr['tot']:>12,.2f}\n"
        if selected_profile == "Sports PM":
            adv += f"6. COPILOT SUGGESTED LOGIC:              R {copilot_tot:>12,.2f}\n"
        adv += "-"*56 + "\n"
        adv += f"SHORTFALL A (Policy Manual vs SABC Manual):   R {(policy_manual['tot'] - applied_manual['tot']):>12,.2f}\n"
        adv += f"SHORTFALL B (Policy Current vs SABC Current): R {(policy_curr['tot'] - applied_curr['tot']):>12,.2f}\n"
        adv += f"ULTIMATE SHORTFALL (Policy Curr vs SABC Man): R {(policy_curr['tot'] - applied_manual['tot']):>12,.2f}\n"

        col_out1, col_out2 = st.columns(2)
        with col_out1: 
            st.code(audit1 + "\n\n" + audit2 + "\n\n" + audit3, language="text")
        with col_out2: 
            st.code(audit4 + "\n\n" + audit5 + ("\n\n" + audit6 if audit6 else ""), language="text")
        st.code(adv, language="text")
            
        full_report = audit1 + "\n\n" + audit2 + "\n\n" + audit3 + "\n\n" + audit4 + "\n\n" + audit5 + ("\n\n" + audit6 if audit6 else "") + "\n\n" + adv
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, full_report.encode('latin-1', 'replace').decode('latin-1'))
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        
        st.download_button(
            label="📄 Download Full PDF Audit Report",
            data=pdf_bytes,
            file_name=f"BEMAWU_Audit_{selected_profile.replace(' ', '_').replace('/', '')}.pdf",
            mime="application/pdf",
            type="primary"
        )
            
    except Exception as e:
        st.error(f"Calculation Error: Check inputs. Details: {e}")
