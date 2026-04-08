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
MIDPOINTS_2021 = {'110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, '120': 1650000, '125': 1175508, '130': 904237, '300': 459910}
MIDPOINTS_CURRENT = {'110A': 3459277, '110B': 2767421, '115A': 2213937, '115B': 1844948, '120': 1724250, '125': 1228406, '130': 944928}

ALL_SEGMENTS = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]

# --- FIXED MULTIPLIER ---
def get_mult(score):
    score = Decimal(str(score))
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
    return float(num_str.replace(",", ""))

# --- FIXED EXTRACTION (WITH EXCEL + ERROR) ---
@st.cache_data
def extract_file_data(file_obj):
    data = {"segments": {}}
    for s in ALL_SEGMENTS:
        data["segments"][s] = {"act": 0.0, "tar": 1.0}

    try:
        file_bytes = file_obj.read()

        if file_obj.name.lower().endswith('.pdf'):
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for p in reader.pages:
                text += p.extract_text() or ""

            for s in ALL_SEGMENTS:
                pattern = rf"{s}[^\d]*?(\d[\d,]+\.\d{{2}})[^\d]*?(\d[\d,]+\.\d{{2}})"
                m = re.search(pattern, text)
                if m:
                    data["segments"][s]["act"] = parse_sabc_number(m.group(1))
                    data["segments"][s]["tar"] = parse_sabc_number(m.group(2))

        elif file_obj.name.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_bytes))

        elif file_obj.name.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_bytes))

        if 'df' in locals():
            for _, row in df.iterrows():
                seg = str(row.get("Segment", "")).strip()
                for s in ALL_SEGMENTS:
                    if seg.lower() == s.lower():
                        data["segments"][s]["act"] = float(row.get("Actual", 0))
                        data["segments"][s]["tar"] = float(row.get("Target", 1))

    except Exception as e:
        st.error(f"Extraction failed: {e}")

    return data

# --- UI ---
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

uploaded_file = st.file_uploader("Upload Statement", type=['pdf','csv','xlsx'])

entries = []
if uploaded_file:
    data = extract_file_data(uploaded_file)
    for s in ALL_SEGMENTS:
        entries.append({"name": s, "act": data["segments"][s]["act"], "tar": data["segments"][s]["tar"]})

# ---------------- SAP MODULE ----------------
st.divider()
st.subheader("SAP Data Upload (Optional)")

sap_file = st.file_uploader("Upload SAP Data", type=['xlsx','csv'], key="sap")

sap_entries = []

if sap_file:
    try:
        sap_df = pd.read_excel(sap_file) if sap_file.name.endswith('.xlsx') else pd.read_csv(sap_file)

        seg_col = st.selectbox("Segment Column", sap_df.columns)
        act_col = st.selectbox("Actual Column", sap_df.columns)
        tar_col = st.selectbox("Target Column", ["None"] + list(sap_df.columns))

        mapping = {}
        for s in ALL_SEGMENTS:
            mapping[s] = st.text_input(f"Keyword for {s}", value=s)

        if st.button("Process SAP Data"):
            for s in ALL_SEGMENTS:
                filt = sap_df[sap_df[seg_col].astype(str).str.contains(mapping[s], case=False, na=False)]
                act_val = filt[act_col].sum()
                tar_val = filt[tar_col].sum() if tar_col != "None" else 1.0
                sap_entries.append({"name": s, "act": act_val, "tar": tar_val})

            st.session_state["sap_entries"] = sap_entries
            st.success("SAP processed")

    except Exception as e:
        st.error(f"SAP error: {e}")

# ---------------- RUN ----------------
if st.button("RUN FORENSIC COMPARISON"):

    if not entries:
        st.error("Upload statement first")
    else:
        weights = PROFILES["Standard AE / SMME"]["statement"]
        mid = (Decimal(MIDPOINTS_CURRENT['130'])/12)

        ta = sum(Decimal(str(e["act"])) for e in entries)
        tt = sum(Decimal(str(e["tar"])) for e in entries)
        pct = (ta/tt*100) if tt>0 else Decimal('0')

        m = get_mult(pct)
        m_pay = mid*m

        applied = run_scenario(entries, mid, weights, m_pay, 'absorbed')

        rep = "--- STATEMENT CALCULATION ---\n"
        rep += "\n".join(applied["lines"])
        rep += f"\nTOTAL: R {applied['tot']:,.2f}\n\n"

        # SAP EXTENSION
        sap_entries = st.session_state.get("sap_entries", [])

        if sap_entries:
            rep += "--- SAP RECONCILIATION ---\n"

            for s in ALL_SEGMENTS:
                stmt = next(e["act"] for e in entries if e["name"]==s)
                sap = next((e["act"] for e in sap_entries if e["name"]==s),0)
                rep += f"{s:<23} {stmt:>12,.2f} {sap:>12,.2f} {(sap-stmt):>12,.2f}\n"

            ta_sap = sum(Decimal(str(e["act"])) for e in sap_entries)
            tt_sap = sum(Decimal(str(e["tar"])) for e in sap_entries)
            pct_sap = (ta_sap/tt_sap*100) if tt_sap>0 else Decimal('0')

            m_sap = get_mult(pct_sap)
            m_pay_sap = mid*m_sap

            sap_calc = run_scenario(sap_entries, mid, weights, m_pay_sap, 'absorbed')

            rep += f"\nCORRECT (SAP): R {sap_calc['tot']:,.2f}\n"
            rep += f"UNDERPAYMENT: R {(sap_calc['tot'] - applied['tot']):,.2f}\n"

        st.code(rep)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, rep)

        st.download_button("Download PDF", pdf.output(dest='S').encode('latin-1'), "report.pdf")
