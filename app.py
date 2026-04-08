import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Forensic Commission Audit System", layout="wide")

ALL_SEGMENTS = [
    "Digital", "Radio Classic", "Radio Sponsorship",
    "Radio Sport Sponsorship", "TV Classic",
    "TV Sponsorship", "TV Sport Sponsorship"
]

PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
                      "Radio Sponsorship": 15.0, "Digital": 5.0,
                      "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5}
    }
}

MIDPOINTS_CURRENT = {
    '130': 944928, '125': 1228406, '120': 1724250
}

# ---------------- MULTIPLIER ----------------
def get_multiplier_from_pct(pct):
    pct = Decimal(str(pct))
    if pct < 100: return Decimal('0.00')
    elif pct == 100: return Decimal('0.50')
    elif pct <= 120: return Decimal('1.00')
    elif pct <= 150: return Decimal('2.10')
    elif pct <= 180: return Decimal('4.10')
    else: return Decimal('6.20')

# ---------------- SCENARIO ENGINE ----------------
def run_scenario(entries, midpoint, weights, multiplier_pay):
    total = Decimal('0')
    for e in entries:
        act = Decimal(str(e["act"]))
        tar = Decimal(str(e["tar"]))
        weight = Decimal(str(weights.get(e["name"], 0))) / 100

        if tar > 0 and act / tar >= 1:
            total += midpoint * weight

    return max(total, multiplier_pay)

# ---------------- FILE EXTRACTION ----------------
@st.cache_data
def extract_file_data(file_obj):
    data = {s: {"act": 0.0, "tar": 1.0} for s in ALL_SEGMENTS}

    try:
        bytes_data = file_obj.read()

        if file_obj.name.endswith(".pdf"):
            reader = PyPDF2.PdfReader(io.BytesIO(bytes_data))
            text = ""
            for p in reader.pages:
                text += p.extract_text() or ""

            for s in ALL_SEGMENTS:
                match = re.search(rf"{s}.*?(\d[\d,]+\.\d{{2}}).*?(\d[\d,]+\.\d{{2}})", text)
                if match:
                    data[s]["act"] = float(match.group(1).replace(",", ""))
                    data[s]["tar"] = float(match.group(2).replace(",", ""))

        elif file_obj.name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(bytes_data))

        elif file_obj.name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(bytes_data))

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

# ---------------- SAP PROCESSING ----------------
def process_sap(df, segment_col, actual_col, target_col, mapping):
    sap_entries = []

    for seg in ALL_SEGMENTS:
        keyword = mapping[seg].lower()

        filt = df[df[segment_col].str.lower().str.contains(keyword, na=False)]

        act = filt[actual_col].sum()
        tar = filt[target_col].sum() if target_col else 1

        sap_entries.append({"name": seg, "act": act, "tar": tar})

    return sap_entries

# ---------------- RECON ----------------
def reconcile(stmt, sap):
    rows = []
    for seg in ALL_SEGMENTS:
        s_val = stmt[seg]["act"]
        sap_val = next(e["act"] for e in sap if e["name"] == seg)
        diff = sap_val - s_val
        rows.append((seg, s_val, sap_val, diff))
    return rows

# ---------------- REPORT ----------------
def build_report(recon_rows, paid, correct):
    rep = "FORENSIC REPORT\n\n"

    rep += "DATA RECONCILIATION\n"
    rep += "-"*70 + "\n"
    rep += f"{'SEGMENT':<25}{'STATEMENT':>15}{'SAP':>15}{'VAR':>15}\n"

    for r in recon_rows:
        rep += f"{r[0]:<25}{r[1]:>15,.2f}{r[2]:>15,.2f}{r[3]:>15,.2f}\n"

    rep += "\n"
    rep += f"PAID: R {paid:,.2f}\n"
    rep += f"CORRECT: R {correct:,.2f}\n"
    rep += f"UNDERPAYMENT: R {correct - paid:,.2f}\n\n"

    rep += "FORENSIC DECLARATION:\n"
    rep += "SAP treated as system of record. Variances indicate potential underpayment.\n"

    return rep

# ---------------- UI ----------------
st.title("Forensic Commission Audit System")

# Upload Statement
stmt_file = st.file_uploader("Upload Commission Statement", type=["pdf","csv","xlsx"])

stmt_data = None
if stmt_file:
    stmt_data = extract_file_data(stmt_file)
    st.success("Statement Loaded")

# SAP Upload
sap_file = st.file_uploader("Upload SAP Data", type=["xlsx","csv"])

sap_df = None
if sap_file:
    if sap_file.name.endswith(".xlsx"):
        sap_df = pd.read_excel(sap_file)
    else:
        sap_df = pd.read_csv(sap_file)

# Mapping
sap_entries = []
if sap_df is not None:
    st.subheader("Map SAP Columns")

    seg_col = st.selectbox("Segment Column", sap_df.columns)
    act_col = st.selectbox("Actual Column", sap_df.columns)
    tar_col = st.selectbox("Target Column", ["None"] + list(sap_df.columns))

    mapping = {}
    for seg in ALL_SEGMENTS:
        mapping[seg] = st.text_input(f"Keyword for {seg}", seg)

    if st.button("Process SAP"):
        sap_entries = process_sap(
            sap_df,
            seg_col,
            act_col,
            None if tar_col=="None" else tar_col,
            mapping
        )
        st.success("SAP Processed")

# Run Analysis
if st.button("RUN FORENSIC ANALYSIS"):

    if not stmt_data or not sap_entries:
        st.error("Upload both Statement and SAP data")
    else:
        weights = PROFILES["Standard AE / SMME"]["statement"]

        midpoint = Decimal(MIDPOINTS_CURRENT['130']) / 12

        # Statement calc
        stmt_entries = [
            {"name": s, "act": stmt_data[s]["act"], "tar": stmt_data[s]["tar"]}
            for s in ALL_SEGMENTS
        ]

        ta = sum(e["act"] for e in stmt_entries)
        tt = sum(e["tar"] for e in stmt_entries)

        pct = (ta/tt)*100 if tt>0 else 0
        mult = get_multiplier_from_pct(pct)

        paid = run_scenario(stmt_entries, midpoint, weights, midpoint*mult)

        # SAP calc
        ta2 = sum(e["act"] for e in sap_entries)
        tt2 = sum(e["tar"] for e in sap_entries)

        pct2 = (ta2/tt2)*100 if tt2>0 else 0
        mult2 = get_multiplier_from_pct(pct2)

        correct = run_scenario(sap_entries, midpoint, weights, midpoint*mult2)

        recon_rows = reconcile(stmt_data, sap_entries)

        report = build_report(recon_rows, paid, correct)

        st.code(report)

        # PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Courier", size=8)
        pdf.multi_cell(0, 4, report)

        st.download_button(
            "Download PDF",
            pdf.output(dest='S').encode('latin-1'),
            "forensic_report.pdf"
        )
