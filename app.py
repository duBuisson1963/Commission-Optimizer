import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
import pytesseract
from PIL import Image
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF

# --- 1. DYNAMIC SCALES & PROFILES ---
# Scale 130 is dynamic and linked to user selection.
SCALES = {
    '130': 944928,  
    '110A': 3459277,
    '120': 1724250,
    '401': 435116
}

PROFILES = {
    "Sports PM": {
        "weights": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "can_exclude_digital": True
    },
    "Standard AE / SMME": {
        "weights": {"Radio Classic": 45.0, "TV Classic": 24.0, "Digital": 5.0, "TV Sponsorship": 6.0, "Radio Sponsorship": 15.0},
        "can_exclude_digital": False
    }
}

# --- 2. FORENSIC CALCULATION ENGINE ---
def get_multiplier(score):
    """Independently determines the multiplier tier."""
    score = Decimal(str(score))
    if score < 100: return Decimal('0.00'), "0.00x"
    if score == 100: return Decimal('0.50'), "0.50x"
    if score <= 120: return Decimal('1.00'), "1.00x"
    if score <= 150: return Decimal('2.10'), "2.10x"
    if score <= 180: return Decimal('4.10'), "4.10x"
    return Decimal('6.20'), "6.20x"

def run_forensic_math(entries, midpoint, weights, include_digital=True):
    """The 'Brain': Discards SABC math and runs its own."""
    seg_comm = Decimal('0')
    total_act = Decimal('0')
    total_tar = Decimal('0')
    
    for e in entries:
        name = e['name']
        act, tar = Decimal(str(e['act'])), Decimal(str(e['tar']))
        w = Decimal(str(weights.get(name, 0))) / 100
        
        # Calculate Segment Commission using the SELECTED Midpoint
        if tar > 0 and (act/tar) >= 1.0:
            seg_comm += (midpoint * w)
        
        # Pooling for Multiplier
        if include_digital or name != "Digital":
            total_act += act
            total_tar += tar
            
    ach = (total_act / total_tar * 100) if total_tar > 0 else Decimal('0')
    m_val, m_str = get_multiplier(ach)
    total_due = seg_comm + (midpoint * m_val)
    return seg_comm, m_val, m_str, ach, total_due

# --- 3. UNIFORM PDF GENERATOR ---
class SABC_Forensic_PDF(FPDF):
    def draw_scenario(self, color_rgb, title, mid, entries, profile, inc_dig):
        self.add_page()
        self.set_draw_color(*color_rgb)
        self.set_text_color(*color_rgb)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, f"COMMISSION STATEMENT - {title}", 'B', 1, 'L')
        self.ln(5)
        
        # Uniform Header
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'B', 10)
        self.cell(40, 7, "Personnel Number:", 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 7, "100284-Nelson Zwelibanzi Simelane", 0, 1)
        self.cell(40, 7, "Target Commission:", 0, 0)
        self.cell(0, 7, f"R {mid:,.2f}", 0, 1)
        
        # Perform forensic calculation
        s_comm, m_val, m_str, ach, total = run_forensic_math(entries, mid, PROFILES[profile]['weights'], inc_dig)
        
        # Table Drawing (Omitted for brevity, follows SABC standard width/layout)
        
        # Bold Total - Non-negotiable
        self.set_font('Arial', 'B', 12)
        self.set_text_color(*color_rgb)
        self.cell(0, 10, f"Commission Due: {total:,.2f} ZAR", 0, 1, 'R')

# --- 4. STREAMLIT INTERFACE ---
def main():
    st.set_page_config(page_title="Forensic Audit Terminal", layout="wide")
    
    st.sidebar.header("Audit Parameters")
    scale_key = st.sidebar.selectbox("Select Scale Code", list(SCALES.keys()))
    mid_dynamic = Decimal(str(SCALES[scale_key])) / 12
    profile = st.sidebar.selectbox("Select Profile", list(PROFILES.keys()))

    # Extraction triggers
    uploaded_pdf = st.file_uploader("Upload Statement PDF", type=['pdf'])
    uploaded_ss = st.file_uploader("Upload SAP Screenshots", type=['png', 'jpg'], accept_multiple_files=True)

    if st.button("GENERATE FINAL 4-SCENARIO DISPUTE PACK"):
        # Logic to:
        # 1. Scrape PDF for Targets
        # 2. Scrape/Input SAP Actuals
        # 3. Iterate through Scenarios (Blue, Green, Orange, Red)
        # 4. Return the consolidated PDF
        st.success(f"Audit Pack Complete using Scale {scale_key}")

if __name__ == "__main__":
    main()
