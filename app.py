import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# ---------------- CONFIG ----------------
st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
st.title("BEMAWU Dual-Profile Forensic Simulator")

ALL_SEGMENTS = [
    "Digital", "Radio Classic", "Radio Sponsorship",
    "Radio Sport Sponsorship", "TV Classic",
    "TV Sponsorship", "TV Sport Sponsorship"
]

PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
                      "Radio Sponsorship": 15.0, "Digital": 5.0,
                      "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5},
        "display_stmt": "45/24/6"
    }
}

MIDPOINTS_CURRENT = {
    '130': 944928, '125': 1228406, '120': 1724250
}

# ---------------- MULTIPLIER ----------------
def get_mult(score):
    score = Decimal(str(score))
    if score < 100: return Decimal('0.00')
    elif score == 100: return Decimal('0.50')
    elif score <= 120: return Decimal('1.00')
    elif score <= 150: return Decimal('2.10')
    elif score <= 180: return Decimal('4.10')
    else: return Decimal('6.20')

# ---------------- HELPERS ----------------
def parse_sabc_number(num_str):
    if not num_str: return 0.0
    num_str = num_str.replace(",", "")
    return float(num_str)

# ---------------- SCENARIO ----------------
def run_scenario(entries, mid, w_map, m_pay):
    lines, sum_seg = [], Decimal('0')

    for e in entries:
        a = Decimal(str(e["act"]))
        t = Decimal(str(e["tar"]))
        w = Decimal(str(w_map.get(e["name"], 0))) / 100

        if w == 0:
            continue

        ach = a / t if t > 0 else Decimal('0')
        sc = (mid * w) if ach >= 1 else Decimal('0')

        sum_seg += sc

        lines.append(
            f"{e['name']:<23} R{a:>11,.2f} | R{t:>11,.2f} | {ach*100:>7.1f}% | R{sc:>11,.2f}"
        )

    total = max(sum_seg, m_pay)
    return {"lines": lines, "sum_seg": sum_seg, "tot": total}

# ---------------- FILE EXTRACTION ----------------
@st.cache_data
def extract_file_data(file_obj):
    data = {s: {"act": 0.0, "tar": 1.0} for s in ALL_SEGMENTS}

    try:
        file_bytes = file_obj.read()

        if file_obj.name.lower().endswith('.pdf'):
            reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for p in reader.pages:
                text += p.extract_text() or ""

            for s in ALL_SEGMENTS:
                pattern = rf"{s}[^\d]*?(-?\d[\d,]+\.\d{{2}})[^\d]*?(-?\d[\d,]+\.\d{{2}})"
                match = re.search(pattern, text)
                if match:
                    data[s]["act"] = parse_sabc_number(match.group(1))
                    data[s]["tar"] = parse_sabc_number(match.group(2))

        elif file_obj.name.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_bytes))

        elif file_obj.name.lower().endswith('.xlsx'):
            df = pd.read_excel(io.BytesIO(file_bytes))

        if 'df' in locals():
            for _, row in df.iterrows():
                seg = str(row.get("Segment", "")).strip()

                for s in ALL_SEGMENTS:
                    if seg.lower() == s.lower():
                        data[s]["act"] = float(row.get("Actual", 0))
                        data[s]["tar"] = float(row.get("Target", 1))

    except Exception as e:
        st.error(f"Extraction error: {e}")

    return data

# ---------------- UI ----------------
stmt_file = st.file_uploader("Upload Commission Statement", type=["pdf", "csv", "xlsx"])

entries = []

if stmt_file:
    stmt_data = extract_file_data(stmt_file)

    for s in ALL_SEGMENTS:
        entries.append({
            "name": s,
            "act": stmt_data[s]["act"],
            "tar": stmt_data[s]["tar"]
        })

    st.success("Statement Loaded")

# ---------------- SAP MODULE ----------------
st.divider()
st.header("SAP DATA RECONCILIATION (OPTIONAL)")

sap_file = st.file_uploader("Upload SAP Data", type=["xlsx", "csv"], key="sap")

sap_entries = []

if sap_file:
    try:
        if sap_file.name.endswith('.xlsx'):
            sap_df = pd.read_excel(sap_file)
        else:
            sap_df = pd.read_csv(sap_file)

        seg_col = st.selectbox("Segment Column", sap_df.columns)
        act_col = st.selectbox("Actual Column", sap_df.columns)
        tar_col = st.selectbox("Target Column", ["None"] + list(sap_df.columns))

        mapping = {}
        for s in ALL_SEGMENTS:
            mapping[s] = st.text_input(f"Keyword for {s}", value=s)

        if st.button("Process SAP Data"):
            for s in ALL_SEGMENTS:
                keyword = mapping[s].lower()
                filt = sap_df[sap_df[seg_col].astype(str).str.lower().str.contains(keyword, na=False)]

                act_val = filt[act_col].sum()
                tar_val = filt[tar_col].sum() if tar_col != "None" else 1.0

                sap_entries.append({
                    "name": s,
                    "act": float(act_val),
                    "tar": float(tar_val)
                })

            st.success("SAP Data Processed")

    except Exception as e:
        st.error(f"SAP Error: {e}")

# ---------------- RUN ----------------
if st.button("RUN FORENSIC ANALYSIS"):

    if not entries:
        st.error("Upload a statement first")
    else:
        weights = PROFILES["Standard AE / SMME"]["statement"]

        mid_curr = (Decimal(MIDPOINTS_CURRENT['130']) / 12).quantize(Decimal('0.01'))

        ta = sum(Decimal(str(e["act"])) for e in entries)
        tt = sum(Decimal(str(e["tar"])) for e in entries)

        rev_ach = (ta / tt * 100) if tt > 0 else Decimal('0')
        m = get_mult(rev_ach)

        m_pay = mid_curr * m

        applied = run_scenario(entries, mid_curr, weights, m_pay)

        rep = "--- STATEMENT CALCULATION ---\n"
        rep += "\n".join(applied["lines"])
        rep += f"\nTOTAL COMMISSION: R {applied['tot']:,.2f}\n\n"

        # ---------------- SAP EXTENSION ----------------
        if sap_entries:
            rep += "\n--- SAP RECONCILIATION ---\n\n"
            rep += f"{'STREAM':<23}{'STMT':>12}{'SAP':>12}{'VAR':>12}\n"

            total_stmt = Decimal('0')
            total_sap = Decimal('0')

            for s in ALL_SEGMENTS:
                stmt_val = next(e["act"] for e in entries if e["name"] == s)
                sap_val = next((e["act"] for e in sap_entries if e["name"] == s), 0)

                var = Decimal(str(sap_val)) - Decimal(str(stmt_val))

                total_stmt += Decimal(str(stmt_val))
                total_sap += Decimal(str(sap_val))

                rep += f"{s:<23}{stmt_val:>12,.2f}{sap_val:>12,.2f}{var:>12,.2f}\n"

            rep += "\n"

            ta_sap = sum(Decimal(str(e["act"])) for e in sap_entries)
            tt_sap = sum(Decimal(str(e["tar"])) for e in sap_entries)

            rev_ach_sap = (ta_sap / tt_sap * 100) if tt_sap > 0 else Decimal('0')
            m_sap = get_mult(rev_ach_sap)

            m_pay_sap = mid_curr * m_sap

            sap_calc = run_scenario(sap_entries, mid_curr, weights, m_pay_sap)

            rep += f"\nCORRECT COMMISSION (SAP): R {sap_calc['tot']:,.2f}\n"
            rep += f"UNDERPAYMENT: R {(sap_calc['tot'] - applied['tot']):,.2f}\n"

        st.code(rep)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, rep)

        st.download_button(
            "Download PDF",
            pdf.output(dest='S').encode('latin-1'),
            "forensic_report.pdf"
        )
